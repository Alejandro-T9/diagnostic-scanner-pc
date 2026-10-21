"""
backend/modules/mainboard.py — Diagnóstico de tarjeta madre (WMI, Windows/WinPE).

Usa WMI (Win32_BaseBoard, Win32_BIOS) para identidad de la placa. Mismo
criterio que la versión Linux (dmidecode): WMI tampoco expone un "chipset"
real, así que se reporta lo que sí trae: fabricante, modelo, versión de
placa, y datos de BIOS. No se reporta conteo de slots de expansión — WMI
no tiene un equivalente confiable a "dmidecode --type slot" (Win32_SystemSlot
suele venir vacío en laptops).

Señal de salud: igual que antes, muchas placas dejan estos campos con
texto de relleno del fabricante ("To Be Filled By O.E.M.", etc.) — se
detecta y reporta como advertencia.
"""

import wmi

PLACEHOLDERS_OEM = (
    "to be filled", "o.e.m", "default string", "not specified", "unknown", "system manufacturer",
    "desconocido",  # valor de relleno que este mismo módulo usa en _armar_datos cuando WMI no devuelve el dato
)

# Recomendación accionable por estado — cumple lo que el documento
# institucional del Semillero promete ("qué acción correctiva debe
# ejecutarse"), no solo el diagnóstico crudo.
_RECOMENDACIONES = {
    "normal": "",
    "advertencia": "Verificar visualmente la placa — datos de fábrica sin configurar pueden indicar una placa reacondicionada.",
    "critico": "",
    "no_determinado": "No se pudo leer la placa base — revisar conexión de WMI.",
}


def diagnosticar() -> dict:
    try:
        conexion = wmi.WMI()
        placas = conexion.Win32_BaseBoard()
        bios = conexion.Win32_BIOS()
    except wmi.x_wmi as error:
        return _resultado_error(f"No se pudo consultar WMI: {error}")

    if not placas:
        return _resultado_error("WMI no devolvió información de la placa base (Win32_BaseBoard vacío).")

    datos = _armar_datos(placas[0], bios[0] if bios else None)
    estado, mensaje = _clasificar(datos)
    return {
        "componente": "mainboard", "estado": estado, "mensaje": mensaje, "datos": datos,
        "recomendacion": _RECOMENDACIONES[estado],
    }


def _armar_datos(placa_base, bios) -> dict:
    return {
        "fabricante": placa_base.Manufacturer or "Desconocido",
        "modelo": placa_base.Product or "Desconocido",
        "version": placa_base.Version or "Desconocida",
        "bios_vendor": (bios.Manufacturer if bios else None) or "Desconocido",
        "bios_version": (bios.SMBIOSBIOSVersion if bios else None) or "Desconocida",
        "bios_fecha": _formatear_fecha_wmi(bios.ReleaseDate) if bios else "Desconocida",
    }


def _formatear_fecha_wmi(fecha_wmi: str) -> str:
    """WMI devuelve fechas como '20230815000000.000000+000' (formato CIM).
    Nos quedamos con AAAA-MM-DD, que es lo único útil para mostrar."""
    if not fecha_wmi or len(fecha_wmi) < 8:
        return "Desconocida"
    return f"{fecha_wmi[0:4]}-{fecha_wmi[4:6]}-{fecha_wmi[6:8]}"


def _clasificar(datos: dict) -> tuple:
    if _es_placeholder(datos["fabricante"]) or _es_placeholder(datos["modelo"]):
        return "advertencia", "La placa base no expone fabricante/modelo válidos (datos de fábrica sin configurar o BIOS corrupta)."
    return "normal", f"{datos['fabricante']} {datos['modelo']} — BIOS {datos['bios_version']} ({datos['bios_fecha']})."


def _es_placeholder(valor: str) -> bool:
    normalizado = (valor or "").strip().lower()
    if not normalizado:
        return True
    return any(marcador in normalizado for marcador in PLACEHOLDERS_OEM)


def _resultado_error(mensaje: str) -> dict:
    return {
        "componente": "mainboard", "estado": "no_determinado", "mensaje": mensaje, "datos": None,
        "recomendacion": _RECOMENDACIONES["no_determinado"],
    }
