"""
backend/modules/cpu.py — Diagnóstico del procesador (WMI + LibreHardwareMonitorLib, Windows/WinPE).

Win32_Processor para identidad y conteo de núcleos/hilos (sin cambios).
Temperatura de CPU vía MSAcpi_ThermalZoneTemperature (WMI) — sigue como
antes, con el mismo límite ya documentado (no todos los laptops la
exponen).

Velocidad de ventiladores vía LibreHardwareMonitorLib, leída a través del
lector compartido modules/_lhm.py (DLLs en backend/native/lhm/) — cumple la promesa de
"telemetría de ventiladores" del documento institucional del Semillero
(Fase II de objetivos específicos). Es opcional: no todo laptop expone
sensores de RPM — su ausencia se refleja como lista vacía, no como error
del componente completo (degradación elegante).

GPU: telemetría auxiliar vía modules/gpu.py (no es un componente propio,
ver docstring de ese módulo) — se agrega como datos["gpu"], anidado, sin
influir en el estado del Procesador.

IMPORTANTE (encontrado en revisión externa, la misma que motivó el
sistema de 5 estados): antes, "no se pudo leer la temperatura" clasificaba
como "normal" — exactamente el error que ese sistema existe para evitar
("dato no disponible" != "componente normal"). Corregido: ahora es
"no_determinado", igual que ya se corrigió en bateria.py y
almacenamiento.py esta misma sesión.
"""

import psutil
import wmi

from . import _lhm, gpu

UMBRAL_ADVERTENCIA_C = 70
UMBRAL_CRITICO_C = 85
_TEMPERATURA_MIN_C = 0
_TEMPERATURA_MAX_C = 110

_ARQUITECTURAS = {0: "x86", 1: "MIPS", 2: "Alpha", 3: "PowerPC", 5: "ARM", 6: "ia64", 9: "x64"}

_RECOMENDACIONES = {
    "normal": "",
    "advertencia": "Verificar el sistema de enfriamiento — pasta térmica o ventilador podrían necesitar mantenimiento.",
    "critico": "Detener el uso del equipo y revisar refrigeración antes de continuar — riesgo de daño térmico.",
    "no_determinado": "No se pudo evaluar completamente el procesador — si persiste, revisar sensores térmicos o la conexión de WMI.",
}


def diagnosticar() -> dict:
    try:
        conexion = wmi.WMI()
        procesadores = conexion.Win32_Processor()
    except wmi.x_wmi as error:
        return _resultado_error(f"No se pudo consultar WMI: {error}")

    if not procesadores:
        return _resultado_error("WMI no devolvió información del procesador.")

    temperatura = _obtener_temperatura_cpu()
    ventiladores = _obtener_ventiladores()
    datos_gpu = gpu.obtener_datos()
    # interval=0.3 (no None): un intervalo corto pero real da una lectura
    # instantánea válida ya en la primera llamada — psutil.cpu_percent()
    # sin intervalo devuelve 0.0 la primera vez que se invoca en el
    # proceso, lo cual sería un dato inventado, no uno real.
    porcentaje_uso = psutil.cpu_percent(interval=0.3)
    datos = _armar_datos(procesadores[0], temperatura, ventiladores, porcentaje_uso, datos_gpu)
    estado, mensaje = _clasificar(datos["nombre"], temperatura)
    return {
        "componente": "cpu", "estado": estado, "mensaje": mensaje, "datos": datos,
        "recomendacion": _RECOMENDACIONES[estado],
    }


def _obtener_temperatura_cpu():
    try:
        raiz_wmi = wmi.WMI(namespace="root/wmi")
        zonas = raiz_wmi.MSAcpi_ThermalZoneTemperature()
        temperaturas = [(z.CurrentTemperature / 10.0) - 273.15 for z in zonas]
        return max(temperaturas) if temperaturas else None
    except wmi.x_wmi:
        return None


def _obtener_ventiladores() -> list:
    """LibreHardwareMonitorLib: velocidad de ventiladores (si el hardware
    expone sensores de RPM), buscando en toda la placa Y en la GPU (un
    ventilador de GPU dedicada suele reportarse bajo el hardware de la
    GPU, no el de la placa). No es garantía en todo laptop — se degrada a
    lista vacía sin tumbar el resto del diagnóstico de CPU."""
    return [
        {"nombre": sensor["nombre"], "rpm": round(sensor["valor"])}
        for sensor in _lhm.filtrar(_lhm.leer_sensores(), "Fan")
        if sensor["valor"] is not None
    ]


def _armar_datos(procesador, temperatura, ventiladores, porcentaje_uso, datos_gpu) -> dict:
    return {
        "nombre": " ".join((procesador.Name or "Desconocido").split()),
        "arquitectura": _ARQUITECTURAS.get(procesador.Architecture, "Desconocida"),
        "nucleos_fisicos": procesador.NumberOfCores,
        "hilos_logicos": procesador.NumberOfLogicalProcessors,
        "frecuencia_maxima_mhz": procesador.MaxClockSpeed,
        "frecuencia_actual_mhz": procesador.CurrentClockSpeed,
        "porcentaje_uso": porcentaje_uso,
        "temperatura_c": round(temperatura, 1) if temperatura is not None else None,
        "ventiladores": ventiladores,
        "gpu": datos_gpu,
    }


def _clasificar(nombre: str, temperatura) -> tuple:
    """Solo la temperatura del CPU decide el estado del Procesador —
    datos_gpu nunca entra acá a propósito (ver módulo gpu.py): que la GPU
    no tenga sensor de temperatura no es evidencia de nada sobre el CPU."""
    if temperatura is None or not (_TEMPERATURA_MIN_C <= temperatura <= _TEMPERATURA_MAX_C):
        return "no_determinado", f"{nombre}: detectado, pero no se pudo obtener su temperatura mediante los sensores disponibles."
    if temperatura > UMBRAL_CRITICO_C:
        return "critico", f"{nombre}: temperatura crítica ({temperatura:.1f}°C)."
    if temperatura >= UMBRAL_ADVERTENCIA_C:
        return "advertencia", f"{nombre}: temperatura elevada ({temperatura:.1f}°C)."
    return "normal", f"{nombre}: temperatura normal ({temperatura:.1f}°C)."


def _resultado_error(mensaje: str) -> dict:
    return {
        "componente": "cpu", "estado": "no_determinado", "mensaje": mensaje, "datos": None,
        "recomendacion": _RECOMENDACIONES["no_determinado"],
    }
