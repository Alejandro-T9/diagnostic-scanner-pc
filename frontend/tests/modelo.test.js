// Pruebas de la lógica pura del frontend (se ejecutan con: node frontend/tests/modelo.test.js).
// Las llama también backend/test_scanner.py::test_frontend_node cuando hay node.
const assert = require("assert");
const { iconoEstado, iconoComponente, iconoUi } = require("../static/js/iconos.js");
const { CHIP_TEXTO } = require("../static/js/estado.js");
const { PESTANAS, pestanaDesdeHash, siguientePestana, temaValido, modoValido, habilitadasSegun,
    calcularVeredicto, normalizarEstado, lineaResumen, medidaClave, datosEquipo, loPrimero, ordenarPorGravedad } = require("../static/js/modelo.js");

const ESTADOS = ["normal", "advertencia", "sospecha", "critico", "no_determinado"];
const COMPONENTES = ["mainboard", "cpu", "ram", "almacenamiento", "fuente_poder", "bateria", "red"];

// (a) cinco siluetas distintas, sin scripts
const estados = ESTADOS.map(iconoEstado);
assert.strictEqual(new Set(estados).size, 5, "los 5 íconos de estado deben ser distintos");
estados.forEach((svg) => assert(!svg.includes("<script"), "sin <script"));

// (b) accesibles y heredan el color
estados.forEach((svg) => {
    assert(svg.includes('aria-hidden="true"'));
    assert(svg.includes('stroke="currentColor"'));
    assert(svg.includes('viewBox="0 0 24 24"') && svg.includes('stroke-width="1.75"'));
});

// (c) estado desconocido -> no_determinado
assert.strictEqual(iconoEstado("raro"), iconoEstado("no_determinado"));

// (d) 7 íconos de componente distintos + uno genérico
const comps = COMPONENTES.map(iconoComponente);
assert.strictEqual(new Set(comps).size, 7);
assert(!comps.includes(iconoComponente("x")), "el genérico no se confunde con un componente");
assert.strictEqual(iconoComponente("x"), iconoComponente("otro"));
comps.concat(iconoComponente("x")).forEach((svg) => assert(svg.includes('aria-hidden="true"') && svg.includes('stroke="currentColor"')));

// (e) íconos de interfaz
assert(iconoUi("menu") && iconoUi("tema-oscuro"));
assert.notStrictEqual(iconoUi("menu"), iconoUi("tema-oscuro"));
const ui = ["tema-claro", "tema-oscuro", "menu", "flecha", "informe", "descargar", "demo", "revisar"].map(iconoUi);
assert.strictEqual(new Set(ui).size, 8);
ui.forEach((svg) => assert(svg.includes('aria-hidden="true"') && svg.includes('stroke="currentColor"')));

// estado.js: cada estado tiene texto de chip
ESTADOS.forEach((e) => assert(typeof CHIP_TEXTO[e] === "string" && CHIP_TEXTO[e]));

// --- modelo.js: pestañas, tema, modo ---
const TRES = ["resumen", "componentes", "recomendaciones"];
assert.deepStrictEqual(PESTANAS, ["resumen", "componentes", "recomendaciones", "analisis"]);

// (a) pestanaDesdeHash
assert.strictEqual(pestanaDesdeHash("#componentes", ["resumen", "componentes"]), "componentes");
assert.strictEqual(pestanaDesdeHash("#componentes", ["resumen"]), "resumen");
assert.strictEqual(pestanaDesdeHash("#analisis", ["resumen", "componentes"]), "resumen");
[ "", "#zzz", null, undefined, 5, {}, "#__proto__", "#constructor" ].forEach((h) =>
    assert.strictEqual(pestanaDesdeHash(h, ["resumen", "componentes"]), "resumen", String(h)));
assert.strictEqual(pestanaDesdeHash("#zzz", null), "resumen");
assert.strictEqual(pestanaDesdeHash("#componentes", undefined), "resumen");

// (b) siguientePestana
assert.strictEqual(siguientePestana("resumen", "ArrowRight", TRES), "componentes");
assert.strictEqual(siguientePestana("recomendaciones", "ArrowRight", TRES), "resumen");
assert.strictEqual(siguientePestana("resumen", "ArrowLeft", TRES), "recomendaciones");
assert.strictEqual(siguientePestana("componentes", "Home", TRES), "resumen");
assert.strictEqual(siguientePestana("resumen", "End", TRES), "recomendaciones");
assert.strictEqual(siguientePestana("componentes", "x", TRES), "componentes");
assert.strictEqual(siguientePestana("resumen", "ArrowRight", ["resumen", "recomendaciones"]), "recomendaciones");
assert.strictEqual(siguientePestana("resumen", "ArrowLeft", ["resumen", "recomendaciones"]), "recomendaciones");
assert.strictEqual(siguientePestana("resumen", "ArrowRight", ["resumen"]), "resumen");
assert.strictEqual(siguientePestana("analisis", "ArrowRight", TRES), "resumen"); // actual fuera de las habilitadas
assert.strictEqual(siguientePestana("analisis", "ArrowLeft", TRES), "recomendaciones"); // desconocida + Izquierda -> la última
assert.strictEqual(siguientePestana("zzz", "ArrowRight", TRES), "resumen");             // desconocida + Derecha -> la primera

// (c) temaValido / modoValido
assert.strictEqual(temaValido("oscuro"), "oscuro");
["x", null, {}, undefined, "Oscuro"].forEach((v) => assert.strictEqual(temaValido(v), "claro"));
assert.strictEqual(temaValido("claro"), "claro");
assert.strictEqual(modoValido("tecnico"), "tecnico");
["x", undefined, null, {}, "Tecnico"].forEach((v) => assert.strictEqual(modoValido(v), "simple"));

// (d) habilitadasSegun
assert.deepStrictEqual(habilitadasSegun(false, true), ["resumen"]);
assert.deepStrictEqual(habilitadasSegun(true, false), TRES);
assert.deepStrictEqual(habilitadasSegun(true, true), PESTANAS);

// --- modelo.js: resumen (veredicto, línea, medida clave, datos del equipo, lo primero) ---
const comp = (id, estado, extra = {}) => ({ componente: id, estado, mensaje: `mensaje ${id}`, datos: null, ...extra });
const todos = (estado) => Object.fromEntries(COMPONENTES.map((id) => [id, comp(id, estado)]));

// (a) medidaClave: solo datos reales o "—", nunca lanza
assert.strictEqual(medidaClave("cpu", { datos: { temperatura_c: 54.1 } }), "54 °C");
assert.strictEqual(medidaClave("cpu", { datos: { nucleos_fisicos: 8 } }), "8 núcleos");
[{ datos: null }, undefined, { datos: { temperatura_c: "x" } }, null, 5, "cpu", { datos: 7 }, { datos: [] }, {}].forEach((v) =>
    assert.strictEqual(medidaClave("cpu", v), "—", JSON.stringify(v)));
assert.strictEqual(medidaClave("ram", { datos: { capacidad_fisica_gb: 16, porcentaje_uso: 53.6 } }), "16 GB · 54 % en uso");
assert.strictEqual(medidaClave("ram", { datos: { capacidad_fisica_gb: 16 } }), "16 GB");
assert.strictEqual(medidaClave("ram", { datos: { capacidad_fisica_gb: "16" } }), "—");
assert.strictEqual(medidaClave("bateria", { datos: { aplica: false } }), "Sin batería");
assert.strictEqual(medidaClave("bateria", { datos: { aplica: true, salud_porcentaje: 85 } }), "85 % de salud");
assert.strictEqual(medidaClave("bateria", { datos: { aplica: true } }), "—");
assert.strictEqual(medidaClave("bateria", { datos: {} }), "—");
assert.strictEqual(medidaClave("red", { datos: { interfaces: [{ link_activo: false }, { link_activo: true, velocidad_mbps: 866 }] } }), "866 Mbps");
assert.strictEqual(medidaClave("red", { datos: { interfaces: [{ link_activo: false }, { link_activo: false }] } }), "Sin enlace");
assert.strictEqual(medidaClave("red", { datos: { interfaces: [] } }), "—");
assert.strictEqual(medidaClave("red", { datos: { interfaces: "x" } }), "—");
assert.strictEqual(medidaClave("mainboard", { datos: { fabricante: "LENOVO", modelo: "20XH002NUS" } }), "LENOVO 20XH002NUS");
const largo = medidaClave("mainboard", { datos: { fabricante: "F".repeat(30), modelo: "M".repeat(30) } });
assert(largo.length <= 28 && largo.endsWith("…"), largo);
assert.strictEqual(medidaClave("mainboard", { datos: { fabricante: 5, modelo: null } }), "—");
assert.strictEqual(medidaClave("fuente_poder", { datos: { rieles: [1, 2, 3] } }), "3 sensores de voltaje");
assert.strictEqual(medidaClave("fuente_poder", { datos: { rieles: [] } }), "—");
assert.strictEqual(medidaClave("almacenamiento", { datos: { discos_internos: [{ tamano_gb: 476.9, salud: "normal" }] } }), "476.9 GB · salud normal");
assert.strictEqual(medidaClave("almacenamiento", { datos: { discos_internos: [{ tamano_gb: 500 }] } }), "500 GB");
assert.strictEqual(medidaClave("almacenamiento", { datos: { discos_internos: [] } }), "—");
assert.strictEqual(medidaClave("zzz", {}), "—");
assert.strictEqual(medidaClave("__proto__", { datos: {} }), "—");
assert.strictEqual(medidaClave(undefined, undefined), "—");

// (b) lineaResumen
assert.strictEqual(lineaResumen(todos("normal")), "Todo lo que pudimos revisar está bien.");
const conSospecha = { ...todos("normal"), ram: comp("ram", "sospecha") };
assert(lineaResumen(conSospecha).startsWith("Están bien: ") && lineaResumen(conSospecha).includes("Necesitan atención: Memoria RAM."), lineaResumen(conSospecha));
const conSinDatos = { ...todos("normal"), red: comp("red", "no_determinado") };
assert(lineaResumen(conSinDatos).includes("No se pudieron revisar: Red.") && lineaResumen(conSinDatos).includes("Todo lo que pudimos revisar está bien."), lineaResumen(conSinDatos));
assert(lineaResumen(todos("no_determinado")).startsWith("No pudimos leer ningún componente de tu PC: "));
assert(lineaResumen(todos("no_determinado")).endsWith("Prueba cerrar y abrir de nuevo aceptando el aviso de Windows."));
const mixto = { cpu: comp("cpu", "critico"), red: comp("red", "no_determinado") };
assert.strictEqual(lineaResumen(mixto), "Necesitan atención: Procesador. No se pudieron revisar: Red.");
assert.strictEqual(lineaResumen({}), "");
assert.strictEqual(lineaResumen(null), "");
assert(lineaResumen({ cpu: comp("cpu", "raro") }).startsWith("No pudimos leer")); // estado raro = sin datos

// (c) loPrimero
const critico = { almacenamiento: comp("almacenamiento", "critico", { guia: { urgencia: "alta", que_hacer: ["Respalda hoy", "Luego cambia el disco"] } }) };
const recMedia = { id: "r1", titulo: "Cambia a un SSD", prioridad: "media" };
const lp = loPrimero({ componentes: critico, recomendaciones: [recMedia] });
assert.strictEqual(lp.length, 2);
assert.deepStrictEqual(lp[0], { texto: "Respalda hoy", destino: "componentes:almacenamiento", urgencia: "alta" });
assert.deepStrictEqual(lp[1], { texto: "Cambia a un SSD", destino: "recomendaciones", urgencia: "media" });
const cinco = { componentes: { ...todos("normal"), cpu: comp("cpu", "critico"), ram: comp("ram", "sospecha"), red: comp("red", "advertencia"), bateria: comp("bateria", "advertencia") },
    recomendaciones: [{ titulo: "R alta", prioridad: "alta" }] };
assert.strictEqual(loPrimero(cinco).length, 3);
assert.strictEqual(loPrimero(cinco, 2).length, 2);
assert.strictEqual(loPrimero(cinco, 10).length, 5);
assert.deepStrictEqual(loPrimero(cinco).map((x) => x.urgencia), ["alta", "alta", "media"]);
assert.strictEqual(loPrimero(cinco)[0].destino, "componentes:cpu"); // empate de urgencia: el componente antes que la recomendación
assert.deepStrictEqual(loPrimero({ componentes: todos("normal") }), []);
assert.deepStrictEqual(loPrimero({ componentes: {} }), []);
assert.deepStrictEqual(loPrimero(null), []);
assert.deepStrictEqual(loPrimero({}), []);
// no_determinado solo si no hay candidatos alta/media
const soloND = { componentes: { ...todos("normal"), red: comp("red", "no_determinado") } };
assert.deepStrictEqual(loPrimero(soloND).map((x) => x.destino), ["componentes:red"]);
assert.strictEqual(loPrimero(soloND)[0].urgencia, "baja");
assert.deepStrictEqual(loPrimero({ componentes: { ...soloND.componentes, cpu: comp("cpu", "critico") } }).map((x) => x.destino), ["componentes:cpu"]);
// texto repetido no se duplica
const rep = { componentes: { cpu: comp("cpu", "critico", { guia: { urgencia: "alta", que_hacer: ["Haz esto"] } }), ram: comp("ram", "critico", { guia: { urgencia: "alta", que_hacer: ["Haz esto"] } }) } };
assert.strictEqual(loPrimero(rep).length, 1);
// sin guía: urgencia por estado y texto = mensaje
const sinGuia = loPrimero({ componentes: { cpu: comp("cpu", "critico"), ram: comp("ram", "sospecha"), red: comp("red", "advertencia") } });
assert.deepStrictEqual(sinGuia.map((x) => [x.urgencia, x.texto]), [["alta", "mensaje cpu"], ["media", "mensaje ram"], ["baja", "mensaje red"]]);
// guía mal formada
assert.strictEqual(loPrimero({ componentes: { cpu: comp("cpu", "critico", { guia: { urgencia: "ninguna", que_hacer: "no es lista" } }) } })[0].texto, "mensaje cpu");
assert.strictEqual(loPrimero({ componentes: { cpu: comp("cpu", "critico", { guia: 5, mensaje: undefined }) } })[0].urgencia, "alta");
assert.deepStrictEqual(loPrimero({ componentes: { cpu: comp("cpu", "normal") }, recomendaciones: [null, 5, { titulo: "baja", prioridad: "baja" }, { prioridad: "alta" }] }), []);

// (d) datosEquipo
const completo = {
    componentes: {
        mainboard: comp("mainboard", "normal", { datos: { fabricante: "LENOVO", modelo: "20XH002NUS" } }),
        cpu: comp("cpu", "normal", { datos: { nombre: "Intel Core i5" } }),
        ram: comp("ram", "normal", { datos: { capacidad_fisica_gb: 16 } }),
    },
    hechos: { so: { nombre: "Windows 11 Pro" }, discos: [{ modelo: "X", tipo: "ssd", externo: false, tamano_gb: 476.9 }, { modelo: "USB", tipo: "hdd", externo: true, tamano_gb: 1000 }] },
};
assert.deepStrictEqual(datosEquipo(completo), [
    { etiqueta: "Equipo", valor: "LENOVO 20XH002NUS" }, { etiqueta: "Sistema", valor: "Windows 11 Pro" },
    { etiqueta: "Procesador", valor: "Intel Core i5" }, { etiqueta: "Memoria", valor: "16 GB" }, { etiqueta: "Disco", valor: "476.9 GB SSD" },
]);
assert.deepStrictEqual(datosEquipo({ componentes: {} }), []);
assert.deepStrictEqual(datosEquipo(null), []);
assert.deepStrictEqual(datosEquipo({ componentes: { cpu: { datos: 5 }, ram: null }, hechos: { so: 3, discos: "x" } }), []);
const hostil = datosEquipo({ componentes: { mainboard: comp("mainboard", "normal", { datos: { fabricante: "<img onerror=x>", modelo: "m" } }) } });
assert.strictEqual(hostil[0].valor, "<img onerror=x> m"); // cadena cruda: el escape ocurre al dibujar
const sinHechos = datosEquipo({ componentes: { almacenamiento: comp("almacenamiento", "normal", { datos: { discos_internos: [{ tamano_gb: 250 }] } }) } });
assert.deepStrictEqual(sinHechos, [{ etiqueta: "Disco", valor: "250 GB" }]);
assert.deepStrictEqual(datosEquipo({ componentes: {}, hechos: { discos: [{ tipo: "desconocido", tamano_gb: 120 }] } }), [{ etiqueta: "Disco", valor: "120 GB" }]);

// (e) normalizarEstado, calcularVeredicto, ordenarPorGravedad
ESTADOS.forEach((e) => assert.strictEqual(normalizarEstado(e), e));
["raro", undefined, null, 5, {}, "__proto__", "constructor"].forEach((v) => assert.strictEqual(normalizarEstado(v), "no_determinado", String(v)));
const un = (e) => ({ x: comp("x", e) });
assert.strictEqual(calcularVeredicto({ ...un("normal"), y: comp("y", "critico"), z: comp("z", "sospecha") }), "CRITICO");
assert.strictEqual(calcularVeredicto({ ...un("normal"), y: comp("y", "sospecha"), z: comp("z", "advertencia") }), "SOSPECHA");
assert.strictEqual(calcularVeredicto({ ...un("normal"), y: comp("y", "advertencia"), z: comp("z", "no_determinado") }), "ADVERTENCIA");
assert.strictEqual(calcularVeredicto({ ...un("normal"), y: comp("y", "no_determinado") }), "NO_DETERMINADO");
assert.strictEqual(calcularVeredicto(un("normal")), "NORMAL");
assert.strictEqual(calcularVeredicto({ x: comp("x", "raro") }), "NO_DETERMINADO");
assert.strictEqual(calcularVeredicto({}), "NORMAL");
assert.strictEqual(calcularVeredicto(null), "NORMAL");
const ord = { a: comp("a", "normal"), b: comp("b", "critico"), c: comp("c", "normal"), d: comp("d", "sospecha"), e: comp("e", "critico") };
assert.deepStrictEqual(ordenarPorGravedad(["a", "b", "c", "d", "e"], ord), ["b", "e", "d", "a", "c"]); // estable
assert.deepStrictEqual(ordenarPorGravedad(["q", "a", "b"], ord), ["b", "q", "a"]);                      // desconocido = no_determinado, antes de normal
assert.deepStrictEqual(ordenarPorGravedad([], null), []);

console.log("modelo.test.js: OK");
