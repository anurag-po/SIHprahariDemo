@echo off
title PRAHARI - Mission HAR Space Experiment Assistant
cd /d "%~dp0"
echo ===============================================================================
echo   PRAHARI - Mission HAR Space Experiment Assistant
echo   Launching application...
echo ===============================================================================
if exist "%~dp0PRAHARI.exe" (
    start "" "%~dp0PRAHARI.exe"
) else if exist "%~dp0PRAHARI\PRAHARI.exe" (
    start "" "%~dp0PRAHARI\PRAHARI.exe"
) else if exist "%~dp0dist\PRAHARI\PRAHARI.exe" (
    start "" "%~dp0dist\PRAHARI\PRAHARI.exe"
) else if exist "%~dp0src\main.py" (
    start "" python "%~dp0src\main.py"
) else (
    echo [ERROR] Could not find PRAHARI.exe or src\main.py in this directory!
    pause
)
