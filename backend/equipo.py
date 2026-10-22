"""
backend/equipo.py — Datos del sistema de apoyo para el recomendador (Windows).

No es un componente de diagnóstico (no entra en scanner.COMPONENTES): reúne
hechos del equipo que los módulos no leen — SO, firmware UEFI/BIOS, Secure
Boot, versión de TPM y tipo de cada disco — para decidir qué recomendar.

Ningún lector es obligatorio como administrador. El TPM (Win32_Tpm) solo se
puede leer con esos permisos: sin ellos ni se intenta y queda en None.
`leer_hechos` nunca lanza: cada lector falla por separado con su valor de
respaldo. Rendimiento: una sola conexión WMI por espacio de nombres y por
llamada a `leer_hechos`, y consultas filtradas (ver `_conexion`).

LÍMITES de `cpu_apto_windows11`: es una heurística por nombre, NO la lista
oficial de Microsoft. Solo reconoce Intel Core iN-XXXX y AMD Ryzen N XXXX;
cualquier otra familia (Celeron, Pentium, Atom, Xeon, Ryzen AI...) da None.
Una CPU apta por nombre aún puede fallar por TPM/Secure Boot (ver `leer_hechos`).
"""

import ctypes
import re
import threading

import wmi

import utils

_NS_ALMACENAMIENTO = "root/Microsoft/Windows/Storage"
_BUS_USB = 7
_BUS_NVME = 17


def tipo_disco(media_type, bus_type) -> str:
    """MSFT_PhysicalDisk.MediaType (4 SSD, 3 HDD) / BusType (17 NVMe) -> ssd|hdd|desconocido."""
    if media_type == 4 or bus_type == _BUS_NVME:
        return "ssd"
    if media_type == 3:
        return "hdd"
    return "desconocido"


def cpu_apto_windows11(nombre) -> "bool | None":
    """Heurística por nombre: Intel Core >= 8.ª gen, Ryzen serie >= 2000. Otra cosa -> None."""
    if not nombre:
        return None
    intel = re.search(r"\bi[3579]-(\d{4,5})", nombre)
    if intel:
        modelo = intel.group(1)
        explicita = re.search(r"(\d{1,2})(?:st|nd|rd|th) Gen", nombre)
        if explicita:
            gen = int(explicita.group(1))
        elif len(modelo) == 5 or modelo[0] == "1":  # 10110U, 1165G7, 1255U: dos primeros dígitos
            gen = int(modelo[:2])
        else:  # 8250U, 7500U
            gen = int(modelo[0])
        return gen >= 8
    ryzen = re.search(r"Ryzen\s+\d\s+(?:PRO\s+)?(\d{4})", nombre)
    if ryzen:
        return int(ryzen.group(1)[0]) >= 2
    return None


_local = threading.local()


def _cache() -> dict:
    """espacio de nombres -> conexión WMI, propia de cada hilo: las conexiones COM pertenecen al hilo que las creó
    (la app puede atender dos /api/scan a la vez). La vacía leer_hechos al empezar y al terminar."""
    if not hasattr(_local, "conexiones"):
        _local.conexiones = {}
    return _local.conexiones


def _conexion(namespace=None):
    """Conectar a WMI cuesta decenas de ms: se hace una vez por espacio de nombres en cada `leer_hechos`."""
    c = _cache()
    if namespace not in c:
        c[namespace] = wmi.WMI(namespace=namespace) if namespace else wmi.WMI()
    return c[namespace]


def _leer_so() -> dict:
    so = _conexion().Win32_OperatingSystem()[0]
    return {"nombre": so.Caption, "build": so.BuildNumber, "arquitectura": so.OSArchitecture}


def _leer_firmware():
    """kernel32.GetFirmwareType: 1 = BIOS, 2 = UEFI (PEFirmwareType del registro no es fiable)."""
    tipo = ctypes.c_int(0)
    if not ctypes.windll.kernel32.GetFirmwareType(ctypes.byref(tipo)):
        return None
    return {1: "bios", 2: "uefi"}.get(tipo.value)


def _leer_secure_boot():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\SecureBoot\State") as clave:
            return bool(winreg.QueryValueEx(clave, "UEFISecureBootEnabled")[0])
    except FileNotFoundError:
        return None


def _leer_tpm():
    """Win32_Tpm.SpecVersion ("2.0, 0, 1.38"): primer número. Sin administrador -> None."""
    # Sin administrador la consulta siempre da acceso denegado, pero tarda ~5 s en fallar: ni se intenta.
    if not utils.es_administrador():
        return None
    tpm = _conexion("root/cimv2/Security/MicrosoftTpm").Win32_Tpm()
    if not tpm:
        return None
    version = re.match(r"\s*(\d+\.\d+)", tpm[0].SpecVersion or "")
    return version.group(1) if version and version.group(1) in ("1.2", "2.0") else None


def _discos_fisicos() -> list:
    return _conexion(_NS_ALMACENAMIENTO).MSFT_PhysicalDisk()


def _leer_discos() -> list:
    gb = 1024 ** 3
    return [
        {
            "modelo": d.FriendlyName or "Desconocido",
            "tipo": tipo_disco(d.MediaType, d.BusType),
            "externo": d.BusType == _BUS_USB,
            "tamano_gb": round(int(d.Size) / gb, 1) if d.Size else None,
        }
        for d in _discos_fisicos()
    ]


def _leer_disco_sistema() -> str:
    """Tipo del disco físico que aloja C: (MSFT_Partition.DiskNumber == MSFT_PhysicalDisk.DeviceId)."""
    storage = _conexion(_NS_ALMACENAMIENTO)
    for p in storage.MSFT_Partition(DriveLetter="C"):
        for d in storage.MSFT_PhysicalDisk(DeviceId=str(p.DiskNumber)):
            return tipo_disco(d.MediaType, d.BusType)
    return "desconocido"


def leer_hechos() -> dict:
    """Nunca lanza: un lector que falla deja su valor de respaldo y no afecta a los demás."""
    def seguro(lector, respaldo):
        try:
            return lector()
        except Exception:
            return respaldo

    _cache().clear()
    # Se buscan por nombre en cada llamada (no por referencia) para que los tests puedan reemplazarlos.
    try:
        return {
            "so": seguro(_leer_so, None),
            "firmware": seguro(_leer_firmware, None),
            "secure_boot": seguro(_leer_secure_boot, None),
            "tpm_version": seguro(_leer_tpm, None),
            "discos": seguro(_leer_discos, []),
            "disco_sistema_tipo": seguro(_leer_disco_sistema, "desconocido"),
        }
    finally:
        _cache().clear()  # no dejar objetos COM de este hilo vivos para el siguiente escaneo
