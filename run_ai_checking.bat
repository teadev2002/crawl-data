@echo off
chcp 65001 > nul
title AI Checking - Gemini API Thẩm Định & Ghi Đè Google Maps
cd /d "%~dp0"
echo ========================================================
echo  ĐANG KHỞI CHẠY CHỨC NĂNG AI CHECKING (GEMINI API)
echo ========================================================
.\.venv\Scripts\python.exe ai_checking.py
pause
