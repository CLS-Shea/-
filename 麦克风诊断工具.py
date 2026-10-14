# -*- coding: utf-8 -*-
"""麦克风诊断工具（新主机用）。
帮你在新主机上快速判断“语音识别不到声音”是硬件/系统问题还是软件问题。
用法：双击运行，或运行:  runtime/python 麦克风诊断工具.py
步骤：1) 列出麦克风  2) 逐个扫描哪个能录到声  3) 详测最佳设备 + VAD 判断
结果会保存到 麦克风诊断结果.txt（utf-8-sig）
"""
import os
import time
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

lines = []
RATE = 16000
CHUNK = 1024


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    lines.append(s)


def _record_audio(p, idx, sec):
    """非阻塞录音 sec 秒，返回音频 bytes；失败返回 b''（不会卡死）。"""
    import pyaudio
    try:
        s = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True,
                   frames_per_buffer=CHUNK, input_device_index=idx, start=False)
        s.start_stream()
    except Exception:
        return b""
    fr = []
    need = max(1, int(sec * RATE / CHUNK))
    deadline = time.time() + sec + 0.5
    while time.time() < deadline and len(fr) < need:
        try:
            if s.get_read_available() >= CHUNK:
                fr.append(s.read(CHUNK, exception_on_overflow=False))
            else:
                time.sleep(0.02)
        except Exception:
            time.sleep(0.02)
    try:
        s.stop_stream()
        s.close()
    except Exception:
        pass
    return b"".join(fr)


def level_of(audio):
    if not audio:
        return 0, 0
    smp = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
    pk = float(np.max(np.abs(smp)))
    rms = float(np.sqrt(np.mean(smp ** 2)))
    return pk, rms


def main():
    import pyaudio
    log("=" * 52)
    log("  枫云AI 麦克风诊断工具")
    log("=" * 52)

    try:
        p = pyaudio.PyAudio()
    except Exception as e:
        log(f"  ❌ PyAudio 初始化失败: {e}")
        return

    # ---- 1. 设备列表 ----
    log("\n[1] 系统识别到的输入(麦克风)设备：")
    in_devs = []
    for i in range(p.get_device_count()):
        try:
            info = p.get_device_info_by_index(i)
            if info.get('maxInputChannels', 0) > 0:
                in_devs.append(i)
                log(f"    [{i}] {info.get('name')}")
        except Exception:
            pass
    if not in_devs:
        log("  ❌ 没有任何输入设备 → Windows 层面就没识别到麦克风")
    try:
        d = p.get_default_input_device_info()
        log(f"\n  Windows 当前默认输入: [{d.get('index')}] {d.get('name')}")
    except Exception as e:
        log(f"\n  ⚠️  无默认输入设备: {e}")

    # ---- 2. 逐个测电平 ----
    log("\n[2] 逐个麦克风测声（请对着麦克风【正常说话】，每个约1秒）...")
    audio_of = {}
    for idx in in_devs[:8]:  # 最多扫 8 个，避免太久
        audio = _record_audio(p, idx, 0.9)
        pk, rms = level_of(audio)
        audio_of[idx] = audio
        if pk >= 800:
            log(f"    ✅ 设备[{idx}] 峰值={pk:.0f} RMS={rms:.1f}  ← 能录到声音！")
        elif pk >= 200:
            log(f"    ⚠️  设备[{idx}] 峰值={pk:.0f} RMS={rms:.1f}  ← 声音很小")
        else:
            log(f"    ❌ 设备[{idx}] 峰值={pk:.0f} RMS={rms:.1f}  ← 几乎静音")

    good = [(i, level_of(audio_of[i])) for i in audio_of if level_of(audio_of[i])[0] >= 800]
    best_idx, best_lv = (max(good, key=lambda x: x[1][0]) if good else (None, (0, 0)))

    if best_idx is None:
        log("\n  ❌ 所有麦克风几乎都静音（峰值都很低）")
        log("  ── 结论：这是【硬件 / 系统 / 权限】问题，不是软件问题 ──")
        log("  请按顺序排查：")
        log("  ① Windows 设置 → 隐私和安全性 → 麦克风")
        log("     → 把『允许应用访问麦克风』【打开】")
        log("     → 再往下找『允许桌面应用访问麦克风』也【打开】")
        log("     （这一步最关键：命令行/后台程序需要桌面应用权限）")
        log("  ② 右键任务栏喇叭 → 声音设置 → 输入")
        log("     → 选对你的麦克风 → 点『测试』看音量是否跳动")
        log("  ③ 确认麦克风没被静音、输入音量没拉到 0")
        log("  ④ 打开系统『录音机』App 录一段：")
        log("      - 能听到 → 麦克风硬件OK，是本程序被系统拦了权限(回到①)")
        log("      - 也录不到 → 麦克风硬件/驱动没就绪")
        audio_for_vad = b""
        best_idx = -1
    else:
        log(f"\n  ✅ 设备[{best_idx}] 能录到声音（峰值={best_lv[0]:.0f}）")
        log(f"  → 请在软件设置里把『麦克风编号』改成 {best_idx}")
        log("  → 或：Windows 声音设置里把该设备设为默认输入")
        log("\n  对该设备详测 3 秒（请正常说话）...")
        audio_for_vad = _record_audio(p, best_idx, 3.0)
        pk, rms = level_of(audio_for_vad)
        dbfs = 20 * np.log10((rms + 1e-9) / 32768)
        log(f"  详测: 峰值={pk:.0f} RMS={rms:.1f}  (约 {dbfs:.0f} dBFS)")

    # ---- 3. VAD 判断 ----
    if audio_for_vad:
        log("\n[3] 语音检测(VAD) 判断这段录音是否算“有人说话”...")
        try:
            import asr as _asr
            if _asr.vad_ready:
                win = _asr.vad_model.window_size()
                a16 = np.frombuffer(audio_for_vad, dtype=np.int16)
                voiced = total = 0
                for i in range(0, len(a16), win):
                    seg = a16[i:i + win].astype(np.float32) / 32768.0
                    if len(seg) < win:
                        seg = np.pad(seg, (0, win - len(seg)))
                    total += 1
                    if _asr.vad_model.is_speech(seg):
                        voiced += 1
                ratio = voiced / max(1, total)
                log(f"  语音帧占比: {voiced}/{total} = {ratio * 100:.0f}%")
                if ratio > 0.03:
                    log("  ✅ VAD 判定有人说话 → 录音链路正常")
                    log("  → 若软件仍不识别：把 asr.py 更新到最新，并把『麦克风编号』设为最佳设备号")
                else:
                    log("  ⚠️  VAD 几乎没判定到语音 → 确认麦克风音量/是否真出声")
            else:
                log("  (VAD 模型未加载，跳过)")
        except Exception as e:
            log(f"  VAD 检测出错: {e}")

    log("\n" + "=" * 52)
    log("总结")
    if best_idx >= 0:
        log("  ✅ 找到了能录到声音的麦克风 → 是【软件设备选择】问题")
        log("  → 软件『麦克风编号』填 " + str(best_idx) + " 即可")
        log("  → 或 Windows 声音设置里把它设为默认输入设备")
    else:
        log("  ❌ 麦克风录不到声音 → 是【硬件/系统/权限】问题")
        log("  → 重点：Windows 隐私 → 麦克风 → 允许『桌面应用』访问麦克风")
    log("=" * 52)
    try:
        with open("麦克风诊断结果.txt", "w", encoding="utf-8-sig") as f:
            f.write("\n".join(lines))
        log("\n结果已保存到: 麦克风诊断结果.txt")
    except Exception:
        pass


if __name__ == "__main__":
    main()
