"""
backend/utils.py — Funciones de apoyo para Diagnostic Scanner PC.

Funciones de bajo nivel que usan tanto app.py como scanner.py: detección
de herramientas instaladas, espacio en disco del entorno donde corre el
backend, y marcas de tiempo. Esto es distinto del diagnóstico S.M.A.R.T.
de las unidades de almacenamiento del equipo, que vive en
backend/modules/almacenamiento.py (fase posterior).
"""

from datetime import datetime, timezone

import ctypes
import json
import os
import socket
import winreg

import psutil
import wmi

# Namespaces WMI que los 7 módulos consultan (ver backend/modules/).
# root/cimv2 es el namespace por defecto (placa, CPU, RAM, red, disco);
# root/wmi es el que usan las clases de batería y temperatura. Pivote de
# Debian Live a WinPE — ver docs/DECISIONES.md — reemplaza la verificación
# anterior de binarios de Linux (smartctl, dmidecode, etc.), que ya no se
# invocan: todo pasa por WMI ahora.
NAMESPACES_WMI_REQUERIDOS = ["root/cimv2", "root/wmi"]


def obtener_timestamp():
    """Devuelve la marca de tiempo actual en formato ISO 8601 (UTC)."""
    try:
        return datetime.now(timezone.utc).isoformat()
    except Exception as error:
        print(f"[ADVERTENCIA] Fallo al generar timestamp: {error}")
        return ""


def verificar_herramientas():
    """Revisa qué namespaces WMI están disponibles para diagnosticar.

    Devuelve {namespace: True/False}. Que un namespace no responda es un
    resultado válido (algún módulo se degradará), no una excepción: solo
    se registra la advertencia si wmi.WMI() falla para ese namespace.
    """
    disponibles = {}
    for namespace in NAMESPACES_WMI_REQUERIDOS:
        try:
            wmi.WMI(namespace=namespace)
            disponibles[namespace] = True
        except wmi.x_wmi as error:
            print(f"[ADVERTENCIA] No se pudo conectar a WMI namespace '{namespace}': {error}")
            disponibles[namespace] = False
    return disponibles


def obtener_espacio_disco(ruta="/"):
    """Devuelve el espacio en disco de `ruta` en GB y el porcentaje de uso.

    Usa psutil.disk_usage sobre el punto de montaje indicado. Si falla
    (por ejemplo, ruta inexistente), devuelve un diccionario con error
    explícito en vez de propagar la excepción hasta /api/status.
    """
    try:
        uso = psutil.disk_usage(ruta)
        gb = 1024 ** 3
        return {
            "total_gb": round(uso.total / gb, 2),
            "usado_gb": round(uso.used / gb, 2),
            "libre_gb": round(uso.free / gb, 2),
            "porcentaje_uso": uso.percent,
        }
    except Exception as error:
        print(f"[ADVERTENCIA] No se pudo leer espacio en disco de '{ruta}': {error}")
        return {
            "total_gb": None,
            "usado_gb": None,
            "libre_gb": None,
            "porcentaje_uso": None,
            "error": str(error),
        }


# Fijo, no depende de ningún escaneo — lo que el proyecto decidió no medir
# a propósito (ver docs/DECISIONES.md, decisiones 19/20/22). Va en el
# reporte para que la limitación quede explícita en la evidencia que se
# entrega, no solo en un documento interno que el técnico no ve.
_LIMITACIONES_CONOCIDAS = [
    "No se ejecutan pruebas de estrés activas (el escaneo es 100% pasivo).",
    "No se analiza el historial de errores de Windows (WHEA).",
    "No se compara este escaneo contra uno anterior — cada arranque es independiente.",
    "No se evalúa la salud de los drivers instalados, solo su versión.",
]


def generar_reporte_texto(resultado, veredicto):
    """Arma el reporte de texto plano de un escaneo, para descargar desde
    el dashboard (/api/reporte). Recibe el veredicto ya calculado en vez
    de importar scanner.py acá: scanner.py ya depende de utils.py, y un
    import en el otro sentido crearía un ciclo.
    """
    if not resultado:
        return "Diagnostic Scanner PC — Reporte de diagnóstico\n\nNo se ha ejecutado ningún escaneo todavía.\n"

    componentes = resultado.get("componentes", {})
    identidad = (componentes.get("mainboard") or {}).get("datos") or {}
    tiempos = resultado.get("tiempos", {})
    cobertura = resultado.get("cobertura", {})

    lineas = [
        "Diagnostic Scanner PC — Reporte de diagnóstico",
        f"ID de diagnóstico: {resultado.get('id_diagnostico', 'desconocido')}",
        f"Generado: {obtener_timestamp()}",
        f"Escaneo realizado: {resultado.get('timestamp', 'desconocido')}",
        "",
        f"Fabricante/modelo: {identidad.get('fabricante', 'desconocido')} {identidad.get('modelo', '')}".rstrip(),
        f"BIOS: {identidad.get('bios_vendor', 'desconocido')} {identidad.get('bios_version', '')} ({identidad.get('bios_fecha', 'desconocida')})".rstrip(),
        "",
        f"Veredicto general: {veredicto}",
        "Resumen: " + ", ".join(f"{clave}={valor}" for clave, valor in resultado.get("resumen", {}).items()),
        f"Cobertura del escaneo: {cobertura.get('porcentaje', '?')}% "
        f"({cobertura.get('completos', '?')} de {cobertura.get('completos', 0) + cobertura.get('parciales', 0)} "
        f"componentes evaluados por completo)",
        f"Tiempo total del escaneo: {tiempos.get('total', '?')} s",
        "",
    ]
    for nombre, info in componentes.items():
        lineas.append(f"--- {nombre.upper()} ({tiempos.get(nombre, '?')} s) ---")
        lineas.append(f"Estado: {info.get('estado')}")
        lineas.append(f"Mensaje: {info.get('mensaje')}")
        if info.get("recomendacion"):
            lineas.append(f"Recomendación: {info['recomendacion']}")
        if info.get("datos"):
            lineas.append(json.dumps(info["datos"], indent=2, ensure_ascii=False))
        lineas.append("")

    sin_datos = [nombre for nombre, info in componentes.items() if info.get("estado") == "no_determinado"]
    lineas.append("--- LIMITACIONES DE ESTE REPORTE ---")
    if sin_datos:
        lineas.append(f"Sin datos suficientes en: {', '.join(sin_datos)} (ver mensaje de cada componente arriba).")
    lineas.extend(_LIMITACIONES_CONOCIDAS)
    lineas.append("")
    return "\n".join(lineas)


def puerto_libre(preferido=5000):
    """Devuelve `preferido` si se puede enlazar en 127.0.0.1; si no, otro libre.

    Solo prueba el loopback (el backend no se expone a la red). Si el
    puerto preferido está ocupado, deja que el sistema asigne uno libre.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
            sonda.bind(("127.0.0.1", preferido))
            return preferido
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
            sonda.bind(("127.0.0.1", 0))
            return sonda.getsockname()[1]


def es_winpe(minint_existe, unidad_sistema):
    """Decide si el entorno es WinPE a partir de dos señales ya leídas.

    Pura (sin I/O) para poder probarla: WinPE crea la clave MiniNT y
    arranca desde una unidad X:.
    """
    return bool(minint_existe) or unidad_sistema.upper().startswith("X:")


def detectar_entorno():
    """Devuelve "winpe" o "windows" según la clave MiniNT y SystemDrive."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\MiniNT",
        ):
            minint_existe = True
    except OSError:
        minint_existe = False
    unidad_sistema = os.environ.get("SystemDrive", "C:")
    return "winpe" if es_winpe(minint_existe, unidad_sistema) else "windows"


def es_administrador():
    """True si el proceso corre con privilegios de administrador.

    Cualquier fallo (API ausente, sistema no Windows) cuenta como False.
    """
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
