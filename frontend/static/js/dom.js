// frontend/static/js/dom.js — Utilidades de DOM compartidas. Depende de estado.js (CHIP_TEXTO)
// e iconos.js, que se cargan antes.

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

// Convierte una cadena SVG de iconos.js en un elemento <svg>. SOLO cadenas de iconos.js
// (constantes): es la única inserción de HTML permitida (ver test_frontend_sin_innerhtml_inseguro).
function crearIcono(svg) {
    const marco = crear("span");
    marco.insertAdjacentHTML("beforeend", svg);
    return marco.firstElementChild || marco;
}

// Chip de estado: ícono con silueta propia + texto. Estado desconocido -> no_determinado.
function crearChipEstado(estado) {
    const e = Object.hasOwn(CHIP_TEXTO, estado) ? estado : "no_determinado";
    const chip = crear("span", `chip-estado chip-estado--${e}`);
    chip.append(crearIcono(iconoEstado(e)), CHIP_TEXTO[e]);
    return chip;
}
