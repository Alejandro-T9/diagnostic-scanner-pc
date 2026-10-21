# .bash_profile del usuario kiosk (autologin en tty1, ver
# etc/systemd/system/getty@tty1.service.d/autologin.conf). Arranca X solo
# la primera vez que se loguea en tty1 — si X falla al iniciar, o si se
# cierra del todo pese al bucle de reintento de .xinitrc, cae acá y
# muestra un diagnóstico en consola en vez de dejar una pantalla en blanco
# sin explicación (misma filosofía de degradación elegante que el resto
# del proyecto).

if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    startx -- -nocursor > /tmp/xorg.log 2>&1

    clear
    echo ""
    echo "=================================================="
    echo " Diagnostic Scanner PC"
    echo " El entorno grafico no pudo iniciar o se cerro."
    echo ""
    echo " IP: $(hostname -I)"
    echo " Dashboard (si el servidor sigue corriendo): http://$(hostname -I | awk '{print $1}'):5000"
    echo " Log de X: /tmp/xorg.log"
    echo "=================================================="
    echo ""
fi
