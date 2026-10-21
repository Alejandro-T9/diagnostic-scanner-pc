"""
backend/lanzador.py — Arranque de Diagnostic Scanner PC en una ventana propia.

Levanta el servidor Flask en un puerto libre de 127.0.0.1, abre la app en
una ventana de Edge/Chrome sin barra de direcciones (modo --app) y apaga
todo cuando la ventana se cierra. Para saber que la ventana sigue abierta
usa como latido el polling de /api/status que hace el frontend cada 2 s:
si deja de llegar, el lanzador termina solo.

Uso: python lanzador.py [--sin-navegador]
"""

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Mapping

# El Python embeddable del USB ignora la carpeta del script (python312._pth),
# así que se agrega BASE_DIR a mano, igual que en app.py.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from flask import request
from werkzeug.serving import make_server

import app
import utils

PUERTO_PREFERIDO = 5000
ESPERA_SERVIDOR_S = 30.0

# Rutas relativas de cada navegador, y de qué variables de entorno cuelgan,
# en orden de preferencia (Edge viene con Windows, así que va primero).
_EDGE = os.path.join("Microsoft", "Edge", "Application", "msedge.exe")
_CHROME = os.path.join("Google", "Chrome", "Application", "chrome.exe")
_CANDIDATOS = (
    ("ProgramFiles(x86)", _EDGE),
    ("ProgramFiles", _EDGE),
    ("ProgramFiles", _CHROME),
    ("ProgramFiles(x86)", _CHROME),
    ("LocalAppData", _CHROME),
)


def elegir_navegador(variables: Mapping[str, str], existe=os.path.exists) -> str | None:
    """Devuelve la ruta del primer Edge/Chrome instalado, o None si no hay.

    `variables` es un mapeo tipo os.environ y `existe` se inyecta para
    poder probar sin tocar el disco. Variables ausentes se saltan.
    """
    for variable, relativa in _CANDIDATOS:
        base = variables.get(variable)
        if not base:
            continue
        ruta = os.path.join(base, relativa)
        if existe(ruta):
            return ruta
    return None


def comando_app(exe: str, url: str, perfil: str) -> list[str]:
    """Línea de comando para abrir `url` como ventana de aplicación.

    El perfil propio (--user-data-dir) fuerza una instancia nueva: sin él,
    Edge delegaría en un proceso ya abierto y terminaría al instante.
    """
    return [
        exe,
        f"--app={url}",
        f"--user-data-dir={perfil}",
        "--no-first-run",
        "--window-size=1280,800",
    ]


def debe_apagar(
    ahora: float,
    ultimo_latido: float | None,
    inicio: float,
    tolerancia_s: float = 150.0,
    gracia_inicial_s: float = 60.0,
) -> bool:
    """Decide si el lanzador debe terminar por falta de latido.

    Sin ningún latido todavía se espera `gracia_inicial_s` desde el inicio;
    con latido, se tolera `tolerancia_s` de silencio. 150 s porque Chromium
    frena los temporizadores de una ventana minimizada u oculta.
    """
    if ultimo_latido is None:
        return ahora - inicio > gracia_inicial_s
    return ahora - ultimo_latido > tolerancia_s


def abrir_ventana(exe: str, url: str, perfil: str, popen=subprocess.Popen, abrir_web=webbrowser.open) -> None:
    """Lanza la ventana --app; si el exe no se puede ejecutar, usa el navegador por defecto."""
    try:
        popen(comando_app(exe, url, perfil))
    except OSError:
        print("No se pudo abrir la ventana de aplicación: usando el navegador por defecto.", flush=True)
        abrir_web(url)


def _esperar_servidor(url: str, timeout_s: float = ESPERA_SERVIDOR_S) -> bool:
    """Sondea /api/status cada 0.3 s hasta que responda; False si se agota."""
    # Sin proxy: uno configurado en Windows puede tragarse las peticiones a 127.0.0.1.
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    limite = time.monotonic() + timeout_s
    while time.monotonic() < limite:
        try:
            with abridor.open(url + "/api/status", timeout=2) as respuesta:
                if respuesta.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.3)
    return False


def main(argv: list[str] | None = None) -> int:
    """Levanta el servidor, abre la ventana y vigila el latido. Devuelve el código de salida."""
    argv = sys.argv[1:] if argv is None else argv
    sin_navegador = "--sin-navegador" in argv

    ultimo_latido: list[float | None] = [None]

    @app.app.after_request
    def _marcar_latido(respuesta):
        if request.path == "/api/status":
            ultimo_latido[0] = time.monotonic()
        return respuesta

    puerto = utils.puerto_libre(PUERTO_PREFERIDO)
    url = f"http://{app.HOST}:{puerto}"
    servidor = make_server(app.HOST, puerto, app.app, threaded=True)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    inicio = time.monotonic()
    hilo.start()

    perfil = None
    try:
        if not _esperar_servidor(url):
            print("Error: el servidor no respondió a tiempo.", file=sys.stderr)
            return 1
        print(f"Diagnostic Scanner PC en {url}", flush=True)
        # El sondeo de arranque marcó un latido: se descarta para que la gracia
        # inicial (60 s) cuente desde que se lanza el navegador.
        ultimo_latido[0] = None
        inicio = time.monotonic()

        if not sin_navegador:
            exe = elegir_navegador(os.environ)
            if exe:
                perfil = tempfile.mkdtemp(prefix="dspc_perfil_")
                abrir_ventana(exe, url, perfil)
            else:
                webbrowser.open(url)

        while hilo.is_alive():
            time.sleep(1)
            if debe_apagar(time.monotonic(), ultimo_latido[0], inicio):
                print("Ventana cerrada: apagando.", flush=True)
                break
    except KeyboardInterrupt:
        pass
    finally:
        servidor.shutdown()
        hilo.join(timeout=5)
        if perfil:
            shutil.rmtree(perfil, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
