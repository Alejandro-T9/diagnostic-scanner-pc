"""
backend/modules/gpu.py — Telemetría de GPU, auxiliar de cpu.py (Windows/WinPE).

NO es un módulo de contrato: no expone diagnosticar(), no está listado en
scanner.py COMPONENTES, y no genera un veredicto propio. El documento
institucional del Semillero define 7 componentes; la GPU (integrada en
la mayoría de las laptops que va a revisar el proyecto, comparte
encapsulado y presupuesto térmico con el CPU) se reporta como sub-info
dentro del componente Procesador (datos.gpu), no como un 8vo componente
— decisión ya tomada en docs/DECISIONES.md (decisión 19) para GPU/
ventiladores, ahora extendida a un módulo propio en vez de funciones
inline en cpu.py.

Win32_VideoController para identidad (nombre, driver) — sin AdapterRAM:
es un campo con un bug documentado de Microsoft en drivers WDDM
modernos (subreporta o desborda en tarjetas con más de 4GB) — mostrar
ese número sería mostrar un dato que ya sabemos que puede estar mal.

Temperatura y uso vía LibreHardwareMonitorLib (misma librería que ya usa
cpu.py y fuente_poder.py, sin dependencia nueva) — sin umbrales propios
de crítico/advertencia: no hay base técnica para asumir que los límites
térmicos de un CPU aplican a su GPU integrada, y menos con presupuesto
térmico compartido entre ambos. Este módulo solo reporta el dato; quien
decide si el Procesador está bien o no es cpu.py, a partir de SU PROPIA
temperatura — nunca de la de la GPU. Sensor ausente = dato en None, no
"normal" ni ningún otro estado inventado.

_telemetria() solo habla con LibreHardwareMonitor y junta lecturas
crudas; _elegir_temperatura()/_elegir_uso() deciden en cuál confiar —
separado a propósito para poder probar la selección con datos simples,
sin necesitar hardware real ni mockear objetos .NET (ver _demo() al
final del archivo).
"""

import os
import sys

import wmi

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "native", "lhm")
if _LIB_DIR not in sys.path:
    sys.path.append(_LIB_DIR)

_TEMPERATURA_MIN_C = 0
_TEMPERATURA_MAX_C = 110


def obtener_datos() -> dict:
    """Nunca lanza: cualquier fallo se degrada a valores None. Esto es
    telemetría auxiliar de cpu.py, no debe poder tumbar el diagnóstico
    del Procesador."""
    nombre, driver = _identidad()
    temperatura_c, porcentaje_uso = _telemetria()
    return {
        "nombre": nombre,
        "driver": driver,
        "temperatura_c": temperatura_c,
        "porcentaje_uso": porcentaje_uso,
    }


def _identidad() -> tuple:
    try:
        conexion = wmi.WMI()
        controladores = conexion.Win32_VideoController()
        if not controladores:
            return None, None
        return controladores[0].Name, controladores[0].DriverVersion
    except wmi.x_wmi:
        return None, None


def _elegir_temperatura(sensores_temp: list):
    """sensores_temp: valores crudos de sensores SensorType.Temperature
    bajo hardware de GPU. Se descarta cualquier lectura fuera de un rango
    físico razonable (mismo criterio que fuente_poder.py con voltajes) —
    un GPU no debería reportar, por ejemplo, temperatura negativa."""
    for valor in sensores_temp:
        if valor is not None and _TEMPERATURA_MIN_C <= valor <= _TEMPERATURA_MAX_C:
            return round(float(valor), 1)
    return None


def _elegir_uso(sensores_load: list):
    """sensores_load: lista de (nombre, valor) de sensores SensorType.Load
    bajo hardware de GPU. Solo confía en el sensor agregado "GPU Core"
    (mismo nombre en los 3 backends de LibreHardwareMonitor — AMD/NVIDIA/
    Intel; no verificable más allá del hardware disponible para probar).
    El resto de sensores Load son motores D3D individuales (3D, Compute,
    Video, Copy...), no representativos del uso general de la GPU.

    A propósito SIN fallback a otro sensor si "GPU Core" falta o da un
    valor fuera de [0, 100]: reemplazarlo por un motor individual
    mostraría un número real, pero de otra cosa, bajo el mismo campo —
    tan engañoso como inventar el dato. Verificado en hardware real que
    un contador de Windows puede devolver un valor puntual imposible
    (217%) en el propio "GPU Core"; en ese caso el resultado también
    debe ser None, no un valor de respaldo (ver _demo() más abajo)."""
    for nombre, valor in sensores_load:
        if nombre == "GPU Core" and valor is not None and 0 <= valor <= 100:
            return round(float(valor), 1)
    return None


def _telemetria() -> tuple:
    try:
        import clr

        clr.AddReference("LibreHardwareMonitorLib")
        from LibreHardwareMonitor.Hardware import Computer, SensorType
    except Exception:
        return None, None

    try:
        computer = Computer()
        computer.IsGpuEnabled = True
        computer.Open()
        try:
            sensores_temp = []
            sensores_load = []
            for hardware in computer.Hardware:
                if "Gpu" not in str(hardware.HardwareType):
                    continue
                hardware.Update()
                for sensor in hardware.Sensors:
                    if sensor.Value is None:
                        continue
                    if sensor.SensorType == SensorType.Temperature:
                        sensores_temp.append(float(sensor.Value))
                    if sensor.SensorType == SensorType.Load:
                        sensores_load.append((str(sensor.Name), float(sensor.Value)))
            return _elegir_temperatura(sensores_temp), _elegir_uso(sensores_load)
        finally:
            computer.Close()
    except Exception:
        return None, None


def _demo():
    """Prueba la selección de sensores con datos simulados — no necesita
    hardware real. Los 3 escenarios son los que expuso la revisión
    externa que motivó este refactor (ver docs/DECISIONES.md, decisión
    22): agregado sano, agregado corrupto (no debe caer a un motor
    individual), y agregado ausente (misma conclusión)."""
    assert _elegir_uso([("GPU Core", 42), ("D3D 3D", 18), ("D3D Compute", 7), ("Video Decode", 2)]) == 42.0
    assert _elegir_uso([("GPU Core", 217), ("D3D 3D", 20)]) is None, "GPU Core corrupto no debe caer a D3D 3D"
    assert _elegir_uso([("D3D 3D", 20)]) is None, "sin GPU Core no debe caer a D3D 3D"
    assert _elegir_uso([]) is None
    assert _elegir_temperatura([45.0]) == 45.0
    assert _elegir_temperatura([150.0]) is None, "temperatura fuera de rango físico debe descartarse"
    assert _elegir_temperatura([]) is None
    print("gpu.py: self-check OK")


if __name__ == "__main__":
    _demo()
