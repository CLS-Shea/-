# -*- coding: utf-8 -*-
"""语音门控（防自录 / 防回声）。

问题背景：音箱放出来的角色语音会被同一个麦克风录进去，被 ASR 当成"用户在说话"，
导致软件自己跟自己对话、上下文混乱。

解决思路（半双工）：TTS 正在合成或播放期间，麦克风数据全部丢弃、不进 ASR 状态机；
播放结束后再保留一小段冷却时间，等扬声器余音和录音缓冲里的残留声音消散。

本模块只保存状态，不 import 任何项目模块：
- tts.py 负责写入（set_tts_busy）
- asr.py 负责读取（is_tts_active / cooldown_remaining）
这样避免 asr / tts 之间的循环导入。
"""
import time

tts_busy = False          # TTS 正在合成或播放
_last_tts_end = 0.0       # 最近一次 TTS 结束的时间戳
COOLDOWN_SECONDS = 0.4    # 播放结束后的冷却时长(秒)。太长会把用户接在句尾说的话开头吃掉


def set_tts_busy(busy):  # 由 tts.py 调用：标记 TTS 开始/结束输出
    global tts_busy, _last_tts_end
    busy = bool(busy)
    if not busy and tts_busy:
        _last_tts_end = time.time()  # 记录结束时刻，进入冷却期
    tts_busy = busy


def is_tts_active():  # TTS 正在输出，或刚结束仍在冷却期内 → 此时不应采集用户语音
    if tts_busy:
        return True
    return (time.time() - _last_tts_end) < COOLDOWN_SECONDS


def cooldown_remaining():  # 距离冷却结束还剩多少秒（用于日志/调试）
    return max(0.0, COOLDOWN_SECONDS - (time.time() - _last_tts_end))
