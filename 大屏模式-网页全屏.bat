@echo off
chcp 65001 >nul
title 枫云AI虚拟伙伴 - 大屏网页全屏模式
cd /d %~dp0

set MATEWEB_KIOSK=1

echo ============================================
echo   枫云AI虚拟伙伴 - 大屏网页全屏模式
echo ============================================
echo.
echo   正在启动... 稍候会自动打开浏览器全屏访问聊天页面
echo.
echo   本机访问:   http://127.0.0.1:5260
echo   其他设备(电视/平板/手机): 浏览器输入本机IP:5260
echo   3D角色页面: 端口 5261(Live2D) 5262(MMD) 5263(VRM)
echo.
echo   提示: 请确保「对话网页开关」已开启(网页模式默认强制开启)
echo        关闭本窗口可退出
echo.

start "" runtime\pythonw main.py
pause
