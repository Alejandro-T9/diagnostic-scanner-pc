"""
backend/informe.py — Informe imprimible (HTML) del último escaneo, para llevar al técnico.

SEGURIDAD: todo texto que viene del escaneo (mensajes, datos como el modelo
de un disco, textos de la guía, ID) pasa por html.escape; solo los literales
fijos de este archivo (incluidos los íconos SVG) van sin escapar. El HTML es autocontenido: estilos en
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
NOMBRES.update(explicador.NOMBRES_ANALISIS)  # las tarjetas del análisis de Windows usan los mismos estilos
ESTADOS = {
    "normal": "Normal", "advertencia": "Advertencia", "sospecha": "Sospecha",
    "critico": "Crítico", "no_determinado": "Sin datos",
}

# Íconos de estado: mismas siluetas y atributos que frontend/static/js/iconos.js (una forma distinta por estado,
# legible también en blanco y negro). Cadenas FIJAS: nunca llevan datos del escaneo.
_SVG_ABRE = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" '
             'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">')


def _svg(cuerpo):
    return f"{_SVG_ABRE}{cuerpo}</svg>"


ICONOS_ESTADO = {
    "normal": _svg('<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.5"/>'),
    "advertencia": _svg('<path d="M12 3.5 21.5 20h-19z"/><path d="M12 9.8v4.2"/><path d="M12 16.8h.01"/>'),
    "sospecha": _svg('<path d="M12 2.5 21.5 12 12 21.5 2.5 12z"/><path d="M12 7.6v4.2"/><path d="M12 16.4h.01"/>'),
    "critico": _svg('<path d="M8.06 2.5h7.88L21.5 8.06v7.88l-5.56 5.56H8.06L2.5 15.94V8.06z"/><path d="M9 9l6 6M15 9l-6 6"/>'),
    "no_determinado": _svg('<circle cx="12" cy="12" r="9" stroke-dasharray="3 3.2"/>'
                           '<path d="M9.6 9.6a2.5 2.5 0 1 1 3.6 2.2c-.7.4-1.2.9-1.2 1.8"/><path d="M12 16.9h.01"/>'),
}

LIMITES = "Este informe se basa solo en lo que el programa pudo medir; no reemplaza la revisión de un técnico."

# Valores del tema CLARO de config/palette.css, copiados porque el informe no carga archivos externos
# (test_informe_estados_con_forma verifica que sigan iguales a la paleta).
_ESTILOS = """
:root {
  --color-fondo: #F4F6F9; --color-tarjeta: #FFFFFF; --color-texto: #1B2430; --color-texto-secundario: #566273;
  --color-marino: #0F2A47; --color-acento: #1F5FBF; --color-borde: #D5DBE3;
  --color-verde: #1A7F4B; --color-amarillo: #946200; --color-naranja: #B54708; --color-rojo: #B42318;
  --color-estado-normal-fondo: #EEF8F2; --color-estado-advertencia-fondo: #FEF7E6; --color-estado-sospecha-fondo: #FDF0E4;
  --color-estado-critico-fondo: #FDEDEB; --color-estado-nodeterminado-fondo: #F0F2F6;
}
.estado-normal { --e: var(--color-verde); --f: var(--color-estado-normal-fondo); }
.estado-advertencia { --e: var(--color-amarillo); --f: var(--color-estado-advertencia-fondo); }
.estado-sospecha { --e: var(--color-naranja); --f: var(--color-estado-sospecha-fondo); }
.estado-critico { --e: var(--color-rojo); --f: var(--color-estado-critico-fondo); }
.estado-no_determinado { --e: var(--color-texto-secundario); --f: var(--color-estado-nodeterminado-fondo); }
body { font-family: "Segoe UI", Arial, sans-serif; color: var(--color-texto); background: var(--color-fondo);
       max-width: 820px; margin: 24px auto; padding: 0 16px; line-height: 1.5; overflow-wrap: anywhere; }
h1 { margin: 0 0 4px 0; color: var(--color-marino); }
h2 { margin: 28px 0 8px 0; border-bottom: 1px solid var(--color-borde); padding-bottom: 4px; }
.meta { color: var(--color-texto-secundario); font-size: 14px; }
.sello { font-size: 20px; font-weight: bold; margin: 16px 0; }
.tarjeta { background: var(--color-tarjeta); border: 1px solid var(--color-borde); border-left: 6px solid var(--e, var(--color-acento));
           border-radius: 8px; padding: 10px 14px; margin: 12px 0; page-break-inside: avoid; overflow-wrap: anywhere; }
.tarjeta h3 { margin: 0 0 6px 0; font-size: 17px; }
.chip { display: inline-block; color: var(--color-texto); background: var(--f); border: 2px solid var(--e); border-radius: 12px;
        padding: 0 10px; font-size: 13px; font-weight: bold; margin-left: 8px; vertical-align: middle; }
.chip svg { width: 16px; height: 16px; vertical-align: -3px; margin-right: 4px; color: var(--e); }
.tarjeta p { margin: 4px 0; } .tarjeta ul { margin: 4px 0 4px 20px; padding: 0; }
.tarjeta details { margin: 6px 0; } .tarjeta summary { cursor: pointer; font-weight: bold; }
.limites { margin-top: 28px; font-size: 14px; color: var(--color-texto-secundario); }
@media print { .no-imprimir { display: none; } .chip, .tarjeta { -webkit-print-color-adjust: exact; print-color-adjust: exact; } body { margin: 0; max-width: none; background: #FFFFFF; } h2 { page-break-after: avoid; } }
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


def _tarjeta(nombre, comp, extra=""):
    estado = comp.get("estado")
    clave = estado if estado in ESTADOS else "no_determinado"  # un estado desconocido nunca llega a una clase CSS
    etiqueta = ESTADOS.get(estado, str(estado))
    guia = comp.get("guia") if isinstance(comp.get("guia"), dict) else None
    detalle = ""
    if guia:
        pasos = guia.get("que_hacer")
        pasos = "".join(f"<li>{escape(str(p))}</li>" for p in pasos) if isinstance(pasos, list) else ""
        normal = estado == "normal"
        quien = "No hace falta" if normal else explicador.QUIEN_TEXTO.get(guia.get("quien"), "Un técnico")
        titulo_pasos = "Para mantenerlo bien:" if normal else "Qué hacer:"
        detalle = (
            f'<p><strong>Qué significa:</strong> {escape(str(guia.get("que_significa", "")))}</p>'
            f'<p><strong>{titulo_pasos}</strong></p><ul>{pasos}</ul>'
            f'<p><strong>Quién lo hace:</strong> {escape(quien)}</p>'
        )
    return (
        f'<div class="tarjeta estado-{clave}">'
        f'<h3>{escape(NOMBRES.get(nombre, nombre))}'
        f'<span class="chip estado-{clave}">{ICONOS_ESTADO[clave]}{escape(etiqueta)}</span></h3>'
        f'<p>{escape(str(comp.get("mensaje", "")))}</p>'
        + detalle
        + extra
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
        '<div class="tarjeta">'
        f'<h3>{_texto(rec.get("titulo"))}</h3>'
        + (f'<p><strong>Prioridad: {escape(prioridad)}</strong></p>' if prioridad in ("alta", "media", "baja") else "")
        + _parrafo(rec.get("detalle"))
        + (f'<p><strong>Basado en:</strong></p><ul>{base}</ul>' if base else "")
        + detalles
        + '</div>'
    )


_MAX_FILAS = 30


def _lista_corta(filas):
    """<ul> con hasta _MAX_FILAS filas ya escapadas y 'y N más' si hay más; nada si no hay filas."""
    filas = [f for f in filas if f]
    if not filas:
        return ""
    items = "".join(f"<li>{f}</li>" for f in filas[:_MAX_FILAS])
    if len(filas) > _MAX_FILAS:
        items += f"<li>y {len(filas) - _MAX_FILAS} más</li>"
    return f"<ul>{items}</ul>"


def _nombres(valores, clave):
    return [escape(v[clave]) for v in valores if isinstance(v, dict) and isinstance(v.get(clave), str)]


def _detalle_analisis(nombre, comp):
    """Listas acotadas del detalle de cada análisis (todo texto del sistema, escapado)."""
    datos = comp.get("datos") if isinstance(comp.get("datos"), dict) else {}
    lista = lambda clave: datos.get(clave) if isinstance(datos.get(clave), list) else []
    if nombre == "inicio":
        activas = [e for e in lista("entradas") if isinstance(e, dict) and e.get("habilitado", True)]
        return "<p><strong>Se abren al encender:</strong></p>" + _lista_corta(_nombres(activas, "nombre"))
    if nombre == "programas":
        ocultos = [p for p in lista("programas") if isinstance(p, dict) and p.get("oculto")]
        recientes = [escape(n) for n in lista("recientes_sin_editor") if isinstance(n, str)]
        return (("<p><strong>Recientes sin editor conocido:</strong></p>" + _lista_corta(recientes) if recientes else "")
                + ("<p><strong>Ocultos por Windows:</strong></p>" + _lista_corta(_nombres(ocultos, "nombre")) if ocultos else ""))
    if nombre == "rendimiento":
        causas = [
            escape(c["titulo"]) + (" — " + escape("; ".join(e for e in c["evidencia"] if isinstance(e, str)))
                                   if isinstance(c.get("evidencia"), list) else "")
            for c in lista("causas") if isinstance(c, dict) and isinstance(c.get("titulo"), str)
        ]
        procesos = [
            f"{escape(p['nombre'])} ({p['cpu']:.0f} % CPU)" for p in lista("procesos_cpu")
            if isinstance(p, dict) and isinstance(p.get("nombre"), str) and isinstance(p.get("cpu"), (int, float))
        ]
        return (("<p><strong>Posibles causas:</strong></p>" + _lista_corta(causas) if causas else "")
                + ("<p><strong>Procesos que más procesador usan:</strong></p>" + _lista_corta(procesos) if procesos else ""))
    if nombre == "espacio":
        carpetas = [
            f"{escape(c['nombre'])}: {c['tamano_gb']} GB" for c in lista("carpetas")
            if isinstance(c, dict) and isinstance(c.get("nombre"), str) and isinstance(c.get("tamano_gb"), (int, float))
        ]
        return "<p><strong>Dónde se va el espacio:</strong></p>" + _lista_corta(carpetas) if carpetas else ""
    return ""


def _bloque_analisis(analisis):
    items = analisis.get("analisis") if isinstance(analisis, dict) else None
    if not isinstance(items, dict) or not items:
        return ""
    tarjetas = "".join(
        _tarjeta(nombre, items[nombre], _detalle_analisis(nombre, items[nombre]))
        for nombre in scanner.ANALISIS if isinstance(items.get(nombre), dict)
    )
    if not tarjetas:
        return ""
    return '<h2>Análisis de Windows</h2><p class="meta">Es una foto del momento; solo lee información.</p>' + tarjetas


def generar_informe_html(resultado, veredicto, analisis=None):
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
        + _bloque_analisis(analisis)
        + '<h2>Preguntas para tu técnico</h2>' + bloque_preguntas
        + f'<p class="limites">{LIMITES}</p>'
    )
    return _pagina(cuerpo)
