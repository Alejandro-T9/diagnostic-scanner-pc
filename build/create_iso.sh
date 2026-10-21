#!/bin/sh
# build/create_iso.sh — v2 (Debian Live): genera una ISO Debian booteable
# con Diagnostic Scanner PC preinstalado, Flask autoarrancando por systemd,
# y Chromium en modo kiosk autoarrancando por X11 (autologin en tty1).
# Reemplaza la versión v1 basada en Alpine (ver docs/DECISIONES.md para el
# motivo de la migración).
#
# La configuración del kiosk (autologin, .xinitrc, política de Chromium)
# vive en build/overlay/ — este script solo la copia al chroot tal cual.
#
# DÓNDE CORRE: dentro de una Debian Live ya booteada (la misma XFCE que
# estás probando), NO en Windows. Necesita squashfs-tools y xorriso
# (se instalan solos si faltan) y debe correr como root.
#
# Uso:
#   sudo sh build/create_iso.sh /ruta/a/debian-live-13.6.0-amd64-xfce.iso
#
# Por qué esto es más confiable que la v1 de Alpine: Debian Live monta su
# raíz como un filesystem.squashfs de solo lectura + overlay (confirmado
# en vivo con `mount | grep squashfs`) — no hay nada que Alpine "adivinara"
# al arrancar (apkovl por hostname, cache autodetectada). Acá todo lo que
# quede DENTRO del squashfs nuevo es exactamente lo que bootea, sin magia
# adicional en tiempo de arranque.
#
# Qué hace, en orden:
#   1. Monta la ISO original y extrae su live/filesystem.squashfs a una
#      carpeta de trabajo (unsquashfs) — la sesión live que estás usando
#      ahora nunca se empaqueta a sí misma, así no se cuela nada de
#      "mesa de trabajo" (curl, terminal abierta, etc.) en la imagen final.
#   2. chroot a esa carpeta (con /proc /sys /dev montados adentro).
#   3. Adentro: scripts/install_tools.sh, copia del proyecto a
#      /opt/diagnostic-scanner-pc, servicio systemd, /etc/issue con la IP.
#   4. Sale del chroot, desmonta, comprime todo en un filesystem.squashfs
#      nuevo (mksquashfs).
#   5. xorriso arma la ISO final, reemplazando solo live/filesystem.squashfs
#      y preservando el arranque BIOS/UEFI original tal cual
#      (-boot_image any replay).

set -e

RUTA_ISO_ORIGINAL="$1"
RUTA_PROYECTO="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
DIR_TRABAJO="/tmp/build-diagnostic-scanner-iso"
DIR_MEDIO="$DIR_TRABAJO/medio-original"
DIR_CHROOT="$DIR_TRABAJO/chroot"
ISO_FINAL="$RUTA_PROYECTO/build/diagnostic-scanner-pc.iso"

morir() {
    echo "[ERROR] $1" >&2
    exit 1
}

verificar_requisitos() {
    [ "$(id -u)" = "0" ] || morir "Corré este script como root (sudo)."
    [ -n "$RUTA_ISO_ORIGINAL" ] || morir "Uso: $0 <ruta-a-debian-live-....iso>"
    [ -f "$RUTA_ISO_ORIGINAL" ] || morir "No existe el archivo: $RUTA_ISO_ORIGINAL"
}

instalar_herramientas_build() {
    echo "[INFO] Instalando herramientas de build (squashfs-tools, xorriso)..."
    apt-get update || morir "Falló 'apt-get update'."
    apt-get install -y --no-install-recommends squashfs-tools xorriso || morir "No se pudo instalar squashfs-tools/xorriso."
}

montar_iso_original() {
    echo "[INFO] Montando la ISO original..."
    mkdir -p "$DIR_MEDIO"
    mount -o loop,ro "$RUTA_ISO_ORIGINAL" "$DIR_MEDIO" || morir "No se pudo montar $RUTA_ISO_ORIGINAL."
    [ -f "$DIR_MEDIO/live/filesystem.squashfs" ] || morir "No encontré live/filesystem.squashfs — ¿es una ISO Debian Live válida?"
}

extraer_squashfs_original() {
    echo "[INFO] Extrayendo filesystem.squashfs original a $DIR_CHROOT..."
    rm -rf "$DIR_CHROOT"
    unsquashfs -d "$DIR_CHROOT" "$DIR_MEDIO/live/filesystem.squashfs" || morir "Falló unsquashfs."
}

# Desmonta todo lo que se haya montado, en cualquier punto en que falle el
# script — evita dejar /proc, /sys o /dev bind-montados sueltos dentro de
# DIR_CHROOT si algo se corta a mitad de camino.
limpiar_montajes() {
    umount "$DIR_CHROOT/dev/pts" 2>/dev/null || true
    umount "$DIR_CHROOT/dev" 2>/dev/null || true
    umount "$DIR_CHROOT/sys" 2>/dev/null || true
    umount "$DIR_CHROOT/proc" 2>/dev/null || true
    umount "$DIR_MEDIO" 2>/dev/null || true
}
trap limpiar_montajes EXIT

preparar_chroot() {
    echo "[INFO] Montando /proc, /sys, /dev dentro del chroot..."
    mount --bind /proc "$DIR_CHROOT/proc"
    mount --bind /sys "$DIR_CHROOT/sys"
    mount --bind /dev "$DIR_CHROOT/dev"
    mount --bind /dev/pts "$DIR_CHROOT/dev/pts"
    cp /etc/resolv.conf "$DIR_CHROOT/etc/resolv.conf"
}

copiar_proyecto_a_chroot() {
    echo "[INFO] Copiando el proyecto a $DIR_CHROOT/opt/diagnostic-scanner-pc..."
    mkdir -p "$DIR_CHROOT/opt/diagnostic-scanner-pc"
    cp -r "$RUTA_PROYECTO"/backend "$RUTA_PROYECTO"/frontend "$RUTA_PROYECTO"/config "$RUTA_PROYECTO"/scripts \
        "$DIR_CHROOT/opt/diagnostic-scanner-pc/"
}

instalar_paquetes_en_chroot() {
    echo "[INFO] Instalando dependencias dentro del chroot (install_tools.sh)..."
    chroot "$DIR_CHROOT" sh /opt/diagnostic-scanner-pc/scripts/install_tools.sh || morir "Falló install_tools.sh dentro del chroot."
}

instalar_kiosk_en_chroot() {
    echo "[INFO] Instalando Chromium y X11 para el modo kiosk..."
    chroot "$DIR_CHROOT" sh -c "export DEBIAN_FRONTEND=noninteractive && apt-get install -y --no-install-recommends chromium xserver-xorg xinit x11-xserver-utils" \
        || morir "Falló instalar el stack de kiosk (chromium/xserver-xorg/xinit)."
}

copiar_overlay_kiosk() {
    echo "[INFO] Copiando configuración de autologin/kiosk (build/overlay/)..."
    cp -a "$RUTA_PROYECTO/build/overlay/." "$DIR_CHROOT/"
    chroot "$DIR_CHROOT" chown -R user:user /home/user
    chmod +x "$DIR_CHROOT/home/user/.xinitrc"
}

instalar_servicio_systemd() {
    echo "[INFO] Configurando el servicio systemd..."
    cat > "$DIR_CHROOT/etc/systemd/system/diagnostic-scanner.service" <<'EOF'
[Unit]
Description=Diagnostic Scanner PC - servidor Flask
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/diagnostic-scanner-pc/backend
ExecStart=/usr/bin/python3 app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
    # Symlink directo en vez de "systemctl enable": adentro de un chroot
    # sin systemd corriendo como PID 1, es lo mismo que haría "enable" pero
    # sin depender de que el daemon esté vivo para procesarlo.
    mkdir -p "$DIR_CHROOT/etc/systemd/system/multi-user.target.wants"
    ln -sf /etc/systemd/system/diagnostic-scanner.service \
        "$DIR_CHROOT/etc/systemd/system/multi-user.target.wants/diagnostic-scanner.service"
}

configurar_banner_ip() {
    echo "[INFO] Configurando /etc/issue con la IP..."
    cat > "$DIR_CHROOT/etc/issue" <<'EOF'

Diagnostic Scanner PC
======================
Dashboard: http://\4:5000

EOF
}

limpiar_chroot() {
    echo "[INFO] Limpiando cache de apt dentro del chroot..."
    chroot "$DIR_CHROOT" apt-get clean || true
}

recomprimir_squashfs() {
    echo "[INFO] Comprimiendo el chroot modificado en un filesystem.squashfs nuevo..."
    rm -f "$DIR_TRABAJO/filesystem.squashfs"
    mksquashfs "$DIR_CHROOT" "$DIR_TRABAJO/filesystem.squashfs" -comp xz -noappend || morir "Falló mksquashfs."
}

armar_iso_nueva() {
    echo "[INFO] Generando la ISO final con xorriso..."
    mkdir -p "$(dirname "$ISO_FINAL")"
    xorriso -indev "$RUTA_ISO_ORIGINAL" \
        -outdev "$ISO_FINAL" \
        -boot_image any replay \
        -map "$DIR_TRABAJO/filesystem.squashfs" /live/filesystem.squashfs \
        -volid "DIAGSCANNER" \
        || morir "Falló xorriso al generar la ISO."
}

verificar_requisitos
instalar_herramientas_build
montar_iso_original
extraer_squashfs_original
preparar_chroot
copiar_proyecto_a_chroot
instalar_paquetes_en_chroot
instalar_kiosk_en_chroot
copiar_overlay_kiosk
instalar_servicio_systemd
configurar_banner_ip
limpiar_chroot
limpiar_montajes
recomprimir_squashfs
armar_iso_nueva

echo "[OK] ISO generada: $ISO_FINAL"
echo "[INFO] Probala booteando esa ISO en una VM NUEVA (no la misma donde corriste este script)."
