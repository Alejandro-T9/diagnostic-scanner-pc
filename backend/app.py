"""
backend/app.py — Servidor Flask principal de Diagnostic Scanner PC.

Expone el dashboard (HTML) y la API REST (JSON) que el frontend consulta
por polling cada 2 segundos. Este archivo es solo la capa de enrutamiento:
la lógica de diagnóstico vive en scanner.py y las funciones de apoyo
(ejecutar comandos, leer estado del sistema) en utils.py.
"""

import os
import sys

# El Python portable embeddable (build/python-portable/) trae un
# python312._pth que desactiva el agregado automático de la carpeta del
# script a sys.path — sin esto, "import scanner"/"import utils" fallan
# con ModuleNotFoundError apenas se corre desde ese Python (no pasa con
# un Python normal de sistema, por eso no se vio hasta probar en WinPE).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import pythoncom
from flask import Flask, Response, jsonify, render_template, request, send_from_directory

import scanner
import utils

FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")
CONFIG_DIR = os.path.join(BASE_DIR, "..", "config")

# Último resultado de /api/scan, en memoria (no se persiste en disco: ver
# decisión "Persistencia: stateless" en docs/DECISIONES.md). Lo usa
# /api/reporte para no tener que re-escanear solo para descargar el texto.
_ultimo_escaneo = None

app = Flask(
    __name__,
    template_folder=os.path.join(FRONTEND_DIR, "templates"),
    static_folder=os.path.join(FRONTEND_DIR, "static"),
)


@app.before_request
def _inicializar_com():
    """WMI usa COM por debajo, y COM se inicializa por hilo del sistema
    operativo, no por proceso. El servidor de Flask atiende cada request
    en su propio hilo (no el principal, donde sí queda inicializado
    "gratis"), así que sin esto cada consulta WMI de cada módulo falla
    con wmi.x_wmi_uninitialised_thread apenas se corre el servidor real
    (no se ve en pruebas directas de un script porque esas sí corren en
    el hilo principal)."""
    pythoncom.CoInitialize()


@app.teardown_request
def _liberar_com(exception=None):
    pythoncom.CoUninitialize()


@app.route("/")
def index():
    """Sirve el dashboard principal. index.html se implementa en una fase posterior."""
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    """Devuelve timestamp, herramientas de diagnóstico disponibles y espacio en disco."""
    try:
        return jsonify({
            "timestamp": utils.obtener_timestamp(),
            "herramientas_disponibles": utils.verificar_herramientas(),
            "espacio_disco": utils.obtener_espacio_disco(),
        })
    except Exception as error:
        return jsonify({
            "estado": "error",
            "mensaje": f"No se pudo obtener el estado del sistema: {error}",
        }), 500


@app.route("/config/<path:archivo>")
def config_estatico(archivo):
    """Sirve config/ por HTTP (ej. palette.css) para que style.css pueda importarlo."""
    return send_from_directory(CONFIG_DIR, archivo)


@app.route("/api/scan")
def api_scan():
    """Dispara el escaneo completo de hardware y devuelve el resultado preliminar."""
    global _ultimo_escaneo
    try:
        resultado = scanner.ejecutar_escaneo_completo()
        _ultimo_escaneo = resultado
        return jsonify(resultado)
    except Exception as error:
        return jsonify({
            "estado": "error",
            "mensaje": f"No se pudo completar el escaneo: {error}",
        }), 500


@app.route("/api/reporte")
def api_reporte():
    """Exporta el último escaneo como texto plano descargable. No persiste
    nada en disco: se arma al vuelo a partir de _ultimo_escaneo en memoria."""
    veredicto = scanner.clasificar_equipo(_ultimo_escaneo) if _ultimo_escaneo else "SIN_DATOS"
    texto = utils.generar_reporte_texto(_ultimo_escaneo, veredicto)
    return Response(
        texto,
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=reporte_diagnostico.txt"},
    )


_PLANTILLA_ERROR_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>__TITULO__</title>
    <style>
        body {
            background-color: #0D1117;
            color: #E6EDF3;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            margin: 0;
        }
        .tarjeta-error {
            background-color: #161B22;
            border-radius: 8px;
            padding: 32px 40px;
            max-width: 480px;
            text-align: center;
        }
        .codigo {
            font-size: 48px;
            font-weight: bold;
            margin: 0 0 8px 0;
            color: __COLOR__;
        }
        .mensaje {
            color: #E6EDF3;
            margin: 0 0 16px 0;
        }
        a {
            color: #58A6FF;
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="tarjeta-error">
        <p class="codigo">__CODIGO__</p>
        <p class="mensaje">__MENSAJE__</p>
        <p><a href="/">Volver al panel principal</a></p>
    </div>
</body>
</html>"""


def _pagina_error(codigo, titulo, mensaje):
    """Arma una página de error en modo oscuro con la paleta exacta del proyecto."""
    color = "#F85149" if codigo >= 500 else "#D29922"
    html = _PLANTILLA_ERROR_HTML.replace("__TITULO__", titulo)
    html = html.replace("__CODIGO__", str(codigo))
    html = html.replace("__MENSAJE__", mensaje)
    return html.replace("__COLOR__", color)


@app.errorhandler(404)
def error_404(error):
    """Ruta no encontrada: JSON si es /api/*, página oscura en el resto de rutas."""
    if request.path.startswith("/api/"):
        return jsonify({"estado": "error", "mensaje": "Recurso no encontrado"}), 404
    return _pagina_error(404, "No encontrado", "La página que buscas no existe."), 404


@app.errorhandler(500)
def error_500(error):
    """Error interno: JSON si es /api/*, página oscura en el resto de rutas.

    NOTA TÉCNICA: con debug=True, Werkzeug muestra su depurador interactivo
    para excepciones no controladas y este manejador NO se activa en ese
    caso (es el comportamiento normal de Flask en desarrollo). Sí se activa
    para errores 500 explícitos (abort(500)) y funcionará siempre una vez
    se use debug=False en la build final para la USB.
    """
    if request.path.startswith("/api/"):
        return jsonify({"estado": "error", "mensaje": "Error interno del servidor"}), 500
    return _pagina_error(500, "Error interno", "Ocurrió un error inesperado en el servidor."), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)