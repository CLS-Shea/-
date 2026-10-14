@echo off
chcp 65001 >nul
title 枫云AI虚拟伙伴 - U盘便携启动器
cd /d %~dp0

echo ==================================================
echo    枫云AI虚拟伙伴 - U盘便携版
echo    插到电脑上，双击本文件即可运行（无需安装）
echo ==================================================
echo.
echo   [1/4] 正在启动主程序（语音识别 / 对话 / 双角色）...
start "" runtime\pythonw main.py

echo   [2/4] 等待角色服务(5261)就绪...
:wait_port
powershell -NoProfile -Command "try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',5261);'OK'}catch{'NO'}" | findstr /i "OK" >nul
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_port
)

echo   [3/4] 正在全屏打开双角色页面...
start "" runtime\pythonw launch_kiosk.py http://127.0.0.1:5261

echo   [4/4] 正在生成《电视访问地址.txt》...
start "" runtime\pythonw tv_address.py
timeout /t 2 /nobreak >nul

echo.
echo   ==================================================
echo   启动完成！本机已全屏显示两个角色。
echo.
echo   【在这台电脑上使用】
echo   - 对着电脑麦克风说话即可对话，角色会同步张嘴
echo   - 与"桌宠版"相同的双角色全屏页面
echo.
echo   【让电视显示同一画面】
echo   1. U盘根目录已自动生成《电视访问地址.txt》
echo   2. 电脑和电视连同一个 WiFi/路由器
echo   3. 电视打开"浏览器"App，照文件里的网址输入即可
echo.
echo   本机IP参考：
ipconfig | findstr /i "IPv4"
echo.
echo   例如 本机IP是 192.168.1.100，电视浏览器输入:
echo        http://192.168.1.100:5261
echo   （端口 5261 = 角色页 / 5260 = 聊天页）
echo.
echo   电视没有浏览器？→ 见 U盘里的《电视部署快速指南.txt》
echo   ==================================================
echo.
echo   提示：关闭本窗口不会停止软件（后台运行中）
pause
