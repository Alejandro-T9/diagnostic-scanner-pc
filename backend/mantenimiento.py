"""
backend/mantenimiento.py — Mantenimiento seguro del Windows instalado (F7a, decisión 44).

Cada acción tiene VISTA PREVIA (qué haría, sin tocar nada) y EJECUCIÓN (solo cuando el usuario confirma en la
pantalla). Lista cerrada de acciones: no se ejecuta ningún comando que llegue desde la web. Nunca apaga el
antivirus, el firewall ni Windows Update, y no toca el registro fuera de la lista de inicio (StartupApproved,
reversible). Lo que se hizo queda en `mantenimiento.log` junto al registro de equipos. Las acciones que cambian algo
dicen cómo deshacerse (o que no se puede). Las tareas largas (sfc, DISM, chkdsk) corren en un hilo y se consultan.
"""

import ctypes
import datetime
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import winreg

import psutil

import registro
import utils
from analisis import espacio, inicio

_MAX_SEG_TEMP = 6.0
_UN_DIA = 24 * 3600
_REPARSE = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT: enlaces y junctions, no se siguen
_GUID = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
_ALTO_RENDIMIENTO = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
_MAXIMO_RENDIMIENTO = "e9a42b02-d5df-448d-aa00-03f14749eb61"
# Nunca se ofrecen para desactivar: seguridad, controladores y la herramienta del colegio.
_PROTEGIDOS = re.compile(r"defender|antivir|securit|segur|realtek|audio|nvidia|amd|intel|driver|bluetooth|touchpad|synaptics|elan|wacom|faronics|freeze|dfserv|hotkey", re.I)
_APROBADO = inicio._APROBADO
_NO_CRIT = "No se puede deshacer."

ACCIONES = {
    "punto_restauracion": {"titulo": "Crear un punto de restauración", "admin": True, "riesgo": "bajo", "tarda": "unos segundos",
                           "descripcion": "Guarda un punto al que Windows puede volver si algo sale mal. Conviene hacerlo antes de lo demás."},
    "temporales": {"titulo": "Limpiar archivos temporales", "admin": False, "riesgo": "bajo", "tarda": "unos segundos",
                   "descripcion": "Borra archivos temporales de más de un día de las carpetas Temp. Los que están en uso se saltan. " + _NO_CRIT},
    "papelera": {"titulo": "Vaciar la papelera", "admin": False, "riesgo": "medio", "tarda": "unos segundos",
                 "descripcion": "Borra para siempre lo que hay en la papelera. Revisa antes que no haya nada que quieras recuperar. " + _NO_CRIT},
    "inicio": {"titulo": "Programas que arrancan con Windows", "admin": False, "riesgo": "bajo", "tarda": "unos segundos",
               "descripcion": "Elige cuáles dejan de abrirse al encender. No se borra nada y puedes volver a activarlos. Los de seguridad y controladores no aparecen."},
    "energia": {"titulo": "Plan de energía de alto rendimiento", "admin": False, "riesgo": "bajo", "tarda": "unos segundos",
                "descripcion": "Cambia el plan de energía para que el equipo no se frene. En portátiles gasta más batería. Se puede volver al plan anterior."},
    "reparar_sistema": {"titulo": "Reparar archivos de Windows (sfc y DISM)", "admin": True, "riesgo": "bajo", "tarda": "de 10 a 40 minutos",
                        "descripcion": "Comprueba y repara los archivos del sistema con las herramientas de Microsoft. No cierres la aplicación mientras corre."},
    "disco": {"titulo": "Revisar el disco en busca de errores", "admin": True, "riesgo": "bajo", "tarda": "de 2 a 15 minutos",
              "descripcion": "Revisa el sistema de archivos con chkdsk sin reiniciar y sin cambiar nada (solo lectura)."},
    "velocidad_disco": {"titulo": "Medir la velocidad del disco", "admin": True, "riesgo": "bajo", "tarda": "1 o 2 minutos",
                        "descripcion": "Mide la lectura del disco del sistema con winsat; sirve para comparar antes y después."},
    "memoria": {"titulo": "Probar la memoria RAM", "admin": True, "riesgo": "medio", "tarda": "el equipo se reinicia",
                "descripcion": "Abre el Diagnóstico de memoria de Windows, que pide reiniciar. Guarda tu trabajo antes."},
    "mrt": {"titulo": "Buscar software malintencionado (Microsoft)", "admin": True, "riesgo": "bajo", "tarda": "de 5 a 30 minutos",
            "descripcion": "Abre la herramienta de eliminación de software malintencionado de Microsoft. No reemplaza a un antivirus."},
    "quitar_parche": {"titulo": "Desinstalar una actualización con problemas", "admin": True, "riesgo": "medio", "tarda": "unos minutos",
                      "descripcion": "Quita una actualización de Windows concreta (por ejemplo, KB5120998 si falla el mouse). Solo si un técnico lo indica."},
}

_trabajos = {}
_cerrojo = threading.Lock()
_antes = None


# --------------------------------------------------------------------------- utilidades
def _correr(comando: list, timeout: int = 120):
    """Ejecuta un comando de la lista cerrada y devuelve (código, salida). Reemplazable en pruebas."""
    r = subprocess.run(comando, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, _texto(r.stdout + r.stderr)


def _texto(datos: bytes) -> str:
    # sfc escribe en UTF-16: al decodificar como OEM quedan NUL entre letras
    return datos.decode("cp850", errors="replace").replace("\x00", "")


def _ruta_log() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(registro.ruta_db())), "mantenimiento.log")


def _log(accion: str, estado: str, mensaje: str, detalle=None) -> None:
    try:
        ruta = _ruta_log()
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(json.dumps({"fecha": datetime.datetime.now().isoformat(timespec="seconds"), "accion": accion,
                                "estado": estado, "mensaje": mensaje, "detalle": detalle}, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass  # el registro de lo hecho es un extra: si no se puede escribir, la acción igual se informa en pantalla


def historial(limite: int = 50) -> list:
    try:
        with open(_ruta_log(), encoding="utf-8") as f:
            lineas = f.readlines()[-limite:]
    except OSError:
        return []
    salida = []
    for linea in reversed(lineas):
        try:
            salida.append(json.loads(linea))
        except ValueError:
            continue
    return salida


def _resultado(estado: str, mensaje: str, detalle=None, **extra) -> dict:
    return {"estado": estado, "mensaje": mensaje, "detalle": detalle if detalle is not None else [], **extra}


def _gb(n: int) -> float:
    return round(n / 1024 ** 3, 2)


# --------------------------------------------------------------------------- medidas (antes y después)
def medidas() -> dict:
    """Foto rápida para comparar antes y después de mantener: espacio libre y programas que arrancan solos."""
    uso = shutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
    try:
        activos = sum(1 for e in _entradas_inicio() if e["habilitado"])
    except Exception:
        activos = None
    return {"libre_gb": _gb(uso.free), "libre_pct": round(uso.free / uso.total * 100, 1), "inicio_activos": activos}


def comparar(reiniciar: bool = False) -> dict:
    """{antes, ahora}: «antes» es la primera medida de la sesión (o la que se pide reiniciar)."""
    global _antes
    ahora = medidas()
    if _antes is None or reiniciar:
        _antes = ahora
    return {"antes": _antes, "ahora": ahora}


# --------------------------------------------------------------------------- temporales
def _carpetas_temp() -> list:
    ruta = [os.environ.get("TEMP", ""), os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")]
    vistas, salida = set(), []
    for r in ruta:
        if r and os.path.isdir(r) and os.path.normcase(os.path.abspath(r)) not in vistas:
            vistas.add(os.path.normcase(os.path.abspath(r)))
            salida.append(os.path.abspath(r))
    return salida


def _recorrer_temp(raiz: str, borrar: bool, limite: float) -> dict:
    """Suma (y borra si `borrar`) los archivos de más de un día bajo `raiz`. Sin seguir enlaces; sin pasar de `limite` s."""
    total = {"bytes": 0, "archivos": 0, "saltados": 0, "completo": True}
    corte = time.time() - _UN_DIA
    pila, vacias = [raiz], []
    while pila:
        if time.monotonic() > limite:
            total["completo"] = False
            break
        carpeta = pila.pop()
        try:
            with os.scandir(carpeta) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                        if e.is_dir(follow_symlinks=False):
                            if not st.st_file_attributes & _REPARSE:
                                pila.append(e.path)
                                vacias.append(e.path)
                        elif st.st_mtime < corte:
                            if borrar:
                                os.remove(e.path)
                            total["bytes"] += st.st_size
                            total["archivos"] += 1
                    except OSError:
                        total["saltados"] += 1  # en uso o sin permiso
        except OSError:
            total["saltados"] += 1
    if borrar:
        for d in reversed(vacias):  # carpetas que quedaron vacías (rmdir falla si no lo están)
            try:
                os.rmdir(d)
            except OSError:
                pass
    return total


def _temporales(borrar: bool) -> dict:
    limite = time.monotonic() + _MAX_SEG_TEMP
    carpetas = [(c, _recorrer_temp(c, borrar, limite)) for c in _carpetas_temp()]
    return {"bytes": sum(t["bytes"] for _, t in carpetas), "archivos": sum(t["archivos"] for _, t in carpetas),
            "saltados": sum(t["saltados"] for _, t in carpetas), "completo": all(t["completo"] for _, t in carpetas),
            "carpetas": [c for c, _ in carpetas]}


# --------------------------------------------------------------------------- inicio
def _entradas_inicio() -> list:
    """Programas de inicio con lo necesario para (des)activarlos: id, nombre, origen, lugar y si están habilitados."""
    fuentes = [("HKCU", winreg.HKEY_CURRENT_USER, inicio._RUN, "Run"),
               ("HKLM", winreg.HKEY_LOCAL_MACHINE, inicio._RUN, "Run"),
               ("HKLM", winreg.HKEY_LOCAL_MACHINE, r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Run", "Run32")]
    entradas = []
    for nombre_raiz, raiz, ruta, lugar in fuentes:
        try:
            valores = inicio._valores(raiz, ruta)
            estados = inicio._valores(raiz, _APROBADO + "\\" + lugar)
        except OSError:
            continue
        entradas += [{"id": f"{nombre_raiz}|{lugar}|{n}", "nombre": n, "comando": str(c)[:120],
                      "habilitado": inicio._habilitado(estados.get(n))} for n, c in valores.items()]
    for e in inicio._leer_carpetas_inicio():
        raiz = "HKCU" if e["origen"] == "usuario" else "HKLM"
        entradas.append({"id": f"{raiz}|StartupFolder|{e['nombre']}", "nombre": e["nombre"], "comando": e["comando"][:120], "habilitado": e["habilitado"]})
    for e in entradas:
        e["protegido"] = bool(_PROTEGIDOS.search(e["nombre"] + " " + e["comando"]))
    return entradas


def _fijar_inicio(id_entrada: str, habilitar: bool) -> None:
    raiz_n, lugar, nombre = id_entrada.split("|", 2)
    raiz = winreg.HKEY_CURRENT_USER if raiz_n == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    with winreg.CreateKeyEx(raiz, _APROBADO + "\\" + lugar, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, nombre, 0, winreg.REG_BINARY, bytes([2 if habilitar else 3]) + bytes(11))


# --------------------------------------------------------------------------- energía
def _plan_activo():
    codigo, salida = _correr(["powercfg", "/getactivescheme"], 15)
    m = re.search(r"([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})\s*\(([^)]*)\)", salida)
    return (m.group(1), m.group(2)) if codigo == 0 and m else (None, None)


def _es_portatil() -> bool:
    try:
        return psutil.sensors_battery() is not None
    except Exception:
        return False


# --------------------------------------------------------------------------- trabajos largos
def _hilo_trabajo(tid: str, comandos: list) -> None:
    t = _trabajos[tid]
    try:
        for cmd in comandos:
            t["actual"] = " ".join(cmd)
            codigo, salida = _correr(cmd, 3 * 3600)
            t["salida"] = (t["salida"] + [l.strip() for l in salida.splitlines() if l.strip()])[-40:]
            t["codigos"].append(codigo)
        t["estado"] = "terminado" if all(c in (0, 3010) for c in t["codigos"]) else "con_avisos"
    except Exception as error:
        t["estado"] = "error"
        t["salida"].append(f"No se pudo ejecutar: {error}")
    t["fin"] = datetime.datetime.now().isoformat(timespec="seconds")
    _log(t["accion"], t["estado"], f"códigos {t['codigos']}", t["salida"][-6:])


def _iniciar_trabajo(accion: str, comandos: list) -> dict:
    with _cerrojo:
        if any(t["estado"] == "corriendo" for t in _trabajos.values()):
            return _resultado("error", "Ya hay una tarea larga en curso. Espera a que termine.")
        tid = uuid.uuid4().hex[:10]
        _trabajos[tid] = {"id": tid, "accion": accion, "estado": "corriendo", "salida": [], "codigos": [], "actual": "",
                          "inicio": datetime.datetime.now().isoformat(timespec="seconds"), "fin": None}
    threading.Thread(target=_hilo_trabajo, args=(tid, comandos), daemon=True).start()
    return _resultado("trabajo", "La tarea empezó. Puede tardar; no cierres la aplicación.", trabajo=tid)


def estado_trabajo(tid: str):
    t = _trabajos.get(tid)
    return dict(t, salida=list(t["salida"]), codigos=list(t["codigos"])) if t else None


_COMANDOS_LARGOS = {
    "reparar_sistema": [["sfc", "/scannow"], ["DISM.exe", "/Online", "/Cleanup-Image", "/RestoreHealth"]],
    "disco": [["chkdsk", os.environ.get("SystemDrive", "C:"), "/scan"]],
    "velocidad_disco": [["winsat", "disk", "-drive", os.environ.get("SystemDrive", "C:")[0].lower()]],
}


# --------------------------------------------------------------------------- vista previa y ejecución
def listar() -> list:
    admin = utils.es_administrador()
    return [{"id": i, **a, "disponible": admin or not a["admin"]} for i, a in ACCIONES.items()]


def previsualizar(accion: str, params: dict) -> dict:
    try:
        if accion == "temporales":
            t = _temporales(False)
            return _resultado("ok", f"Se liberarían unos {t['bytes'] / 1024 ** 2:.0f} MB ({t['archivos']} archivos viejos)."
                              + ("" if t["completo"] else " Es un cálculo parcial: hay muchos archivos."), t["carpetas"])
        if accion == "papelera":
            p = espacio._leer_papelera()
            return _resultado("ok", "No se pudo leer la papelera." if p["tamano_gb"] is None
                              else f"La papelera tiene {p['archivos']} elemento(s), {p['tamano_gb']} GB.", [])
        if accion == "inicio":
            lista = [e for e in _entradas_inicio() if e["habilitado"] and not e["protegido"]]
            return _resultado("ok", f"{len(lista)} programa(s) arrancan con Windows y se pueden desactivar.", lista)
        if accion == "energia":
            guid, nombre = _plan_activo()
            nota = " Es un portátil: gastará más batería." if _es_portatil() else ""
            return _resultado("ok", f"Plan actual: {nombre or 'desconocido'}.{nota}", [], anterior=guid)
        if accion == "quitar_parche":
            kb = str(params.get("kb", "")).upper().removeprefix("KB")
            if not re.fullmatch(r"\d{6,8}", kb):
                return _resultado("error", "Escribe el número de la actualización, por ejemplo KB5120998.")
            return _resultado("ok", f"Se desinstalaría KB{kb}. Windows puede pedir reiniciar.", [f"KB{kb}"])
        if accion in ACCIONES:
            return _resultado("ok", ACCIONES[accion]["descripcion"], [])
        return _resultado("error", "Esa acción no existe.")
    except Exception as error:
        return _resultado("error", f"No se pudo preparar la vista previa: {error}")


def ejecutar(accion: str, params: dict) -> dict:
    """Ejecuta una acción de la lista cerrada. Nunca lanza: devuelve estado ok / trabajo / error y lo anota en el registro."""
    if accion not in ACCIONES:
        return _resultado("error", "Esa acción no existe.")
    if ACCIONES[accion]["admin"] and not utils.es_administrador():
        return _resultado("error", "Esta acción necesita permisos de administrador. Cierra y abre de nuevo la aplicación aceptando el aviso de Windows.")
    try:
        r = _ejecutar(accion, params)
    except Exception as error:
        r = _resultado("error", f"No se pudo completar la acción: {error}")
    if r["estado"] != "trabajo":  # los trabajos se anotan al terminar
        _log(accion, r["estado"], r["mensaje"], r["detalle"][:10] if isinstance(r["detalle"], list) else r["detalle"])
    return r


def _ejecutar(accion: str, params: dict) -> dict:
    if accion == "punto_restauracion":
        codigo, salida = _correr(["powershell", "-NoProfile", "-Command",
                                  "Checkpoint-Computer -Description 'Diagnostic Scanner PC' -RestorePointType MODIFY_SETTINGS -ErrorAction Stop"], 180)
        if codigo == 0:
            return _resultado("ok", "Punto de restauración creado.")
        return _resultado("error", "No se pudo crear el punto (la protección del sistema puede estar apagada o ya se creó uno en las últimas 24 horas).",
                          salida.strip().splitlines()[-2:])
    if accion == "temporales":
        t = _temporales(True)
        return _resultado("ok", f"Se liberaron {t['bytes'] / 1024 ** 2:.0f} MB ({t['archivos']} archivos). {t['saltados']} estaban en uso o sin permiso y se saltaron.", t["carpetas"])
    if accion == "papelera":
        antes = espacio._leer_papelera()["tamano_gb"]
        codigo = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)  # sin confirmar, sin progreso, sin sonido
        return _resultado("ok" if codigo in (0, -2147418113) else "error",  # S_OK / ya estaba vacía
                          f"Papelera vaciada ({antes} GB)." if codigo in (0, -2147418113) else f"Windows no pudo vaciar la papelera (código {codigo}).")
    if accion == "inicio":
        ids, habilitar = params.get("ids"), params.get("accion") == "reactivar"
        if not isinstance(ids, list) or not ids:
            return _resultado("error", "No elegiste ningún programa.")
        actuales = {e["id"]: e for e in _entradas_inicio()}
        hechos, fallos = [], []
        for i in ids[:50]:
            e = actuales.get(i) if isinstance(i, str) else None
            if e is None or (e["protegido"] and not habilitar):  # solo entradas que existen y no son de seguridad
                fallos.append(f"{i}: no disponible")
                continue
            try:
                _fijar_inicio(i, habilitar)
                hechos.append(i)
            except OSError as error:
                fallos.append(f"{e['nombre']}: {error}")
        verbo = "reactivaron" if habilitar else "desactivaron"
        return _resultado("ok" if hechos else "error", f"Se {verbo} {len(hechos)} programa(s)." + (f" {len(fallos)} no se pudieron." if fallos else ""),
                          {"hechos": hechos, "fallos": fallos})
    if accion == "energia":
        volver = params.get("volver_a")
        if volver is not None:
            if not isinstance(volver, str) or not _GUID.match(volver):
                return _resultado("error", "El plan anterior no es válido.")
            codigo, _ = _correr(["powercfg", "/setactive", volver], 15)
            return _resultado("ok" if codigo == 0 else "error", "Volviste al plan anterior." if codigo == 0 else "No se pudo volver al plan anterior.")
        anterior, _ = _plan_activo()
        codigo, salida = _correr(["powercfg", "/setactive", _ALTO_RENDIMIENTO], 15)
        if codigo != 0:  # el plan no existe en este equipo: se crea a partir del de máximo rendimiento
            codigo, salida = _correr(["powercfg", "-duplicatescheme", _MAXIMO_RENDIMIENTO], 15)
            nuevo = re.search(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", salida)
            codigo = _correr(["powercfg", "/setactive", nuevo.group(0)], 15)[0] if codigo == 0 and nuevo else 1
        return _resultado("ok" if codigo == 0 else "error", "Plan de alto rendimiento activado." if codigo == 0 else "No se pudo cambiar el plan de energía.",
                          [], anterior=anterior)
    if accion in _COMANDOS_LARGOS:
        return _iniciar_trabajo(accion, _COMANDOS_LARGOS[accion])
    if accion in ("memoria", "mrt"):
        exe = shutil.which("mdsched.exe" if accion == "memoria" else "mrt.exe")
        if not exe:
            return _resultado("error", "No se encontró la herramienta en este Windows.")
        subprocess.Popen([exe], stdin=subprocess.DEVNULL)
        return _resultado("ok", "Se abrió la herramienta de Windows; sigue sus instrucciones en esa ventana.")
    if accion == "quitar_parche":
        kb = str(params.get("kb", "")).upper().removeprefix("KB")
        if not re.fullmatch(r"\d{6,8}", kb):
            return _resultado("error", "Escribe el número de la actualización, por ejemplo KB5120998.")
        codigo, salida = _correr(["wusa", "/uninstall", f"/kb:{kb}", "/quiet", "/norestart"], 600)
        if codigo in (0, 3010):
            return _resultado("ok", f"KB{kb} desinstalada." + (" Reinicia el equipo para terminar." if codigo == 3010 else ""))
        return _resultado("error", f"No se pudo desinstalar KB{kb} (código {codigo}); puede que no esté instalada.")
    return _resultado("error", "Esa acción no existe.")
