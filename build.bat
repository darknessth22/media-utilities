@echo off
echo ========================================
echo Media Utility - Windows Build Script
echo ========================================
echo.

REM Activate venv if present, else fall back to system Python
if exist "%~dp0..\venv\Scripts\activate.bat" (
    call "%~dp0..\venv\Scripts\activate.bat"
    echo Activated venv at %~dp0..\venv
) else if exist "%~dp0venv\Scripts\activate.bat" (
    call "%~dp0venv\Scripts\activate.bat"
    echo Activated venv at %~dp0venv
)

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://python.org
    pause
    exit /b 1
)

echo Python found, starting build process...
echo.

python build_executable.py

echo.
echo Build process completed!
echo Check the output above for any errors.
echo.
pause
