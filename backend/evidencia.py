"""
backend/evidencia.py — Documentos de evidencia a partir del registro de equipos (F7c, decisión 46).

Acta imprimible con código de integridad SHA-256, comparación con la revisión anterior del mismo equipo e informe
de la jornada. Solo lee el registro; todo texto que viene del sistema o del usuario se escapa antes de entrar al HTML.
El código de integridad permite comprobar que una copia impresa corresponde a lo guardado, pero NO es una firma:
quien pueda escribir en el archivo del registro puede cambiarlo, y el código se recalcularía con lo cambiado.
"""

import datetime
from html import escape

import informe
import registro

_PESO = {"normal": 0, "no_determinado": 1, "advertencia": 2, "sospecha": 3, "critico": 4}
_ESTILO = ("<style>table.ev{border-collapse:collapse;width:100%;margin:12px 0}table.ev th,table.ev td{border:1px solid #888;"
           "padding:6px 8px;text-align:left;font-size:13px}.firma{display:inline-block;width:45%;margin-top:48px;"
           "border-top:1px solid #000;padding-top:4px}pre.ev{white-space:pre-wrap;font-family:inherit}"
           ".codigo{font-family:Consolas,monospace;word-break:break-all}</style>")


def _estado_txt(e) -> str:
    return informe.ESTADOS.get(e, "Sin datos")


def _estados_de(fila: dict) -> dict:
    """{nombre legible: estado} del hardware y del análisis de Windows guardados."""
    out = {informe.NOMBRES.get(n, n): e for n, e in fila["estados"].items()}
    analisis = fila["detalle"].get("analisis")
    items = analisis.get("analisis") if isinstance(analisis, dict) else None
    for n, c in (items.items() if isinstance(items, dict) else []):
        if isinstance(c, dict):
            out[informe.NOMBRES.get(n, n)] = c.get("estado")
    return out


def comparar(fila: dict, previa: dict) -> list:
    """Cambios entre dos revisiones: [{nombre, antes, ahora, tipo}] con tipo mejoro / empeoro / nuevo / ya_no_esta; lo igual no sale."""
    antes, ahora = _estados_de(previa), _estados_de(fila)
    cambios = []
    for nombre in sorted(set(antes) | set(ahora)):
        a, b = antes.get(nombre), ahora.get(nombre)
        if a == b:
            continue
        if a is None:
            tipo = "nuevo"
        elif b is None:
            tipo = "ya_no_esta"
        else:
            tipo = "mejoro" if _PESO.get(b, 1) < _PESO.get(a, 1) else "empeoro"
        cambios.append({"nombre": nombre, "antes": a, "ahora": b, "tipo": tipo})
    return cambios


_TIPO_TXT = {"mejoro": "Mejoró", "empeoro": "Empeoró", "nuevo": "Nuevo en esta revisión", "ya_no_esta": "Ya no se revisó"}


def _tabla_cambios(cambios: list) -> str:
    if not cambios:
        return "<p>No hay diferencias de estado entre las dos revisiones.</p>"
    filas = "".join(f"<tr><td>{escape(c['nombre'])}</td><td>{escape(_estado_txt(c['antes']) if c['antes'] else '—')}</td>"
                    f"<td>{escape(_estado_txt(c['ahora']) if c['ahora'] else '—')}</td><td>{_TIPO_TXT[c['tipo']]}</td></tr>" for c in cambios)
    return f'<table class="ev"><tr><th>Componente</th><th>Antes</th><th>Ahora</th><th>Cambio</th></tr>{filas}</table>'


def acta_html(id_equipo: int):
    """Acta imprimible de un equipo guardado, o None si no existe."""
    fila = registro.obtener_fila(id_equipo)
    if fila is None:
        return None
    previa = registro.anterior(fila)
    estados = "".join(f"<tr><td>{escape(n)}</td><td>{escape(_estado_txt(e))}</td></tr>" for n, e in sorted(_estados_de(fila).items()))
    post = fila["detalle"].get("postinstalacion")
    cuerpo = [_ESTILO, "<h1>Acta de revisión de equipo</h1>",
              '<table class="ev">'
              f"<tr><th>Equipo</th><td>{escape(fila['etiqueta'])}</td><th>Fecha</th><td>{escape(fila['fecha'].replace('T', ' '))}</td></tr>"
              f"<tr><th>Responsable</th><td>{escape(fila['responsable'] or '—')}</td><th>Resultado</th><td>{escape(_estado_txt(fila['veredicto'].lower()))}</td></tr>"
              f"<tr><th>Modelo</th><td>{escape(fila['equipo'] or '—')}</td><th>Sistema</th><td>{escape(fila['sistema'] or '—')}</td></tr></table>"]
    if fila["notas"]:
        cuerpo.append(f'<h2>Notas</h2><pre class="ev">{escape(fila["notas"])}</pre>')
    cuerpo.append(f'<h2>Estado de cada componente</h2><table class="ev"><tr><th>Componente</th><th>Estado</th></tr>{estados}</table>')
    if isinstance(post, dict) and isinstance(post.get("acta"), str):
        marcadas = ", ".join(escape(str(m)) for m in post.get("marcadas", []) if isinstance(m, str)) or "ninguna"
        cuerpo.append(f'<h2>Revisión posterior a la instalación</h2><pre class="ev">{escape(post["acta"])}</pre><p>Tareas a mano marcadas: {marcadas}.</p>')
    if previa:
        cuerpo.append(f"<h2>Comparación con la revisión del {escape(previa['fecha'].replace('T', ' '))}</h2>" + _tabla_cambios(comparar(fila, previa)))
    cuerpo.append('<p><span class="firma">Técnico</span> &nbsp; <span class="firma">Responsable del equipo</span></p>')
    cuerpo.append(f'<h2>Código de integridad</h2><p class="codigo">{registro.huella(fila)}</p>'
                  "<p>Es el código SHA-256 de lo guardado en el registro. Sirve para comprobar que esta copia coincide con el registro; "
                  "no es una firma digital.</p>")
    return informe._pagina("\n".join(cuerpo))


def comparacion_html(id_equipo: int):
    """Comparación de un equipo con su revisión anterior; None si no existe, o texto de aviso si no hay anterior."""
    fila = registro.obtener_fila(id_equipo)
    if fila is None:
        return None
    previa = registro.anterior(fila)
    if previa is None:
        return informe._pagina(_ESTILO + "<h1>Comparación</h1><p>Este equipo no tiene una revisión anterior guardada con el mismo nombre.</p>")
    return informe._pagina(f"{_ESTILO}<h1>Comparación de {escape(fila['etiqueta'])}</h1>"
                           f"<p>Revisión anterior: {escape(previa['fecha'].replace('T', ' '))}. Revisión actual: {escape(fila['fecha'].replace('T', ' '))}.</p>"
                           + _tabla_cambios(comparar(fila, previa)))


def jornada_html(fecha=None) -> str:
    """Resumen de los equipos guardados en una fecha (AAAA-MM-DD; por defecto hoy)."""
    try:
        dia = datetime.date.fromisoformat(fecha).isoformat() if fecha else datetime.date.today().isoformat()
    except ValueError:
        dia = datetime.date.today().isoformat()
    filas = registro.del_dia(dia)
    cuenta = {}
    for f in filas:
        cuenta[f["veredicto"]] = cuenta.get(f["veredicto"], 0) + 1
    resumen = ", ".join(f"{escape(_estado_txt(v.lower()))}: {n}" for v, n in sorted(cuenta.items())) or "sin equipos"
    tabla = "".join(f"<tr><td>{escape(f['fecha'][11:16])}</td><td>{escape(f['etiqueta'])}</td><td>{escape(f['responsable'] or '—')}</td>"
                    f"<td>{escape(f['equipo'] or '—')}</td><td>{escape(_estado_txt(f['veredicto'].lower()))}</td></tr>" for f in filas)
    cuerpo = (f"{_ESTILO}<h1>Informe de la jornada del {escape(dia)}</h1><p>Equipos revisados: <strong>{len(filas)}</strong>. {resumen}.</p>"
              + (f'<table class="ev"><tr><th>Hora</th><th>Equipo</th><th>Responsable</th><th>Modelo</th><th>Resultado</th></tr>{tabla}</table>'
                 if filas else "<p>No hay equipos guardados en esa fecha.</p>"))
    return informe._pagina(cuerpo)
