@echo off
title PRAHARI - One-Click Setup & Launcher
echo ===============================================================================
echo        PRAHARI MISSION HAR ASSISTANT - AUTOMATED SETUP
echo ===============================================================================
echo.

if exist "installer\setup_prahari.exe" (
    start "" "installer\setup_prahari.exe"
    exit /b
)

echo [STEP 1/3] Upgrading pip and installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo [STEP 2/3] Checking AI Model Weights...
python src\download_models.py

echo.
echo [STEP 3/3] Starting PRAHARI...
set PRAHARI_CAMERA_TYPE=browser
python src\main.py --config config\desk_objects_experiment.json
pause
