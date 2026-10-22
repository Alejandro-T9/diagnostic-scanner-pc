"""
backend/recomendador.py — Recomendaciones del equipo (F3) a partir de un escaneo.

Función pura: `recomendar(resultado, hechos)` recibe el resultado de un
escaneo y los hechos de `equipo.leer_hechos()` y devuelve una lista de
recomendaciones. NUNCA lanza (cada regla va aislada: si falla, se omite) y
NUNCA inventa: una regla solo corre si existen los datos que necesita; lo que
no se pudo leer no se afirma. Las reglas están en
docs/reglas-recomendaciones.md ("Recomendaciones del equipo (F3)"): si se
cambia una, hay que cambiar la otra.

Estilo de los textos (para personas sin conocimientos técnicos): tuteo, frases
cortas, sin alarmismo, sin marcas de hardware ni precios, y sin afirmar que el
equipo está "limpio" o "seguro": esta herramienta mide hardware, no busca virus.
"""

import equipo

_ORDEN_PRIORIDAD = {"alta": 0, "media": 1, "baja": 2}

_NOTA_W10 = ("Windows 10 dejó de recibir actualizaciones de seguridad gratuitas en octubre de 2025; "
             "úsalo con cuidado y mantén tus archivos respaldados.")
_NOTA_MINIOS = "Es una versión modificada no oficial de Windows 10; instálala con ayuda de un técnico."
_NOTA_W7 = ("Windows 7 no recibe actualizaciones de seguridad desde 2020. Úsalo solo si tu equipo o tus "
            "programas lo exigen, de preferencia sin internet o con mucho cuidado.")
_NOTA_TPM = "Falta confirmar el TPM 2.0 (se lee con permisos de administrador): compruébalo antes de instalar."
_NOTA_SB = "Falta confirmar el Arranque seguro (Secure Boot): compruébalo antes de instalar."
_NOTA_32 = "Para procesadores de 32 bits hay pocas versiones compatibles; un técnico debe confirmar cuál sirve."


def _comp(res, nombre) -> dict:
    return ((res or {}).get("componentes") or {}).get(nombre) or {}


def _dato(res, nombre, clave):
    datos = _comp(res, nombre).get("datos")
    return datos.get(clave) if isinstance(datos, dict) else None


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _g(x) -> str:
    return f"{x:g}"  # 16.0 -> "16", 7.4 -> "7.4"


def _rec(id_, titulo, detalle, basado_en, prioridad, quien, opciones=()) -> dict:
    return {"id": id_, "titulo": titulo, "detalle": detalle, "basado_en": basado_en,
            "prioridad": prioridad, "quien": quien, "opciones": list(opciones)}


def _ram_gb(res):
    for clave in ("capacidad_fisica_gb", "capacidad_disponible_so_gb"):
        v = _num(_dato(res, "ram", clave))
        if v is not None:
            return v
    return None


def _arq64(res, hechos):
    """True si algún dato dice 64 bits (el procesador lo admite aunque el SO sea de 32), False si dice 32/x86."""
    textos = [str(((hechos or {}).get("so") or {}).get("arquitectura") or ""),
              str(_dato(res, "cpu", "arquitectura") or "")]
    if any("64" in t for t in textos):
        return True
    if any("32" in t or "x86" in t for t in textos):
        return False
    return None


def _windows11(cpu_nombre, h):
    """-> (opcion | None, razones por las que se omitió, datos que faltan confirmar)."""
    apto, fw, sb, tpm = equipo.cpu_apto_windows11(cpu_nombre), h.get("firmware"), h.get("secure_boot"), h.get("tpm_version")
    razones = []
    if apto is False:
        razones.append("Procesador anterior a lo que pide Windows 11")
    elif apto is None:
        razones.append("No se pudo comprobar si el procesador sirve para Windows 11")
    if fw == "bios":
        razones.append("Firmware BIOS clásica: Windows 11 pide UEFI")
    elif fw != "uefi":
        razones.append("No se pudo leer el tipo de firmware (Windows 11 pide UEFI)")
    if sb is False:
        razones.append("Arranque seguro (Secure Boot) desactivado: Windows 11 lo pide")
    if tpm == "1.2":
        razones.append("TPM 1.2: Windows 11 pide 2.0")
    if razones:
        return None, razones, []
    # Un dato ilegible no descarta Windows 11 (no se afirma incompatibilidad): queda pendiente de confirmar.
    pendientes = (["el TPM 2.0"] if tpm is None else []) + (["el Arranque seguro"] if sb is None else [])
    notas = ([_NOTA_TPM] if tpm is None else []) + ([_NOTA_SB] if sb is None else [])
    return {"nombre": "Windows 11", "nota": " ".join(notas), "motivo": ""}, [], pendientes


def _regla_so(res, h):
    ram, arq64 = _ram_gb(res), _arq64(res, h)
    if ram is None or arq64 is None:
        return None
    cpu_nombre, sistema = _dato(res, "cpu", "nombre"), h.get("disco_sistema_tipo")
    g = _g(ram)
    w11, razones, pendientes = None, [], []
    base = []
    if arq64 and ram >= 4:
        w11, razones, pendientes = _windows11(cpu_nombre, h)
        if w11:
            w11["motivo"] = f"Tu equipo tiene {g} GB de RAM, un procesador reciente y cumple los requisitos que se pudieron comprobar."
        base.append({"nombre": "Windows 10", "nota": _NOTA_W10,
                     "motivo": f"Tu equipo tiene {g} GB de RAM y un procesador de 64 bits, suficiente para Windows 10."})
    if ram >= 4:
        base.append({"nombre": "Ubuntu o Linux Mint", "nota": "" if arq64 else _NOTA_32,
                     "motivo": f"Con {g} GB de RAM funciona con fluidez y se actualiza gratis."})
    else:
        base.append({"nombre": "Lubuntu o Linux Mint XFCE", "nota": "" if arq64 else _NOTA_32,
                     "motivo": f"Es liviano: funciona bien con poca memoria ({g} GB)."})
    # shortcut: MiniOS10 exige 64 bits y >= 2 GB (Windows 10 de 64 bits); el brief no fija ese piso para el caso HDD.
    if arq64 and ram >= 2 and (ram < 4 or (sistema == "hdd" and ram < 8)):
        base.append({"nombre": "MiniOS10", "nota": _NOTA_MINIOS,
                     "motivo": f"Es una versión liviana de Windows 10, pensada para equipos con poca RAM ({g} GB) o disco duro mecánico."})
    if arq64 is False or ram < 2:
        base.append({"nombre": "Windows 7", "nota": _NOTA_W7,
                     "motivo": "Tu equipo es antiguo o tiene muy poca memoria, y puede que no admita sistemas más nuevos."})
    if w11:
        base.insert(0, w11)
    if not base:
        return None
    basado = [f"RAM: {g} GB"]
    if cpu_nombre:
        basado.append(f"Procesador: {cpu_nombre}")
    basado.append("Arquitectura: 64 bits" if arq64 else "Arquitectura: 32 bits")
    if h.get("firmware") in ("uefi", "bios"):
        basado.append("Firmware: UEFI" if h["firmware"] == "uefi" else "Firmware: BIOS clásica")
    if arq64 and ram >= 4:
        tpm = h.get("tpm_version")
        basado.append(f"TPM: {tpm}" if tpm else "TPM: no se pudo leer (se lee con permisos de administrador)")
    if sistema in ("ssd", "hdd"):
        basado.append(f"Disco principal: {sistema.upper()}")
    basado += razones
    principal = base[0]["nombre"]
    if w11:
        principal += f" (falta confirmar {' y '.join(pendientes)})" if pendientes else ""
    quien = "tu_mismo" if base[0]["nombre"] in ("Windows 11", "Windows 10") else "tecnico"
    return _rec("so", "Sistema operativo que conviene a tu equipo",
                f"Según tus componentes te recomendamos: {principal}. También puedes ver otras opciones.",
                basado, "baja", quien, base)


def _regla_disco_ssd(res, h):
    sistema = h.get("disco_sistema_tipo")
    internos = [d for d in h.get("discos") or [] if not d.get("externo")]
    if sistema == "hdd":
        basado = ["Disco principal: HDD (disco duro mecánico)"]
    elif sistema == "desconocido" and internos and all(d.get("tipo") == "hdd" for d in internos):
        basado = ["Discos internos: HDD"]
    else:
        return None
    return _rec("disco_ssd", "Pasa tu disco a un SSD",
                "Tu equipo usa un disco duro mecánico. Un SSD es un disco sin partes móviles: con él el equipo "
                "arranca y abre los programas mucho más rápido. Para el cambio hay que copiar tus archivos o "
                "reinstalar el sistema, por eso conviene hacerlo con un técnico.",
                basado, "media", "tecnico")


def _regla_ram_ampliar(res, h):
    ram, uso = _ram_gb(res), _num(_dato(res, "ram", "porcentaje_uso"))
    if ram is None or uso is None or ram >= 8 or uso < 80:
        return None
    detalle = ("Durante el análisis, tu equipo usaba casi toda su memoria RAM, que es el espacio donde "
               "trabajan los programas abiertos. Agregar más memoria suele hacerlo más ágil.")
    if ram <= 4:
        detalle += " Con tan poca memoria, varios programas a la vez irán lentos."
    return _rec("ram_ampliar", "Amplía la memoria RAM", detalle,
                [f"RAM: {_g(ram)} GB", f"Uso de RAM durante el análisis: {_g(uso)} %"], "media", "tecnico")


def _regla_respaldo(res, h):
    estado = _comp(res, "almacenamiento").get("estado")
    if estado not in ("sospecha", "critico"):
        return None
    basado = ["Estado del disco según Windows: " + ("con señales de desgaste" if estado == "sospecha" else "crítico")]
    if _comp(res, "almacenamiento").get("mensaje"):
        basado.append(_comp(res, "almacenamiento")["mensaje"])
    return _rec("respaldo", "Haz hoy una copia de tus archivos importantes",
                "Windows indica que tu disco tiene señales de desgaste. No significa que vaya a fallar mañana, "
                "pero conviene tener una copia. Guarda tus fotos, documentos y trabajos en otro disco, en un "
                "pendrive o en la nube.",
                basado, "alta", "tu_mismo")


def _regla_refrigeracion(res, h):
    estado = _comp(res, "cpu").get("estado")
    if estado not in ("advertencia", "critico"):
        return None
    temp = _num(_dato(res, "cpu", "temperatura_c"))
    basado = [f"Temperatura del procesador: {_g(temp)} °C" if temp is not None
              else "Estado del procesador durante el análisis: " + ("crítico" if estado == "critico" else "con advertencia")]
    return _rec("refrigeracion", "Revisa la limpieza y la refrigeración",
                "Tu procesador trabaja más caliente de lo normal. Suele deberse al polvo acumulado, a un "
                "ventilador que gira poco o a la pasta térmica (la pasta que ayuda a pasar el calor) ya seca. "
                "Mientras tanto, el equipo puede bajar su velocidad solo para protegerse. Un técnico puede "
                "limpiarlo y revisarlo.",
                basado, "alta" if estado == "critico" else "media", "tecnico")


def _reglas_bateria(res, h):
    if _dato(res, "bateria", "aplica") is not True:
        return []
    salud, ciclos = _num(_dato(res, "bateria", "salud_porcentaje")), _num(_dato(res, "bateria", "ciclos_carga"))
    recs = []
    if salud is not None and salud < 70:
        recs.append(_rec("bateria_cambio", "Planea cambiar la batería",
                         "Tu batería ya guarda bastante menos carga que cuando era nueva, así que el equipo "
                         "se apagará antes de lo que esperas cuando no esté enchufado. Puedes seguir usándolo; "
                         "conviene planear el cambio con un técnico.",
                         [f"Salud de la batería: {_g(round(salud, 1))} % de su capacidad original"],
                         "media" if salud < 40 else "baja", "tecnico"))
    basado = ([f"Ciclos de carga: {_g(ciclos)}"] if ciclos is not None else []) + \
             ([f"Salud de la batería: {_g(round(salud, 1))} % de su capacidad original"] if salud is not None else [])
    recs.append(_rec("bateria_cuidado", "Cuida tu batería",
                     "Evita el calor mientras carga, no la dejes llegar a 0 % seguido y, si el equipo casi "
                     "siempre está enchufado, procura no mantenerla al 100 % todo el tiempo. Puede ayudar a "
                     "que dure más; es una buena práctica, no una falla.",
                     basado or ["Se detectó una batería en el equipo"], "baja", "tu_mismo"))
    return recs


_REGLAS = (_regla_so, _regla_disco_ssd, _regla_ram_ampliar, _regla_respaldo, _regla_refrigeracion)


def recomendar(resultado, hechos) -> list:
    """Lista de recomendaciones ordenada alta -> media -> baja; `[]` si no hay nada que decir. Nunca lanza."""
    h = hechos if isinstance(hechos, dict) else {}
    recs = []
    for regla in _REGLAS + (_reglas_bateria,):
        try:
            salida = regla(resultado, h)
        except Exception:
            continue
        recs += salida if isinstance(salida, list) else [salida] if salida else []
    return sorted(recs, key=lambda r: _ORDEN_PRIORIDAD[r["prioridad"]])
