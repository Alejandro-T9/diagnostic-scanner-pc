#!/bin/sh
# .xinitrc del usuario kiosk — arranca directo con Chromium en modo kiosk,
# sin gestor de ventanas. El bucle relanza Chromium si se cierra (crash,
# Alt+F4, Ctrl+W, lo que sea): en vez de perseguir cada atajo de escape
# posible uno por uno, aceptamos que se pueda cerrar y hacemos que vuelva
# solo en 2 segundos — no queda nunca un escritorio vacío expuesto.

xset -dpms
xset s off
xset s noblank

while true; do
    chromium \
        --kiosk \
        --noerrdialogs \
        --disable-infobars \
        --disable-session-crashed-bubble \
        --disable-translate \
        --disable-pinch \
        --overscroll-history-navigation=0 \
        --no-first-run \
        --fast --fast-start \
        http://localhost:5000
    sleep 2
done
