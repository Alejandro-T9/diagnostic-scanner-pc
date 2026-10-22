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
import io
import socket
import threading

import app
import equipo
import explicador
import lanzador
import recomendador
import scanner
import utils
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
    # (a) cobertura + (b) forma + (c) reglas por estado + (d) palabras prohibidas
    for c in scanner.COMPONENTES:
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
        for c in scanner.COMPONENTES:
            assert set(datos[c]) == scanner.ESTADOS_VALIDOS, (c, set(datos[c]))
        assert set(datos["_veredictos"]) == set(explicador.FRASES_VEREDICTO), datos["_veredictos"]
        assert set(datos) == set(scanner.COMPONENTES) | {"_veredictos"}, set(datos)
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
        assert "Aún no hay un escaneo" in h and "Revisar mi PC" in h and "Escanear Sistema" in h, h
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


if __name__ == "__main__":
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
    test_equipo()
    test_equipo_rendimiento()
    test_equipo_cache_por_hilo()
    test_recomendador()
    test_recomendador_so_actual()
    test_recomendador_endurecimiento()
    print("test_scanner.py: todos los casos OK")
