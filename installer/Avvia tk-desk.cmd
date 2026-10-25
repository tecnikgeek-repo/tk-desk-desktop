@echo off
rem Avvia tk-desk (nessuna installazione). Impostazioni e rubrica stanno nella cartella "Dati".
start "" "%~dp0app\python\pythonw.exe" "%~dp0app\run.py" %*
