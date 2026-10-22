"""
backend/analisis/rendimiento.py — ¿Por qué va lento el equipo?

SOLO LECTURA, sin administrador. Es una FOTO DEL MOMENTO: mide durante ~1 s
y busca posibles causas de lentitud. NO es un diagnóstico definitivo ni mide
todo; si el equipo ahora va bien, la foto saldrá "normal" aunque a otras horas
vaya lento (conviene correrla cuando está lento).
Mide (psutil, más dos lecturas reutilizadas: tipo de disco de equipo.py y
cantidad de programas de inicio de inicio.py):
- uso de RAM y de CPU durante la medición;
- espacio libre de la unidad del sistema;
- ocupación del disco en esa misma ventana de 1 s;
- los 5 procesos que más CPU y los 5 que más RAM usan.

Causas, en orden de prioridad (la primera se presenta como la más probable):
  ram         RAM >= 90 %
  espacio     libre de la unidad del sistema < 10 %
  disco_lento disco duro mecánico (HDD) ocupado >= 90 %
  cpu         CPU >= 90 % y un proceso >= 50 % del procesador
  inicio      10 o más programas de inicio
Un dato que falta o no es un número NUNCA produce una causa. Con la RAM y la
CPU ausentes no se midió lo esencial: "no_determinado". Nunca emite "critico".

CPU por proceso: psutil la da como % de UN núcleo (puede pasar de 100), así
que se divide por el número de núcleos lógicos: "proceso >= 50 %" significa
la mitad de TODO el procesador. Los nombres de proceso son texto no confiable:
se guardan crudos y se escapan al mostrarlos.
"""

import math
import os
import time

import psutil

import equipo
from analisis import inicio

UMBRAL_RAM_PCT = 90
UMBRAL_ESPACIO_PCT = 10
UMBRAL_DISCO_PCT = 90
UMBRAL_CPU_PCT = 90
UMBRAL_PROCESO_PCT = 50
UMBRAL_INICIO = 10
_MAX_PROCESOS = 5
_VENTANA_SEG = 1.0

_RECOMENDACIONES = {
    "normal": "Si el equipo se pone lento, repite el análisis justo en ese momento: esta medición es solo una foto del momento.",
    "advertencia": ("Lee la causa que se indica y cierra lo que no uses; si la lentitud sigue, "
                    "repite el análisis cuando el equipo esté lento y muéstraselo a un técnico."),
    "no_determinado": "Abre el Administrador de tareas (Ctrl+Mayús+Esc) para ver qué programa usa más y repite el análisis.",
}


def _num(x):
    """float si es un número real finito (no bool); si no, None."""
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return float(x)


def _pct(x):
    """Porcentaje válido (0-100) o None."""
    v = _num(x)
    return None if v is None else min(100.0, max(0.0, v))


def _procesos(lista) -> list:
    """Hasta 5 procesos bien formados {"nombre", "cpu", "ram_mb"}; lo demás se descarta."""
    salida = []
    for p in lista if isinstance(lista, list) else []:
        if not isinstance(p, dict) or not isinstance(p.get("nombre"), str):
            continue
        cpu, ram = _pct(p.get("cpu")), _num(p.get("ram_mb"))
        if cpu is None or ram is None:
            continue
        salida.append({"nombre": p["nombre"], "cpu": round(cpu, 1), "ram_mb": round(max(0.0, ram), 1)})
    return salida[:_MAX_PROCESOS]


def _causas(medicion: dict) -> list:
    """PURA. Causas en orden de prioridad; cada una {"id", "titulo", "evidencia": [str]}."""
    m = medicion if isinstance(medicion, dict) else {}
    ram, libre, ocupado, cpu = (_num(m.get(k)) for k in ("ram_uso", "disco_c_libre_pct", "disco_ocupado_pct", "cpu_uso"))
    inicio_total = m.get("inicio_total")
    causas = []
    if ram is not None and ram >= UMBRAL_RAM_PCT:
        evidencia = [f"Uso de RAM durante la medición: {ram:.0f} %"]
        total = _num(m.get("ram_total_gb"))
        if total:
            evidencia.append(f"Memoria RAM total: {total:.1f} GB".replace(".", ","))
        causas.append({"id": "ram", "titulo": "La memoria RAM está casi llena", "evidencia": evidencia})
    if libre is not None and libre < UMBRAL_ESPACIO_PCT:
        unidad = os.environ.get("SystemDrive", "C:")
        texto = f"{math.floor(libre * 10 + 1e-6) / 10:.1f}".replace(".", ",")  # truncado: no redondea hacia el umbral
        causas.append({"id": "espacio", "titulo": f"Queda poco espacio libre en el disco {unidad}",
                       "evidencia": [f"Espacio libre en {unidad}: {texto} %"]})
    if m.get("disco_tipo") == "hdd" and ocupado is not None and ocupado >= UMBRAL_DISCO_PCT:
        causas.append({"id": "disco_lento",
                       "titulo": "El disco duro está trabajando al máximo; los discos mecánicos son más lentos que los SSD",
                       "evidencia": [f"Disco duro (HDD) ocupado al {ocupado:.0f} %"]})
    if cpu is not None and cpu >= UMBRAL_CPU_PCT:
        pesados = [p for p in _procesos(m.get("procesos")) if p["cpu"] >= UMBRAL_PROCESO_PCT]
        if pesados:
            p = max(pesados, key=lambda q: q["cpu"])
            causas.append({"id": "cpu", "titulo": f"El procesador está muy ocupado por {p['nombre']}",
                           "evidencia": [f"Uso del procesador durante la medición: {cpu:.0f} %",
                                         f"Proceso '{p['nombre']}' usando {p['cpu']:.0f} % del procesador"]})
    if isinstance(inicio_total, int) and not isinstance(inicio_total, bool) and inicio_total >= UMBRAL_INICIO:
        causas.append({"id": "inicio", "titulo": "Muchos programas arrancan al encender el equipo",
                       "evidencia": [f"Programas de inicio: {inicio_total}"]})
    return causas


def _clasificar(causas: list, medicion_valida: bool) -> tuple:
    if not medicion_valida:
        return "no_determinado", "No se pudo medir el rendimiento del equipo en este momento."
    if not causas:
        return "normal", ("En esta medición no se encontró nada que explique lentitud — "
                          "recuerda que es una foto del momento.")
    otras = len(causas) - 1
    resto = "" if otras == 0 else " Hay otra posible." if otras == 1 else f" Hay otras {otras} posibles."
    return "advertencia", f"La causa más probable es: {causas[0]['titulo']}.{resto}"


def diagnosticar() -> dict:
    try:
        crudo = _medir()  # se busca por nombre al llamar: reemplazable en pruebas
        if not isinstance(crudo, dict):
            raise TypeError("medición mal formada")
    except Exception:
        crudo = {}
    medicion = {
        "ram_uso": _pct(crudo.get("ram_uso")),
        "ram_total_gb": _num(crudo.get("ram_total_gb")),
        "disco_c_libre_pct": _pct(crudo.get("disco_c_libre_pct")),
        "disco_tipo": crudo.get("disco_tipo") if crudo.get("disco_tipo") in ("ssd", "hdd") else "desconocido",
        "disco_ocupado_pct": _pct(crudo.get("disco_ocupado_pct")),
        "cpu_uso": _pct(crudo.get("cpu_uso")),
        "inicio_total": crudo.get("inicio_total") if isinstance(crudo.get("inicio_total"), int)
                        and not isinstance(crudo.get("inicio_total"), bool) else None,
    }
    procesos_cpu, procesos_ram = _procesos(crudo.get("procesos_cpu")), _procesos(crudo.get("procesos_ram"))
    valida = medicion["ram_uso"] is not None or medicion["cpu_uso"] is not None
    causas = _causas({**medicion, "procesos": crudo.get("procesos", procesos_cpu)}) if valida else []
    estado, mensaje = _clasificar(causas, valida)
    return {
        "componente": "rendimiento", "estado": estado, "mensaje": mensaje,
        "datos": {"causas": causas, "medicion": medicion, "procesos_cpu": procesos_cpu, "procesos_ram": procesos_ram},
        "recomendacion": _RECOMENDACIONES[estado],
    }


def _tiempos_disco():
    """{disco: ms acumulados de lectura+escritura} o None si el sistema no los da."""
    try:
        return {d: c.read_time + c.write_time for d, c in psutil.disk_io_counters(perdisk=True).items()}
    except Exception:
        return None


def _medir() -> dict:
    """Lee el equipo (~1,4 s: la ventana de 1 s más el tipo de disco). Cada lectura que falla queda en None."""
    nucleos = psutil.cpu_count() or 1
    unidad = os.environ.get("SystemDrive", "C:")
    medicion = {"ram_uso": None, "ram_total_gb": None, "disco_c_libre_pct": None, "disco_tipo": "desconocido",
                "disco_ocupado_pct": None, "cpu_uso": None, "inicio_total": None,
                "procesos": [], "procesos_cpu": [], "procesos_ram": []}

    # Ventana de 1 s compartida: contadores de disco antes y después, CPU total y por proceso en medio.
    try:
        for p in psutil.process_iter(["cpu_percent"]):  # la primera lectura de cada proceso solo "arma" la medición
            pass
    except Exception:
        pass
    antes, t0 = _tiempos_disco(), time.monotonic()
    try:
        medicion["cpu_uso"] = _pct(psutil.cpu_percent(interval=_VENTANA_SEG))
    except Exception:
        time.sleep(_VENTANA_SEG)
    ventana, despues = time.monotonic() - t0, _tiempos_disco()

    if antes and despues and ventana > 0:
        # shortcut: Windows no da busy_time; read_time+write_time suma el tiempo de cada petición (puede superar
        # la ventana con peticiones en paralelo, por eso se acota a 100) y se toma el disco más ocupado, no
        # necesariamente el del sistema. Cambiar a contadores de rendimiento (PhysicalDisk) si hace falta precisión.
        deltas = [(despues[d] - antes[d]) / (ventana * 1000) * 100 for d in despues if d in antes]
        medicion["disco_ocupado_pct"] = _pct(max(deltas)) if deltas else None

    try:
        vm = psutil.virtual_memory()
        medicion["ram_uso"] = _pct(vm.percent)
        medicion["ram_total_gb"] = round(vm.total / 1024 ** 3, 1)
    except Exception:
        pass
    try:
        uso = psutil.disk_usage(unidad + "\\")
        medicion["disco_c_libre_pct"] = _pct(round(uso.free * 100 / uso.total, 1))
    except Exception:
        pass

    try:
        filas = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            i = p.info  # los procesos inaccesibles traen None en ese campo; los que murieron no aparecen
            if not i.get("pid") or not isinstance(i.get("name"), str) or i.get("cpu_percent") is None:
                continue  # pid 0 = "System Idle Process": su "CPU" es el tiempo libre
            rss = getattr(i.get("memory_info"), "rss", None)
            filas.append({"nombre": i["name"], "cpu": _pct(i["cpu_percent"] / nucleos) or 0.0,
                          "ram_mb": (rss or 0) / 1024 ** 2})
        medicion["procesos_cpu"] = _procesos(sorted(filas, key=lambda f: f["cpu"], reverse=True)[:_MAX_PROCESOS])
        medicion["procesos_ram"] = _procesos(sorted(filas, key=lambda f: f["ram_mb"], reverse=True)[:_MAX_PROCESOS])
        medicion["procesos"] = medicion["procesos_cpu"]
    except Exception:
        pass

    try:
        medicion["disco_tipo"] = equipo.leer_hechos()["disco_sistema_tipo"]
    except Exception:
        pass
    try:
        medicion["inicio_total"] = inicio.diagnosticar()["datos"]["total"]
    except Exception:
        pass
    return medicion
