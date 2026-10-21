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

import scanner
from modules import almacenamiento, bateria, cpu, gpu, mainboard, ram, red


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


if __name__ == "__main__":
    test_ram()
    test_bateria()
    test_almacenamiento()
    test_cpu()
    test_mainboard()
    test_red()
    test_gpu_sensores()
    test_consistencia_scanner()
    test_prioridad_veredicto()
    test_cobertura()
    print("test_scanner.py: todos los casos OK")
