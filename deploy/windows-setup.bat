@echo off
chcp 65001 >nul
title GMO Bot Setup

echo ========================================
echo   GMO Bot Windows Setup
echo ========================================
echo.

:: Administrator check
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Administrator privileges required. Restarting...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo Running as Administrator...
echo.

:: Execute PowerShell script
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows-setup.ps1"

echo.
echo Setup complete. Press any key to close...
pause >nul
