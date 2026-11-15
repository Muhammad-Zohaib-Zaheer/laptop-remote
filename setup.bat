@echo off
REM ===================================================================
REM  Laptop Remote -- SET UP everything on this laptop (run this one file).
REM  Double-click it. It will ask for administrator rights, then download
REM  the project and set it all up. uninstall.bat undoes everything.
REM ===================================================================
setlocal

REM This needs administrator rights (Defender exclusion, start-with-Windows).
net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo Asking for administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

REM Use the setup script next to this file if present, otherwise fetch it.
if exist "%~dp0setup.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$f=Join-Path $env:TEMP 'laptop-remote-setup.ps1'; Invoke-WebRequest 'https://raw.githubusercontent.com/zuhaibx69/laptop-remote/main/setup.ps1' -OutFile $f -UseBasicParsing; & $f"
)

echo.
pause
