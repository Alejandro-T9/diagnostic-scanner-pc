#!/bin/sh
# scripts/install_tools.sh — Instala en Debian las herramientas de
# diagnóstico y las dependencias Python que necesita Diagnostic Scanner PC.
#
# apt en vez de apk (proyecto migrado de Alpine a Debian Live — ver
# docs/DECISIONES.md). Todo lo que necesitamos vive en el repo "main"
# estándar de Debian, sin habilitar nada extra (a diferencia de Alpine,
# donde stress-ng/memtester exigían el repo "community" aparte).
#
# DEBIAN_FRONTEND=noninteractive: evita que algún paquete se quede
# esperando una respuesta interactiva a mitad de un build desatendido.

set -e

export DEBIAN_FRONTEND=noninteractive

PAQUETES="smartmontools dmidecode lm-sensors util-linux usbutils ethtool stress-ng memtester python3-flask python3-psutil"

morir() {
    echo "[ERROR] $1" >&2
    exit 1
}

[ "$(id -u)" = "0" ] || morir "Este script necesita permisos de root (apt lo requiere)."

echo "[INFO] Actualizando índice de paquetes..."
apt-get update || morir "Falló 'apt-get update'. Revisa la conexión o /etc/apt/sources.list."

echo "[INFO] Instalando paquetes: $PAQUETES"
# shellcheck disable=SC2086
apt-get install -y --no-install-recommends $PAQUETES || morir "Falló 'apt-get install'. Revisa que los nombres de paquete sigan existiendo en este repo."

echo "[OK] Herramientas instaladas correctamente."
