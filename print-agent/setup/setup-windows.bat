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

REM ── Check printer is plugged in ─────────────────────────────────
echo [1/3] Checking for printer...
powershell -Command "Get-PnpDevice | Where-Object {$_.InstanceId -like '*0FE6*'}" 2>nul | findstr /i "0fe6" >nul
if %errorLevel% equ 0 (
    echo   Printer detected.
) else (
    echo   WARNING: Printer not detected automatically.
    echo   Make sure the POS58 is plugged in and powered on.
    echo   Continuing anyway...
    echo.
)

REM ── Add agent ───────────────────────────────────────────────────
echo [2/3] Setting up agent...
set AGENT_SRC=%~dp0shekel-agent.exe

if not exist "%AGENT_SRC%" (
    echo ERROR: shekel-agent.exe not found.
    echo Make sure shekel-agent.exe is in the same folder as this script.
    pause
    exit /b 1
)

REM Copy agent to AppData so it has a stable path
set AGENT_DEST=%APPDATA%\ShekelAgent\shekel-agent.exe
mkdir "%APPDATA%\ShekelAgent" 2>nul
copy /Y "%AGENT_SRC%" "%AGENT_DEST%" >nul
echo   Agent installed.

REM ── Create VBS launcher (silent background run) ──────────────────
set VBS=%APPDATA%\ShekelAgent\shekel-agent-launcher.vbs
echo Set WshShell = CreateObject("WScript.Shell") > "%VBS%"
echo WshShell.Run """%AGENT_DEST%""", 0, False >> "%VBS%"

REM ── Ask about autostart ─────────────────────────────────────────
echo [3/3] Autostart setup...
echo.
echo   Do you want the print agent to start
echo   automatically every time you log in?
echo.
echo   [Y] Yes - start automatically on login
echo   [N] No  - I will start it manually
echo.
set /p AUTOSTART="   Your choice (Y/N): "

if /i "%AUTOSTART%"=="Y" (
    set STARTUP_VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\shekel-agent-launcher.vbs
    copy /Y "%VBS%" "%STARTUP_VBS%" >nul
    echo   Autostart enabled.
) else (
    echo   Autostart skipped.
    echo   To start manually, run:
    echo   %AGENT_DEST%
)

REM ── Start agent now in background ────────────────────────────────
echo.
echo   Starting agent in background...
cscript //nologo "%VBS%"

REM Wait a moment then verify it started
timeout /t 2 /nokey >nul
curl -s http://localhost:8765/health >nul 2>&1
if %errorLevel% equ 0 (
    echo   Agent is running.
) else (
    echo   WARNING: Could not verify agent is running.
    echo   Try opening http://localhost:8765/health in your browser.
)

echo.
echo ========================================
echo   Setup complete!
echo.
echo   The print agent is running silently
echo   in the background.
echo.
echo   Verify it is running anytime at:
echo   http://localhost:8765/health
echo ========================================
pause