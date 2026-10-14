# -*- coding: utf-8 -*-
"""唤醒互动窗口（语音喊名字唤醒 / 点击角色唤醒 共用）。

- 语音唤醒：main.py 的 handle_voice_text() 命中唤醒词后 extend_wake_window()
- 点击唤醒：live2d.py 的 /api/wake_click 路由切换角色后 extend_wake_window()
- 窗口内说每句话都会续期；连续 WAKE_SESSION_SECONDS 秒没说话就回到"待唤醒"。

状态独立成模块，避免 main.py 与 live2d.py 互相 import 造成循环依赖。
"""
import threading
import time

WAKE_SESSION_SECONDS = 30  # 唤醒后保持互动的时长（秒）

_lock = threading.Lock()
_expire = 0.0


def wake_window_active():  # 当前是否处于唤醒后的互动窗口中
    return time.time() < _expire


def extend_wake_window(seconds=None):  # 开始/续期互动窗口
    global _expire
    with _lock:
        _expire = time.time() + (WAKE_SESSION_SECONDS if seconds is None else seconds)
    return _expire


def expire_wake_window():  # 立即结束互动窗口（回到待唤醒）
    global _expire
    with _lock:
        _expire = 0.0


def remaining_seconds():  # 互动窗口剩余秒数
    return max(0.0, _expire - time.time())
