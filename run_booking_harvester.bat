@echo off
chcp 65001 > nul
title Cào Dữ Liệu Booking.com Trực Tiếp (Stage 1)
cd /d "%~dp0"
echo ========================================================
echo  ĐANG KHỞI CHẠY CÔNG CỤ CÀO BOOKING.COM TRỰC TIẾP (STAGE 1)
echo ========================================================
.\.venv\Scripts\python.exe booking_harvester.py
pause
