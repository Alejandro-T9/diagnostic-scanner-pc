"""
backend/analisis/inicio.py — Programas que se abren solos al encender el equipo.

SOLO LECTURA, sin administrador, sin PowerShell. Cuenta:
- las entradas de las claves Run (usuario, equipo y equipo de 32 bits) del registro;
- los accesos directos de las carpetas Inicio (del usuario y de todos).
Cada entrada trae su estado en el Administrador de tareas (StartupApproved):
las que el usuario ya deshabilitó salen en la lista con "habilitado": False
pero NO cuentan en el total, para que "Deshabilitar" baje de verdad el número.
Además informa aparte cuántos servicios de Windows arrancan solos (no suman).
NO mide cuánto tarda el arranque ni si cada programa hace falta. Tareas
programadas y otras formas de arranque no se leen.
"""

import os
import winreg

import psutil

UMBRAL_ADVERTENCIA = 10
_MAX_ENTRADAS = 200
_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APROBADO = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"

_RECOMENDACIONES = {
    "normal": "No hace falta hacer nada; son pocos programas.",
    "advertencia": "Si el equipo tarda en arrancar, desactiva en el Administrador de tareas los que no necesites al encender.",
    "no_determinado": "Mira la lista en el Administrador de tareas, pestaña Inicio, y repite el análisis.",
}


def diagnosticar() -> dict:
    entradas, fuentes_ok = [], 0
    for lector in (_leer_run, _leer_carpetas_inicio):  # se busca por nombre al llamar: reemplazable en pruebas
        try:
            entradas += [{**e, "habilitado": e.get("habilitado", True)} for e in lector()]
            fuentes_ok += 1
        except Exception:
            continue
    try:
        servicios = _contar_servicios_automaticos()
    except Exception:
        servicios = None

    total = None if fuentes_ok == 0 else sum(1 for e in entradas if e["habilitado"])
    estado, mensaje = _clasificar(total)
    entradas.sort(key=lambda e: not e["habilitado"])  # estable: las deshabilitadas al final
    return {
        "componente": "inicio", "estado": estado, "mensaje": mensaje,
        "datos": {"total": total, "entradas": entradas[:_MAX_ENTRADAS], "servicios_automaticos": servicios},
        "recomendacion": _RECOMENDACIONES[estado],
    }


def _clasificar(total) -> tuple:
    """total = programas de inicio habilitados (o None si no se pudo leer ninguna fuente)."""
    if total is None:
        return "no_determinado", "No se pudo leer la lista de programas de inicio."
    if total == 0:
        mensaje = "Al encender el equipo no se abre ningún programa por sí solo."
    elif total == 1:
        mensaje = "Al encender el equipo se abre 1 programa por sí solo."
    else:
        mensaje = f"Al encender el equipo se abren {total} programas por sí solos."
    return ("advertencia" if total >= UMBRAL_ADVERTENCIA else "normal"), mensaje


def _habilitado(valor) -> bool:
    """Decodifica el valor binario de StartupApproved: primer byte 0x03/0x07 = deshabilitado
    por el usuario; 0x02/0x06, ausente o ilegible = habilitado."""
    return not (isinstance(valor, (bytes, bytearray)) and len(valor) > 0 and valor[0] in (0x03, 0x07))


def _valores(raiz, ruta: str) -> dict:
    """{nombre: valor} de una clave; {} si no existe; OSError si no se puede abrir."""
    try:
        with winreg.OpenKey(raiz, ruta) as clave:
            resultado, i = {}, 0
            while True:
                try:
                    nombre, valor, _ = winreg.EnumValue(clave, i)
                except OSError:
                    return resultado
                resultado[nombre] = valor
                i += 1
    except FileNotFoundError:
        return {}


def _leer_run() -> list:
    # (hive, clave Run, clave StartupApproved, origen)
    fuentes = [
        (winreg.HKEY_CURRENT_USER, _RUN, _APROBADO + r"\Run", "usuario"),
        (winreg.HKEY_LOCAL_MACHINE, _RUN, _APROBADO + r"\Run", "equipo"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Run",
         _APROBADO + r"\Run32", "equipo"),
    ]
    entradas, fallos = [], 0
    for raiz, ruta, aprobado, origen in fuentes:
        try:
            valores = _valores(raiz, ruta)
        except OSError:
            fallos += 1
            continue
        try:
            estados = _valores(raiz, aprobado)
        except OSError:
            estados = {}  # sin estado legible = habilitado
        entradas += [{"nombre": n, "comando": str(c), "origen": origen, "habilitado": _habilitado(estados.get(n))}
                     for n, c in valores.items()]
    if fallos == len(fuentes):
        raise OSError("no se pudo leer ninguna clave Run")
    return entradas


def _leer_carpetas_inicio() -> list:
    sub = r"Microsoft\Windows\Start Menu\Programs\Startup"
    fuentes = [
        (os.path.join(os.environ.get("APPDATA", ""), sub), winreg.HKEY_CURRENT_USER, "usuario"),
        (os.path.join(os.environ.get("ProgramData", ""), sub), winreg.HKEY_LOCAL_MACHINE, "equipo"),
    ]
    entradas, fallos = [], 0
    for carpeta, raiz, origen in fuentes:
        try:
            nombres = [n for n in os.listdir(carpeta) if n.lower() != "desktop.ini"]
        except FileNotFoundError:
            continue
        except OSError:
            fallos += 1
            continue
        try:
            estados = _valores(raiz, _APROBADO + r"\StartupFolder")
        except OSError:
            estados = {}
        entradas += [{"nombre": n, "comando": os.path.join(carpeta, n), "origen": origen,
                      "habilitado": _habilitado(estados.get(n))} for n in nombres]
    if fallos == len(fuentes):
        raise OSError("no se pudo leer ninguna carpeta Inicio")
    return entradas


def _contar_servicios_automaticos():
    try:
        return sum(1 for s in psutil.win_service_iter() if s.start_type() == "automatic")
    except Exception:
        return None
