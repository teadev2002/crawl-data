@echo off
echo ========================================================
echo   KHOI CHAY HE THONG WEB DASHBOARD - ANTIGRAVITY DATA
echo ========================================================
echo.
echo [*] Dang khoi dong Web Server tai http://127.0.0.1:8000 ...
echo [*] Trinh duyet web se tu dong mo len trong giay lat.
echo.
start "" /b cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"
.venv\Scripts\python.exe server.py
pause
