"""
backend/postinstalacion.py — Lista de revisión para un equipo recién instalado o formateado (F6, decisión 43).

SOLO LECTURA, sin administrador: no instala, no activa, no desactiva ni cambia nada. Comprueba lo que se puede leer
(controladores, protección de Windows, espacio, nombre del equipo, activación, programas básicos) y deja como
tareas «a mano» lo que no (buscar actualizaciones, copias de seguridad). La activación solo se LEE: la app no trae ni
sugiere activadores, y siempre recomienda una licencia legítima. Reusa los módulos de backend/analisis/.
Perfil opcional (perfil.json junto a backend/, o la ruta de DSPC_PERFIL; ver perfil.ejemplo.json): prefijo del nombre del
equipo, zona horaria, idioma y carpeta de instaladores del USB. Sin perfil esas comprobaciones no aparecen.
"""

import datetime
import json
import os
import re
import socket
import subprocess
import winreg

from analisis import controladores, espacio, programas, seguridad

_NOMBRE_DE_FABRICA = re.compile(r"^(DESKTOP|LAPTOP|WIN)-[A-Z0-9]{5,8}$", re.I)
# categoría -> patrones del nombre del programa (cualquiera basta)
_SIN_VALOR = {"", "0", "default string", "to be filled by o.e.m.", "none", "system serial number", "not specified"}
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


def _perfil() -> dict:
    ruta = os.environ.get("DSPC_PERFIL") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "perfil.json")
    try:
        with open(ruta, encoding="utf-8-sig") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def _ficha() -> dict:
    """Datos de identificación para la hoja de SOPORTE TÉCNICO; lo que no se lee queda vacío."""
    import wmi
    c = wmi.WMI()
    ficha = {"fabricante": "", "modelo": "", "serial": "", "sistema": "", "macs": []}
    for sistema in c.Win32_ComputerSystem():
        ficha["fabricante"], ficha["modelo"] = str(sistema.Manufacturer or "").strip(), str(sistema.Model or "").strip()
    for bios in c.Win32_BIOS():
        serial = str(bios.SerialNumber or "").strip()
        ficha["serial"] = "" if serial.lower() in _SIN_VALOR else serial
    for so in c.Win32_OperatingSystem():
        ficha["sistema"] = f"{str(so.Caption or '').strip()} (compilación {so.BuildNumber})"
    ficha["macs"] = [str(a.MACAddress) for a in c.Win32_NetworkAdapter(PhysicalAdapter=True) if a.MACAddress]
    return ficha


def _ultima_actualizacion():
    """Fecha de la actualización instalada más reciente (datetime.date) o None si no se pudo leer."""
    import wmi
    fechas = []
    for q in wmi.WMI().Win32_QuickFixEngineering():
        for formato in ("%m/%d/%Y", "%Y%m%d", "%d/%m/%Y"):
            try:
                fechas.append(datetime.datetime.strptime(str(q.InstalledOn).strip(), formato).date())
                break
            except ValueError:
                continue
    return max(fechas) if fechas else None


def _reinicio_pendiente():
    """True/False según las marcas de Windows Update y de instalaciones; None si no se pudo leer."""
    claves = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
              r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending")
    try:
        for clave in claves:
            try:
                winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, clave))
                return True
            except FileNotFoundError:
                continue
        return False
    except OSError:
        return None


def _zona_horaria() -> str:
    r = subprocess.run(["tzutil", "/g"], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.stdout.strip()


def _idioma() -> str:
    import ctypes
    buf = ctypes.create_unicode_buffer(85)
    return buf.value if ctypes.windll.kernel32.GetUserDefaultLocaleName(buf, 85) else ""


def _contar_instaladores(ruta) -> int:
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ruta)
    try:
        return sum(1 for f in os.listdir(base) if f.lower().endswith((".exe", ".msi", ".msix")))
    except OSError:
        return 0


def _actualizaciones(ultima, hoy=None) -> dict:
    titulo = "Actualizaciones de Windows instaladas"
    if ultima is None:
        return _item("actualizaciones_auto", titulo, "no_determinado", "No se pudo leer cuándo se instaló la última actualización.",
                     "Míralo en Configuración → Windows Update → Historial.")
    dias = ((hoy or datetime.date.today()) - ultima).days
    if dias > 60:
        return _item("actualizaciones_auto", titulo, "advertencia", f"La última actualización se instaló hace {dias} días.",
                     "Busca actualizaciones en Configuración → Windows Update (necesita internet).")
    return _item("actualizaciones_auto", titulo, "normal", f"La última actualización se instaló hace {max(dias, 0)} días.")


def _reinicio(pendiente) -> dict:
    if pendiente is True:
        return _item("reinicio", "Reinicio pendiente", "advertencia", "Windows pide reiniciar para terminar de instalar algo.",
                     "Guarda tu trabajo y reinicia el equipo.")
    if pendiente is False:
        return _item("reinicio", "Reinicio pendiente", "normal", "No hay reinicios pendientes.")
    return _item("reinicio", "Reinicio pendiente", "no_determinado", "No se pudo comprobar.", "Reinicia el equipo por si acaso.")


def _del_perfil(perfil: dict, zona, idioma, instaladores) -> list:
    """Comprobaciones del perfil del colegio; zona, idioma e instaladores se leen aparte (reemplazables en pruebas)."""
    items = []
    if isinstance(perfil.get("zona_horaria"), str):
        ok = zona == perfil["zona_horaria"]
        items.append(_item("perfil_zona", "Zona horaria", "normal" if ok else "advertencia", f"Zona horaria actual: {zona or 'desconocida'}.",
                           "" if ok else f"Cámbiala a «{perfil['zona_horaria']}» en Configuración → Hora e idioma."))
    if isinstance(perfil.get("idioma"), str):
        ok = (idioma or "").lower().startswith(perfil["idioma"].lower())
        items.append(_item("perfil_idioma", "Idioma de Windows", "normal" if ok else "advertencia", f"Idioma actual: {idioma or 'desconocido'}.",
                           "" if ok else "Instala o elige el idioma en Configuración → Hora e idioma."))
    if isinstance(perfil.get("carpeta_instaladores"), str):
        items.append(_item("perfil_instaladores", "Carpeta de instaladores del USB", "normal" if instaladores else "advertencia",
                           f"Hay {instaladores} instalador(es) listos." if instaladores else "No se encontró la carpeta o está vacía.",
                           "" if instaladores else "Pon ahí los instaladores del navegador, PDF y oficina para usarlos sin internet."))
    return items


def _item(id_, titulo, estado, detalle, que_hacer="", manual=False):
    return {"id": id_, "titulo": titulo, "estado": estado, "detalle": detalle, "que_hacer": que_hacer, "manual": manual}


def _desde_analisis(id_, titulo, modulo, ok_si_normal=True):
    r = modulo.diagnosticar()
    if r["estado"] == "normal":
        return _item(id_, titulo, "normal", r["mensaje"])
    return _item(id_, titulo, r["estado"] if r["estado"] != "critico" else "advertencia", r["mensaje"], r["recomendacion"])


def _nombre(nombre: str, prefijo=None) -> dict:
    if isinstance(prefijo, str) and prefijo:
        if nombre.upper().startswith(prefijo.upper()):
            return _item("nombre", "Nombre del equipo", "normal", f"El equipo se llama {nombre}.")
        return _item("nombre", "Nombre del equipo", "advertencia", f"El nombre {nombre} no empieza por «{prefijo}».",
                     f"Ponle un nombre que empiece por {prefijo} (por ejemplo {prefijo}03): Configuración → Sistema → Acerca de → Cambiar nombre.")
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
    perfil = _perfil()
    if isinstance(nombre, str):
        nombre_item, nombre_txt = _nombre(nombre, perfil.get("prefijo_nombre")), nombre
    else:
        nombre_item, nombre_txt = nombre, ""
    items = [
        _seguro(lambda: _desde_analisis("controladores", "Controladores (drivers)", controladores), "controladores", "Controladores (drivers)"),
        _seguro(lambda: _desde_analisis("seguridad", "Protección de Windows", seguridad), "seguridad", "Protección de Windows"),
        _seguro(lambda: _desde_analisis("espacio", "Espacio libre en el disco", espacio), "espacio", "Espacio libre en el disco"),
        nombre_item,
        _seguro(lambda: _licencia(_windows_activado()), "licencia", "Windows activado"),
        _seguro(lambda: _actualizaciones(_ultima_actualizacion()), "actualizaciones_auto", "Actualizaciones de Windows instaladas"),
        _seguro(lambda: _reinicio(_reinicio_pendiente()), "reinicio", "Reinicio pendiente"),
    ]
    if perfil:
        try:
            carpeta = perfil.get("carpeta_instaladores")
            items += _del_perfil(perfil, _zona_horaria() if "zona_horaria" in perfil else None, _idioma() if "idioma" in perfil else None,
                                 _contar_instaladores(carpeta) if isinstance(carpeta, str) else 0)
        except Exception:
            items.append(_item("perfil", "Perfil del colegio", "no_determinado", "No se pudo aplicar el perfil.", "Revisa perfil.json."))
    try:
        items += _basicos(_nombres_programas())
    except Exception:
        items.append(_item("programas", "Programas básicos", "no_determinado", "No se pudo leer la lista de programas.", "Revísalos a mano."))
    items += [_item(i, t, "no_determinado", "Se revisa a mano.", q, manual=True) for i, t, q in _MANUALES]
    try:
        ficha = _ficha()
    except Exception:
        ficha = {}
    return {"timestamp": datetime.datetime.now().isoformat(timespec="seconds"), "equipo": nombre_txt, "ficha": ficha, "items": items,
            "acta": texto_acta(nombre_txt, items, ficha)}


def texto_acta(equipo: str, items: list, ficha=None) -> str:
    """Texto para pegar en la hoja de SOPORTE TÉCNICO: una línea por punto revisado."""
    marca = {"normal": "OK", "advertencia": "PENDIENTE", "sospecha": "PENDIENTE", "no_determinado": "REVISAR"}
    lineas = [f"Revisión posterior a la instalación — {datetime.date.today().isoformat()}", f"Equipo: {equipo or 'sin nombre'}"]
    ficha = ficha if isinstance(ficha, dict) else {}
    for etiqueta, valor in (("Modelo", " ".join(x for x in (ficha.get("fabricante"), ficha.get("modelo")) if x)), ("Serial", ficha.get("serial")),
                            ("Sistema", ficha.get("sistema")), ("MAC", ", ".join(ficha.get("macs") or []))):
        if valor:
            lineas.append(f"{etiqueta}: {valor}")
    lineas += [f"[{marca.get(i['estado'], 'REVISAR')}] {i['titulo']}: {i['detalle']}" for i in items if not i.get("manual")]
    lineas += [f"[A MANO] {i['titulo']}" for i in items if i.get("manual")]
    return "\n".join(lineas)
