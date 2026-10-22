"""
backend/analisis/seguridad.py — Protección básica de Windows y señales de alerta.

SOLO LECTURA, sin administrador. Lee el estado (no lo cambia): antivirus de Windows (WMI), firewall y
control de cuentas (registro). Además informa "señales de alerta" que merecen una mirada:
procesos que corren desde Temp/Descargas, entradas extra en el archivo hosts y un proxy configurado.
NO es un antivirus: no escanea archivos ni detecta rootkits, y las señales de alerta no son un
veredicto (muchos instaladores legítimos corren desde Descargas). Si el antivirus de Windows está
apagado puede ser porque hay otro instalado: eso no se puede saber desde aquí.
El estado solo depende de la protección leída; las señales se informan aparte.
"""

import os
import winreg

import psutil

_MAX = 30
_RUTAS_RARAS = ("\\appdata\\local\\temp\\", "\\downloads\\", "\\windows\\temp\\")
_RECOMENDACIONES = {
    "normal": "No hace falta hacer nada.",
    "advertencia": "Abre Seguridad de Windows y revisa lo que aparece desactivado; si usas otro antivirus, ignóralo.",
    "sospecha": "Este análisis no produce este nivel; trátalo como un error del análisis.",
    "critico": "Este análisis no produce este nivel; trátalo como un error del análisis.",
    "no_determinado": "Abre Seguridad de Windows para ver el estado y repite el análisis.",
}


def _dword(raiz, ruta, nombre):
    try:
        with winreg.OpenKey(raiz, ruta) as k:
            return winreg.QueryValueEx(k, nombre)[0]
    except OSError:
        return None


def _leer_proteccion() -> dict:
    p = {"antivirus_tiempo_real": None, "firewall": None, "uac": None}
    try:
        import wmi
        estado = wmi.WMI(namespace="root/Microsoft/Windows/Defender").MSFT_MpComputerStatus()[0]
        p["antivirus_tiempo_real"] = bool(estado.RealTimeProtectionEnabled)
    except Exception:
        pass
    base = r"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy"
    perfiles = [_dword(winreg.HKEY_LOCAL_MACHINE, f"{base}\\{n}", "EnableFirewall") for n in ("StandardProfile", "PublicProfile")]
    if any(x is not None for x in perfiles):
        p["firewall"] = all(x != 0 for x in perfiles if x is not None)
    uac = _dword(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System", "EnableLUA")
    if uac is not None:
        p["uac"] = bool(uac)
    return p


def _leer_senales() -> dict:
    procesos = []
    for pr in psutil.process_iter(["name", "exe"]):
        try:
            exe = (pr.info.get("exe") or "").lower()
            if any(r in exe for r in _RUTAS_RARAS):
                procesos.append({"nombre": pr.info.get("name") or "?", "ruta": pr.info.get("exe")})
        except (psutil.Error, OSError):
            continue
    hosts = []
    try:
        ruta = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), r"System32\drivers\etc\hosts")
        with open(ruta, encoding="utf-8", errors="replace") as f:
            for linea in f:
                t = linea.strip()
                if t and not t.startswith("#") and not t.split()[0] in ("127.0.0.1", "::1"):
                    hosts.append(t[:120])
    except OSError:
        pass
    proxy = _dword(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings", "ProxyEnable")
    return {"procesos_en_carpetas_temporales": procesos[:_MAX], "hosts_extra": hosts[:_MAX], "proxy_activo": bool(proxy) if proxy is not None else None}


def _clasificar(p: dict) -> tuple:
    leidos = {k: v for k, v in p.items() if isinstance(v, bool)}
    if not leidos:
        return "no_determinado", "No se pudo leer el estado de la protección de Windows."
    nombres = {"antivirus_tiempo_real": "el antivirus de Windows (protección en tiempo real)", "firewall": "el firewall", "uac": "el control de cuentas de usuario"}
    apagados = [nombres[k] for k, v in leidos.items() if not v]
    if apagados:
        return "advertencia", "Aparece desactivado: " + ", ".join(apagados) + "."
    return "normal", "La protección básica de Windows que se pudo leer está activada."


def diagnosticar() -> dict:
    try:
        p = _leer_proteccion()
        estado, mensaje = _clasificar(p)
    except Exception:
        p, estado, mensaje = {}, "no_determinado", "No se pudo leer el estado de la protección de Windows."
    try:
        senales = _leer_senales()
    except Exception:
        senales = {}
    return {"componente": "seguridad", "estado": estado, "mensaje": mensaje,
            "datos": {**p, **senales}, "recomendacion": _RECOMENDACIONES[estado]}
