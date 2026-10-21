@echo off
setlocal
set USB=%~dp0
set PYTHON=%USB%python-portable\python.exe
set PROYECTO=%USB%diagnostic_scanner_pc
set CHROME=%USB%chromium\chrome.exe

rem DevTools deshabilitado por politica oficial de Chromium (mismo
rem mecanismo que la version Linux via JSON, adaptado al registro de
rem Windows). Si "reg add" falla por falta de permisos (probando sin ser
rem SYSTEM/admin), el kiosk igual arranca, solo sin esta proteccion --
rem degradacion elegante, no bloqueante.
reg add "HKLM\SOFTWARE\Policies\Chromium" /v DeveloperToolsDisabled /t REG_DWORD /d 1 /f >nul 2>&1

rem Fondo de pantalla propio -- no toca boot.wim, cero riesgo para el
rem arranque (a diferencia de editar iconos/apps del escritorio, que si
rem viven dentro de boot.wim). Solo se ve un par de segundos antes de que
rem Chromium tape toda la pantalla.
rem
rem Se guarda por registro (queda como valor por defecto) pero el
rem repintado real se hace con SystemParametersInfo via Python/ctypes --
rem el truco de "RUNDLL32 UpdatePerUserSystemParameters" no siempre
rem repinta al toque segun el contexto de sesion; SystemParametersInfo es
rem la API que Windows mismo usa para esto, y no depende de esa duda.
reg add "HKCU\Control Panel\Desktop" /v Wallpaper /t REG_SZ /d "%USB%fondo.jpg" /f >nul 2>&1
reg add "HKCU\Control Panel\Desktop" /v WallpaperStyle /t REG_SZ /d "10" /f >nul 2>&1
reg add "HKCU\Control Panel\Desktop" /v TileWallpaper /t REG_SZ /d "0" /f >nul 2>&1
"%PYTHON%" -c "import ctypes; ctypes.windll.user32.SystemParametersInfoW(20, 0, r'%USB%fondo.jpg', 3)" >nul 2>&1

echo Iniciando Diagnostic Scanner PC...
start "flask" /min "%PYTHON%" "%PROYECTO%\backend\app.py"

rem Con debug=False (ver backend/app.py) Flask arranca rapido, pero en
rem hardware real de la USB se vio mas lento que en la PC de desarrollo
rem -- 6 segundos da margen sin alargar mucho el arranque.
timeout /t 6 /nobreak >nul

rem Bucle: si Chromium se cierra (crash, Alt+F4, lo que sea), vuelve a
rem abrir en 2 segundos. Mismo criterio que la version Linux (decision 14
rem en docs/DECISIONES.md) -- no perseguir cada atajo de escape posible,
rem aceptar que se pueda cerrar y que vuelva solo.
:kiosk_loop
"%CHROME%" --kiosk --noerrdialogs --disable-infobars --disable-session-crashed-bubble --disable-translate --disable-pinch --overscroll-history-navigation=0 --no-first-run --fast --fast-start "http://localhost:5000"
timeout /t 2 /nobreak >nul
goto kiosk_loop
