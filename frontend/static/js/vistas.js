// frontend/static/js/vistas.js — Vistas: cada función dibuja el DOM de una pestaña a partir de datos ya calculados
// por modelo.js. Solo crear()/textContent/crearIcono/crearChipEstado: nada del escaneo entra como HTML.
// Depende de estado.js, iconos.js, dom.js y modelo.js (cargados antes); al hacer clic usa activarPestana y
// abrirComponente de app.js, que se resuelven en ese momento (app.js se carga después).

// Estado vacío (sin escaneo todavía). El botón es el mismo "Revisar mi PC" de la barra; marcarOcupado lo gestiona por id.
function _resumenVacio() {
    const vacio = crear("div", "simple-vacio");
    const boton = crear("button", "boton-primario boton-grande", "Revisar mi PC");
    boton.type = "button";
    boton.id = "boton-revisar-vacio";
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

// Va a la pestaña del destino ("componentes:<id>" o "recomendaciones") y deja el foco dentro de ella.
function _irA(destino, componentes) {
    const [pestana, id] = destino.split(/:(.*)/s);
    if (id && componentes[id] && typeof componentes[id] === "object") abrirComponente(id, componentes[id]); // selecciona el detalle y activa Componentes
    else activarPestana(pestana, true);
    const panel = document.getElementById(`panel-${pestana}`);
    if (panel && !panel.hidden) panel.focus({ preventScroll: true });
    window.scrollTo(0, 0);
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
