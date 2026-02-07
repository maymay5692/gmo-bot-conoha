@echo off
chcp 65001 >nul
title GMO Bot - Download Release

echo ========================================
echo   GMO Bot Release Downloader
echo ========================================
echo.

:: Administrator check
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Administrator privileges required. Restarting...
    powershell -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

echo Running as Administrator...
echo.

:: Execute PowerShell script (pass all arguments)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0download-release.ps1" %*

echo.
echo Done. Press any key to close...
pause >nul
