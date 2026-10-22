"""
backend/analisis/programas.py — Programas instalados, incluidos los que Windows no muestra.

SOLO LECTURA, sin administrador. Junta dos fuentes:
- el registro de "Desinstalar" (HKLM, HKLM\\Wow6432Node para 32 bits y HKCU);
- los accesos del menú Inicio (lo que muestra shell:AppsFolder: aplicaciones de la
  tienda, herramientas de Windows, accesos a documentos o a "Desinstalar…"),
  con PowerShell Get-StartApps (tiempo límite 6 s, sin ventana). No son
  programas instalados: se cuentan aparte (origen "menu_inicio").
"oculto" significa "Windows no lo lista en Configuración": entradas marcadas
SystemComponent o que cuelgan de otro programa (parches, componentes). Esos NO
cuentan para el aviso, porque la persona no los ve en su lista.
Aviso: 3 o más programas visibles de editor vacío o desconocido instalados en
los últimos 30 días. Un editor desconocido no significa que el programa sea
malo; este análisis no busca virus.
LÍMITE: Get-StartApps solo lista lo que tiene acceso en el menú Inicio; los
programas portátiles (sin instalador) y los que no registran su desinstalación
no aparecen. Sin PowerShell se usa solo el registro.
"""

import datetime
import json
import re
import shutil
import subprocess
import winreg

UMBRAL_RECIENTES = 3
DIAS_RECIENTE = 30
_MAX_LISTA = 300
_MAX_RECIENTES = 20
_SEG_POWERSHELL = 6
_EDITORES_DESCONOCIDOS = {"", "unknown", "desconocido"}
_UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
_CLAVES = [
    (winreg.HKEY_LOCAL_MACHINE, _UNINSTALL),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, _UNINSTALL),
]

_RECOMENDACIONES = {
    "normal": "Recorre la lista de vez en cuando; lo que no uses puedes quitarlo desde Configuración → Aplicaciones. Esta revisión no busca virus.",
    "advertencia": ("Revisa en la lista los programas instalados hace poco y sin editor conocido; eso no significa que sean malos. "
                    "Si no reconoces alguno, búscalo o pregunta a un técnico antes de quitarlo."),
    "no_determinado": "Mira la lista en Configuración → Aplicaciones y repite el análisis.",
}


def diagnosticar() -> dict:
    lista = []
    for lector in (_leer_registro, _leer_aplicaciones_inicio):  # se busca por nombre al llamar: reemplazable en pruebas
        try:
            lista += [p for p in lector() if isinstance(p, dict) and isinstance(p.get("nombre"), str) and p["nombre"]]
        except Exception:
            continue
    # El menú Inicio solo aporta lo que el registro no trae (mismo nombre, sin distinguir mayúsculas).
    del_registro = {p["nombre"].casefold() for p in lista if p.get("origen") != "menu_inicio"}
    programas = []
    for p in lista:
        if p.get("origen") == "menu_inicio":
            if p["nombre"].casefold() in del_registro:
                continue
            del_registro.add(p["nombre"].casefold())  # y entre sí tampoco se repiten
        programas.append(p)

    hoy = datetime.date.today()
    if not programas:  # un equipo real siempre tiene alguno: sin nada, es que no se pudo leer
        estado, mensaje = "no_determinado", "No se pudo leer la lista de programas instalados."
        datos = {"total": None, "instalados": None, "en_menu_inicio": None, "ocultos": 0, "programas": [],
                 "recientes_sin_editor": []}
    else:
        estado, mensaje = _clasificar(programas, hoy)
        programas.sort(key=lambda p: (bool(p.get("oculto")), p["nombre"].casefold()))
        en_menu = sum(1 for p in programas if p.get("origen") == "menu_inicio")
        datos = {
            "total": len(programas),  # instalados + accesos del menú Inicio
            "instalados": len(programas) - en_menu,
            "en_menu_inicio": en_menu,
            "ocultos": sum(1 for p in programas if p.get("oculto")),
            "programas": programas[:_MAX_LISTA],
            "recientes_sin_editor": [p["nombre"] for p in _recientes_sin_editor(programas, hoy)][:_MAX_RECIENTES],
        }
        if not datos["instalados"]:  # solo menú Inicio: el total de instalados es desconocido, no 0
            datos["total"] = datos["instalados"] = None
    return {"componente": "programas", "estado": estado, "mensaje": mensaje, "datos": datos,
            "recomendacion": _RECOMENDACIONES[estado]}


def _es_reciente(fecha, hoy: datetime.date, dias: int = DIAS_RECIENTE) -> bool:
    """fecha = AAAAMMDD del registro. Ausente, mal formada o futura -> False."""
    if not isinstance(fecha, str) or not re.fullmatch(r"\d{8}", fecha):
        return False
    try:
        instalado = datetime.datetime.strptime(fecha, "%Y%m%d").date()
    except ValueError:
        return False
    return 0 <= (hoy - instalado).days <= dias


def _recientes_sin_editor(programas: list, hoy: datetime.date) -> list:
    return [p for p in programas
            if not p.get("oculto")
            and str(p.get("editor") or "").strip().casefold() in _EDITORES_DESCONOCIDOS
            and _es_reciente(p.get("fecha"), hoy)]


def _clasificar(programas: list, hoy: datetime.date) -> tuple:
    """programas = lista ya leída (puede estar vacía; el llamador decide si fue por una lectura fallida)."""
    en_menu = sum(1 for p in programas if p.get("origen") == "menu_inicio")
    instalados = len(programas) - en_menu
    ocultos = sum(1 for p in programas if p.get("oculto"))
    accesos = f"{en_menu} acceso{'s' if en_menu != 1 else ''} en el menú Inicio"
    if instalados:
        mensaje = f"Hay {instalados} programa{'s' if instalados != 1 else ''} instalado{'s' if instalados != 1 else ''}"
        if ocultos:
            mensaje += f" ({ocultos} oculto{'s' if ocultos != 1 else ''} por Windows)"
        mensaje += f" y {accesos}." if en_menu else "."
    else:  # solo se leyó el menú Inicio: sin el registro no hay fechas ni editores que evaluar
        return "no_determinado", f"No se pudo leer la lista de programas instalados; hay {accesos}."
    n = len(_recientes_sin_editor(programas, hoy))
    if n >= UMBRAL_RECIENTES:
        return "advertencia", f"{mensaje} Hay {n} programas recientes sin editor conocido: revisa si los reconoces."
    return "normal", mensaje


def _texto(valor):
    if isinstance(valor, int) and not isinstance(valor, bool):
        valor = str(valor)
    if not isinstance(valor, str):
        return None
    return valor.strip() or None


def _valor(clave, nombre):
    try:
        return winreg.QueryValueEx(clave, nombre)[0]
    except OSError:
        return None


def _leer_registro() -> list:
    encontrados, fallos = {}, 0
    for raiz, ruta in _CLAVES:
        try:
            clave = winreg.OpenKey(raiz, ruta)
        except FileNotFoundError:
            continue
        except OSError:
            fallos += 1
            continue
        with clave:
            for i in range(winreg.QueryInfoKey(clave)[0]):
                try:
                    sub = winreg.EnumKey(clave, i)
                    with winreg.OpenKey(clave, sub) as k:
                        nombre = _texto(_valor(k, "DisplayName"))
                        if not nombre:
                            continue
                        fecha = _texto(_valor(k, "InstallDate"))
                        entrada = {
                            "nombre": nombre,
                            "version": _texto(_valor(k, "DisplayVersion")),
                            "editor": _texto(_valor(k, "Publisher")),
                            "fecha": fecha if fecha and re.fullmatch(r"\d{8}", fecha) else None,
                            "oculto": _texto(_valor(k, "SystemComponent")) == "1" or _texto(_valor(k, "ParentKeyName")) is not None,
                            "origen": "registro",
                        }
                except OSError:
                    continue
                clave_dup = (entrada["nombre"].casefold(), (entrada["version"] or "").casefold())
                previa = encontrados.setdefault(clave_dup, entrada)
                previa["oculto"] = previa["oculto"] and entrada["oculto"]  # visible si alguna copia lo es
                previa["fecha"] = previa["fecha"] or entrada["fecha"]
    if fallos == len(_CLAVES):
        raise OSError("no se pudo leer ninguna clave Uninstall")
    return list(encontrados.values())


def _parsear_aplicaciones(texto) -> list:
    """Salida JSON de Get-StartApps: una lista, o un solo objeto cuando hay una única aplicación."""
    try:
        datos = json.loads(texto)
    except (TypeError, ValueError):
        return []
    if isinstance(datos, dict):
        datos = [datos]
    if not isinstance(datos, list):
        return []
    return [{"nombre": d["Name"], "version": None, "editor": None, "fecha": None, "oculto": False, "origen": "menu_inicio"}
            for d in datos if isinstance(d, dict) and isinstance(d.get("Name"), str) and d["Name"].strip()]


def _leer_aplicaciones_inicio() -> list:
    powershell = shutil.which("powershell.exe")
    if not powershell:
        return []
    try:
        r = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding = [Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=_SEG_POWERSHELL,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)
        return _parsear_aplicaciones(r.stdout) if r.returncode == 0 else []
    except Exception:
        return []
