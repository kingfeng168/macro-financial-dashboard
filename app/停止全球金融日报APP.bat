@echo off
REM ============================================================
REM  全球金融日报 APP 停止器
REM  关闭后台静默运行的 live_server.py (pythonw) 进程
REM ============================================================
title 停止全球金融日报 APP
cd /d "."
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like '*live_server.py*' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('已停止 PID ' + $_.ProcessId) } catch {} }"
timeout /t 1 >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('全球金融日报 APP 已停止 (后台服务器已关闭)。','已停止',[System.Windows.Forms.MessageBoxButtons]::OK,[System.Windows.Forms.MessageBoxIcon]::Information)"
