"""
backend/instalador.py — Instalador offline con verificación de huella (F7b, decisión 45).

Instala SOLO programas que el equipo puso en la carpeta `instaladores/` y declaró en `instaladores.json`
(ver instaladores.ejemplo.json). Cada instalación exige: archivo dentro de la carpeta (sin rutas), extensión
.exe/.msi, huella SHA-256 declarada que COINCIDA con el archivo, permisos de administrador y confirmación en
pantalla. No descarga nada de internet, no incluye activadores ni modificaciones de programas, y no ejecuta
comandos escritos en la web: los argumentos salen del manifiesto, que es un archivo local del USB.
La instalación corre como tarea larga del módulo de mantenimiento (se consulta con /api/mantenimiento/trabajo/<id>).
"""

import hashlib
import json
import os
import re

import mantenimiento
import postinstalacion
import utils

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXT = (".exe", ".msi")


def carpeta() -> str:
    """Carpeta de instaladores: DSPC_INSTALADORES, o `carpeta_instaladores` del perfil, o «instaladores» junto a backend/."""
    ruta = os.environ.get("DSPC_INSTALADORES") or postinstalacion._perfil().get("carpeta_instaladores") or "instaladores"
    return os.path.abspath(os.path.join(BASE_DIR, "..", ruta))


def _huella(ruta: str) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _manifiesto() -> list:
    """Entradas válidas del manifiesto; [] si no existe o no se puede leer. Las malformadas se descartan una a una."""
    try:
        with open(os.path.join(carpeta(), "instaladores.json"), encoding="utf-8-sig") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return []
    entradas = datos.get("programas") if isinstance(datos, dict) else None
    validas = []
    for e in entradas if isinstance(entradas, list) else []:
        if (isinstance(e, dict) and all(isinstance(e.get(k), str) and e[k].strip() for k in ("id", "nombre", "archivo"))
                and re.fullmatch(r"[a-z0-9_-]{1,40}", e["id"]) and isinstance(e.get("args", []), list)
                and all(isinstance(a, str) for a in e.get("args", []))):
            validas.append(e)
    return validas


def _problema(e: dict, base: str):
    """Motivo por el que NO se puede instalar, o None. Revisa el archivo, la extensión y que la huella declarada exista."""
    nombre = e["archivo"]
    if nombre != os.path.basename(nombre) or not nombre.lower().endswith(_EXT):
        return "El archivo debe estar directamente en la carpeta y ser .exe o .msi."
    if not os.path.isfile(os.path.join(base, nombre)):
        return "No se encuentra el archivo en la carpeta de instaladores."
    if not _SHA256.match(str(e.get("sha256", "")).lower()):
        return "Falta la huella SHA-256 en el manifiesto: sin ella no se instala."
    return None


def listar() -> dict:
    base = carpeta()
    try:
        nombres = [p["nombre"].lower() for p in postinstalacion._programas_instalados()]
    except Exception:
        nombres = None  # no se pudo leer: no se afirma ni que esté ni que falte
    entradas = []
    for e in _manifiesto():
        patron = e.get("detectar")
        instalado = None if nombres is None or not isinstance(patron, str) else any(re.search(patron, n, re.I) for n in nombres)
        entradas.append({"id": e["id"], "nombre": e["nombre"], "version": str(e.get("version", "")), "categoria": str(e.get("categoria", "")),
                         "instalado": instalado, "problema": _problema(e, base)})
    return {"carpeta": base, "existe": os.path.isdir(base), "administrador": utils.es_administrador(), "entradas": entradas}


def instalar(id_programa: str) -> dict:
    """Verifica y lanza la instalación. Nunca lanza: devuelve {estado: trabajo|error, mensaje, ...}."""
    if not utils.es_administrador():
        return {"estado": "error", "mensaje": "Instalar necesita permisos de administrador. Cierra y abre de nuevo la aplicación aceptando el aviso de Windows."}
    base = carpeta()
    e = next((x for x in _manifiesto() if x["id"] == id_programa), None)
    if e is None:
        return {"estado": "error", "mensaje": "Ese programa no está en el manifiesto de instaladores."}
    motivo = _problema(e, base)
    if motivo:
        return {"estado": "error", "mensaje": motivo}
    ruta = os.path.join(base, e["archivo"])
    try:
        if _huella(ruta) != str(e["sha256"]).lower():
            mantenimiento._log("instalar_" + e["id"], "error", "La huella SHA-256 no coincide: no se instaló.")
            return {"estado": "error", "mensaje": "La huella SHA-256 del archivo no coincide con la del manifiesto: el archivo cambió o está dañado. No se instaló."}
    except OSError as error:
        return {"estado": "error", "mensaje": f"No se pudo leer el instalador: {error}"}
    cmd = ["msiexec", "/i", ruta, *e.get("args", [])] if ruta.lower().endswith(".msi") else [ruta, *e.get("args", [])]
    r = mantenimiento._iniciar_trabajo("instalar_" + e["id"], [cmd])
    if r["estado"] == "trabajo":
        r["mensaje"] = f"Instalando {e['nombre']}… no cierres la aplicación."
    return r


def huellas() -> list:
    """SHA-256 de cada .exe/.msi de la carpeta, para copiarlos al manifiesto."""
    base = carpeta()
    try:
        archivos = sorted(f for f in os.listdir(base) if f.lower().endswith(_EXT) and os.path.isfile(os.path.join(base, f)))
    except OSError:
        return []
    return [{"archivo": f, "sha256": _huella(os.path.join(base, f)), "mb": round(os.path.getsize(os.path.join(base, f)) / 1024 ** 2, 1)} for f in archivos]
