@echo off
setlocal enabledelayedexpansion

echo ==============================================================================
echo   PRAHARI - Windows Standalone Executable Build Script (PyInstaller)
echo ==============================================================================

cd /d "%~dp0\.."

echo [1/3] Checking Python and PyInstaller...
python -m PyInstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] PyInstaller not found. Installing PyInstaller...
    python -m pip install pyinstaller
)

echo [2/3] Building PRAHARI Standalone Distribution (onedir)...
python -m PyInstaller --noconfirm --clean packaging\PRAHARI.spec
if %errorlevel% neq 0 (
    echo [!] PyInstaller build failed!
    exit /b 1
)

echo [3/3] Verifying Bundled Assets in dist\PRAHARI...
if not exist "dist\PRAHARI\PRAHARI.exe" (
    echo [!] Error: dist\PRAHARI\PRAHARI.exe was not created.
    exit /b 1
)

if not exist "dist\PRAHARI\_internal\models\yolov8n.pt" if not exist "dist\PRAHARI\models\yolov8n.pt" (
    echo [*] Copying models folder into dist\PRAHARI\models...
    if not exist "dist\PRAHARI\models" mkdir "dist\PRAHARI\models"
    copy /y "models\yolov8n.pt" "dist\PRAHARI\models\" >nul 2>&1
)

if not exist "dist\PRAHARI\_internal\config" if not exist "dist\PRAHARI\config" (
    echo [*] Copying config folder into dist\PRAHARI\config...
    xcopy /e /i /y "config" "dist\PRAHARI\config\" >nul 2>&1
)

echo ==============================================================================
echo   [SUCCESS] Standalone Build Complete: dist\PRAHARI\PRAHARI.exe
echo ==============================================================================
