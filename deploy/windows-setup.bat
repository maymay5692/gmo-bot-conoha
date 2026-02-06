@echo off
chcp 65001 >nul
title GMO Bot Setup

echo ========================================
echo   GMO Bot Windows Setup
echo ========================================
echo.

:: 管理者権限チェック
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo 管理者権限が必要です。再起動します...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo 管理者権限で実行中...
echo.

:: PowerShellスクリプトを実行
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows-setup.ps1"

echo.
echo 完了しました。何かキーを押すと閉じます...
pause >nul
