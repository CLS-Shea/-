import json
import os
import re
import wave
import pyaudio
import sherpa_onnx
import numpy as np
import soundfile as sf
import voice_gate

asr_model_path = "data/model/ASR/sherpa-onnx-sense-voice-zh-en-ja-ko-yue"
# 语言列表：优先中文，去掉日韩以提升中文识别准确率
ASR_HOTWORDS = ""  # 可在此添加热词，用空格分隔，如"南京工程学院 南小橙"
vp_model_path = "data/model/SpeakerID/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
vp_config, extractor, audio1, sample_rate1, embedding1 = None, None, None, None, None
with open('data/db/config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)
asr_sensitivity = config["语音识别灵敏度"]
voiceprint_switch = config["声纹识别"]
with open('data/set/more_set.json', 'r', encoding='utf-8') as f:
    more_set = json.load(f)
mic_num = int(more_set["麦克风编号"])
voiceprint_threshold = float(more_set["声纹识别阈值"])
# 灵敏度映射：数字 = 判定"说完了"所需的最长静音时长（秒）。
# 数值越大，录音越宽容，句中停顿越不易被截断（保证完整录入）。
# 配合 record_audio 的尾部缓冲与重新激活机制，可容忍更长的句中停顿。
SILENCE_DURATION_MAP = {"高": 1.2, "中": 1.8, "低": 2.8}
SILENCE_DURATION = SILENCE_DURATION_MAP.get(asr_sensitivity, 1.2)
FORMAT = pyaudio.paInt16
CHANNELS, RATE, CHUNK = 1, 16000, 1024
SILENCE_CHUNKS = SILENCE_DURATION * RATE / CHUNK  # 静音持续的帧数
p, stream, recognizer = None, None, None
cache_path = "data/cache/cache_record.wav"
model = f"{asr_model_path}/model.int8.onnx"
tokens = f"{asr_model_path}/tokens.txt"

# 声纹模型预加载：提前加载好，避免首次使用时卡顿
vp_embedding_ready = False
audio1, sample_rate1 = None, None
try:
    if voiceprint_switch == "开启" and os.path.exists(vp_model_path) and os.path.exists("data/cache/voiceprint/myvoice.wav"):
        vp_config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=vp_model_path, debug=False, provider="cpu",
                                                                num_threads=int(os.cpu_count()) - 1)
        _vp_extractor = sherpa_onnx.SpeakerEmbeddingExtractor(vp_config)
        audio1, sample_rate1 = sf.read("data/cache/voiceprint/myvoice.wav", dtype="float32", always_2d=True)
        audio1 = audio1[:, 0]
        _vp_stream = _vp_extractor.create_stream()
        _vp_stream.accept_waveform(sample_rate=sample_rate1, waveform=audio1)
        _vp_stream.input_finished()
        embedding1 = np.array(_vp_extractor.compute(_vp_stream))
        extractor = _vp_extractor  # 复用给 verify_speakers
        vp_embedding_ready = True
        print("✓ 声纹模型预加载完成")
    else:
        vp_config = None
        extractor = None
        embedding1 = None
except Exception as e:
    print(f"声纹模型预加载失败（可忽略）: {e}")
    vp_config = None
    extractor = None
    embedding1 = None


def rms(data):  # 计算音频数据的均方根（先转float32，避免int16平方溢出为NaN）
    return np.sqrt(np.mean(np.frombuffer(data, dtype=np.int16).astype(np.float32) ** 2))


def dbfs(rms_value):  # 将均方根转换为分贝满量程（dBFS）
    return 20 * np.log10(rms_value / (2 ** 15))  # 16位音频


def _tts_output_active():  # 防自录：判断音箱此刻是否正在放出角色语音
    """两个来源取其一即认为“TTS 正在输出”：
    1) voice_gate 标记（覆盖合成阶段 + 播放结束后的冷却期，由 tts.py 写入）；
    2) pygame 混音器真实播放状态（覆盖流式播放段与段之间的缝隙）。"""
    try:
        if voice_gate.is_tts_active():
            return True
    except Exception:
        pass
    try:
        import pygame as _pg
        if _pg.mixer.get_init() and _pg.mixer.music.get_busy():
            return True
    except Exception:
        pass
    return False


# ==================== Silero VAD 语音活动检测（提升录音起止准确度） ====================
# 有该模型时启用 VAD，对"人声/环境噪声"判断远优于单纯能量阈值，
# 能准确捕捉语音开头、避免把呼吸/噪声当语音、也避免漏掉句尾弱音。
VAD_MODEL_PATH = "data/model/ASR/silero_vad.onnx"
vad_model, vad_ready = None, False
try:
    if os.path.exists(VAD_MODEL_PATH):
        _vad_cfg = sherpa_onnx.VadModelConfig()
        _vad_cfg.sample_rate = RATE
        _vad_cfg.silero_vad.model = VAD_MODEL_PATH
        _vad_cfg.silero_vad.min_silence_duration = 0.3   # 内部静音粒度（越小越灵敏）
        _vad_cfg.silero_vad.min_speech_duration = 0.15   # 最短语音段（放低，捕捉开头弱音字）
        _vad_cfg.silero_vad.threshold = 0.45             # 语音概率阈值(0~1)（放低，对轻声更敏感）
        _vad_cfg.silero_vad.max_speech_duration = 30
        _vad_cfg.silero_vad.window_size = 512
        vad_model = sherpa_onnx.VadModel.create(_vad_cfg)
        vad_ready = True
        print("✓ Silero VAD 语音活动检测已启用，录音将更完整")
except Exception as e:
    vad_model, vad_ready = None, False
    print(f"VAD 模型加载失败（将回退到动态能量阈值检测）: {e}")


def _vad_is_voice(audio_bytes):  # 用 VAD 判断一帧(1024样本)是否含语音
    samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    win = vad_model.window_size()
    for i in range(0, len(samples), win):
        seg = samples[i:i + win]
        if len(seg) < win:
            seg = np.pad(seg, (0, win - len(seg)))
        if vad_model.is_speech(seg):
            return True
    return False


def _ensure_stream():
    """确保麦克风流已打开；配置的「麦克风编号」在新主机无效时，自动回退到
    系统默认/第一个可用输入设备，避免语音输入因设备索引不同而永久失效。"""
    global p, stream, mic_num
    if stream is not None:
        return True
    if p is None:
        try:
            p = pyaudio.PyAudio()
        except Exception as e:
            print(f"[ASR] PyAudio 初始化失败: {e}")
            return False
    candidates = []
    if isinstance(mic_num, int) and mic_num >= 0:
        candidates.append(mic_num)
    try:
        dflt = p.get_default_input_device_info()
        if dflt.get('index') not in candidates:
            candidates.append(dflt['index'])
    except Exception:
        pass
    try:
        for i in range(p.get_device_count()):
            try:
                info = p.get_device_info_by_index(i)
                if info.get('maxInputChannels', 0) > 0 and i not in candidates:
                    candidates.append(i)
            except Exception:
                pass
    except Exception:
        pass
    for idx in candidates:
        try:
            stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True,
                            frames_per_buffer=CHUNK, input_device_index=idx)
            mic_num = idx
            print(f"[ASR] 麦克风已就绪 (设备索引 {idx})")
            return True
        except Exception:
            continue
    try:
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        mic_num = -1
        print("[ASR] 麦克风已就绪 (系统默认设备)")
        return True
    except Exception as e:
        print(f"[ASR] 无法打开任何麦克风: {e}")
        return False


def record_audio():  # 录音（智能起止检测：VAD + 动态能量阈值，实现连续完整识别）
    global p, stream
    # ================= 录音参数 =================
    MAX_RECORD_SECONDS = 30       # 最长录音30秒（防止死循环/失控）
    MIN_SPEECH_SECONDS = 0.3      # 最少有效语音0.3秒（排除咳嗽/环境噪声）
    # 结束判定：连续静音达到设定时长（灵敏度）才可能结束
    silence_chunks_limit = int(SILENCE_CHUNKS) + 1
    # 尾部缓冲：判定结束后额外保留的帧数，防止丢失句尾弱读音（如"吗""呢"）
    # 配合"重新激活"机制，句中停顿期间若再次说话会自动接续，保证完整录入
    tail_chunks = int(0.8 * RATE / CHUNK)   # 尾部缓冲加大，保留句尾弱音(如"鹭")
    # 开始去抖：连续几帧判为语音才确认开始（防止瞬时噪声误触发；
    # 2 帧≈128ms，比 3 帧更容易留住用户开口的第一个字）
    start_confirm_chunks = 2
    max_chunks = MAX_RECORD_SECONDS * RATE // CHUNK
    min_speech_chunks = MIN_SPEECH_SECONDS * RATE // CHUNK

    if not _ensure_stream():
        return b''  # 无可用麦克风（未插入/设备被占用），本次不录音

    frames = []
    voice_started = False   # 是否已确认开始录音
    pending_start = 0       # 连续判为语音但未确认开始的帧数（去抖用）
    speech_chunks = 0       # 有效语音累计帧数（用于最小时长判断）
    silence_counter = 0     # 连续静音帧数
    tail_remaining = 0      # 尾部缓冲剩余帧数
    total_chunks = 0        # 总录音帧数（超时保护）

    # 动态噪声底（VAD 不可用时的能量阈值回退方案）
    noise_floor = None
    # 防自录：记录上一循环 TTS 是否在输出，用于在它刚结束时重置 VAD/状态
    tts_was_active = False

    while True:
        data = stream.read(CHUNK)
        total_chunks += 1

        # ---------- 0. 防自录（半双工）：TTS 正在输出时丢弃麦克风数据 ----------
        # 不把音箱放出的角色语音当成用户说话；同时持续读取可清空录音缓冲，
        # 避免“停止录音的这段时间”缓存的旧声音在恢复录音后被一次性识别。
        if _tts_output_active():
            tts_was_active = True
            frames, pending_start, silence_counter, tail_remaining = [], 0, 0, 0
            speech_chunks, total_chunks, noise_floor = 0, 0, None
            voice_started = False
            continue
        if tts_was_active:
            # TTS 刚结束（含冷却期）：重置 VAD 内部状态与录制状态，从干净状态重新等待用户说话
            tts_was_active = False
            if vad_ready:
                try:
                    vad_model.reset()
                except Exception:
                    pass
            frames, pending_start, silence_counter, tail_remaining = [], 0, 0, 0
            speech_chunks, total_chunks, noise_floor = 0, 0, None
            voice_started = False
            continue

        # ---------- 1. 语音活动检测：优先 VAD，回退动态能量阈值 ----------
        if vad_ready:
            is_voice = _vad_is_voice(data)
        else:
            current_rms = rms(data)
            current_dbfs = dbfs(current_rms)
            if noise_floor is None:
                noise_floor = current_dbfs if current_dbfs != float('-inf') else -60.0
            is_silence = (current_dbfs == float('-inf') or current_dbfs < -35.0)
            if is_silence and current_dbfs != float('-inf'):
                noise_floor = 0.9 * noise_floor + 0.1 * current_dbfs  # 慢速自适应噪声底
            voice_threshold = min(-25.0, noise_floor + 8.0)
            is_voice = current_dbfs != float('-inf') and current_dbfs > voice_threshold

        # ---------- 2. 超时保护 ----------
        if total_chunks > max_chunks:
            if voice_started:
                break  # 已开始则强制结束
            else:
                # 一直没人说话：清空状态继续监听（避免空转）
                frames, pending_start, silence_counter, tail_remaining = [], 0, 0, 0
                speech_chunks, total_chunks, noise_floor = 0, 0, None
                continue

        # ---------- 3. 开始/结束状态机 ----------
        if not voice_started:
            # === 等待语音开始 ===
            if is_voice:
                frames.append(data)  # 先保留判定帧，确认开始后一起保留
                pending_start += 1
                if pending_start >= start_confirm_chunks:
                    voice_started = True  # 确认开始
                    speech_chunks += pending_start
                    pending_start = 0
                    silence_counter = 0
                    tail_remaining = tail_chunks
            else:
                if pending_start > 0:
                    # 未达到开始标准就停止 → 丢弃（防误触发）
                    frames = []
                    pending_start = 0
        else:
            # === 已开始，持续录音 ===
            frames.append(data)
            if is_voice:
                speech_chunks += 1
                silence_counter = 0
                tail_remaining = tail_chunks  # 有语音→重置尾部缓冲（说话未停则不断续录）
            else:
                silence_counter += 1
                if silence_counter > silence_chunks_limit:
                    # 疑似语音结束：进入尾部缓冲倒计时（保留句尾弱音）
                    tail_remaining -= 1
                    if tail_remaining <= 0:
                        break
                # 静音未到阈值 → 视为句中停顿，继续录音

    audio = b''.join(frames)
    # 有效语音太短（如咳嗽、环境噪声）→ 判为无效，返回空
    if speech_chunks < min_speech_chunks:
        return b''
    return audio


def _trim_silence(audio_bytes):  # 去除首尾静音，让识别聚焦语音内容，提升完整度
    samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
    if len(samples) < 1024:
        return audio_bytes
    frame_len = 512
    n_frames = len(samples) // frame_len
    energies = np.sqrt(
        np.mean(np.square(samples[:n_frames * frame_len].reshape(n_frames, frame_len)), axis=1))
    peak = np.max(energies)
    # 阈值降到相对峰值3%(且不低于100≈-46dB)，首尾缓冲加大：
    # 弱音被帧内静音稀释后能量会变低(如句尾"鹭"整帧均值仅~1150)，
    # 阈值太高会把开头清声母(如"程"的ch)和句尾弱音误当静音裁掉
    threshold = max(100.0, peak * 0.03)
    voiced = np.where(energies > threshold)[0]
    if len(voiced) == 0:
        return audio_bytes
    start = max(0, voiced[0] - 8)    # 首部多留缓冲，避免开头的清声母(如"程"的ch)被切掉
    end = min(n_frames, voiced[-1] + 6)
    return samples[start * frame_len:end * frame_len].astype(np.int16).tobytes()


# open_source_project_address:https://github.com/swordswind/ai_virtual_mate_web
def verify_speakers():  # 声纹识别
    global vp_config, extractor, audio1, sample_rate1, embedding1
    audio_file1 = "data/cache/voiceprint/myvoice.wav"
    audio_file2 = cache_path

    def load_audio(filename):
        audio, sample_rate = sf.read(filename, dtype="float32", always_2d=True)
        audio = audio[:, 0]
        return audio, sample_rate

    def extract_speaker_embedding(audio, sample_rate):
        vp_stream = extractor.create_stream()
        vp_stream.accept_waveform(sample_rate=sample_rate, waveform=audio)
        vp_stream.input_finished()
        embedding = extractor.compute(vp_stream)
        return np.array(embedding)

    def cosine_similarity():
        dot_product = np.dot(embedding1, embedding2)
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        return dot_product / (norm1 * norm2) if (norm1 * norm2) != 0 else 0.0

    print("正在加载说话人嵌入模型...")
    try:
        if vp_config is None:
            vp_config = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=vp_model_path, debug=False, provider="cpu",
                                                                    num_threads=int(os.cpu_count()) - 1)
            extractor = sherpa_onnx.SpeakerEmbeddingExtractor(vp_config)
            audio1, sample_rate1 = load_audio(audio_file1)
            embedding1 = extract_speaker_embedding(audio1, sample_rate1)
        audio2, sample_rate2 = load_audio(audio_file2)
        embedding2 = extract_speaker_embedding(audio2, sample_rate2)
        similarity = cosine_similarity()
        if similarity >= voiceprint_threshold:
            print(f"✓ 结果: 是同一个说话人 (相似度 {similarity:.4f} >= 阈值 {voiceprint_threshold})")
            return True
        else:
            print(f"✗ 结果: 不是同一个说话人 (相似度 {similarity:.4f} < 阈值 {voiceprint_threshold})")
            return False
    except Exception as e:
        print(f"声纹识别出错，详情：{e}")
        return True


def recognize_audio(audiodata):  # 语音识别
    global recognizer
    # 去除首尾静音，让识别聚焦语音内容，避免静音影响识别结果
    audiodata = _trim_silence(audiodata)
    if len(audiodata) == 0:
        return ""
    if recognizer is None:
        recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model, tokens=tokens, use_itn=True,
            num_threads=int(os.cpu_count()) - 1)
    with wave.open(cache_path, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(audiodata)
    with wave.open(cache_path, 'rb') as wf:
        n_frames = wf.getnframes()
        duration = n_frames / RATE
    if duration < 0.3:  # 至少0.3秒的音频才处理，小于此值直接忽略
        return ""
    if voiceprint_switch == "开启":
        if not verify_speakers():
            return ""
    audio, sample_rate = sf.read(cache_path, dtype="float32", always_2d=True)
    asr_stream = recognizer.create_stream()
    asr_stream.accept_waveform(sample_rate, audio[:, 0])
    recognizer.decode_stream(asr_stream)
    res = json.loads(str(asr_stream.result))
    emotion_key = res.get('emotion', '').strip('<|>')
    event_key = res.get('event', '').strip('<|>')
    text = res.get('text', '')
    emotion_dict = {"HAPPY": "[开心]", "SAD": "[伤心]", "ANGRY": "[愤怒]", "DISGUSTED": "[厌恶]", "SURPRISED": "[惊讶]",
                    "NEUTRAL": "", "EMO_UNKNOWN": ""}
    event_dict = {"BGM": "", "Applause": "[鼓掌]", "Laughter": "[大笑]", "Cry": "[哭]", "Sneeze": "[打喷嚏]",
                  "Cough": "[咳嗽]", "Breath": "[深呼吸]", "Speech": "", "Event_UNK": ""}
    emotion = emotion_dict.get(emotion_key, "")
    event = event_dict.get(event_key, "")
    result = event + text + emotion
    if result == "The.":
        return ""
    # 如果结果中不含任何中文字符且长度小于3，视为无效识别
    if not re.search(r'[\u4e00-\u9fff]', result) and len(result) < 3:
        return ""
    return result
