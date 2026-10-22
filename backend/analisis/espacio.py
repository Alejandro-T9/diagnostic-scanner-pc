"""
backend/analisis/espacio.py — Espacio libre del disco del sistema y carpetas grandes.

SOLO LECTURA, sin administrador. Mide:
- el espacio libre de la unidad del sistema (psutil; normalmente C:);
- el tamaño de %TEMP%, Windows\\Temp, Descargas y la Papelera, para que la
  persona sepa dónde mirar primero.
NO mide: la salud del disco (eso es modules/almacenamiento.py), archivos
duplicados ni cuánto ocupa cada programa.

Cada carpeta se recorre con topes de tiempo y de archivos (y un tope total del
módulo); si se corta, el elemento lleva "parcial": True y el tamaño es un
mínimo. No se siguen enlaces ni uniones (junctions) y los errores de permiso
se ignoran por entrada.
"""

import ctypes
import os
import time

import psutil

UMBRAL_SOSPECHA_PCT = 5
UMBRAL_ADVERTENCIA_PCT = 10
_SEG_POR_CARPETA = 1.0
_SEG_TOTAL_CARPETAS = 3.0
_MAX_ARCHIVOS = 200_000
_REPARSE_POINT = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT: enlaces simbólicos y junctions

_RECOMENDACIONES = {
    "normal": "Tu disco principal tiene espacio de sobra; no hace falta hacer nada.",
    "advertencia": "Conviene liberar espacio pronto: empieza por la papelera y las descargas que ya no uses.",
    "sospecha": "Libera espacio cuanto antes: vacía la papelera, borra descargas viejas y pasa tus archivos a otro disco.",
    "no_determinado": "Mira en Este equipo cuánto espacio queda libre en el disco C: y repite el análisis.",
}


def diagnosticar() -> dict:
    try:
        disco = _leer_disco_c()
    except Exception:
        disco = None
    try:
        carpetas = _leer_carpetas()
    except Exception:
        carpetas = []

    if not disco:
        estado, mensaje = _clasificar(None)
    else:
        estado, mensaje = _clasificar(disco["libre_pct"], disco)
    return {
        "componente": "espacio", "estado": estado, "mensaje": mensaje,
        "datos": {"disco_c": disco, "carpetas": carpetas},
        "recomendacion": _RECOMENDACIONES[estado],
    }


def _clasificar(libre_pct, disco=None) -> tuple:
    if libre_pct is None:
        return "no_determinado", "No se pudo leer cuánto espacio libre queda en el disco principal."
    unidad = (disco or {}).get("unidad", "C:")
    detalle = ""
    if disco:
        detalle = f" ({disco['libre_gb']:.0f} GB de {disco['total_gb']:.0f} GB)"
    mensaje = f"Te queda el {libre_pct:.0f} % libre del disco {unidad}{detalle}."
    if libre_pct < UMBRAL_SOSPECHA_PCT:
        return "sospecha", mensaje
    if libre_pct < UMBRAL_ADVERTENCIA_PCT:
        return "advertencia", mensaje
    return "normal", mensaje


def _leer_disco_c():
    unidad = os.environ.get("SystemDrive", "C:")
    uso = psutil.disk_usage(unidad + "\\")
    gb = 1024 ** 3
    return {
        "unidad": unidad,
        "total_gb": round(uso.total / gb, 1),
        "libre_gb": round(uso.free / gb, 1),
        "usado_gb": round(uso.used / gb, 1),
        "libre_pct": round(uso.free * 100 / uso.total, 1),
    }


def _leer_carpetas() -> list:
    perfil = os.environ.get("USERPROFILE", "")
    # shortcut: Descargas = %USERPROFILE%\Downloads; si el usuario la movió
    # a otra ruta no se ve (queda sin medir), cambiar a SHGetKnownFolderPath.
    candidatas = [
        ("Archivos temporales del usuario", os.environ.get("TEMP")),
        ("Archivos temporales de Windows", os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")),
        ("Descargas", os.path.join(perfil, "Downloads") if perfil else None),
    ]
    limite_total = time.monotonic() + _SEG_TOTAL_CARPETAS
    resultado = []
    for nombre, ruta in candidatas:
        medido = None
        if ruta:
            try:
                seg = max(0.0, min(_SEG_POR_CARPETA, limite_total - time.monotonic()))
                medido = _medir_carpeta(ruta, seg, _MAX_ARCHIVOS)
            except Exception:
                medido = None
        item = {"nombre": nombre, "ruta": ruta or None, "tamano_gb": None, "archivos": None}
        if medido:
            item["tamano_gb"] = round(medido[0] / 1024 ** 3, 2)
            item["archivos"] = medido[1]
            if medido[2]:
                item["parcial"] = True
        resultado.append(item)
    resultado.append(_leer_papelera())
    return resultado


def _medir_carpeta(ruta: str, max_seg: float, max_archivos: int):
    """(bytes, archivos, parcial) o None si la carpeta no existe o no se puede abrir."""
    limite = time.monotonic() + max_seg
    pendientes = [ruta]
    total = archivos = 0
    parcial = False
    abierta = False
    while pendientes and not parcial:
        try:
            with os.scandir(pendientes.pop()) as it:
                abierta = True
                for entrada in it:
                    if archivos >= max_archivos or time.monotonic() > limite:
                        parcial = True
                        break
                    try:
                        info = entrada.stat(follow_symlinks=False)
                        if entrada.is_symlink() or getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
                            continue
                        if entrada.is_dir(follow_symlinks=False):
                            pendientes.append(entrada.path)
                        else:
                            total += info.st_size
                            archivos += 1
                    except OSError:
                        continue
        except OSError:
            continue
    if not abierta:
        return None
    return total, archivos, parcial


class _InfoPapelera(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("i64Size", ctypes.c_int64), ("i64NumItems", ctypes.c_int64)]


def _leer_papelera() -> dict:
    item = {"nombre": "Papelera de reciclaje", "ruta": None, "tamano_gb": None, "archivos": None}
    try:
        info = _InfoPapelera(ctypes.sizeof(_InfoPapelera))
        if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) == 0:
            item["tamano_gb"] = round(info.i64Size / 1024 ** 3, 2)
            item["archivos"] = info.i64NumItems
    except Exception:
        pass
    return item
