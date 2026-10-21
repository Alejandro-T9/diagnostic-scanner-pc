"""
backend/modules/_lhm.py — Lector único de sensores de LibreHardwareMonitorLib.

NO es un módulo de diagnóstico (el guion bajo inicial es a propósito): no
expone diagnosticar() ni está en scanner.COMPONENTES. Es infraestructura
compartida de cpu.py (ventiladores), gpu.py (temperatura/uso) y
fuente_poder.py (voltajes). Antes, cada uno abría su propio Computer() —
tres Open()/Close() por escaneo, y abrir la librería es lo más lento de
leer sensores. Ahora se abre UNA vez, se leen todos los sensores y el
resultado queda en caché hasta que scanner.ejecutar_escaneo_completo()
llama invalidar() al empezar el siguiente escaneo.

Acá no hay lógica de selección ni de umbrales: solo se leen y aplanan los
sensores; cada módulo decide en cuáles confiar con filtrar().

Forma de cada sensor:
    {"tipo_hardware": str, "hardware": str, "tipo": str, "nombre": str, "valor": float | None}
"tipo" es str(SensorType) ("Fan", "Temperature", "Voltage", "Load"...); los
sub-hardware se aplanan y heredan el tipo_hardware de su padre.
"""

import os
import sys
import threading

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "native", "lhm")
if _LIB_DIR not in sys.path:
    sys.path.append(_LIB_DIR)

# Flask corre con threaded=True: dos peticiones podrían pedir sensores a la
# vez. El candado cubre lectura + caché para que la librería se abra una
# sola vez y nadie lea una caché a medio llenar.
_candado = threading.Lock()
_cache = None   # None = aún no se ha leído; lista (posiblemente vacía) = ya se leyó
_error = None


def leer_sensores(lector=None) -> list:
    """Devuelve todos los sensores (de la caché si ya se leyeron). Nunca
    lanza: ante cualquier fallo devuelve [] y deja el mensaje en
    error_carga(). `lector` (callable sin argumentos) reemplaza la lectura
    real — solo para pruebas, sin hardware ni mockear objetos .NET."""
    global _cache, _error
    with _candado:
        if _cache is not None:
            return _cache
        try:
            _cache = (lector or _leer_hardware)()
            _error = None
        except Exception as error:
            _cache = []
            _error = str(error) or error.__class__.__name__
        return _cache


def error_carga():
    """Mensaje del último fallo de carga/lectura, o None si fue bien."""
    return _error


def invalidar() -> None:
    """Borra la caché y el error: la siguiente lectura vuelve al hardware."""
    global _cache, _error
    with _candado:
        _cache = None
        _error = None


def filtrar(sensores: list, tipo: str, hardware_contiene=None) -> list:
    """Sensores de un `tipo` exacto y, si se da, cuyo tipo_hardware contenga
    esa subcadena (p. ej. "Gpu" cubre GpuNvidia, GpuAmd y GpuIntel)."""
    return [
        s for s in sensores
        if s["tipo"] == tipo and (hardware_contiene is None or hardware_contiene in s["tipo_hardware"])
    ]


def _leer_hardware() -> list:
    """Única parte no testeable sin hardware real. Lanza si la librería no
    carga o falla al leer; leer_sensores() lo convierte en [] + error.

    No habilita IsMemoryEnabled: esa vía requiere RAMSPDToolkit-NDD, una
    dependencia extra de LibreHardwareMonitorLib no relacionada con
    sensores de CPU/GPU/placa que no está empaquetada acá (ram.py ya
    cubre la memoria)."""
    import clr

    clr.AddReference("LibreHardwareMonitorLib")
    from LibreHardwareMonitor.Hardware import Computer

    computer = Computer()
    computer.IsCpuEnabled = True
    computer.IsGpuEnabled = True
    computer.IsMotherboardEnabled = True
    computer.Open()
    try:
        return _recoger_sensores(computer.Hardware)
    finally:
        computer.Close()


def _recoger_sensores(lista_hardware) -> list:
    """Aplana los sensores de cada hardware y sub-hardware. Un componente
    que falla (p. ej. Update() de la GPU) se omite solo a él: no descarta
    los sensores de CPU/placa ya leídos ni los que faltan."""
    sensores = []
    for hardware in lista_hardware:
        tipo_hardware = str(hardware.HardwareType)
        sensores.extend(_leer_uno(hardware, tipo_hardware))
        try:
            subs = list(hardware.SubHardware)
        except Exception:
            continue
        for sub in subs:
            sensores.extend(_leer_uno(sub, tipo_hardware))
    return sensores


def _leer_uno(hardware, tipo_hardware: str) -> list:
    try:
        hardware.Update()
        return _aplanar(hardware, tipo_hardware)
    except Exception:
        return []


def _aplanar(hardware, tipo_hardware: str) -> list:
    return [
        {
            "tipo_hardware": tipo_hardware,
            "hardware": str(hardware.Name),
            "tipo": str(sensor.SensorType),
            "nombre": str(sensor.Name),
            "valor": float(sensor.Value) if sensor.Value is not None else None,
        }
        for sensor in hardware.Sensors
    ]
