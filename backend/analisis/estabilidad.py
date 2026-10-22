"""
backend/analisis/estabilidad.py — ¿El equipo se ha trabado o apagado solo en los últimos 30 días?

SOLO LECTURA, sin administrador: cuenta eventos del registro "Sistema" de Windows con `wevtutil`
(pantallazos azules, apagados inesperados y errores de disco). Es un conteo de lo que Windows anotó;
no explica la causa ni mide la salud real del disco.
"""

import re
import shutil
import subprocess

DIAS = 30
_MS = DIAS * 24 * 3600 * 1000
_CONSULTAS = {
    "pantallazos_azules": "Provider[@Name='Microsoft-Windows-WER-SystemErrorReporting'] and (EventID=1001)",
    "apagados_inesperados": "Provider[@Name='Microsoft-Windows-Kernel-Power'] and (EventID=41)",
    "errores_disco": "Provider[@Name='disk'] and (EventID=7 or EventID=11 or EventID=51)",
}
_RECOMENDACIONES = {
    "normal": "No hace falta hacer nada; Windows no anotó fallas graves en este periodo.",
    "advertencia": "Si el equipo se traba, anota cuándo pasa y consulta a un técnico antes de que se repita.",
    "sospecha": "Haz una copia de tus archivos importantes y pide a un técnico que revise el disco y la memoria.",
    "critico": "Este análisis no produce este nivel; trátalo como un error del análisis.",
    "no_determinado": "No se pudo leer el registro de Windows; mira el Visor de eventos y repite el análisis.",
}


def _contar(condicion: str):
    """Número de eventos que cumplen la condición en los últimos DIAS; None si no se pudo leer."""
    exe = shutil.which("wevtutil")
    if not exe:
        return None
    consulta = f"*[System[({condicion}) and TimeCreated[timediff(@SystemTime) <= {_MS}]]]"
    r = subprocess.run([exe, "qe", "System", f"/q:{consulta}", "/c:200", "/f:xml"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=15,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        return None
    return len(re.findall(r"<Event[ >]", r.stdout))


def _leer_eventos() -> dict:
    return {nombre: _contar(cond) for nombre, cond in _CONSULTAS.items()}


def _clasificar(c: dict) -> tuple:
    """c = conteos por tipo (None = no se pudo leer). Solo evidencia leída decide el estado."""
    v = {k: n for k, n in c.items() if isinstance(n, int) and n >= 0}
    if not v:
        return "no_determinado", "No se pudo leer el registro de eventos de Windows."
    azules, apagados, disco = v.get("pantallazos_azules", 0), v.get("apagados_inesperados", 0), v.get("errores_disco", 0)
    resumen = f"En {DIAS} días Windows anotó {azules} pantallazo(s) azul(es), {apagados} apagado(s) inesperado(s) y {disco} error(es) de disco."
    if azules >= 3 or disco >= 1:
        return "sospecha", resumen
    if azules >= 1 or apagados >= 2:
        return "advertencia", resumen
    return "normal", resumen


def diagnosticar() -> dict:
    try:
        conteos = _leer_eventos()
        estado, mensaje = _clasificar(conteos)
    except Exception as error:
        conteos, estado, mensaje = {}, "no_determinado", f"No se pudo leer el registro de eventos: {error}"
    return {"componente": "estabilidad", "estado": estado, "mensaje": mensaje,
            "datos": {"dias": DIAS, **{k: v for k, v in conteos.items()}}, "recomendacion": _RECOMENDACIONES[estado]}
