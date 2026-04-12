@echo off
setlocal enabledelayedexpansion
title Shekel Print Agent - Windows Setup

echo ========================================
echo   Shekel Print Agent - Windows Setup
echo ========================================
echo.

REM ── Check for admin ─────────────────────────────────────────────
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script needs administrator privileges.
    echo.
    echo Right-click setup-windows.bat and select
    echo "Run as administrator"
    echo.
    pause
    exit /b 1
)

REM ── Check printer ────────────────────────────────────────────────
echo [1/4] Checking for printer...
powershell -Command "Get-PnpDevice | Where-Object {$_.InstanceId -like '*0FE6*'}" 2>nul | findstr /i "0fe6" >nul
if %errorLevel% equ 0 (
    echo   Printer detected.
) else (
    echo   WARNING: Printer not detected automatically.
    echo   Make sure POS58 is plugged in and powered on.
    echo   Continuing anyway...
    echo.
)

REM ── Install agent ────────────────────────────────────────────────
echo [2/4] Installing agent...
set AGENT_SRC=%~dp0shekel-agent.exe

if not exist "%AGENT_SRC%" (
    echo ERROR: shekel-agent.exe not found.
    echo Make sure shekel-agent.exe is in the same folder as this script.
    pause
    exit /b 1
)

mkdir "%APPDATA%\ShekelAgent" 2>nul
copy /Y "%AGENT_SRC%" "%APPDATA%\ShekelAgent\shekel-agent.exe" >nul
echo   Agent installed to %APPDATA%\ShekelAgent\

REM ── Create silent VBS launcher ───────────────────────────────────
set VBS=%APPDATA%\ShekelAgent\shekel-agent-launcher.vbs
echo Set WshShell = CreateObject("WScript.Shell") > "%VBS%"
echo WshShell.Run """%APPDATA%\ShekelAgent\shekel-agent.exe""", 0, False >> "%VBS%"
echo   Silent launcher created.

REM ── Ask about autostart ──────────────────────────────────────────
echo [3/4] Autostart setup...
echo.
echo   Do you want the print agent to start
echo   automatically every time you log in?
echo.
echo   [Y] Yes - start automatically on login
echo   [N] No  - I will start it manually
echo.
set /p AUTOSTART="   Your choice (Y/N): "

if /i "%AUTOSTART%"=="Y" (
    schtasks /delete /tn "ShekelPrintAgent" /f >nul 2>&1
    schtasks /create /tn "ShekelPrintAgent" ^
        /tr "wscript.exe \"%APPDATA%\ShekelAgent\shekel-agent-launcher.vbs\"" ^
        /sc onlogon ^
        /rl highest ^
        /f >nul
    if %errorLevel% equ 0 (
        echo   Autostart enabled via Task Scheduler.
    ) else (
        echo   Task Scheduler failed. Trying Startup folder...
        copy /Y "%VBS%" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\shekel-agent-launcher.vbs" >nul
        echo   Autostart enabled via Startup folder.
    )
) else (
    echo   Autostart skipped.
    echo   To start manually run:
    echo   %APPDATA%\ShekelAgent\shekel-agent.exe
)

REM ── Start agent now in background ────────────────────────────────
echo [4/4] Starting agent now...
wscript.exe "%VBS%"
timeout /t 3 /nokey >nul

curl -s http://localhost:8765/health >nul 2>&1
if %errorLevel% equ 0 (
    echo   Agent is running successfully.
) else (
    echo   WARNING: Could not verify agent is running.
    echo   Check http://localhost:8765/health in your browser.
)

echo.
echo ========================================
echo   Setup complete!
echo.
echo   Agent is running silently
echo   in the background.
echo.
echo   You can delete this folder now.
echo   Everything is saved to:
echo   %APPDATA%\ShekelAgent\
echo.
echo   Verify anytime at:
echo   http://localhost:8765/health
echo ========================================
pause