# -*- coding: utf-8 -*-
"""大屏模式浏览器全屏启动器
自动检测 Edge/Chrome 并用全屏方式打开指定网址（供大屏/电视互动使用）。
用法: python launch_kiosk.py <url> [--kiosk]
  --kiosk: 使用严格 Kiosk 模式（自助终端，无地址栏/标签栏，需 Alt+F4 或 Esc 退出）
  默认: 使用普通全屏模式（可 F11 退出）
"""
import os
import sys
import subprocess
import webbrowser

# 常见浏览器路径（按优先级）
BROWSERS = [
    (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "--start-fullscreen"),
    (r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", "--start-fullscreen"),
    (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--start-fullscreen"),
    (r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "--start-fullscreen"),
    (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "--kiosk"),
    (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--kiosk"),
]


def find_browser(use_kiosk=False):
    """返回 (浏览器exe路径, 全屏参数)；找不到返回 (None, None)"""
    for exe, flag in BROWSERS:
        if use_kiosk and flag != "--kiosk":
            continue
        if not use_kiosk and flag == "--kiosk":
            continue
        if os.path.exists(exe):
            return exe, flag
    return None, None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_kiosk = "--kiosk" in sys.argv
    url = args[0] if args else "http://127.0.0.1:5260"

    exe, flag = find_browser(use_kiosk)
    if exe:
        try:
            subprocess.Popen([exe, flag, url])
            mode = "Kiosk自助终端" if use_kiosk else "全屏"
            print(f"[大屏] 已用{os.path.basename(os.path.dirname(os.path.dirname(exe)))}浏览器以{mode}模式打开: {url}")
            return
        except Exception as e:
            print(f"[大屏] 浏览器启动失败: {e}")

    # 兜底：默认浏览器打开（需手动 F11 全屏）
    try:
        webbrowser.open(url)
        print(f"[大屏] 已用默认浏览器打开: {url}（请手动按 F11 全屏）")
    except Exception as e:
        print(f"[大屏] 打开浏览器失败: {e}")


if __name__ == "__main__":
    main()
