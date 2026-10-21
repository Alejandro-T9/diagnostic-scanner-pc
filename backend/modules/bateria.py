"""
backend/modules/bateria.py — Diagnóstico de batería (WMI, Windows/WinPE).

Win32_Battery (namespace root/cimv2) para estado y carga actual.
BatteryStaticData + BatteryFullChargedCapacity (namespace root/wmi) para
capacidad de diseño vs. capacidad actual — el mismo par de valores que la
versión Linux leía de /sys/class/power_supply/BAT0/{energy_full,energy_full_design}.
BatteryCycleCount (mismo namespace) para ciclos de carga.

Nota: Win32_Battery.BatteryStatus es una clase conocida por ser imprecisa
(no distingue bien "en uso normal con batería" de "desconocido") — es una
limitación documentada de la clase, no un bug de este módulo.

Decisión de diseño: sin batería detectada => estado "normal", no
"no_determinado". Un equipo de escritorio sin batería no debe salir mal
parado en el veredicto global por un componente que ni le aplica — no
tener batería no es lo mismo que no poder leer una batería que sí existe.
"""

import wmi

UMBRAL_ADVERTENCIA_SALUD = 70
UMBRAL_CRITICO_SALUD = 40

_NO_INTERPRETABLE = "No determinado por el sistema"

# 1 ("Other") y 10 ("Undefined") son, según la propia documentación de
# Win32_Battery, catch-alls sin significado accionable — mostrar el valor
# crudo ("Otro"/"Indefinido") le da al usuario una falsa sensación de dato
# concreto. Se muestran con el mismo texto que un dato no interpretable,
# igual que 2 ("Unknown") ya se traducía honestamente como "Desconocido".
_ESTADOS_WMI = {
    1: _NO_INTERPRETABLE, 2: "Desconocido", 3: "Completamente cargada", 4: "Baja",
    5: "Crítica", 6: "Cargando", 7: "Cargando y alta", 8: "Cargando y baja",
    9: "Cargando y crítica", 10: _NO_INTERPRETABLE, 11: "Parcialmente cargada",
}

_RECOMENDACIONES = {
    "normal": "",
    "advertencia": "Monitorear la batería — podría necesitar reemplazo en los próximos meses.",
    "critico": "Reemplazar la batería antes de reasignar el equipo.",
    "no_determinado": "No se pudo leer la batería — revisar conexión de WMI.",
}


def diagnosticar() -> dict:
    try:
        conexion = wmi.WMI()
        baterias = conexion.Win32_Battery()
    except wmi.x_wmi as error:
        return _resultado_error(f"No se pudo consultar WMI: {error}")

    if not baterias:
        return {
            "componente": "bateria",
            "estado": "normal",
            "mensaje": "Sin batería detectada (equipo de escritorio o no aplica).",
            "datos": {"aplica": False},
            "recomendacion": _RECOMENDACIONES["normal"],
        }

    datos = _leer_bateria(baterias[0])
    estado, mensaje = _clasificar(datos["salud_porcentaje"])
    return {
        "componente": "bateria", "estado": estado, "mensaje": mensaje, "datos": datos,
        "recomendacion": _RECOMENDACIONES[estado],
    }


def _leer_bateria(bateria) -> dict:
    capacidad_diseno, capacidad_actual = _leer_capacidades()
    salud = _calcular_salud(capacidad_actual, capacidad_diseno)
    return {
        "aplica": True,
        "estado_carga": _ESTADOS_WMI.get(bateria.BatteryStatus, "Desconocido"),
        "porcentaje_carga_actual": bateria.EstimatedChargeRemaining,
        "ciclos_carga": _leer_ciclos(),
        "salud_porcentaje": salud,
    }


def _calcular_salud(capacidad_actual, capacidad_diseno):
    """Separado de _leer_bateria para poder probarse sin WMI. capacidad_actual
    en 0 es un dato real (batería completamente muerta, el peor caso
    posible) y no debe tratarse igual que "no se pudo leer" solo por ser
    falsy en Python — a diferencia de capacidad_diseno, que en 0 no tendría
    sentido físico (y evita además la división por cero)."""
    if capacidad_actual is None or not capacidad_diseno:
        return None
    return round(capacidad_actual / capacidad_diseno * 100, 1)


def _leer_capacidades():
    """BatteryStaticData/BatteryFullChargedCapacity viven en root/wmi, no
    en root/cimv2 — requieren su propia conexión WMI."""
    try:
        raiz_wmi = wmi.WMI(namespace="root/wmi")
        diseno = raiz_wmi.BatteryStaticData()
        actual = raiz_wmi.BatteryFullChargedCapacity()
        capacidad_diseno = diseno[0].DesignedCapacity if diseno else None
        capacidad_actual = actual[0].FullChargedCapacity if actual else None
        return capacidad_diseno, capacidad_actual
    except wmi.x_wmi:
        return None, None


def _leer_ciclos():
    try:
        raiz_wmi = wmi.WMI(namespace="root/wmi")
        ciclos = raiz_wmi.BatteryCycleCount()
        return ciclos[0].CycleCount if ciclos else None
    except wmi.x_wmi:
        return None


def _clasificar(salud) -> tuple:
    if salud is None:
        return "no_determinado", "Batería detectada, pero faltan datos de capacidad de diseño para calcular su salud."
    if salud < UMBRAL_CRITICO_SALUD:
        return "critico", f"Salud de la batería crítica: {salud:.1f}% de la capacidad de diseño."
    if salud <= UMBRAL_ADVERTENCIA_SALUD:
        return "advertencia", f"Salud de la batería reducida: {salud:.1f}% de la capacidad de diseño."
    return "normal", f"Batería en buen estado: {salud:.1f}% de la capacidad de diseño."


def _resultado_error(mensaje: str) -> dict:
    return {
        "componente": "bateria", "estado": "no_determinado", "mensaje": mensaje, "datos": None,
        "recomendacion": _RECOMENDACIONES["no_determinado"],
    }
