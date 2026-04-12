@echo off
title Shekel Print Agent - Uninstall

echo ========================================
echo   Shekel Print Agent - Uninstall
echo ========================================
echo.

REM ── Check for admin ─────────────────────────────────────────────
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script needs administrator privileges.
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

echo [1/4] Stopping agent...
taskkill /f /im shekel-agent.exe >nul 2>&1
echo   Done.

echo [2/4] Removing Task Scheduler entry...
schtasks /delete /tn "ShekelPrintAgent" /f >nul 2>&1
echo   Done.

echo [3/4] Removing startup folder entry...
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\shekel-agent-launcher.vbs" >nul 2>&1
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\shekel-agent.exe" >nul 2>&1
echo   Done.

echo [4/4] Removing agent files...
rmdir /s /q "%APPDATA%\ShekelAgent" >nul 2>&1
echo   Done.

echo.
echo ========================================
echo   Uninstall complete!
echo   All traces removed.
echo ========================================
pause