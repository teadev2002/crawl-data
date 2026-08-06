@echo off
chcp 65001 > nul
title Sửa Lỗi Lệch Dòng Title & URL (Cách 1)
cd /d "%~dp0"
echo ========================================================
echo  ĐANG KHỞI CHẠY CÔNG CỤ SỬA LỖI LỆCH DÒNG TITLE & URL (CÁCH 1)
echo ========================================================
.\.venv\Scripts\python.exe mismatch_repairer.py
pause
