// frontend/static/js/iconos.js — Íconos propios en SVG en línea (un solo trazo de 1,75 px, currentColor).
// Devuelven cadenas CONSTANTES (nunca llevan datos del escaneo): dom.js las inserta con seguridad.
// Cada estado tiene una silueta distinta, para distinguirlos también sin color (spec 4.3).

const _SVG_ABRE = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    + 'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">';
const _svg = (cuerpo) => `${_SVG_ABRE}${cuerpo}</svg>`;
// Exclamación: raya + punto (un tramo de largo ~0 con extremo redondo).
const _EXCLAMACION = (arriba, abajo) => `<path d="M12 ${arriba}v4.2"/><path d="M12 ${abajo}h.01"/>`;

const _ICONOS_ESTADO = {
    // círculo + visto
    normal: _svg('<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.5"/>'),
    // triángulo + exclamación
    advertencia: _svg(`<path d="M12 3.5 21.5 20h-19z"/>${_EXCLAMACION(9.8, 16.8)}`),
    // rombo + exclamación
    sospecha: _svg(`<path d="M12 2.5 21.5 12 12 21.5 2.5 12z"/>${_EXCLAMACION(7.6, 16.4)}`),
    // octágono + cruz
    critico: _svg('<path d="M8.06 2.5h7.88L21.5 8.06v7.88l-5.56 5.56H8.06L2.5 15.94V8.06z"/><path d="M9 9l6 6M15 9l-6 6"/>'),
    // círculo discontinuo + interrogación
    no_determinado: _svg('<circle cx="12" cy="12" r="9" stroke-dasharray="3 3.2"/>'
        + '<path d="M9.6 9.6a2.5 2.5 0 1 1 3.6 2.2c-.7.4-1.2.9-1.2 1.8"/><path d="M12 16.9h.01"/>'),
};

const _ICONOS_COMPONENTE = {
    mainboard: _svg('<rect x="4" y="4" width="16" height="16" rx="1.5"/><rect x="9" y="9" width="6" height="6" rx=".5"/>'
        + '<path d="M4 9H1.5M4 15H1.5M20 9h2.5M20 15h2.5"/>'),
    cpu: _svg('<rect x="6" y="6" width="12" height="12" rx="1.5"/><rect x="9.5" y="9.5" width="5" height="5" rx=".5"/>'
        + '<path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>'),
    ram: _svg('<rect x="3" y="7" width="18" height="9" rx="1.5"/><path d="M7 7v9M11 7v9M15 7v9"/><path d="M5 16v2M9 16v2M13 16v2M17 16v2"/>'),
    almacenamiento: _svg('<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>'),
    fuente_poder: _svg('<path d="M13 2 4 14h6l-1 8 9-12h-6z"/>'),
    bateria: _svg('<rect x="3" y="7" width="16" height="10" rx="2"/><path d="M21.5 10.5v3"/><path d="M7 12h6"/>'),
    red: _svg('<path d="M2.5 9.5a14 14 0 0 1 19 0"/><path d="M5.5 13a9.5 9.5 0 0 1 13 0"/><path d="M8.7 16.3a5 5 0 0 1 6.6 0"/><path d="M12 19.5h.01"/>'),
};
// Genérico (id desconocido): una caja, para que no se confunda con ningún componente.
const _ICONO_GENERICO = _svg('<path d="M12 3 20 7.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5 12 12l8-4.5M12 12v9"/>');

const _ICONOS_UI = {
    "tema-claro": _svg('<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>'),
    "tema-oscuro": _svg('<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>'),
    menu: _svg('<circle cx="12" cy="5.5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="18.5" r="1"/>'),
    flecha: _svg('<path d="M9 5l7 7-7 7"/>'),
    informe: _svg('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>'),
    descargar: _svg('<path d="M12 4v10.5M7.5 10.5 12 15l4.5-4.5"/><path d="M4 16.5V20h16v-3.5"/>'),
    demo: _svg('<path d="M9.5 3h5M10 3v6L4.7 18.2A1.5 1.5 0 0 0 6 20.5h12a1.5 1.5 0 0 0 1.3-2.3L14 9V3"/><path d="M7.5 15h9"/>'),
    revisar: _svg('<path d="M20 12a8 8 0 0 1-13.9 5.4M4 12a8 8 0 0 1 13.9-5.4"/><path d="M18 3v4h-4M6 21v-4h4"/>'),
};

function iconoEstado(estado) {
    return _ICONOS_ESTADO[typeof estado === "string" && Object.hasOwn(_ICONOS_ESTADO, estado) ? estado : "no_determinado"];
}

function iconoComponente(id) {
    return Object.hasOwn(_ICONOS_COMPONENTE, id) ? _ICONOS_COMPONENTE[id] : _ICONO_GENERICO;
}

function iconoUi(nombre) {
    return Object.hasOwn(_ICONOS_UI, nombre) ? _ICONOS_UI[nombre] : "";
}

if (typeof module !== "undefined") module.exports = { iconoEstado, iconoComponente, iconoUi };
