@echo off
REM 延迟打开浏览器, 避免服务器尚未就绪 (由启动器调用, 退出后不残留)
timeout /t 5 >nul
start "" "http://localhost:8800/"
exit
