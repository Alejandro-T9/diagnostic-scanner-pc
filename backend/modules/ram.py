"""
backend/modules/ram.py — Diagnóstico de memoria RAM (WMI, Windows/WinPE).

Win32_PhysicalMemory reemplaza a dmidecode para identidad física (tipo,
velocidad, fabricante) y también para la capacidad total: es la suma de
lo físicamente instalado en los módulos, no lo que el sistema operativo
actual ve disponible. Esto último (psutil.virtual_memory().total) puede
ser bastante menor al arrancar desde USB — Ventoy en modo WIMBOOT reserva
parte de la RAM para la propia imagen de arranque — y confundía al
mostrarse como "capacidad total" (probado en hardware real: WMI detectó
2 módulos correctamente pero psutil reportaba 5.85GB en una laptop de
8GB). Se muestran ambos valores por separado, con nombres que no se
prestan a confundirlos.
"""

import wmi
import psutil

UMBRAL_ADVERTENCIA_PORCENTAJE = 80
UMBRAL_CRITICO_PORCENTAJE = 95

_RECOMENDACIONES = {
    "normal": "",
    "advertencia": "Cerrar procesos innecesarios o considerar ampliar RAM si el uso alto es constante.",
    "critico": "Uso de RAM crítico — el equipo puede volverse inestable, revisar procesos o memoria física instalada.",
    "no_determinado": "No se pudo leer la memoria — revisar conexión de WMI.",
}


def diagnosticar() -> dict:
    try:
        conexion = wmi.WMI()
        modulos = conexion.Win32_PhysicalMemory()
    except wmi.x_wmi as error:
        return _resultado_error(f"No se pudo consultar WMI: {error}")

    if not modulos:
        return _resultado_error("WMI no devolvió información de los módulos de memoria (Win32_PhysicalMemory vacío).")

    uso = _obtener_uso_ram()
    datos = _armar_datos(modulos, uso)
    estado, mensaje = _clasificar(uso["porcentaje_uso"])
    return {
        "componente": "ram", "estado": estado, "mensaje": mensaje, "datos": datos,
        "recomendacion": _RECOMENDACIONES[estado],
    }


def _obtener_uso_ram() -> dict:
    memoria = psutil.virtual_memory()
    gb = 1024 ** 3
    return {
        "capacidad_disponible_so_gb": round(memoria.total / gb, 2),
        "porcentaje_uso": memoria.percent,
    }


def _capacidad_fisica_gb(modulos) -> float:
    gb = 1024 ** 3
    total_bytes = sum(int(m.Capacity) for m in modulos if m.Capacity)
    return round(total_bytes / gb, 2)


def _armar_datos(modulos, uso: dict) -> dict:
    primero = modulos[0] if modulos else None
    return {
        "capacidad_fisica_gb": _capacidad_fisica_gb(modulos),
        "capacidad_disponible_so_gb": uso["capacidad_disponible_so_gb"],
        "fabricante": (primero.Manufacturer if primero else None) or "Desconocido",
        "velocidad_mhz": primero.Speed if primero else None,
        "configuracion_canales": _canales(len(modulos)),
        "modulos_detectados": len(modulos),
        "porcentaje_uso": uso["porcentaje_uso"],
    }


def _canales(cantidad_modulos: int) -> str:
    # ponytail: heurística por conteo de módulos poblados, igual que la
    # versión Linux — no lee el mapeo real de canales del chipset.
    if cantidad_modulos >= 2:
        return "Dual channel (o superior)"
    if cantidad_modulos == 1:
        return "Single channel"
    return "Desconocida"


def _clasificar(porcentaje_uso: float) -> tuple:
    if porcentaje_uso > UMBRAL_CRITICO_PORCENTAJE:
        return "critico", f"Uso de RAM crítico: {porcentaje_uso:.1f}%."
    if porcentaje_uso >= UMBRAL_ADVERTENCIA_PORCENTAJE:
        return "advertencia", f"Uso de RAM elevado: {porcentaje_uso:.1f}%."
    return "normal", f"Uso de RAM normal: {porcentaje_uso:.1f}% — no incluye una prueba de integridad de los módulos."


def _resultado_error(mensaje: str) -> dict:
    return {
        "componente": "ram", "estado": "no_determinado", "mensaje": mensaje, "datos": None,
        "recomendacion": _RECOMENDACIONES["no_determinado"],
    }
