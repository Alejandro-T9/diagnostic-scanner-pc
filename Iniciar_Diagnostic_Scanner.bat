@echo off
setlocal EnableExtensions
title Diagnostic Scanner PC

rem ------------------------------------------------------------------
rem Lanzador de Diagnostic Scanner PC (modo portable, Windows 10/11).
rem
rem Doble clic: pide permisos de administrador (para leer temperaturas,
rem voltajes y S.M.A.R.T.), detecta si corre desde el USB o desde la
rem carpeta de desarrollo y arranca backend\lanzador.py.
rem
rem Si el usuario rechaza el aviso de Windows, la app abre igual pero sin
rem administrador (algunos sensores saldran como no_determinado).
rem
rem Uso: Iniciar_Diagnostic_Scanner.bat [elevado] [argumentos...]
rem   "elevado" lo pone el propio .bat al relanzarse con administrador; con
rem   ese argumento nunca vuelve a pedir elevacion. Los demas argumentos
rem   (por ejemplo --sin-navegador) se pasan tal cual a lanzador.py.
rem ------------------------------------------------------------------

rem Guardar ya la ruta de este .bat: SHIFT tambien desplaza %0 y despues
rem %~dp0 y %~f0 dejarian de apuntar a este archivo.
set "AQUI=%~dp0"
set "ESTE_BAT=%~f0"

set "ELEVADO=0"
if /i "%~1"=="elevado" set "ELEVADO=1"
if "%ELEVADO%"=="1" shift

rem Recoger los argumentos restantes para reenviarlos a lanzador.py.
rem (shift no cambia %*, por eso se arma la lista a mano.)
set "ARGS="
:recoger
if "%~1"=="" goto fin_recoger
set ARGS=%ARGS% %1
shift
goto recoger
:fin_recoger

rem --- Paso 1: administrador ---------------------------------------
rem "net session" solo funciona con permisos de administrador.
net session >nul 2>&1
if not errorlevel 1 goto detectar
if "%ELEVADO%"=="1" goto detectar

echo Se pedira permiso de administrador para poder leer los sensores.
echo Si lo rechazas, la aplicacion abre igual pero con lecturas reducidas.
rem Un apostrofo en la ruta romperia el comando de PowerShell: se duplica.
set "ESTE_BAT_PS=%ESTE_BAT:'=''%"
rem Se lanza cmd.exe con /s /c y comillas dobles explicitas ([char]34): si se
rem ejecutara el .bat directo, Windows lo corre como cmd /C "ruta" y su manejo
rem de comillas falla con carpetas que llevan &, @ o parentesis sin espacios.
rem Linea final: cmd.exe /s /c ""ruta\este.bat" elevado"
powershell -NoProfile -Command "Start-Process cmd.exe -ArgumentList ('/s /c '+[char]34+[char]34+'%ESTE_BAT_PS%'+[char]34+' elevado'+[char]34) -Verb RunAs -ErrorAction Stop" >nul 2>&1
if errorlevel 1 goto sin_admin
rem Se abrio la ventana con administrador: esta ya no hace falta.
exit /b 0

:sin_admin
echo.
echo No se concedio el permiso de administrador. Se continua sin el:
echo algunos sensores (temperaturas, voltajes, S.M.A.R.T.) no se podran leer.
echo.

rem --- Paso 2: detectar el diseno de carpetas ----------------------
:detectar
set "LANZADOR_USB=%AQUI%diagnostic_scanner_pc\backend\lanzador.py"
set "LANZADOR_DEV=%AQUI%backend\lanzador.py"
set "PYTHON_USB=%AQUI%python-portable\python.exe"

if exist "%LANZADOR_USB%" goto diseno_usb
if exist "%LANZADOR_DEV%" goto diseno_dev
goto falta_lanzador

:diseno_usb
rem USB: el Python viene en la carpeta python-portable junto a este .bat.
set "LANZADOR=%LANZADOR_USB%"
set "PYTHON=%PYTHON_USB%"
if exist "%PYTHON%" goto ejecutar
echo.
echo ERROR: no se encontro el Python portable del USB.
echo   Se busco en: "%PYTHON%"
echo Copia la carpeta python-portable junto a este archivo.
goto fallo

:diseno_dev
rem Desarrollo: se usa el Python instalado en el PATH.
set "LANZADOR=%LANZADOR_DEV%"
set "PYTHON=python"
rem Comprobar que python responde (ignora el acceso directo vacio de la
rem tienda de Windows, que existe pero no ejecuta nada).
python -c "" >nul 2>&1
if not errorlevel 1 goto ejecutar
echo.
echo ERROR: no se encontro Python en el PATH.
echo   Instala Python 3.10 o superior y marca "Add Python to PATH".
echo   (Diseno de desarrollo detectado: "%LANZADOR_DEV%")
goto fallo

:falta_lanzador
echo.
echo ERROR: no se encontro el programa Diagnostic Scanner PC.
echo   Se busco en:
echo     "%LANZADOR_USB%"
echo     "%LANZADOR_DEV%"
echo Ejecuta este archivo desde la raiz del USB o de la carpeta del proyecto.
goto fallo

rem --- Paso 3: ejecutar --------------------------------------------
:ejecutar
"%PYTHON%" "%LANZADOR%"%ARGS%
set "CODIGO=%errorlevel%"
if "%CODIGO%"=="0" exit /b 0
echo.
echo El programa termino con error (codigo %CODIGO%).
pause
exit /b %CODIGO%

:fallo
echo.
pause
exit /b 1
