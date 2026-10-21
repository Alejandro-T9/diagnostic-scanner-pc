"""
backend/modules/almacenamiento.py — Diagnóstico de almacenamiento (WMI, Windows/WinPE).

Win32_DiskDrive da identidad/tamaño de cada disco. MSFT_PhysicalDisk.HealthStatus
(namespace root/Microsoft/Windows/Storage, la API moderna de Windows Storage
Management) da el estado de salud real — reemplaza el intento anterior con
MSStorageDriver_FailurePredictStatus (root/wmi), que fallaba sin dar una
razón clara. MSFT_PhysicalDisk sí respondió sin problemas de permisos en
las pruebas (verificado en hardware real).

MSFT_StorageReliabilityCounter (mismo namespace) da contadores tipo SMART
(temperatura, desgaste, errores) — pero SÍ requiere privilegios elevados
(confirmado: x_access_denied corriendo como usuario normal en la PC de
desarrollo). WinPE corre como SYSTEM por defecto, así que debería
funcionar ahí sin configuración extra; no se pudo verificar en vivo por
la barrera de permisos en la PC de desarrollo, así que el catch acá es
más amplio de lo habitual (también AttributeError) — si algún nombre de
campo no coincide con lo documentado por Microsoft, se degrada sin esos
datos en vez de tumbar el diagnóstico completo de almacenamiento.

IMPORTANTE (encontrado en revisión externa del reporte): el veredicto solo
considera discos INTERNOS (interfaz != USB). Antes, cualquier memoria USB
conectada (incluido el propio USB de arranque del proyecto) se evaluaba
como si fuera almacenamiento de la laptop — un disco externo "sin salud
confirmada" podía tapar o mezclar el resultado del disco real. Los discos
externos se siguen reportando en "datos" para inventario, pero por
separado, y no afectan el estado del componente.
"""

import wmi

# 0/1/2 son los valores documentados de MSFT_PhysicalDisk.HealthStatus.
# "sospecha" (no "advertencia") para el nivel 1: es la propia Windows
# Storage Management diciendo "no del todo sano", evidencia real de un
# posible problema, no una simple observación a monitorear.
_ESTADOS_SALUD = {0: "normal", 1: "sospecha", 2: "critico"}

_RECOMENDACIONES = {
    "normal": "",
    "sospecha": "Programar respaldo de datos como precaución — Windows reporta salud reducida en el disco.",
    "critico": "Reemplazar la unidad antes de seguir en uso — riesgo real de pérdida de datos.",
    "no_determinado": "No se pudo determinar la salud del disco — revisar conexión física o de WMI.",
}


def diagnosticar() -> dict:
    try:
        conexion = wmi.WMI()
        discos = conexion.Win32_DiskDrive()
    except wmi.x_wmi as error:
        return _resultado_error(f"No se pudo consultar WMI: {error}")

    if not discos:
        return _resultado_error("WMI no devolvió ningún disco (Win32_DiskDrive vacío).")

    salud_por_indice = _obtener_salud()
    contadores_por_indice = _obtener_contadores()
    todos = [_leer_disco(d, salud_por_indice, contadores_por_indice) for d in discos]

    internos = [d for d in todos if not d["externo"]]
    externos = [d for d in todos if d["externo"]]

    estado, mensaje = _clasificar(internos)
    return {
        "componente": "almacenamiento", "estado": estado, "mensaje": mensaje,
        "datos": {"discos_internos": internos, "discos_externos": externos},
        "recomendacion": _RECOMENDACIONES[estado],
    }


def _obtener_salud() -> dict:
    """MSFT_PhysicalDisk.HealthStatus por índice de disco (Win32_DiskDrive.Index
    == MSFT_PhysicalDisk.DeviceId, verificado en hardware real). No requiere
    privilegios elevados."""
    try:
        storage = wmi.WMI(namespace="root/Microsoft/Windows/Storage")
        return {int(d.DeviceId): d.HealthStatus for d in storage.MSFT_PhysicalDisk()}
    except wmi.x_wmi:
        return {}


def _obtener_contadores() -> dict:
    """MSFT_StorageReliabilityCounter por índice de disco — requiere
    privilegios elevados. Se degrada a vacío si no hay acceso o si algún
    campo no responde como se esperaba, en vez de tumbar el módulo entero."""
    try:
        storage = wmi.WMI(namespace="root/Microsoft/Windows/Storage")
        return {int(c.DeviceId): c for c in storage.MSFT_StorageReliabilityCounter()}
    except (wmi.x_wmi, AttributeError):
        return {}


def _leer_disco(disco, salud_por_indice: dict, contadores_por_indice: dict) -> dict:
    gb = 1024 ** 3
    salud = salud_por_indice.get(disco.Index)
    contador = contadores_por_indice.get(disco.Index)
    interfaz = disco.InterfaceType or "Desconocida"
    return {
        "modelo": disco.Model or "Desconocido",
        "interfaz": interfaz,
        "externo": interfaz.upper() == "USB",
        "tamano_gb": round(int(disco.Size) / gb, 1) if disco.Size else None,
        "salud": _ESTADOS_SALUD.get(salud, "no_determinado"),
        "temperatura_c": contador.Temperature if contador else None,
        "desgaste_porcentaje": contador.Wear if contador else None,
        "horas_encendido": contador.PowerOnHours if contador else None,
        "errores_lectura": contador.ReadErrorsUncorrected if contador else None,
    }


def _clasificar(internos: list) -> tuple:
    if not internos:
        return "no_determinado", "No se detectó ningún disco interno (solo almacenamiento externo/USB, si lo hay)."

    criticos = [d for d in internos if d["salud"] == "critico"]
    if criticos:
        return "critico", f"Salud crítica en: {', '.join(d['modelo'] for d in criticos)}."

    sospechosos = [d for d in internos if d["salud"] == "sospecha"]
    if sospechosos:
        return "sospecha", f"Salud reducida (Windows Storage Health) en: {', '.join(d['modelo'] for d in sospechosos)}."

    no_determinados = [d for d in internos if d["salud"] == "no_determinado"]
    if no_determinados:
        return "no_determinado", f"No se pudo leer la salud de: {', '.join(d['modelo'] for d in no_determinados)}."

    return "normal", f"Salud normal en {len(internos)} disco(s) interno(s): {', '.join(d['modelo'] for d in internos)}."


def _resultado_error(mensaje: str) -> dict:
    return {
        "componente": "almacenamiento", "estado": "no_determinado", "mensaje": mensaje, "datos": None,
        "recomendacion": _RECOMENDACIONES["no_determinado"],
    }
