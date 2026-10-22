// frontend/static/js/modelo.js — Lógica pura (pestañas, tema, modo y datos del Resumen). Sin DOM ni window:
// se prueba con Node (frontend/tests/modelo.test.js). Script clásico: las funciones quedan globales.

const PESTANAS = ["resumen", "componentes", "recomendaciones", "analisis", "equipos", "postinstalacion"];
const SIEMPRE = ["resumen", "equipos", "postinstalacion"]; // no dependen de un escaneo de hardware

function _lista(habilitadas) {
    return Array.isArray(habilitadas) ? habilitadas.filter((p) => PESTANAS.includes(p)) : [];
}

// "#componentes" -> "componentes" si está habilitada; cualquier otra cosa -> "resumen".
function pestanaDesdeHash(hash, habilitadas) {
    const id = typeof hash === "string" ? hash.replace(/^#/, "") : "";
    return _lista(habilitadas).includes(id) ? id : "resumen";
}

// Flechas recorren circularmente solo las habilitadas; Home/End primera/última; otra tecla -> actual.
function siguientePestana(actual, tecla, habilitadas) {
    const lista = _lista(habilitadas);
    if (!lista.length) return actual;
    const i = lista.indexOf(actual);
    if (i < 0 && tecla === "ArrowLeft") return lista[lista.length - 1]; // actual desconocida: Izquierda -> última
    if (tecla === "ArrowRight") return lista[(i + 1) % lista.length];
    if (tecla === "ArrowLeft") return lista[(i - 1 + lista.length) % lista.length];
    if (tecla === "Home") return lista[0];
    if (tecla === "End") return lista[lista.length - 1];
    return actual;
}

// Claro por defecto: solo "oscuro" exacto activa el oscuro.
function temaValido(valor) {
    return valor === "oscuro" ? "oscuro" : "claro";
}

// Simple por defecto: solo "tecnico" exacto activa el técnico.
function modoValido(valor) {
    return valor === "tecnico" ? "tecnico" : "simple";
}

// Sin escaneo solo Resumen; "analisis" únicamente cuando la función existe (F4a).
function habilitadasSegun(tieneEscaneo, analisisDisponible) {
    if (!tieneEscaneo) return PESTANAS.filter((p) => SIEMPRE.includes(p));
    return PESTANAS.filter((p) => p !== "analisis" || analisisDisponible);
}

// --- Resumen: veredicto, línea, medida clave, datos del equipo y "lo primero". Todo devuelve texto plano (nunca HTML). ---
// En el navegador SEVERIDAD, CHIP_TEXTO y NOMBRES_COMPONENTES son globales de estado.js; en Node se importan.
const _E = typeof module !== "undefined" ? require("./estado.js") : { SEVERIDAD, CHIP_TEXTO, NOMBRES_COMPONENTES };

const _obj = (v) => (v !== null && typeof v === "object" && !Array.isArray(v) ? v : null);
const _num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
// Rangos plausibles (cpu.py usa 0-110 °C): un valor fuera de rango es un sensor con basura, no una medida.
const _rango = (v, min, max) => { const n = _num(v); return n !== null && n >= min && n <= max ? n : null; };
const _pos = (v) => { const n = _num(v); return n !== null && n > 0 ? n : null; };   // capacidades, núcleos, velocidades
const _pct = (v) => _rango(v, 0, 100);
const _temp = (v) => _rango(v, 0, 110);
const _txt = (v) => (typeof v === "string" && v.trim() ? v.trim() : null);
const _dec = (n) => String(Math.round(n * 10) / 10);   // a lo sumo un decimal: 476.9
const _datos = (info) => _obj(_obj(info)?.datos);
const _estadoDe = (info) => normalizarEstado(_obj(info)?.estado);
const _SIN_MEDIDA = "—";

function nombreComp(id) {
    return Object.hasOwn(_E.NOMBRES_COMPONENTES, id) ? _E.NOMBRES_COMPONENTES[id] : id;
}

// Cualquier cosa fuera de los 5 estados (backend raro o viejo) se trata como "no_determinado".
function normalizarEstado(estado) {
    return typeof estado === "string" && Object.hasOwn(_E.CHIP_TEXTO, estado) ? estado : "no_determinado";
}

// El estado más grave presente define el veredicto (orden de SEVERIDAD); sin componentes, NORMAL.
function calcularVeredicto(componentes) {
    const estados = new Set(Object.values(_obj(componentes) || {}).map(_estadoDe));
    for (const nivel of _E.SEVERIDAD) {
        if (estados.has(nivel)) return nivel.toUpperCase();
    }
    return "NORMAL";
}

// "Están bien: A, B. Necesitan atención: C. No se pudieron revisar: D." (sin grupos vacíos).
function lineaResumen(componentes) {
    const comps = _obj(componentes) || {};
    const ids = Object.keys(comps);
    if (!ids.length) return "";
    const grupo = (cumple) => ids.filter((id) => cumple(_estadoDe(comps[id]))).map(nombreComp);
    const bien = grupo((e) => e === "normal");
    const sinDatos = grupo((e) => e === "no_determinado");
    const atencion = grupo((e) => e !== "normal" && e !== "no_determinado");
    const noRevisados = sinDatos.length ? `No se pudieron revisar: ${sinDatos.join(", ")}.` : "";
    if (!bien.length && !atencion.length) {
        return `No pudimos leer ningún componente de tu PC: ${sinDatos.join(", ")}. Prueba cerrar y abrir de nuevo aceptando el aviso de Windows.`;
    }
    if (!atencion.length) return ["Todo lo que pudimos revisar está bien.", noRevisados].filter(Boolean).join(" ");
    return [bien.length && `Están bien: ${bien.join(", ")}.`, `Necesitan atención: ${atencion.join(", ")}.`, noRevisados].filter(Boolean).join(" ");
}

// Medida corta de la ficha: solo con datos reales; sin dato, "—".
const _MEDIDAS = {
    cpu(d) {
        const t = _temp(d.temperatura_c), n = _pos(d.nucleos_fisicos);
        return t !== null ? `${Math.round(t)} °C` : n !== null ? `${n} núcleos` : null;
    },
    ram(d) {
        const gb = _pos(d.capacidad_fisica_gb), uso = _pct(d.porcentaje_uso);
        return [gb !== null && `${_dec(gb)} GB`, uso !== null && `${Math.round(uso)} % en uso`].filter(Boolean).join(" · ") || null;
    },
    almacenamiento(d) {
        const disco = Array.isArray(d.discos_internos) ? _obj(d.discos_internos[0]) : null;
        if (!disco) return null;
        const gb = _pos(disco.tamano_gb);
        const salud = typeof disco.salud === "string" && Object.hasOwn(_E.CHIP_TEXTO, disco.salud)
            ? (disco.salud === "no_determinado" ? "no determinada" : _E.CHIP_TEXTO[disco.salud].toLowerCase()) : null;
        return [gb !== null && `${_dec(gb)} GB`, salud && `salud ${salud}`].filter(Boolean).join(" · ") || null;
    },
    bateria(d) {
        if (d.aplica === false) return "Sin batería";
        const s = _pct(d.salud_porcentaje);
        return d.aplica === true && s !== null ? `${Math.round(s)} % de salud` : null;
    },
    red(d) {
        const ifs = Array.isArray(d.interfaces) ? d.interfaces.map(_obj).filter(Boolean) : [];
        const conEnlace = ifs.filter((i) => i.link_activo === true);
        if (conEnlace.length) { // la primera con velocidad conocida; si ninguna la tiene, no hay medida
            const v = conEnlace.map((i) => _pos(i.velocidad_mbps)).find((x) => x !== null);
            return v !== undefined ? `${_dec(v)} Mbps` : null;
        }
        return ifs.some((i) => i.link_activo === false) ? "Sin enlace" : null;
    },
    mainboard(d) {
        const s = [_txt(d.fabricante), _txt(d.modelo)].filter(Boolean).join(" ");
        return s.length > 28 ? `${s.slice(0, 27)}…` : s || null;
    },
    fuente_poder(d) {
        const n = Array.isArray(d.rieles) ? d.rieles.length : 0;
        return n ? `${n} ${n === 1 ? "sensor" : "sensores"} de voltaje` : null;
    },
};

function medidaClave(id, info) {
    const d = _datos(info);
    if (!d || typeof id !== "string" || !Object.hasOwn(_MEDIDAS, id)) return _SIN_MEDIDA;
    return _MEDIDAS[id](d) || _SIN_MEDIDA;
}

// Datos del equipo: solo lo que se leyó. Los que no existen se omiten.
function datosEquipo(resultado) {
    const r = _obj(resultado) || {};
    const comps = _obj(r.componentes) || {};
    const hechos = _obj(r.hechos) || {};
    const d = (id) => _datos(comps[id]);
    const filas = [];
    const agregar = (etiqueta, valor) => { if (valor) filas.push({ etiqueta, valor }); };

    const mb = d("mainboard");
    agregar("Equipo", mb && [_txt(mb.fabricante), _txt(mb.modelo)].filter(Boolean).join(" "));
    agregar("Sistema", _txt(_obj(hechos.so)?.nombre));
    agregar("Procesador", _txt(d("cpu")?.nombre));
    const gb = _pos(d("ram")?.capacidad_fisica_gb);
    agregar("Memoria", gb !== null && `${_dec(gb)} GB`);

    let discos = (Array.isArray(hechos.discos) ? hechos.discos : []).map(_obj).filter((x) => x && x.externo !== true && _pos(x.tamano_gb) !== null);
    if (!discos.length) {
        const internos = d("almacenamiento")?.discos_internos;
        const primero = Array.isArray(internos) ? _obj(internos[0]) : null;
        discos = primero && _pos(primero.tamano_gb) !== null ? [primero] : [];
    }
    agregar("Disco", discos.map((x) => {
        const tipo = typeof x.tipo === "string" && ["ssd", "hdd"].includes(x.tipo) ? ` ${x.tipo.toUpperCase()}` : "";
        return `${_dec(x.tamano_gb)} GB${tipo}`;
    }).join(", "));
    return filas;
}

// Hasta `maximo` pasos: componentes con problema y recomendaciones de prioridad alta/media, por urgencia.
const _URGENCIAS = ["alta", "media", "baja"];
const _URGENCIA_POR_ESTADO = { critico: "alta", sospecha: "media" };

function loPrimero(resultado, maximo = 3) {
    const r = _obj(resultado) || {};
    const candidatos = [];
    Object.entries(_obj(r.componentes) || {}).forEach(([id, info], orden) => {
        const i = _obj(info);
        const estado = _estadoDe(i);
        if (!i || estado === "normal") return;
        const guia = _obj(i.guia);
        const pasos = guia && Array.isArray(guia.que_hacer) ? guia.que_hacer : [];
        candidatos.push({
            texto: _txt(pasos[0]) || _txt(i.mensaje) || `${nombreComp(id)}: ${_E.CHIP_TEXTO[estado]}`,
            destino: `componentes:${id}`,
            urgencia: guia && _URGENCIAS.includes(guia.urgencia) ? guia.urgencia : (_URGENCIA_POR_ESTADO[estado] || "baja"),
            peso: _E.SEVERIDAD.indexOf(estado), orden, sinDatos: estado === "no_determinado",
        });
    });
    (Array.isArray(r.recomendaciones) ? r.recomendaciones : []).forEach((rec, orden) => {
        const x = _obj(rec);
        if (x && ["alta", "media"].includes(x.prioridad) && _txt(x.titulo)) {
            candidatos.push({ texto: _txt(x.titulo), destino: "recomendaciones", urgencia: x.prioridad, peso: _E.SEVERIDAD.length, orden: 1000 + orden });
        }
    });
    // Un componente sin datos no desplaza a lo que sí se sabe que importa.
    const hayUrgente = candidatos.some((c) => !c.sinDatos && c.urgencia !== "baja");
    const vistos = new Set();
    const limite = Number.isFinite(maximo) ? Math.max(0, Math.floor(maximo)) : 3;
    return candidatos
        .filter((c) => !(hayUrgente && c.sinDatos))
        .sort((a, b) => _URGENCIAS.indexOf(a.urgencia) - _URGENCIAS.indexOf(b.urgencia) || a.peso - b.peso || a.orden - b.orden)
        .filter((c) => !vistos.has(c.texto) && vistos.add(c.texto))
        .slice(0, limite)
        .map(({ texto, destino, urgencia }) => ({ texto, destino, urgencia }));
}

// Orden estable de más a menos grave (estado desconocido = no_determinado).
function ordenarPorGravedad(ids, componentes) {
    const comps = _obj(componentes) || {};
    const peso = (id) => _E.SEVERIDAD.indexOf(_estadoDe(comps[id]));
    return (Array.isArray(ids) ? ids.slice() : []).sort((a, b) => peso(a) - peso(b));
}

// El componente seleccionado solo vale si es un componente propio del resultado (nunca una propiedad heredada).
function seleccionValida(id, componentes) {
    const comps = _obj(componentes);
    return typeof id === "string" && comps && Object.hasOwn(comps, id) && _obj(comps[id]) ? id : null;
}

// Respuesta de /api/scan aprovechable: un objeto con `componentes` objeto. Se valida ANTES de tocar la pantalla.
function resultadoValido(resultado) {
    return _obj(_obj(resultado)?.componentes) !== null;
}

const _MAX_FILAS_ANALISIS = 30;

function resultadoAnalisisValido(r) {
    return _obj(_obj(r)?.analisis) !== null;
}

// Listas de detalle de cada análisis: [{titulo, items: [texto crudo], mas}] (sin escapar; la vista usa textContent).
function detalleAnalisis(nombre, info) {
    const datos = _obj(_obj(info)?.datos) || {};
    const lista = (k) => (Array.isArray(datos[k]) ? datos[k] : []);
    const nombres = (a) => a.filter((x) => _obj(x) && typeof x.nombre === "string").map((x) => x.nombre);
    let grupos = [];
    if (nombre === "inicio") grupos = [["Se abren al encender", nombres(lista("entradas").filter((e) => _obj(e) && e.habilitado !== false))]];
    else if (nombre === "programas") grupos = [
        ["Recientes sin editor conocido", lista("recientes_sin_editor").filter((n) => typeof n === "string")],
        ["Ocultos por Windows", nombres(lista("programas").filter((p) => _obj(p) && p.oculto))],
    ];
    else if (nombre === "rendimiento") grupos = [
        ["Posibles causas", lista("causas").filter((c) => _obj(c) && typeof c.titulo === "string")
            .map((c) => c.titulo + (Array.isArray(c.evidencia) ? " — " + c.evidencia.filter((e) => typeof e === "string").join("; ") : ""))],
        ["Procesos que más procesador usan", lista("procesos_cpu").filter((p) => _obj(p) && typeof p.nombre === "string" && Number.isFinite(p.cpu))
            .map((p) => `${p.nombre} (${Math.round(p.cpu)} % CPU)`)],
    ];
    else if (nombre === "espacio") grupos = [["Dónde se va el espacio", lista("carpetas")
        .filter((c) => _obj(c) && typeof c.nombre === "string" && Number.isFinite(c.tamano_gb)).map((c) => `${c.nombre}: ${c.tamano_gb} GB`)]];
    else if (nombre === "estabilidad") grupos = [["Lo que Windows anotó (últimos 30 días)", [
        ["pantallazos_azules", "Pantallazos azules"], ["apagados_inesperados", "Apagados inesperados"], ["errores_disco", "Errores de disco"],
    ].filter(([k]) => Number.isFinite(datos[k])).map(([k, t]) => `${t}: ${datos[k]}`)]];
    else if (nombre === "controladores") grupos = [["Dispositivos con problema", nombres(lista("dispositivos"))]];
    else if (nombre === "seguridad") grupos = [
        ["Programas que corren desde Temp o Descargas", nombres(lista("procesos_en_carpetas_temporales"))],
        ["Líneas extra en el archivo hosts", lista("hosts_extra").filter((h) => typeof h === "string")],
        ["Otros avisos", datos.proxy_activo === true ? ["Hay un proxy configurado en Windows"] : []],
    ];
    return grupos.filter(([, items]) => items.length).map(([titulo, items]) => ({
        titulo, items: items.slice(0, _MAX_FILAS_ANALISIS), mas: Math.max(0, items.length - _MAX_FILAS_ANALISIS),
    }));
}

if (typeof module !== "undefined") {
    module.exports = {
        resultadoAnalisisValido, detalleAnalisis,
        PESTANAS, pestanaDesdeHash, siguientePestana, temaValido, modoValido, habilitadasSegun,
        nombreComp, normalizarEstado, calcularVeredicto, lineaResumen, medidaClave, datosEquipo, loPrimero, ordenarPorGravedad, seleccionValida, resultadoValido,
    };
}
