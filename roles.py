# -*- coding: utf-8 -*-
"""双角色管理模块：南小橙(男) + 程小鹭(女) 并排显示，按角色名唤醒对应角色。

设计要点：
- 角色配置唯一来源：data/db/roles.json
- state 是可变的跨线程共享状态（current=当前交互角色索引，speaking=正在说话的索引）
- 各模块用 `import roles` 后通过 roles.state / roles.get_current_role() 访问，
  避免 `from xx import *` 值拷贝导致运行中切换角色不生效的问题
"""
import json
import os

_ROLES_PATH = os.path.join('data', 'db', 'roles.json')

with open(_ROLES_PATH, 'r', encoding='utf-8') as _f:
    _config = json.load(_f)

ROLES = _config.get("角色", [])

# 可变共享状态（跨线程）：current=当前交互角色索引；speaking=正在说话的索引(-1=无人说话)
state = {"current": 0, "speaking": -1}

# 初始化当前角色（优先 roles.json 的"当前角色"字段，否则默认第一个）
_cur_name = _config.get("当前角色", "")
if ROLES:
    _found = next((i for i, r in enumerate(ROLES) if r.get("名称") == _cur_name), -1)
    state["current"] = _found if _found >= 0 else 0


def get_current_role():
    """返回当前交互角色 dict；异常时返回空 dict"""
    if not ROLES:
        return {}
    idx = state["current"]
    if idx < 0 or idx >= len(ROLES):
        idx = 0
    return ROLES[idx]


def get_role_index_by_name(name):
    """按名称匹配角色索引（支持包含匹配，如"南小橙"/"小橙"都能命中）"""
    if not name:
        return -1
    for i, r in enumerate(ROLES):
        rname = r.get("名称", "")
        if name == rname or (rname and (name in rname or rname in name)):
            return i
    return -1


def switch_role(name):
    """按角色名切换当前交互角色，成功返回 True"""
    idx = get_role_index_by_name(name)
    if idx >= 0:
        state["current"] = idx
        return True
    return False


def current_role_name():
    """当前角色显示名"""
    return get_current_role().get("名称", "")
