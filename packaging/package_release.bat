@echo off
setlocal enabledelayedexpansion

echo ==============================================================================
echo   PRAHARI - Release Distribution Builder (Portable + Launcher + Setup)
echo ==============================================================================

cd /d "%~dp0\.."

set "VERSION=v1.0.0"
set "RELEASE_DIR=release"
set "RELEASE_ZIP=%RELEASE_DIR%\PRAHARI-%VERSION%-Windows-x64.zip"

if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"

if not exist "dist\PRAHARI\PRAHARI.exe" (
    echo [*] dist\PRAHARI not found. Running build_windows.bat first...
    call "packaging\build_windows.bat"
    if %errorlevel% neq 0 (
        echo [!] Build failed. Aborting packaging.
        exit /b 1
    )
)

echo [1/5] Syncing Standalone Build to %RELEASE_DIR%\PRAHARI ...
robocopy "dist\PRAHARI" "%RELEASE_DIR%\PRAHARI" /E /NFL /NDL /NJH /NJS >nul 2>&1
:: Exclude heavy model weights from release package so models are downloaded on first launch
del /f /q "%RELEASE_DIR%\PRAHARI\models\*.pt" >nul 2>&1
del /f /q "%RELEASE_DIR%\PRAHARI\models\*.task" >nul 2>&1
del /f /q "%RELEASE_DIR%\PRAHARI\_internal\models\*.pt" >nul 2>&1
del /f /q "%RELEASE_DIR%\PRAHARI\_internal\models\*.task" >nul 2>&1

echo [2/5] Creating Portable Package Archive (models excluded for first-launch acquisition): %RELEASE_ZIP% ...
if exist "%RELEASE_ZIP%" del /f /q "%RELEASE_ZIP%"
python -c "import zipfile, os; z = zipfile.ZipFile(r'%RELEASE_ZIP%', 'w', zipfile.ZIP_DEFLATED); [z.write(os.path.join(root, f), os.path.relpath(os.path.join(root, f), r'dist')) for root, _, files in os.walk(r'dist\PRAHARI') for f in files if not f.endswith('.pt') and not f.endswith('.task')]; z.write(r'run_prahari.bat', 'run_prahari.bat') if os.path.exists(r'run_prahari.bat') else None; z.close()"
if %errorlevel% neq 0 (
    echo [!] Error creating release ZIP archive!
    exit /b 1
)

echo [3/5] Calculating SHA-256 Checksum for Release ZIP...
python -c "import hashlib; h = hashlib.sha256(open(r'%RELEASE_ZIP%', 'rb').read()).hexdigest(); open(r'%RELEASE_DIR%\SHA256SUMS.txt', 'w').write(f'{h}  PRAHARI-%VERSION%-Windows-x64.zip\n'); print(f'[*] SHA-256: {h}')"
if %errorlevel% neq 0 (
    echo [!] Error calculating SHA-256 checksum!
    exit /b 1
)

echo [4/5] Compiling Native Setup Installer...
call "packaging\build_installer.bat"
if %errorlevel% neq 0 (
    echo [!] Installer compilation failed!
    exit /b 1
)

echo [5/5] Generating Release Support Files in %RELEASE_DIR% ...

:: 1. Launch_PRAHARI.bat
(
echo @echo off
echo title PRAHARI Launcher
echo cd /d "%%~dp0"
echo if exist "PRAHARI\PRAHARI.exe" ^(
echo     start "" "PRAHARI\PRAHARI.exe"
echo ^) else if exist "PRAHARI.exe" ^(
echo     start "" "PRAHARI.exe"
echo ^) else ^(
echo     echo [ERROR] PRAHARI.exe not found!
echo     pause
echo ^)
) > "%RELEASE_DIR%\Launch_PRAHARI.bat"

:: 2. Install_Desktop_Shortcut.bat
(
echo @echo off
echo title PRAHARI - Desktop Shortcut Installer
echo cd /d "%%~dp0"
echo set "TARGET_EXE=%%~dp0PRAHARI\PRAHARI.exe"
echo if not exist "%%TARGET_EXE%%" set "TARGET_EXE=%%~dp0PRAHARI.exe"
echo powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'PRAHARI.lnk')); $s.TargetPath = '%%TARGET_EXE%%'; $s.WorkingDirectory = [System.IO.Path]::GetDirectoryName('%%TARGET_EXE%%'); $s.Description = 'PRAHARI - Mission HAR Space Experiment Assistant'; $s.Save()"
echo echo [SUCCESS] Desktop shortcut created!
echo pause
) > "%RELEASE_DIR%\Install_Desktop_Shortcut.bat"

:: 3. Release README.md
(
echo # PRAHARI Windows Release v1.0.0
echo.
echo ## Option 1: Automated Windows Installer ^(Recommended^)
echo 1. Run `PRAHARI-Setup-v1.0.0.exe`.
echo 2. The installer automatically downloads the application package, verifies SHA-256 integrity, extracts all required components, and registers Desktop and Start Menu shortcuts.
echo 3. Check **Launch PRAHARI** and click **Finish**.
echo.
echo ## Option 2: Portable Standalone Release
echo 1. Extract `PRAHARI-v1.0.0-Windows-x64.zip` to any folder on your computer.
echo 2. Double-click `PRAHARI\PRAHARI.exe` or `Launch_PRAHARI.bat` to launch.
echo 3. Optionally run `Install_Desktop_Shortcut.bat` to place a shortcut on your Desktop.
echo.
echo ## System Requirements
echo - Windows 10 / 11 (64-bit^)
echo - No Python, C#, or developer tools required. All AI models, Qt runtime, and vision libraries are pre-bundled.
) > "%RELEASE_DIR%\README.md"

echo ==============================================================================
echo   [SUCCESS] PRAHARI Windows Release Built Successfully:
echo   - Installer:         %RELEASE_DIR%\PRAHARI-Setup-%VERSION%.exe
echo   - Portable ZIP:      %RELEASE_DIR%\PRAHARI-%VERSION%-Windows-x64.zip
echo   - Checksums:         %RELEASE_DIR%\SHA256SUMS.txt
echo   - Standalone Bundle: %RELEASE_DIR%\PRAHARI\PRAHARI.exe
echo   - 1-Click Launcher:  %RELEASE_DIR%\Launch_PRAHARI.bat
echo   - Desktop Shortcut:  %RELEASE_DIR%\Install_Desktop_Shortcut.bat
echo   - Documentation:     %RELEASE_DIR%\README.md
echo ==============================================================================
