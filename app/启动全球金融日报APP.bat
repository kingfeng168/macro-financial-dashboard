@echo off
REM ============================================================
REM  全球金融日报 APP 启动器 (静默后台运行 · 不弹黑窗口)
REM  作用: 用 pythonw 静默启动实时数据服务器(live_server.py), 固定端口 8800
REM  停止: 双击同目录「停止全球金融日报APP.bat」 或 任务管理器结束 pythonw.exe
REM ============================================================
title 全球金融日报 APP
cd /d "."

REM ---- 清理可能占用 8800 的旧 live_server 进程 (不影响其他端口) ----
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*live_server.py*' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }" >nul 2>&1
timeout /t 2 >nul

REM ---- 静默启动服务器 (pythonw 无控制台窗口) ----
start "" "pythonw" live_server.py 8800

REM ---- 延迟 5 秒后打开浏览器仪表盘 ----
start "" ".\open_browser_delayed.bat"

REM ---- 仅当启动失败时才弹窗提示 (成功则全程无窗口) ----
start "" powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 4; if(-not(Get-NetTCPConnection -LocalPort 8800 -State Listen -ErrorAction SilentlyContinue)){ Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('服务器启动失败: 端口 8800 无监听。'+[char]10+'请检查 pythonw.exe 路径或手动运行 live_server.py。','启动失败',[System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::Error) }"
