@echo off
echo ========================================================
echo   CONG CU KHOI PHUC CATEGORYNAME SONG SONG 2 LUONG
echo ========================================================
echo.
echo [*] Dang khoi tao va bat 2 luong (TOP & BOTTOM)...
echo.
start "Category Repairer - LUONG TOP (TU TREN XUONG)" cmd /k ".venv\Scripts\python category_repairer.py --mode=top"
start "Category Repairer - LUONG BOTTOM (TU DUOI LEN)" cmd /k ".venv\Scripts\python category_repairer.py --mode=bottom"
echo [+] Da kich hoat thanh cong 2 luong song song!
echo.
pause
