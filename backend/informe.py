"""
backend/informe.py — Informe imprimible (HTML) del último escaneo, para llevar al técnico.

SEGURIDAD: todo texto que viene del escaneo (mensajes, datos como el modelo
de un disco, textos de la guía, ID) pasa por html.escape; solo los literales
fijos de este archivo van sin escapar. El HTML es autocontenido: estilos en
línea, sin JS ni recursos externos (debe verse igual sin internet).
"""

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
QUIEN = {"tu_mismo": "Tú mismo", "tecnico": "Un técnico", "nadie": "Nadie"}

LIMITES = "Este informe se basa solo en lo que el programa pudo medir; no reemplaza la revisión de un técnico."

_ESTILOS = """
body { font-family: "Segoe UI", Arial, sans-serif; color: #1F2328; background: #FFFFFF;
       max-width: 820px; margin: 24px auto; padding: 0 16px; line-height: 1.5; }
h1 { margin: 0 0 4px 0; } h2 { margin: 28px 0 8px 0; border-bottom: 1px solid #D0D7DE; padding-bottom: 4px; }
.meta { color: #57606A; font-size: 14px; }
.sello { font-size: 20px; font-weight: bold; margin: 16px 0; }
.tarjeta { border: 1px solid #D0D7DE; border-left-width: 6px; border-radius: 6px;
           padding: 10px 14px; margin: 12px 0; page-break-inside: avoid; }
.tarjeta h3 { margin: 0 0 6px 0; font-size: 17px; }
.chip { display: inline-block; color: #FFFFFF; border-radius: 12px; padding: 1px 10px;
        font-size: 13px; margin-left: 8px; vertical-align: middle; }
.tarjeta p { margin: 4px 0; } .tarjeta ul { margin: 4px 0 4px 20px; padding: 0; }
.limites { margin-top: 28px; font-size: 14px; color: #57606A; }
@media print { body { margin: 0; max-width: none; } h2 { page-break-after: avoid; } }
"""


def _pagina(cuerpo):
    return ('<!DOCTYPE html>\n<html lang="es">\n<head>\n<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<title>Informe de diagnóstico</title>\n<style>{_ESTILOS}</style>\n</head>\n'
            f'<body>\n{cuerpo}\n</body>\n</html>')


def _tarjeta(nombre, comp):
    etiqueta, color = ESTADOS.get(comp.get("estado"), (str(comp.get("estado")), "#8B949E"))
    guia = comp.get("guia") or {}
    pasos = "".join(f"<li>{escape(str(p))}</li>" for p in guia.get("que_hacer", []))
    return (
        f'<div class="tarjeta" style="border-left-color:{color}">'
        f'<h3>{escape(NOMBRES.get(nombre, nombre))}'
        f'<span class="chip" style="background:{color}">{escape(etiqueta)}</span></h3>'
        f'<p>{escape(str(comp.get("mensaje", "")))}</p>'
        f'<p><strong>Qué significa:</strong> {escape(str(guia.get("que_significa", "")))}</p>'
        f'<p><strong>Qué hacer:</strong></p><ul>{pasos}</ul>'
        f'<p><strong>Quién lo hace:</strong> {escape(QUIEN.get(guia.get("quien"), "Un técnico"))}</p>'
        '</div>'
    )


def generar_informe_html(resultado, veredicto):
    """Documento HTML completo del escaneo; página amable si no hay escaneo."""
    if not resultado or not resultado.get("componentes"):
        return _pagina(
            '<h1>Informe de diagnóstico</h1>'
            '<p>Aún no hay un escaneo. Vuelve al panel y pulsa «Escanear Sistema».</p>'
        )
    comps = resultado["componentes"]
    orden = {e: i for i, e in enumerate(scanner._SEVERIDAD)}
    ordenados = sorted(comps.items(), key=lambda kv: orden.get(kv[1].get("estado"), len(orden)))

    datos_mb = (comps.get("mainboard") or {}).get("datos") or {}
    equipo = " ".join(str(datos_mb[k]) for k in ("fabricante", "modelo") if datos_mb.get(k))
    sello = explicador.FRASES_VEREDICTO.get(veredicto, veredicto)

    preguntas = [
        (nombre, (c.get("guia") or {}).get("pregunta_tecnico", ""))
        for nombre, c in ordenados if c.get("estado") != "normal"
    ]
    preguntas = [(n, p) for n, p in preguntas if p]
    if preguntas:
        lista = "".join(
            f"<li><strong>{escape(NOMBRES.get(n, n))}:</strong> {escape(p)}</li>" for n, p in preguntas
        )
        bloque_preguntas = f"<ul>{lista}</ul>"
    else:
        bloque_preguntas = ("<p>No hacen falta preguntas: todo lo que se pudo medir está normal.</p>")

    cuerpo = (
        '<h1>Informe de diagnóstico</h1>'
        f'<div class="meta">ID: {escape(str(resultado.get("id_diagnostico", "")))} · '
        f'Fecha: {escape(str(resultado.get("timestamp", "")))}</div>'
        + (f'<div class="meta">Equipo: {escape(equipo)}</div>' if equipo else "")
        + f'<div class="sello">{escape(str(sello))}</div>'
        + "".join(_tarjeta(n, c) for n, c in ordenados)
        + '<h2>Preguntas para tu técnico</h2>' + bloque_preguntas
        + f'<p class="limites">{LIMITES}</p>'
    )
    return _pagina(cuerpo)
