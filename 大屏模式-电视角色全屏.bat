@echo off
chcp 65001 >nul
title 枫云AI虚拟伙伴 - 电视大屏模式(全屏双角色+语音)
cd /d %~dp0

echo ============================================
echo   枫云AI虚拟伙伴 - 电视大屏模式
echo   主机运行 + 电视全屏显示双角色 + 语音对话
echo ============================================
echo.
echo   1. 正在启动主程序(语音识别/对话已在后台运行)...
start "" runtime\pythonw main.py

echo   2. 等待 Live2D 角色服务(5261)就绪...
:wait_port
powershell -NoProfile -Command "try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',5261);'OK'}catch{'NO'}" | findstr /i "OK" >nul
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_port
)

echo   3. 服务已就绪，正在全屏打开角色页...
start "" runtime\pythonw launch_kiosk.py http://127.0.0.1:5261

echo.
echo   ============================================
echo   电视访问地址:  http://本机IP:5261
echo   聊天页(打字):  http://本机IP:5260
echo.
echo   本机IP查看(下方任一):
ipconfig | findstr /i "IPv4"
echo.
echo   使用方法:
echo   - 电视用浏览器打开上方「电视访问地址」即可全屏显示双角色
echo   - 语音对话请在【主机】上用麦克风说话(识别/合成在主机)
echo   - 说话时电视上的角色会同步张嘴
echo   ============================================
echo.
echo   提示: 关闭本窗口不会停止软件(后台运行中)
echo        需退出软件请到任务管理器结束 pythonw
pause
