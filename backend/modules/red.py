"""
backend/modules/red.py — Diagnóstico de tarjetas de red (WMI, Windows/WinPE).

Win32_NetworkAdapter(PhysicalAdapter=True) enumera interfaces físicas.
Win32_PerfFormattedData_Tcpip_NetworkInterface da errores de paquetes,
cruzado por nombre de adaptador (WMI no tiene una sola clase con ambos
datos).

Nota: en pruebas, adaptadores virtuales de software de virtualización
(ej. VirtualBox Host-Only) a veces se filtran como PhysicalAdapter=True
igual — quirk conocido de WMI, no afecta laptops sin ese software.

Clasificación: sin enlace en ninguna interfaz = advertencia (decisión 36);
la red nunca produce "critico".
"""

import wmi

# Win32_NetworkAdapter.Speed devuelve este valor centinela cuando la
# velocidad no está disponible (adaptador sin enlace) — no es una
# velocidad real, hay que descartarlo explícitamente.
_SPEED_DESCONOCIDA = 2**63 - 1

_CONECTADO = 2  # Win32_NetworkAdapter.NetConnectionStatus

_RECOMENDACIONES = {
    "normal": "",
    "sospecha": "Revisar cables/antena — hay enlace pero con errores de paquetes, evidencia de un posible problema.",
    "advertencia": "Revisa que el cable o el Wi-Fi estén conectados; si sigue sin conexión, revisa la tarjeta de red o su driver.",
    "critico": "Estado no alcanzable para la red: sin enlace es advertencia. Repetir el análisis.",
    "no_determinado": "No se detectó ninguna interfaz de red — revisar hardware o driver.",
}


def diagnosticar() -> dict:
    try:
        conexion = wmi.WMI()
        adaptadores = conexion.Win32_NetworkAdapter(PhysicalAdapter=True)
        contadores = {c.Name: c for c in conexion.Win32_PerfFormattedData_Tcpip_NetworkInterface()}
    except wmi.x_wmi as error:
        return _resultado_error(f"No se pudo consultar WMI: {error}")

    if not adaptadores:
        return _resultado_error("No se detectó ninguna interfaz de red física.")

    resultados = [_diagnosticar_interfaz(a, contadores) for a in adaptadores]
    estado, mensaje = _clasificar(resultados)
    return {
        "componente": "red", "estado": estado, "mensaje": mensaje, "datos": {"interfaces": resultados},
        "recomendacion": _RECOMENDACIONES[estado],
    }


def _diagnosticar_interfaz(adaptador, contadores: dict) -> dict:
    contador = contadores.get(adaptador.Name)
    return {
        "nombre": adaptador.Name,
        "link_activo": adaptador.NetConnectionStatus == _CONECTADO,
        "velocidad_mbps": _velocidad_mbps(adaptador.Speed),
        "errores_rx": int(contador.PacketsReceivedErrors) if contador else None,
    }


def _velocidad_mbps(velocidad):
    if velocidad is None or int(velocidad) >= _SPEED_DESCONOCIDA:
        return None
    return int(velocidad) // 1_000_000


def _clasificar(resultados: list) -> tuple:
    con_link = [i for i in resultados if i["link_activo"]]
    if not con_link:
        # Decisión 36: sin enlace puede ser solo Wi-Fi apagado o sin cable; no es "crítico".
        return "advertencia", "Ninguna interfaz de red tiene enlace activo."

    con_errores = [i for i in con_link if i.get("errores_rx") is not None and i["errores_rx"] > 0]
    if con_errores:
        return "sospecha", f"Enlace activo, pero con errores de paquetes en: {', '.join(i['nombre'] for i in con_errores)}."

    # Un contador de errores no leído (None) no es lo mismo que "0 errores
    # confirmados" — antes se trataban igual y el enlace salía "normal"
    # sin haber verificado nada realmente.
    sin_dato = [i for i in con_link if i.get("errores_rx") is None]
    if sin_dato:
        return "no_determinado", f"Enlace activo, pero no se pudo leer el conteo de errores de paquetes en: {', '.join(i['nombre'] for i in sin_dato)}."

    return "normal", f"Enlace activo en: {', '.join(i['nombre'] for i in con_link)}."


def _resultado_error(mensaje: str) -> dict:
    return {
        "componente": "red", "estado": "no_determinado", "mensaje": mensaje, "datos": None,
        "recomendacion": _RECOMENDACIONES["no_determinado"],
    }
