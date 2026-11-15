@echo off
REM ===================================================================
REM  Laptop Remote -- REMOVE everything setup.bat installed (run this one file).
REM  Double-click it. It will ask for administrator rights, then stop the
REM  server, remove the start-with-Windows shortcut and the Defender
REM  exclusion, and delete the installed folder.
REM ===================================================================
setlocal

net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo Asking for administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

if exist "%~dp0uninstall.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$f=Join-Path $env:TEMP 'laptop-remote-uninstall.ps1'; Invoke-WebRequest 'https://raw.githubusercontent.com/Muhammad-Zohaib-Zaheer/laptop-remote/main/uninstall.ps1' -OutFile $f -UseBasicParsing; & $f"
)

echo.
pause
