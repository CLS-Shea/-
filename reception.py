# -*- coding: utf-8 -*-
"""现场接待模式的状态和安全边界。

现场模式通过环境变量 MATEWEB_RECEPTION=1 或 data/set/reception_mode.json 开启，
默认关闭以保留原通用伙伴模式。该模块不保存访客原文，只维护当前一轮接待的
角色、最后活动时间和请求代次。
"""
import json
import os
import threading
import time

CONFIG_PATH = os.path.join("data", "set", "reception_mode.json")
DEFAULT_CONFIG = {
    "enabled": False,
    "idle_seconds": 15,
    "request_timeout_seconds": 8,
    "default_role": "南小橙",
    "fixed_intro_trigger": "开始学院介绍",
    "fixed_intro_text": "欢迎来到南京工程学院天印湖科创学院。南小橙将为您介绍学院的定位、特色和代表成果。",
    "approved_search_topics": [],
}


def _load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            cfg.update(loaded)
    except (OSError, ValueError, TypeError):
        pass
    cfg["enabled"] = os.environ.get("MATEWEB_RECEPTION", "").strip() == "1" or bool(cfg.get("enabled"))
    try:
        cfg["idle_seconds"] = max(1, int(cfg["idle_seconds"]))
    except (TypeError, ValueError):
        cfg["idle_seconds"] = DEFAULT_CONFIG["idle_seconds"]
    try:
        cfg["request_timeout_seconds"] = max(1, int(cfg["request_timeout_seconds"]))
    except (TypeError, ValueError):
        cfg["request_timeout_seconds"] = DEFAULT_CONFIG["request_timeout_seconds"]
    return cfg


CONFIG = _load_config()
_lock = threading.RLock()
_state = {
    "role": CONFIG["default_role"],
    "last_activity": 0.0,
    "request_id": 0,
    "intro_playing": False,
    "pending_role": "",
}


def enabled():
    return bool(CONFIG.get("enabled"))


def idle_seconds():
    return int(CONFIG["idle_seconds"])


def request_timeout_seconds():
    return int(CONFIG["request_timeout_seconds"])


def fixed_intro_trigger():
    return str(CONFIG.get("fixed_intro_trigger") or DEFAULT_CONFIG["fixed_intro_trigger"])


def fixed_intro_text():
    return str(CONFIG.get("fixed_intro_text") or DEFAULT_CONFIG["fixed_intro_text"])


def search_topic_approved(msg):
    """现场模式只允许学院批准的专业主题联网搜索；空清单默认不开放。"""
    if not enabled():
        return True
    topics = CONFIG.get("approved_search_topics") or []
    return any(str(topic).strip() and str(topic).strip() in (msg or "") for topic in topics)


def touch():
    with _lock:
        _state["last_activity"] = time.monotonic()


def idle_expired(now=None):
    with _lock:
        last = _state["last_activity"]
    return bool(last and (now or time.monotonic()) - last >= idle_seconds())


def begin_request():
    """开始新请求并返回不可复用的请求代次。"""
    with _lock:
        _state["request_id"] += 1
        _state["last_activity"] = time.monotonic()
        return _state["request_id"]


def request_current(request_id):
    with _lock:
        return request_id == _state["request_id"]


def finish_session():
    """结束访客会话；返回默认角色名，不保存访客内容。"""
    with _lock:
        _state["request_id"] += 1
        _state["last_activity"] = 0.0
        _state["intro_playing"] = False
        _state["pending_role"] = ""
        return CONFIG["default_role"]


def set_intro_playing(value):
    with _lock:
        _state["intro_playing"] = bool(value)


def intro_playing():
    with _lock:
        return bool(_state["intro_playing"])


def set_role(name):
    with _lock:
        _state["role"] = name


def pending_role():
    with _lock:
        return _state["pending_role"]


def request_role_switch(name):
    with _lock:
        _state["pending_role"] = name or ""


def confirm_role_switch(confirmed):
    with _lock:
        name = _state["pending_role"]
        _state["pending_role"] = ""
    return name if confirmed else ""


def current_role():
    with _lock:
        return _state["role"]

