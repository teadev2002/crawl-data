@echo off
echo ========================================================
echo   CONG CU CAO DIA DIEM GOOGLE MAPS SONG SONG 2 LUONG
echo ========================================================
echo.
echo [*] Dang khoi tao file ket qua va bat 2 luong (TOP & BOTTOM)...
echo.
start "Map Scraper - LUONG TOP (TU TREN XUONG)" cmd /k ".venv\Scripts\python map_scraper.py --mode=top"
start "Map Scraper - LUONG BOTTOM (TU DUOI LEN)" cmd /k ".venv\Scripts\python map_scraper.py --mode=bottom"
echo [+] Da kich hoat thanh cong 2 luong song song!
echo.
pause
