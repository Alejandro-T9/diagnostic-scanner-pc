// frontend/static/js/modelo.js — Lógica pura del armazón (pestañas, tema, modo). Sin DOM ni window:
// se prueba con Node (frontend/tests/modelo.test.js). Script clásico: las funciones quedan globales.

const PESTANAS = ["resumen", "componentes", "recomendaciones", "analisis"];

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
    if (!tieneEscaneo) return ["resumen"];
    return PESTANAS.filter((p) => p !== "analisis" || analisisDisponible);
}

if (typeof module !== "undefined") {
    module.exports = { PESTANAS, pestanaDesdeHash, siguientePestana, temaValido, modoValido, habilitadasSegun };
}
