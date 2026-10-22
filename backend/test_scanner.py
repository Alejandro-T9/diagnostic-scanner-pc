"""
backend/test_scanner.py — Suite de regresión de la lógica de clasificación.

Mismo estilo que modules/gpu.py::_demo(): asserts simples, sin pytest ni
fixtures — el proyecto no tiene un framework de test como dependencia y
no hace falta agregar uno para esto. Corre con: python test_scanner.py

Cubre dos cosas distintas:
1. Que cada módulo clasifique cada caso conocido en el estado correcto
   (regresión: un cambio futuro que rompa esto se nota acá, no en
   producción ni en la sustentación).
2. Que scanner.py sea internamente consistente (ESTADOS_VALIDOS/
   _SEVERIDAD/COMPONENTES no se desincronizan entre sí) y que el
   veredicto global priorice evidencia real por sobre datos ausentes
   (decisión 22 en docs/DECISIONES.md) — sin depender de hardware real,
   con datos simulados.

No reemplaza la verificación en hardware real (ver DECISIONES.md): esto
prueba la LÓGICA de clasificación, no que WMI/LibreHardwareMonitor
devuelvan lo que se espera en una laptop concreta.
"""

import contextlib
import datetime
import winreg
import io
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time

import app
import equipo
import explicador
import lanzador
import recomendador
import scanner
import utils
from analisis import espacio, inicio, programas, rendimiento
from modules import _lhm, almacenamiento, bateria, cpu, fuente_poder, gpu, mainboard, ram, red


def _assert_estado(nombre_caso, obtenido, esperado):
    assert obtenido == esperado, f"{nombre_caso}: se esperaba '{esperado}', dio '{obtenido}'"


def test_ram():
    _assert_estado("RAM uso normal", ram._clasificar(50.0)[0], "normal")
    _assert_estado("RAM uso alto", ram._clasificar(87.0)[0], "advertencia")
    _assert_estado("RAM uso crítico", ram._clasificar(97.0)[0], "critico")


def test_bateria():
    _assert_estado("Batería sana", bateria._clasificar(90.0)[0], "normal")
    _assert_estado("Batería degradada (crítico)", bateria._clasificar(30.0)[0], "critico")
    _assert_estado("Batería sin dato de capacidad", bateria._clasificar(None)[0], "no_determinado")
    # capacidad_actual en 0 es un dato real (batería completamente muerta,
    # el peor caso posible) — no debe convertirse en None solo por ser
    # falsy en Python, como si no se hubiera podido leer.
    _assert_estado("Salud con capacidad actual en 0 (batería muerta)", bateria._calcular_salud(0, 5000), 0.0)
    assert bateria._calcular_salud(None, 5000) is None, "capacidad actual ausente sí debe dar None"
    assert bateria._calcular_salud(4000, 0) is None, "capacidad de diseño en 0 no es un dato real, evita división por cero"


def test_almacenamiento():
    interno_sano = {"modelo": "SSD-SANO", "externo": False, "salud": "normal"}
    interno_sospechoso = {"modelo": "SSD-SOSPECHA", "externo": False, "salud": "sospecha"}

    _assert_estado("Disco interno sano", almacenamiento._clasificar([interno_sano])[0], "normal")
    _assert_estado("Disco interno degradado", almacenamiento._clasificar([interno_sospechoso])[0], "sospecha")
    # _clasificar() solo recibe "internos" — diagnosticar() ya separó los
    # discos USB antes de llamarla (decisión 20). Por eso una lista vacía
    # es exactamente lo que pasaría con un equipo donde solo hay USB
    # conectado: no hay forma de que un externo "se cuele" acá, la firma
    # de la función no lo permite.
    _assert_estado("Sin discos internos (solo USB, si lo hay)", almacenamiento._clasificar([])[0], "no_determinado")


def test_cpu():
    _assert_estado("CPU temperatura normal", cpu._clasificar("CPU", 50.0)[0], "normal")
    _assert_estado("CPU temperatura elevada", cpu._clasificar("CPU", 75.0)[0], "advertencia")
    _assert_estado("CPU temperatura crítica", cpu._clasificar("CPU", 90.0)[0], "critico")
    estado, mensaje = cpu._clasificar("CPU", None)
    _assert_estado("CPU sin sensor de temperatura", estado, "no_determinado")
    assert "normal" not in mensaje.lower(), "el mensaje de no_determinado no debe sonar a 'todo bien'"
    # Caso real visto en producción (reporte 2026-08-21): un sensor ausente
    # que WMI reporta como 0 crudo se convierte en -273.15°C (cero
    # absoluto) al aplicar el offset — sin límite inferior, ese valor caía
    # en "normal" por no superar ningún umbral.
    estado, _ = cpu._clasificar("CPU", -273.15)
    _assert_estado("CPU temperatura físicamente imposible (sensor placeholder)", estado, "no_determinado")


def test_mainboard():
    # "Desconocido" es el propio valor de relleno que este módulo usa
    # (_armar_datos) cuando WMI no devuelve fabricante/modelo — si
    # _es_placeholder no lo reconoce, un dato ausente se reporta como
    # "normal" en vez de "advertencia".
    assert mainboard._es_placeholder("Desconocido") is True, "el propio fallback del módulo debe reconocerse como placeholder"
    assert mainboard._es_placeholder("To Be Filled By O.E.M.") is True
    assert mainboard._es_placeholder("") is True
    assert mainboard._es_placeholder("LENOVO") is False, "un fabricante real no debe marcarse como placeholder"


def test_red():
    con_link = {"nombre": "Ethernet", "link_activo": True, "velocidad_mbps": 1000, "errores_rx": 0}
    con_errores = {"nombre": "WiFi", "link_activo": True, "velocidad_mbps": 100, "errores_rx": 5}
    sin_dato_errores = {"nombre": "Ethernet", "link_activo": True, "velocidad_mbps": 1000, "errores_rx": None}
    sin_link = {"nombre": "Ethernet", "link_activo": False, "velocidad_mbps": None, "errores_rx": None}

    _assert_estado("Enlace activo sin errores confirmados", red._clasificar([con_link])[0], "normal")
    _assert_estado("Enlace activo con errores reales", red._clasificar([con_errores])[0], "sospecha")
    # Decisión 36: sin enlace es ADVERTENCIA (Wi-Fi apagado o sin cable no es "problema serio").
    _assert_estado("Ningún enlace activo", red._clasificar([sin_link])[0], "advertencia")
    # La red ya no puede dar "critico" con ninguna combinación de interfaces.
    for combo in ([sin_link], [con_link], [con_errores], [sin_dato_errores], [sin_link, con_link],
                  [sin_link, con_errores], [sin_link, sin_dato_errores], [con_link, con_errores]):
        assert red._clasificar(combo)[0] != "critico", combo
    # Conteo de errores no leído (None) no es lo mismo que "0 errores
    # confirmados" — antes `or 0` los trataba igual y el enlace salía
    # "normal" sin haber verificado nada.
    _assert_estado("Enlace activo, conteo de errores no disponible", red._clasificar([sin_dato_errores])[0], "no_determinado")


def test_gpu_sensores():
    # Mismos 3 escenarios de la revisión externa que motivó separar
    # _elegir_uso() de _telemetria() en gpu.py (decisión 22).
    assert gpu._elegir_uso([("GPU Core", 42), ("D3D 3D", 18)]) == 42.0
    assert gpu._elegir_uso([("GPU Core", 217), ("D3D 3D", 20)]) is None, "GPU Core corrupto no debe caer a D3D 3D"
    assert gpu._elegir_uso([("D3D 3D", 20)]) is None, "sin GPU Core no debe caer a un motor individual"


def test_gpu_aislamiento():
    # gpu.obtener_datos() es auxiliar de cpu.py y promete no lanzar nunca:
    # si falla identidad o telemetría, solo ese lado se degrada a None.
    def _boom():
        raise RuntimeError("boom")

    identidad_orig, telemetria_orig = gpu._identidad, gpu._telemetria
    try:
        gpu._identidad = _boom
        gpu._telemetria = lambda: (55.0, 12.0)
        datos = gpu.obtener_datos()
        assert datos == {"nombre": None, "driver": None, "temperatura_c": 55.0, "porcentaje_uso": 12.0}, datos

        gpu._identidad = lambda: ("GPU X", "1.2.3")
        gpu._telemetria = _boom
        datos = gpu.obtener_datos()
        assert datos == {"nombre": "GPU X", "driver": "1.2.3", "temperatura_c": None, "porcentaje_uso": None}, datos
    finally:
        gpu._identidad, gpu._telemetria = identidad_orig, telemetria_orig


def _sensor(tipo_hardware, tipo, nombre, valor):
    return {"tipo_hardware": tipo_hardware, "hardware": f"{tipo_hardware} X", "tipo": tipo, "nombre": nombre, "valor": valor}


def test_lhm():
    # (a) Caché: el lector real se invoca una sola vez por escaneo, no una
    # vez por módulo — esa es la razón de ser de _lhm.
    llamadas = []

    def _lector():
        llamadas.append(1)
        return [_sensor("Cpu", "Voltage", "Core #1 VID", 1.1)]

    _lhm.invalidar()
    try:
        _lhm.leer_sensores(lector=_lector)
        _lhm.leer_sensores(lector=_lector)
        assert len(llamadas) == 1, f"el lector debía invocarse 1 vez, se invocó {len(llamadas)}"
        _lhm.invalidar()
        _lhm.leer_sensores(lector=_lector)
        assert len(llamadas) == 2, f"tras invalidar() debía releerse (2 en total), hubo {len(llamadas)}"

        # (b) filtrar: por tipo exacto y, opcionalmente, por tipo de hardware.
        sensores = [
            _sensor("Motherboard", "Fan", "Fan #1", 1800),
            _sensor("GpuNvidia", "Fan", "GPU Fan", 900),
            _sensor("GpuNvidia", "Temperature", "GPU Core", 50),
            _sensor("Cpu", "Voltage", "Core #1 VID", 1.1),
        ]
        ventiladores = _lhm.filtrar(sensores, "Fan")
        assert [s["nombre"] for s in ventiladores] == ["Fan #1", "GPU Fan"], ventiladores
        ventiladores_gpu = _lhm.filtrar(sensores, "Fan", hardware_contiene="Gpu")
        assert [s["nombre"] for s in ventiladores_gpu] == ["GPU Fan"], ventiladores_gpu
        assert _lhm.filtrar(sensores, "Load") == []

        # (c) Un fallo del lector nunca se propaga: lista vacía + mensaje.
        def _lector_roto():
            raise RuntimeError("driver bloqueado")

        _lhm.invalidar()
        assert _lhm.leer_sensores(lector=_lector_roto) == []
        assert "driver bloqueado" in (_lhm.error_carga() or ""), _lhm.error_carga()
        _lhm.invalidar()
        assert _lhm.error_carga() is None
    finally:
        _lhm.invalidar()


def test_fuente_poder_sin_sensores():
    # Review Focus 4: "no se pudo cargar la librería" (error real, p. ej.
    # driver bloqueado) no debe confundirse con "la placa no tiene sensores".
    def _lector_roto():
        raise RuntimeError("driver bloqueado")

    _lhm.invalidar()
    try:
        _lhm.leer_sensores(lector=_lector_roto)  # deja el fallo en la caché
        resultado = fuente_poder.diagnosticar()
        _assert_estado("Fuente sin sensores por fallo de carga", resultado["estado"], "no_determinado")
        assert "driver bloqueado" in resultado["mensaje"], resultado["mensaje"]

        _lhm.invalidar()
        _lhm.leer_sensores(lector=lambda: [])  # sin error, simplemente no hay sensores
        resultado = fuente_poder.diagnosticar()
        _assert_estado("Fuente sin sensores y sin error", resultado["estado"], "no_determinado")
        assert "ningún sensor de voltaje" in resultado["mensaje"], resultado["mensaje"]

        _lhm.invalidar()
        _lhm.leer_sensores(lector=lambda: [_sensor("Cpu", "Voltage", "Core #1 VID", 1.1)])
        resultado = fuente_poder.diagnosticar()
        _assert_estado("Fuente con un sensor de voltaje válido", resultado["estado"], "normal")
        assert resultado["datos"]["rieles"] == [{"origen": "Cpu X", "sensor": "Core #1 VID", "voltios": 1.1}], resultado["datos"]

        # La lectura compartida también trae la GPU (la necesitan cpu/gpu),
        # pero fuente_poder solo reporta placa + CPU: el voltaje de núcleo
        # de una GPU en reposo (~0 V) no debe disparar "sospecha".
        _lhm.invalidar()
        _lhm.leer_sensores(lector=lambda: [
            _sensor("Cpu", "Voltage", "Core #1 VID", 1.1),
            _sensor("GpuAmd", "Voltage", "GPU Core", 0.0),
        ])
        resultado = fuente_poder.diagnosticar()
        _assert_estado("Voltaje de GPU en reposo no cuenta", resultado["estado"], "normal")
        assert [r["sensor"] for r in resultado["datos"]["rieles"]] == ["Core #1 VID"], resultado["datos"]
    finally:
        _lhm.invalidar()


def test_consistencia_scanner():
    # ESTADOS_VALIDOS y _SEVERIDAD deben listar exactamente los mismos 5
    # nombres — si alguien agrega un estado nuevo en uno y se olvida del
    # otro, el veredicto global podría ignorarlo en silencio.
    assert set(scanner.ESTADOS_VALIDOS) == set(scanner._SEVERIDAD), \
        "ESTADOS_VALIDOS y _SEVERIDAD divergieron"
    assert len(scanner.COMPONENTES) == 7, "el alcance del proyecto son 7 componentes, ver DECISIONES.md"
    assert "gpu" not in scanner.COMPONENTES, "GPU es sub-info de cpu, no un componente propio (decisión 21)"


def test_prioridad_veredicto():
    def _simular(**estados):
        return {"componentes": {nombre: {"estado": estado} for nombre, estado in estados.items()}}

    # El caso exacto de la revisión externa (decisión 22): una advertencia
    # real en un componente no debe quedar tapada por un sensor ausente
    # en otro componente distinto.
    resultado = _simular(almacenamiento="advertencia", cpu="no_determinado", ram="normal")
    _assert_estado("SSD advertencia + CPU sin dato", scanner.clasificar_equipo(resultado), "ADVERTENCIA")

    # no_determinado solo, sin nada más grave: sigue pesando más que normal.
    resultado = _simular(cpu="no_determinado", ram="normal")
    _assert_estado("Solo CPU sin dato", scanner.clasificar_equipo(resultado), "NO_DETERMINADO")

    # critico siempre gana, incluso sobre sospecha.
    resultado = _simular(bateria="critico", almacenamiento="sospecha")
    _assert_estado("Crítico + sospecha", scanner.clasificar_equipo(resultado), "CRITICO")

    # Todo normal.
    resultado = _simular(**{c: "normal" for c in scanner.COMPONENTES})
    _assert_estado("Los 7 en normal", scanner.clasificar_equipo(resultado), "NORMAL")


def test_cobertura():
    componentes = {
        "mainboard": {"estado": "normal"},
        "cpu": {"estado": "no_determinado"},
        "ram": {"estado": "advertencia"},
        "almacenamiento": {"estado": "critico"},
        "fuente_poder": {"estado": "normal"},
        "bateria": {"estado": "normal"},
        "red": {"estado": "normal"},
    }
    cobertura = scanner._calcular_cobertura(componentes)
    # "critico" cuenta como medido — cobertura es sobre poder leer el
    # dato, no sobre si el equipo está sano (decisión 22).
    assert cobertura == {"porcentaje": 86, "completos": 6, "parciales": 1}, cobertura


def test_utils_entorno():
    assert utils.es_winpe(True, "C:") is True
    assert utils.es_winpe(False, "x:") is True
    assert utils.es_winpe(False, "C:") is False
    assert utils.detectar_entorno() in {"winpe", "windows"}
    assert isinstance(utils.es_administrador(), bool)

    # Puerto libre: si el preferido está libre, se devuelve el mismo.
    sonda = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sonda.bind(("127.0.0.1", 0))
        puerto_libre_prueba = sonda.getsockname()[1]
    finally:
        sonda.close()
    assert utils.puerto_libre(puerto_libre_prueba) == puerto_libre_prueba

    # Si el preferido está ocupado (enlazado y escuchando), devuelve otro.
    ocupado = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        ocupado.bind(("127.0.0.1", 0))
        ocupado.listen(1)
        puerto_ocupado = ocupado.getsockname()[1]
        alternativo = utils.puerto_libre(puerto_ocupado)
        assert alternativo != puerto_ocupado and alternativo > 0, alternativo
    finally:
        ocupado.close()


def _en_hilo(funcion):
    """Corre `funcion` en un hilo aparte y re-lanza su excepción en el principal.

    El servidor real atiende en hilos; usar test_client() en el hilo principal
    deja un par CoInitialize/CoUninitialize de COM que al salir imprime
    "Win32 exception occurred releasing IUnknown" (inofensivo, solo de test).
    """
    error = []

    def _correr():
        try:
            funcion()
        except BaseException as excepcion:
            error.append(excepcion)

    hilo = threading.Thread(target=_correr)
    hilo.start()
    hilo.join()
    if error:
        raise error[0]


def test_app_rutas():
    """Rutas de app.py: host seguro, /api/status ampliado y errores en JSON."""
    # (a) Decisión 27: el servidor solo escucha en loopback.
    assert app.HOST == "127.0.0.1", app.HOST

    escaneo_original = scanner.ejecutar_escaneo_completo
    reporte_original = utils.generar_reporte_texto
    app._ultimo_escaneo = None

    def _peticiones():
        cliente = app.app.test_client()
        # (b) /api/status agrega entorno (str) y administrador (bool).
        respuesta = cliente.get("/api/status")
        assert respuesta.status_code == 200, respuesta.status_code
        datos = respuesta.get_json()
        assert isinstance(datos["entorno"], str), datos
        assert isinstance(datos["administrador"], bool), datos
        assert "timestamp" in datos and "espacio_disco" in datos, datos

        # (c) Resultado no serializable: 500 y NO se guarda el escaneo.
        scanner.ejecutar_escaneo_completo = lambda: {"x": object()}
        respuesta = cliente.get("/api/scan")
        assert respuesta.status_code == 500, respuesta.status_code
        assert app._ultimo_escaneo is None, app._ultimo_escaneo

        # (d) Falla al armar el reporte: 500 con JSON, no página HTML.
        def _reporte_roto(*args, **kwargs):
            raise RuntimeError("fallo simulado")

        utils.generar_reporte_texto = _reporte_roto
        respuesta = cliente.get("/api/reporte")
        assert respuesta.status_code == 500, respuesta.status_code
        assert respuesta.mimetype == "application/json", respuesta.mimetype
        assert respuesta.get_json()["estado"] == "error", respuesta.get_json()

    try:
        _en_hilo(_peticiones)
    finally:
        scanner.ejecutar_escaneo_completo = escaneo_original
        utils.generar_reporte_texto = reporte_original
        app._ultimo_escaneo = None


def test_lanzador():
    """Funciones puras de lanzador.py: elegir navegador, comando y latido."""
    # (a) elegir_navegador con existencia simulada (sin tocar el disco).
    variables = {
        "ProgramFiles(x86)": "C:\\PF86",
        "ProgramFiles": "C:\\PF",
        "LocalAppData": "C:\\Local",
    }
    edge86 = "C:\\PF86\\Microsoft\\Edge\\Application\\msedge.exe"
    chrome_local = "C:\\Local\\Google\\Chrome\\Application\\chrome.exe"
    chrome_pf = "C:\\PF\\Google\\Chrome\\Application\\chrome.exe"

    assert lanzador.elegir_navegador(variables, lambda ruta: ruta == edge86) == edge86
    assert lanzador.elegir_navegador(variables, lambda ruta: ruta == chrome_local) == chrome_local
    assert lanzador.elegir_navegador(variables, lambda ruta: False) is None
    # Edge y Chrome presentes: gana Edge.
    assert lanzador.elegir_navegador(variables, lambda ruta: ruta in (edge86, chrome_pf)) == edge86
    # Variables de entorno ausentes: se saltan, sin romper.
    assert lanzador.elegir_navegador({}, lambda ruta: True) is None
    # Brave (Chromium) va después de Edge y Chrome, en ProgramFiles, x86 y LocalAppData.
    brave = "BraveSoftware\\Brave-Browser\\Application\\brave.exe"
    brave_pf, brave86, brave_local = (f"C:\\PF\\{brave}", f"C:\\PF86\\{brave}", f"C:\\Local\\{brave}")
    assert lanzador.elegir_navegador(variables, lambda ruta: ruta == brave_pf) == brave_pf
    assert lanzador.elegir_navegador(variables, lambda ruta: ruta == brave86) == brave86
    assert lanzador.elegir_navegador(variables, lambda ruta: ruta == brave_local) == brave_local
    assert lanzador.elegir_navegador(variables, lambda ruta: ruta in (brave_pf, brave86, brave_local)) == brave_pf
    assert lanzador.elegir_navegador(variables, lambda ruta: ruta in (edge86, brave_pf)) == edge86
    assert lanzador.elegir_navegador(variables, lambda ruta: ruta in (chrome_pf, brave_pf)) == chrome_pf
    assert lanzador.elegir_navegador({"ProgramFiles": "C:\\PF"}, lambda ruta: ruta == brave86) is None

    # (b) comando_app: ventana tipo aplicación con perfil propio.
    comando = lanzador.comando_app("C:\\e.exe", "http://127.0.0.1:5000", "C:\\tmp\\p")
    assert comando[0] == "C:\\e.exe", comando
    assert "--app=http://127.0.0.1:5000" in comando, comando
    assert "--user-data-dir=C:\\tmp\\p" in comando, comando

    # (c) debe_apagar: gracia inicial y tolerancia de latido.
    assert lanzador.debe_apagar(110.0, None, 100.0) is False   # 10 s sin latido
    assert lanzador.debe_apagar(161.0, None, 100.0) is True     # 61 s sin latido
    assert lanzador.debe_apagar(200.0, 100.0, 0.0) is False     # latido hace 100 s
    assert lanzador.debe_apagar(251.0, 100.0, 0.0) is True      # latido hace 151 s

    # (d) abrir_ventana: si no se puede lanzar el exe (OSError), cae al navegador por defecto.
    url = "http://127.0.0.1:5000"
    abiertas = []

    def _popen_roto(*args, **kwargs):
        raise OSError("exe desaparecido")

    with contextlib.redirect_stdout(io.StringIO()):  # silencia el aviso impreso
        lanzador.abrir_ventana("C:\\e.exe", url, "C:\\tmp\\p", popen=_popen_roto, abrir_web=abiertas.append)
    assert abiertas == [url], abiertas

    lanzados = []
    abiertas.clear()
    lanzador.abrir_ventana("C:\\e.exe", url, "C:\\tmp\\p", popen=lanzados.append, abrir_web=abiertas.append)
    assert lanzados == [lanzador.comando_app("C:\\e.exe", url, "C:\\tmp\\p")], lanzados
    assert abiertas == [], abiertas

    # (e) latido_tras_pausa: si el propio bucle de vigilancia se detuvo (equipo
    # suspendido), el latido se renueva para dar margen al navegador.
    assert lanzador.latido_tras_pausa(101.0, 100.0, 90.0) == 90.0       # sin pausa: igual
    assert lanzador.latido_tras_pausa(101.0, 100.0, None) is None        # sin pausa, sin latido: igual
    assert lanzador.latido_tras_pausa(400.0, 200.0, 50.0) == 400.0       # pausa de 200 s, latido viejo
    assert lanzador.latido_tras_pausa(400.0, 200.0, None) == 400.0       # pausa sin latido previo
    assert lanzador.latido_tras_pausa(110.0, 100.0, 5.0) == 5.0          # justo en el umbral (10 s): no es pausa


class _FakeSensor:
    def __init__(self, tipo, nombre, valor):
        self.SensorType, self.Name, self.Value = tipo, nombre, valor


class _FakeHardware:
    """Imita un IHardware de LibreHardwareMonitor (solo lo que lee _lhm)."""

    def __init__(self, tipo, nombre, sensores=(), sub=(), falla=False):
        self.HardwareType, self.Name = tipo, nombre
        self.Sensors = [_FakeSensor(*s) for s in sensores]
        self.SubHardware = list(sub)
        self._falla = falla

    def Update(self):
        if self._falla:
            raise RuntimeError("Update() falló")


def test_lhm_recoger_aislamiento():
    # Un hardware (p. ej. la GPU) que falla en Update() no debe descartar los
    # sensores del resto, ni los de un sub-hardware sano del mismo equipo.
    cpu_sano = _FakeHardware("Cpu", "CPU X", [("Temperature", "CPU Package", 60.0)])
    gpu_roto = _FakeHardware("GpuNvidia", "GPU X", [("Temperature", "GPU Core", 50.0)], falla=True)
    placa = _FakeHardware(
        "Motherboard", "Placa X", [("Fan", "Fan #1", 1500.0)],
        sub=[
            _FakeHardware("Motherboard", "SuperIO roto", [("Fan", "Fan #9", 1.0)], falla=True),
            _FakeHardware("Motherboard", "SuperIO", [("Voltage", "Vcore", 1.1)]),
        ],
    )
    sensores = _lhm._recoger_sensores([cpu_sano, gpu_roto, placa])
    nombres = [s["nombre"] for s in sensores]
    assert nombres == ["CPU Package", "Fan #1", "Vcore"], nombres
    assert sensores[2]["tipo_hardware"] == "Motherboard" and sensores[2]["hardware"] == "SuperIO", sensores[2]


def test_lhm_consumidores():
    # Pegamento entre _lhm y sus consumidores: cpu (ventiladores) y gpu
    # (telemetría) leen la misma caché y respetan la forma de salida.
    _lhm.invalidar()
    try:
        _lhm.leer_sensores(lector=lambda: [
            _sensor("Motherboard", "Fan", "Fan #1", 1234.6),
            _sensor("GpuNvidia", "Fan", "GPU Fan", 900.2),
            _sensor("Motherboard", "Fan", "Fan #2", None),
            _sensor("GpuNvidia", "Temperature", "GPU Core", 55.0),
            _sensor("Cpu", "Temperature", "CPU Package", 70.0),
            _sensor("GpuNvidia", "Load", "GPU Core", 42.0),
            _sensor("Cpu", "Load", "CPU Total", 90.0),
        ])
        assert cpu._obtener_ventiladores() == [
            {"nombre": "Fan #1", "rpm": 1235},
            {"nombre": "GPU Fan", "rpm": 900},
        ], cpu._obtener_ventiladores()
        assert gpu._telemetria() == (55.0, 42.0), gpu._telemetria()
    finally:
        _lhm.invalidar()

    # El escaneo completo arranca invalidando la caché de sensores.
    invalidaciones = []
    invalidar_orig, componentes_orig = _lhm.invalidar, scanner.COMPONENTES
    try:
        _lhm.invalidar = lambda: invalidaciones.append(1)
        scanner.COMPONENTES = []
        scanner.ejecutar_escaneo_completo()
        assert invalidaciones == [1], invalidaciones
    finally:
        _lhm.invalidar, scanner.COMPONENTES = invalidar_orig, componentes_orig
        _lhm.invalidar()


def test_explicador():
    llaves = {"que_significa", "que_hacer", "quien", "urgencia", "pregunta_tecnico"}
    prohibidas = ("peligro", "infectad", "limpio", "garantiza")
    # F4a: los 4 análisis viven aparte de COMPONENTES pero tienen las mismas guías
    assert scanner.ANALISIS == ["espacio", "inicio", "programas", "rendimiento", "estabilidad", "controladores", "seguridad"], scanner.ANALISIS
    assert set(scanner.ANALISIS).isdisjoint(scanner.COMPONENTES)
    assert set(explicador.NOMBRES_ANALISIS) == set(scanner.ANALISIS), explicador.NOMBRES_ANALISIS
    assert all(v.strip() for v in explicador.NOMBRES_ANALISIS.values())
    # (a) cobertura + (b) forma + (c) reglas por estado + (d) palabras prohibidas
    for c in scanner.COMPONENTES + scanner.ANALISIS:
        for e in scanner.ESTADOS_VALIDOS:
            g = explicador.GUIAS[c][e]
            assert set(g) == llaves, (c, e, set(g))
            assert g["que_significa"].strip(), (c, e)
            assert isinstance(g["que_hacer"], list) and g["que_hacer"], (c, e)
            assert all(isinstance(p, str) and p.strip() for p in g["que_hacer"]), (c, e)
            assert g["quien"] in explicador.QUIEN_VALIDOS, (c, e, g["quien"])
            assert g["urgencia"] in explicador.URGENCIAS_VALIDAS, (c, e, g["urgencia"])
            if e == "normal":
                assert g["urgencia"] == "ninguna" and g["quien"] == "nadie", (c, e)
                assert g["pregunta_tecnico"] == "", (c, e)
            else:
                assert g["pregunta_tecnico"].strip(), (c, e)
            if e == "critico":
                assert g["urgencia"] == "alta", (c, e)
            if e == "sospecha":
                assert g["urgencia"] == "media", (c, e)
            if c in scanner.ANALISIS:  # reglas de F4a: advertencia baja/media y campos cortos
                if e == "advertencia":
                    assert g["urgencia"] in ("baja", "media"), (c, e)
                for campo in (g["que_significa"], g["pregunta_tecnico"], *g["que_hacer"]):
                    assert len(campo) <= 220, (c, e, len(campo))
            texto = " ".join([g["que_significa"], g["pregunta_tecnico"], *g["que_hacer"]]).lower()
            for palabra in prohibidas:
                assert palabra not in texto, (c, e, palabra)
    # (e) par desconocido: guía genérica, sin lanzar
    for par in (("inexistente", "normal"), ("cpu", "estado_raro")):
        g = explicador.guia_para(*par)
        assert set(g) == llaves, (par, set(g))
        assert g["quien"] == "tecnico" and g["urgencia"] == "baja", (par, g)
    # (f) guia_para devuelve copia
    g = explicador.guia_para("cpu", "normal")
    g["que_hacer"].append("mutado")
    assert "mutado" not in explicador.GUIAS["cpu"]["normal"]["que_hacer"]
    assert "mutado" not in explicador.guia_para("cpu", "normal")["que_hacer"]
    # (g') frases del veredicto: exactamente las 5 severidades en mayúsculas
    assert set(explicador.FRASES_VEREDICTO) == {s.upper() for s in scanner._SEVERIDAD}, explicador.FRASES_VEREDICTO
    assert all(v.strip() for v in explicador.FRASES_VEREDICTO.values())
    # (g) sin permisos de administrador el CPU no puede leer sensores
    g = explicador.GUIAS["cpu"]["no_determinado"]
    assert "administrador" in " ".join([g["que_significa"], *g["que_hacer"]]).lower()
    assert g["quien"] == "tu_mismo"


def test_escaner_adjunta_guia():
    import types
    base = {"componente": "cpu", "estado": "critico", "mensaje": "m", "datos": {"x": 1}, "recomendacion": "r"}
    importlib_orig = scanner.importlib
    try:
        # (a) éxito: conserva las 5 llaves y agrega la guía
        modulo = types.SimpleNamespace(diagnosticar=lambda: dict(base))
        scanner.importlib = types.SimpleNamespace(import_module=lambda nombre: modulo)
        r = scanner._escanear_componente("cpu")
        assert r["guia"]["urgencia"] == "alta", r
        assert {k: r[k] for k in base} == base, r
        # (b) módulo inexistente (importlib real) -> no_determinado con guía
        scanner.importlib = importlib_orig
        r = scanner._escanear_componente("inexistente")
        assert r["estado"] == "no_determinado" and "guia" in r, r
        # (b2) excepción del módulo y contrato incumplido también llevan guía
        def _roto():
            raise RuntimeError("x")
        scanner.importlib = types.SimpleNamespace(import_module=lambda n: types.SimpleNamespace(diagnosticar=_roto))
        assert "guia" in scanner._escanear_componente("cpu")
        scanner.importlib = types.SimpleNamespace(import_module=lambda n: types.SimpleNamespace(diagnosticar=lambda: {"estado": "normal"}))
        r = scanner._escanear_componente("cpu")
        assert r["estado"] == "no_determinado" and "guia" in r, r
    finally:
        scanner.importlib = importlib_orig
    # (c) el contrato no cambió
    assert scanner._cumple_contrato(dict(base)) is True
    # (e) reporte de texto: solo los componentes no normales llevan la guía
    resultado = {"componentes": {
        "cpu": {**base, "guia": explicador.guia_para("cpu", "critico")},
        "ram": {**base, "componente": "ram", "estado": "normal", "guia": explicador.guia_para("ram", "normal")},
        "red": {**base, "componente": "red", "estado": "critico"},  # sin guía: no rompe
    }}
    texto = utils.generar_reporte_texto(resultado, "CRITICO")
    assert texto.count("Qué significa:") == 1 and texto.count("Quién lo hace:") == 1, texto
    assert "Qué hacer:\n- " in texto, texto
    assert explicador.guia_para("cpu", "critico")["quien"] == "tecnico" and "Quién lo hace: Un técnico" in texto, texto


def test_escaner_recomendaciones():
    hechos_falsos = {"ram_gb": 4}
    recs_falsas = [{"id": "so", "titulo": "Sistema operativo", "detalle": "Detalle X", "basado_en": ["4 GB de RAM"],
                    "prioridad": "media", "quien": "tecnico",
                    "opciones": [{"nombre": "Windows 10", "motivo": "Suficiente", "nota": "Soporte limitado"},
                                 {"nombre": "Lubuntu", "motivo": "Liviano", "nota": ""}]}]
    llamadas = []
    COMP_orig, hechos_orig, rec_orig = scanner.COMPONENTES, equipo.leer_hechos, recomendador.recomendar
    try:
        scanner.COMPONENTES = []
        # (a) el escaneo adjunta lo que devuelven las funciones, sin tocar el ID
        equipo.leer_hechos = lambda: hechos_falsos
        recomendador.recomendar = lambda resultado, hechos: (llamadas.append((resultado, hechos)), recs_falsas)[1]
        r = scanner.ejecutar_escaneo_completo()
        assert r["hechos"] == hechos_falsos and r["recomendaciones"] == recs_falsas, r
        assert {"hechos", "recomendaciones", "total"} <= set(r["tiempos"]), r["tiempos"]
        # el ID depende solo de los componentes: lo que devuelvan hechos/recomendar no lo cambia
        id_a = r["id_diagnostico"]
        equipo.leer_hechos = lambda: {"otro": 1}
        recomendador.recomendar = lambda resultado, hechos: []
        assert scanner.ejecutar_escaneo_completo()["id_diagnostico"][-4:] == id_a[-4:]
        equipo.leer_hechos = lambda: hechos_falsos
        recomendador.recomendar = lambda resultado, hechos: (llamadas.append((resultado, hechos)), recs_falsas)[1]
        assert llamadas and "componentes" in llamadas[0][0] and llamadas[0][1] == hechos_falsos, llamadas
        # (b) si algo lanza, el escaneo completa igual
        def _roto():
            raise RuntimeError("x")
        equipo.leer_hechos = _roto
        with contextlib.redirect_stderr(io.StringIO()):
            r = scanner.ejecutar_escaneo_completo()
        assert r["hechos"] == {} and r["recomendaciones"] == [], r
        assert "hechos" in r["tiempos"] and "recomendaciones" in r["tiempos"], r["tiempos"]
        equipo.leer_hechos = lambda: hechos_falsos
        recomendador.recomendar = lambda resultado, hechos: _roto()
        with contextlib.redirect_stderr(io.StringIO()):
            r = scanner.ejecutar_escaneo_completo()
        assert r["hechos"] == hechos_falsos and r["recomendaciones"] == [], r
    finally:
        scanner.COMPONENTES, equipo.leer_hechos, recomendador.recomendar = COMP_orig, hechos_orig, rec_orig
        _lhm.invalidar()
    # (c) reporte de texto
    texto = utils.generar_reporte_texto({"componentes": {}, "recomendaciones": recs_falsas}, "NORMAL")
    for esperado in ("--- RECOMENDACIONES ---", "[media] Sistema operativo", "Detalle: Detalle X", "Basado en:\n- 4 GB de RAM",
                     "Opciones:\n- Windows 10: Suficiente (Soporte limitado)", "- Lubuntu: Liviano\n"):
        assert esperado in texto, (esperado, texto)
    assert texto.index("--- RECOMENDACIONES ---") < texto.index("--- LIMITACIONES"), texto
    assert "RECOMENDACIONES" not in utils.generar_reporte_texto({"componentes": {}}, "NORMAL")
    # (d) basura a nivel de campo dentro de recomendaciones válidas: sin excepción ni líneas absurdas
    basura = [{"titulo": "T1", "detalle": None, "basado_en": "RAM: 4 GB", "opciones": "Windows 10", "quien": ["x"]},
              {"titulo": "T2", "detalle": 5, "basado_en": 7, "opciones": [{"nombre": "N", "motivo": None, "nota": 3}], "quien": {"a": 1}},
              {"titulo": "T3", "basado_en": [None, "ok"], "opciones": {"nombre": "x"}, "quien": "tecnico"}]
    texto = utils.generar_reporte_texto({"componentes": {}, "recomendaciones": basura}, "NORMAL")
    assert "Detalle: None" not in texto and "None" not in texto, texto
    assert "- RAM: 4 GB\n" in texto and "- R\n" not in texto and "- ok\n" in texto, texto
    assert "Opciones:\n- N\n" in texto and "- W\n" not in texto, texto
    assert "Quién lo hace: Un técnico" in texto and texto.count("Quién lo hace:") == 1, texto
    for raro in (None, "x", [None, {}, {"titulo": "T"}, 5]):
        utils.generar_reporte_texto({"componentes": {}, "recomendaciones": raro}, "NORMAL")


def test_guias_endpoint():
    def _peticion():
        r = app.app.test_client().get("/api/guias")
        assert r.status_code == 200, r.status_code
        datos = r.get_json()
        for c in scanner.COMPONENTES + scanner.ANALISIS:
            assert set(datos[c]) == scanner.ESTADOS_VALIDOS, (c, set(datos[c]))
        assert set(datos["_veredictos"]) == set(explicador.FRASES_VEREDICTO), datos["_veredictos"]
        assert set(datos) == set(scanner.COMPONENTES) | set(scanner.ANALISIS) | {"_veredictos", "_nombres_analisis"}, set(datos)
        assert set(datos["_nombres_analisis"]) == set(scanner.ANALISIS), datos["_nombres_analisis"]
    _en_hilo(_peticion)


def _escaneo_falso(estado_cpu="critico"):
    """Escaneo mínimo: mainboard con datos hostiles + cpu en `estado_cpu`."""
    def comp(nombre, estado, mensaje, datos=None):
        return {"componente": nombre, "estado": estado, "mensaje": mensaje,
                "datos": datos or {}, "recomendacion": "r",
                "guia": explicador.guia_para(nombre, estado)}
    return {"id_diagnostico": "ID-<i>1", "timestamp": "2026-10-21 10:00:00", "componentes": {
        "mainboard": comp("mainboard", "normal", "Placa <b>ok</b>",
                          {"fabricante": "Acme", "modelo": "<script>alert(1)</script> & Co"}),
        "cpu": comp("cpu", estado_cpu, "CPU caliente"),
    }}


def test_informe():
    import informe
    from html import escape as escape_html
    # (a) todo texto del escaneo se escapa
    html = informe.generar_informe_html(_escaneo_falso(), "CRITICO")
    assert "<script>alert(1)</script>" not in html and "<b>ok</b>" not in html and "<i>1" not in html, html
    assert "&lt;script&gt;" in html and "&lt;b&gt;ok" in html, html
    assert html.lstrip().startswith("<!DOCTYPE html>") and 'lang="es"' in html
    assert explicador.FRASES_VEREDICTO["CRITICO"] in html
    assert html.index("Procesador") < html.index("Tarjeta Madre"), "orden por severidad"
    # (b) sin escaneo: página amable, no lanza
    for vacio in (None, {}):
        h = informe.generar_informe_html(vacio, "SIN_DATOS")
        assert "Aún no hay un escaneo" in h and "Revisar mi PC" in h and "Escanear Sistema" not in h, h
    # (c) preguntas solo de componentes no normales; límites siempre
    g = explicador.guia_para("cpu", "critico")
    assert "Preguntas para tu técnico" in html and html.count(g["pregunta_tecnico"]) == 1
    assert "no reemplaza la revisión de un técnico" in html
    h = informe.generar_informe_html(_escaneo_falso("normal"), "NORMAL")
    assert "Preguntas para tu técnico" in h and "no hacen falta preguntas" in h.lower(), h
    assert "no reemplaza la revisión de un técnico" in h
    # (d) estilos de impresión y sin recursos externos
    assert "@media print" in html
    assert "<script" not in html.replace("&lt;script", "") and "http://" not in html and "https://" not in html

    # (d2) endurecimiento: cadenas hostiles en estado/guía, sin recursos externos
    assert "&amp; Co" in html and "<link" not in html and "src=" not in html
    assert "print-color-adjust" in html and "Según lo que el programa pudo medir." in html
    hostil = _escaneo_falso()
    hostil["componentes"]["cpu"]["estado"] = "<u>x</u>"
    hostil["componentes"]["cpu"]["guia"] = {"que_significa": "<em>sig</em>", "que_hacer": None,
                                            "quien": "tecnico", "pregunta_tecnico": "<q>preg</q>"}
    hostil["componentes"]["mainboard"]["datos"] = "no es dict"
    h = informe.generar_informe_html(hostil, "CRITICO")
    for crudo in ("<u>x</u>", "<em>sig</em>", "<q>preg</q>"):
        assert crudo not in h and escape_html(crudo) in h, crudo
    # componente no normal sin guía: sin líneas de guía ni "todo está normal"
    sin_guia = _escaneo_falso()
    sin_guia["componentes"]["cpu"].pop("guia")
    h = informe.generar_informe_html(sin_guia, "CRITICO")
    assert "todo está normal" not in h and "No hay preguntas sugeridas" in h, h
    assert h.count("Qué significa:") == 1 and h.count("Quién lo hace:") == 1, h  # solo la tarjeta normal
    assert "Quién lo hace: No hace falta" in h.replace("</strong> ", " ").replace("<strong>", "")

    # (f) fecha local legible, pista de impresión, paso de mantenimiento en normales
    assert explicador.QUIEN_TEXTO == {"tu_mismo": "Tú mismo", "tecnico": "Un técnico", "nadie": "Nadie"}
    assert utils.QUIEN_TEXTO is explicador.QUIEN_TEXTO
    import re
    assert re.search(r"Fecha: \d{2}/\d{2}/\d{4} \d{2}:\d{2}<", informe.generar_informe_html(
        {**_escaneo_falso(), "timestamp": "2026-10-21T23:10:05.123456+00:00"}, "CRITICO")), "fecha local"
    for basura in ("2026-10-21 10:00:00", "<i>x</i>", "", None):
        h = informe.generar_informe_html({**_escaneo_falso(), "timestamp": basura}, "CRITICO")
        assert "<i>x</i>" not in h and "Fecha:" in h, basura
    h = informe.generar_informe_html({**_escaneo_falso(), "timestamp": "<i>x</i>"}, "CRITICO")
    assert "Fecha: &lt;i&gt;x&lt;/i&gt;" in h, h
    assert '<p class="no-imprimir">Para imprimirlo o guardarlo como PDF, pulsa Ctrl+P.</p>' in html
    assert ".no-imprimir { display: none" in html
    assert html.count("Para mantenerlo bien:") == 1 and html.count("Qué hacer:") == 1, html  # normal vs crítico

    # (e) ruta: sin escaneo responde 200 text/html; con excepción, JSON 500
    original, generar = app._ultimo_escaneo, informe.generar_informe_html

    def _peticion():
        cliente = app.app.test_client()
        r = cliente.get("/api/informe")
        assert r.status_code == 200 and r.mimetype == "text/html", (r.status_code, r.mimetype)
        assert "Aún no hay un escaneo" in r.get_data(as_text=True)
        informe.generar_informe_html = lambda *a: 1 / 0
        r = cliente.get("/api/informe")
        assert r.status_code == 500 and r.get_json()["estado"] == "error", r.status_code

    try:
        app._ultimo_escaneo = None
        _en_hilo(_peticion)
    finally:
        app._ultimo_escaneo = original
        informe.generar_informe_html = generar


def test_informe_recomendaciones():
    import informe
    rec = {"id": "so", "titulo": "<script>alert(1)</script> & Co", "detalle": "Det <i>x</i>",
           "basado_en": ["RAM: 4 GB", "<u>cpu</u>"], "prioridad": "alta", "quien": "tecnico",
           "opciones": [{"nombre": "Lubuntu <b>n</b>", "motivo": "Liviano", "nota": "<b>x</b>"}]}
    base = _escaneo_falso()
    # (a)(b) escapado, <details open> con el nombre, y antes de las preguntas
    html = informe.generar_informe_html({**base, "recomendaciones": [rec]}, "CRITICO")
    assert "<script>alert(1)</script>" not in html and "<b>x</b>" not in html and "<u>cpu</u>" not in html, html
    assert "&lt;script&gt;" in html and "&lt;b&gt;x&lt;/b&gt;" in html
    assert "Recomendaciones para tu equipo" in html and "Prioridad: alta" in html and "Basado en:" in html
    assert "<details open><summary>Lubuntu &lt;b&gt;n&lt;/b&gt;</summary>" in html and "Liviano" in html, html
    assert html.index("Recomendaciones para tu equipo") < html.index("Preguntas para tu técnico")
    assert "Det <i>x</i>" not in html and "Det &lt;i&gt;x&lt;/i&gt;" in html, html  # detalle hostil escapado
    assert "overflow-wrap: anywhere" in html
    # opciones sin motivo ni nota: sin <p></p> vacíos
    vacia = informe.generar_informe_html({**base, "recomendaciones": [
        {**rec, "detalle": "", "opciones": [{"nombre": "Solo", "motivo": "", "nota": None}]}]}, "CRITICO")
    assert "<summary>Solo</summary></details>" in vacia and "<p></p>" not in vacia, vacia
    # (c) sin recomendaciones: la sección no aparece
    for v in ({}, {"recomendaciones": []}, {"recomendaciones": None}, {"recomendaciones": "x"}):
        h = informe.generar_informe_html({**base, **v}, "CRITICO")
        assert "Recomendaciones para tu equipo" not in h, v
    # (d) tolerancia a datos mal formados: no lanza
    raros = [None, 5, "x", {}, {"titulo": "t", "basado_en": 7, "opciones": "x"},
             {"titulo": "t", "basado_en": [3, None], "prioridad": 9, "opciones": [None, {}, {"motivo": "m"}]},
             {"titulo": None, "detalle": [], "opciones": [{"nombre": "n", "nota": None}]}]
    for r in raros:
        informe.generar_informe_html({**base, "recomendaciones": [r, rec]}, "CRITICO")
    assert "Recomendaciones para tu equipo" in informe.generar_informe_html({**base, "recomendaciones": raros}, "CRITICO")


def test_informe_estados_con_forma():
    """El informe usa los valores claros de palette.css (variables en línea) y cada estado lleva su ícono de forma
    ANTES del texto, el mismo que la app (iconos.js); sigue escapando y sin recursos externos."""
    import informe
    raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

    def comp(nombre, estado):
        return {"componente": nombre, "estado": estado, "mensaje": f"mensaje {nombre}", "datos": {},
                "recomendacion": "r", "guia": explicador.guia_para(nombre, estado)}
    estados = {"mainboard": "normal", "ram": "advertencia", "almacenamiento": "sospecha",
               "cpu": "critico", "red": "no_determinado"}
    base = {"id_diagnostico": "ID-1", "timestamp": "2026-10-21T10:00:00+00:00",
            "componentes": {n: comp(n, e) for n, e in estados.items()}}
    html = informe.generar_informe_html(base, "CRITICO")

    # (a) por tarjeta: <svg aria-hidden> + texto del estado dentro del chip, ícono primero; los 5 son distintos
    chips = re.findall(r'<span class="chip [^"]*">(<svg.*?</svg>)([^<]+)</span>', html, flags=re.S)
    assert [t for _, t in chips].count("Normal") == 1 and len(chips) == 5, chips
    assert {t for _, t in chips} == {"Normal", "Advertencia", "Sospecha", "Crítico", "Sin datos"}, chips
    assert len({svg for svg, _ in chips}) == 5, "los 5 íconos de estado deben ser distintos"
    for svg, _ in chips:
        assert 'aria-hidden="true"' in svg and 'stroke="currentColor"' in svg and "<script" not in svg, svg
    assert html.count("<svg") == 5, "ningún otro SVG (y ninguno con datos del escaneo)"

    # (b) mismas siluetas que la app: la forma principal de cada estado está también en iconos.js
    with open(os.path.join(raiz, "frontend", "static", "js", "iconos.js"), encoding="utf-8") as f:
        js = f.read()
    formas = {"normal": '<circle cx="12" cy="12" r="9"/>', "advertencia": "M12 3.5 21.5 20h-19z",
              "sospecha": "M12 2.5 21.5 12 12 21.5 2.5 12z",
              "critico": "M8.06 2.5h7.88L21.5 8.06v7.88l-5.56 5.56H8.06L2.5 15.94V8.06z", "no_determinado": 'stroke-dasharray="3 3.2"'}
    por_texto = {t: svg for svg, t in chips}
    etiquetas = {"normal": "Normal", "advertencia": "Advertencia", "sospecha": "Sospecha", "critico": "Crítico",
                 "no_determinado": "Sin datos"}
    for e, forma in formas.items():
        assert forma in js and forma in por_texto[etiquetas[e]], (e, forma)

    # (c) variables CSS en línea con los valores CLAROS de palette.css, incluidos los fondos teñidos de cada estado
    with open(os.path.join(raiz, "config", "palette.css"), encoding="utf-8") as f:
        claro = _variables_css(f.read(), ":root")
    en_informe = _variables_css(re.search(r"<style>(.*?)</style>", html, flags=re.S).group(1), ":root")
    obligatorias = ["--color-fondo", "--color-tarjeta", "--color-texto", "--color-texto-secundario", "--color-marino",
                    "--color-borde", "--color-acento", "--color-verde", "--color-amarillo", "--color-naranja", "--color-rojo"]
    obligatorias += [f"--color-estado-{e}-fondo" for e in _ESTADOS_PALETA]
    for nombre in obligatorias:
        assert en_informe.get(nombre) == claro[nombre], (nombre, en_informe.get(nombre), claro.get(nombre))
    assert all(claro[n] == v for n, v in en_informe.items()), "variable del informe que no está en la paleta clara"

    # (d) sigue escapando (estado hostil, mensajes hostiles) y sin recursos externos
    hostil = _escaneo_falso()
    hostil["componentes"]["cpu"]["estado"] = "<u>x</u>"
    h = informe.generar_informe_html(hostil, "CRITICO")
    assert "<u>x</u>" not in h and "&lt;u&gt;x&lt;/u&gt;" in h and "<script>alert(1)</script>" not in h, h
    assert h.count("<svg") == 2 and "&lt;script&gt;" in h  # estado desconocido -> ícono de "no determinado", sin texto crudo
    for pagina in (html, h):
        assert "<link" not in pagina and "src=" not in pagina and "http://" not in pagina and "https://" not in pagina
        assert "print-color-adjust" in pagina


def test_equipo():
    # (a) clasificación de discos
    assert equipo.tipo_disco(4, None) == "ssd"
    assert equipo.tipo_disco(None, 17) == "ssd"
    assert equipo.tipo_disco(3, 11) == "hdd"
    assert equipo.tipo_disco(None, None) == "desconocido"
    assert equipo.tipo_disco(5, 3) == "desconocido"

    # (b) heurística de CPU apta para Windows 11 (solo por nombre)
    apto = equipo.cpu_apto_windows11
    assert apto("Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz") is True
    assert apto("Intel(R) Core(TM) i7-7500U CPU") is False
    assert apto("11th Gen Intel(R) Core(TM) i7-1165G7 @ 2.80GHz") is True
    assert apto("Intel(R) Core(TM) i3-10110U CPU @ 2.10GHz") is True
    assert apto("Intel(R) Core(TM) i5-6200U CPU @ 2.30GHz") is False
    assert apto("AMD Ryzen 7 PRO 5850U with Radeon Graphics") is True
    assert apto("AMD Ryzen 5 1600 Six-Core Processor") is False
    assert apto("AMD Ryzen 5 3500U with Radeon Vega Mobile Gfx") is True
    assert apto("Intel(R) Celeron(R) N4020 CPU @ 1.10GHz") is None
    assert apto("") is None
    assert apto(None) is None

    llaves = {"so", "entorno", "firmware", "secure_boot", "tpm_version", "discos", "disco_sistema_tipo"}
    lectores = ["_leer_so", "_leer_entorno", "_leer_firmware", "_leer_secure_boot", "_leer_tpm", "_leer_discos", "_leer_disco_sistema"]
    originales = {n: getattr(equipo, n) for n in lectores}

    def roto(*a, **k):
        raise RuntimeError("falla simulada")

    try:
        # (c) todos los lectores rotos: valores de respaldo, sin excepción
        for n in lectores:
            setattr(equipo, n, roto)
        hechos = equipo.leer_hechos()
        assert set(hechos) == llaves, hechos
        assert hechos["so"] is None and hechos["firmware"] is None and hechos["entorno"] is None
        assert hechos["secure_boot"] is None and hechos["tpm_version"] is None
        assert hechos["discos"] == [] and hechos["disco_sistema_tipo"] == "desconocido", hechos

        # (d) un solo lector roto: los demás conservan su valor
        for n in lectores:
            setattr(equipo, n, originales[n])
        equipo._leer_firmware = lambda: "uefi"
        equipo._leer_secure_boot = lambda: True
        equipo._leer_tpm = roto
        hechos = equipo.leer_hechos()
        assert hechos["tpm_version"] is None
        assert hechos["firmware"] == "uefi" and hechos["secure_boot"] is True, hechos
    finally:
        for n, f in originales.items():
            setattr(equipo, n, f)

    # (e) llamada real: no se afirma nada del hardware de la máquina de pruebas
    hechos = equipo.leer_hechos()
    assert set(hechos) == llaves, hechos
    assert hechos["firmware"] in {"uefi", "bios", None}, hechos["firmware"]
    assert hechos["entorno"] in {"windows", "winpe", None}, hechos["entorno"]
    assert isinstance(hechos["discos"], list)
    assert hechos["disco_sistema_tipo"] in {"ssd", "hdd", "desconocido"}


def test_equipo_rendimiento():
    """Sin administrador no se intenta el TPM (5 s de espera y acceso denegado); un solo WMI de almacenamiento por lectura."""
    conexiones = []

    class _FalsoWMI:
        def __init__(self, namespace=None, **k):
            conexiones.append(namespace)
            self.ns = namespace

        def Win32_Tpm(self):
            raise AssertionError("no debe consultar el TPM")

        def query(self, wql):
            return []

        def MSFT_PhysicalDisk(self, **k):
            return []

        def MSFT_Partition(self, **k):
            return []

    wmi_orig, admin_orig = equipo.wmi.WMI, utils.es_administrador
    try:
        equipo.wmi.WMI = _FalsoWMI
        utils.es_administrador = lambda: False
        assert equipo._leer_tpm() is None and conexiones == [], conexiones
        equipo.leer_hechos()
        # una conexión por namespace (cimv2 + almacenamiento), nunca el TPM
        assert conexiones.count(equipo._NS_ALMACENAMIENTO) == 1 and len(conexiones) <= 2, conexiones
        assert not any("MicrosoftTpm" in str(n) for n in conexiones), conexiones
    finally:
        equipo.wmi.WMI, utils.es_administrador = wmi_orig, admin_orig


def test_equipo_cache_por_hilo():
    """Las conexiones WMI/COM son del hilo que las creó: cada hilo tiene su caché y leer_hechos no toca la ajena."""
    class _Obj:
        pass

    def _falso(namespace=None, **k):
        o = _Obj()
        o.hilo = threading.get_ident()
        return o

    wmi_orig = equipo.wmi.WMI
    paso_a, fin_b, res = threading.Event(), threading.Event(), {}

    def hilo_a():
        res["a1"] = equipo._conexion("ns")
        paso_a.set()
        fin_b.wait(5)  # B ya terminó su leer_hechos: la conexión de A debe seguir ahí
        res["a2"] = equipo._conexion("ns")
        res["dict_a"] = equipo._cache()

    def hilo_b():
        paso_a.wait(5)
        res["b1"] = equipo._conexion("ns")
        res["dict_b"] = equipo._cache()
        equipo.leer_hechos()
        fin_b.set()

    try:
        equipo.wmi.WMI = _falso
        ta, tb = threading.Thread(target=hilo_a), threading.Thread(target=hilo_b)
        ta.start(); tb.start(); ta.join(10); tb.join(10)
    finally:
        equipo.wmi.WMI = wmi_orig
    assert res["a1"] is res["a2"] and res["a1"] is not res["b1"], res
    assert res["a1"].hilo != res["b1"].hilo
    assert res["dict_a"] is not res["dict_b"]
    assert equipo._cache() is equipo._cache()
    # sin hardware concreto: el valor real siempre es uno de los permitidos
    assert equipo.leer_hechos()["disco_sistema_tipo"] in {"ssd", "hdd", "desconocido"}


def _res_reco(**comps):
    """Resultado mínimo de escaneo: {componente: (estado, datos)} -> {"componentes": {...}}."""
    return {"componentes": {n: {"componente": n, "estado": e, "mensaje": "", "datos": d}
                            for n, (e, d) in comps.items()}}


_CPU_MODERNO = "AMD Ryzen 7 PRO 5850U with Radeon Graphics"
_CPU_VIEJO = "Intel(R) Core(TM) i5-7200U"


def _pc(ram_gb=16, cpu_nombre=_CPU_MODERNO, arq="x64", uso=30, **otros):
    """Resultado con RAM y CPU; `otros` agrega componentes extra (estado, datos)."""
    return _res_reco(**{"ram": ("normal", {"capacidad_fisica_gb": ram_gb, "porcentaje_uso": uso}),
                        "cpu": ("normal", {"nombre": cpu_nombre, "arquitectura": arq, "temperatura_c": 50.0}),
                        **otros})


def _hechos_reco(arq="64-bit", firmware="uefi", secure_boot=True, tpm="2.0", discos=(), sistema="ssd",
                 so_nombre="Windows", entorno=None):
    return {"so": {"nombre": so_nombre, "build": "1", "arquitectura": arq}, "entorno": entorno, "firmware": firmware,
            "secure_boot": secure_boot, "tpm_version": tpm, "discos": list(discos),
            "disco_sistema_tipo": sistema}


def _ids(recs):
    return [r["id"] for r in recs]


def _por_id(recs, id_):
    return next(r for r in recs if r["id"] == id_)


def _nombres(rec):
    return [o["nombre"] for o in rec["opciones"]]


def test_recomendador():
    # (a) equipo moderno: Windows 11 es la principal
    r = _por_id(recomendador.recomendar(_pc(16), _hechos_reco()), "so")
    assert _nombres(r)[0] == "Windows 11", r["opciones"]
    assert r["detalle"].startswith("Según tus componentes te recomendamos:"), r["detalle"]
    assert any("16" in linea for linea in r["basado_en"]), r["basado_en"]
    assert r["prioridad"] == "baja" and r["quien"] == "tu_mismo", r

    # (b) TPM ilegible (único dato que falta): Windows 11 es la principal, pendiente de confirmar; Windows 10 sigue
    r = _por_id(recomendador.recomendar(_pc(16), _hechos_reco(tpm=None)), "so")
    assert _nombres(r)[:2] == ["Windows 11", "Windows 10"], _nombres(r)
    nota = r["opciones"][0]["nota"]
    assert nota.startswith("Falta confirmar el TPM 2.0, un chip de seguridad que Windows 11 pide."), nota
    assert "administrador" in nota and "técnico" in nota, nota
    assert r["detalle"].startswith("Según tus componentes te recomendamos: Windows 11 (falta confirmar el TPM 2.0)."), r["detalle"]
    assert r["quien"] == "tecnico", r  # sin administrador la persona no puede comprobarlo sola
    assert any("TPM (chip de seguridad): no se pudo leer" in linea for linea in r["basado_en"]), r["basado_en"]
    r = _por_id(recomendador.recomendar(_pc(16), _hechos_reco(secure_boot=None)), "so")
    assert "Arranque seguro (Secure Boot), una protección del arranque que Windows 11 pide" in r["opciones"][0]["nota"], r["opciones"][0]
    assert r["quien"] == "tecnico", r

    # (c) procesador antiguo: Windows 11 no se ofrece y se explica por qué
    r = _por_id(recomendador.recomendar(_pc(16, _CPU_VIEJO), _hechos_reco()), "so")
    assert "Windows 11" not in _nombres(r), _nombres(r)
    assert any("anterior a lo que pide Windows 11" in linea for linea in r["basado_en"]), r["basado_en"]
    r = _por_id(recomendador.recomendar(_pc(16), _hechos_reco(tpm="1.2")), "so")
    assert "Windows 11" not in _nombres(r)
    r = _por_id(recomendador.recomendar(_pc(16), _hechos_reco(secure_boot=False)), "so")
    assert "Windows 11" not in _nombres(r)
    assert ("El Arranque seguro está desactivado hoy; Windows 11 lo pide activado o disponible. "
            "Un técnico puede revisar si se puede activar.") in r["basado_en"], r["basado_en"]
    r = _por_id(recomendador.recomendar(_pc(16), _hechos_reco(firmware="bios")), "so")
    assert "Windows 11" not in _nombres(r)
    assert ("El equipo arranca hoy en modo BIOS clásico (Legacy); Windows 11 pide modo UEFI. "
            "Un técnico puede revisar si se puede cambiar.") in r["basado_en"], r["basado_en"]
    assert "Modo de arranque: BIOS clásica (el antiguo)" in r["basado_en"], r["basado_en"]
    r = _por_id(recomendador.recomendar(_pc(16), _hechos_reco()), "so")
    assert "Modo de arranque: UEFI (el moderno)" in r["basado_en"] and "TPM (chip de seguridad): 2.0" in r["basado_en"], r["basado_en"]
    assert not any("Firmware" in x for x in r["basado_en"]), r["basado_en"]
    assert "un procesador que, por su modelo, sirve para Windows 11" in r["opciones"][0]["motivo"], r["opciones"][0]

    # (d) poca RAM: MiniOS10 aparece, Windows 7 nunca es la principal y va al final
    r = _por_id(recomendador.recomendar(_pc(2, _CPU_VIEJO), _hechos_reco(sistema="hdd")), "so")
    assert "MiniOS10" in _nombres(r) and _nombres(r)[0] != "Windows 7", _nombres(r)
    assert r["quien"] == "tecnico", r
    r = _por_id(recomendador.recomendar(_pc(1, _CPU_VIEJO, "x86"), _hechos_reco(arq="32-bit")), "so")
    assert _nombres(r)[-1] == "Windows 7", _nombres(r)
    assert "actualizaciones de seguridad" in r["opciones"][-1]["nota"], r["opciones"][-1]
    assert any("32 bits" in linea for linea in r["basado_en"]), r["basado_en"]

    # (e) sin datos de firmware/TPM: no falla y Windows 11 no es la principal
    r = _por_id(recomendador.recomendar(_pc(8), {"so": {"arquitectura": "64-bit"}}), "so")
    assert _nombres(r)[0] != "Windows 11", _nombres(r)

    # (f) disco duro mecánico -> SSD; con SSD de sistema y un HDD de datos, no
    assert "disco_ssd" in _ids(recomendador.recomendar(_pc(), _hechos_reco(sistema="hdd")))
    mixto = _hechos_reco(sistema="ssd", discos=[{"modelo": "a", "tipo": "ssd", "externo": False},
                                                {"modelo": "b", "tipo": "hdd", "externo": False}])
    assert "disco_ssd" not in _ids(recomendador.recomendar(_pc(), mixto))
    solo_hdd = _hechos_reco(sistema="desconocido", discos=[{"modelo": "b", "tipo": "hdd", "externo": False}])
    assert "disco_ssd" in _ids(recomendador.recomendar(_pc(), solo_hdd))
    mixto["disco_sistema_tipo"] = "desconocido"
    assert "disco_ssd" not in _ids(recomendador.recomendar(_pc(), mixto))

    # (g) RAM justa y muy usada -> ampliar; con 16 GB no
    assert "ram_ampliar" in _ids(recomendador.recomendar(_pc(4, uso=88), _hechos_reco()))
    assert "ram_ampliar" not in _ids(recomendador.recomendar(_pc(16, uso=95), _hechos_reco()))

    # (h) disco con sospecha -> respaldo urgente
    r = _por_id(recomendador.recomendar(_pc(almacenamiento=("sospecha", {})), _hechos_reco()), "respaldo")
    assert r["prioridad"] == "alta" and r["quien"] == "tu_mismo", r

    # (i) procesador caliente
    crit = _res_reco(cpu=("critico", {"nombre": _CPU_MODERNO, "arquitectura": "x64", "temperatura_c": 96.0}))
    adv = _res_reco(cpu=("advertencia", {"nombre": _CPU_MODERNO, "arquitectura": "x64", "temperatura_c": 80.0}))
    assert _por_id(recomendador.recomendar(crit, {}), "refrigeracion")["prioridad"] == "alta"
    r = _por_id(recomendador.recomendar(adv, {}), "refrigeracion")
    assert r["prioridad"] == "media" and any("80" in linea for linea in r["basado_en"]), r

    # (j) batería
    sin = recomendador.recomendar(_pc(bateria=("normal", {"aplica": False})), _hechos_reco())
    assert not [i for i in _ids(sin) if i.startswith("bateria")], _ids(sin)
    con = recomendador.recomendar(
        _pc(bateria=("advertencia", {"aplica": True, "salud_porcentaje": 55, "ciclos_carga": 400})), _hechos_reco())
    assert "bateria_cambio" in _ids(con) and "bateria_cuidado" in _ids(con), _ids(con)
    assert _por_id(con, "bateria_cambio")["prioridad"] == "baja"

    # (k) entradas vacías o rotas: [] y sin excepción
    assert recomendador.recomendar(None, None) == []
    assert recomendador.recomendar({}, {}) == []
    assert recomendador.recomendar({"componentes": {"ram": None, "cpu": {"datos": "x"}}}, {"so": 3}) == []

    # (l) forma y orden, con todas las reglas activas a la vez
    completo = recomendador.recomendar(
        _pc(4, uso=90, almacenamiento=("sospecha", {}), cpu=("critico", {"nombre": _CPU_VIEJO, "arquitectura": "x64", "temperatura_c": 96.0}),
            bateria=("critico", {"aplica": True, "salud_porcentaje": 30, "ciclos_carga": 900})),
        _hechos_reco(sistema="hdd"))
    assert set(_ids(completo)) == {"so", "disco_ssd", "ram_ampliar", "respaldo", "refrigeracion",
                                   "bateria_cambio", "bateria_cuidado"}, _ids(completo)
    rango = {"alta": 0, "media": 1, "baja": 2}
    for rec in completo:
        assert isinstance(rec["basado_en"], list) and rec["basado_en"], rec
        assert all(isinstance(x, str) and x for x in rec["basado_en"]), rec
        assert rec["prioridad"] in rango and rec["quien"] in {"tu_mismo", "tecnico", "nadie"}, rec
        assert isinstance(rec["titulo"], str) and isinstance(rec["detalle"], str) and isinstance(rec["opciones"], list)
    pr = [rango[x["prioridad"]] for x in completo]
    assert pr == sorted(pr), [(x["id"], x["prioridad"]) for x in completo]
    assert _por_id(completo, "bateria_cambio")["prioridad"] == "media"

    # (m) vocabulario: sin alarmismo ni afirmaciones de seguridad
    escenarios = [completo, con,
                  recomendador.recomendar(_pc(1, _CPU_VIEJO, "x86"), _hechos_reco(arq="32-bit", tpm=None)),
                  recomendador.recomendar(_pc(16), _hechos_reco(tpm=None))]
    for recs in escenarios:
        for rec in recs:
            textos = [rec["titulo"], rec["detalle"], *rec["basado_en"]]
            textos += [t for o in rec["opciones"] for t in o.values()]
            for t in textos:
                for mala in ("peligro", "infectad", "limpio", "garantiza"):
                    assert mala not in t.lower(), (mala, t)


def test_recomendador_so_actual():
    """El SO que ya corre en el equipo (Windows 11 real) cuenta; en WinPE no se confía en el nombre."""
    def so(res, **kw):
        return _por_id(recomendador.recomendar(res, _hechos_reco(**kw)), "so")

    # (a) Windows 11 real, TPM ilegible: ya lo tiene, sin "falta confirmar" ni Windows 10
    r = so(_pc(16), so_nombre="Microsoft Windows 11 Pro", entorno="windows", tpm=None)
    assert _nombres(r)[0] == "Windows 11" and "Windows 10" not in _nombres(r), _nombres(r)
    assert "Ya lo tienes" in r["opciones"][0]["motivo"], r["opciones"][0]
    assert "Windows 11 (ya lo tienes instalado)" in r["detalle"], r["detalle"]
    assert r["detalle"].startswith("Según tus componentes te recomendamos: Windows 11 (ya lo tienes instalado)."), r["detalle"]
    assert "Sistema actual: Microsoft Windows 11 Pro" in r["basado_en"], r["basado_en"]
    assert not any("falta confirmar" in t.lower() for t in [r["detalle"], *[o["nota"] for o in r["opciones"]]]), r
    assert "Ubuntu o Linux Mint" in _nombres(r), _nombres(r)  # lo demás sigue las reglas por RAM
    assert r["quien"] == "tu_mismo", r

    # (b) WinPE también dice "Windows 11": se aplican las reglas normales
    r = so(_pc(16), so_nombre="Microsoft Windows 11 Pro", entorno="winpe", tpm=None)
    assert "falta confirmar" in r["detalle"] and "Windows 10" in _nombres(r), r
    assert "Ya lo tienes" not in r["opciones"][0]["motivo"], r["opciones"][0]
    r = so(_pc(16), so_nombre="Microsoft Windows 11 Pro", entorno=None, tpm=None)  # entorno desconocido: igual
    assert "Ya lo tienes" not in r["opciones"][0]["motivo"], r["opciones"][0]

    # (c) Windows 10 actual: sin cambios (Windows 11 con CPU vieja sigue fuera)
    r = so(_pc(16, _CPU_VIEJO), so_nombre="Microsoft Windows 10 Pro", entorno="windows")
    assert _nombres(r)[0] == "Windows 10" and "Windows 11" not in _nombres(r), _nombres(r)

    # (d) Windows 11 instalado con un procesador que la heurística no conoce: sigue siendo Windows 11
    r = so(_pc(16, "Intel(R) Core(TM) Ultra 7 155H"), so_nombre="Microsoft Windows 11 Home", entorno="windows")
    assert _nombres(r)[0] == "Windows 11" and "Windows 10" not in _nombres(r), _nombres(r)
    assert not any("No se pudo comprobar si el procesador" in x for x in r["basado_en"]), r["basado_en"]

    # (e) ARM: la arquitectura se trata como desconocida (sin consejos pensados para x64)
    assert "so" not in _ids(recomendador.recomendar(_pc(16, "Snapdragon ARM", "ARM64"), _hechos_reco(arq="ARM 64-bit Processor")))
    assert "so" not in _ids(recomendador.recomendar(_pc(16, _CPU_MODERNO, "x64"), _hechos_reco(arq="ARM 64-bit Processor")))


def test_recomendador_endurecimiento():
    # (a) RAM 0.0 no es una lectura real: se usa el respaldo del SO; si tampoco hay, no hay recomendación de SO
    cpu = ("normal", {"nombre": _CPU_MODERNO, "arquitectura": "x64", "temperatura_c": 50.0})
    r = _por_id(recomendador.recomendar(_res_reco(
        ram=("normal", {"capacidad_fisica_gb": 0.0, "capacidad_disponible_so_gb": 8, "porcentaje_uso": 30}), cpu=cpu),
        _hechos_reco()), "so")
    assert "RAM: 8 GB" in r["basado_en"], r["basado_en"]
    for ram in ({"capacidad_fisica_gb": 0.0, "capacidad_disponible_so_gb": 0},
                {"capacidad_fisica_gb": 0.0, "capacidad_disponible_so_gb": None}, {"capacidad_fisica_gb": 0.0}):
        assert "so" not in _ids(recomendador.recomendar(_res_reco(ram=("normal", ram), cpu=cpu), _hechos_reco())), ram

    # (b) los motivos de Linux son hechos medidos, sin promesas de rendimiento
    for gb, sistema in ((16, "ssd"), (2, "hdd"), (1, "ssd")):
        r = _por_id(recomendador.recomendar(_pc(gb), _hechos_reco(sistema=sistema)), "so")
        for o in r["opciones"]:
            assert "fluidez" not in o["motivo"] and "funciona bien" not in o["motivo"], o
    assert "Con 16 GB de RAM tu equipo cumple lo que suelen pedir" in _por_id(
        recomendador.recomendar(_pc(16), _hechos_reco()), "so")["opciones"][-1]["motivo"]

    # (c) respaldo: el texto crudo del módulo no se copia; se nombra el disco afectado
    res = _pc(almacenamiento=("sospecha", {"discos_internos": [
        {"modelo": "DISCO-A", "salud": "sospecha"}, {"modelo": "DISCO-B", "salud": "normal"}]}))
    res["componentes"]["almacenamiento"]["mensaje"] = "Salud reducida (Windows Storage Health) en: DISCO-A."
    r = _por_id(recomendador.recomendar(res, _hechos_reco()), "respaldo")
    assert "Disco afectado: DISCO-A" in r["basado_en"], r["basado_en"]
    assert not any("Storage Health" in x or "DISCO-B" in x for x in r["basado_en"]), r["basado_en"]
    assert _por_id(recomendador.recomendar(_pc(almacenamiento=("critico", {})), _hechos_reco()), "respaldo")["basado_en"] == [
        "Estado del disco según Windows: crítico"]

    # (d) límites
    def _ampliar(ram, uso):
        return "ram_ampliar" in _ids(recomendador.recomendar(_pc(ram, uso=uso), _hechos_reco()))
    assert not _ampliar(8, 80) and _ampliar(7.9, 80) and _ampliar(4, 80) and not _ampliar(4, 79.9)

    def _bat(salud):
        return recomendador.recomendar(_pc(bateria=("advertencia", {"aplica": True, "salud_porcentaje": salud})), _hechos_reco())
    assert "bateria_cambio" not in _ids(_bat(70)) and "bateria_cuidado" in _ids(_bat(70))
    assert _por_id(_bat(69.9), "bateria_cambio")["prioridad"] == "baja"
    assert _por_id(_bat(40), "bateria_cambio")["prioridad"] == "baja"
    assert _por_id(_bat(39.9), "bateria_cambio")["prioridad"] == "media"

    usb = _hechos_reco(sistema="desconocido", discos=[{"modelo": "x", "tipo": "hdd", "externo": True}])
    assert "disco_ssd" not in _ids(recomendador.recomendar(_pc(), usb))

    assert _nombres(_por_id(recomendador.recomendar(_pc(2), _hechos_reco(sistema="hdd")), "so")) == [
        "Lubuntu o Linux Mint XFCE", "MiniOS10"]
    w10 = next(o for o in _por_id(recomendador.recomendar(_pc(8, _CPU_VIEJO), _hechos_reco()), "so")["opciones"]
               if o["nombre"] == "Windows 10")
    assert "actualizaciones de seguridad" in w10["nota"] and "2025" not in w10["nota"], w10
    mini = next(o for o in _por_id(recomendador.recomendar(_pc(2), _hechos_reco(sistema="hdd")), "so")["opciones"]
                if o["nombre"] == "MiniOS10")
    assert "no viene de Microsoft" in mini["nota"] and "licencia de Windows válida" in mini["nota"], mini
    opciones = _por_id(recomendador.recomendar(_pc(1), _hechos_reco()), "so")["opciones"]
    assert opciones[-1]["nombre"] == "Windows 7" and "actualizaciones de seguridad" in opciones[-1]["nota"], opciones


def _variables_css(texto, selector):
    """Variables --nombre: valor del bloque `selector { ... }` (sin comentarios)."""
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    bloque = re.search(re.escape(selector) + r"\s*\{(.*?)\}", texto, flags=re.S)
    assert bloque, f"no hay bloque {selector}"
    return {n: v.strip() for n, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", bloque.group(1))}


def _luminancia(color):
    canales = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(a, b):
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


_ESTADOS_PALETA = ("normal", "advertencia", "sospecha", "critico", "nodeterminado")
_TOKENS_PALETA = (
    ["--color-fondo", "--color-tarjeta", "--color-texto", "--color-texto-secundario", "--color-verde",
     "--color-amarillo", "--color-naranja", "--color-rojo", "--color-acento", "--color-borde",
     "--radio-borde", "--sombra-tarjeta", "--color-marino", "--color-sobre-marino", "--color-borde-control",
     "--radio-1", "--radio-2", "--sombra-1", "--sombra-2", "--fuente"]
    + [f"--color-estado-{e}-fondo" for e in _ESTADOS_PALETA]
    + [f"--espacio-{i}" for i in range(1, 9)]
    + [f"--texto-{t}" for t in ("xs", "s", "m", "l", "xl", "xxl")])


def test_paleta():
    raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    with open(os.path.join(raiz, "config", "palette.css"), encoding="utf-8") as f:
        paleta = f.read()
    with open(os.path.join(raiz, "frontend", "static", "css", "style.css"), encoding="utf-8") as f:
        estilos = f.read()
    temas = {"claro": _variables_css(paleta, ":root"),
             "oscuro": _variables_css(paleta, ':root[data-theme="dark"]')}

    # (h) mismos nombres en ambos temas
    assert set(temas["claro"]) == set(temas["oscuro"]), set(temas["claro"]) ^ set(temas["oscuro"])

    # (g) toda var(--x) de style.css (sin contar el respaldo) está definida en ambos temas, salvo las
    # propiedades locales que la propia hoja declara (p. ej. --estado-color), cuyo valor sí sale de la paleta
    sin_coment = re.sub(r"/\*.*?\*/", "", estilos, flags=re.S)
    locales = set(re.findall(r"(--[\w-]+)\s*:", sin_coment))
    usadas = set(re.findall(r"var\(\s*(--[\w-]+)", sin_coment)) - locales
    for tema, v in temas.items():
        assert usadas <= set(v), (tema, sorted(usadas - set(v)))
        # una propiedad local con el mismo nombre que un token taparía a la paleta (y a su tema oscuro)
        assert not (locales & set(v)), (tema, sorted(locales & set(v)))

    # (i) color-scheme declarado en cada tema (controles y barras de desplazamiento nativos)
    sin_comentarios = re.sub(r"/\*.*?\*/", "", paleta, flags=re.S)
    for selector, esquema in ((":root", "light"), (':root[data-theme="dark"]', "dark")):
        bloque = re.search(re.escape(selector) + r"\s*\{(.*?)\}", sin_comentarios, flags=re.S).group(1)
        assert re.search(r"(?<![\w-])color-scheme\s*:\s*" + esquema + r"\s*;", bloque), (selector, esquema)

    for tema, v in temas.items():
        # (a) tokens presentes
        faltan = [t for t in _TOKENS_PALETA if t not in v]
        assert not faltan, (tema, faltan)
        tarjeta, fondo = v["--color-tarjeta"], v["--color-fondo"]
        # (b) texto sobre tarjeta y fondo
        for t in ("--color-texto", "--color-texto-secundario"):
            for base in (tarjeta, fondo):
                assert _contraste(v[t], base) >= 4.5, (tema, t, base, _contraste(v[t], base))
        # (c) estados y acento sobre tarjeta
        for t in ("--color-verde", "--color-amarillo", "--color-naranja", "--color-rojo", "--color-acento"):
            assert _contraste(v[t], tarjeta) >= 4.5, (tema, t, _contraste(v[t], tarjeta))
        # (d) texto sobre la barra marino
        assert _contraste(v["--color-sobre-marino"], v["--color-marino"]) >= 4.5, tema
        # (d2) texto de los botones de acento
        assert _contraste(v["--color-sobre-acento"], v["--color-acento"]) >= 4.5, tema
        # (c2) estados y acento también sobre el fondo de la página
        for t in ("--color-verde", "--color-amarillo", "--color-naranja", "--color-rojo", "--color-acento"):
            assert _contraste(v[t], fondo) >= 4.5, (tema, t, "fondo", _contraste(v[t], fondo))
        # (e) borde de controles (sobre tarjeta y sobre el fondo de la página)
        for base in (tarjeta, fondo):
            assert _contraste(v["--color-borde-control"], base) >= 3.0, (tema, base, _contraste(v["--color-borde-control"], base))
        # (f) chip: color de estado sobre su fondo teñido ("no determinado" usa el texto secundario)
        colores = {"normal": "--color-verde", "advertencia": "--color-amarillo", "sospecha": "--color-naranja",
                   "critico": "--color-rojo", "nodeterminado": "--color-texto-secundario"}
        for e, t in colores.items():
            r = _contraste(v[t], v[f"--color-estado-{e}-fondo"])
            assert r >= 4.5, (tema, e, r)
            # (f2) franja de avisos: texto normal sobre el fondo teñido del estado
            r = _contraste(v["--color-texto"], v[f"--color-estado-{e}-fondo"])
            assert r >= 4.5, (tema, e, "texto", r)


def test_frontend_node():
    """Pruebas de lógica pura del frontend con node (se omiten si node no está instalado)."""
    if not shutil.which("node"):
        return
    raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    r = subprocess.run(["node", os.path.join("frontend", "tests", "modelo.test.js")], cwd=raiz,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr


# Única inserción de HTML permitida por nombre: cadenas CONSTANTES de iconos.js, y solo en dom.js.
_HTML_PERMITIDO = {"dom.js": ('marco.insertAdjacentHTML("beforeend", svg);',)}
_INSERTA_HTML = re.compile(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|createContextualFragment|DOMParser|srcdoc")


def _una_llamada_escapar(expr):
    """True si expr es UNA sola llamada escapar(...) con paréntesis balanceados (no `escapar(a) + g(b)`)."""
    if not (expr.startswith("escapar(") and expr.endswith(")")):
        return False
    prof = 0
    for i, c in enumerate(expr[7:], 7):
        prof += (c == "(") - (c == ")")
        if prof == 0:
            return i == len(expr) - 1
    return False


def _html_seguro(linea):
    """Asignaciones a innerHTML aceptadas: literal sin ${ ni +; `...${escapar(...)}...` con TODA expresión
    envuelta en escapar(); o `= escapar(...)` completo. Cualquier otra cosa (p. ej. concatenar) es insegura."""
    if re.search(r"""\.innerHTML\s*=\s*("[^"$+]*"|'[^'$+]*')\s*;?\s*$""", linea):
        return True
    m = re.search(r"\.innerHTML\s*=\s*`([^`]*)`\s*;?\s*$", linea)
    if m:
        return all(_una_llamada_escapar(e) for e in re.findall(r"\$\{(.*?)\}", m.group(1)))
    return bool(re.search(r"\.innerHTML\s*=\s*escapar\((?:[^()]|\([^()]*\))*\)\s*;?\s*$", linea))


def test_frontend_sin_innerhtml_inseguro():
    """Toda línea de frontend/static/js/*.js que inserta HTML pasa _html_seguro, o es la inserción
    de íconos constantes de dom.js (lista blanca por archivo)."""
    carpeta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "static", "js")
    # La propia regla rechaza lo que debe rechazar.
    assert _html_seguro("x.innerHTML = `<b>${escapar(a)}</b>`;")
    assert _html_seguro("x.innerHTML = escapar(a);")
    assert _html_seguro("x.innerHTML = '<br>';")
    assert not _html_seguro("x.innerHTML = '<b>' + escapar(a) + b;")
    assert not _html_seguro("x.innerHTML = `<b>${a}${escapar(b)}</b>`;")
    assert not _html_seguro("x.innerHTML = escapar(a) + b;")
    assert _html_seguro("x.innerHTML = `<b>${escapar(f(a))}</b>`;")
    assert not _html_seguro("x.innerHTML = `<b>${escapar(a) + g(b)}</b>`;")
    assert not _html_seguro("x.innerHTML = `<b>${escapar(a)) + g(b)}</b>`;")
    malas = []
    for nombre in sorted(os.listdir(carpeta)):
        if not nombre.endswith(".js"):
            continue
        with open(os.path.join(carpeta, nombre), encoding="utf-8") as f:
            for n, linea in enumerate(f, 1):
                if not _INSERTA_HTML.search(linea) or linea.lstrip().startswith("//"):
                    continue
                if _html_seguro(linea) or linea.strip() in _HTML_PERMITIDO.get(nombre, ()):
                    continue
                malas.append(f"{nombre}:{n}: {linea.strip()}")
    assert not malas, "HTML sin escapar:\n" + "\n".join(malas)


_IDS_ARMAZON = ("boton-revisar", "menu-mas", "boton-mas", "panel-resumen", "panel-componentes",
                "panel-recomendaciones", "panel-analisis", "aviso-error", "aviso-demo", "aviso-admin")


def test_indice_estructura():
    """GET / entrega el armazón nuevo: pestañas, botón único, menú Más, avisos y el script anti-parpadeo del tema."""
    def _peticiones():
        cliente = app.app.test_client()
        r = cliente.get("/")
        assert r.status_code == 200, r.status_code
        html = r.get_data(as_text=True)
        assert 'role="tablist"' in html
        for i in _IDS_ARMAZON:
            assert f'id="{i}"' in html, i
        assert 'id="boton-escanear"' not in html
        # Lectores de pantalla: región de estado del escaneo y nombre accesible del botón "Más" (el texto se oculta en pantallas angostas).
        assert re.search(r'<p[^>]*id="estado-escaneo"[^>]*role="status"|<p[^>]*role="status"[^>]*id="estado-escaneo"', html), "falta #estado-escaneo con role=status"
        assert re.search(r'<button[^>]*id="boton-mas"[^>]*aria-label="Más opciones"', html), "#boton-mas sin aria-label"
        # Script anti-parpadeo: en <head>, antes de la hoja de estilos.
        cabeza = html.split("</head>")[0]
        guion = re.search(r"<script>[^<]*tema_interfaz[^<]*</script>", cabeza)
        assert guion, "falta el script inline del tema en <head>"
        assert guion.start() < cabeza.index('<link rel="stylesheet"'), "el script del tema va antes de la hoja de estilos"
        # modelo.js se carga después de dom.js; vistas.js después de modelo.js y antes de app.js.
        orden = [html.index(f"js/{n}.js") for n in ("estado", "iconos", "dom", "modelo", "vistas", "app")]
        assert orden == sorted(orden), orden
        assert cliente.get("/static/js/modelo.js").status_code == 200
        assert cliente.get("/static/js/vistas.js").status_code == 200
        assert 'id="resumen-vista"' in html and 'id="simple-vacio"' not in html

    _en_hilo(_peticiones)


def test_indice_recomendaciones():
    """Las pestañas Recomendaciones y Análisis de Windows existen en la página; la de Análisis arranca oculta (hasta F4a)."""
    def _peticion():
        html = app.app.test_client().get("/").get_data(as_text=True)
        assert 'id="panel-recomendaciones"' in html
        assert re.search(r'<section[^>]*id="panel-analisis"[^>]*\bhidden\b', html), "panel-analisis debe llevar hidden"
        assert re.search(r'<button[^>]*id="tab-analisis"[^>]*\bhidden\b', html), "tab-analisis debe llevar hidden"
        assert 'id="recomendaciones-vista"' in html

    _en_hilo(_peticion)


_RESTOS_DEL_MAPA = ("mapa-svg", "POSICIONES_MAPA", "mapa-silueta", "resaltarComponente", "punto-etiqueta")


def test_sin_codigo_del_mapa():
    """El mapa de puntos ya no existe en ninguna parte: ni en la plantilla, ni en los scripts, ni en la hoja."""
    frontend = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
    archivos = [os.path.join(frontend, "templates", "index.html"), os.path.join(frontend, "static", "css", "style.css")]
    carpeta_js = os.path.join(frontend, "static", "js")
    archivos += [os.path.join(carpeta_js, n) for n in sorted(os.listdir(carpeta_js)) if n.endswith(".js")]
    for ruta in archivos:
        with open(ruta, encoding="utf-8") as f:
            texto = f.read()
        for resto in _RESTOS_DEL_MAPA:
            assert resto not in texto, (os.path.basename(ruta), resto)

    def _peticion():
        html = app.app.test_client().get("/").get_data(as_text=True)
        assert 'id="mapa-svg"' not in html
        assert 'id="componentes-vista"' in html

    _en_hilo(_peticion)


def test_analisis_espacio():
    for libre, esperado in ((4.9, "sospecha"), (5.0, "advertencia"), (9.9, "advertencia"), (10.0, "normal"),
                            (None, "no_determinado")):
        _assert_estado(f"espacio libre {libre}", espacio._clasificar(libre)[0], esperado)
    # Entradas imposibles (NaN, negativo, > 100) no se clasifican.
    for raro in (float("nan"), -1.0, 100.5, "7"):
        _assert_estado(f"espacio libre raro {raro!r}", espacio._clasificar(raro)[0], "no_determinado")
    # El texto no contradice el estado en los umbrales: un decimal cuando es < 10 %.
    est, msg = espacio._clasificar(9.9)
    assert est == "advertencia" and "9,9 %" in msg, msg
    est, msg = espacio._clasificar(4.9)
    assert est == "sospecha" and "4,9 %" in msg, msg
    est, msg = espacio._clasificar(9.99)  # sin redondear a 10 mientras el estado sea advertencia
    assert est == "advertencia" and "9,9 %" in msg, msg
    assert "34 %" in espacio._clasificar(34.0)[1]
    assert "disco C:" not in espacio._RECOMENDACIONES["no_determinado"]

    disco = {"unidad": "C:", "total_gb": 476.0, "libre_gb": 33.3, "usado_gb": 442.7, "libre_pct": 7.0}
    carpetas = [{"nombre": "Descargas", "ruta": "C:/Users/x/Downloads", "tamano_gb": 1.5, "archivos": 10}]
    leer_disco, leer_carpetas = espacio._leer_disco_c, espacio._leer_carpetas
    try:
        espacio._leer_disco_c = lambda: disco
        espacio._leer_carpetas = lambda: carpetas
        r = espacio.diagnosticar()
        assert set(r) == {"componente", "estado", "mensaje", "datos", "recomendacion"}
        assert r["componente"] == "espacio"
        _assert_estado("espacio simulado 7 %", r["estado"], "advertencia")
        assert r["datos"]["disco_c"]["libre_pct"] == 7.0 and r["datos"]["carpetas"] == carpetas
        assert "7,0 %" in r["mensaje"] and "33 GB de 476 GB" in r["mensaje"], r["mensaje"]
        assert r["recomendacion"]

        espacio._leer_disco_c = lambda: None
        _assert_estado("espacio sin lectura", espacio.diagnosticar()["estado"], "no_determinado")

        def _lanza():
            raise OSError("sin acceso")
        espacio._leer_disco_c = _lanza
        _assert_estado("espacio lector lanza", espacio.diagnosticar()["estado"], "no_determinado")

        espacio._leer_disco_c = lambda: disco
        espacio._leer_carpetas = _lanza
        r = espacio.diagnosticar()
        _assert_estado("espacio sin carpetas", r["estado"], "advertencia")
        assert r["datos"]["carpetas"] == []

        # Un disco mal formado (llaves ausentes, no es dict) degrada, no lanza.
        espacio._leer_carpetas = lambda: carpetas
        for malo in ({"libre_pct": 7.0}, "C:", [1, 2], {"unidad": "C:", "libre_pct": 7.0, "libre_gb": "x", "total_gb": 1}):
            espacio._leer_disco_c = lambda malo=malo: malo
            r = espacio.diagnosticar()
            _assert_estado(f"espacio disco mal formado {malo!r}", r["estado"], "no_determinado")
            assert r["recomendacion"] and r["datos"]["carpetas"] == carpetas
    finally:
        espacio._leer_disco_c, espacio._leer_carpetas = leer_disco, leer_carpetas

    # Recorrido de carpetas: cuenta archivos, respeta el tope y no entra por enlaces.
    import tempfile
    with tempfile.TemporaryDirectory() as raiz:
        for i in range(5):
            with open(os.path.join(raiz, f"a{i}.txt"), "wb") as f:
                f.write(b"x" * 100)
        os.mkdir(os.path.join(raiz, "sub"))
        with open(os.path.join(raiz, "sub", "b.txt"), "wb") as f:
            f.write(b"x" * 50)
        assert espacio._medir_carpeta(raiz, 5.0, 1000) == (550, 6, False)
        assert espacio._medir_carpeta(raiz, 5.0, 3)[2] is True
        assert espacio._medir_carpeta(os.path.join(raiz, "no_existe"), 5.0, 10) is None
        assert espacio._medir_carpeta(raiz, 0, 1000)[2] is True  # sin tiempo: parcial

        # Una junction que apunta a la propia carpeta ni cuenta doble ni entra en bucle.
        try:
            hecho = subprocess.run(["cmd", "/c", "mklink", "/J", os.path.join(raiz, "sub", "bucle"), raiz],
                                   capture_output=True, timeout=10).returncode == 0
        except Exception:
            hecho = False
        if hecho:
            assert espacio._medir_carpeta(raiz, 5.0, 1000) == (550, 6, False)
            os.rmdir(os.path.join(raiz, "sub", "bucle"))  # quita la junction sin tocar el destino

    t0 = time.perf_counter()
    r = espacio.diagnosticar()
    dt = time.perf_counter() - t0
    assert r["componente"] == "espacio" and r["estado"] in scanner.ESTADOS_VALIDOS and r["estado"] != "critico"
    assert dt <= 4.0, f"espacio tardó {dt:.1f} s"


def test_analisis_inicio():
    for total, esperado in ((9, "normal"), (10, "advertencia"), (0, "normal"), (None, "no_determinado")):
        _assert_estado(f"inicio total {total}", inicio._clasificar(total)[0], esperado)
    # StartupApproved: 02/06 = habilitado; 03/07 = deshabilitado por el usuario; lo demas cuenta como habilitado.
    assert inicio._habilitado(b"\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00") is True
    assert inicio._habilitado(b"\x06\x00\x00\x00") is True
    assert inicio._habilitado(b"\x03\x00\x00\x00\x01\x01\x01\x01\x01\x01\x01\x01") is False
    assert inicio._habilitado(b"\x07\x00\x00\x00") is False
    assert inicio._habilitado(None) is True and inicio._habilitado(b"") is True and inicio._habilitado(b"\xff\x00") is True

    def _entradas(prefijo, n, origen):
        return [{"nombre": f"{prefijo}{i}", "comando": f"C:/p/{prefijo}{i}.exe", "origen": origen, "habilitado": True}
                for i in range(n)]

    def _lanza():
        raise OSError("sin acceso")

    run, carpetas, servicios = inicio._leer_run, inicio._leer_carpetas_inicio, inicio._contar_servicios_automaticos
    try:
        inicio._contar_servicios_automaticos = lambda: 87
        inicio._leer_run = lambda: _entradas("run", 6, "usuario")
        inicio._leer_carpetas_inicio = lambda: _entradas("car", 5, "equipo")
        r = inicio.diagnosticar()
        assert set(r) == {"componente", "estado", "mensaje", "datos", "recomendacion"} and r["componente"] == "inicio"
        _assert_estado("inicio 11 habilitadas", r["estado"], "advertencia")
        assert r["datos"]["total"] == 11 and len(r["datos"]["entradas"]) == 11
        assert r["datos"]["servicios_automaticos"] == 87 and "11 programas" in r["mensaje"], r["mensaje"]
        assert r["recomendacion"]

        # Dos deshabilitadas en el Administrador de tareas: salen en la lista pero no cuentan.
        inicio._leer_run = lambda: _entradas("run", 6, "usuario")[:4] + [
            {**e, "habilitado": False} for e in _entradas("off", 2, "usuario")]
        r = inicio.diagnosticar()
        assert r["datos"]["total"] == 9 and len(r["datos"]["entradas"]) == 11
        assert sum(1 for e in r["datos"]["entradas"] if e["habilitado"] is False) == 2
        _assert_estado("inicio 9 habilitadas + 2 deshabilitadas", r["estado"], "normal")

        # Un lector que lanza se ignora; todos lanzando -> no_determinado; servicios None no rompe.
        inicio._leer_run = _lanza
        inicio._contar_servicios_automaticos = lambda: None
        r = inicio.diagnosticar()
        assert r["datos"]["total"] == 5 and r["datos"]["servicios_automaticos"] is None
        inicio._leer_carpetas_inicio = _lanza
        r = inicio.diagnosticar()
        _assert_estado("inicio sin fuentes", r["estado"], "no_determinado")
        assert r["datos"]["entradas"] == []

        # Datos hostiles: se conservan crudos (el escape se hace al mostrar).
        hostil = {"nombre": "<script>alert(1)</script>", "comando": "a & b", "origen": "usuario"}
        inicio._leer_run = lambda: [hostil]
        inicio._leer_carpetas_inicio = lambda: []
        r = inicio.diagnosticar()
        assert r["datos"]["entradas"][0]["nombre"] == "<script>alert(1)</script>"
        assert r["datos"]["entradas"][0]["habilitado"] is True and r["datos"]["total"] == 1

        # Muchísimas entradas: lista acotada a 200, total real.
        inicio._leer_run = lambda: _entradas("m", 300, "equipo")
        r = inicio.diagnosticar()
        assert len(r["datos"]["entradas"]) == 200 and r["datos"]["total"] == 300
        json.dumps(r)
    finally:
        inicio._leer_run, inicio._leer_carpetas_inicio = run, carpetas
        inicio._contar_servicios_automaticos = servicios

    # Sin APPDATA/ProgramData no se arma una ruta relativa: esa fuente se salta.
    guardado = {k: os.environ.get(k) for k in ("APPDATA", "ProgramData")}
    import tempfile
    carpeta_actual = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as raiz:
            try:
                os.chdir(raiz)
                sub = os.path.join(raiz, r"Microsoft\Windows\Start Menu\Programs\Startup")
                os.makedirs(sub)
                open(os.path.join(sub, "relativo.lnk"), "w").close()
                os.environ["APPDATA"] = ""
                os.environ.pop("ProgramData", None)
                try:
                    inicio._leer_carpetas_inicio()
                    raise AssertionError("sin APPDATA/ProgramData no debe leer ninguna carpeta")
                except OSError:
                    pass  # ninguna fuente usable: "no se pudo leer", sin leer la ruta relativa
                os.environ["APPDATA"] = raiz  # con la variable puesta sí se lee esa fuente
                assert [e["nombre"] for e in inicio._leer_carpetas_inicio()] == ["relativo.lnk"]
            finally:
                os.chdir(carpeta_actual)
    finally:
        os.chdir(carpeta_actual)
        for k, v in guardado.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    t0 = time.perf_counter()
    r = inicio.diagnosticar()
    dt = time.perf_counter() - t0
    assert set(r) == {"componente", "estado", "mensaje", "datos", "recomendacion"} and r["componente"] == "inicio"
    assert r["estado"] in scanner.ESTADOS_VALIDOS and r["estado"] != "critico"
    assert dt <= 4.0, f"inicio tardó {dt:.1f} s"


def test_analisis_programas():
    hoy = datetime.date(2026, 10, 22)
    # Fechas: hasta 30 días atrás es reciente; ausente, mal formada o futura no cuenta (y no lanza).
    for fecha, esperado in (("20261015", True), ("20260922", True), ("20261022", True), ("20260921", False),
                            ("20260801", False), ("20261101", False), (None, False), ("", False), ("abc", False),
                            ("20261340", False), ("2026-10-15", False), (20261015, False)):
        assert programas._es_reciente(fecha, hoy) is esperado, (fecha, esperado)

    def _p(nombre, editor="", fecha=None, oculto=False, origen="registro", version="1.0"):
        return {"nombre": nombre, "version": version, "editor": editor, "fecha": fecha, "oculto": oculto, "origen": origen}

    def _recientes(n, editor="", oculto=False):
        return [_p(f"Prog{i}", editor, "20261010", oculto) for i in range(n)]

    for nombre, lista, esperado in (
            ("3 recientes sin editor", _recientes(3), "advertencia"),
            ("2 recientes sin editor", _recientes(2), "normal"),
            ("3 pero uno con editor", _recientes(2) + [_p("Conocido", "Microsoft Corporation", "20261010")], "normal"),
            ("editor 'Unknown'/'Desconocido'/espacios",
             [_p("A", "Unknown", "20261010"), _p("B", "  DESCONOCIDO ", "20261010"), _p("C", "   ", "20261010")], "advertencia"),
            ("3 sin editor pero viejos", [_p(f"V{i}", "", "20250101") for i in range(3)], "normal"),
            ("3 sin editor con fecha futura o ausente", [_p("F", "", "20271010"), _p("G", "", None), _p("H", "", "xx")], "normal"),
            ("ocultos no cuentan (parches de Windows)", _recientes(3, oculto=True), "normal"),
            ("menu Inicio sin editor ni fecha", [_p("Reg", "X", "20200101")] + [_p(f"T{i}", None, None, origen="menu_inicio") for i in range(5)], "normal"),
            ("solo menu Inicio (registro ilegible)", [_p(f"T{i}", None, None, origen="menu_inicio") for i in range(5)], "no_determinado")):
        _assert_estado(f"programas {nombre}", programas._clasificar(lista, hoy)[0], esperado)
    msg = programas._clasificar(_recientes(3) + [_p("Oc", "x", None, True)], hoy)[1]
    assert "4 programas instalados" in msg and "1 oculto" in msg and "3 programas recientes sin editor" in msg, msg
    assert "ocultos" not in programas._clasificar(_recientes(1, "x"), hoy)[1]
    # El menú Inicio se cuenta aparte de los instalados.
    msg = programas._clasificar([_p("A", "X"), _p("B", "X", oculto=True)] + [_p(f"M{i}", None, origen="menu_inicio") for i in range(3)], hoy)[1]
    assert msg == "Hay 2 programas instalados (1 oculto por Windows) y 3 accesos en el menú Inicio.", msg
    msg = programas._clasificar([_p("A", "X"), _p("M", None, origen="menu_inicio")], hoy)[1]
    assert msg == "Hay 1 programa instalado y 1 acceso en el menú Inicio.", msg
    assert "menú Inicio" not in programas._clasificar([_p("A", "X")], hoy)[1]

    registro = [_p("Zeta", "Zeta SA", "20200101"), _p("alfa", "Alfa SA", "20200101"), _p("Beta", "Beta SA", "20200101"),
                _p("KB123456", "Microsoft", "20261010", oculto=True)]
    tienda = [_p("Calculadora", None, origen="menu_inicio", version=None), _p("ZETA", None, origen="menu_inicio", version=None)]
    leer_registro, leer_tienda = programas._leer_registro, programas._leer_aplicaciones_inicio

    def _lanza():
        raise OSError("sin acceso")

    try:
        programas._leer_registro = lambda: [dict(x) for x in registro]
        programas._leer_aplicaciones_inicio = lambda: [dict(x) for x in tienda]
        r = programas.diagnosticar()
        assert set(r) == {"componente", "estado", "mensaje", "datos", "recomendacion"} and r["componente"] == "programas"
        _assert_estado("programas simulados", r["estado"], "normal")
        assert r["datos"]["total"] == 5 and r["datos"]["ocultos"] == 1, r["datos"]
        assert r["datos"]["instalados"] == 4 and r["datos"]["en_menu_inicio"] == 1
        nombres = [x["nombre"] for x in r["datos"]["programas"]]
        assert nombres == ["alfa", "Beta", "Calculadora", "Zeta", "KB123456"], nombres  # sin duplicado; oculto al final
        assert r["mensaje"] == "Hay 4 programas instalados (1 oculto por Windows) y 1 acceso en el menú Inicio.", r["mensaje"]
        assert r["datos"]["recientes_sin_editor"] == [] and r["recomendacion"]

        # Review Focus 4: tres recientes sin editor entre otros.
        programas._leer_registro = lambda: registro + _recientes(3)
        r = programas.diagnosticar()
        _assert_estado("programas 3 recientes sin editor", r["estado"], "advertencia")
        assert sorted(r["datos"]["recientes_sin_editor"]) == ["Prog0", "Prog1", "Prog2"]
        assert "3 programas recientes sin editor" in r["mensaje"] and r["recomendacion"]

        # Review Focus 1: datos hostiles se conservan crudos (el escape se hace al mostrar).
        programas._leer_registro = lambda: [_p("<img src=x onerror=alert(1)>", "A & B", "20200101")]
        programas._leer_aplicaciones_inicio = lambda: []
        r = programas.diagnosticar()
        assert r["datos"]["programas"][0]["nombre"] == "<img src=x onerror=alert(1)>"
        assert r["datos"]["programas"][0]["editor"] == "A & B"
        json.dumps(r)

        # Un lector que lanza se ignora; ambos lanzando o vacíos -> no_determinado.
        programas._leer_registro = _lanza
        programas._leer_aplicaciones_inicio = lambda: [dict(x) for x in tienda]
        r = programas.diagnosticar()
        _assert_estado("programas sin registro", r["estado"], "no_determinado")
        assert r["datos"]["total"] is None and r["datos"]["instalados"] is None and r["datos"]["en_menu_inicio"] == 2
        assert "No se pudo leer" in r["mensaje"] and "2 accesos" in r["mensaje"], r["mensaje"]
        programas._leer_registro = lambda: [dict(x) for x in registro]
        programas._leer_aplicaciones_inicio = _lanza
        assert programas.diagnosticar()["datos"]["total"] == 4
        programas._leer_aplicaciones_inicio = _lanza
        programas._leer_registro = _lanza
        r = programas.diagnosticar()
        _assert_estado("programas ambos lanzan", r["estado"], "no_determinado")
        assert r["datos"]["total"] is None and r["datos"]["programas"] == [] and r["recomendacion"]
        programas._leer_registro = lambda: []
        programas._leer_aplicaciones_inicio = lambda: []
        _assert_estado("programas ambos vacíos", programas.diagnosticar()["estado"], "no_determinado")
        # Entradas mal formadas de un lector simulado se descartan sin lanzar.
        programas._leer_registro = lambda: [None, "x", {"version": "1"}, _p("Bien", "X", "20200101")]
        r = programas.diagnosticar()
        assert r["datos"]["total"] == 1 and r["datos"]["programas"][0]["nombre"] == "Bien"

        # Review Focus 3: 500 programas -> lista de 300, total real, JSON serializable; recientes acotados a 20.
        reciente = datetime.date.today().strftime("%Y%m%d")
        programas._leer_registro = lambda: [_p(f"P{i:03d}", "", reciente) for i in range(500)]
        r = programas.diagnosticar()
        assert len(r["datos"]["programas"]) == 300 and r["datos"]["total"] == 500
        assert len(r["datos"]["recientes_sin_editor"]) == 20
        _assert_estado("programas 500 recientes", r["estado"], "advertencia")
        assert "500 programas" in r["mensaje"]
        json.dumps(r)
    finally:
        programas._leer_registro, programas._leer_aplicaciones_inicio = leer_registro, leer_tienda

    # _leer_registro con un winreg simulado: tipos, ocultos, duplicados y claves cerradas.
    class _Clave:
        def __init__(self, valores=None, subs=None):
            self.valores, self.subs, self.abierta = valores or {}, subs or {}, True

        def __enter__(self):
            return self

        def __exit__(self, *a):
            self.abierta = False

    abiertas = []
    real_winreg = winreg
    HKLM, HKCU = real_winreg.HKEY_LOCAL_MACHINE, real_winreg.HKEY_CURRENT_USER
    arbol = {
        (HKLM, programas._UNINSTALL): {
            "a": {"DisplayName": "Normal", "DisplayVersion": "1.0", "Publisher": "Editor SA", "InstallDate": "20261001"},
            "b": {"DisplayName": "Componente", "SystemComponent": 1},
            "c": {"DisplayName": "ComponenteTexto", "SystemComponent": "1"},
            "d": {"DisplayName": "Parche", "ParentKeyName": "OperatingSystem"},
            "e": {"DisplayName": "ParentVacio", "ParentKeyName": "  "},
            "f": {"Publisher": "Sin nombre"},
            "g": {"DisplayName": b"bytes", "DisplayVersion": 7, "InstallDate": 20261001},
            "i": {"DisplayName": "Fechado", "DisplayVersion": "1"},
            "h": {"DisplayName": "Basura", "Publisher": b"\x00\x01", "InstallDate": "ayer", "SystemComponent": 0},
        },
        (HKLM, programas._CLAVES[1][1]): {
            "a32": {"DisplayName": "NORMAL", "DisplayVersion": "1.0", "InstallDate": "20261002", "SystemComponent": 1},
            "i32": {"DisplayName": "fechado", "DisplayVersion": "1", "InstallDate": "20261003"},
        },
        (HKCU, programas._UNINSTALL): {
            "u": {"DisplayName": "Normal", "DisplayVersion": "2.0", "InstallDate": "20260101"},
        },
    }

    class _WinregFalso:
        HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER = HKLM, HKCU

        @staticmethod
        def OpenKey(base, ruta):
            if isinstance(base, _Clave):
                clave = _Clave(base.subs[ruta])
            elif (base, ruta) in arbol:
                clave = _Clave(subs=arbol[(base, ruta)])
            else:
                raise FileNotFoundError(ruta)
            abiertas.append(clave)
            return clave

        @staticmethod
        def QueryInfoKey(clave):
            return (len(clave.subs), 0, 0)

        @staticmethod
        def EnumKey(clave, i):
            return list(clave.subs)[i]

        @staticmethod
        def QueryValueEx(clave, nombre):
            if nombre not in clave.valores:
                raise FileNotFoundError(nombre)
            return clave.valores[nombre], 1

    winreg_original = programas.winreg
    try:
        programas.winreg = _WinregFalso
        leido = {(x["nombre"], x["version"]): x for x in programas._leer_registro()}
    finally:
        programas.winreg = winreg_original
    assert not any(k.abierta for k in abiertas) and len(abiertas) == 3 + 12, "todas las claves deben cerrarse"
    assert set(leido) == {("Normal", "1.0"), ("Componente", None), ("ComponenteTexto", None), ("Parche", None),
                          ("ParentVacio", None), ("Fechado", "1"), ("Basura", None), ("Normal", "2.0")}, sorted(map(str, leido))
    assert leido[("Fechado", "1")]["fecha"] == "20261003"  # se conserva la primera fecha no vacía de las copias
    n1 = leido[("Normal", "1.0")]
    assert n1["editor"] == "Editor SA" and n1["fecha"] == "20261001" and n1["oculto"] is False  # NORMAL (32 bits) es la misma
    assert leido[("Componente", None)]["oculto"] is True and leido[("ComponenteTexto", None)]["oculto"] is True
    assert leido[("Parche", None)]["oculto"] is True and leido[("ParentVacio", None)]["oculto"] is False
    assert leido[("Basura", None)] == {"nombre": "Basura", "version": None, "editor": None, "fecha": None,
                                       "oculto": False, "origen": "registro"}
    json.dumps(list(leido.values()))

    # Salida de PowerShell: lista, objeto único (un solo programa), vacía o basura.
    assert programas._parsear_aplicaciones('[{"Name":"Calc","AppID":"x"},{"Name":"Fotos","AppID":"y"}]') == [
        {"nombre": "Calc", "version": None, "editor": None, "fecha": None, "oculto": False, "origen": "menu_inicio"},
        {"nombre": "Fotos", "version": None, "editor": None, "fecha": None, "oculto": False, "origen": "menu_inicio"}]
    assert [x["nombre"] for x in programas._parsear_aplicaciones('{"Name":"Unica","AppID":"x"}')] == ["Unica"]
    for basura in ("", "no es json", "null", '"texto"', '[{"AppID":"x"}, 5]', None):
        assert programas._parsear_aplicaciones(basura) == [], basura

    # Sin PowerShell, con tiempo agotado o con error: [] sin lanzar (y sin ventana).
    which, run = programas.shutil.which, programas.subprocess.run
    try:
        programas.shutil.which = lambda _n: None
        assert programas._leer_aplicaciones_inicio() == []
        programas.shutil.which = lambda _n: "powershell.exe"

        def _agota(*a, **k):
            raise subprocess.TimeoutExpired("powershell", 6)
        programas.subprocess.run = _agota
        assert programas._leer_aplicaciones_inicio() == []

        visto = {}

        def _falso(args, **k):
            visto.update(k)
            return subprocess.CompletedProcess(args, 0, stdout='{"Name":"Unica"}', stderr="")
        programas.subprocess.run = _falso
        assert [x["nombre"] for x in programas._leer_aplicaciones_inicio()] == ["Unica"]
        assert visto["timeout"] == 6 and visto["creationflags"] == subprocess.CREATE_NO_WINDOW
        assert visto["stdin"] == subprocess.DEVNULL
        programas.subprocess.run = lambda args, **k: subprocess.CompletedProcess(args, 1, stdout='{"Name":"X"}', stderr="e")
        assert programas._leer_aplicaciones_inicio() == []
    finally:
        programas.shutil.which, programas.subprocess.run = which, run

    # Llamada real: contrato, estado válido, serializable y dentro del tiempo.
    t0 = time.perf_counter()
    r = programas.diagnosticar()
    dt = time.perf_counter() - t0
    assert set(r) == {"componente", "estado", "mensaje", "datos", "recomendacion"} and r["componente"] == "programas"
    assert r["estado"] in scanner.ESTADOS_VALIDOS and r["estado"] != "critico"
    assert r["datos"]["total"] is None or r["datos"]["total"] >= len(r["datos"]["programas"])
    json.dumps(r)
    assert dt <= 8.0, f"programas tardó {dt:.1f} s"


def test_analisis_rendimiento():
    sano = {"ram_uso": 50.0, "ram_total_gb": 16.0, "disco_c_libre_pct": 40.0, "disco_tipo": "ssd",
            "disco_ocupado_pct": 5.0, "cpu_uso": 20.0, "procesos": [], "inicio_total": 4}

    def ids(**cambios):
        return [c["id"] for c in rendimiento._causas({**sano, **cambios})]

    # (a) cada causa con su condición y sus números en la evidencia
    assert rendimiento._causas(sano) == []
    c = rendimiento._causas({**sano, "ram_uso": 93.0})
    assert [x["id"] for x in c] == ["ram"] and any("93" in e for e in c[0]["evidencia"]), c
    assert set(c[0]) == {"id", "titulo", "evidencia"} and c[0]["titulo"]
    assert ids(ram_uso=89.9) == [] and ids(ram_uso=90) == ["ram"]
    c = rendimiento._causas({**sano, "disco_c_libre_pct": 8.0})
    assert [x["id"] for x in c] == ["espacio"] and any("8" in e for e in c[0]["evidencia"]), c
    assert ids(disco_c_libre_pct=10.0) == [] and ids(disco_c_libre_pct=9.9) == ["espacio"]
    c = rendimiento._causas({**sano, "disco_tipo": "hdd", "disco_ocupado_pct": 95.0})
    assert [x["id"] for x in c] == ["disco_lento"] and any("95" in e for e in c[0]["evidencia"]), c
    assert ids(disco_tipo="ssd", disco_ocupado_pct=95.0) == []
    assert ids(disco_tipo="desconocido", disco_ocupado_pct=95.0) == []
    assert ids(disco_tipo="hdd", disco_ocupado_pct=89.0) == []

    def proc(cpu):
        return [{"nombre": "chrome.exe", "cpu": cpu, "ram_mb": 300.0}]

    c = rendimiento._causas({**sano, "cpu_uso": 95.0, "procesos": proc(60.0)})
    assert [x["id"] for x in c] == ["cpu"] and any("chrome.exe" in e for e in c[0]["evidencia"]), c
    assert ids(cpu_uso=95.0, procesos=proc(49.0)) == [] and ids(cpu_uso=95.0, procesos=[]) == []
    assert ids(cpu_uso=89.0, procesos=proc(60.0)) == []
    c = rendimiento._causas({**sano, "inicio_total": 12})
    assert [x["id"] for x in c] == ["inicio"] and any("12" in e for e in c[0]["evidencia"]), c
    assert ids(inicio_total=9) == []
    # Dato ausente, mal tipado o NaN: no se afirma nada.
    vacio = {"ram_uso": None, "disco_c_libre_pct": None, "disco_tipo": "hdd", "disco_ocupado_pct": None,
             "cpu_uso": None, "procesos": [{"nombre": "x", "cpu": 99.0, "ram_mb": 1.0}], "inicio_total": None}
    assert rendimiento._causas(vacio) == [] and rendimiento._causas({}) == []
    assert rendimiento._causas({"ram_uso": "alto", "disco_c_libre_pct": float("nan"), "inicio_total": True,
                                "cpu_uso": float("nan"), "procesos": "no"}) == []
    # (b) orden de prioridad con varias causas
    todo = {"ram_uso": 95.0, "disco_c_libre_pct": 5.0, "disco_tipo": "hdd", "disco_ocupado_pct": 99.0,
            "cpu_uso": 97.0, "procesos": proc(70.0), "inicio_total": 15}
    assert [x["id"] for x in rendimiento._causas(todo)] == ["ram", "espacio", "disco_lento", "cpu", "inicio"]
    # (c) clasificación
    assert rendimiento._clasificar([], True)[0] == "normal"
    assert "foto del momento" in rendimiento._clasificar([], True)[1]
    assert rendimiento._clasificar([], False)[0] == "no_determinado"
    uno = rendimiento._causas({**sano, "ram_uso": 93.0})
    e, m = rendimiento._clasificar(uno, True)
    assert e == "advertencia" and uno[0]["titulo"] in m and "Hay otra" not in m, m
    dos = rendimiento._causas({**sano, "ram_uso": 93.0, "inicio_total": 12})
    e, m = rendimiento._clasificar(dos, True)
    assert e == "advertencia" and dos[0]["titulo"] in m and "Hay otra posible." in m, m
    cinco = rendimiento._causas(todo)
    e, m = rendimiento._clasificar(cinco, True)
    assert e == "advertencia" and cinco[0]["titulo"] in m and "Hay otras 4 posibles." in m, m

    # (d) diagnosticar con _medir simulado
    def medicion(**cambios):
        return {**sano, "procesos_cpu": [], "procesos_ram": [], **cambios}

    original = rendimiento._medir
    try:
        rendimiento._medir = lambda: medicion(ram_uso=93.0, inicio_total=12,
                                             procesos_cpu=[{"nombre": "a.exe", "cpu": 10.0, "ram_mb": 5.0}],
                                             procesos_ram=[{"nombre": "b.exe", "cpu": 1.0, "ram_mb": 900.0}])
        r = rendimiento.diagnosticar()
        assert set(r) == {"componente", "estado", "mensaje", "datos", "recomendacion"} and r["componente"] == "rendimiento"
        _assert_estado("rendimiento 2 causas", r["estado"], "advertencia")
        assert [x["id"] for x in r["datos"]["causas"]] == ["ram", "inicio"] and "Hay otra posible." in r["mensaje"], r["mensaje"]
        assert set(r["datos"]) == {"causas", "medicion", "procesos_cpu", "procesos_ram"}
        assert r["datos"]["procesos_cpu"][0]["nombre"] == "a.exe" and r["datos"]["procesos_ram"][0]["ram_mb"] == 900.0
        assert r["datos"]["medicion"]["ram_uso"] == 93.0 and "procesos_cpu" not in r["datos"]["medicion"]
        assert r["recomendacion"]
        json.dumps(r)
        rendimiento._medir = lambda: medicion()
        r = rendimiento.diagnosticar()
        _assert_estado("rendimiento sano", r["estado"], "normal")
        assert r["datos"]["causas"] == [] and r["recomendacion"]
        # Ni RAM ni CPU: no se midió lo esencial.
        rendimiento._medir = lambda: medicion(ram_uso=None, cpu_uso=None)
        _assert_estado("rendimiento sin ram ni cpu", rendimiento.diagnosticar()["estado"], "no_determinado")
        # Solo falta la CPU: lo demás se evalúa.
        rendimiento._medir = lambda: medicion(cpu_uso=None, ram_uso=95.0)
        _assert_estado("rendimiento sin cpu", rendimiento.diagnosticar()["estado"], "advertencia")

        def _lanza():
            raise OSError("sin acceso")

        rendimiento._medir = _lanza
        r = rendimiento.diagnosticar()
        _assert_estado("rendimiento _medir lanza", r["estado"], "no_determinado")
        assert r["datos"]["causas"] == [] and "No se pudo medir" in r["mensaje"] and r["recomendacion"]
        json.dumps(r)
        rendimiento._medir = lambda: "basura"
        _assert_estado("rendimiento _medir mal formado", rendimiento.diagnosticar()["estado"], "no_determinado")

        # (e) nombre de proceso hostil: se conserva crudo (el escape se hace al mostrar), en causa y en listas.
        hostil = [{"nombre": "<b>x</b>", "cpu": 80.0, "ram_mb": 10.0}]
        rendimiento._medir = lambda: medicion(cpu_uso=96.0, procesos=hostil, procesos_cpu=hostil, procesos_ram=hostil)
        r = rendimiento.diagnosticar()
        assert r["datos"]["procesos_cpu"][0]["nombre"] == "<b>x</b>"
        assert r["datos"]["causas"][0]["id"] == "cpu" and any("<b>x</b>" in e for e in r["datos"]["causas"][0]["evidencia"])
        json.dumps(r)
        # Listas acotadas a 5.
        muchos = [{"nombre": f"p{i}", "cpu": 1.0, "ram_mb": 1.0} for i in range(20)]
        rendimiento._medir = lambda: medicion(procesos_cpu=muchos, procesos_ram=muchos)
        r = rendimiento.diagnosticar()
        assert len(r["datos"]["procesos_cpu"]) == 5 and len(r["datos"]["procesos_ram"]) == 5
    finally:
        rendimiento._medir = original

    # (f) llamada real: contrato, estado válido, serializable y dentro del tiempo.
    t0 = time.perf_counter()
    r = rendimiento.diagnosticar()
    dt = time.perf_counter() - t0
    assert set(r) == {"componente", "estado", "mensaje", "datos", "recomendacion"} and r["componente"] == "rendimiento"
    assert r["estado"] in scanner.ESTADOS_VALIDOS and r["estado"] != "critico"
    assert len(r["datos"]["procesos_cpu"]) <= 5 and len(r["datos"]["procesos_ram"]) <= 5
    json.dumps(r)
    assert dt <= 8.0, f"rendimiento tardó {dt:.1f} s"


def test_analisis_orquestador_api_informe():
    """ejecutar_analisis + /api/analisis + secciones del informe y del reporte de texto."""
    import informe
    import types
    importlib_orig = scanner.importlib
    base = {"componente": "x", "estado": "normal", "mensaje": "ok", "datos": {}, "recomendacion": "r"}

    def falso(nombre):
        if nombre.endswith("espacio"):
            return types.SimpleNamespace(diagnosticar=lambda: {**base, "componente": "espacio", "estado": "advertencia",
                "datos": {"carpetas": [{"nombre": "<b>Temp</b> & Co", "tamano_gb": 1.5}]}})
        if nombre.endswith("inicio"):
            def roto():
                raise RuntimeError("x")
            return types.SimpleNamespace(diagnosticar=roto)
        if nombre.endswith("programas"):
            return types.SimpleNamespace(diagnosticar=lambda: {"estado": "normal"})  # contrato incumplido
        return types.SimpleNamespace(diagnosticar=lambda: {**base, "componente": "rendimiento", "datos": {
            "causas": [{"id": "ram", "titulo": "RAM <i>llena</i>", "evidencia": ["Uso: 93 %"]}],
            "procesos_cpu": [{"nombre": "<script>alert(1)</script>.exe", "cpu": 62.0, "ram_mb": 10}]}})
    try:
        scanner.importlib = types.SimpleNamespace(import_module=falso)
        r = scanner.ejecutar_analisis()
        assert list(r["analisis"]) == scanner.ANALISIS and "total" in r["tiempos"], r
        assert all("guia" in v for v in r["analisis"].values()), r
        assert r["analisis"]["inicio"]["estado"] == "no_determinado" and r["analisis"]["programas"]["estado"] == "no_determinado"
        assert r["resumen"]["total_componentes"] == 7 and r["resumen"]["no_determinado"] == 2 and r["resumen"]["advertencia"] == 1, r["resumen"]

        # informe: escapado, topes de filas y ausencia sin análisis
        h = informe.generar_informe_html(_escaneo_falso(), "CRITICO", r)
        assert "Análisis de Windows" in h and "&lt;script&gt;alert(1)&lt;/script&gt;.exe" in h, h
        assert "<script>alert(1)</script>" not in h and "&lt;b&gt;Temp&lt;/b&gt; &amp; Co" in h
        assert h.index("Análisis de Windows") < h.index("Preguntas para tu técnico")
        grande = {"analisis": {"inicio": {**base, "estado": "advertencia", "datos": {
            "entradas": [{"nombre": f"p{i}", "habilitado": True} for i in range(80)]}}}}
        h2 = informe.generar_informe_html(_escaneo_falso(), "CRITICO", grande)
        assert "y 50 más" in h2 and h2.count("<li>p") == 30, h2.count("<li>p")
        assert "Análisis de Windows" not in informe.generar_informe_html(_escaneo_falso(), "CRITICO", None)
        assert "Análisis de Windows" not in informe.generar_informe_html(_escaneo_falso(), "CRITICO", {"analisis": "x"})

        # reporte de texto
        txt = utils.generar_reporte_texto(_escaneo_falso(), "CRITICO", r)
        assert "--- ANÁLISIS DE WINDOWS ---" in txt and "[advertencia] espacio" in txt, txt
        assert "ANÁLISIS DE WINDOWS" not in utils.generar_reporte_texto(_escaneo_falso(), "CRITICO")

        # endpoint: 200 con análisis; 500 si no serializa sin pisar el último guardado; el informe lo incluye
        def _peticion():
            app._ultimo_analisis = None
            c = app.app.test_client().get("/api/analisis")
            assert c.status_code == 200 and set(c.get_json()["analisis"]) == set(scanner.ANALISIS), c.status_code
            previo = app._ultimo_analisis
            assert previo is not None
            original = scanner.ejecutar_analisis
            scanner.ejecutar_analisis = lambda: {"analisis": {"x": object()}}
            try:
                c = app.app.test_client().get("/api/analisis")
                assert c.status_code == 500 and app._ultimo_analisis is previo
            finally:
                scanner.ejecutar_analisis = original
            app._ultimo_escaneo = _escaneo_falso()
            h = app.app.test_client().get("/api/informe").get_data(as_text=True)
            assert "Análisis de Windows" in h
        try:
            _en_hilo(_peticion)
        finally:
            app._ultimo_analisis = None
            app._ultimo_escaneo = None
    finally:
        scanner.importlib = importlib_orig


def test_analisis_f4b():
    from analisis import estabilidad, controladores, seguridad
    # estabilidad: solo la evidencia leída decide; None = no se pudo leer
    cl = estabilidad._clasificar
    assert cl({"pantallazos_azules": None, "apagados_inesperados": None, "errores_disco": None})[0] == "no_determinado"
    assert cl({"pantallazos_azules": 0, "apagados_inesperados": 1, "errores_disco": 0})[0] == "normal"
    assert cl({"pantallazos_azules": 1, "apagados_inesperados": 0, "errores_disco": 0})[0] == "advertencia"
    assert cl({"pantallazos_azules": 0, "apagados_inesperados": 2, "errores_disco": 0})[0] == "advertencia"
    assert cl({"pantallazos_azules": 0, "apagados_inesperados": 0, "errores_disco": 1})[0] == "sospecha"
    assert cl({"pantallazos_azules": 3, "apagados_inesperados": 0, "errores_disco": 0})[0] == "sospecha"
    # controladores
    assert [controladores._clasificar(n)[0] for n in (None, 0, 1, 2, 3)] == ["no_determinado", "normal", "advertencia", "advertencia", "sospecha"]
    # seguridad: solo la protección leída decide el estado; las señales no
    assert seguridad._clasificar({"antivirus_tiempo_real": None, "firewall": None, "uac": None})[0] == "no_determinado"
    assert seguridad._clasificar({"antivirus_tiempo_real": True, "firewall": True, "uac": None})[0] == "normal"
    assert seguridad._clasificar({"antivirus_tiempo_real": True, "firewall": False, "uac": True})[0] == "advertencia"
    # nunca lanzan ni producen critico aunque los lectores fallen
    def falla():
        raise OSError("x")
    o = (estabilidad._leer_eventos, controladores._leer_dispositivos, seguridad._leer_proteccion, seguridad._leer_senales)
    try:
        estabilidad._leer_eventos = controladores._leer_dispositivos = seguridad._leer_proteccion = seguridad._leer_senales = falla
        for m in (estabilidad, controladores, seguridad):
            r = m.diagnosticar()
            assert set(r) == {"componente", "estado", "mensaje", "datos", "recomendacion"} and r["estado"] == "no_determinado", r
    finally:
        estabilidad._leer_eventos, controladores._leer_dispositivos, seguridad._leer_proteccion, seguridad._leer_senales = o
    # reales: contrato y sin critico
    for m in (estabilidad, controladores, seguridad):
        r = m.diagnosticar()
        assert r["estado"] in scanner.ESTADOS_VALIDOS and r["estado"] != "critico", r


def test_evidencia():
    import datetime
    import os
    import re
    import sqlite3
    import tempfile
    import evidencia
    import registro
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DSPC_REGISTRO"] = os.path.join(tmp, "registro.db")
        try:
            assert evidencia.acta_html(1) is None and evidencia.comparacion_html(1) is None
            assert "No hay equipos" in evidencia.jornada_html(None)
            antes = _escaneo_falso("critico")
            despues = _escaneo_falso("normal")
            despues["componentes"]["red"] = {"componente": "red", "estado": "advertencia", "mensaje": "m", "datos": {}, "recomendacion": "r"}
            a = registro.guardar(antes, None, "CRITICO", "pc-1", "Ana <b>", "Nota <script>x</script>")
            assert evidencia.comparacion_html(a) is not None and "no tiene una revisión anterior" in evidencia.comparacion_html(a)
            b = registro.guardar(despues, {"analisis": {"seguridad": {"estado": "advertencia"}}}, "ADVERTENCIA", "PC-1", "", "", {"acta": "Equipo: <i>x</i>", "marcadas": ["respaldo"]})
            otro = registro.guardar(despues, None, "NORMAL", "PC-2")
            fb, fa = registro.obtener_fila(b), registro.obtener_fila(a)
            assert registro.anterior(fb)["id"] == a and registro.anterior(fa) is None and registro.anterior(registro.obtener_fila(otro)) is None
            c = {x["nombre"]: x["tipo"] for x in evidencia.comparar(fb, fa)}
            assert c["Procesador"] == "mejoro" and c["Red"] == "nuevo" and c["Seguridad básica"] == "nuevo" and "Tarjeta Madre" not in c, c
            assert {x["tipo"] for x in evidencia.comparar(fa, fb)} >= {"empeoro", "ya_no_esta"}
            # acta: escapada, con firma, comparación y un código de integridad que cambia si se altera el registro
            h = evidencia.acta_html(b)
            assert "&lt;i&gt;x&lt;/i&gt;" in h and "<i>x</i>" not in h and "Comparación con la revisión" in h and "Mejoró" in h and "Responsable del equipo" in h
            codigo = re.search(r'class="codigo">([0-9a-f]{64})<', h).group(1)
            assert codigo == registro.huella(fb)
            ha = evidencia.acta_html(a)
            assert "Ana &lt;b&gt;" in ha and "&lt;script&gt;x&lt;/script&gt;" in ha and "<script>x" not in ha
            con = sqlite3.connect(os.environ["DSPC_REGISTRO"])
            con.execute("UPDATE equipos SET notas='alterada' WHERE id=?", (b,))
            con.commit()
            con.close()
            assert registro.huella(registro.obtener_fila(b)) != codigo
            # jornada
            hoy = datetime.date.today().isoformat()
            j = evidencia.jornada_html(hoy)
            assert "Equipos revisados: <strong>3</strong>" in j and "PC-2" in j and "Advertencia: 1" in j, j[-500:]
            assert "Equipos revisados: <strong>3</strong>" in evidencia.jornada_html("no-es-fecha")  # fecha inválida = hoy
            assert "No hay equipos" in evidencia.jornada_html("2020-01-01")
            def _peticion():
                cl = app.app.test_client()
                assert "Acta de revisión" in cl.get(f"/api/registro/{a}/acta").get_data(as_text=True)
                assert cl.get("/api/registro/999/acta").status_code == 404 and cl.get("/api/registro/999/comparar").status_code == 404
                assert "Mejoró" in cl.get(f"/api/registro/{b}/comparar").get_data(as_text=True)
                assert "Informe de la jornada" in cl.get("/api/registro/jornada").get_data(as_text=True)
            _en_hilo(_peticion)
        finally:
            os.environ.pop("DSPC_REGISTRO", None)


def test_instalador():
    import hashlib
    import json
    import os
    import tempfile
    import instalador
    import mantenimiento as m
    import postinstalacion
    originales = (m._iniciar_trabajo, utils.es_administrador, postinstalacion._programas_instalados)
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DSPC_INSTALADORES"] = tmp
        os.environ["DSPC_REGISTRO"] = os.path.join(tmp, "reg", "r.db")
        try:
            assert instalador.listar()["entradas"] == [] and instalador.huellas() == []  # sin manifiesto
            bueno, msi = os.path.join(tmp, "bueno.exe"), os.path.join(tmp, "paquete.msi")
            for ruta, datos in ((bueno, b"instalador de prueba"), (msi, b"otro")):
                with open(ruta, "wb") as f:
                    f.write(datos)
            h = hashlib.sha256(b"instalador de prueba").hexdigest()
            manifiesto = {"programas": [
                {"id": "ok", "nombre": "Bueno", "archivo": "bueno.exe", "args": ["/S"], "sha256": h.upper(), "detectar": "^bueno"},
                {"id": "msi", "nombre": "Paquete", "archivo": "paquete.msi", "args": ["/qn"], "sha256": hashlib.sha256(b"otro").hexdigest()},
                {"id": "malo", "nombre": "Cambiado", "archivo": "bueno.exe", "sha256": "0" * 64},
                {"id": "sinhash", "nombre": "Sin huella", "archivo": "bueno.exe"},
                {"id": "ruta", "nombre": "Ruta", "archivo": "..\\fuera.exe", "sha256": h},
                {"id": "ext", "nombre": "Script", "archivo": "bueno.bat", "sha256": h},
                {"id": "falta", "nombre": "Falta", "archivo": "no_esta.exe", "sha256": h},
                {"id": "MAL ID", "nombre": "x", "archivo": "bueno.exe", "sha256": h},
                {"id": "argsmalos", "nombre": "x", "archivo": "bueno.exe", "sha256": h, "args": [1]},
                "basura", {"nombre": "sin id"},
            ]}
            with open(os.path.join(tmp, "instaladores.json"), "w", encoding="utf-8") as f:
                json.dump(manifiesto, f)
            postinstalacion._programas_instalados = lambda: [{"nombre": "Bueno 1.0"}]
            r = instalador.listar()
            est = {e["id"]: e for e in r["entradas"]}
            assert set(est) == {"ok", "msi", "malo", "sinhash", "ruta", "ext", "falta"}, set(est)
            assert est["ok"]["problema"] is None and est["ok"]["instalado"] is True and est["msi"]["instalado"] is None
            assert all(est[i]["problema"] for i in ("sinhash", "ruta", "ext", "falta")) and est["malo"]["problema"] is None
            # instalar: administrador, huella que coincide y comando armado solo con datos del manifiesto
            lanzados = []
            m._iniciar_trabajo = lambda accion, cmds: (lanzados.append((accion, cmds)), {"estado": "trabajo", "mensaje": "x", "detalle": [], "trabajo": "t1"})[1]
            utils.es_administrador = lambda: False
            assert instalador.instalar("ok")["estado"] == "error" and not lanzados
            utils.es_administrador = lambda: True
            assert instalador.instalar("inventado")["estado"] == "error"
            for id_malo in ("sinhash", "ruta", "ext", "falta"):
                assert instalador.instalar(id_malo)["estado"] == "error", id_malo
            r = instalador.instalar("malo")
            assert r["estado"] == "error" and "no coincide" in r["mensaje"] and not lanzados, r
            r = instalador.instalar("ok")
            assert r["estado"] == "trabajo" and lanzados == [("instalar_ok", [[bueno, "/S"]])], lanzados
            instalador.instalar("msi")
            assert lanzados[-1][1] == [["msiexec", "/i", msi, "/qn"]], lanzados[-1]
            hs = {x["archivo"]: x["sha256"] for x in instalador.huellas()}
            assert hs["bueno.exe"] == h and set(hs) == {"bueno.exe", "paquete.msi"}, hs
            # rutas: GET listar y huellas; instalar exige JSON
            def _peticion():
                cl = app.app.test_client()
                assert len(cl.get("/api/instaladores").get_json()["entradas"]) == 7
                assert cl.get("/api/instaladores/huellas").get_json()["huellas"]
                assert cl.post("/api/instaladores/ok/instalar").status_code == 400
                assert cl.post("/api/instaladores/ok/instalar", json={}).get_json()["estado"] == "trabajo"
            _en_hilo(_peticion)
        finally:
            m._iniciar_trabajo, utils.es_administrador, postinstalacion._programas_instalados = originales
            os.environ.pop("DSPC_INSTALADORES", None)
            os.environ.pop("DSPC_REGISTRO", None)


def test_mantenimiento_y_nota():
    import os
    import tempfile
    import threading
    import time
    import mantenimiento as m
    import registro
    originales = (m._correr, m._carpetas_temp, m._entradas_inicio, m._fijar_inicio, utils.es_administrador)
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DSPC_REGISTRO"] = os.path.join(tmp, "reg", "registro.db")
        try:
            # lista cerrada, permisos y acciones desconocidas
            assert set(m.ACCIONES) >= {"temporales", "inicio", "energia", "reparar_sistema", "quitar_parche"}
            assert all(a["descripcion"] and a["riesgo"] in ("bajo", "medio") for a in m.ACCIONES.values())
            utils.es_administrador = lambda: False
            assert {a["id"]: a["disponible"] for a in m.listar()}["reparar_sistema"] is False
            assert m.ejecutar("reparar_sistema", {})["estado"] == "error" and "administrador" in m.ejecutar("reparar_sistema", {})["mensaje"]
            assert m.ejecutar("formatear_todo", {})["estado"] == "error" and m.previsualizar("formatear_todo", {})["estado"] == "error"
            utils.es_administrador = lambda: True
            assert {a["id"]: a["disponible"] for a in m.listar()}["reparar_sistema"] is True

            # temporales: la vista previa no borra; borra solo lo de más de un día y las carpetas que quedan vacías
            temp = os.path.join(tmp, "Temp")
            os.makedirs(os.path.join(temp, "sub"))
            viejo, nuevo, anidado = os.path.join(temp, "viejo.tmp"), os.path.join(temp, "nuevo.tmp"), os.path.join(temp, "sub", "viejo2.tmp")
            for ruta in (viejo, nuevo, anidado):
                with open(ruta, "wb") as f:
                    f.write(b"x" * 1000)
            hace_3_dias = time.time() - 3 * 86400
            os.utime(viejo, (hace_3_dias, hace_3_dias))
            os.utime(anidado, (hace_3_dias, hace_3_dias))
            m._carpetas_temp = lambda: [temp]
            p = m.previsualizar("temporales", {})
            assert p["estado"] == "ok" and os.path.exists(viejo) and os.path.exists(anidado), p
            r = m.ejecutar("temporales", {})
            assert r["estado"] == "ok" and not os.path.exists(viejo) and not os.path.exists(anidado) and os.path.exists(nuevo), r
            assert not os.path.exists(os.path.join(temp, "sub")), "la carpeta vacía debía borrarse"

            # inicio: nunca se ofrece ni se desactiva lo protegido o lo que no existe
            lista = [{"id": "HKCU|Run|Spotify", "nombre": "Spotify", "comando": "x", "habilitado": True, "protegido": False},
                     {"id": "HKCU|Run|Defender", "nombre": "Windows Defender", "comando": "x", "habilitado": True, "protegido": True},
                     {"id": "HKCU|Run|Apagado", "nombre": "Apagado", "comando": "x", "habilitado": False, "protegido": False}]
            m._entradas_inicio = lambda: lista
            hechos = []
            m._fijar_inicio = lambda i, h: hechos.append((i, h))
            assert [e["nombre"] for e in m.previsualizar("inicio", {})["detalle"]] == ["Spotify"]
            r = m.ejecutar("inicio", {"ids": ["HKCU|Run|Spotify", "HKCU|Run|Defender", "HKCU|Run|Inventado", 7]})
            assert hechos == [("HKCU|Run|Spotify", False)] and len(r["detalle"]["fallos"]) == 3, (hechos, r)
            assert m.ejecutar("inicio", {"ids": []})["estado"] == "error"
            assert m.ejecutar("inicio", {"ids": ["HKCU|Run|Spotify"], "accion": "reactivar"})["estado"] == "ok" and hechos[-1] == ("HKCU|Run|Spotify", True)
            assert all(m._PROTEGIDOS.search(n) for n in ("Windows Defender", "Realtek HD Audio", "NVIDIA Control", "Faronics Deep Freeze"))
            assert not m._PROTEGIDOS.search("Spotify") and not m._PROTEGIDOS.search("Discord")

            # energía y parches: solo comandos de la lista, con datos validados
            llamadas = []

            def falso(cmd, timeout=120):
                llamadas.append(cmd)
                if cmd[:2] == ["powercfg", "/getactivescheme"]:
                    return 0, "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Equilibrado)"
                return (3010, "") if cmd[0] == "wusa" else (0, "")
            m._correr = falso
            r = m.ejecutar("energia", {})
            assert r["estado"] == "ok" and r["anterior"] == "381b4222-f694-41f0-9685-ff5bb260df2e", r
            assert ["powercfg", "/setactive", m._ALTO_RENDIMIENTO] in llamadas
            assert m.ejecutar("energia", {"volver_a": "no-es-guid; calc"})["estado"] == "error"
            assert m.ejecutar("energia", {"volver_a": r["anterior"]})["estado"] == "ok"
            assert m.previsualizar("energia", {})["anterior"] == r["anterior"]
            for malo in ("", "abc", "KB12", "5120998; calc", "KB1234567890"):
                assert m.ejecutar("quitar_parche", {"kb": malo})["estado"] == "error", malo
            r = m.ejecutar("quitar_parche", {"kb": "kb5120998"})
            assert r["estado"] == "ok" and "Reinicia" in r["mensaje"] and ["wusa", "/uninstall", "/kb:5120998", "/quiet", "/norestart"] in llamadas

            # tareas largas: corren en segundo plano, solo una a la vez y quedan anotadas
            suelta = threading.Event()
            m._correr = lambda cmd, timeout=120: (suelta.wait(5), (0, "todo bien"))[1]
            r = m.ejecutar("disco", {})
            assert r["estado"] == "trabajo" and m.estado_trabajo(r["trabajo"])["estado"] == "corriendo"
            assert m.ejecutar("reparar_sistema", {})["estado"] == "error"  # ya hay una en curso
            suelta.set()
            for _ in range(50):
                if m.estado_trabajo(r["trabajo"])["estado"] != "corriendo":
                    break
                time.sleep(0.1)
            t = m.estado_trabajo(r["trabajo"])
            assert t["estado"] == "terminado" and t["codigos"] == [0] and t["salida"] == ["todo bien"], t
            assert m.estado_trabajo("no-existe") is None
            assert any(h["accion"] == "disco" for h in m.historial()) and any(h["accion"] == "temporales" for h in m.historial())
            m._correr = lambda cmd, timeout=120: (1, "avisos")
            r = m.ejecutar("velocidad_disco", {})
            for _ in range(50):
                if m.estado_trabajo(r["trabajo"])["estado"] != "corriendo":
                    break
                time.sleep(0.1)
            assert m.estado_trabajo(r["trabajo"])["estado"] == "con_avisos"
            c = m.comparar(True)
            assert set(c) == {"antes", "ahora"} and 0 <= c["ahora"]["libre_pct"] <= 100, c

            # nota automática
            esc = _escaneo_falso()
            n = registro.nota_automatica(esc, {"analisis": {"seguridad": {"estado": "advertencia", "mensaje": "Aparece desactivado: el firewall."}}},
                                         [{"titulo": "Nombre del equipo", "estado": "advertencia"}, {"titulo": "A mano", "estado": "advertencia", "manual": True}],
                                         ["temporales: Se liberaron 300 MB"])
            assert "Procesador (crítico)" in n and "Seguridad básica (advertencia)" in n and "Pendiente al instalar: Nombre del equipo." in n, n
            assert "A mano" not in n and "Mantenimiento hecho: temporales" in n and len(n) <= 1000
            assert registro.nota_automatica(None) == "" and registro.nota_automatica({"componentes": {}}) == ""
            assert "sin hallazgos" in registro.nota_automatica({"componentes": {"cpu": {"estado": "normal", "mensaje": "ok"}}})
            assert len(registro.nota_automatica({"componentes": {f"c{i}": {"estado": "critico", "mensaje": "m" * 200} for i in range(40)}})) <= 1000

            # protección web: otras páginas no pueden disparar acciones
            def _peticion():
                cl = app.app.test_client()
                assert cl.post("/api/mantenimiento/temporales/ejecutar").status_code == 400  # sin JSON (formulario de otro sitio)
                assert cl.post("/api/mantenimiento/temporales/ejecutar", data="x", content_type="text/plain").status_code == 400
                assert cl.get("/api/registro", headers={"Host": "evil.example.com"}).status_code == 400
                assert cl.get("/api/mantenimiento").status_code == 200 and cl.get("/api/mantenimiento").get_json()["acciones"]
                assert cl.post("/api/mantenimiento/temporales/previsualizar", json={}).get_json()["estado"] == "ok"
                assert cl.get("/api/mantenimiento/trabajo/xx").status_code == 404
                app._ultimo_escaneo = esc
                assert "Procesador (crítico)" in cl.post("/api/registro/nota", json={"items": []}).get_json()["nota"]
            try:
                _en_hilo(_peticion)
            finally:
                app._ultimo_escaneo = None
        finally:
            m._correr, m._carpetas_temp, m._entradas_inicio, m._fijar_inicio, utils.es_administrador = originales
            os.environ.pop("DSPC_REGISTRO", None)


def test_registro_y_postinstalacion():
    import os
    import tempfile
    import postinstalacion
    import registro
    # --- registro (F5): opt-in, validación, CSV seguro y borrado ---
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DSPC_REGISTRO"] = os.path.join(tmp, "sub", "registro.db")
        try:
            assert registro.listar() == []
            for malo in (None, {}, {"componentes": {}}):
                try:
                    registro.guardar(malo, None, "NORMAL", "PC1")
                    assert False, "debía rechazar un escaneo vacío"
                except ValueError:
                    pass
            try:
                registro.guardar(_escaneo_falso(), None, "NORMAL", "   ")
                assert False, "debía exigir etiqueta"
            except ValueError:
                pass
            n = registro.guardar(_escaneo_falso(), {"analisis": {}}, "CRITICO", "=HYPERLINK(x)", "Ana", "n" * 5000)
            fila = registro.listar()[0]
            assert fila["id"] == n and fila["veredicto"] == "CRITICO" and fila["estados"]["cpu"] == "critico", fila
            assert len(fila["notas"]) == 1000 and fila["equipo"] == "Acme <script>alert(1)</script> & Co", fila
            assert registro.obtener(n)["escaneo"]["componentes"]["cpu"]["estado"] == "critico" and registro.obtener(999) is None
            texto = registro.csv_texto()
            assert texto.startswith("﻿id,fecha") and "'=HYPERLINK(x)" in texto and ",=HYPERLINK" not in texto, texto
            # rutas
            def _peticion():
                c = app.app.test_client()
                app._ultimo_escaneo = None
                assert c.post("/api/registro", json={"etiqueta": "X"}).status_code == 400  # sin escaneo
                assert c.post("/api/registro", data="etiqueta=X", content_type="text/plain").status_code == 400
                app._ultimo_escaneo = _escaneo_falso()
                r = c.post("/api/registro", json={"etiqueta": "Sala 1 - PC 3", "responsable": "Luis", "postinstalacion": {"acta": "Equipo: <b>X</b>\n[OK] algo", "marcadas": ["respaldo", 5, "<i>"]}})
                assert r.status_code == 201, r.get_data(as_text=True)
                assert len(c.get("/api/registro").get_json()["equipos"]) == 2  # el anterior + este
                h = c.get(f"/api/registro/{r.get_json()['id']}/informe").get_data(as_text=True)
                assert "&lt;script&gt;alert(1)&lt;/script&gt;" in h and "<script>alert(1)" not in h
                assert "Revisión posterior a la instalación" in h and "Equipo: &lt;b&gt;X&lt;/b&gt;" in h and "respaldo, &lt;i&gt;" in h and "<b>X</b>" not in h, h[-400:]
                # una post-instalación inválida no rompe el guardado ni agrega la sección
                r2 = c.post("/api/registro", json={"etiqueta": "Sin post", "postinstalacion": "x"})
                assert r2.status_code == 201 and "Revisión posterior" not in c.get(f"/api/registro/{r2.get_json()['id']}/informe").get_data(as_text=True)
                assert c.delete(f"/api/registro/{r2.get_json()['id']}").status_code == 200
                assert c.get("/api/registro/csv").mimetype == "text/csv"
                assert c.get("/api/registro/9999/informe").status_code == 404
                assert c.delete(f"/api/registro/{r.get_json()['id']}").status_code == 200
                assert c.delete(f"/api/registro/{r.get_json()['id']}").status_code == 404
            try:
                _en_hilo(_peticion)
            finally:
                app._ultimo_escaneo = None
            assert registro.borrar(n) and registro.listar() == []
        finally:
            os.environ.pop("DSPC_REGISTRO", None)
    # --- post-instalación (F6): lectura pura, con lectores simulados ---
    assert postinstalacion._nombre("DESKTOP-ABC1234")["estado"] == "advertencia"
    assert postinstalacion._nombre("PC-SALA1-03")["estado"] == "normal"
    assert [postinstalacion._licencia(v)["estado"] for v in (True, False, None)] == ["normal", "advertencia", "no_determinado"]
    assert "activador" in postinstalacion._licencia(False)["que_hacer"].lower()
    b = {i["titulo"]: i["estado"] for i in postinstalacion._basicos(["Google Chrome", "7-Zip 23", "Foxit Reader"])}
    assert b["Navegador (además de Edge)"] == b["Compresor de archivos"] == b["Lector de PDF"] == "normal" and b["Suite de oficina"] == "advertencia", b
    # F6b: ficha en el acta, actualizaciones, reinicio y perfil del colegio
    import datetime
    hoy = datetime.date(2026, 10, 22)
    assert postinstalacion._actualizaciones(None)["estado"] == "no_determinado"
    assert postinstalacion._actualizaciones(datetime.date(2026, 9, 1), hoy)["estado"] == "normal"
    assert postinstalacion._actualizaciones(datetime.date(2026, 8, 1), hoy)["estado"] == "advertencia"
    assert [postinstalacion._reinicio(v)["estado"] for v in (True, False, None)] == ["advertencia", "normal", "no_determinado"]
    assert postinstalacion._nombre("PC-SALA1-03", "pc-")["estado"] == "normal" and postinstalacion._nombre("DESKTOP-ABC1234", "PC-")["estado"] == "advertencia"
    perfil = {"zona_horaria": "SA Pacific Standard Time", "idioma": "es", "carpeta_instaladores": "x"}
    ok = {i["id"]: i["estado"] for i in postinstalacion._del_perfil(perfil, "SA Pacific Standard Time", "es-CO", 3)}
    mal = {i["id"]: i["estado"] for i in postinstalacion._del_perfil(perfil, "UTC", "en-US", 0)}
    assert set(ok.values()) == {"normal"} and set(mal.values()) == {"advertencia"} and len(ok) == 3, (ok, mal)
    assert postinstalacion._del_perfil({}, None, None, 0) == []
    acta = postinstalacion.texto_acta("PC-1", [], {"fabricante": "ACME", "modelo": "X1", "serial": "S123", "sistema": "Windows 11", "macs": ["AA:BB"]})
    assert "Modelo: ACME X1" in acta and "Serial: S123" in acta and "MAC: AA:BB" in acta, acta
    assert "Serial" not in postinstalacion.texto_acta("PC-1", [], {"serial": ""}) and "Modelo" not in postinstalacion.texto_acta("PC-1", [], None)
    os.environ["DSPC_PERFIL"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "no_existe.json")
    try:
        assert postinstalacion._perfil() == {}
    finally:
        os.environ.pop("DSPC_PERFIL", None)
    # F7 (detecciones de solo lectura)
    d = postinstalacion._desactualizados([{"nombre": "WinRAR 5.50 (64-bit)", "version": "5.50.0"}, {"nombre": "WinRAR", "version": "7.01"},
                                           {"nombre": "Mozilla Firefox ESR", "version": "115.0"}, {"nombre": "Mozilla Firefox", "version": "140.2"},
                                           {"nombre": "WinRAR sin versión", "version": None}])
    assert len(d) == 2 and "5.50" in d[0] and "115" in d[1], d
    assert postinstalacion._version("5.50") == (5, 50) and postinstalacion._version(None) == () and postinstalacion._version("v7") == (7,)
    assert postinstalacion._item_desactualizados([])["estado"] == "normal" and postinstalacion._item_desactualizados(d)["estado"] == "advertencia"
    assert postinstalacion._item_deep_freeze(False) == [] and postinstalacion._item_deep_freeze(True)[0]["estado"] == "advertencia"
    assert [postinstalacion._item_windows_update(v)["estado"] for v in (True, False, None)] == ["advertencia", "normal", "no_determinado"]
    originales = (postinstalacion._nombre_equipo, postinstalacion._windows_activado, postinstalacion._programas_instalados)
    def falla():
        raise OSError("x")
    try:
        postinstalacion._nombre_equipo = postinstalacion._windows_activado = postinstalacion._programas_instalados = falla
        r = postinstalacion.revisar()  # ningún lector rompe la revisión
        assert all(i["estado"] in scanner.ESTADOS_VALIDOS for i in r["items"]), r["items"]
        assert sum(1 for i in r["items"] if i["manual"]) == 3 and "[A MANO]" in r["acta"], r["acta"]
    finally:
        postinstalacion._nombre_equipo, postinstalacion._windows_activado, postinstalacion._programas_instalados = originales
    _en_hilo(lambda: [None for c in [app.app.test_client().get("/api/postinstalacion")] if (c.status_code == 200 and c.get_json()["acta"]) or (_ for _ in ()).throw(AssertionError(c.status_code))])


if __name__ == "__main__":
    test_evidencia()
    test_instalador()
    test_mantenimiento_y_nota()
    test_registro_y_postinstalacion()
    test_analisis_f4b()
    test_paleta()
    test_frontend_node()
    test_frontend_sin_innerhtml_inseguro()
    test_indice_estructura()
    test_indice_recomendaciones()
    test_sin_codigo_del_mapa()
    test_ram()
    test_bateria()
    test_almacenamiento()
    test_cpu()
    test_mainboard()
    test_red()
    test_gpu_sensores()
    test_gpu_aislamiento()
    test_lhm()
    test_lhm_recoger_aislamiento()
    test_lhm_consumidores()
    test_fuente_poder_sin_sensores()
    test_consistencia_scanner()
    test_prioridad_veredicto()
    test_cobertura()
    test_utils_entorno()
    test_app_rutas()
    test_lanzador()
    test_explicador()
    test_escaner_adjunta_guia()
    test_escaner_recomendaciones()
    test_guias_endpoint()
    test_informe()
    test_informe_recomendaciones()
    test_informe_estados_con_forma()
    test_equipo()
    test_equipo_rendimiento()
    test_equipo_cache_por_hilo()
    test_recomendador()
    test_recomendador_so_actual()
    test_recomendador_endurecimiento()
    test_analisis_espacio()
    test_analisis_inicio()
    test_analisis_programas()
    test_analisis_rendimiento()
    test_analisis_orquestador_api_informe()
    print("test_scanner.py: todos los casos OK")
