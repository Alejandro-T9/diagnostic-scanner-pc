// frontend/static/js/vistas.js — Vistas: cada función dibuja el DOM de una pestaña a partir de datos ya calculados
// por modelo.js. Solo crear()/textContent/crearIcono/crearChipEstado: nada del escaneo entra como HTML.
// Depende de estado.js, iconos.js, dom.js y modelo.js (cargados antes); al hacer clic usa activarPestana,
// seleccionarComponente y escanearSistema de app.js, que se resuelven en ese momento (app.js se carga después).

// Estado vacío (sin escaneo todavía), el mismo en Resumen y en Componentes. El botón es el mismo "Revisar mi PC"
// de la barra; marcarOcupado lo gestiona por su clase.
function _resumenVacio() {
    const vacio = crear("div", "simple-vacio");
    const boton = crear("button", "boton-primario boton-grande boton-revisar-vacio", "Revisar mi PC");
    boton.type = "button";
    boton.addEventListener("click", () => escanearSistema());
    vacio.append(
        crear("p", "simple-vacio-titulo", "Todavía no hemos revisado tu PC."),
        boton,
        crear("p", "simple-vacio-nota", "Suele tardar alrededor de un minuto. Solo lee información: no borra ni cambia tus archivos ni tu configuración."),
    );
    return vacio;
}

// Tarjeta principal: icono grande del estado, titular en palabras, línea de resumen, cobertura y el informe.
function _resumenHero(resultado) {
    const veredicto = calcularVeredicto(resultado.componentes);
    const estado = veredicto.toLowerCase();
    const frase = tablaGuias && tablaGuias._veredictos && tablaGuias._veredictos[veredicto];

    const icono = crear("span", "hero-icono");
    icono.append(crearIcono(iconoEstado(estado)));
    const texto = crear("div", "hero-texto");
    texto.append(crear("h2", "hero-titular", typeof frase === "string" && frase ? frase : CHIP_TEXTO[estado]));
    const linea = lineaResumen(resultado.componentes);
    if (linea) texto.append(crear("p", "hero-linea", linea));
    const cob = resultado.cobertura;
    if (cob && [cob.porcentaje, cob.completos, cob.parciales].every(Number.isFinite)) {
        texto.append(crear("p", "hero-cobertura", `Cobertura: ${cob.porcentaje} % (${cob.completos} de ${cob.completos + cob.parciales} evaluados por completo)`));
    }
    const informe = crear("a", "boton-secundario hero-informe", "Abrir informe para el técnico");
    informe.href = "/api/informe";
    informe.target = "_blank";
    informe.rel = "noopener";

    const hero = crear("div", `resumen-hero estado--${estado}`);
    hero.append(icono, texto, informe);
    return hero;
}

function _resumenEquipo(resultado) {
    const filas = datosEquipo(resultado);
    if (!filas.length) return null;
    const lista = crear("dl", "datos-equipo");
    filas.forEach(({ etiqueta, valor }) => {
        const fila = crear("div");
        fila.append(crear("dt", "", etiqueta), crear("dd", "", valor));
        lista.append(fila);
    });
    const bloque = crear("section", "resumen-bloque");
    bloque.append(crear("h2", "", "Tu equipo"), lista);
    return bloque;
}

// Va a la pestaña del destino ("componentes:<id>" o "recomendaciones") y deja el foco en el componente elegido (seleccionarComponente) o, si no hay, en el panel.
function _irA(destino, componentes) {
    const [pestana, id] = destino.split(/:(.*)/s);
    window.scrollTo(0, 0); // antes de cambiar: la tarjeta o fila elegida se desplaza a la vista después
    if (seleccionValida(id, componentes)) { seleccionarComponente(id); return; } // activa Componentes, resalta y enfoca ese componente
    activarPestana(pestana, true);
    const panel = document.getElementById(`panel-${pestana}`);
    if (panel && !panel.hidden) panel.focus({ preventScroll: true });
}

function _resumenLoPrimero(resultado) {
    const bloque = crear("section", "resumen-bloque");
    bloque.append(crear("h2", "", "Lo primero que conviene hacer"));
    const pasos = loPrimero(resultado);
    if (!pasos.length) {
        const nada = crear("p", "lo-primero-nada");
        nada.append(crearIcono(iconoEstado("normal")), "Por ahora no hay nada urgente.");
        bloque.append(nada);
        return bloque;
    }
    const lista = crear("ol", "lo-primero");
    lista.setAttribute("role", "list"); // el número lo dibuja el CSS: sin esto algunos lectores pierden la lista
    pasos.forEach((paso) => {
        const [pestana, id] = paso.destino.split(/:(.*)/s);
        const texto = crear("div", "paso-texto");
        texto.append(crear("span", `etiqueta-urgencia ${paso.urgencia}`, `Urgencia: ${paso.urgencia}`), crear("span", "", paso.texto));
        const ir = crear("button", "boton-enlace", pestana === "componentes" ? `Ver ${nombreComp(id)}` : "Ver recomendaciones");
        ir.type = "button";
        ir.addEventListener("click", () => _irA(paso.destino, resultado.componentes));
        const item = crear("li", "paso");
        item.append(texto, ir);
        lista.append(item);
    });
    bloque.append(lista);
    return bloque;
}

// Siete fichas en el orden de siempre (la cuadrícula no se mueve entre escaneos); un id desconocido va al final.
function _resumenFichas(componentes) {
    const ids = [...Object.keys(NOMBRES_COMPONENTES).filter((id) => Object.hasOwn(componentes, id)),
        ...Object.keys(componentes).filter((id) => !Object.hasOwn(NOMBRES_COMPONENTES, id))];
    const cuadricula = crear("div", "fichas");
    ids.forEach((id) => {
        const info = componentes[id];
        const estado = normalizarEstado(info && info.estado);
        const ficha = crear("button", `ficha estado--${estado}`);
        ficha.type = "button";
        const cabecera = crear("span", "ficha-cabecera");
        const icono = crear("span", "ficha-icono");
        icono.append(crearIcono(iconoComponente(id)));
        cabecera.append(icono, crear("span", "ficha-nombre", nombreComp(id)));
        ficha.append(cabecera, crearChipEstado(estado), crear("span", "ficha-medida", medidaClave(id, info)));
        ficha.addEventListener("click", () => _irA(`componentes:${id}`, componentes));
        cuadricula.append(ficha);
    });
    const bloque = crear("section", "resumen-fichas");
    bloque.append(crear("h2", "", "Cada parte de tu PC"), cuadricula);
    return bloque;
}

// resultado = {componentes, hechos?, recomendaciones?, cobertura?} de un escaneo; null/sin componentes = estado vacío.
function dibujarResumen(resultado, contenedor) {
    const comps = resultado && resultado.componentes;
    // Sin componentes no hay nada que afirmar ("Tu PC está bien" sería inventado): se muestra el estado vacío.
    if (!comps || typeof comps !== "object" || Array.isArray(comps) || !Object.keys(comps).length) {
        contenedor.replaceChildren(_resumenVacio());
        return;
    }
    const raiz = crear("div", "resumen");
    const columnas = crear("div", "resumen-columnas");
    columnas.append(...[_resumenEquipo(resultado), _resumenLoPrimero(resultado)].filter(Boolean));
    raiz.append(_resumenHero(resultado), columnas, _resumenFichas(comps));
    contenedor.replaceChildren(raiz);
}

// --- Componentes: tarjetas con guía (modo simple) o tabla técnica con filas expandibles (modo técnico) ---

const _esDict = (v) => v !== null && typeof v === "object" && !Array.isArray(v);

function _etiquetaCampo(clave) {
    if (Object.hasOwn(ETIQUETAS_CAMPOS, clave)) return ETIQUETAS_CAMPOS[clave];
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
                if (!_esDict(item)) { grupo.append(_filaDato(clave, item)); return; } // elemento suelto (no objeto): una fila, sin romper el dibujo
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

function pasosGuia(guia) {
    return Array.isArray(guia.que_hacer) ? guia.que_hacer : [];
}

// Guía en el detalle técnico. Sin guía no se dibuja nada.
function bloqueGuia(guia) {
    if (!_esDict(guia)) return null;
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

// Modo simple: una tarjeta por componente con icono, estado, mensaje y la guía (qué significa, qué hacer, quién, urgencia).
function _tarjetaComponente(id, info, nombre = nombreComp(id)) {
    const estado = normalizarEstado(info.estado);
    const icono = crear("span", "tarjeta-comp-icono");
    icono.append(crearIcono(iconoComponente(id)));
    const cabecera = crear("header", "tarjeta-comp-cabecera");
    cabecera.append(icono, crear("h3", "", nombre), crearChipEstado(estado));
    const tarjeta = crear("article", `tarjeta-comp estado--${estado}`);
    tarjeta.tabIndex = -1; // enfocable por programa: al llegar desde el Resumen el foco cae en la tarjeta elegida
    tarjeta.append(cabecera, crear("p", "tarjeta-comp-mensaje", info.mensaje));
    const guia = _esDict(info.guia) ? info.guia : null;
    if (!guia) return tarjeta;
    if (guia.que_significa) tarjeta.append(crear("p", "tarjeta-comp-significa", guia.que_significa));
    const pasos = pasosGuia(guia);
    if (pasos.length) {
        const lista = crear("ol", "tarjeta-simple-pasos");
        pasos.forEach((p) => lista.append(crear("li", "", p)));
        tarjeta.append(crear("h4", "tarjeta-comp-subtitulo", estado === "normal" ? "Para mantenerlo bien" : "Qué hacer"), lista);
    }
    const etiquetas = crear("div", "tarjeta-simple-etiquetas");
    if (Object.hasOwn(QUIEN_TEXTO, guia.quien)) etiquetas.append(crear("span", `etiqueta-quien ${guia.quien}`, QUIEN_TEXTO[guia.quien]));
    if (["baja", "media", "alta"].includes(guia.urgencia)) etiquetas.append(crear("span", `etiqueta-urgencia ${guia.urgencia}`, `Urgencia: ${guia.urgencia}`));
    if (etiquetas.childNodes.length) tarjeta.append(etiquetas);
    return tarjeta;
}

// Modo técnico: lo que muestra la fila expandida (resumen + guía a un lado, datos del módulo al otro).
function _detalleTecnico(id, info) {
    const resumen = crear("div", "detalle-resumen");
    const cabecera = crear("div", "detalle-cabecera");
    cabecera.append(crear("h3", "", nombreComp(id)), crearChipEstado(info.estado));
    resumen.append(cabecera, crear("p", "detalle-mensaje", info.mensaje));
    if (info.recomendacion) {
        const recomendacion = crear("div", "detalle-recomendacion");
        recomendacion.append(crear("strong", "", "Recomendación:"), ` ${info.recomendacion}`);
        resumen.append(recomendacion);
    }
    const guia = bloqueGuia(info.guia);
    if (guia) resumen.append(guia);
    const datos = crear("div", "detalle-datos");
    if (_esDict(info.datos) && Object.keys(info.datos).length) datos.append(..._renderizarCuerpoDatos(info.datos));
    else datos.append(crear("p", "detalle-sin-datos", "Sin datos técnicos adicionales para este componente."));
    const cuerpo = crear("div", "detalle-cuerpo");
    cuerpo.append(resumen, datos);
    return cuerpo;
}

// Desplaza lo mínimo para que el elemento se vea (sin animación si se pidió movimiento reducido).
function _aVista(elemento) {
    const reducido = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    elemento.scrollIntoView({ block: "nearest", behavior: reducido ? "auto" : "smooth" });
}

// Abre o cierra una fila de la tabla técnica (aria-expanded + el detalle que controla).
function _alternarFila(fila, abrir) {
    fila.classList.toggle("abierta", abrir);
    fila.querySelector("button").setAttribute("aria-expanded", String(abrir));
    fila.nextElementSibling.hidden = !abrir;
}

// Devuelve [fila, detalle]: dos <tr> hermanos (el detalle va oculto hasta abrir la fila).
function _filaComponente(id, info, n) {
    const estado = normalizarEstado(info.estado);
    const idDetalle = `detalle-comp-${n}`;
    const icono = crear("span", "fila-comp-icono");
    icono.append(crearIcono(iconoComponente(id)));
    const flecha = crear("span", "fila-comp-flecha");
    flecha.append(crearIcono(iconoUi("flecha")));
    const boton = crear("button", "fila-comp-boton");
    boton.type = "button";
    boton.setAttribute("aria-expanded", "false");
    boton.setAttribute("aria-controls", idDetalle);
    boton.append(flecha, icono, crear("span", "fila-comp-nombre", nombreComp(id)));
    const nombre = crear("th", "celda-nombre");
    nombre.scope = "row";
    nombre.setAttribute("role", "rowheader"); // los roles explícitos mantienen la semántica de tabla aunque el CSS apile las filas (display:block)
    nombre.append(boton);
    const celda = (rotulo, clase, ...contenido) => {
        const td = crear("td", clase);
        td.setAttribute("role", "cell");
        td.dataset.label = rotulo; // en ventana angosta el CSS lo muestra como rótulo de la fila apilada
        td.append(...contenido);
        return td;
    };
    const fila = crear("tr", `fila-comp estado--${estado}`);
    fila.dataset.id = id;
    fila.setAttribute("role", "row");
    fila.append(nombre, celda("Estado", "", crearChipEstado(estado)),
        celda("Medición clave", "dato-tecnico", medidaClave(id, info)),
        celda("Mensaje", "", typeof info.mensaje === "string" ? info.mensaje : ""));
    // El botón recibe Enter/Espacio y su clic sube hasta la fila: un solo manejador sirve a mouse y teclado.
    fila.addEventListener("click", () => {
        const abrir = !fila.classList.contains("abierta");
        _alternarFila(fila, abrir);
        if (abrir) _aVista(detalle); // el detalle queda debajo de la fila: que no se quede fuera de la pantalla
    });

    const detalle = crear("tr", `detalle-comp estado--${estado}`);
    detalle.id = idDetalle;
    detalle.hidden = true;
    detalle.setAttribute("role", "row");
    const celdaDetalle = crear("td");
    celdaDetalle.setAttribute("role", "cell");
    celdaDetalle.colSpan = 4;
    celdaDetalle.append(_detalleTecnico(id, info));
    detalle.append(celdaDetalle);
    return [fila, detalle];
}

function _tablaComponentes(ids, comps, abiertas) {
    const encabezado = crear("tr");
    encabezado.setAttribute("role", "row");
    ["Componente", "Estado", "Medición clave", "Mensaje"].forEach((t) => {
        const th = crear("th", "", t);
        th.scope = "col";
        th.setAttribute("role", "columnheader");
        encabezado.append(th);
    });
    const cabeza = crear("thead");
    cabeza.setAttribute("role", "rowgroup");
    cabeza.append(encabezado);
    const cuerpo = crear("tbody");
    cuerpo.setAttribute("role", "rowgroup");
    const filas = new Map();
    ids.forEach((id, n) => {
        const [fila, detalle] = _filaComponente(id, comps[id], n);
        cuerpo.append(fila, detalle);
        if (abiertas.has(id)) _alternarFila(fila, true);
        filas.set(id, fila);
    });
    const tabla = crear("table", "tabla-comp");
    tabla.setAttribute("role", "table");
    tabla.append(crear("caption", "sr-only", "Componentes del equipo: estado, medición clave y mensaje. Cada fila se puede abrir para ver el detalle técnico."), cabeza, cuerpo);
    const envoltura = crear("div", "tabla-comp-envoltura");
    envoltura.append(tabla);
    return { envoltura, filas };
}

// resultado = {componentes,...} de un escaneo (null/sin componentes = la invitación a revisar); modo = "simple" | "tecnico";
// seleccionado = id del componente a resaltar (tarjeta) o expandir (fila), o null.
function dibujarComponentes(resultado, modo, seleccionado, contenedor) {
    const comps = resultado && resultado.componentes;
    if (!comps || typeof comps !== "object" || Array.isArray(comps) || !Object.keys(comps).length) {
        contenedor.replaceChildren(_resumenVacio());
        return;
    }
    const elegido = seleccionValida(seleccionado, comps);
    // Un redibujo con la misma selección (nuevo escaneo, cambio de modo) no cierra las filas que el usuario abrió a mano;
    // si la selección cambió, solo queda abierta la elegida.
    const mismaSeleccion = (contenedor.dataset.seleccion || "") === (elegido || "");
    const abiertas = new Set(mismaSeleccion ? [...contenedor.querySelectorAll(".fila-comp.abierta")].map((f) => f.dataset.id) : []);
    contenedor.dataset.seleccion = elegido || "";
    if (elegido) abiertas.add(elegido);
    const ids = ordenarPorGravedad(Object.keys(comps).filter((id) => _esDict(comps[id])), comps);

    const raiz = crear("div", "componentes");
    raiz.append(crear("h2", "", modo === "tecnico" ? "Detalle técnico de cada parte" : "Cada parte de tu PC, explicada"));
    let destino = null;
    if (modo === "tecnico") {
        const { envoltura, filas } = _tablaComponentes(ids, comps, abiertas);
        raiz.append(envoltura);
        destino = elegido && filas.get(elegido);
    } else {
        const lista = crear("div", "tarjetas-comp");
        ids.forEach((id) => {
            const tarjeta = _tarjetaComponente(id, comps[id]);
            if (id === elegido) { tarjeta.setAttribute("aria-current", "true"); destino = tarjeta; }
            lista.append(tarjeta);
        });
        raiz.append(lista);
    }
    contenedor.replaceChildren(raiz);
    if (destino) _aVista(destino); // sin efecto si la pestaña no se ve (panel oculto)
}

// --- Recomendaciones del equipo (F3): solo de escaneos reales que las traigan ---

// Pestaña sin escaneo real (estado vacío o demostración): nunca recomendaciones inventadas, solo la invitación a revisar.
function dibujarInvitacionRecomendaciones(contenedor) {
    const vacio = crear("div", "simple-vacio");
    const boton = crear("button", "boton-primario boton-grande boton-revisar-vacio", "Revisar mi PC");
    boton.type = "button";
    boton.addEventListener("click", () => escanearSistema());
    vacio.append(
        crear("p", "simple-vacio-titulo", "Todavía no hay recomendaciones para mostrar."),
        boton,
        crear("p", "simple-vacio-nota", "Aparecen después de una revisión real de este equipo."),
    );
    contenedor.replaceChildren(vacio);
}

// recomendaciones = lista de un escaneo REAL (puede venir vacía o null: "Por ahora no hay recomendaciones").
function dibujarRecomendaciones(recomendaciones, contenedor) {
    const lista = Array.isArray(recomendaciones) ? recomendaciones.filter((r) => r && typeof r === "object") : [];
    const bloque = crear("div", "recomendaciones");
    bloque.append(crear("h2", "", "Recomendaciones para tu equipo"));
    if (!lista.length) {
        bloque.append(crear("p", "recomendaciones-nota", "Por ahora no hay recomendaciones para este equipo."));
        contenedor.replaceChildren(bloque);
        return;
    }
    bloque.append(crear("p", "recomendaciones-nota", "Son sugerencias basadas en lo que se pudo medir en este equipo."));
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
    contenedor.replaceChildren(bloque);
}

// Pestaña "Análisis de Windows". vista: "vacio" | "demo" (invitan a revisar; nada se inventa) | "cta" | "resultado".
function dibujarAnalisis(vista, analisis, contenedor, { alAnalizar, ocupado } = {}) {
    const bloque = crear("div", "analisis");
    bloque.append(crear("h2", "", "Análisis de Windows"));
    bloque.append(crear("p", "recomendaciones-nota", "Es una foto del momento, solo lee información y no cambia nada en tu equipo."));
    if (vista === "vacio" || vista === "demo") {
        bloque.append(crear("p", "", vista === "demo"
            ? "Estás viendo una demostración. Pulsa «Volver a revisar» para revisar tu PC de verdad y luego analiza Windows."
            : "Primero revisa tu PC con el botón «Revisar mi PC»."));
    } else {
        const boton = crear("button", "boton-primario", ocupado ? "Analizando…" : (analisis ? "Volver a analizar" : "Analizar mi Windows"));
        boton.type = "button";
        boton.id = "boton-analizar";
        boton.disabled = !!ocupado;
        boton.setAttribute("aria-busy", String(!!ocupado));
        if (alAnalizar) boton.addEventListener("click", alAnalizar);
        bloque.append(boton);
    }
    if (vista === "resultado" && analisis) {
        const items = analisis.analisis;
        const lista = crear("div", "analisis-tarjetas");
        Object.keys(NOMBRES_ANALISIS).filter((id) => _esDict(items[id])).forEach((id) => {
            const info = { ...items[id], estado: normalizarEstado(items[id].estado) };
            const tarjeta = _tarjetaComponente(id, info, NOMBRES_ANALISIS[id]);
            detalleAnalisis(id, info).forEach((g) => {
                tarjeta.append(crear("h4", "tarjeta-comp-subtitulo", g.titulo));
                const ul = crear("ul", "tarjeta-simple-pasos");
                g.items.forEach((t) => ul.append(crear("li", "", t)));
                if (g.mas) ul.append(crear("li", "", `y ${g.mas} más`));
                tarjeta.append(ul);
            });
            lista.append(tarjeta);
        });
        bloque.append(lista);
    }
    contenedor.replaceChildren(bloque);
}


// Pestaña "Equipos" (F5, opt-in): formulario para guardar el último escaneo + inventario. datos = {equipos, archivo} o null.
function dibujarEquipos(datos, puedeGuardar, contenedor, { alGuardar, alBorrar, alNota, mensaje, hayPost } = {}) {
    const bloque = crear("div", "analisis");
    bloque.append(crear("h2", "", "Equipos revisados"));
    bloque.append(crear("p", "recomendaciones-nota", "Es opcional: solo se guarda lo que tú pides, en un archivo de tu USB. No se envía nada por internet."));
    if (puedeGuardar) {
        const form = crear("form", "form-registro");
        [["etiqueta", "Nombre o etiqueta del equipo (obligatorio)", "input"], ["responsable", "Responsable o dueño", "input"], ["notas", "Notas", "textarea"]].forEach(([id, texto, tipo]) => {
            const campo = crear("label", "campo-registro", texto);
            const entrada = crear(tipo);
            entrada.name = id;
            entrada.maxLength = id === "notas" ? 1000 : 80;
            if (id === "etiqueta") entrada.required = true;
            campo.append(entrada);
            form.append(campo);
            if (id === "notas") {
                const auto = crear("button", "boton-mas", "Generar nota automática");
                auto.type = "button";
                auto.addEventListener("click", () => alNota && alNota(entrada, true));
                form.append(auto);
                if (alNota) alNota(entrada, false); // al abrir, rellena solo si está vacío
            }
        });
        if (hayPost) {
            const incluir = crear("label", "campo-registro-marca");
            const marca = crear("input");
            marca.type = "checkbox";
            marca.name = "incluir_post";
            marca.checked = true;
            incluir.append(marca, " Incluir la revisión de post-instalación (con las tareas marcadas)");
            form.append(incluir);
        }
        const guardar = crear("button", "boton-primario", "Guardar este equipo");
        guardar.type = "submit";
        form.append(guardar);
        form.addEventListener("submit", (e) => { e.preventDefault(); if (alGuardar) alGuardar(Object.fromEntries(new FormData(form))); });
        bloque.append(form);
    } else {
        bloque.append(crear("p", "", "Para guardar un equipo, primero revisa tu PC de verdad con «Revisar mi PC»."));
    }
    if (mensaje) bloque.append(crear("p", "recomendaciones-nota", mensaje));
    const equipos = datos && Array.isArray(datos.equipos) ? datos.equipos.filter(_esDict) : null;
    if (!equipos) bloque.append(crear("p", "", "Cargando el registro…"));
    else if (!equipos.length) bloque.append(crear("p", "", "Aún no hay equipos guardados."));
    else {
        const acciones = crear("p", "recomendaciones-nota");
        const csv = crear("a", "", "Exportar a Excel (CSV)");
        csv.href = "/api/registro/csv";
        acciones.append(`${equipos.length} equipo(s) guardados. `, csv);
        bloque.append(acciones);
        const envoltura = crear("div", "tabla-comp-envoltura");
        const tabla = crear("table", "tabla-comp");
        const cab = crear("tr");
        ["Fecha", "Etiqueta", "Responsable", "Equipo", "Resultado", "Acciones"].forEach((t) => cab.append(crear("th", "", t)));
        const encabezado = crear("thead");
        encabezado.append(cab);
        tabla.append(encabezado);
        const cuerpo = crear("tbody");
        equipos.forEach((e) => {
            const fila = crear("tr");
            [String(e.fecha || "").replace("T", " "), e.etiqueta, e.responsable, [e.equipo, e.sistema].filter(Boolean).join(" · ")].forEach((t) => fila.append(crear("td", "", t || "—")));
            const resultado = crear("td");
            resultado.append(crearChipEstado(String(e.veredicto || "").toLowerCase()));
            fila.append(resultado);
            const celda = crear("td");
            const informe = crear("a", "", "Ver informe");
            informe.href = `/api/registro/${encodeURIComponent(e.id)}/informe`;
            informe.target = "_blank";
            informe.rel = "noopener";
            const borrar = crear("button", "boton-mas", "Borrar");
            borrar.type = "button";
            borrar.addEventListener("click", () => { if (alBorrar) alBorrar(e); });
            celda.append(informe, " ", borrar);
            fila.append(celda);
            cuerpo.append(fila);
        });
        tabla.append(cuerpo);
        envoltura.append(tabla);
        bloque.append(envoltura);
    }
    contenedor.replaceChildren(bloque);
}

// Pestaña "Post-instalación" (F6): lista de revisión de un equipo recién instalado. datos = respuesta de /api/postinstalacion o null.
function dibujarPostinstalacion(datos, ocupado, contenedor, { alRevisar, marcadas, alMarcar } = {}) {
    const bloque = crear("div", "analisis");
    bloque.append(crear("h2", "", "Equipo recién instalado"));
    bloque.append(crear("p", "recomendaciones-nota", "Revisa lo básico después de instalar o formatear. Solo lee: no instala, no activa y no cambia nada."));
    const boton = crear("button", "boton-primario", ocupado ? "Revisando…" : (datos ? "Volver a revisar" : "Revisar este equipo"));
    boton.type = "button";
    boton.id = "boton-postinstalacion";
    boton.disabled = !!ocupado;
    boton.setAttribute("aria-busy", String(!!ocupado));
    if (alRevisar) boton.addEventListener("click", alRevisar);
    bloque.append(boton);
    const items = datos && Array.isArray(datos.items) ? datos.items.filter((i) => _esDict(i) && typeof i.titulo === "string") : [];
    if (items.length) {
        const lista = crear("div", "analisis-tarjetas");
        items.forEach((i) => {
            const tarjeta = crear("article", "tarjeta-comp");
            const cab = crear("div", "tarjeta-comp-cabecera");
            if (i.manual) {
                const titulo = crear("h3");
                const etiqueta = crear("label");
                const marca = crear("input");
                marca.type = "checkbox";
                marca.checked = !!(marcadas && marcadas.has(i.id));
                marca.addEventListener("change", () => { if (alMarcar) alMarcar(i.id, marca.checked); });
                etiqueta.append(marca, ` ${i.titulo}`);
                titulo.append(etiqueta);
                cab.append(titulo);
            } else {
                cab.append(crear("h3", "", i.titulo), crearChipEstado(normalizarEstado(i.estado)));
            }
            tarjeta.append(cab);
            if (!i.manual && i.detalle) tarjeta.append(crear("p", "tarjeta-comp-mensaje", i.detalle));
            if (i.que_hacer) tarjeta.append(crear("p", "tarjeta-comp-significa", i.que_hacer));
            lista.append(tarjeta);
        });
        bloque.append(lista);
        if (typeof datos.acta === "string") {
            bloque.append(crear("h3", "", "Texto para la hoja de SOPORTE TÉCNICO"));
            const area = crear("textarea", "acta-texto");
            area.readOnly = true;
            area.rows = Math.min(16, datos.acta.split("\n").length + 1);
            area.value = datos.acta;
            area.setAttribute("aria-label", "Texto de la revisión para copiar");
            const copiar = crear("button", "boton-mas", "Copiar texto");
            copiar.type = "button";
            copiar.addEventListener("click", () => {
                area.select();
                try { navigator.clipboard.writeText(datos.acta); copiar.textContent = "Copiado"; } catch (e) { document.execCommand("copy"); }
            });
            bloque.append(area, copiar);
        }
    }
    contenedor.replaceChildren(bloque);
}


// Pestaña "Mantenimiento" (F7a). datos = respuesta de /api/mantenimiento o null. est = {previas, resultados, trabajos, seleccion, ocupado}:
// cada acción muestra primero qué haría y solo ejecuta tras confirmar. Todo texto del sistema entra con textContent.
function dibujarMantenimiento(datos, est, contenedor, { alPrevisualizar, alEjecutar, alMedir, alSeleccionar } = {}) {
    const bloque = crear("div", "analisis");
    bloque.append(crear("h2", "", "Mantenimiento seguro"));
    bloque.append(crear("p", "recomendaciones-nota", "Cada acción muestra primero qué haría y pide tu confirmación. Nunca apaga el antivirus, el firewall ni Windows Update."));
    if (!datos || !Array.isArray(datos.acciones)) {
        bloque.append(crear("p", "", "Cargando…"));
        contenedor.replaceChildren(bloque);
        return;
    }
    if (!datos.administrador) {
        bloque.append(crear("p", "aviso-mant", "Sin permisos de administrador solo funcionan la limpieza, los programas de inicio y el plan de energía. Para lo demás, cierra y abre de nuevo la aplicación aceptando el aviso de Windows."));
    }
    // Antes y ahora
    const m = datos.medidas;
    if (_esDict(m) && _esDict(m.antes) && _esDict(m.ahora)) {
        const caja = crear("div", "tarjeta-comp");
        caja.append(crear("h3", "", "Antes y ahora"));
        const filas = [["Espacio libre en el disco", (x) => (Number.isFinite(x.libre_gb) ? `${x.libre_gb} GB (${x.libre_pct} %)` : "—")],
                       ["Programas que arrancan solos", (x) => (Number.isFinite(x.inicio_activos) ? String(x.inicio_activos) : "—")]];
        const ul = crear("ul", "tarjeta-simple-pasos");
        filas.forEach(([t, f]) => ul.append(crear("li", "", `${t}: antes ${f(m.antes)}, ahora ${f(m.ahora)}`)));
        caja.append(ul);
        const medir = crear("button", "boton-mas", "Medir de nuevo");
        medir.type = "button";
        medir.addEventListener("click", () => alMedir && alMedir(false));
        const reiniciar = crear("button", "boton-mas", "Tomar lo de ahora como «antes»");
        reiniciar.type = "button";
        reiniciar.addEventListener("click", () => alMedir && alMedir(true));
        caja.append(medir, " ", reiniciar);
        bloque.append(caja);
    }
    const lista = crear("div", "analisis-tarjetas");
    datos.acciones.filter(_esDict).forEach((a) => {
        const id = String(a.id);
        const tarjeta = crear("article", "tarjeta-comp");
        const cab = crear("div", "tarjeta-comp-cabecera");
        cab.append(crear("h3", "", a.titulo), crear("span", `etiqueta-urgencia ${a.riesgo === "medio" ? "media" : "baja"}`, `Riesgo ${a.riesgo} · ${a.tarda}`));
        tarjeta.append(cab, crear("p", "tarjeta-comp-significa", a.descripcion));
        const ocupada = est.ocupado === id;
        if (!a.disponible) {
            tarjeta.append(crear("p", "", "Necesita permisos de administrador."));
            lista.append(tarjeta);
            return;
        }
        let kb = null;
        if (id === "quitar_parche") {
            const campo = crear("label", "campo-registro", "Número de la actualización (por ejemplo KB5120998)");
            kb = crear("input");
            kb.maxLength = 12;
            campo.append(kb);
            tarjeta.append(campo);
        }
        const params = () => (kb ? { kb: kb.value } : {});
        const previa = est.previas[id];
        const ver = crear("button", "boton-mas", ocupada ? "Trabajando…" : "Ver qué haría");
        ver.type = "button";
        ver.disabled = !!est.ocupado;
        ver.addEventListener("click", () => alPrevisualizar && alPrevisualizar(id, params()));
        tarjeta.append(ver);
        if (_esDict(previa)) {
            tarjeta.append(crear("p", "tarjeta-comp-mensaje", previa.mensaje));
            let ids = null;
            if (id === "inicio" && Array.isArray(previa.detalle)) {
                ids = est.seleccion[id] || (est.seleccion[id] = new Set());
                const ul = crear("ul", "lista-marcas");
                previa.detalle.filter(_esDict).forEach((e) => {
                    const li = crear("li");
                    const et = crear("label");
                    const marca = crear("input");
                    marca.type = "checkbox";
                    marca.checked = ids.has(e.id);
                    marca.addEventListener("change", () => { if (marca.checked) ids.add(e.id); else ids.delete(e.id); if (alSeleccionar) alSeleccionar(); });
                    et.append(marca, ` ${e.nombre}`);
                    li.append(et);
                    ul.append(li);
                });
                tarjeta.append(ul);
            } else if (id === "temporales" && Array.isArray(previa.detalle)) {
                const ul = crear("ul", "tarjeta-simple-pasos");
                previa.detalle.forEach((c) => ul.append(crear("li", "", String(c))));
                tarjeta.append(ul);
            }
            if (previa.estado === "ok") {
                const hacer = crear("button", "boton-primario", `Ejecutar: ${a.titulo}`);
                hacer.type = "button";
                hacer.disabled = !!est.ocupado || (ids !== null && ids.size === 0);
                hacer.addEventListener("click", () => {
                    if (!window.confirm(`${a.titulo}\n\n${a.descripcion}\n\n¿Continuar?`)) return;
                    if (alEjecutar) alEjecutar(id, ids ? { ids: [...ids] } : params());
                });
                tarjeta.append(hacer);
            }
        }
        const r = est.resultados[id];
        if (_esDict(r)) {
            tarjeta.append(crear("p", r.estado === "error" ? "aviso-mant" : "tarjeta-comp-mensaje", r.mensaje));
            const deshacer = crear("button", "boton-mas", "");
            deshacer.type = "button";
            if (id === "energia" && r.estado === "ok" && typeof r.anterior === "string") {
                deshacer.textContent = "Volver al plan anterior";
                deshacer.addEventListener("click", () => alEjecutar && alEjecutar("energia", { volver_a: r.anterior }));
                tarjeta.append(deshacer);
            } else if (id === "inicio" && _esDict(r.detalle) && Array.isArray(r.detalle.hechos) && r.detalle.hechos.length) {
                deshacer.textContent = "Volver a activarlos";
                deshacer.addEventListener("click", () => alEjecutar && alEjecutar("inicio", { ids: r.detalle.hechos, accion: "reactivar" }));
                tarjeta.append(deshacer);
            }
        }
        const t = est.trabajos[id];
        if (_esDict(t)) {
            const texto = { corriendo: "En curso… no cierres la aplicación.", terminado: "Terminó sin problemas.", con_avisos: "Terminó con avisos: muéstrale el resultado a un técnico.", error: "No se pudo ejecutar." }[t.estado] || "";
            tarjeta.append(crear("p", t.estado === "terminado" ? "tarjeta-comp-mensaje" : "aviso-mant", texto));
            if (Array.isArray(t.salida) && t.salida.length) tarjeta.append(crear("pre", "salida-mant", t.salida.slice(-12).join("\n")));
        }
        lista.append(tarjeta);
    });
    bloque.append(lista);
    const hist = Array.isArray(datos.historial) ? datos.historial.filter(_esDict) : [];
    if (hist.length) {
        bloque.append(crear("h3", "", "Lo que se hizo"));
        const ul = crear("ul", "tarjeta-simple-pasos");
        hist.slice(0, 15).forEach((h) => ul.append(crear("li", "", `${String(h.fecha || "").replace("T", " ")} — ${h.accion}: ${h.mensaje}`)));
        bloque.append(ul);
    }
    contenedor.replaceChildren(bloque);
}
