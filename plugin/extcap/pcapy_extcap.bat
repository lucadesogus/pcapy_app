@echo off
rem Pcapy capture interface for Wireshark on Windows.
rem Wireshark runs .bat/.exe files from its extcap folder but not .py files, so this launcher starts the
rem Python script that install.ps1 puts in the "pcapy" subfolder next to it.
where py >nul 2>nul && goto usepy
where python >nul 2>nul && goto usepython
echo Pcapy needs Python 3 on your PATH ^(https://www.python.org/downloads/^). 1>&2
exit /b 1
:usepy
py -3 "%~dp0pcapy\pcapy_extcap.py" %*
exit /b %errorlevel%
:usepython
python "%~dp0pcapy\pcapy_extcap.py" %*
exit /b %errorlevel%
