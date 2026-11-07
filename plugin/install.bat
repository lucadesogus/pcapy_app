@echo off
rem Double-click to install the Pcapy Wireshark plugins. Pass options through, e.g.: install.bat -Uninstall
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
echo.
pause
