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

// resultado = {componentes, hechos?, cobertura?, recomendaciones?}. Cada vista se dibuja en vistas.js.
function renderizarDiagnostico(resultado) {
    const { componentes, recomendaciones } = resultado;
    document.body.classList.remove("sin-escaneo");
    // Un estado desconocido (backend raro/viejo) se trata como "no_determinado":
    // así ninguna clase CSS ni texto sale de un valor no previsto.
    for (const info of Object.values(componentes)) info.estado = normalizarEstado(info.estado);
    // La selección sigue solo si el componente existe en este resultado.
    componenteSeleccionado = seleccionValida(componenteSeleccionado, componentes);
    ultimoResultado = resultado;
    dibujarResumen(resultado, document.getElementById("resumen-vista"));
    redibujarComponentes();
    renderizarRecomendaciones(recomendaciones);
    actualizarPestanas();
}

function redibujarComponentes() {
    dibujarComponentes(ultimoResultado, modo, componenteSeleccionado, document.getElementById("componentes-vista"));
}

// Clic en una ficha o en "Ver ..." del Resumen: abre Componentes con ese componente resaltado (tarjeta) o expandido (fila).
function seleccionarComponente(id) {
    componenteSeleccionado = id;
    activarPestana("componentes", true); // antes de dibujar: scrollIntoView necesita el panel visible
    redibujarComponentes();
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
    dibujarComponentes(null, modo, null, document.getElementById("componentes-vista"));
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
    try {
        const guias = cargarGuias(); // en paralelo al escaneo: el titular en palabras necesita _veredictos (nunca lanza)
        const respuesta = await fetch("/api/scan");
        if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
        const resultado = await respuesta.json();
        await guias;
        ocultarDemo(); // un escaneo real siempre reemplaza al modo demo
        escaneosReales++;
        renderizarDiagnostico(resultado); // conserva la selección si el componente sigue existiendo
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
    componenteSeleccionado = null; // la demo empieza sin selección
    renderizarDiagnostico(DATOS_MOCK);
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

// Frases de veredicto del Resumen; al llegar se repinta (si falla, queda el texto de siempre).
cargarGuias().then((t) => { if (t) repintar(); });
actualizarStatus();
setInterval(actualizarStatus, 2000);
