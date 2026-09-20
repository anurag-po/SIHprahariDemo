@echo off
setlocal enabledelayedexpansion

echo ==============================================================================
echo   PRAHARI - Windows Standalone Executable Build Script (PyInstaller)
echo ==============================================================================

cd /d "%~dp0\.."

echo [1/3] Checking Python 3.11 and PyInstaller...
set PY_CMD=py -3.11
%PY_CMD% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] py -3.11 not found in PATH; falling back to active python runner...
    set PY_CMD=python
)
echo [*] Using Python runner: %PY_CMD%

%PY_CMD% -m PyInstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] PyInstaller not found. Installing PyInstaller via %PY_CMD%...
    %PY_CMD% -m pip install pyinstaller
)

echo [2/3] Building PRAHARI Standalone Distribution (onedir)...
%PY_CMD% -m PyInstaller --noconfirm --clean packaging\PRAHARI.spec
if %errorlevel% neq 0 (
    echo [!] PyInstaller build failed!
    exit /b 1
)

echo [3/3] Verifying Canonical Bundled Assets in dist\PRAHARI\_internal...
if not exist "dist\PRAHARI\PRAHARI.exe" (
    echo [!] Error: dist\PRAHARI\PRAHARI.exe was not created.
    exit /b 1
)

:: Ensure single canonical runtime location in _internal (where PyInstaller bundles runtime assets)
if not exist "dist\PRAHARI\_internal\models" mkdir "dist\PRAHARI\_internal\models"
xcopy /e /i /y "models" "dist\PRAHARI\_internal\models\" >nul 2>&1

if not exist "dist\PRAHARI\_internal\config" mkdir "dist\PRAHARI\_internal\config"
xcopy /e /i /y "config" "dist\PRAHARI\_internal\config\" >nul 2>&1

:: Remove any duplicate copies at root dist\PRAHARI to maintain single canonical location
if exist "dist\PRAHARI\models" rmdir /s /q "dist\PRAHARI\models"
if exist "dist\PRAHARI\config" rmdir /s /q "dist\PRAHARI\config"

echo ==============================================================================
echo   [SUCCESS] Standalone Build Complete: dist\PRAHARI\PRAHARI.exe
echo ==============================================================================
