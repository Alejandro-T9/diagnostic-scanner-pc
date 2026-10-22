"""
backend/informe.py — Informe imprimible (HTML) del último escaneo, para llevar al técnico.

SEGURIDAD: todo texto que viene del escaneo (mensajes, datos como el modelo
de un disco, textos de la guía, ID) pasa por html.escape; solo los literales
fijos de este archivo van sin escapar. El HTML es autocontenido: estilos en
línea, sin JS ni recursos externos (debe verse igual sin internet).
"""

from datetime import datetime
from html import escape

import explicador
import scanner

NOMBRES = {
    "mainboard": "Tarjeta Madre", "cpu": "Procesador", "ram": "Memoria RAM",
    "almacenamiento": "Almacenamiento", "fuente_poder": "Fuente de Poder",
    "bateria": "Batería", "red": "Red",
}
ESTADOS = {
    "normal": ("Normal", "#3FB950"), "advertencia": ("Advertencia", "#D29922"),
    "sospecha": ("Sospecha", "#DB6D28"), "critico": ("Crítico", "#F85149"),
    "no_determinado": ("No determinado", "#8B949E"),
}

LIMITES = "Este informe se basa solo en lo que el programa pudo medir; no reemplaza la revisión de un técnico."

_ESTILOS = """
body { font-family: "Segoe UI", Arial, sans-serif; color: #1F2328; background: #FFFFFF;
       max-width: 820px; margin: 24px auto; padding: 0 16px; line-height: 1.5; overflow-wrap: anywhere; }
h1 { margin: 0 0 4px 0; } h2 { margin: 28px 0 8px 0; border-bottom: 1px solid #D0D7DE; padding-bottom: 4px; }
.meta { color: #57606A; font-size: 14px; }
.sello { font-size: 20px; font-weight: bold; margin: 16px 0; }
.tarjeta { border: 1px solid #D0D7DE; border-left-width: 6px; border-radius: 6px;
           padding: 10px 14px; margin: 12px 0; page-break-inside: avoid; overflow-wrap: anywhere; }
.tarjeta h3 { margin: 0 0 6px 0; font-size: 17px; }
.chip { display: inline-block; color: #1F2328; background: #FFFFFF; border: 2px solid; border-radius: 12px;
        padding: 0 10px; font-size: 13px; font-weight: bold; margin-left: 8px; vertical-align: middle; }
.tarjeta p { margin: 4px 0; } .tarjeta ul { margin: 4px 0 4px 20px; padding: 0; }
.tarjeta details { margin: 6px 0; } .tarjeta summary { cursor: pointer; font-weight: bold; }
.limites { margin-top: 28px; font-size: 14px; color: #57606A; }
@media print { .no-imprimir { display: none; } .chip, .tarjeta { -webkit-print-color-adjust: exact; print-color-adjust: exact; } body { margin: 0; max-width: none; } h2 { page-break-after: avoid; } }
"""


def _fecha_local(ts):
    """ISO UTC -> 'dd/mm/aaaa HH:MM' en hora local; si no se puede, el texto original (escapado)."""
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return escape(str(ts))


def _pagina(cuerpo):
    return ('<!DOCTYPE html>\n<html lang="es">\n<head>\n<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>Informe de diagnóstico</title>\n<style>{_ESTILOS}</style>\n</head>\n'
            f'<body>\n{cuerpo}\n</body>\n</html>')


def _tarjeta(nombre, comp):
    etiqueta, color = ESTADOS.get(comp.get("estado"), (str(comp.get("estado")), "#8B949E"))
    guia = comp.get("guia") if isinstance(comp.get("guia"), dict) else None
    detalle = ""
    if guia:
        pasos = guia.get("que_hacer")
        pasos = "".join(f"<li>{escape(str(p))}</li>" for p in pasos) if isinstance(pasos, list) else ""
        normal = comp.get("estado") == "normal"
        quien = "No hace falta" if normal else explicador.QUIEN_TEXTO.get(guia.get("quien"), "Un técnico")
        titulo_pasos = "Para mantenerlo bien:" if normal else "Qué hacer:"
        detalle = (
            f'<p><strong>Qué significa:</strong> {escape(str(guia.get("que_significa", "")))}</p>'
            f'<p><strong>{titulo_pasos}</strong></p><ul>{pasos}</ul>'
            f'<p><strong>Quién lo hace:</strong> {escape(quien)}</p>'
        )
    return (
        f'<div class="tarjeta" style="border-left-color:{color}">'
        f'<h3>{escape(NOMBRES.get(nombre, nombre))}'
        f'<span class="chip" style="border-color:{color}">{escape(etiqueta)}</span></h3>'
        f'<p>{escape(str(comp.get("mensaje", "")))}</p>'
        + detalle
        + '</div>'
    )


def _texto(valor):
    """Texto escapado de un campo del escaneo; vacío si no es str."""
    return escape(valor) if isinstance(valor, str) else ""


def _parrafo(valor):
    """<p> con el texto escapado; nada si está vacío (evita <p></p> con margen)."""
    texto = _texto(valor)
    return f"<p>{texto}</p>" if texto else ""


def _recomendacion(rec):
    if not isinstance(rec, dict):
        return ""
    prioridad = rec.get("prioridad")
    base = rec.get("basado_en")
    base = "".join(f"<li>{escape(b)}</li>" for b in base if isinstance(b, str)) if isinstance(base, list) else ""
    opciones = rec.get("opciones")
    opciones = [o for o in opciones if isinstance(o, dict) and isinstance(o.get("nombre"), str)] \
        if isinstance(opciones, list) else []
    # <details open>: el informe no tiene JS y al imprimir debe verse el texto de cada opción.
    detalles = "".join(
        f'<details open><summary>{escape(o["nombre"])}</summary>'
        f'{_parrafo(o.get("motivo"))}{_parrafo(o.get("nota"))}</details>'
        for o in opciones
    )
    return (
        '<div class="tarjeta" style="border-left-color:#0969DA">'
        f'<h3>{_texto(rec.get("titulo"))}</h3>'
        + (f'<p><strong>Prioridad: {escape(prioridad)}</strong></p>' if prioridad in ("alta", "media", "baja") else "")
        + _parrafo(rec.get("detalle"))
        + (f'<p><strong>Basado en:</strong></p><ul>{base}</ul>' if base else "")
        + detalles
        + '</div>'
    )


def generar_informe_html(resultado, veredicto):
    """Documento HTML completo del escaneo; página amable si no hay escaneo."""
    if not resultado or not resultado.get("componentes"):
        return _pagina(
            '<h1>Informe de diagnóstico</h1>'
            '<p>Aún no hay un escaneo. Vuelve al panel y pulsa «Revisar mi PC».</p>'
        )
    comps = resultado["componentes"]
    orden = {e: i for i, e in enumerate(scanner._SEVERIDAD)}
    ordenados = sorted(comps.items(), key=lambda kv: orden.get(kv[1].get("estado"), len(orden)))

    datos_mb = (comps.get("mainboard") or {}).get("datos")
    datos_mb = datos_mb if isinstance(datos_mb, dict) else {}
    equipo = " ".join(str(datos_mb[k]) for k in ("fabricante", "modelo") if datos_mb.get(k))
    sello = explicador.FRASES_VEREDICTO.get(veredicto, veredicto)

    preguntas = [
        (nombre, (c["guia"].get("pregunta_tecnico", "") if isinstance(c.get("guia"), dict) else ""))
        for nombre, c in ordenados if c.get("estado") != "normal"
    ]
    preguntas = [(n, p) for n, p in preguntas if p]
    if preguntas:
        lista = "".join(
            f"<li><strong>{escape(NOMBRES.get(n, n))}:</strong> {escape(p)}</li>" for n, p in preguntas
        )
        bloque_preguntas = f"<ul>{lista}</ul>"
    else:
        if any(c.get("estado") != "normal" for c in comps.values()):
            bloque_preguntas = "<p>No hay preguntas sugeridas para este informe.</p>"
        else:
            bloque_preguntas = "<p>No hacen falta preguntas: todo está normal.</p>"

    recs = resultado.get("recomendaciones")
    recs = "".join(_recomendacion(r) for r in recs) if isinstance(recs, list) else ""
    bloque_recs = f"<h2>Recomendaciones para tu equipo</h2>{recs}" if recs else ""

    cuerpo = (
        '<h1>Informe de diagnóstico</h1>'
        f'<div class="meta">ID: {escape(str(resultado.get("id_diagnostico", "")))} · '
        f'Fecha: {_fecha_local(resultado.get("timestamp", ""))}</div>'
        '<p class="no-imprimir">Para imprimirlo o guardarlo como PDF, pulsa Ctrl+P.</p>'
        + (f'<div class="meta">Equipo: {escape(equipo)}</div>' if equipo else "")
        + f'<div class="sello">{escape(str(sello))}</div>'
        '<div class="meta">Según lo que el programa pudo medir.</div>'
        + "".join(_tarjeta(n, c) for n, c in ordenados)
        + bloque_recs
        + '<h2>Preguntas para tu técnico</h2>' + bloque_preguntas
        + f'<p class="limites">{LIMITES}</p>'
    )
    return _pagina(cuerpo)
