"""
backend/respaldo.py — Respaldo guiado de los archivos del dueño antes de formatear (F7c, decisión 46).

COPIA, nunca mueve ni borra: usa robocopy hacia una carpeta nueva «Respaldo_<fecha>_<equipo>» de un disco que NO sea
el del sistema. Elige el usuario qué carpetas y a qué disco; se calcula el tamaño y se comprueba que quepa antes de copiar.
Las carpetas salen de una lista cerrada (Documentos, Escritorio, Imágenes, Descargas, Videos, Música) y el destino debe
ser una de las unidades que la propia app lista: nada de rutas escritas en la web. Corre como tarea larga (mantenimiento).
No copia correos, programas ni perfiles de navegador: avisa de ello.
"""

import ctypes
import datetime
import os
import re
import socket
import time
import uuid

import psutil

import mantenimiento

_MAX_SEG = 8.0
_REPARSE = 0x400
# carpetas conocidas de Windows (GUID): respetan que estén redirigidas a OneDrive
_CARPETAS = {
    "documentos": ("Documentos", "FDD39AD0-238F-46AF-ADB4-6C85480369C7"),
    "escritorio": ("Escritorio", "B4BFCC3A-DB2C-424C-B029-7FE99A87C641"),
    "imagenes": ("Imágenes", "33E28130-4E1E-4676-835A-98395C3BC3BB"),
    "descargas": ("Descargas", "374DE290-123F-4565-9164-39C4925E467B"),
    "videos": ("Videos", "18989B1D-99B5-455B-841C-AB7C74E4DDFC"),
    "musica": ("Música", "4BD8D571-6D19-48D3-BE97-422220080E43"),
}


class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]


def _ruta_conocida(guid: str):
    """Ruta real de una carpeta conocida del usuario, o None."""
    try:
        g = _GUID()
        ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p("{" + guid + "}"), ctypes.byref(g))
        ruta = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(ruta)) != 0:
            return None
        valor = ruta.value
        ctypes.windll.ole32.CoTaskMemFree(ruta)
        return valor if valor and os.path.isdir(valor) else None
    except Exception:
        return None


def _tamano(ruta: str, limite: float) -> dict:
    """Bytes y archivos bajo `ruta`, sin seguir enlaces y sin pasar de `limite` (monotonic); completo=False si se cortó."""
    total, archivos, completo, pila = 0, 0, True, [ruta]
    while pila:
        if time.monotonic() > limite:
            completo = False
            break
        try:
            with os.scandir(pila.pop()) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                        if e.is_dir(follow_symlinks=False):
                            if not st.st_file_attributes & _REPARSE:
                                pila.append(e.path)
                        else:
                            total += st.st_size
                            archivos += 1
                    except OSError:
                        continue
        except OSError:
            continue
    return {"bytes": total, "archivos": archivos, "completo": completo}


def destinos() -> list:
    """Unidades donde se puede guardar el respaldo: todas las que no son la del sistema y se pueden escribir."""
    sistema = os.path.splitdrive(os.environ.get("SystemRoot", "C:\\Windows"))[0].upper()
    salida = []
    for p in psutil.disk_partitions(all=False):
        letra = os.path.splitdrive(p.mountpoint)[0].upper()
        if not letra or letra == sistema or "cdrom" in p.opts.lower():
            continue
        try:
            uso = psutil.disk_usage(p.mountpoint)
        except OSError:
            continue
        salida.append({"unidad": letra + "\\", "libre_gb": round(uso.free / 1024 ** 3, 1), "libre_bytes": uso.free,
                       "externo": "removable" in p.opts.lower()})
    return salida


def previsualizar() -> dict:
    """Carpetas del usuario con su tamaño y los destinos posibles. Solo lectura."""
    limite = time.monotonic() + _MAX_SEG
    carpetas = []
    for id_, (nombre, guid) in _CARPETAS.items():
        ruta = _ruta_conocida(guid)
        if ruta:
            carpetas.append({"id": id_, "nombre": nombre, "ruta": ruta, **_tamano(ruta, limite)})
    return {"carpetas": carpetas, "destinos": destinos(),
            "aviso": "Se copian solo estas carpetas. No se copian correos, programas, juegos ni favoritos del navegador: respáldalos aparte si hacen falta."}


def copiar(ids: list, unidad: str) -> dict:
    """Valida lo pedido y lanza la copia con robocopy. Nunca lanza: {estado: trabajo|error, mensaje, ...}."""
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i in _CARPETAS for i in ids):
        return {"estado": "error", "mensaje": "Elige al menos una carpeta de la lista.", "detalle": []}
    destino = next((d for d in destinos() if isinstance(unidad, str) and d["unidad"].upper() == unidad.upper()), None)
    if destino is None:
        return {"estado": "error", "mensaje": "Elige una unidad de destino de la lista (no puede ser el disco del sistema).", "detalle": []}
    limite = time.monotonic() + 60
    origenes, total = [], 0
    for i in ids:
        ruta = _ruta_conocida(_CARPETAS[i][1])
        if not ruta:
            continue
        t = _tamano(ruta, limite)
        total += t["bytes"]
        origenes.append((_CARPETAS[i][0], ruta))
    if not origenes:
        return {"estado": "error", "mensaje": "No se encontraron esas carpetas en este equipo.", "detalle": []}
    if total * 1.05 > destino["libre_bytes"]:
        return {"estado": "error", "mensaje": f"No cabe: se necesitan unos {total / 1024 ** 3:.1f} GB y la unidad tiene {destino['libre_gb']} GB libres.", "detalle": []}
    equipo = re.sub(r"[^A-Za-z0-9_-]", "_", socket.gethostname())[:30]
    raiz = os.path.join(destino["unidad"], f"Respaldo_{datetime.date.today().isoformat()}_{equipo}_{uuid.uuid4().hex[:4]}")
    # /E subcarpetas, /XJ sin enlaces, /R:1 /W:1 sin reintentos largos; los archivos en uso se saltan y quedan como aviso
    comandos = [["robocopy", ruta, os.path.join(raiz, nombre), "/E", "/XJ", "/R:1", "/W:1", "/NFL", "/NDL", "/NP"] for nombre, ruta in origenes]
    r = mantenimiento._iniciar_trabajo("respaldo", comandos, ok=tuple(range(8)))  # robocopy 0-7 = copió (con o sin cambios), 8+ = falló
    if r["estado"] == "trabajo":
        r["mensaje"] = f"Copiando a {raiz}. No cierres la aplicación ni saques la unidad."
        r["destino"] = raiz
    return r
