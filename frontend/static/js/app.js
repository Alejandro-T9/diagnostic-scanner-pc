// frontend/static/js/app.js — Lógica del dashboard de Diagnostic Scanner PC.
// Sin dependencias externas. Responsabilidades: polling de /api/status cada
// 2s (timestamp, salud de conexión), disparo de /api/scan, y el panel de
// detalle por componente (mapa físico + ficha, enlazados por selección).

// Nombres legibles de cada componente (mismo orden que backend/scanner.py COMPONENTES).
const NOMBRES_COMPONENTES = {
    mainboard: "Tarjeta Madre",
    cpu: "Procesador",
    ram: "Memoria RAM",
    almacenamiento: "Almacenamiento",
    fuente_poder: "Fuente de Poder",
    bateria: "Batería",
    red: "Red",
};

// Texto corto del chip de estado (la palabra "estado" ya no hace falta,
// el color + la palabra alcanzan). Mismos 5 niveles que
// backend/scanner.py ESTADOS_VALIDOS.
const CHIP_TEXTO = {
    normal: "Normal",
    advertencia: "Advertencia",
    sospecha: "Sospecha",
    critico: "Crítico",
    no_determinado: "Sin datos",
};

// Mismo orden que _SEVERIDAD en backend/scanner.py (ver decisión 22 en
// docs/DECISIONES.md): el estado más severo presente entre los
// componentes define el veredicto global. "no_determinado" pesa menos
// que "advertencia" — evidencia real de un problema en OTRO componente
// no debe quedar tapada en el titular por un sensor que no respondió.
const SEVERIDAD = ["critico", "sospecha", "advertencia", "no_determinado", "normal"];

// Posición aproximada de cada componente sobre la silueta de la laptop en
// el mapa físico (viewBox 300x260 de #mapa-svg) — ver frontend/templates/index.html.
const POSICIONES_MAPA = {
    mainboard: [150, 45],
    cpu: [110, 95],
    ram: [190, 95],
    almacenamiento: [230, 150],
    red: [70, 150],
    bateria: [150, 195],
    fuente_poder: [150, 130],
};

// Fragmentos de <path>/<rect> por componente (viewBox 24x24, stroke
// currentColor) — mismo ícono se usa en la fila de la ficha.
const ICONOS = {
    mainboard: '<rect x="4" y="4" width="16" height="16" rx="1.5"/><rect x="9" y="9" width="6" height="6"/><line x1="4" y1="9" x2="1.5" y2="9"/><line x1="4" y1="15" x2="1.5" y2="15"/><line x1="20" y1="9" x2="22.5" y2="9"/><line x1="20" y1="15" x2="22.5" y2="15"/>',
    cpu: '<rect x="6" y="6" width="12" height="12" rx="1"/><line x1="9" y1="2" x2="9" y2="6"/><line x1="15" y1="2" x2="15" y2="6"/><line x1="9" y1="18" x2="9" y2="22"/><line x1="15" y1="18" x2="15" y2="22"/><line x1="2" y1="9" x2="6" y2="9"/><line x1="2" y1="15" x2="6" y2="15"/><line x1="18" y1="9" x2="22" y2="9"/><line x1="18" y1="15" x2="22" y2="15"/>',
    ram: '<rect x="3" y="8" width="18" height="8" rx="1"/><line x1="7" y1="8" x2="7" y2="16"/><line x1="11" y1="8" x2="11" y2="16"/><line x1="15" y1="8" x2="15" y2="16"/>',
    almacenamiento: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/>',
    fuente_poder: '<path d="M13 2 4 14h6l-1 8 9-12h-6z"/>',
    bateria: '<rect x="4" y="7" width="14" height="10" rx="2"/><line x1="18" y1="10" x2="21" y2="10"/><line x1="18" y1="14" x2="21" y2="14"/>',
    red: '<path d="M5 12a10 10 0 0 1 14 0"/><path d="M8.5 15.5a5 5 0 0 1 7 0"/><circle cx="12" cy="19" r="1"/>',
};

// Etiquetas en español para las llaves de "datos" que devuelve cada
// módulo — ver backend/modules/*.py. Una llave sin entrada acá cae al
// fallback de _etiquetaCampo() (reemplaza guiones bajos, capitaliza).
const ETIQUETAS_CAMPOS = {
    fabricante: "Fabricante", modelo: "Modelo", version: "Versión",
    bios_vendor: "Proveedor BIOS", bios_version: "Versión BIOS", bios_fecha: "Fecha BIOS",
    nombre: "Nombre", arquitectura: "Arquitectura",
    nucleos_fisicos: "Núcleos físicos", hilos_logicos: "Hilos lógicos",
    frecuencia_maxima_mhz: "Frecuencia máxima", temperatura_c: "Temperatura",
    temperatura_gpu_c: "Temperatura GPU", ventiladores: "Ventiladores", rpm: "Velocidad",
    capacidad_fisica_gb: "Capacidad física instalada",
    capacidad_disponible_so_gb: "Disponible para el sistema operativo",
    velocidad_mhz: "Velocidad", frecuencia_actual_mhz: "Frecuencia actual",
    configuracion_canales: "Canales", modulos_detectados: "Módulos detectados",
    porcentaje_uso: "Uso", interfaz: "Interfaz", tamano_gb: "Tamaño",
    salud: "Salud", desgaste_porcentaje: "Desgaste", externo: "Conexión USB",
    horas_encendido: "Horas de encendido", errores_lectura: "Errores de lectura",
    aplica: "Aplica", estado_carga: "Estado de carga",
    porcentaje_carga_actual: "Carga actual", ciclos_carga: "Ciclos de carga",
    salud_porcentaje: "Salud", link_activo: "Enlace activo",
    velocidad_mbps: "Velocidad", errores_rx: "Errores recibidos",
    discos_internos: "Discos internos", discos_externos: "Discos externos (no afectan el estado)",
    interfaces: "Interfaces",
    origen: "Origen", sensor: "Sensor", voltios: "Voltaje", rieles: "Sensores de voltaje",
    gpu: "GPU", driver: "Controlador (driver)",
};

const DATOS_MOCK = {
    componentes: {
        mainboard: { componente: "mainboard", estado: "normal", mensaje: "Chipset y buses estables", datos: null },
        cpu: { componente: "cpu", estado: "normal", mensaje: "4 núcleos, 45°C", datos: null },
        ram: { componente: "ram", estado: "advertencia", mensaje: "8GB detectados, uso elevado", datos: null },
        almacenamiento: { componente: "almacenamiento", estado: "sospecha", mensaje: "Salud reducida (Windows Storage Health) en 1 disco", datos: null },
        fuente_poder: { componente: "fuente_poder", estado: "normal", mensaje: "Voltajes dentro de rango", datos: null },
        bateria: { componente: "bateria", estado: "critico", mensaje: "Capacidad al 42% del diseño original", datos: null },
        red: { componente: "red", estado: "no_determinado", mensaje: "No se detectó ninguna interfaz de red física", datos: null },
    },
};

let componenteSeleccionado = null;
let ultimoResultado = null; // {componentes, cobertura} del último render, para repintar al cambiar de modo
let tablaGuias = null;      // respuesta de /api/guias (guías por componente/estado + _veredictos)
let modo = "simple";
let escaneando = false;     // hay un /api/scan en curso
let escaneosReales = 0;     // cuenta resultados reales ya pintados (para abortar una demo que quedó atrás)

// Todo texto que venga del escaneo (mensaje, nombres de dispositivos, guía)
// pasa por acá antes de entrar a un innerHTML.
function escapar(valor) {
    return String(valor).replace(/[&<>"']/g, (c) => (
        { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
}

function crear(etiqueta, clase, texto) {
    const nodo = document.createElement(etiqueta);
    if (clase) nodo.className = clase;
    if (texto !== undefined) nodo.textContent = texto;
    return nodo;
}

function nombreComp(id) {
    return NOMBRES_COMPONENTES[id] || id;
}

function iconoSvg(id) {
    return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">${ICONOS[id] || ""}</svg>`;
}

function calcularVeredicto(componentes) {
    const estados = new Set(Object.values(componentes).map((c) => c.estado));
    for (const nivel of SEVERIDAD) {
        if (estados.has(nivel)) return nivel.toUpperCase();
    }
    return "NORMAL";
}

function resaltarComponente(id, activo) {
    document.querySelectorAll(`[data-id="${id}"]`).forEach((el) => el.classList.toggle("resaltado", activo));
}

function marcarSeleccionado(id) {
    document.querySelectorAll(".punto, .fila").forEach((el) => {
        el.classList.toggle("seleccionado", el.dataset.id === id);
    });
}

function renderizarResumen(componentes, cobertura) {
    const veredicto = calcularVeredicto(componentes);
    const sello = document.getElementById("sello");
    // Modo simple: frase en palabras (tabla del backend); sin tabla, el texto de siempre.
    const frase = tablaGuias && tablaGuias._veredictos && tablaGuias._veredictos[veredicto];
    sello.textContent = modo === "simple" && frase ? frase : veredicto;
    sello.className = `sello ${veredicto}`;

    const conteo = { normal: 0, advertencia: 0, sospecha: 0, critico: 0, no_determinado: 0 };
    Object.values(componentes).forEach((c) => { conteo[c.estado] = (conteo[c.estado] || 0) + 1; });

    // Solo se muestran los niveles con al menos 1 componente, en orden de
    // severidad — con 7 componentes y 5 estados posibles, listar ceros
    // sería puro ruido.
    const partes = SEVERIDAD.filter((nivel) => conteo[nivel] > 0)
        .map((nivel) => `${conteo[nivel]} ${CHIP_TEXTO[nivel].toLowerCase()}`);
    document.getElementById("resumen-texto").textContent = partes.join(" · ");

    // Sin cobertura (modo demo): se limpia en vez de mostrar
    // un dato que no vino de un escaneo real.
    document.getElementById("cobertura-texto").textContent = cobertura
        ? `Cobertura: ${cobertura.porcentaje}% (${cobertura.completos}/${cobertura.completos + cobertura.parciales} evaluados por completo)`
        : "";
}

function renderizarDiagnostico(componentes, cobertura) {
    document.body.classList.remove("sin-escaneo");
    // Un estado desconocido (backend raro/viejo) se trata como "no_determinado":
    // así ninguna clase CSS ni texto sale de un valor no previsto.
    for (const info of Object.values(componentes)) {
        if (!Object.hasOwn(CHIP_TEXTO, info.estado)) info.estado = "no_determinado";
    }
    const svg = document.getElementById("mapa-svg");
    svg.querySelectorAll(".punto, .punto-etiqueta").forEach((el) => el.remove());

    const filasEl = document.getElementById("filas");
    filasEl.innerHTML = "";

    for (const [id, info] of Object.entries(componentes)) {
        const posicion = POSICIONES_MAPA[id];
        if (posicion) {
            const [x, y] = posicion;
            const grupo = document.createElementNS("http://www.w3.org/2000/svg", "g");
            grupo.setAttribute("class", `punto ${info.estado}`);
            grupo.dataset.id = id;
            grupo.setAttribute("transform", `translate(${x},${y})`);
            grupo.innerHTML = '<circle class="halo" r="16"></circle><circle class="nucleo" r="6"></circle>';
            grupo.addEventListener("mouseenter", () => resaltarComponente(id, true));
            grupo.addEventListener("mouseleave", () => resaltarComponente(id, false));
            grupo.addEventListener("click", () => seleccionarComponente(id, info));
            svg.appendChild(grupo);

            const etiqueta = document.createElementNS("http://www.w3.org/2000/svg", "text");
            etiqueta.setAttribute("class", "punto-etiqueta");
            etiqueta.setAttribute("x", x);
            etiqueta.setAttribute("y", y > 100 ? y + 26 : y - 14);
            etiqueta.setAttribute("text-anchor", "middle");
            etiqueta.textContent = nombreComp(id).split(" ")[0].toUpperCase();
            svg.appendChild(etiqueta);
        }

        const fila = document.createElement("div");
        fila.className = "fila";
        fila.dataset.id = id;
        fila.innerHTML = `
            <div class="franja ${escapar(info.estado)}"></div>
            <div class="fila-icono">${iconoSvg(id)}</div>
            <div class="fila-info">
                <div class="nombre">${escapar(nombreComp(id))}</div>
                <div class="detalle">${escapar(info.mensaje)}</div>
            </div>
            <div class="fila-chip ${escapar(info.estado)}">${escapar(CHIP_TEXTO[info.estado] || info.estado)}</div>
        `;
        fila.addEventListener("mouseenter", () => resaltarComponente(id, true));
        fila.addEventListener("mouseleave", () => resaltarComponente(id, false));
        fila.addEventListener("click", () => seleccionarComponente(id, info));
        filasEl.appendChild(fila);
    }

    ultimoResultado = { componentes, cobertura };
    renderizarResumen(componentes, cobertura);
    renderizarSimple(componentes);
}

function seleccionarComponente(id, info) {
    componenteSeleccionado = id;
    marcarSeleccionado(id);
    renderizarDetalle(id, info);
}

function _etiquetaCampo(clave) {
    if (ETIQUETAS_CAMPOS[clave]) return ETIQUETAS_CAMPOS[clave];
    return clave.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

function _formatearValor(clave, valor) {
    if (valor === null || valor === undefined) return "—";
    if (typeof valor === "boolean") return valor ? "Sí" : "No";
    if (clave.endsWith("_mhz")) return `${valor} MHz`;
    if (clave.endsWith("_gb")) return `${valor} GB`;
    if (clave.endsWith("_c")) return `${valor}°C`;
    if (clave.endsWith("_mbps")) return `${valor} Mbps`;
    if (clave === "voltios") return `${valor} V`;
    if (clave === "rpm") return `${valor} RPM`;
    if (clave.includes("porcentaje") || clave.startsWith("salud_")) return `${valor}%`;
    if (clave === "horas_encendido") return `${valor} h`;
    return String(valor);
}

// Arma el detalle "lo más interno posible" a partir del dict "datos" tal
// cual lo devuelve cada módulo, sin lógica particular por componente:
// - un array (ej. datos.discos_internos, datos.interfaces) se desglosa
//   en un subitem por elemento;
// - un objeto anidado (ej. datos.gpu) se desglosa recursivamente con la
//   misma función, en vez de un caso especial por llave — así un módulo
//   futuro puede anidar lo que necesite (ej. bateria.cargador) sin tocar
//   este renderer de nuevo;
// - cualquier otra llave se muestra como fila etiqueta/valor.
function _renderizarCuerpoDatos(datos) {
    return Object.entries(datos).map(([clave, valor]) => {
        if (Array.isArray(valor)) {
            const items = valor.map((item) => `
                <div class="detalle-subitem">
                    ${Object.entries(item).map(([k, v]) => `
                        <div class="detalle-fila"><span>${escapar(_etiquetaCampo(k))}</span><span class="dato-tecnico">${escapar(_formatearValor(k, v))}</span></div>
                    `).join("")}
                </div>
            `).join("");
            return `<div class="detalle-grupo"><h4>${escapar(_etiquetaCampo(clave))}</h4>${items}</div>`;
        }
        if (valor !== null && typeof valor === "object") {
            return `<div class="detalle-grupo"><h4>${escapar(_etiquetaCampo(clave))}</h4>${_renderizarCuerpoDatos(valor)}</div>`;
        }
        return `<div class="detalle-fila"><span>${escapar(_etiquetaCampo(clave))}</span><span class="dato-tecnico">${escapar(_formatearValor(clave, valor))}</span></div>`;
    }).join("");
}

function renderizarDetalle(id, info) {
    const panel = document.getElementById("detalle-panel");
    const cuerpo = info.datos
        ? _renderizarCuerpoDatos(info.datos)
        : `<p class="detalle-sin-datos">Sin datos técnicos adicionales para este componente.</p>`;

    const recomendacion = info.recomendacion
        ? `<div class="detalle-recomendacion"><strong>Recomendación:</strong> ${escapar(info.recomendacion)}</div>`
        : "";

    panel.innerHTML = `
        <div class="detalle-cabecera">
            <h3>${escapar(nombreComp(id))}</h3>
            <span class="fila-chip ${escapar(info.estado)}">${escapar(CHIP_TEXTO[info.estado] || info.estado)}</span>
        </div>
        <p class="detalle-mensaje">${escapar(info.mensaje)}</p>
        ${recomendacion}
        ${bloqueGuiaHtml(info.guia)}
        ${cuerpo}
    `;
}

const QUIEN_TEXTO = {
    tu_mismo: "Lo puedes hacer tú",
    tecnico: "Mejor con un técnico",
    nadie: "No necesita acción",
};

function pasosGuia(guia) {
    return Array.isArray(guia.que_hacer) ? guia.que_hacer : [];
}

// Guía en el panel de detalle (modo técnico). Sin guía no se dibuja nada.
function bloqueGuiaHtml(guia) {
    if (!guia) return "";
    const pasos = pasosGuia(guia).map((p) => `<li>${escapar(p)}</li>`).join("");
    return `
        <div class="detalle-guia">
            <h4>Guía</h4>
            <p><strong>Qué significa:</strong> ${escapar(guia.que_significa || "")}</p>
            ${pasos ? `<p><strong>Qué hacer:</strong></p><ol>${pasos}</ol>` : ""}
            <p><strong>Quién lo hace:</strong> ${escapar(QUIEN_TEXTO[guia.quien] || guia.quien || "")}</p>
        </div>
    `;
}

// --- Modo simple: veredicto en palabras, una línea de resumen y una tarjeta
// por componente de más a menos grave. Solo DOM + textContent. ---
function renderizarSimple(componentes) {
    const ids = Object.keys(componentes);
    const bien = ids.filter((id) => componentes[id].estado === "normal").map(nombreComp);
    const sinDatos = ids.filter((id) => componentes[id].estado === "no_determinado").map(nombreComp);
    const atencion = ids.filter((id) => !["normal", "no_determinado"].includes(componentes[id].estado)).map(nombreComp);
    const noRevisados = sinDatos.length ? `No se pudieron revisar: ${sinDatos.join(", ")}.` : "";
    let linea;
    if (!bien.length && !atencion.length) linea = `No pudimos leer ningún componente de tu PC: ${sinDatos.join(", ")}. Prueba cerrar y abrir de nuevo aceptando el aviso de Windows.`;
    else if (!atencion.length) linea = ["Todo lo que pudimos revisar está bien.", noRevisados].filter(Boolean).join(" ");
    else linea = [bien.length && `Están bien: ${bien.join(", ")}.`, `Necesitan atención: ${atencion.join(", ")}.`, noRevisados].filter(Boolean).join(" ");
    document.getElementById("simple-resumen").textContent = linea;

    const contenedor = document.getElementById("simple-tarjetas");
    contenedor.replaceChildren();
    const orden = (id) => {
        const i = SEVERIDAD.indexOf(componentes[id].estado);
        return i < 0 ? SEVERIDAD.length : i;
    };
    ids.slice().sort((a, b) => orden(a) - orden(b)).forEach((id) => {
        const info = componentes[id];
        const tarjeta = crear("div", `tarjeta-simple ${info.estado}`);
        const cab = crear("div", "tarjeta-simple-cabecera");
        cab.append(crear("h3", "", nombreComp(id)),
            crear("span", `fila-chip ${info.estado}`, CHIP_TEXTO[info.estado] || info.estado));
        tarjeta.append(cab, crear("p", "tarjeta-simple-mensaje", info.mensaje));
        const guia = info.guia;
        if (guia) {
            if (guia.que_significa) tarjeta.append(crear("p", "", guia.que_significa));
            const pasos = pasosGuia(guia);
            if (pasos.length) {
                if (info.estado === "normal") { const t = crear("p", ""); t.append(crear("strong", "", "Para mantenerlo bien:")); tarjeta.append(t); }
                const lista = crear("ol", "tarjeta-simple-pasos");
                pasos.forEach((p) => lista.append(crear("li", "", p)));
                tarjeta.append(lista);
            }
            const etiquetas = crear("div", "tarjeta-simple-etiquetas");
            if (QUIEN_TEXTO[guia.quien]) etiquetas.append(crear("span", `etiqueta-quien ${guia.quien}`, QUIEN_TEXTO[guia.quien]));
            if (["baja", "media", "alta"].includes(guia.urgencia)) {
                etiquetas.append(crear("span", `etiqueta-urgencia ${guia.urgencia}`, `Urgencia: ${guia.urgencia}`));
            }
            if (etiquetas.childNodes.length) tarjeta.append(etiquetas);
        }
        contenedor.append(tarjeta);
    });
}

// Estado inicial (y tras cambiar de modo sin escaneo): sin datos inventados.
function pintarVacio() {
    document.body.classList.add("sin-escaneo");
    const sello = document.getElementById("sello");
    sello.textContent = "Sin escaneo todavía";
    sello.className = "sello NO_DETERMINADO";
    document.getElementById("resumen-texto").textContent = "";
    document.getElementById("cobertura-texto").textContent = "";
    document.getElementById("filas").replaceChildren();
    document.getElementById("mapa-svg").querySelectorAll(".punto, .punto-etiqueta").forEach((el) => el.remove());
}

function repintar() {
    if (!ultimoResultado) { pintarVacio(); return; }
    renderizarDiagnostico(ultimoResultado.componentes, ultimoResultado.cobertura);
    if (componenteSeleccionado && ultimoResultado.componentes[componenteSeleccionado]) {
        seleccionarComponente(componenteSeleccionado, ultimoResultado.componentes[componenteSeleccionado]);
    }
}

function aplicarModo(nuevo, guardar) {
    modo = nuevo === "tecnico" ? "tecnico" : "simple";
    document.body.classList.toggle("modo-simple", modo === "simple");
    document.getElementById("modo-simple-btn").setAttribute("aria-pressed", String(modo === "simple"));
    document.getElementById("modo-tecnico-btn").setAttribute("aria-pressed", String(modo === "tecnico"));
    if (guardar) {
        try { localStorage.setItem("modo_interfaz", modo); } catch (e) { /* sin almacenamiento: solo no se recuerda */ }
    }
    repintar();
}

// Tabla de guías + frases de veredicto. Si falla, la app sigue sin guías.
async function cargarGuias() {
    if (tablaGuias) return tablaGuias;
    try {
        const respuesta = await fetch("/api/guias");
        if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
        tablaGuias = await respuesta.json();
    } catch (error) {
        tablaGuias = null;
    }
    return tablaGuias;
}

function mostrarError(mensaje) {
    const aviso = document.getElementById("aviso-error");
    aviso.textContent = mensaje;
    aviso.classList.add("activo");
}

function ocultarError() {
    document.getElementById("aviso-error").classList.remove("activo");
}

// Polling liviano: solo confirma que el backend sigue vivo y refresca el
// timestamp. No toca el diagnóstico — eso solo cambia con un escaneo real.
async function actualizarStatus() {
    try {
        const respuesta = await fetch("/api/status");
        if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
        const datos = await respuesta.json();
        document.getElementById("timestamp").textContent =
            `Última actualización: ${new Date(datos.timestamp).toLocaleTimeString()}`;
        // Aviso de falta de administrador: solo tiene sentido en Windows
        // normal (WinPE ya corre con todos los permisos).
        const sinAdmin = datos.administrador === false && datos.entorno === "windows";
        document.getElementById("aviso-admin").classList.toggle("activo", sinAdmin);
        ocultarError();
    } catch (error) {
        mostrarError("No se pudo conectar con el backend. Verifica que el servidor esté corriendo.");
    }
}

async function escanearSistema() {
    const boton = document.getElementById("boton-escanear");
    const botonRevisar = document.getElementById("boton-revisar");
    const barra = document.getElementById("barra-progreso-contenedor");
    escaneando = true;
    boton.disabled = true;
    botonRevisar.disabled = true;
    barra.classList.add("activa");
    try {
        const guias = cargarGuias(); // en paralelo al escaneo: el sello en palabras necesita _veredictos (nunca lanza)
        const respuesta = await fetch("/api/scan");
        if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
        const resultado = await respuesta.json();
        await guias;
        ocultarDemo(); // un escaneo real siempre reemplaza al modo demo
        escaneosReales++;
        renderizarDiagnostico(resultado.componentes, resultado.cobertura);
        // Si había un componente abierto, se refresca con el dato nuevo en
        // vez de perder la selección en cada escaneo.
        if (componenteSeleccionado && resultado.componentes[componenteSeleccionado]) {
            seleccionarComponente(componenteSeleccionado, resultado.componentes[componenteSeleccionado]);
        }
        ocultarError();
    } catch (error) {
        mostrarError("No se pudo completar el escaneo. Verifica que el servidor esté corriendo.");
    } finally {
        escaneando = false;
        boton.disabled = false;
        botonRevisar.disabled = false;
        barra.classList.remove("activa");
    }
}

// Modo demo: para preparar la sustentación sin depender de que la laptop
// de turno tenga justo algo mal en ese momento. Reusa DATOS_MOCK (ya
// ejercita los 5 estados a la vez) — no usa /api/scan (solo pide la tabla de
// guías), y el aviso de datos simulados se muestra junto con los datos falsos.
// La clase "demo" en <body> oculta el botón del informe (no hay escaneo real).
function mostrarDemo() {
    document.getElementById("aviso-demo").classList.add("activo");
    document.body.classList.add("demo");
}

function ocultarDemo() {
    document.getElementById("aviso-demo").classList.remove("activo");
    document.body.classList.remove("demo");
}

async function verModoDemo() {
    if (escaneando) return; // un escaneo real en curso manda sobre la demo
    const antes = escaneosReales;
    const tabla = await cargarGuias();
    // Si un escaneo real empezó o terminó mientras esperábamos, no se pinta la demo encima.
    if (escaneando || escaneosReales !== antes) return;
    mostrarDemo();
    for (const info of Object.values(DATOS_MOCK.componentes)) {
        const guia = tabla && tabla[info.componente] && tabla[info.componente][info.estado];
        if (guia) info.guia = guia; else delete info.guia;
    }
    renderizarDiagnostico(DATOS_MOCK.componentes);
    componenteSeleccionado = null;
    document.getElementById("detalle-panel").innerHTML =
        '<p class="detalle-vacio">Selecciona un componente del mapa o la lista para ver el detalle completo.</p>';
}

document.getElementById("boton-escanear").addEventListener("click", escanearSistema);
document.getElementById("boton-revisar").addEventListener("click", escanearSistema);
document.getElementById("boton-demo").addEventListener("click", verModoDemo);

// Sin menú contextual: el dashboard corre en un kiosk sin teclado/mouse
// de uso general, y el clic derecho de Chromium expone "Inspeccionar"
// entre otras cosas que no queremos a mano en ese contexto.
document.addEventListener("contextmenu", (evento) => evento.preventDefault());

document.getElementById("modo-simple-btn").addEventListener("click", () => aplicarModo("simple", true));
document.getElementById("modo-tecnico-btn").addEventListener("click", () => aplicarModo("tecnico", true));

let modoGuardado = null;
try { modoGuardado = localStorage.getItem("modo_interfaz"); } catch (e) { /* almacenamiento bloqueado: se usa el modo simple */ }
aplicarModo(modoGuardado, false);

// Arranque: sin datos hasta el primer escaneo (DATOS_MOCK solo sale con "Ver Modo Demostración").

// Frases de veredicto para el sello; al llegar se repinta (si falla, queda el texto de siempre).
cargarGuias().then((t) => { if (t) repintar(); });
actualizarStatus();
setInterval(actualizarStatus, 2000);
