"""
backend/modules/fuente_poder.py — Diagnóstico de fuente de poder (WinPE).

WMI no expone ninguna clase estándar y confiable para voltajes de placa
(ver Fase 2 del plan de pivote a WinPE en
docs/superpowers/plans/2026-08-12-pivot-winpe-hirens-pe.md). En su lugar
se usa LibreHardwareMonitorLib (biblioteca open source, sucesora activa
de OpenHardwareMonitor), cargada vía pythonnet (paquete `clr`) — las DLLs
viven en backend/native/lhm/. Verificado en hardware real: en un AMD
Ryzen expone el voltaje VID de cada núcleo y el riel SVI2 (Core/SoC).

Importante, verificado en la misma prueba: la placa base de esa laptop
NO expuso ningún sensor de voltaje propio (0 subhardware bajo
Motherboard — común en laptops, a diferencia de muchas placas de
escritorio con chip Super I/O accesible). Los únicos voltajes reales
disponibles fueron los del procesador. Por eso el módulo reporta
CUALQUIER sensor de voltaje que LibreHardwareMonitorLib encuentre (placa
+ CPU), sin asumir de antemano cuáles van a estar presentes.

Sin clasificación por "nominal ± tolerancia" como la versión Linux
(+12V/+5V/+3.3V): los voltajes de CPU que sí se pudieron leer son
telemetría dinámica del regulador interno (VID/SVI2), no rieles fijos de
fuente de poder — varían con la carga, no hay un "nominal" razonable
para compararlos. El estado refleja si se pudo leer telemetría de
voltaje o no, con una validación de rango físico básica (nada de 0V o
valores absurdos), no un veredicto de "está bien" contra un ideal fijo
que no existe para estos sensores.
"""

import os
import sys

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "native", "lhm")
if _LIB_DIR not in sys.path:
    sys.path.append(_LIB_DIR)

_VOLTAJE_MINIMO_FISICO = 0
_VOLTAJE_MAXIMO_FISICO = 20

_RECOMENDACIONES = {
    "normal": "",
    "sospecha": "Voltaje fuera de rango físico esperado — revisar la fuente de poder o el regulador interno.",
    "critico": "",
    "no_determinado": "Diagnóstico de voltajes no disponible en este modo (ver Fase 2 del pivote a WinPE).",
}


def diagnosticar() -> dict:
    try:
        import clr

        clr.AddReference("LibreHardwareMonitorLib")
        from LibreHardwareMonitor.Hardware import Computer, SensorType
    except Exception as error:
        return _resultado_error(f"No se pudo cargar LibreHardwareMonitorLib: {error}")

    try:
        rieles = _leer_voltajes(Computer, SensorType)
    except Exception as error:
        return _resultado_error(f"Fallo al leer sensores de hardware: {error}")

    if not rieles:
        return _resultado_error("No se encontró ningún sensor de voltaje en esta placa/procesador.")

    estado, mensaje = _clasificar(rieles)
    return {
        "componente": "fuente_poder", "estado": estado, "mensaje": mensaje, "datos": {"rieles": rieles},
        "recomendacion": _RECOMENDACIONES[estado],
    }


def _leer_voltajes(Computer, SensorType) -> list:
    """No habilita IsMemoryEnabled: esa vía requiere RAMSPDToolkit-NDD, una
    dependencia extra de LibreHardwareMonitorLib no relacionada con
    voltajes que no está empaquetada acá (fuente_poder no necesita datos
    de RAM, eso ya lo cubre ram.py)."""
    computer = Computer()
    computer.IsMotherboardEnabled = True
    computer.IsCpuEnabled = True
    computer.Open()
    try:
        rieles = []
        for hardware in computer.Hardware:
            hardware.Update()
            rieles.extend(_sensores_voltaje(hardware, SensorType))
            for sub in hardware.SubHardware:
                sub.Update()
                rieles.extend(_sensores_voltaje(sub, SensorType))
        return rieles
    finally:
        computer.Close()


def _sensores_voltaje(hardware, SensorType) -> list:
    return [
        {"origen": str(hardware.Name), "sensor": str(sensor.Name), "voltios": round(float(sensor.Value), 3)}
        for sensor in hardware.Sensors
        if sensor.SensorType == SensorType.Voltage and sensor.Value is not None
    ]


def _clasificar(rieles: list) -> tuple:
    fuera_de_rango = [
        r for r in rieles if r["voltios"] <= _VOLTAJE_MINIMO_FISICO or r["voltios"] > _VOLTAJE_MAXIMO_FISICO
    ]
    if fuera_de_rango:
        return "sospecha", f"Lectura fuera de rango físico posible en: {', '.join(r['sensor'] for r in fuera_de_rango)}."
    return "normal", f"Telemetría de voltaje del procesador dentro de rango ({len(rieles)} sensor(es)) — no mide directamente el cargador, la batería ni los rieles de la placa."


def _resultado_error(mensaje: str) -> dict:
    return {
        "componente": "fuente_poder", "estado": "no_determinado", "mensaje": mensaje, "datos": None,
        "recomendacion": _RECOMENDACIONES["no_determinado"],
    }
