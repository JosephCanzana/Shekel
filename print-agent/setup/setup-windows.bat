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

REM ── Add to startup ──────────────────────────────────────────────
echo [2/3] Adding to startup...
set AGENT_SRC=%~dp0shekel-agent.exe

if not exist "%AGENT_SRC%" (
    echo ERROR: shekel-agent.exe not found.
    echo Make sure shekel-agent.exe is in the same folder as this script.
    pause
    exit /b 1
)

set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\shekel-agent.exe
copy /Y "%AGENT_SRC%" "%STARTUP%" >nul
echo   Added to startup folder.

REM ── Start agent now ─────────────────────────────────────────────
echo [3/3] Starting agent...
start "" "%STARTUP%"
echo   Agent started.

echo.
echo ========================================
echo   Setup complete!
echo.
echo   The print agent will now start
echo   automatically every time you log in.
echo.
echo   Keep the terminal window open while
echo   using Shekel.
echo ========================================
pause