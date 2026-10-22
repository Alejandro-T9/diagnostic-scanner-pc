"""
backend/postinstalacion.py — Lista de revisión para un equipo recién instalado o formateado (F6, decisión 43).

SOLO LECTURA, sin administrador: no instala, no activa, no desactiva ni cambia nada. Comprueba lo que se puede leer
(controladores, protección de Windows, espacio, nombre del equipo, activación, programas básicos) y deja como
tareas «a mano» lo que no (buscar actualizaciones, copias de seguridad). La activación solo se LEE: la app no trae ni
sugiere activadores, y siempre recomienda una licencia legítima. Reusa los módulos de backend/analisis/.
"""

import datetime
import re
import socket

from analisis import controladores, espacio, programas, seguridad

_NOMBRE_DE_FABRICA = re.compile(r"^(DESKTOP|LAPTOP|WIN)-[A-Z0-9]{5,8}$", re.I)
# categoría -> patrones del nombre del programa (cualquiera basta)
_BASICOS = {
    "Navegador (además de Edge)": r"chrome|firefox|brave|opera",
    "Lector de PDF": r"adobe (acrobat|reader)|foxit|sumatra",
    "Compresor de archivos": r"7-zip|winrar|winzip|peazip",
    "Suite de oficina": r"microsoft (office|365)|libreoffice|openoffice|wps office",
}


def _nombre_equipo() -> str:
    return socket.gethostname()


def _windows_activado():
    """True/False según la licencia de Windows; None si no se pudo leer."""
    import wmi
    for p in wmi.WMI().query("SELECT Name, LicenseStatus FROM SoftwareLicensingProduct WHERE PartialProductKey IS NOT NULL"):
        if str(p.Name or "").startswith("Windows"):
            return int(p.LicenseStatus) == 1
    return None


def _nombres_programas() -> list:
    return [p["nombre"] for p in programas._leer_registro() if isinstance(p, dict) and isinstance(p.get("nombre"), str)]


def _item(id_, titulo, estado, detalle, que_hacer="", manual=False):
    return {"id": id_, "titulo": titulo, "estado": estado, "detalle": detalle, "que_hacer": que_hacer, "manual": manual}


def _desde_analisis(id_, titulo, modulo, ok_si_normal=True):
    r = modulo.diagnosticar()
    if r["estado"] == "normal":
        return _item(id_, titulo, "normal", r["mensaje"])
    return _item(id_, titulo, r["estado"] if r["estado"] != "critico" else "advertencia", r["mensaje"], r["recomendacion"])


def _nombre(nombre: str) -> dict:
    if _NOMBRE_DE_FABRICA.match(nombre or ""):
        return _item("nombre", "Nombre del equipo", "advertencia", f"Tiene el nombre de fábrica ({nombre}).",
                     "Ponle un nombre fácil de reconocer (por ejemplo PC-SALA1-03): Configuración → Sistema → Acerca de → Cambiar nombre.")
    return _item("nombre", "Nombre del equipo", "normal", f"El equipo se llama {nombre}.")


def _licencia(activado) -> dict:
    if activado is True:
        return _item("licencia", "Windows activado", "normal", "Windows aparece activado.")
    if activado is False:
        return _item("licencia", "Windows activado", "advertencia", "Windows no aparece activado.",
                     "Usa una licencia legítima (la del equipo o una comprada). Esta app no incluye ni recomienda activadores.")
    return _item("licencia", "Windows activado", "no_determinado", "No se pudo leer el estado de activación.",
                 "Míralo en Configuración → Sistema → Activación.")


def _basicos(nombres: list) -> list:
    out = []
    for categoria, patron in _BASICOS.items():
        hay = any(re.search(patron, n, re.I) for n in nombres)
        out.append(_item("prog_" + re.sub(r"\W+", "_", categoria.lower()).strip("_"), categoria, "normal" if hay else "advertencia",
                         "Hay uno instalado." if hay else "No se encontró ninguno.",
                         "" if hay else "Instálalo desde la página oficial del programa o desde la carpeta de instaladores de tu USB."))
    return out


_MANUALES = [
    ("actualizaciones", "Buscar actualizaciones de Windows", "Configuración → Windows Update → Buscar actualizaciones, hasta que diga «Estás al día». Necesita internet."),
    ("respaldo", "Confirmar que se hizo copia de los archivos del dueño", "Antes de entregar el equipo, verifica con el dueño que sus archivos están a salvo."),
    ("prueba_funcional", "Probar sonido, cámara, Wi-Fi y USB", "Abre un video, una videollamada de prueba y conecta una memoria USB."),
]


def _seguro(f, id_, titulo):
    """Un lector que falla no tumba la lista: ese ítem queda «sin datos»."""
    try:
        return f()
    except Exception:
        return _item(id_, titulo, "no_determinado", "No se pudo comprobar.", "Revísalo a mano.")


def revisar() -> dict:
    nombre = _seguro(lambda: _nombre_equipo(), "nombre", "Nombre del equipo")
    if isinstance(nombre, str):
        nombre_item, nombre_txt = _nombre(nombre), nombre
    else:
        nombre_item, nombre_txt = nombre, ""
    items = [
        _seguro(lambda: _desde_analisis("controladores", "Controladores (drivers)", controladores), "controladores", "Controladores (drivers)"),
        _seguro(lambda: _desde_analisis("seguridad", "Protección de Windows", seguridad), "seguridad", "Protección de Windows"),
        _seguro(lambda: _desde_analisis("espacio", "Espacio libre en el disco", espacio), "espacio", "Espacio libre en el disco"),
        nombre_item,
        _seguro(lambda: _licencia(_windows_activado()), "licencia", "Windows activado"),
    ]
    try:
        items += _basicos(_nombres_programas())
    except Exception:
        items.append(_item("programas", "Programas básicos", "no_determinado", "No se pudo leer la lista de programas.", "Revísalos a mano."))
    items += [_item(i, t, "no_determinado", "Se revisa a mano.", q, manual=True) for i, t, q in _MANUALES]
    return {"timestamp": datetime.datetime.now().isoformat(timespec="seconds"), "equipo": nombre_txt, "items": items,
            "acta": texto_acta(nombre_txt, items)}


def texto_acta(equipo: str, items: list) -> str:
    """Texto para pegar en la hoja de SOPORTE TÉCNICO: una línea por punto revisado."""
    marca = {"normal": "OK", "advertencia": "PENDIENTE", "sospecha": "PENDIENTE", "no_determinado": "REVISAR"}
    lineas = [f"Revisión posterior a la instalación — {datetime.date.today().isoformat()}", f"Equipo: {equipo or 'sin nombre'}"]
    lineas += [f"[{marca.get(i['estado'], 'REVISAR')}] {i['titulo']}: {i['detalle']}" for i in items if not i.get("manual")]
    lineas += [f"[A MANO] {i['titulo']}" for i in items if i.get("manual")]
    return "\n".join(lineas)
