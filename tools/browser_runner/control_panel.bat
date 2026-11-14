@echo off
:: PS5 Research Control Panel — double-click to launch (requests admin)
:: Or run from an already-admin terminal

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting admin privileges for port 53...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0control_panel.ps1"
pause
