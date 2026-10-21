@echo off
setlocal
set PROYECTO=%~dp0

echo Iniciando Diagnostic Scanner PC (demo local)...
start "flask" /min python "%PROYECTO%backend\app.py"

timeout /t 2 /nobreak >nul

start "" "http://localhost:5000"

echo Listo. El dashboard deberia abrirse en tu navegador.
pause
