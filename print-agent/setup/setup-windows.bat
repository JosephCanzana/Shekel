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

REM ── Check printer is plugged in ──────────────────────────────────
echo [1/4] Checking for printer...
powershell -Command "Get-PnpDevice | Where-Object {$_.InstanceId -like '*0FE6*' -or $_.InstanceId -like '*811E*'}" 2>nul | findstr /i "pos\|thermal\|0fe6\|811e" >nul
if %errorLevel% equ 0 (
    echo   Printer detected.
) else (
    echo   WARNING: Printer not detected.
    echo   Make sure the POS58 is plugged in and powered on.
    echo   You can continue, but Zadig may not see it.
    echo.
    pause
)

REM ── Zadig driver install ─────────────────────────────────────────
echo [2/4] Installing WinUSB driver...
echo.
echo   This will open Zadig. Please:
echo   1. Click Options - List All Devices
echo   2. Find your POS58 printer (VID 0FE6 / PID 811E)
echo   3. Set driver to WinUSB
echo   4. Click Replace Driver
echo   5. Close Zadig when done
echo.
echo   Press any key to open Zadig...
pause >nul

REM Download Zadig if not present
set ZADIG=""
if exist "%~dp0zadig.exe" set ZADIG="%~dp0zadig.exe"
if exist "%~dp0zadig-2.9.exe" set ZADIG="%~dp0zadig-2.9.exe"

if %ZADIG%=="" (
    echo ERROR: Zadig not found.
    echo Make sure zadig.exe or zadig-2.9.exe is in the same folder.
    pause
    exit /b 1
)
"%~dp0zadig.exe"
echo   Zadig closed. Continuing...

REM ── Add to startup ───────────────────────────────────────────────
echo [3/4] Adding to startup...
set AGENT_SRC=%~dp0..\dist\shekel-agent.exe
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\shekel-agent.exe

if not exist "%AGENT_SRC%" (
    echo   WARNING: Binary not found at %AGENT_SRC%
    echo   Run 'python build.py' first to build the agent.
    goto :start_skip
)

copy /Y "%AGENT_SRC%" "%STARTUP%" >nul
echo   Added to startup folder.

REM ── Start agent now ──────────────────────────────────────────────
echo [4/4] Starting agent...
start "" "%STARTUP%"
echo   Agent started.

:start_skip
echo.
echo ========================================
echo   Setup complete!
echo.
echo   The print agent will now start
echo   automatically every time you log in.
echo.
echo   A terminal window will appear in the
echo   background when it is running.
echo ========================================
pause