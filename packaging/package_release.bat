@echo off
setlocal enabledelayedexpansion

echo ==============================================================================
echo   PRAHARI - Release Packaging & SHA-256 Checksum Generator
echo ==============================================================================

cd /d "%~dp0\.."

set "VERSION=v1.0.0"
set "RELEASE_DIR=release"
set "ZIP_NAME=PRAHARI-%VERSION%-Windows-x64.zip"
set "ZIP_PATH=%RELEASE_DIR%\%ZIP_NAME%"
set "CHECKSUM_FILE=%RELEASE_DIR%\SHA256SUMS.txt"

if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"

if not exist "dist\PRAHARI\PRAHARI.exe" (
    echo [*] dist\PRAHARI not found. Running build_windows.bat first...
    call "packaging\build_windows.bat"
    if %errorlevel% neq 0 (
        echo [!] Build failed. Aborting packaging.
        exit /b 1
    )
)

echo [1/2] Creating Portable Release ZIP: %ZIP_PATH% ...
if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%"

powershell -NoProfile -Command ^
    "Compress-Archive -Path 'dist\PRAHARI\*' -DestinationPath '%ZIP_PATH%' -CompressionLevel Optimal -Force"

if not exist "%ZIP_PATH%" (
    echo [!] Failed to create ZIP archive.
    exit /b 1
)

echo [2/2] Generating SHA-256 Checksum...
powershell -NoProfile -Command ^
    "$hash = (Get-FileHash -Path '%ZIP_PATH%' -Algorithm SHA256).Hash.ToLower(); $line = \"$hash  %ZIP_NAME%\"; Set-Content -Path '%CHECKSUM_FILE%' -Value $line; Write-Host \"SHA256: $hash\""

echo ==============================================================================
echo   [SUCCESS] Package Created: %ZIP_PATH%
echo   [SUCCESS] Checksum Saved:  %CHECKSUM_FILE%
echo ==============================================================================
