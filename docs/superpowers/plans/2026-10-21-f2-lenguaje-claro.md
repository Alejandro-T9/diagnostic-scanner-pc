# F2: Lenguaje claro para usuarios sin conocimientos técnicos — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que cada componente y cada estado muestre, junto al semáforo, un texto simple de qué significa, qué hacer y quién debe hacerlo; que exista un modo simple y un modo técnico; y que se pueda abrir un informe imprimible para llevar al técnico.

**Architecture:** Un módulo nuevo `backend/explicador.py` guarda una tabla `(componente, estado) → guía`. `scanner.py` pega la guía a cada resultado **sin tocar el contrato de 5 llaves** (la llave `guia` es aditiva). `backend/informe.py` arma un informe HTML imprimible a partir del último escaneo. El frontend gana un interruptor modo simple/técnico, un sello en palabras y tarjetas con la guía.

**Tech Stack:** Python 3.12, Flask 3, JS vanilla (sin frameworks), HTML/CSS propios. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-10-21-version-portable-no-tecnicos-design.md` (secciones 3, 4 D6/D7/D10, 5.1, 5.7 y 9) y decisión 28 de `docs/DECISIONES.md`.

## Global Constraints

- Contrato de módulos de 5 llaves (`componente, estado, mensaje, datos, recomendacion`) **no cambia**; `guia` es una llave extra que agrega `scanner.py`. `scanner._cumple_contrato` no se modifica.
- Sin frameworks JS, sin dependencias nuevas de Python.
- Ningún dato inventado: cada afirmación de un texto debe poder rastrearse a lo medido. Prohibido alarmismo ("tu PC está en peligro"), empujar a comprar, o prometer que algo "está limpio/seguro". Sin jerga en el texto simple: si se usa un término técnico, se explica en la misma frase.
- Tono: tuteo ("tu PC", "selecciona"), frases cortas. La interfaz actual usa voseo ("Seleccioná"): se corrige en las dos cadenas que existen (`frontend/templates/index.html`, `frontend/static/js/app.js`).
- Valores permitidos de la guía: `quien ∈ {"tu_mismo", "tecnico", "nadie"}`; `urgencia ∈ {"ninguna", "baja", "media", "alta"}`.
- Todo texto que venga de un dispositivo (modelo de disco, nombre de adaptador) y termine en HTML debe escaparse (`html.escape`).
- Pruebas: `cd backend; python test_scanner.py` (ver `docs/superpowers/plans/COMANDO_PRUEBAS.txt`); estilo `assert`, sin pytest, tests registrados en `__main__`; stderr limpio.
- Las decisiones nuevas van al final de `docs/DECISIONES.md` (solo se agrega).
- Estados posibles: `normal`, `advertencia`, `sospecha`, `critico`, `no_determinado`. Componentes: `mainboard, cpu, ram, almacenamiento, fuente_poder, bateria, red`.

## Review Focus

1. Texto de un dispositivo con HTML (`<script>`, `&`) dentro del informe imprimible: debe salir escapado. → Tarea 3.
2. Resultado con un estado o componente desconocido (o un módulo que devolvió "error"): la guía cae a un texto genérico, nunca `KeyError`. → Tarea 1.
3. `/api/informe` pedido antes de cualquier escaneo: página amable con la instrucción de escanear, no un error 500. → Tarea 3.
4. Procesador `no_determinado` (lo normal si la app corre sin administrador): la guía debe mencionar el permiso de administrador. → Tarea 1.
5. Interfaz con un escaneo sin `guia` (modo demostración antiguo o backend viejo): no se rompe, simplemente no muestra la tarjeta. → Tarea 4 (verificación manual).

---

### Task 1: `explicador.py` — la tabla de guías

**Files:**
- Create: `backend/explicador.py`
- Test: `backend/test_scanner.py`
- Modify: `docs/reglas-recomendaciones.md` (una nota al inicio: los textos simples viven en `backend/explicador.py`)

**Interfaces:**
- Produces:
  - `GUIAS: dict[str, dict[str, dict]]` — 7 componentes × 5 estados = 35 entradas. Cada entrada: `{"que_significa": str, "que_hacer": list[str], "quien": str, "urgencia": str, "pregunta_tecnico": str}`.
  - `guia_para(componente: str, estado: str) -> dict` — devuelve una **copia** de la entrada; si el par no existe devuelve una guía genérica (`quien="tecnico"`, `urgencia="baja"`, texto que explica que no se pudo interpretar el resultado).
  - `QUIEN_VALIDOS = {"tu_mismo", "tecnico", "nadie"}` y `URGENCIAS_VALIDAS = {"ninguna", "baja", "media", "alta"}`.
  - `FRASES_VEREDICTO: dict[str, str]` — `NORMAL` → "Tu PC está bien"; `ADVERTENCIA` y `SOSPECHA` → "Tu PC necesita atención"; `CRITICO` → "Tu PC tiene un problema serio"; `NO_DETERMINADO` → "No pudimos revisar todo" (única fuente: la usan el informe y, vía `/api/guias`, el frontend).

**Reglas de contenido (el implementador redacta los 35 textos; estas reglas son vinculantes):**
- `normal` → `urgencia="ninguna"`, `quien="nadie"`, `que_hacer` con **un** hábito de mantenimiento útil para ese componente, `pregunta_tecnico=""`.
- `critico` → `urgencia="alta"`. `sospecha` → `urgencia="media"`. `advertencia` → `urgencia="baja"` o `"media"` según el componente. `no_determinado` → `urgencia="baja"`.
- `que_significa` explica el estado **para ese componente** en 1–2 frases sin jerga y sin inventar causas que el módulo no mide. Partir de lo que cada módulo realmente evalúa: temperatura del CPU (advertencia ≥ 70 °C, crítico > 85 °C), uso de RAM (advertencia ≥ 80 %, crítico > 95 %), salud S.M.A.R.T. del disco según Windows Storage Health, salud de la batería frente a su capacidad de diseño, enlace y errores de paquetes de la red, placa con datos de fábrica sin configurar, lectura de voltajes del procesador.
- `que_hacer` es una lista de 1–3 pasos concretos. Un paso que implique abrir el equipo o reemplazar hardware va con `quien="tecnico"`; cerrar programas, hacer copia de seguridad o cambiar hábitos va con `quien="tu_mismo"`.
- `pregunta_tecnico` (solo estados distintos de `normal`): una pregunta que el usuario puede hacerle al técnico, en tuteo, para comprobar que lo que se le propone se justifica con lo medido (p. ej. "¿Qué prueba muestra que el disco debe cambiarse y no solo respaldarse?").
- `cpu` + `no_determinado`: debe decir que sin permisos de administrador algunos sensores no se pueden leer, y que cerrar y abrir de nuevo aceptando el aviso de Windows suele resolverlo (`quien="tu_mismo"`).
- `almacenamiento` + `critico`: prioridad a respaldar la información antes de cualquier otra acción.
- Prohibido en los textos: "peligro", "infectado", "limpio", "seguro", "garantiza", nombres de marcas, precios, y recomendar comprar algo concreto.

- [ ] **Step 1: Escribir `test_explicador()`** en `test_scanner.py` y registrarla en `__main__`. Aserciones: (a) cobertura: para cada uno de los 7 componentes (`scanner.COMPONENTES`) y cada estado de `scanner.ESTADOS_VALIDOS`, `explicador.GUIAS[c][e]` existe; (b) forma: las 5 llaves exactas, `que_significa` no vacío, `que_hacer` es lista de `str` no vacíos, `quien ∈ QUIEN_VALIDOS`, `urgencia ∈ URGENCIAS_VALIDAS`; (c) reglas por estado: `normal` ⇒ `urgencia=="ninguna"` y `quien=="nadie"` y `pregunta_tecnico==""`; `critico` ⇒ `urgencia=="alta"`; `sospecha` ⇒ `urgencia=="media"`; estados distintos de `normal` ⇒ `pregunta_tecnico` no vacía y `len(que_hacer) >= 1`; (d) palabras prohibidas: ningún texto (en minúsculas) de ninguna entrada contiene `peligro`, `infectad`, `limpio`, `garantiza`; (e) Review Focus 2: `guia_para("inexistente", "normal")` y `guia_para("cpu", "estado_raro")` devuelven un dict con las 5 llaves sin lanzar; (f) `guia_para` devuelve copia: mutar `["que_hacer"]` del resultado no altera `GUIAS`; (g') `explicador.FRASES_VEREDICTO` tiene exactamente las 5 llaves en mayúsculas de `scanner._SEVERIDAD` y valores no vacíos; (g) Review Focus 4: el texto de `GUIAS["cpu"]["no_determinado"]` (que_significa + pasos, en minúsculas) contiene `administrador`.
- [ ] **Step 2: Correr `cd backend; python test_scanner.py` y ver que falla** (módulo `explicador` inexistente).
- [ ] **Step 3: Implementar `backend/explicador.py`** con las firmas de arriba y los 35 textos redactados según las reglas. Un comentario de cabecera en español explica que la tabla es la única fuente de los textos simples y que el equipo revisa la redacción (spec §8).
- [ ] **Step 4: Agregar la nota en `docs/reglas-recomendaciones.md`** (2–3 líneas) y correr `python test_scanner.py` → pasa. Checkpoint (`git commit`).

### Task 2: El escáner adjunta la guía; reporte de texto y `/api/guias`

**Files:**
- Modify: `backend/scanner.py` (`_escanear_componente`), `backend/utils.py` (`generar_reporte_texto`), `backend/app.py`
- Test: `backend/test_scanner.py`

**Interfaces:**
- Consumes: `explicador.guia_para(componente, estado) -> dict` (Tarea 1).
- Produces: cada valor de `resultado["componentes"][nombre]` incluye la llave `"guia"` (dict de la Tarea 1) — también para los resultados de `_resultado_error`; `GET /api/guias` devuelve `{componente: {estado: guia}}` (la tabla completa, JSON, 200); el reporte de texto agrega, por componente distinto de `normal`, las líneas `Qué significa:`, `Qué hacer:` (un paso por línea con `- `) y `Quién lo hace:`.

- [ ] **Step 1: Escribir los tests** `test_escaner_adjunta_guia()` y `test_guias_endpoint()` en `test_scanner.py`: (a) con un módulo falso que devuelve el contrato de 5 llaves con `estado="critico"` (reemplazando `importlib.import_module` o `scanner._escanear_componente`'s módulo, restaurando en `finally`), la salida de `scanner._escanear_componente("cpu")` incluye `guia` con `urgencia=="alta"` **y conserva las 5 llaves originales intactas**; (b) un módulo inexistente (`_escanear_componente("inexistente")`) devuelve un resultado `no_determinado` que también incluye `guia`; (c) `scanner._cumple_contrato(respuesta_sin_guia)` sigue devolviendo `True` (el contrato no cambió); (d) `GET /api/guias` (cliente de prueba en hilo de trabajo, como `test_app_rutas`) responde 200 y el JSON tiene los 7 componentes con 5 estados; (e) `utils.generar_reporte_texto` de un resultado con un componente `critico` y su `guia` contiene `Qué significa:` y `Quién lo hace:`, y para un componente `normal` **no** agrega esas líneas. Registrar en `__main__`.
- [ ] **Step 2: Correr y ver que falla.**
- [ ] **Step 3: Implementar:** en `scanner._escanear_componente`, antes de devolver (en las tres salidas: éxito, error de módulo y contrato incumplido) agregar `guia` a una copia del dict (`{**respuesta, "guia": explicador.guia_para(nombre, respuesta["estado"])}`); ruta `/api/guias` en `app.py` que responde `explicador.GUIAS`; ampliar `generar_reporte_texto` con las líneas indicadas.
- [ ] **Step 4: Correr `python test_scanner.py`** → pasa, stderr limpio. Checkpoint.

### Task 3: Informe imprimible para el técnico

**Files:**
- Create: `backend/informe.py`
- Modify: `backend/app.py` (ruta `/api/informe`)
- Test: `backend/test_scanner.py`

**Interfaces:**
- Consumes: resultado de escaneo con `guia` por componente (Tarea 2) y `scanner.clasificar_equipo(resultado) -> str`.
- Produces:
  - `informe.generar_informe_html(resultado: dict | None, veredicto: str) -> str` — documento HTML completo (`<!DOCTYPE html>`, `lang="es"`, estilos en línea con una regla `@media print`, sin recursos externos). Contenido: título, fecha/ID de diagnóstico, identidad del equipo (fabricante/modelo de `componentes.mainboard.datos` si existe), sello en palabras (misma frase que usa el frontend, ver Tarea 4), por cada componente una tarjeta con nombre, estado, `mensaje`, `guia.que_significa` y pasos, y al final la sección **"Preguntas para tu técnico"** con las `pregunta_tecnico` de los componentes distintos de `normal`, más una frase fija de límites ("Este informe se basa solo en lo que el programa pudo medir; no reemplaza la revisión de un técnico"). Si `resultado` es `None`/vacío devuelve una página amable "Aún no hay un escaneo: vuelve al panel y pulsa Escanear Sistema".
  - `GET /api/informe` → 200 `text/html` con `informe.generar_informe_html(_ultimo_escaneo, veredicto)`; ante cualquier excepción, 500 JSON como las demás rutas.
- Todo texto que no sea una cadena fija se escapa con `html.escape`.

- [ ] **Step 1: Escribir `test_informe()`**: (a) con un resultado cuyo `mainboard.datos["modelo"]` es `"<script>alert(1)</script> & Co"` y un `mensaje` con `<b>`, el HTML devuelto **no** contiene `<script>alert(1)</script>` ni `<b>` sin escapar, y sí contiene `&lt;script&gt;` (Review Focus 1); (b) con `resultado=None` devuelve HTML con el texto "Aún no hay un escaneo" y no lanza (Review Focus 3); (c) con un componente `critico` aparece la sección "Preguntas para tu técnico" con su `pregunta_tecnico` escapada; con todos `normal` esa sección no lista preguntas pero sí muestra la frase de límites; (d) el HTML contiene `@media print`; (e) `GET /api/informe` con `app._ultimo_escaneo = None` responde 200 y `text/html` (cliente de prueba en hilo de trabajo; restaurar `_ultimo_escaneo` en `finally`). Registrar en `__main__`.
- [ ] **Step 2: Correr y ver que falla.**
- [ ] **Step 3: Implementar `backend/informe.py` y la ruta.** El sello en palabras sale de `explicador.FRASES_VEREDICTO` (Tarea 1). Exponerlo también en `/api/guias` bajo la llave `"_veredictos"` (ajustar la ruta de la Tarea 2 y su prueba (d): ahora la respuesta tiene los 7 componentes **más** `_veredictos`) para que el frontend no duplique las frases.
- [ ] **Step 4: Correr `python test_scanner.py`** → pasa. Checkpoint.

### Task 4: Interfaz: modo simple / modo técnico

**Files:**
- Modify: `frontend/templates/index.html`, `frontend/static/js/app.js`, `frontend/static/css/style.css`

**Interfaces:**
- Consumes: `guia` dentro de cada componente del escaneo; `GET /api/guias` (tabla completa + `_veredictos`); `GET /api/informe`.
- Produces: interruptor visible "Modo simple | Modo técnico" (por defecto **simple**; se recuerda con `localStorage` dentro de `try/catch`, y la app funciona igual si falla); sello con frase en palabras; botón "Informe para el técnico" (abre `/api/informe` en una pestaña nueva).

**Comportamiento:**
- *Modo técnico:* la interfaz actual sin cambios, más un bloque con la guía (qué significa / qué hacer / quién) dentro del panel de detalle.
- *Modo simple:* se oculta el mapa físico y la lista técnica; se ve (1) el sello con la frase del veredicto, (2) una línea "Están bien: A, B. Necesitan atención: C." (si todos están bien, "Todo lo que pudimos revisar está bien."), (3) una tarjeta por componente **ordenadas de más grave a menos grave** con nombre, chip de estado, `mensaje`, `guia.que_significa`, los pasos de `que_hacer`, y una etiqueta "Lo puedes hacer tú" / "Mejor con un técnico" / "No necesita acción" según `quien` y un indicador de urgencia en palabras; (4) el botón del informe.
- *Modo demostración:* al activarlo, el JS pide `/api/guias`, y completa cada componente de `DATOS_MOCK` con `guia = tabla[componente][estado]`; si la petición falla, muestra los componentes sin tarjeta de guía (no rompe).
- Si un componente llega **sin** `guia`, no se dibuja su bloque de guía (Review Focus 5).
- Reemplazar las dos cadenas con voseo ("Seleccioná un componente…") por tuteo ("Selecciona un componente…").
- Sin librerías, sin `innerHTML` con texto del dispositivo sin escapar: usar `textContent` o una función `escapar()` para `mensaje` y los textos de la guía.
- Reusar la paleta de `config/palette.css` y las clases de chip existentes; el CSS nuevo va en `style.css`.

- [ ] **Step 1: Implementar** los cambios descritos (HTML del interruptor y contenedor del modo simple; JS de render, persistencia, `/api/guias`, escape; CSS).
- [ ] **Step 2: Verificación automática** con el servidor real (`python backend\lanzador.py --sin-navegador` desde `backend/`, leer la URL de su salida): `GET /` contiene el interruptor y el contenedor; `GET /static/js/app.js` no contiene la cadena `Seleccioná`; `GET /api/guias` responde 200; `GET /api/informe` responde 200 `text/html`. Matar el proceso al terminar.
- [ ] **Step 3: Verificación visual** (la hace el controlador con el navegador integrado, o el usuario): modo simple y técnico, modo demostración con los 5 estados, escaneo real, apertura del informe, ventana angosta (~700 px) sin desbordes, y consola del navegador sin errores. Anotar el resultado en el informe de la tarea. Checkpoint.

### Task 5: Brave y otros Chromium como navegador de la ventana

**Files:**
- Modify: `backend/lanzador.py` (`_CANDIDATOS` / `elegir_navegador`)
- Test: `backend/test_scanner.py` (`test_lanzador`)

**Interfaces:**
- Produces: `elegir_navegador(variables, existe) -> str | None` considera **después** de Edge y Chrome: Brave en `<ProgramFiles>\BraveSoftware\Brave-Browser\Application\brave.exe`, `<ProgramFiles(x86)>` y `<LocalAppData>`. (Brave es Chromium y acepta `--app` y `--user-data-dir`; la laptop del equipo no tiene Edge y hoy cae al navegador predeterminado en una pestaña normal.)

- [ ] **Step 1: Agregar a `test_lanzador`:** con `existe` simulado y solo Brave en `ProgramFiles`, `elegir_navegador` devuelve esa ruta; con Edge y Brave presentes devuelve Edge; con Chrome y Brave presentes devuelve Chrome.
- [ ] **Step 2: Correr y ver que falla; implementar** agregando las tres rutas al final de la lista, en ese orden; correr `python test_scanner.py` → pasa. Checkpoint.

---

## Self-review

- **Cobertura de la spec §5.1/§5.7:** sello en palabras (T3, T4) · resumen "Están bien / Necesitan atención" (T4) · guía por componente y estado con qué significa, qué hacer, quién y urgencia (T1, T2, T4) · informe para el técnico con preguntas generadas desde hallazgos reales (T3) · modo simple/técnico (T4) · prueba de cobertura de todos los pares (T1) · tuteo (T4, T1). El vocabulario "¿Qué es esto?" desplegable de §5.1 **no** está en F2; queda como mejora posterior.
- **Consistencia de tipos:** `guia_para`, `GUIAS`, `FRASES_VEREDICTO`, `/api/guias` (con `_veredictos`) y `generar_informe_html` se usan con las mismas firmas donde se consumen.
- **Contrato:** `scanner._cumple_contrato` no se toca y una prueba lo confirma (T2c).
- **Redacción:** los 35 textos los escribe el implementador bajo reglas explícitas; el equipo debe revisarlos antes de cerrar F2 (spec §8).
