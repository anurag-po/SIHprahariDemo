@echo off
setlocal enabledelayedexpansion

echo ==============================================================================
echo   PRAHARI - Native Windows Bootstrapper Installer Compiler (csc.exe)
echo ==============================================================================

cd /d "%~dp0\.."

set "CSC_PATH="
if exist "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe" (
    set "CSC_PATH=C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
) else if exist "C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe" (
    set "CSC_PATH=C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"
)

if "%CSC_PATH%"=="" (
    echo [!] Error: .NET Framework csc.exe compiler not found in C:\Windows\Microsoft.NET\Framework...
    exit /b 1
)

set "VERSION=v1.0.0"
set "RELEASE_DIR=release"
set "OUT_EXE=%RELEASE_DIR%\PRAHARI-Setup-%VERSION%.exe"

if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"

echo [*] Compiling %OUT_EXE% using %CSC_PATH% ...
"%CSC_PATH%" /target:winexe /platform:anycpu /optimize+ /r:System.dll /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /r:System.Core.dll /out:"%OUT_EXE%" "packaging\installer\PRAHARI_Setup.cs"

if %errorlevel% neq 0 (
    echo [!] Compilation failed!
    exit /b 1
)

echo ==============================================================================
echo   [SUCCESS] Bootstrapper Installer Built: %OUT_EXE%
echo ==============================================================================
