@echo off
chcp 65001 >nul
title 枫云AI虚拟伙伴 - 大屏桌面全屏模式
cd /d %~dp0

set MATEWEB_FULLSCREEN=1

echo ============================================
echo   枫云AI虚拟伙伴 - 大屏桌面全屏模式
echo ============================================
echo.
echo   正在启动... 主窗口将自动全屏显示
echo.
echo   提示: 按 F11 或 Esc 退出全屏
echo        关闭本窗口可退出
echo.

start "" runtime\pythonw main.py
pause
