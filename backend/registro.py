"""
backend/registro.py — Registro opcional de equipos revisados (SQLite local). Decisión 42.

OPT-IN: solo se escribe cuando el usuario pulsa «Guardar en el registro». Nada se envía por internet; el
archivo vive en el USB (carpeta registros/ junto a backend/) o donde diga la variable DSPC_REGISTRO.
Guarda el último escaneo y análisis en memoria más etiqueta, responsable y notas. Para borrar todo basta
con borrar el archivo. Sin sqlite3 externo: solo la biblioteca estándar.
"""

import csv
import io
import json
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_MAX_TEXTO = {"etiqueta": 80, "responsable": 80, "notas": 1000}
_COLUMNAS_CSV = ["id", "fecha", "etiqueta", "responsable", "notas", "veredicto", "equipo", "sistema", "procesador", "memoria_gb"]

_ESQUEMA = """CREATE TABLE IF NOT EXISTS equipos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT NOT NULL, etiqueta TEXT NOT NULL, responsable TEXT NOT NULL DEFAULT '',
    notas TEXT NOT NULL DEFAULT '', veredicto TEXT NOT NULL, equipo TEXT NOT NULL DEFAULT '', sistema TEXT NOT NULL DEFAULT '',
    procesador TEXT NOT NULL DEFAULT '', memoria_gb REAL, estados TEXT NOT NULL, detalle TEXT NOT NULL)"""


def ruta_db() -> str:
    return os.environ.get("DSPC_REGISTRO") or os.path.join(BASE_DIR, "..", "registros", "registro.db")


@contextmanager
def _conectar():
    """Conexión que confirma al salir y SIEMPRE se cierra (en Windows un archivo abierto no se puede mover ni borrar)."""
    ruta = os.path.abspath(ruta_db())
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with closing(sqlite3.connect(ruta, timeout=5)) as con:
        con.row_factory = sqlite3.Row
        with con:
            con.execute(_ESQUEMA)
            yield con


def _txt(v, maximo):
    return v.strip()[:maximo] if isinstance(v, str) else ""


def _resumen_equipo(escaneo: dict) -> dict:
    """Datos de identificación del equipo, leídos sin suponer nada: lo que falta queda vacío."""
    comps = escaneo.get("componentes") if isinstance(escaneo.get("componentes"), dict) else {}
    dato = lambda c: comps.get(c, {}).get("datos") if isinstance(comps.get(c), dict) and isinstance(comps[c].get("datos"), dict) else {}
    mb, so = dato("mainboard"), escaneo.get("hechos", {}).get("so") if isinstance(escaneo.get("hechos"), dict) else None
    gb = dato("ram").get("capacidad_fisica_gb")
    return {
        "equipo": " ".join(x for x in (mb.get("fabricante"), mb.get("modelo")) if isinstance(x, str)),
        "sistema": so.get("nombre") if isinstance(so, dict) and isinstance(so.get("nombre"), str) else "",
        "procesador": dato("cpu").get("nombre") if isinstance(dato("cpu").get("nombre"), str) else "",
        "memoria_gb": gb if isinstance(gb, (int, float)) and not isinstance(gb, bool) else None,
    }


def _post_valida(post):
    """Revisión de post-instalación a guardar: solo el texto del acta y las tareas a mano marcadas; None si no es válida."""
    if not isinstance(post, dict) or not isinstance(post.get("acta"), str) or not post["acta"].strip():
        return None
    marcadas = post.get("marcadas") if isinstance(post.get("marcadas"), list) else []
    return {"acta": post["acta"][:6000], "marcadas": [m[:40] for m in marcadas if isinstance(m, str)][:20]}


def guardar(escaneo, analisis, veredicto: str, etiqueta, responsable="", notas="", post=None) -> int:
    """Guarda un equipo y devuelve su id. ValueError si no hay escaneo real o falta la etiqueta."""
    if not isinstance(escaneo, dict) or not escaneo.get("componentes"):
        raise ValueError("Primero revisa tu PC: no hay un escaneo que guardar.")
    etiqueta = _txt(etiqueta, _MAX_TEXTO["etiqueta"])
    if not etiqueta:
        raise ValueError("Escribe un nombre o etiqueta para reconocer el equipo.")
    estados = {n: c.get("estado") for n, c in escaneo["componentes"].items() if isinstance(c, dict)}
    r = _resumen_equipo(escaneo)
    detalle = json.dumps({"escaneo": escaneo, "analisis": analisis, "postinstalacion": _post_valida(post)}, ensure_ascii=False, default=str)
    with _conectar() as con:
        cur = con.execute(
            "INSERT INTO equipos (fecha, etiqueta, responsable, notas, veredicto, equipo, sistema, procesador, memoria_gb, estados, detalle)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), etiqueta, _txt(responsable, _MAX_TEXTO["responsable"]),
             _txt(notas, _MAX_TEXTO["notas"]), str(veredicto), r["equipo"], r["sistema"], r["procesador"], r["memoria_gb"],
             json.dumps(estados), detalle))
        return cur.lastrowid


def listar(limite: int = 500) -> list:
    """Equipos guardados, el más reciente primero (sin el detalle pesado)."""
    with _conectar() as con:
        filas = con.execute("SELECT id, fecha, etiqueta, responsable, notas, veredicto, equipo, sistema, procesador, memoria_gb, estados"
                            " FROM equipos ORDER BY id DESC LIMIT ?", (int(limite),)).fetchall()
    return [{**dict(f), "estados": json.loads(f["estados"])} for f in filas]


def obtener(id_equipo: int):
    """El detalle guardado de un equipo ({escaneo, analisis}) o None."""
    with _conectar() as con:
        f = con.execute("SELECT detalle FROM equipos WHERE id=?", (int(id_equipo),)).fetchone()
    return json.loads(f["detalle"]) if f else None


def borrar(id_equipo: int) -> bool:
    with _conectar() as con:
        return con.execute("DELETE FROM equipos WHERE id=?", (int(id_equipo),)).rowcount > 0


def csv_texto() -> str:
    """CSV para Excel: UTF-8 con BOM, y las celdas que empiezan por = + - @ se neutralizan (inyección de fórmulas)."""
    salida = io.StringIO()
    w = csv.writer(salida)
    w.writerow(_COLUMNAS_CSV)
    seguro = lambda v: "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v
    for f in listar(100000):
        w.writerow([seguro(f[c]) for c in _COLUMNAS_CSV])
    return "﻿" + salida.getvalue()
