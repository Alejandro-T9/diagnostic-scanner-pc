// frontend/static/js/app.js — Lógica del dashboard de Diagnostic Scanner PC.
// Sin dependencias externas. Responsabilidades: polling de /api/status cada
// 2s (timestamp, salud de conexión), disparo de /api/scan, la selección de componente
// (que dibuja vistas.js en Resumen y Componentes) y el armazón: pestañas (con hash en la
// URL), menú "Más" y botón único de revisión.

let componenteSeleccionado = null;
let ultimoResultado = null; // resultado del último render ({componentes, hechos, cobertura, recomendaciones}), para repintar al cambiar de modo
let tablaGuias = null;      // respuesta de /api/guias (guías por componente/estado + _veredictos)
let modo = "simple";
let escaneando = false;     // hay un /api/scan en curso
let escaneosReales = 0;     // cuenta resultados reales ya pintados (para abortar una demo que quedó atrás)
let ultimoAnalisis = null;  // resultado de /api/analisis (se conserva entre escaneos de hardware)
let analizando = false;
let errorVisible = null;    // "conexion" | "escaneo" | null: tipo del aviso de error visible (el sondeo solo borra el de conexión)

// resultado = {componentes, hechos?, cobertura?, recomendaciones?}. Cada vista se dibuja en vistas.js.
function renderizarDiagnostico(resultado) {
    // Una entrada que no es objeto (null, número...) se omite: ninguna vista la dibuja ni la cuenta.
    const componentes = Object.fromEntries(Object.entries(resultado.componentes).filter(([, info]) => info !== null && typeof info === "object" && !Array.isArray(info)));
    resultado = { ...resultado, componentes };
    const { recomendaciones } = resultado;
    document.body.classList.remove("sin-escaneo");
    // Un estado desconocido (backend raro/viejo) se trata como "no_determinado":
    // así ninguna clase CSS ni texto sale de un valor no previsto.
    for (const info of Object.values(componentes)) info.estado = normalizarEstado(info.estado);
    // La selección sigue solo si el componente existe en este resultado.
    componenteSeleccionado = seleccionValida(componenteSeleccionado, componentes);
    ultimoResultado = resultado;
    dibujarResumen(resultado, document.getElementById("resumen-vista"));
    redibujarComponentes();
    // Recomendaciones solo de un escaneo real: en la demostración la pestaña invita a revisar (nunca se inventan).
    const vistaRecs = document.getElementById("recomendaciones-vista");
    if (document.body.classList.contains("demo")) dibujarInvitacionRecomendaciones(vistaRecs);
    else dibujarRecomendaciones(recomendaciones, vistaRecs);
    dibujarPanelAnalisis();
    if (typeof dibujarPanelEquipos === "function") dibujarPanelEquipos(); // puede llamarse antes de que se defina (arranque)
    if (escaneando) marcarOcupado(true); // los botones de invitación acaban de recrearse
    actualizarPestanas();
}

function dibujarPanelAnalisis() {
    const contenedor = document.getElementById("analisis-vista");
    if (document.body.classList.contains("sin-escaneo")) dibujarAnalisis("vacio", null, contenedor);
    else if (document.body.classList.contains("demo")) dibujarAnalisis("demo", null, contenedor);
    else dibujarAnalisis(ultimoAnalisis ? "resultado" : "cta", ultimoAnalisis, contenedor, { alAnalizar: analizarWindows, ocupado: analizando });
}

async function analizarWindows() {
    if (analizando || escaneando) return;
    analizando = true;
    dibujarPanelAnalisis();
    ocultarError("escaneo");
    anunciar("Analizando Windows…");
    try {
        const respuesta = await fetch("/api/analisis");
        if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
        const resultado = await respuesta.json();
        if (!resultadoAnalisisValido(resultado)) throw new Error("respuesta sin análisis");
        ultimoAnalisis = resultado;
        anunciar("Análisis de Windows terminado.");
    } catch (error) {
        const mensaje = "No se pudo completar el análisis de Windows.";
        mostrarError(mensaje, "escaneo");
        anunciar(mensaje);
    } finally {
        analizando = false;
        dibujarPanelAnalisis();
        const boton = document.getElementById("boton-analizar");
        if (boton) boton.focus({ preventScroll: true });
    }
}

function redibujarComponentes() {
    dibujarComponentes(ultimoResultado, modo, componenteSeleccionado, document.getElementById("componentes-vista"));
}

// Clic en una ficha o en "Ver ..." del Resumen: abre Componentes con ese componente resaltado (tarjeta) o expandido (fila).
function seleccionarComponente(id) {
    componenteSeleccionado = id;
    activarPestana("componentes", true); // antes de dibujar: scrollIntoView necesita el panel visible
    redibujarComponentes();
    // El foco va al componente elegido (no al panel); preventScroll porque _aVista ya lo desplazó a la vista.
    const elegido = (modo === "tecnico"
        ? [...document.querySelectorAll(".fila-comp")].find((f) => f.dataset.id === id)?.querySelector(".fila-comp-boton")
        : document.querySelector('.tarjeta-comp[aria-current="true"]'));
    if (elegido) elegido.focus({ preventScroll: true });
}

// Estado inicial (y tras cambiar de modo sin escaneo): sin datos inventados.
function pintarVacio() {
    document.body.classList.add("sin-escaneo");
    dibujarInvitacionRecomendaciones(document.getElementById("recomendaciones-vista"));
    dibujarResumen(null, document.getElementById("resumen-vista"));
    dibujarComponentes(null, modo, null, document.getElementById("componentes-vista"));
    dibujarPanelAnalisis();
    if (escaneando) marcarOcupado(true); // los botones del estado vacío acaban de recrearse
    actualizarPestanas();
}

function repintar() {
    if (ultimoResultado) renderizarDiagnostico(ultimoResultado);
    else pintarVacio();
}

function aplicarModo(nuevo, guardar) {
    modo = modoValido(nuevo);
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

// Región role="status" para lectores de pantalla (#estado-escaneo): solo se escribe si el texto cambió.
function anunciar(texto) {
    const region = document.getElementById("estado-escaneo");
    if (region.textContent !== texto) region.textContent = texto;
}

// tipo: "conexion" (la sondea /api/status y se borra sola al volver) o "escaneo" (queda hasta el próximo escaneo).
// Es un role="alert": solo se toca el DOM si algo cambió, para que no se relea cada 2 s.
function mostrarError(mensaje, tipo) {
    const texto = document.getElementById("aviso-error-texto");
    if (texto.textContent !== mensaje) texto.textContent = mensaje;
    const aviso = document.getElementById("aviso-error");
    if (!aviso.classList.contains("activo")) aviso.classList.add("activo");
    errorVisible = tipo;
}

// Sin `tipo` borra cualquier error; con `tipo` solo si el visible es de ese tipo.
function ocultarError(tipo) {
    if (tipo && errorVisible !== tipo) return;
    document.getElementById("aviso-error").classList.remove("activo");
    errorVisible = null;
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
        ocultarError("conexion"); // un error de escaneo no lo borra el sondeo
    } catch (error) {
        mostrarError("No se pudo conectar con el backend. Verifica que el servidor esté corriendo.", "conexion");
    }
}

// Botón único de revisión (barra superior + el grande del estado vacío): ocupado mientras corre el escaneo.
function marcarOcupado(ocupado) {
    const botones = [document.getElementById("boton-revisar"), ...document.querySelectorAll(".boton-revisar-vacio")];
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
    ocultarError("escaneo");
    anunciar("Revisando tu PC…");
    try {
        const guias = cargarGuias(); // en paralelo al escaneo: el titular en palabras necesita _veredictos (nunca lanza)
        const respuesta = await fetch("/api/scan");
        if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
        const resultado = await respuesta.json();
        await guias;
        if (!resultadoValido(resultado)) throw new Error("respuesta sin componentes"); // antes de tocar la pantalla: nada queda a medias
        ocultarDemo(); // un escaneo real siempre reemplaza al modo demo
        escaneosReales++;
        renderizarDiagnostico(resultado); // conserva la selección si el componente sigue existiendo
        ocultarError();
        const veredicto = calcularVeredicto(resultado.componentes);
        const frase = tablaGuias && tablaGuias._veredictos && tablaGuias._veredictos[veredicto];
        const titular = typeof frase === "string" && frase ? frase : CHIP_TEXTO[veredicto.toLowerCase()];
        anunciar(`${titular}${/[.!?]$/.test(titular) ? "" : "."} ${lineaResumen(resultado.componentes)}`.trim());
    } catch (error) {
        const mensaje = "No se pudo completar el escaneo. Verifica que el servidor esté corriendo.";
        mostrarError(mensaje, "escaneo");
        anunciar(mensaje);
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
    componenteSeleccionado = null; // la demo empieza sin selección
    renderizarDiagnostico(DATOS_MOCK);
    anunciar("Mostrando una demostración con datos simulados.");
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

// --- Equipos (F5, registro opcional) y Post-instalación (F6) ---
let datosRegistro = null;      // respuesta de /api/registro
let mensajeRegistro = "";
let datosPostinstalacion = null;
let revisandoPost = false;
const marcadasPost = new Set(); // ids de las tareas a mano marcadas en esta sesión

function puedeGuardarEquipo() {
    return !document.body.classList.contains("sin-escaneo") && !document.body.classList.contains("demo");
}

function dibujarPanelEquipos() {
    dibujarEquipos(datosRegistro, puedeGuardarEquipo(), document.getElementById("equipos-vista"), {
        alGuardar: guardarEquipo, alBorrar: borrarEquipo, alNota: rellenarNota, mensaje: mensajeRegistro, hayPost: !!datosPostinstalacion,
    });
}

// Nota automática (hallazgos, pendientes de instalación y mantenimiento de hoy). Sin forzar, no pisa lo que el usuario ya escribió.
async function rellenarNota(campo, forzar) {
    if (!forzar && campo.value.trim()) return;
    try {
        const cuerpo = await _postJson("/api/registro/nota", { items: datosPostinstalacion ? datosPostinstalacion.items : [] });
        if (typeof cuerpo.nota === "string" && cuerpo.nota && (forzar || !campo.value.trim())) campo.value = cuerpo.nota;
    } catch (error) { /* sin nota automática: el usuario escribe la suya */ }
}

async function cargarRegistro() {
    try {
        const respuesta = await fetch("/api/registro");
        if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
        datosRegistro = await respuesta.json();
    } catch (error) {
        datosRegistro = { equipos: [] };
        mensajeRegistro = "No se pudo leer el registro de equipos.";
    }
    dibujarPanelEquipos();
}

async function guardarEquipo(campos) {
    const { incluir_post: incluirPost, ...datos } = campos;
    if (incluirPost && datosPostinstalacion) datos.postinstalacion = { acta: datosPostinstalacion.acta, marcadas: [...marcadasPost] };
    try {
        const respuesta = await fetch("/api/registro", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos) });
        const cuerpo = await respuesta.json().catch(() => ({}));
        mensajeRegistro = respuesta.ok ? "Equipo guardado en el registro." : (cuerpo.mensaje || "No se pudo guardar el equipo.");
    } catch (error) {
        mensajeRegistro = "No se pudo guardar el equipo.";
    }
    anunciar(mensajeRegistro);
    await cargarRegistro();
}

async function borrarEquipo(equipo) {
    if (!window.confirm(`¿Borrar «${equipo.etiqueta}» del registro? No se puede deshacer.`)) return;
    try {
        const respuesta = await fetch(`/api/registro/${encodeURIComponent(equipo.id)}`, { method: "DELETE" });
        mensajeRegistro = respuesta.ok ? "Equipo borrado del registro." : "No se pudo borrar el equipo.";
    } catch (error) {
        mensajeRegistro = "No se pudo borrar el equipo.";
    }
    anunciar(mensajeRegistro);
    await cargarRegistro();
}

function dibujarPanelPostinstalacion() {
    dibujarPostinstalacion(datosPostinstalacion, revisandoPost, document.getElementById("postinstalacion-vista"), {
        alRevisar: revisarPostinstalacion, marcadas: marcadasPost,
        alMarcar: (id, marcada) => { if (marcada) marcadasPost.add(id); else marcadasPost.delete(id); },
    });
}

async function revisarPostinstalacion() {
    if (revisandoPost) return;
    revisandoPost = true;
    dibujarPanelPostinstalacion();
    anunciar("Revisando el equipo…");
    try {
        const respuesta = await fetch("/api/postinstalacion");
        if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
        datosPostinstalacion = await respuesta.json();
        marcadasPost.clear();
        dibujarPanelEquipos();
        anunciar("Revisión terminada.");
    } catch (error) {
        mostrarError("No se pudo completar la revisión del equipo.", "escaneo");
    } finally {
        revisandoPost = false;
        dibujarPanelPostinstalacion();
        const boton = document.getElementById("boton-postinstalacion");
        if (boton) boton.focus({ preventScroll: true });
    }
}

dibujarPanelPostinstalacion();
cargarRegistro();


// --- Mantenimiento seguro (F7a) ---
const mant = { datos: null, previas: {}, resultados: {}, trabajos: {}, seleccion: {}, ocupado: null };
let sondeoTrabajo = null;

const _postJson = (url, cuerpo) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo || {}) }).then((r) => r.json());

function dibujarPanelMantenimiento() {
    dibujarMantenimiento(mant.datos, mant, document.getElementById("mantenimiento-vista"), {
        alPrevisualizar: previsualizarMant, alEjecutar: ejecutarMant, alMedir: medirMant, alSeleccionar: dibujarPanelMantenimiento,
    });
}

async function cargarMantenimiento(reiniciar) {
    try {
        const respuesta = await fetch(`/api/mantenimiento${reiniciar ? "?reiniciar=1" : ""}`);
        if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
        mant.datos = await respuesta.json();
    } catch (error) {
        mostrarError("No se pudo leer el mantenimiento.", "escaneo");
    }
    dibujarPanelMantenimiento();
}

const medirMant = (reiniciar) => cargarMantenimiento(reiniciar);

async function previsualizarMant(id, params) {
    mant.ocupado = id;
    dibujarPanelMantenimiento();
    try {
        mant.previas[id] = await _postJson(`/api/mantenimiento/${encodeURIComponent(id)}/previsualizar`, params);
        if (id === "inicio") mant.seleccion.inicio = new Set();
    } catch (error) {
        mant.previas[id] = { estado: "error", mensaje: "No se pudo preparar la vista previa.", detalle: [] };
    }
    mant.ocupado = null;
    dibujarPanelMantenimiento();
}

async function ejecutarMant(id, params) {
    mant.ocupado = id;
    delete mant.resultados[id];
    dibujarPanelMantenimiento();
    try {
        const r = await _postJson(`/api/mantenimiento/${encodeURIComponent(id)}/ejecutar`, params);
        mant.resultados[id] = r;
        anunciar(r.mensaje);
        if (r.estado === "trabajo") sondearTrabajo(id, r.trabajo);
    } catch (error) {
        mant.resultados[id] = { estado: "error", mensaje: "No se pudo ejecutar la acción.", detalle: [] };
    }
    mant.ocupado = null;
    await cargarMantenimiento(false); // refresca historial y medidas
}

function sondearTrabajo(id, tid) {
    clearInterval(sondeoTrabajo);
    sondeoTrabajo = setInterval(async () => {
        try {
            const respuesta = await fetch(`/api/mantenimiento/trabajo/${encodeURIComponent(tid)}`);
            if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
            mant.trabajos[id] = await respuesta.json();
        } catch (error) {
            mant.trabajos[id] = { estado: "error", salida: [] };
        }
        dibujarPanelMantenimiento();
        if (mant.trabajos[id].estado !== "corriendo") {
            clearInterval(sondeoTrabajo);
            anunciar("La tarea de mantenimiento terminó.");
            cargarMantenimiento(false);
        }
    }, 2000);
}

dibujarPanelMantenimiento();
cargarMantenimiento(false);


// --- Instaladores del USB (F7b) ---
const inst = { datos: null, resultados: {}, trabajos: {}, huellas: null, ocupado: null };
let sondeoInstalacion = null;

function dibujarPanelInstaladores() {
    dibujarInstaladores(inst.datos, inst, document.getElementById("instaladores-vista"), { alInstalar: instalarPrograma, alHuellas: calcularHuellas });
}

async function cargarInstaladores() {
    try {
        const respuesta = await fetch("/api/instaladores");
        if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
        inst.datos = await respuesta.json();
    } catch (error) {
        inst.datos = { carpeta: "", existe: false, administrador: false, entradas: [] };
    }
    dibujarPanelInstaladores();
}

async function calcularHuellas() {
    anunciar("Calculando huellas…");
    try {
        const respuesta = await fetch("/api/instaladores/huellas");
        inst.huellas = respuesta.ok ? (await respuesta.json()).huellas : [];
    } catch (error) {
        inst.huellas = [];
    }
    dibujarPanelInstaladores();
}

async function instalarPrograma(id) {
    inst.ocupado = id;
    delete inst.resultados[id];
    delete inst.trabajos[id];
    dibujarPanelInstaladores();
    try {
        const r = await _postJson(`/api/instaladores/${encodeURIComponent(id)}/instalar`, {});
        inst.resultados[id] = r;
        anunciar(r.mensaje);
        if (r.estado === "trabajo") {
            sondearInstalacion(id, r.trabajo);
            return;
        }
    } catch (error) {
        inst.resultados[id] = { estado: "error", mensaje: "No se pudo iniciar la instalación." };
    }
    inst.ocupado = null;
    dibujarPanelInstaladores();
}

function sondearInstalacion(id, tid) {
    clearInterval(sondeoInstalacion);
    sondeoInstalacion = setInterval(async () => {
        try {
            const respuesta = await fetch(`/api/mantenimiento/trabajo/${encodeURIComponent(tid)}`);
            if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
            inst.trabajos[id] = await respuesta.json();
        } catch (error) {
            inst.trabajos[id] = { estado: "error" };
        }
        if (inst.trabajos[id].estado !== "corriendo") {
            clearInterval(sondeoInstalacion);
            inst.ocupado = null;
            anunciar("La instalación terminó.");
            await cargarInstaladores(); // vuelve a leer qué quedó instalado
        } else {
            dibujarPanelInstaladores();
        }
    }, 2000);
}

dibujarPanelInstaladores();
cargarInstaladores();


// --- Respaldo antes de formatear (F7c) ---
const resp = { datos: null, ocupado: null, resultado: null, trabajo: null, seleccion: new Set(), unidad: null };
let sondeoRespaldo = null;

function dibujarPanelRespaldo() {
    dibujarRespaldo(resp.datos, resp, document.getElementById("respaldo-vista"), { alCalcular: calcularRespaldo, alCopiar: copiarRespaldo, alCambiar: dibujarPanelRespaldo });
}

async function calcularRespaldo() {
    resp.ocupado = "calculando";
    dibujarPanelRespaldo();
    try {
        const respuesta = await fetch("/api/respaldo");
        if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
        resp.datos = await respuesta.json();
        resp.seleccion = new Set(resp.datos.carpetas.filter((c) => c.id !== "descargas").map((c) => c.id)); // Descargas suele ser basura: no va marcada
    } catch (error) {
        resp.resultado = { estado: "error", mensaje: "No se pudo calcular el respaldo." };
    }
    resp.ocupado = null;
    dibujarPanelRespaldo();
}

async function copiarRespaldo(carpetas, unidad) {
    resp.ocupado = "copiando";
    resp.resultado = null;
    resp.trabajo = null;
    dibujarPanelRespaldo();
    try {
        const r = await _postJson("/api/respaldo/copiar", { carpetas, unidad });
        resp.resultado = r;
        anunciar(r.mensaje);
        if (r.estado === "trabajo") {
            sondearRespaldo(r.trabajo);
            return;
        }
    } catch (error) {
        resp.resultado = { estado: "error", mensaje: "No se pudo iniciar la copia." };
    }
    resp.ocupado = null;
    dibujarPanelRespaldo();
}

function sondearRespaldo(tid) {
    clearInterval(sondeoRespaldo);
    sondeoRespaldo = setInterval(async () => {
        try {
            const respuesta = await fetch(`/api/mantenimiento/trabajo/${encodeURIComponent(tid)}`);
            if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
            resp.trabajo = await respuesta.json();
        } catch (error) {
            resp.trabajo = { estado: "error", salida: [] };
        }
        if (resp.trabajo.estado !== "corriendo") {
            clearInterval(sondeoRespaldo);
            resp.ocupado = null;
            anunciar("El respaldo terminó.");
        }
        dibujarPanelRespaldo();
    }, 2000);
}

dibujarPanelRespaldo();

desdeHash();

// Frases de veredicto del Resumen; al llegar se repinta (si falla, queda el texto de siempre).
cargarGuias().then((t) => { if (t) repintar(); });
actualizarStatus();
setInterval(actualizarStatus, 2000);
