"""
backend/analisis/controladores.py — Dispositivos con driver faltante o con error.

SOLO LECTURA, sin administrador: consulta WMI (Win32_PnPEntity) por dispositivos cuyo código de
error es distinto de 0. Se ignoran los deshabilitados a propósito (código 22). No revisa versiones
de drivers ni si hay uno más nuevo.
"""

import wmi

_MAX = 50
_RECOMENDACIONES = {
    "normal": "No hace falta hacer nada.",
    "advertencia": "Abre el Administrador de dispositivos y revisa los que tienen un signo de advertencia.",
    "sospecha": "Instala los drivers del fabricante del equipo o pide ayuda a un técnico.",
    "critico": "Este análisis no produce este nivel; trátalo como un error del análisis.",
    "no_determinado": "Abre el Administrador de dispositivos y repite el análisis.",
}


def _leer_dispositivos() -> list:
    c = wmi.WMI()
    return [{"nombre": d.Name or "Dispositivo sin nombre", "codigo": int(d.ConfigManagerErrorCode)}
            for d in c.query("SELECT Name, ConfigManagerErrorCode FROM Win32_PnPEntity WHERE ConfigManagerErrorCode <> 0")
            if int(d.ConfigManagerErrorCode) != 22]  # 22 = deshabilitado por el usuario


def _clasificar(n) -> tuple:
    if not isinstance(n, int) or n < 0:
        return "no_determinado", "No se pudo leer la lista de dispositivos."
    if n == 0:
        return "normal", "Windows no marca ningún dispositivo con problema de controlador."
    texto = f"Windows marca {n} dispositivo{'s' if n != 1 else ''} con problema de controlador."
    return ("sospecha" if n >= 3 else "advertencia"), texto


def diagnosticar() -> dict:
    try:
        lista = _leer_dispositivos()
        n = len(lista)
    except Exception:
        lista, n = [], None
    estado, mensaje = _clasificar(n)
    return {"componente": "controladores", "estado": estado, "mensaje": mensaje,
            "datos": {"total": n, "dispositivos": lista[:_MAX]}, "recomendacion": _RECOMENDACIONES[estado]}
