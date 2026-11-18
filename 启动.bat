@echo off
rem Darkforge launcher: the bundled pythonw runs launcher\dfgui.py (no console window)
if not exist "%~dp0launcher\python\pythonw.exe" goto missing
if not exist "%~dp0launcher\dfgui.py" goto missing
start "" "%~dp0launcher\python\pythonw.exe" -I "%~dp0launcher\dfgui.py"
goto :eof
:missing
chcp 65001 >nul
echo 启动器的文件不全（launcher\python 或 launcher\dfgui.py 不见了），请重新解压整合包。
echo 如果是被杀毒软件删掉的，先把整合包文件夹加进杀毒软件的信任区，再重新解压。
pause
