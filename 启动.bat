@echo off
rem Start the launcher through the bundled pythonw (launcher\spawn.py, no window); fall back to hidden powershell
if not exist "%~dp0launcher\python\pythonw.exe" goto ps
if not exist "%~dp0launcher\spawn.py" goto ps
start "" "%~dp0launcher\python\pythonw.exe" -I "%~dp0launcher\spawn.py" gui.ps1
goto :eof
:ps
start "" powershell -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File "%~dp0launcher\gui.ps1"
