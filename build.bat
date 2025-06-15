@echo off
echo ========================================
echo Media Utility - Windows Build Script
echo ========================================
echo.

REM 
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

echo Python found, starting build process...
echo.

REM 
python build_executable.py

echo.
echo Build process completed!
echo Check the output above for any errors.
echo.
pause
