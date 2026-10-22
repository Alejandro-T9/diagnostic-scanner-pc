"""
backend/scanner.py — Orquestador central del diagnóstico de hardware.

Este archivo NO implementa las pruebas de cada componente (eso vive en
backend/modules/<componente>.py); coordina el flujo completo: llama a
cada módulo, tolera que todavía no existan, arma el reporte final y
calcula el resumen y el color global del equipo.
"""

from datetime import datetime, timezone

import hashlib
import importlib
import sys
import time

import equipo
import explicador
import recomendador
import utils
from modules import _lhm

# Los 7 componentes del alcance del proyecto (mismo orden y nombres que
# backend/modules/__init__.py).
COMPONENTES = [
    "mainboard",
    "cpu",
    "ram",
    "almacenamiento",
    "fuente_poder",
    "bateria",
    "red",
]

# Valores permitidos para la llave "estado" en la respuesta de un módulo.
# Sistema de 5 niveles (ver docs/DECISIONES.md) — reemplaza al de 3 niveles
# original. "sospecha" existe para diferenciar "hay evidencia de un posible
# problema" de "advertencia" (algo a monitorear, sin indicio de falla) y de
# "critico" (evidencia fuerte). "no_determinado" existe para diferenciar
# "no se pudo leer el dato" de "se leyó y está mal" — son cosas distintas,
# mezclarlas era la crítica principal a la versión anterior.
ESTADOS_VALIDOS = {"normal", "advertencia", "sospecha", "critico", "no_determinado"}

# Orden de severidad, de más grave a menos — determina el veredicto global.
# CORREGIDO (revisión externa, 2026-08-18 — ver decisión 22 en
# docs/DECISIONES.md): "no_determinado" pesa MENOS que "advertencia", no
# más. Son ejes distintos — confianza de medición vs. severidad de
# condición — y el propósito del veredicto es priorizar evidencia
# accionable ("qué revisar físicamente"). Un componente sin dato de un
# sensor no debe tapar en el titular la evidencia real de otro componente
# que sí se pudo leer y dio mal. Sigue pesando más que "normal": esa parte
# de la decisión 20 seguía siendo correcta (no saber no es lo mismo que
# estar bien).
_SEVERIDAD = ["critico", "sospecha", "advertencia", "no_determinado", "normal"]


def ejecutar_escaneo_completo() -> dict:
    """Orquesta el escaneo completo de los 7 componentes del equipo.

    Importa cada módulo de diagnóstico de forma dinámica: si el módulo aún
    no existe, o si falla al ejecutarse, el componente queda marcado como
    "error" sin detener el resto del escaneo. Así /api/scan funciona desde
    ya y se va completando solo, a medida que se agregan módulos.

    También cronometra cada módulo (para detectar cuál domina el tiempo
    total, útil al mostrar evidencia de la app en la sustentación) y
    calcula "cobertura": qué tan completo fue el escaneo, un eje distinto
    de qué tan sano está el equipo (ver _calcular_cobertura).
    """
    # Los sensores de LibreHardwareMonitor se leen una sola vez por escaneo
    # y se comparten entre cpu/gpu/fuente_poder; cada escaneo parte de cero.
    _lhm.invalidar()
    tiempos = {}
    inicio_total = time.perf_counter()
    componentes = {}
    for nombre in COMPONENTES:
        inicio = time.perf_counter()
        componentes[nombre] = _escanear_componente(nombre)
        tiempos[nombre] = round(time.perf_counter() - inicio, 3)
    # Mismo hilo que el escaneo (COM ya inicializado). Si algo falla el
    # escaneo igual completa, solo sin hechos/recomendaciones.
    inicio = time.perf_counter()
    hechos, recomendaciones = {}, []
    try:
        hechos = equipo.leer_hechos()
        tiempos["hechos"] = round(time.perf_counter() - inicio, 3)
        recomendaciones = recomendador.recomendar({"componentes": componentes}, hechos)
    except Exception as error:
        print(f"[scanner] hechos/recomendaciones no disponibles: {error}", file=sys.stderr)
    tiempos.setdefault("hechos", round(time.perf_counter() - inicio, 3))
    tiempos["total"] = round(time.perf_counter() - inicio_total, 3)

    return {
        "id_diagnostico": _generar_id_diagnostico(componentes),
        "timestamp": utils.obtener_timestamp(),
        "herramientas_disponibles": utils.verificar_herramientas(),
        "componentes": componentes,
        "hechos": hechos,
        "recomendaciones": recomendaciones,
        "resumen": _calcular_resumen(componentes),
        "cobertura": _calcular_cobertura(componentes),
        "tiempos": tiempos,
    }


def _generar_id_diagnostico(componentes: dict) -> str:
    """ID legible y trazable de un escaneo puntual — nunca se persiste (no
    rompe la arquitectura stateless, ver decisión 4 en docs/DECISIONES.md),
    solo permite que un técnico diga "este reporte corresponde a este
    escaneo". Formato: DSPC-AAAAMMDD-HHMM-XXXX; los últimos 4 caracteres
    son un hash corto del contenido, no aleatorios — dos escaneos con
    resultado idéntico en el mismo minuto comparten ID a propósito, son
    el mismo hallazgo para efectos del reporte."""
    momento = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    huella = hashlib.sha1(str(componentes).encode("utf-8")).hexdigest()[:4].upper()
    return f"DSPC-{momento}-{huella}"


def _calcular_cobertura(componentes: dict) -> dict:
    """Qué tan completo fue el escaneo — no qué tan sano está el equipo,
    son ejes distintos (ver decisión 22: confianza de medición vs.
    severidad de condición). Un componente "completo" es uno que SÍ se
    pudo leer, sin importar si el resultado fue bueno o malo (hasta
    "critico" cuenta como medido, solo "no_determinado" no). Derivado
    directo del propio conteo de estados, sin ningún cálculo nuevo — nada
    que pueda convertirse en un número inventado."""
    total = len(componentes)
    parciales = sum(1 for info in componentes.values() if info.get("estado") == "no_determinado")
    completos = total - parciales
    return {
        "porcentaje": round(completos / total * 100) if total else 0,
        "completos": completos,
        "parciales": parciales,
    }


def clasificar_equipo(resultado: dict) -> str:
    """Determina el veredicto global del equipo: el estado más severo entre
    los 7 componentes, según _SEVERIDAD. Devuelve el nombre del estado en
    mayúsculas (NORMAL/ADVERTENCIA/SOSPECHA/CRITICO/NO_DETERMINADO).

    NOTA: esto reemplaza el veredicto de 3 colores (Verde/Amarillo/Rojo)
    que describe el documento institucional del Semillero — decisión
    consciente, no un descuido. Ver docs/DECISIONES.md.
    """
    estados = {info.get("estado") for info in resultado.get("componentes", {}).values()}
    for nivel in _SEVERIDAD:
        if nivel in estados:
            return nivel.upper()
    return "NORMAL"


def _escanear_componente(nombre: str) -> dict:
    """Ejecuta el diagnóstico de un componente, tolerando módulo faltante.

    Intenta importar backend/modules/<nombre>.py y llamar a diagnosticar().
    Si el módulo no existe, si la llamada lanza una excepción, o si la
    respuesta no cumple el contrato mínimo, el componente queda marcado
    como "error" en vez de tumbar el resto del escaneo.
    """
    try:
        modulo = importlib.import_module(f"modules.{nombre}")
    except ImportError:
        return _con_guia(nombre, _resultado_error(nombre, "Módulo no implementado"))

    try:
        respuesta = modulo.diagnosticar()
    except Exception as error:
        return _con_guia(nombre, _resultado_error(nombre, f"Fallo al ejecutar el diagnóstico: {error}"))

    if not _cumple_contrato(respuesta):
        return _con_guia(nombre, _resultado_error(nombre, "El módulo no respetó el contrato (componente/estado/mensaje/datos)"))
    return _con_guia(nombre, respuesta)


def _con_guia(nombre: str, respuesta: dict) -> dict:
    """Copia de la respuesta con la llave extra "guia" (explicación en
    lenguaje simple, ver explicador.py). Se agrega DESPUÉS de validar el
    contrato: _cumple_contrato sigue exigiendo solo las 5 llaves del módulo."""
    return {**respuesta, "guia": explicador.guia_para(nombre, respuesta["estado"])}


def _resultado_error(nombre: str, mensaje: str) -> dict:
    """Arma la respuesta estándar de "no determinado" para un componente
    que no se pudo diagnosticar (módulo faltante, excepción, o contrato
    incumplido) — no es lo mismo que un componente que sí se leyó y dio
    mal (eso es "critico"/"sospecha")."""
    return {
        "componente": nombre, "estado": "no_determinado", "mensaje": mensaje, "datos": None,
        "recomendacion": "Revisar la instalación del módulo o el entorno de ejecución.",
    }


def _cumple_contrato(respuesta) -> bool:
    """Valida que la respuesta de un módulo tenga las 5 llaves mínimas
    y que 'estado' sea uno de los valores permitidos. "recomendacion"
    (acción sugerida por estado) se agregó para cumplir lo que el
    documento institucional del Semillero promete: no solo diagnosticar,
    también indicar qué acción corresponde."""
    if not isinstance(respuesta, dict):
        return False
    llaves_requeridas = {"componente", "estado", "mensaje", "datos", "recomendacion"}
    if not llaves_requeridas.issubset(respuesta.keys()):
        return False
    return respuesta["estado"] in ESTADOS_VALIDOS


def _calcular_resumen(componentes: dict) -> dict:
    """Cuenta cuántos componentes cayeron en cada estado, para 'resumen'."""
    conteo = {"normal": 0, "advertencia": 0, "sospecha": 0, "critico": 0, "no_determinado": 0}
    for info in componentes.values():
        estado = info.get("estado", "no_determinado")
        if estado in conteo:
            conteo[estado] += 1
        else:
            conteo["no_determinado"] += 1
    return {"total_componentes": len(componentes), **conteo}