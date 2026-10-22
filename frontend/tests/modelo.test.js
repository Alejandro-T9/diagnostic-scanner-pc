// Pruebas de la lógica pura del frontend (se ejecutan con: node frontend/tests/modelo.test.js).
// Las llama también backend/test_scanner.py::test_frontend_node cuando hay node.
const assert = require("assert");
const { iconoEstado, iconoComponente, iconoUi } = require("../static/js/iconos.js");
const { CHIP_TEXTO } = require("../static/js/estado.js");
const { PESTANAS, pestanaDesdeHash, siguientePestana, temaValido, modoValido, habilitadasSegun } = require("../static/js/modelo.js");

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

console.log("modelo.test.js: OK");
