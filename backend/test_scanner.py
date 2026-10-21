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

import socket

import app
import lanzador
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
    _assert_estado("Ningún enlace activo", red._clasificar([sin_link])[0], "critico")
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


def test_app_rutas():
    """Rutas de app.py: host seguro, /api/status ampliado y errores en JSON."""
    # (a) Decisión 27: el servidor solo escucha en loopback.
    assert app.HOST == "127.0.0.1", app.HOST

    cliente = app.app.test_client()
    escaneo_original = scanner.ejecutar_escaneo_completo
    reporte_original = utils.generar_reporte_texto
    app._ultimo_escaneo = None
    try:
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
    test_fuente_poder_sin_sensores()
    test_consistencia_scanner()
    test_prioridad_veredicto()
    test_cobertura()
    test_utils_entorno()
    test_app_rutas()
    test_lanzador()
    print("test_scanner.py: todos los casos OK")
