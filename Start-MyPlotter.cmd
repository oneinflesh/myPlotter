@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start\Start-MyPlotter.ps1"
if errorlevel 1 (
    echo.
    echo My Plotter could not start. See the error above.
    pause
)
