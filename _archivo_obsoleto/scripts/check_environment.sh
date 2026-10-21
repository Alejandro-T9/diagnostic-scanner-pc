#!/bin/sh
# scripts/check_environment.sh — Verifica que el entorno tenga todo lo que
# Diagnostic Scanner PC necesita para correr: Python 3.10+, Flask/psutil
# importables, y las 9 herramientas CLI de diagnóstico.
#
# Diferencia entre "crítico" y "opcional": Python/Flask/psutil son
# bloqueantes (sin ellos el servidor ni arranca). Las 9 herramientas CLI
# no lo son — backend/scanner.py ya tolera que falte cualquiera de ellas
# y marca solo ese componente como "error", sin tumbar el resto del
# escaneo. Por eso una herramienta faltante se reporta pero no hace
# fallar este script; que falte Python/Flask/psutil sí.

HERRAMIENTAS="smartctl dmidecode sensors lscpu lsblk lsusb ethtool stress-ng memtester"
TOTAL_HERRAMIENTAS=9
PYTHON_MINIMO="3.10"

falla_critica=0

echo "=== Diagnostic Scanner PC — verificación de entorno ==="
echo ""

echo "--- Herramientas de diagnóstico ---"
disponibles=0
for herramienta in $HERRAMIENTAS; do
    if command -v "$herramienta" >/dev/null 2>&1; then
        echo "[OK]    $herramienta"
        disponibles=$((disponibles + 1))
    else
        echo "[FALTA] $herramienta"
    fi
done
echo ""
echo "Resumen: $disponibles de $TOTAL_HERRAMIENTAS herramientas disponibles."
echo ""

echo "--- Python y dependencias ---"
if ! command -v python3 >/dev/null 2>&1; then
    echo "[FALTA] python3 no está en el PATH"
    falla_critica=1
else
    version="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
        echo "[OK]    python3 $version (mínimo requerido: $PYTHON_MINIMO)"
    else
        echo "[FALTA] python3 $version es menor al mínimo requerido ($PYTHON_MINIMO)"
        falla_critica=1
    fi

    if python3 -c 'import flask' >/dev/null 2>&1; then
        echo "[OK]    Flask importa correctamente"
    else
        echo "[FALTA] Flask no importa (¿corriste scripts/install_tools.sh?)"
        falla_critica=1
    fi

    if python3 -c 'import psutil' >/dev/null 2>&1; then
        echo "[OK]    psutil importa correctamente"
    else
        echo "[FALTA] psutil no importa (¿corriste scripts/install_tools.sh?)"
        falla_critica=1
    fi
fi
echo ""

if [ "$falla_critica" = "1" ]; then
    echo "[ERROR] Faltan requisitos críticos (Python/Flask/psutil). El servidor no puede arrancar."
    exit 1
fi

echo "[OK] Entorno listo. El servidor puede arrancar aunque falten herramientas de diagnóstico."
exit 0
