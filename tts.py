import asyncio
import glob
import edge_tts
import pyttsx3
import sherpa_onnx
import numpy as np
import soundfile as sf
from function import *
import roles
import voice_gate as _voice_gate  # 防自录：向 asr.py 传递"TTS 正在输出"状态

vits_model_dir = f"{vits_target_dir}/{vits_model_name}"
vits_tts = None
try:
    vits_model_path = glob.glob(os.path.join(vits_model_dir, "*.onnx"))[0]
    vits_tokens_path = f"{vits_model_dir}/tokens.txt"
    vits_lexicon_path = f"{vits_model_dir}/lexicon.txt"
    vits_dict_dir = f"{vits_model_dir}/dict"
    vits_tts_config = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
        vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=vits_model_path, lexicon=vits_lexicon_path,
                                                   tokens=vits_tokens_path, dict_dir=vits_dict_dir), provider="cpu",
        num_threads=int(os.cpu_count()) - 1))
except Exception as e1:
    print(f"VITS模型加载错误，详情：{e1}")
voice_path = 'data/cache/cache_voice.mp3'
voice_path_wav = 'data/cache/cache_voice.wav'  # 用于WAV格式的TTS引擎
lang_mapping = {"中文": "zh", "英语": "uk", "日语": "jp"}
select_lang = lang_mapping.get(paddle_lang, "kor")
edge_speaker_mapping = {"晓艺-年轻女声": "zh-CN-XiaoyiNeural", "晓晓-成稳女声": "zh-CN-XiaoxiaoNeural",
                        "云健-大型纪录片男声": "zh-CN-YunjianNeural",
                        "云希-元气少年男声(推荐)": "zh-CN-YunxiNeural",
                        "云夏-年轻男声": "zh-CN-YunxiaNeural", "云扬-成稳男声": "zh-CN-YunyangNeural",
                        "晓北-辽宁话女声": "zh-CN-liaoning-XiaobeiNeural",
                        "晓妮-陕西话女声": "zh-CN-shaanxi-XiaoniNeural", "晓佳-粤语成稳女声": "zh-HK-HiuGaaiNeural",
                        "晓满-粤语年轻女声": "zh-HK-HiuMaanNeural", "云龙-粤语男声": "zh-HK-WanLungNeural",
                        "晓辰-台湾话年轻女声": "zh-TW-HsiaoChenNeural", "晓宇-台湾话成稳女声": "zh-TW-HsiaoYuNeural",
                        "云哲-台湾话男声": "zh-TW-YunJheNeural", "佳太-日语男声": "ja-JP-KeitaNeural"}
edge_select_speaker = edge_speaker_mapping.get(edge_speaker, "ja-JP-NanamiNeural")
play_tts_flag = 0
try:
    x3_engine = pyttsx3.init()
except Exception as e1:
    print(f"pyttsx3初始化错误，详情：{e1}")

# ===== pygame mixer 全局初始化（只一次，永不退出）=====
_mixer_inited = False
try:
    # 先 quit 确保干净状态（防止之前被意外 quit）
    try: pg.mixer.quit()
    except: pass
    pg.mixer.init(frequency=24000)
    _mixer_inited = True
    print("✓ 音频混音器初始化成功")
except Exception as e:
    print(f"✗ 音频混音器初始化失败: {e}")


def _ensure_mixer():  # 确保音频混音器已初始化；外接设备接入后自动重试(无需重启软件)
    global _mixer_inited
    if _mixer_inited:
        return True
    try:
        try: pg.mixer.quit()
        except: pass
        pg.mixer.init(frequency=24000)
        _mixer_inited = True
        print("✓ 音频混音器重新初始化成功")
        return True
    except Exception as e:
        print(f"✗ 音频混音器仍不可用: {e}")
        return False



def stop_tts():  # 停止播放
    global play_tts_flag
    play_tts_flag = 0
    try:
        pg.mixer.music.stop()
    except:
        pass
    _voice_gate.set_tts_busy(False)  # 防自录：停止输出，恢复麦克风（随后进入短暂冷却）


def _release_voice_file():  # 释放 mixer 对音频文件的锁定，允许后续覆盖写
    """pygame 的 music.load() 会锁定音频文件，stop() 后仍不释放，
    导致下一次 TTS 覆盖写 cache 音频时在 Windows 上报 Permission denied / Error opening。
    必须调用 music.unload() 才能释放文件句柄。"""
    try:
        if pg.mixer.get_init():
            pg.mixer.music.stop()
            try:
                pg.mixer.music.unload()
            except:
                pass
    except:
        pass


# ===== 英文/数字 → 中文读法转换（内置VITS模型只支持中文，需先转换才能读英文和数字）=====
NUMBER_CN = {'0': '零', '1': '一', '2': '二', '3': '三', '4': '四', '5': '五', '6': '六', '7': '七', '8': '八', '9': '九'}
LETTER_CN = {
    'a': '诶', 'b': '比', 'c': '西', 'd': '迪', 'e': '伊', 'f': '艾弗', 'g': '吉',
    'h': '艾尺', 'i': '艾', 'j': '杰', 'k': '开', 'l': '艾勒', 'm': '艾姆', 'n': '艾恩',
    'o': '欧', 'p': '屁', 'q': '吉欧', 'r': '阿尔', 's': '艾丝', 't': '提', 'u': '优',
    'v': '维', 'w': '达不溜', 'x': '艾克斯', 'y': '歪', 'z': '贼'}


def _num_to_cn(num_str):  # 阿拉伯数字转中文数值读法（支持亿级以下）
    if not num_str.isdigit():
        return num_str
    n = int(num_str)
    if n == 0:
        return '零'
    digits = '零一二三四五六七八九'

    def read_group(g):  # 读 0~9999 一组
        if g == 0:
            return ''
        s = ''
        q, b, shi, ge = g // 1000, (g % 1000) // 100, (g % 100) // 10, g % 10
        if q:
            s += digits[q] + '千'
        if b:
            s += digits[b] + '百'
        elif q and (shi or ge):
            s += '零'
        if shi:
            s += '十' if (shi == 1 and not s) else digits[shi] + '十'
        elif b and ge:
            s += '零'
        if ge:
            s += digits[ge]
        return s

    yi = n // 100000000
    wan = (n % 100000000) // 10000
    rest = n % 10000
    parts = []
    if yi:
        parts.append(read_group(yi) + '亿')
    if wan:
        parts.append(read_group(wan) + '万')
    elif (yi or wan) and rest and rest < 1000:
        parts.append('零')
    if rest:
        parts.append(read_group(rest))
    return ''.join(parts)


def _convert_to_chinese_readable(text):  # 把英文和数字转换为中文读法
    import re
    # 1) 数字 → 中文（≥5位按逐位读，如手机号/编号；否则按数值读）
    def num_repl(m):
        s = m.group(0)
        if len(s) >= 5:
            return ''.join(NUMBER_CN[c] for c in s)
        return _num_to_cn(s)

    text = re.sub(r'\d+', num_repl, text)
    # 2) 英文字母/单词 → 逐字母中文读音（如 AI → 诶艾）
    def letter_repl(m):
        return ''.join(LETTER_CN.get(c.lower(), c) for c in m.group(0))

    text = re.sub(r'[A-Za-z]+', letter_repl, text)
    return text


def tts_vits(text, out_path=None, release=True):  # 内置VITS — 生成单段语音
    global vits_tts
    if vits_tts is None:
        vits_tts = sherpa_onnx.OfflineTts(vits_tts_config)
    target = out_path if out_path else voice_path_wav
    text = _convert_to_chinese_readable(text)  # 英文/数字转中文读法（VITS仅支持中文）
    audio = vits_tts.generate(text, sid=0, speed=1.0)
    if release:  # 释放 mixer 对音频文件的锁定，否则覆盖写会失败（流式播放时由事件同步保证，不在此打断播放）
        _release_voice_file()
    if vits_model_name == "sherpa-onnx-vits-zh-ll":
        samples = np.array(audio.samples, dtype=np.float32)
        amplified_samples = samples * 4  # 音量放大4倍
        amplified_samples = np.clip(amplified_samples, -1.0, 1.0)
        amplified_samples_int16 = (amplified_samples * 32767).astype(np.int16)
        sf.write(target, amplified_samples_int16, samplerate=audio.sample_rate, subtype="PCM_16", format="wav")
    else:
        sf.write(target, audio.samples, samplerate=audio.sample_rate, subtype="PCM_16", format="wav")


def tts_vits_full(text_segments):  # 内置VITS — 合并全部片段为一段完整语音
    """把所有文本片段合成到同一个WAV文件，实现流畅不间断播放"""
    global vits_tts
    if vits_tts is None:
        vits_tts = sherpa_onnx.OfflineTts(vits_tts_config)
    all_samples = []
    sample_rate = None
    for segment in text_segments:
        if play_tts_flag != 1:
            break
        audio = vits_tts.generate(_convert_to_chinese_readable(segment), sid=0, speed=1.0)
        if sample_rate is None:
            sample_rate = audio.sample_rate
        samples = np.array(audio.samples, dtype=np.float32)
        all_samples.append(samples)
    if not all_samples:
        return
    full_audio = np.concatenate(all_samples)
    amplified = np.clip(full_audio * 4, -1.0, 1.0)
    amplified_int16 = (amplified * 32767).astype(np.int16)
    _release_voice_file()  # 先释放 mixer 对 cache_voice.wav 的锁定，否则覆盖写会失败
    sf.write(voice_path_wav, amplified_int16, samplerate=sample_rate, subtype="PCM_16", format="wav")


def _current_role_voice():  # 大屏双角色：当前角色的TTS音色（非实时引擎用）
    """返回当前角色配置的阿里云音色ID；未配置/占位时回退到 custom_tts_set.txt 默认音色"""
    return _current_role_tts_voice(realtime=False)


# ===================== 阿里云实时TTS（qwen-tts 实时语音合成）=====================
# 使用 DashScope SDK 的 QwenTtsRealtime（WebSocket 流式），依赖 dashscope>=1.25.11。
# 模型按音色自动选择：
#   - 系统音色(如 Ethan/Serena/Cherry)  → qwen3-tts-flash-realtime（稳定版，已验证）
#   - 声音设计音色(qwen-tts-vd-*前缀)   → qwen3-tts-vd-realtime-2026-01-15
#   - 声音复刻音色(qwen-tts-vc-*前缀)   → qwen3-tts-vc-realtime-2026-01-15
# 重要：声音设计/复刻音色绑定"创建时指定的 target_model"，合成模型必须与之一致。
#   现有的 qwen-tts-vd-bailian-voice-... 音色是为非实时 qwen-tts 创建的，实时模型不可用。
#   如需自定义音色走实时合成，请在百炼控制台用声音设计重建，target_model 选 qwen3-tts-vd-realtime-2026-01-15。
REALTIME_TTS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"  # 华北2（北京）地域；新加坡请用 wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime
_realtime_tts_ready = False
try:
    import dashscope as _dashscope
    from dashscope.audio.qwen_tts_realtime import (
        QwenTtsRealtime as _QwenTtsRealtime,
        QwenTtsRealtimeCallback as _QwenTtsRealtimeCallback,
        AudioFormat as _QwenAudioFormat,
    )
    _realtime_tts_ready = True
except Exception as _e:
    print(f"[阿里云实时TTS] dashscope SDK 未就绪，请安装 dashscope>=1.25.11：{_e}")


def _current_role_tts_cfg(key, default=''):  # 大屏双角色：读取角色的实时TTS附加配置
    """读取 roles.json 里的实时TTS附加项（实时TTS模型/实时TTS语速/实时TTS音调/实时TTS指令）；
    未配置或还是占位符时返回 default。"""
    try:
        val = (roles.get_current_role().get(key) or '').strip()
        if val and "__待填" not in val:
            return val
    except Exception:
        pass
    return default


def _realtime_tts_model(voice):
    """选择实时合成模型：
    1) 角色显式配置了「实时TTS模型」→ 用它（例如需要"指令控制"来稳定语速语调时，
       用 qwen3-tts-instruct-flash-realtime）；
    2) 否则按音色前缀自动选（声音设计/复刻音色必须与创建音色时的模型一致）。"""
    explicit = _current_role_tts_cfg('实时TTS模型')
    if explicit:
        return explicit
    v = (voice or "").strip()
    if v.startswith("qwen-tts-vd-"):
        return "qwen3-tts-vd-realtime-2026-01-15"
    if v.startswith("qwen-tts-vc-"):
        return "qwen3-tts-vc-realtime-2026-01-15"
    return "qwen3-tts-flash-realtime"


def _realtime_session_extras():  # 角色级语速/音调/指令（可选项，没配置就不传）
    """speech_rate 语速(1.0=正常)、pitch_rate 音调(1.0=正常)、
    instructions 自然语言指令（控制语气、语速、情感等表现力）。"""
    extra = {}
    sr = _current_role_tts_cfg('实时TTS语速')
    if sr:
        try:
            extra['speech_rate'] = float(sr)
        except Exception:
            print(f"[阿里云实时TTS] 实时TTS语速配置无效：{sr}")
    pr = _current_role_tts_cfg('实时TTS音调')
    if pr:
        try:
            extra['pitch_rate'] = float(pr)
        except Exception:
            print(f"[阿里云实时TTS] 实时TTS音调配置无效：{pr}")
    ins = _current_role_tts_cfg('实时TTS指令')
    if ins:
        extra['instructions'] = ins
    return extra


def _current_role_tts_voice(realtime=False):
    """当前角色TTS音色：realtime=True 时优先取 实时TTS音色 字段，否则取 TTS音色 字段；
    未配置/占位时回退到 custom_tts_set.txt 默认音色。"""
    try:
        role = roles.get_current_role()
        if realtime:
            voice = (role.get("实时TTS音色") or "").strip()
            if voice and "__待填" not in voice:
                return voice
        voice = (role.get("TTS音色") or "").strip()
        if voice and "__待填" not in voice:
            return voice
    except Exception:
        pass
    return custom_tts_voice


def _write_pcm_wav(path, pcm_bytes, sample_rate=24000):
    """PCM裸数据写为WAV（实时合成输出为 24000Hz 单声道16bit）"""
    import wave as _wave
    _release_voice_file()  # 释放 mixer 文件锁，防止覆盖写失败
    with _wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm_bytes)


def _synthesize_realtime_segment(text, out_path, use_extras=True):
    """单段文本阿里云实时合成 → 写入 WAV，返回 out_path；失败抛异常。
    use_extras=False 时不传语速/音调/指令（作为参数不被服务端支持时的降级重试）。"""
    import base64 as _b64
    import threading as _th
    if not _realtime_tts_ready:
        raise Exception("未安装 dashscope>=1.25.11，无法使用阿里云实时TTS")
    _dashscope.api_key = custom_tts_key  # QwenTtsRealtime 构造时读取 dashscope.api_key
    voice = _current_role_tts_voice(realtime=True)
    model = _realtime_tts_model(voice)
    done = _th.Event()
    finished = [False]  # 是否收到 session.finished（音频完整收完）
    chunks = []
    err = {}

    class _CB(_QwenTtsRealtimeCallback):
        def on_open(self):
            pass

        def on_event(self, response):
            try:
                t = response.get('type', '')
                if t == 'response.audio.delta':
                    chunks.append(_b64.b64decode(response['delta']))
                elif t == 'session.finished':
                    finished[0] = True
                    done.set()
                elif t == 'error':
                    e = response.get('error', {})
                    err['msg'] = f"{e.get('code', '')}: {e.get('message', str(response))}"
                    done.set()
            except Exception as e:
                err['msg'] = str(e)
                done.set()

        def on_close(self, code, msg):
            done.set()

    rt = _QwenTtsRealtime(model=model, callback=_CB(), url=REALTIME_TTS_URL)
    try:
        rt.connect()
        _extras = _realtime_session_extras() if use_extras else {}
        rt.update_session(voice=voice, response_format=_QwenAudioFormat.PCM_24000HZ_MONO_16BIT,
                          mode='server_commit', language_type='Chinese', **_extras)
        rt.append_text(text)
        rt.finish()
        # 轮询等待完成：被 stop_tts() 中断(play_tts_flag=0)时尽快中止，避免卡住后续流程
        import time as _time
        _deadline = _time.time() + 60
        while not done.is_set() and play_tts_flag == 1:
            if _time.time() >= _deadline:
                break
            _time.sleep(0.05)
        if not done.is_set():
            raise Exception("实时合成超时或已中断")
        if err.get('msg'):
            raise Exception(f"实时合成失败({model}/{voice})：{err['msg']}")
        if not finished[0]:
            raise Exception(f"实时合成连接中断，音频不完整({model}/{voice})")
        if not chunks:
            raise Exception(f"实时合成未返回音频({model}/{voice})")
        _write_pcm_wav(out_path, b''.join(chunks))
        return out_path
    finally:
        try:
            rt.close()
        except Exception:
            pass


def custom_tts_realtime(text):
    """整段文本实时合成 → 返回WAV路径（兜底：合并整段播放，首响延迟较高）"""
    return _synthesize_realtime_segment(text, voice_path_wav)


_realtime_blocked_until = 0  # 实时TTS WebSocket 失败的冷却截止时间(秒时间戳)


def _tts_realtime_play_full(text):
    """整段文本单会话实时合成 → 一次性完整播放。成功返回 True，失败返回 False(不弹窗)。
    失败由 _tts_alibaba_play 决定是否回退到非实时 HTTP qwen-tts。"""
    if not _realtime_tts_ready:
        print("[阿里云实时TTS] dashscope SDK 未就绪，无法使用")
        return False
    _dashscope.api_key = custom_tts_key
    for attempt in range(2):
        try:
            # 第一次带上角色的语速/音调/指令；失败则去掉这些参数再试一次（防止服务端不支持导致完全无声）
            _synthesize_realtime_segment(text, voice_path_wav, use_extras=(attempt == 0))
            if play_tts_flag == 1:
                _play_voice(voice_path_wav)
            return True
        except Exception as e:
            if play_tts_flag != 1:
                return False  # 用户主动停止，不再重试
            print(f"[阿里云实时TTS] 第{attempt + 1}次合成失败：{e}")
    return False


def _tts_alibaba_play(text):
    """阿里云整段合成播放：优先实时TTS(WebSocket)；连接失败自动回退到非实时HTTP qwen-tts。
    解决部分网络/防火墙拦截 WebSocket(api-ws 端点) 但 HTTPS 正常导致的实时合成失败。
    实时失败后进入 120 秒冷却，期间直接走 HTTP，避免每次回复都白等 WebSocket 连接超时。"""
    global _realtime_blocked_until
    import time as _time
    if _time.time() >= _realtime_blocked_until and _tts_realtime_play_full(text):
        return
    _realtime_blocked_until = _time.time() + 120  # 实时不可用 → 后续 120s 直接走 HTTP 回退
    print("[阿里云TTS] 实时(WebSocket)不可用，自动回退到非实时HTTP qwen-tts...")
    try:
        if play_tts_flag != 1:
            return
        _out = custom_tts(text)
        if play_tts_flag == 1:
            _play_voice(_out)
    except Exception as e:
        print(f"[阿里云TTS] 非实时HTTP回退也失败：{e}")
        notice("阿里云TTS合成失败：实时(WebSocket)与非实时(HTTP)均不可用，请检查网络或custom_tts_set.txt配置")


def custom_tts(text):  # 自定义TTS（支持阿里云百炼 qwen-tts 原生协议，以及 OpenAI 兼容服务商）
    import requests as _rq
    # ---- 阿里云百炼：compatible-mode 不支持 /audio/speech，需走原生 multimodal-generation ----
    if "dashscope.aliyuncs.com" in custom_tts_url:
        ep = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
        body = {
            "model": custom_tts_model,     # 例如 qwen-tts
            "input": {"text": text},
            "voice": _current_role_voice(),  # 当前角色的音色（大屏双角色）
            "parameters": {"format": "wav"},
            "stream": False,
        }
        resp = _rq.post(ep, headers={"Authorization": f"Bearer {custom_tts_key}",
                                     "Content-Type": "application/json"}, json=body, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        audio_url = data.get("output", {}).get("audio", {}).get("url")
        if not audio_url:
            raise Exception(f"百炼TTS未返回音频地址: {str(data)[:200]}")
        audio_resp = _rq.get(audio_url, timeout=60)
        audio_resp.raise_for_status()
        _release_voice_file()  # 释放 mixer 对音频文件的锁定
        with open(voice_path_wav, "wb") as f:
            f.write(audio_resp.content)
        return voice_path_wav
    # ---- 其他 OpenAI 兼容服务商 ----
    client = OpenAI(api_key=custom_tts_key, base_url=custom_tts_url)
    with client.audio.speech.with_streaming_response.create(
            model=custom_tts_model, voice=_current_role_voice(), input=text, response_format="mp3") as response:
        response.stream_to_file(voice_path)
    return voice_path


def _play_voice(file_path=None):  # 播放音频（模块级，供流式播放与 get_tts_play 复用）
    """播放音频，不初始化/退出mixer（已在全局初始化）"""
    import os as _os
    if not _ensure_mixer():
        print("[TTS] 混音器未初始化，无法播放")
        return
    if file_path is None:
        file_path = voice_path
    if not _os.path.exists(file_path):
        print(f"[TTS] 音频文件不存在: {file_path}")
        return
    file_size = _os.path.getsize(file_path)
    print(f"[TTS] 播放: {file_path} ({file_size} bytes)")
    try:
        pg.mixer.music.load(file_path)
        pg.mixer.music.play()
        while pg.mixer.music.get_busy() and play_tts_flag == 1:
            pg.time.Clock().tick(1)
        pg.mixer.music.stop()
        _release_voice_file()  # 播放完毕立即释放文件锁，下次 TTS 才能覆盖写同一文件
    except Exception as e:
        print(f"[TTS播放错误] {file_path}: {e}")
        _release_voice_file()


def _tts_vits_stream(segments):  # 流式合成+播放VITS语音（显著缩短首响延迟）
    """相比"一次性合成全部再播放"，本函数让第一段合成完(约1s)就立即出声，
    同时后台预合成后续段落，播放时无缝衔接，大幅缩短文字→音频的间隔。
    使用两个轮换文件 + 事件同步，确保不会与正在播放的文件冲突。"""
    from queue import Queue
    import threading as _th
    paths = [voice_path_wav, 'data/cache/cache_voice_2.wav']
    released = [_th.Event(), _th.Event()]
    released[0].set()  # 初始两个文件均可写入
    released[1].set()
    seg_queue = Queue()

    def producer():
        try:
            for i, segment in enumerate(segments):
                if play_tts_flag != 1:
                    break
                idx = i % 2
                released[idx].wait()  # 等待该文件被播放完毕释放（防覆盖正在播放的文件）
                released[idx].clear()
                tts_vits(segment, out_path=paths[idx], release=False)
                seg_queue.put((paths[idx], idx))
        finally:
            seg_queue.put(None)  # 结束标记

    def consumer():
        while True:
            item = seg_queue.get()
            if item is None:
                break
            path, idx = item
            if play_tts_flag == 1:
                _play_voice(path)  # 播完内部会释放文件锁
            released[idx].set()  # 通知 producer：该文件已释放，可写下一轮
        _voice_gate.set_tts_busy(False)  # 防自录：流式播放全部结束，解除麦克风屏蔽

    try:
        Thread(target=producer, daemon=True).start()
        Thread(target=consumer, daemon=True).start()
    except Exception:
        _voice_gate.set_tts_busy(False)  # 启动失败不要让麦克风一直被屏蔽
        raise


# open_source_project_address:https://github.com/swordswind/ai_virtual_mate_web
def get_tts_play(text):  # 语音合成并播放
    global play_tts_flag
    play_tts_flag = 1
    roles.state["speaking"] = roles.state["current"]  # 大屏双角色：标记当前说话角色(嘴型/肢体语言)

    def _active_engine():  # 大屏双角色：当前角色指定的TTS引擎优先，否则用界面选择
        try:
            return roles.get_current_role().get("TTS引擎") or tts_menu.get()
        except Exception:
            return tts_menu.get()

    engine = _active_engine()

    def play_voice(file_path=None):  # 兼容旧调用：转发到模块级实现
        return _play_voice(file_path)

    def split_text(text2):
        segments2 = re.split(r'([\n:：!！?？;；。])', text2)
        combined = []
        for i in range(0, len(segments2), 2):
            if i + 1 < len(segments2):
                combined.append(segments2[i] + segments2[i + 1])
            elif segments2[i].strip():
                combined.append(segments2[i])
        segments = [seg.strip() for seg in combined if seg.strip()]
        # 合并短片段，但不要合并太多——VITS可以一次生成全部
        MIN_SEG_LEN = 6
        merged = []
        for seg in segments:
            if merged and len(merged[-1]) < MIN_SEG_LEN:
                merged[-1] = merged[-1] + seg
            else:
                merged.append(seg)
        return merged if merged else [text2]

    async def ms_edge_tts(segment2):
        communicate = edge_tts.Communicate(segment2, edge_select_speaker, rate=f"{edge_rate}%", pitch=f"{edge_pitch}Hz")
        await communicate.save(voice_path)

    processed_text = text.split("</think>")[-1].strip().replace("#", "").replace("*", "")
    processed_text = re.sub(r'[(（].*?[)）]', '', processed_text)
    segments = split_text(processed_text)

    def get_tts_play_th():
        error_messages = {"Error opening", "Permission denied"}
        _voice_gate.set_tts_busy(True)  # 防自录：合成+播放全程屏蔽麦克风
        try:
            _release_voice_file()  # 生成前先确保 mixer 已释放音频文件锁（防上次播放残留锁定）
            if engine == "内置低延迟VITS":
                # 流式策略：第一段合成完立即播放，后续段后台预生成，缩短首响延迟且无缝衔接
                _tts_vits_stream(segments)
            elif engine == "阿里云实时TTS":
                # 阿里云整段合成：优先实时(WebSocket)，失败自动回退非实时HTTP qwen-tts
                # (兼容防火墙/网络拦截 WebSocket 但 HTTPS 正常的环境)
                _tts_alibaba_play("".join(segments))
            else:
                # 其他引擎：逐段合成+播放
                for segment in segments:
                    if play_tts_flag != 1:
                        break
                    if engine == "云端edge-tts":
                        try:
                            asyncio.run(ms_edge_tts(segment))
                            play_voice()
                        except Exception as e:
                            if "403" in str(e) or "Handshake" in str(e):
                                notice("微软edge-tts服务被限制，请切换为「内置低延迟VITS」或「自定义API-TTS」")
                                print("[TTS] edge-tts 403被禁，建议使用内置低延迟VITS")
                            else:
                                raise e
                    elif engine == "云端Paddle-TTS":
                        url = f'https://fanyi.baidu.com/gettts?lan={select_lang}&spd={paddle_rate}&text={segment}'
                        res = rq.get(url)
                        with open(voice_path, 'wb') as f:
                            f.write(res.content)
                        play_voice()
                    elif engine == "本地GPT-SoVITS":
                        url = f'http://{local_tts_ip}:{gsv_port}/tts?text={segment}&text_lang={gsv_lang}&prompt_text={gsv_prompt}&prompt_lang={gsv_prompt_lang}&ref_audio_path={gsv_ref_audio_path}'
                        try:
                            res = rq.get(url)
                            with open(voice_path, 'wb') as f:
                                f.write(res.content)
                            play_voice()
                        except Exception as e:
                            if not any(msg in str(e) for msg in error_messages):
                                notice(f"本地GPT-SoVITS整合包API服务器未开启，错误详情：{e}")
                    elif engine == "本地CosyVoice":
                        url = f'http://{local_tts_ip}:9881/cosyvoice/?text={segment}'
                        try:
                            res = rq.get(url)
                            with open(voice_path, 'wb') as f:
                                f.write(res.content)
                            play_voice()
                        except Exception as e:
                            if "Error opening" not in str(e):
                                notice(f"本地CosyVoice整合包API服务器未开启，错误详情：{e}")
                    elif engine == "本地Index-TTS":
                        url = f'http://{local_tts_ip}:9884/indextts/?text={segment}'
                        try:
                            res = rq.get(url)
                            with open(voice_path, 'wb') as f:
                                f.write(res.content)
                            play_voice()
                        except Exception as e:
                            if not any(msg in str(e) for msg in error_messages):
                                notice(f"本地Index-TTS整合包API服务器未开启，错误详情：{e}")
                    elif engine == "本地VoxCPM":
                        url = f'http://{local_tts_ip}:9885/voxcpm/?text={segment}'
                        try:
                            res = rq.get(url)
                            with open(voice_path, 'wb') as f:
                                f.write(res.content)
                            play_voice()
                        except Exception as e:
                            if not any(msg in str(e) for msg in error_messages):
                                notice(f"本地VoxCPM整合包API服务器未开启，错误详情：{e}")
                    elif engine == "系统自带TTS":
                        try:
                            x3_engine.save_to_file(segment, voice_path_wav)
                            x3_engine.runAndWait()
                            play_voice(voice_path_wav)
                        except Exception as e:
                            if not any(msg in str(e) for msg in error_messages):
                                notice("您的电脑未启用系统自带TTS，可选择其他语音合成引擎")
                    elif engine == "自定义API-TTS":
                        try:
                            full_text = "".join(segments)
                            _out_path = custom_tts(full_text)
                            play_voice(_out_path)
                        except Exception as e:
                            if not any(msg in str(e) for msg in error_messages):
                                notice(f"请前往data/set/custom_tts_set.txt正确配置自定义API-TTS，错误详情：{e}")
                        break  # 自定义API-TTS已合并全部文本，跳出循环
        except Exception as e:
            if not any(msg in str(e) for msg in error_messages):
                notice(f"{engine}服务拥挤或出错，可选择其他语音合成引擎，错误详情：{str(e)}")
        finally:
            roles.state["speaking"] = -1  # 大屏双角色：播放结束，复位说话角色(前端所有角色闭嘴)
            # 防自录：解除麦克风屏蔽；内置VITS是流式异步播放，由 _tts_vits_stream 的 consumer 结束时报
            if engine != "内置低延迟VITS":
                _voice_gate.set_tts_busy(False)

    Thread(target=get_tts_play_th).start()
