// frontend/static/js/app.js — Lógica del dashboard de Diagnostic Scanner PC.
// Sin dependencias externas. Responsabilidades: polling de /api/status cada
// 2s (timestamp, salud de conexión), disparo de /api/scan, y el panel de
// detalle por componente (mapa físico + ficha, enlazados por selección), y el armazón:
// pestañas (con hash en la URL), menú "Más" y botón único de revisión.

let componenteSeleccionado = null;
let ultimoResultado = null; // resultado del último render ({componentes, hechos, cobertura, recomendaciones}), para repintar al cambiar de modo
let tablaGuias = null;      // respuesta de /api/guias (guías por componente/estado + _veredictos)
let modo = "simple";
let escaneando = false;     // hay un /api/scan en curso
let escaneosReales = 0;     // cuenta resultados reales ya pintados (para abortar una demo que quedó atrás)

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

// resultado = {componentes, hechos?, cobertura?, recomendaciones?}. El Resumen lo dibuja vistas.js; el panel de
// diagnóstico (sello, mapa y filas) sigue provisionalmente en Componentes hasta que se rehaga esa pestaña.
function renderizarDiagnostico(resultado) {
    const { componentes, cobertura, recomendaciones } = resultado;
    document.body.classList.remove("sin-escaneo");
    // Un estado desconocido (backend raro/viejo) se trata como "no_determinado":
    // así ninguna clase CSS ni texto sale de un valor no previsto.
    for (const info of Object.values(componentes)) info.estado = normalizarEstado(info.estado);
    const svg = document.getElementById("mapa-svg");
    svg.querySelectorAll(".punto, .punto-etiqueta").forEach((el) => el.remove());

    const filasEl = document.getElementById("filas");
    filasEl.replaceChildren();

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
            grupo.addEventListener("click", () => abrirComponente(id, info));
            svg.appendChild(grupo);

            const etiqueta = document.createElementNS("http://www.w3.org/2000/svg", "text");
            etiqueta.setAttribute("class", "punto-etiqueta");
            etiqueta.setAttribute("x", x);
            etiqueta.setAttribute("y", y > 100 ? y + 26 : y - 14);
            etiqueta.setAttribute("text-anchor", "middle");
            etiqueta.textContent = nombreComp(id).split(" ")[0].toUpperCase();
            svg.appendChild(etiqueta);
        }

        const fila = crear("div", "fila");
        fila.dataset.id = id;
        const icono = crear("div", "fila-icono");
        icono.append(crearIcono(iconoComponente(id)));
        const textos = crear("div", "fila-info");
        textos.append(crear("div", "nombre", nombreComp(id)), crear("div", "detalle", info.mensaje));
        fila.append(crear("div", `franja ${info.estado}`), icono, textos, crearChipEstado(info.estado));
        fila.addEventListener("mouseenter", () => resaltarComponente(id, true));
        fila.addEventListener("mouseleave", () => resaltarComponente(id, false));
        fila.addEventListener("click", () => abrirComponente(id, info));
        filasEl.appendChild(fila);
    }

    ultimoResultado = resultado;
    dibujarResumen(resultado, document.getElementById("resumen-vista"));
    renderizarResumen(componentes, cobertura);
    renderizarSimple(componentes);
    renderizarRecomendaciones(recomendaciones);
    actualizarPestanas();
}

function seleccionarComponente(id, info) {
    componenteSeleccionado = id;
    marcarSeleccionado(id);
    renderizarDetalle(id, info);
}

// Clic en un punto del mapa o una fila (pestaña Resumen): el detalle vive en Componentes.
function abrirComponente(id, info) {
    seleccionarComponente(id, info);
    activarPestana("componentes", true);
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
// Devuelve un arreglo de nodos (todo por textContent: nada del escaneo entra como HTML).
function _filaDato(clave, valor) {
    const fila = crear("div", "detalle-fila");
    fila.append(crear("span", "", _etiquetaCampo(clave)), crear("span", "dato-tecnico", _formatearValor(clave, valor)));
    return fila;
}

function _renderizarCuerpoDatos(datos) {
    return Object.entries(datos).map(([clave, valor]) => {
        const esArray = Array.isArray(valor);
        if (!esArray && (valor === null || typeof valor !== "object")) return _filaDato(clave, valor);
        const grupo = crear("div", "detalle-grupo");
        grupo.append(crear("h4", "", _etiquetaCampo(clave)));
        if (esArray) {
            valor.forEach((item) => {
                const sub = crear("div", "detalle-subitem");
                sub.append(...Object.entries(item).map(([k, v]) => _filaDato(k, v)));
                grupo.append(sub);
            });
        } else {
            grupo.append(..._renderizarCuerpoDatos(valor));
        }
        return grupo;
    });
}

function renderizarDetalle(id, info) {
    const panel = document.getElementById("detalle-panel");
    const cabecera = crear("div", "detalle-cabecera");
    cabecera.append(crear("h3", "", nombreComp(id)), crearChipEstado(info.estado));
    panel.replaceChildren(cabecera, crear("p", "detalle-mensaje", info.mensaje));

    if (info.recomendacion) {
        const recomendacion = crear("div", "detalle-recomendacion");
        recomendacion.append(crear("strong", "", "Recomendación:"), ` ${info.recomendacion}`);
        panel.append(recomendacion);
    }
    const guia = bloqueGuia(info.guia);
    if (guia) panel.append(guia);
    if (info.datos) panel.append(..._renderizarCuerpoDatos(info.datos));
    else panel.append(crear("p", "detalle-sin-datos", "Sin datos técnicos adicionales para este componente."));
}

function pasosGuia(guia) {
    return Array.isArray(guia.que_hacer) ? guia.que_hacer : [];
}

// Guía en el panel de detalle (modo técnico). Sin guía no se dibuja nada.
function bloqueGuia(guia) {
    if (!guia) return null;
    const rotulado = (rotulo, texto) => {
        const p = crear("p");
        p.append(crear("strong", "", rotulo), ` ${texto}`);
        return p;
    };
    const bloque = crear("div", "detalle-guia");
    bloque.append(crear("h4", "", "Guía"), rotulado("Qué significa:", guia.que_significa || ""));
    const pasos = pasosGuia(guia);
    if (pasos.length) {
        const lista = crear("ol");
        pasos.forEach((p) => lista.append(crear("li", "", p)));
        const titulo = crear("p");
        titulo.append(crear("strong", "", "Qué hacer:"));
        bloque.append(titulo, lista);
    }
    bloque.append(rotulado("Quién lo hace:", Object.hasOwn(QUIEN_TEXTO, guia.quien) ? QUIEN_TEXTO[guia.quien] : guia.quien || ""));
    return bloque;
}

// --- Modo simple: veredicto en palabras, una línea de resumen y una tarjeta
// por componente de más a menos grave. Solo DOM + textContent. ---
function renderizarSimple(componentes) {
    const ids = Object.keys(componentes);
    document.getElementById("simple-resumen").textContent = lineaResumen(componentes);

    const contenedor = document.getElementById("simple-tarjetas");
    contenedor.replaceChildren();
    ordenarPorGravedad(ids, componentes).forEach((id) => {
        const info = componentes[id];
        const tarjeta = crear("div", `tarjeta-simple ${info.estado}`);
        const cab = crear("div", "tarjeta-simple-cabecera");
        cab.append(crear("h3", "", nombreComp(id)),
            crearChipEstado(info.estado));
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
            if (Object.hasOwn(QUIEN_TEXTO, guia.quien)) etiquetas.append(crear("span", `etiqueta-quien ${guia.quien}`, QUIEN_TEXTO[guia.quien]));
            if (["baja", "media", "alta"].includes(guia.urgencia)) {
                etiquetas.append(crear("span", `etiqueta-urgencia ${guia.urgencia}`, `Urgencia: ${guia.urgencia}`));
            }
            if (etiquetas.childNodes.length) tarjeta.append(etiquetas);
        }
        contenedor.append(tarjeta);
    });
}

// Recomendaciones del equipo (F3): solo de escaneos reales que las traigan; sin lista, el bloque no existe.
function renderizarRecomendaciones(recomendaciones) {
    const bloque = document.getElementById("recomendaciones");
    bloque.replaceChildren();
    const lista = Array.isArray(recomendaciones) ? recomendaciones.filter((r) => r && typeof r === "object") : [];
    bloque.hidden = !lista.length;
    if (!lista.length) return;
    bloque.append(crear("h2", "", "Recomendaciones para tu equipo"),
        crear("p", "recomendaciones-nota", "Son sugerencias basadas en lo que se pudo medir en este equipo."));
    const texto = (v) => (typeof v === "string" ? v : "");
    lista.forEach((rec) => {
        const tarjeta = crear("div", "tarjeta-simple recomendacion");
        tarjeta.append(crear("h3", "", texto(rec.titulo)));
        if (texto(rec.detalle)) tarjeta.append(crear("p", "", rec.detalle));
        if (Array.isArray(rec.basado_en) && rec.basado_en.some((b) => typeof b === "string")) {
            tarjeta.append(crear("p", "", "Basado en:"));
            const ul = crear("ul", "tarjeta-simple-pasos");
            rec.basado_en.filter((b) => typeof b === "string").forEach((b) => ul.append(crear("li", "", b)));
            tarjeta.append(ul);
        }
        if (Array.isArray(rec.opciones)) {
            rec.opciones.filter((o) => o && typeof o.nombre === "string").forEach((o) => {
                const det = crear("details", "recomendacion-opcion");
                det.append(crear("summary", "", o.nombre));
                if (texto(o.motivo)) det.append(crear("p", "", o.motivo));
                if (texto(o.nota)) det.append(crear("p", "", o.nota));
                tarjeta.append(det);
            });
        }
        const etiquetas = crear("div", "tarjeta-simple-etiquetas");
        if (["baja", "media", "alta"].includes(rec.prioridad)) {
            etiquetas.append(crear("span", `etiqueta-urgencia ${rec.prioridad}`, `Prioridad: ${rec.prioridad}`));
        }
        if (rec.quien === "tu_mismo" || rec.quien === "tecnico") {
            etiquetas.append(crear("span", `etiqueta-quien ${rec.quien}`, QUIEN_TEXTO[rec.quien]));
        }
        if (etiquetas.childNodes.length) tarjeta.append(etiquetas);
        bloque.append(tarjeta);
    });
}

// Estado inicial (y tras cambiar de modo sin escaneo): sin datos inventados.
function pintarVacio() {
    document.body.classList.add("sin-escaneo");
    renderizarRecomendaciones(null);
    dibujarResumen(null, document.getElementById("resumen-vista"));
    if (escaneando) marcarOcupado(true); // el botón del estado vacío acaba de recrearse
    const sello = document.getElementById("sello");
    sello.textContent = "Sin escaneo todavía";
    sello.className = "sello NO_DETERMINADO";
    document.getElementById("resumen-texto").textContent = "";
    document.getElementById("cobertura-texto").textContent = "";
    document.getElementById("filas").replaceChildren();
    document.getElementById("mapa-svg").querySelectorAll(".punto, .punto-etiqueta").forEach((el) => el.remove());
    actualizarPestanas();
}

function repintar() {
    if (!ultimoResultado) { pintarVacio(); return; }
    renderizarDiagnostico(ultimoResultado);
    if (componenteSeleccionado && ultimoResultado.componentes[componenteSeleccionado]) {
        seleccionarComponente(componenteSeleccionado, ultimoResultado.componentes[componenteSeleccionado]);
    }
}

function aplicarModo(nuevo, guardar) {
    modo = modoValido(nuevo);
    document.body.classList.toggle("modo-simple", modo === "simple");
    document.getElementById("modo-simple-btn").setAttribute("aria-pressed", String(modo === "simple"));
    document.getElementById("modo-tecnico-btn").setAttribute("aria-pressed", String(modo === "tecnico"));
    if (guardar) {
        try { localStorage.setItem("modo_interfaz", modo); } catch (e) { /* sin almacenamiento: solo no se recuerda */ }
    }
    repintar();
}

// Tema claro/oscuro (temaValido vive en modelo.js: claro por defecto).
function aplicarTema(tema, guardar) {
    const oscuro = temaValido(tema) === "oscuro";
    if (oscuro) document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.removeAttribute("data-theme");
    const boton = document.getElementById("boton-tema");
    // Etiqueta fija ("Tema oscuro", solo para lectores de pantalla); el estado lo comunica aria-pressed.
    if (boton) boton.setAttribute("aria-pressed", String(oscuro));
    const icono = document.getElementById("boton-tema-icono");
    if (icono) icono.replaceChildren(crearIcono(iconoUi(oscuro ? "tema-claro" : "tema-oscuro")));
    if (guardar) {
        try { localStorage.setItem("tema_interfaz", oscuro ? "oscuro" : "claro"); } catch (e) { /* sin almacenamiento: solo no se recuerda */ }
    }
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
    document.getElementById("aviso-error-texto").textContent = mensaje;
    document.getElementById("aviso-error").classList.add("activo");
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

// Botón único de revisión (barra superior + el grande del estado vacío): ocupado mientras corre el escaneo.
function marcarOcupado(ocupado) {
    const botones = [document.getElementById("boton-revisar"), document.getElementById("boton-revisar-vacio")].filter(Boolean);
    const teniaFoco = botones.includes(document.activeElement);
    botones.forEach((b) => { b.disabled = ocupado; if (ocupado) b.setAttribute("aria-busy", "true"); else b.removeAttribute("aria-busy"); b.classList.toggle("ocupado", ocupado); });
    document.getElementById("boton-revisar-texto").textContent =
        ocupado ? "Revisando…" : (escaneosReales > 0 ? "Volver a revisar" : "Revisar mi PC");
    document.getElementById("barra-progreso-contenedor").classList.toggle("activa", ocupado);
    // Al deshabilitarse el botón que tenía el foco, este se pierde: se devuelve al botón de la barra.
    if (!ocupado && (teniaFoco || document.activeElement === document.body)) botones[0].focus({ preventScroll: true });
}

async function escanearSistema() {
    if (escaneando) return;
    escaneando = true;
    marcarOcupado(true);
    try {
        const guias = cargarGuias(); // en paralelo al escaneo: el sello en palabras necesita _veredictos (nunca lanza)
        const respuesta = await fetch("/api/scan");
        if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
        const resultado = await respuesta.json();
        await guias;
        ocultarDemo(); // un escaneo real siempre reemplaza al modo demo
        escaneosReales++;
        renderizarDiagnostico(resultado);
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
        marcarOcupado(false);
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
    renderizarDiagnostico(DATOS_MOCK);
    componenteSeleccionado = null;
    document.getElementById("detalle-panel").replaceChildren(
        crear("p", "detalle-vacio", "Selecciona un componente del mapa o la lista para ver el detalle completo."));
}

document.getElementById("boton-revisar").addEventListener("click", escanearSistema);
document.getElementById("boton-demo").addEventListener("click", verModoDemo);

// Íconos de la interfaz: cada [data-icono="tipo:nombre"] recibe su SVG (cadenas constantes de iconos.js).
const ICONO_POR_TIPO = { ui: iconoUi, comp: iconoComponente, estado: iconoEstado };
document.querySelectorAll("[data-icono]").forEach((el) => {
    const [tipo, nombre] = el.dataset.icono.split(":");
    if (Object.hasOwn(ICONO_POR_TIPO, tipo)) el.append(crearIcono(ICONO_POR_TIPO[tipo](nombre)));
});

// --- Pestañas: roving tabindex, hash de la URL y teclado (lógica pura en modelo.js) ---
let pestanaActual = "resumen";

function pestanasHabilitadas() {
    return habilitadasSegun(!document.body.classList.contains("sin-escaneo"), ANALISIS_DISPONIBLE);
}

// Estado de las pestañas según haya o no escaneo (sin escaneo solo Resumen es accionable).
function actualizarPestanas() {
    const habilitadas = pestanasHabilitadas();
    PESTANAS.forEach((id) => {
        const tab = document.getElementById(`tab-${id}`);
        tab.hidden = id === "analisis" && !ANALISIS_DISPONIBLE;
        if (habilitadas.includes(id)) tab.removeAttribute("aria-disabled");
        else tab.setAttribute("aria-disabled", "true");
    });
    if (!habilitadas.includes(pestanaActual)) activarPestana("resumen", false);
}

// historial=true (clic o teclado del usuario): pushState; si no (arranque, hash externo): replaceState.
function activarPestana(id, historial) {
    id = pestanaDesdeHash(`#${id}`, pestanasHabilitadas());
    pestanaActual = id;
    PESTANAS.forEach((p) => {
        const seleccionada = p === id;
        const tab = document.getElementById(`tab-${p}`);
        tab.setAttribute("aria-selected", String(seleccionada));
        tab.tabIndex = seleccionada ? 0 : -1;
        document.getElementById(`panel-${p}`).hidden = !seleccionada;
    });
    if (location.hash !== `#${id}`) {
        try { (historial ? history.pushState : history.replaceState).call(history, null, "", `#${id}`); } catch (e) { /* sin historial: solo no queda el hash */ }
    }
}

const idDeTab = (tab) => tab.id.replace("tab-", "");
const listaPestanas = document.querySelector('[role="tablist"]');
listaPestanas.addEventListener("click", (evento) => {
    const tab = evento.target.closest('[role="tab"]');
    if (!tab || tab.getAttribute("aria-disabled") === "true") return;
    activarPestana(idDeTab(tab), true);
});
listaPestanas.addEventListener("keydown", (evento) => {
    const tab = evento.target.closest('[role="tab"]');
    if (!tab) return;
    const destino = siguientePestana(idDeTab(tab), evento.key, pestanasHabilitadas());
    if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(evento.key)) return;
    evento.preventDefault();
    activarPestana(destino, true);
    document.getElementById(`tab-${destino}`).focus();
});
const desdeHash = () => activarPestana(pestanaDesdeHash(location.hash, pestanasHabilitadas()), false);
window.addEventListener("hashchange", desdeHash);
window.addEventListener("popstate", desdeHash);

// --- Menú "Más": clic, Enter/Espacio, flechas, Escape (devuelve el foco), Tab y clic fuera ---
const botonMas = document.getElementById("boton-mas");
const menuMas = document.getElementById("menu-mas");
// Los ítems ocultos por CSS (informe sin escaneo real o en demo) no cuentan.
const itemsMenu = () => [...menuMas.querySelectorAll('[role="menuitem"]')].filter((el) => el.offsetParent !== null);

function abrirMenu(posicion) {
    menuMas.hidden = false;
    botonMas.setAttribute("aria-expanded", "true");
    const items = itemsMenu();
    (posicion === "ultimo" ? items[items.length - 1] : items[0]).focus();
}

function cerrarMenu(devolverFoco) {
    menuMas.hidden = true;
    botonMas.setAttribute("aria-expanded", "false");
    if (devolverFoco) botonMas.focus();
}

botonMas.addEventListener("click", () => (menuMas.hidden ? abrirMenu("primero") : cerrarMenu(true)));
botonMas.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && !menuMas.hidden) { evento.preventDefault(); cerrarMenu(true); return; }
    if (evento.key !== "ArrowDown" && evento.key !== "ArrowUp") return;
    evento.preventDefault();
    abrirMenu(evento.key === "ArrowUp" ? "ultimo" : "primero");
});
menuMas.addEventListener("keydown", (evento) => {
    const items = itemsMenu();
    const i = items.indexOf(document.activeElement);
    const mover = { ArrowDown: (i + 1) % items.length, ArrowUp: (i - 1 + items.length) % items.length, Home: 0, End: items.length - 1 };
    if (Object.hasOwn(mover, evento.key)) { evento.preventDefault(); items[mover[evento.key]].focus(); }
    else if (evento.key === "Escape") { evento.preventDefault(); cerrarMenu(true); }
    else if (evento.key === "Tab") { botonMas.focus(); cerrarMenu(false); } // el Tab sigue desde el botón
    else if (evento.key === " " && evento.target.tagName === "A") { evento.preventDefault(); evento.target.click(); }
});
menuMas.addEventListener("click", () => cerrarMenu(true)); // elegir un ítem cierra el menú
document.addEventListener("click", (evento) => {
    if (!menuMas.hidden && !evento.target.closest(".mas")) cerrarMenu(false);
});

// Sin menú contextual: el dashboard corre en un kiosk sin teclado/mouse
// de uso general, y el clic derecho de Chromium expone "Inspeccionar"
// entre otras cosas que no queremos a mano en ese contexto.
document.addEventListener("contextmenu", (evento) => evento.preventDefault());

document.getElementById("modo-simple-btn").addEventListener("click", () => aplicarModo("simple", true));
document.getElementById("modo-tecnico-btn").addEventListener("click", () => aplicarModo("tecnico", true));

const botonTema = document.getElementById("boton-tema");
if (botonTema) botonTema.addEventListener("click", () =>
    aplicarTema(document.documentElement.getAttribute("data-theme") === "dark" ? "claro" : "oscuro", true));
let temaGuardado = null;
try { temaGuardado = localStorage.getItem("tema_interfaz"); } catch (e) { /* almacenamiento bloqueado: tema claro */ }
aplicarTema(temaGuardado, false);

let modoGuardado = null;
try { modoGuardado = localStorage.getItem("modo_interfaz"); } catch (e) { /* almacenamiento bloqueado: se usa el modo simple */ }
aplicarModo(modoGuardado, false);

// Arranque: sin datos hasta el primer escaneo (DATOS_MOCK solo sale con "Ver demostración").
desdeHash();

// Frases de veredicto para el sello; al llegar se repinta (si falla, queda el texto de siempre).
cargarGuias().then((t) => { if (t) repintar(); });
actualizarStatus();
setInterval(actualizarStatus, 2000);
