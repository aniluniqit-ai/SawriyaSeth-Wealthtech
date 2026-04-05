@echo off
echo ============================================
echo   JSS Sawriya Seth Wealthtech - Building EXE
echo ============================================
echo.
python -m pip install pyinstaller
echo.
pyinstaller --onefile --windowed ^
  --name "JSS_Wealthtech_AI_Trading" ^
  --icon "images/app_icon.ico" ^
  --add-data "config;config" ^
  --add-data "images;images" ^
  --hidden-import "core" ^
  --hidden-import "brokers" ^
  --hidden-import "strategies" ^
  --hidden-import "telegram" ^
  --hidden-import "ui" ^
  omai_main.py
echo.
echo Build Complete! EXE is in dist/ folder.
echo Copy config/ and images/ folders next to the EXE.
pause
