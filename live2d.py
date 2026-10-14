import json
import logging
import random
import threading
import pygame as pg
from flask import Flask, send_from_directory, render_template_string, request
import roles
import wake  # 唤醒互动窗口（与 main.py 的语音唤醒共用）

with open('data/db/config.json', 'r', encoding='utf-8') as file:
    config = json.load(file)
live2d_port = int(config["L2D角色网页端口"])
username = config.get("用户名", "")
app = Flask(__name__, static_folder='dist')
logging.getLogger('werkzeug').setLevel(logging.ERROR)

live2d_web_template = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/png" href="assets/image/logo.png" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <style>
      html, body {
        margin: 0;
        padding: 0;
        width: 100%;
        height: 100%;
        overflow: hidden; /* 全屏展示角色，隐藏滚动条 */
      }
      body {
        background-image: url('assets/image/bg.jpg');
        background-size: cover;
        background-repeat: no-repeat;
        background-position: center center;
        background-attachment: fixed;
      }
      #canvas2 {
        width: 100%;
        height: 100vh; /* 全屏高度，适配大屏/电视 */
        margin: 0 auto;
        display: block;
        background-color: transparent;
      }
    </style>
    <script src="/assets/live2d_core/live2dcubismcore.min.js"></script>
    <script src="/assets/live2d_core/live2d.min.js"></script>
    <script src="/assets/live2d_core/pixi.min.js"></script>
    <title>Live2D角色 - 枫云AI虚拟伙伴Web版</title>
    <script type="module" crossorigin src="/assets/live2d.js"></script>
  </head>
  <body>
    <div id="app"></div>
    <canvas id="canvas2"></canvas>
  </body>
</html>
"""

live2d_pet_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/png" href="assets/image/logo.png" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <style>
        html, body {
            margin: 0; /* 去掉默认边距 */
            padding: 0; /* 去掉默认内边距 */
            overflow: hidden; /* 禁用溢出滚动条 */
            width: 100%; /* 100%宽度 */
            height: 100%; /* 100%高度 */
        }
        #canvas2 {
            width: 100%; /* 自适应窗口宽度 */
            height: 100vh; /* 自适应窗口高度(可全屏/放大窗口) */
            display: block;
            background-color: transparent;
        }
    </style>
    <script src="/assets/live2d_core/live2dcubismcore.min.js"></script>
    <script src="/assets/live2d_core/live2d.min.js"></script>
    <script src="/assets/live2d_core/pixi.min.js"></script>
    <title>桌宠 - 枫云AI虚拟伙伴</title>
    <script type="module" crossorigin src="/assets/live2d.js"></script>
</head>
<body>
    <div id="app"></div>
    <canvas id="canvas2"></canvas>
</body>
</html>
"""


# open_source_project_address:https://github.com/swordswind/ai_virtual_mate_web
@app.route('/')
def index():
    return render_template_string(live2d_web_template)


@app.route('/pet')
def desktop_pet():
    return render_template_string(live2d_pet_template)


@app.route('/assets/<path:path>')
def serve_static(path):
    if path.endswith(".js"):
        return send_from_directory('./dist/assets', path, mimetype='application/javascript')
    return send_from_directory('./dist/assets', path)


@app.route('/api/get_mouth_y')
def check_play_state():
    # 大屏双角色：返回当前说话角色索引，前端只有该角色张嘴/做肢体语言
    is_playing = pg.mixer.music.get_busy() if pg.mixer.get_init() else False
    speaking = roles.state.get("speaking", -1)
    if is_playing and speaking >= 0:
        return json.dumps({"y": random.uniform(0.1, 0.9), "speaker": speaking}, ensure_ascii=False)
    return json.dumps({"y": 0, "speaker": -1}, ensure_ascii=False)


@app.route('/api/roles')
def get_roles():
    # 大屏双角色：返回两个角色的名称与索引，供前端/调试使用
    return json.dumps([{"index": i, "name": r.get("名称", ""), "gender": r.get("性别", "")}
                       for i, r in enumerate(roles.ROLES)], ensure_ascii=False)


@app.route('/api/current_role')
def get_current_role():
    # 大屏双角色：返回当前交互角色
    return json.dumps({"index": roles.state.get("current", 0), "name": roles.current_role_name()},
                      ensure_ascii=False)


def _click_wake_greeting():  # 点击唤醒后的语音回应（用当前角色的音色）
    try:
        from tts import get_tts_play
        get_tts_play(f"我在呢，{username}～" if username else "我在呢～")
    except Exception as e:
        print(f"[点击唤醒] 语音回应失败: {e}")


@app.route('/api/wake_click')
def wake_click():
    """大屏触摸 / 鼠标点击角色 → 唤醒对应角色。
    idx：0=左边角色(南小橙)，1=右边角色(程小鹭)。"""
    try:
        idx = int(request.args.get('idx', -1))
    except Exception:
        idx = -1
    if idx < 0 or idx >= len(roles.ROLES):
        return json.dumps({"ok": False, "error": "无效角色索引"}, ensure_ascii=False)
    roles.state["current"] = idx            # 点谁就用谁的人设 / 音色 / 动嘴角色
    wake.extend_wake_window()                # 打开互动窗口，接下来直接说话即可
    name = roles.current_role_name()
    threading.Thread(target=_click_wake_greeting, daemon=True).start()
    print(f"[点击唤醒] 已唤醒「{name}」，{wake.WAKE_SESSION_SECONDS}秒内可继续对话")
    return json.dumps({"ok": True, "index": idx, "name": name,
                       "seconds": wake.WAKE_SESSION_SECONDS}, ensure_ascii=False)


def run_live2d():
    app.run(port=live2d_port, host="0.0.0.0")
