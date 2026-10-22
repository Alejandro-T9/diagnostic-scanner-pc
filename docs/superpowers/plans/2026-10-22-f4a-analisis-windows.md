# F4a: Análisis de Windows ("¿por qué va lento?") — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un segundo análisis, a pedido del usuario, que mira el Windows instalado (no el hardware): cuánto espacio queda y qué lo ocupa, qué arranca con el equipo, qué programas hay instalados (incluidos los ocultos) y cuál es la causa más probable de que el equipo vaya lento, todo con texto en lenguaje claro y solo lectura.

**Architecture:** Cuatro módulos nuevos en `backend/analisis/` (`espacio`, `inicio`, `programas`, `rendimiento`) con el **mismo contrato de 5 llaves** que los módulos de hardware (`componente, estado, mensaje, datos, recomendacion`). No se agregan a `scanner.COMPONENTES` (no cambian el veredicto, la cobertura ni el mapa de los 7 componentes del proyecto): viven en una lista aparte `scanner.ANALISIS` y se ejecutan con `scanner.ejecutar_analisis()` desde un endpoint propio `GET /api/analisis` y un botón propio. Cada resultado recibe su `guia` como los demás (`explicador.GUIAS` se amplía a 11 componentes). El último análisis se guarda en memoria (`_ultimo_analisis`) para el reporte de texto y el informe imprimible.

**Tech Stack:** Python 3.12, `winreg`, `psutil`, `ctypes`, `subprocess` (PowerShell, solo lectura, con tiempo límite), Flask 3, JS vanilla. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-10-21-version-portable-no-tecnicos-design.md` (§3, §5.3 filas `programas`, `inicio`, `rendimiento`, `espacio`; §5.4 honestidad; §6) y decisiones 28, 33, 37 de `docs/DECISIONES.md`.

## Global Constraints

- Contrato de 5 llaves intacto; `scanner._cumple_contrato` no cambia; `COMPONENTES` sigue siendo exactamente los 7 componentes de hardware.
- **Solo lectura**: nada se borra, se cambia ni se desinstala. Ningún módulo requiere administrador; lo que no se pueda leer queda `no_determinado` con un mensaje honesto.
- Ningún dato inventado; los umbrales (abajo) son reglas documentadas, no diagnósticos. Sin alarmismo, sin marcas, sin "peligro/infectado/limpio/garantiza"; tuteo; sin jerga sin explicar.
- Todo lo que se lea del sistema (nombres de programas, editores, rutas, procesos) y llegue a HTML se escapa (`html.escape` en Python; `textContent`/`crear()`/`escapar()` en JS). Los datos leídos pueden ser hostiles.
- Cada módulo: una función `_clasificar(...)` **pura** (sin E/S) probada con datos simulados, y lectores privados reemplazables en pruebas, que **nunca lanzan** hacia afuera (`try/except Exception` → `no_determinado`).
- Tiempo: cada módulo ≤ 4 s en esta laptop sin administrador; el análisis completo ≤ ~10 s. Subprocesos (PowerShell) con `timeout` y `CREATE_NO_WINDOW`; si `powershell.exe` no existe (WinPE), degradar a lo que se pueda leer sin él.
- Sin dependencias nuevas. Tests: `cd backend; python test_scanner.py` (ver `docs/superpowers/plans/COMANDO_PRUEBAS.txt`), estilo `assert`, registrados en `__main__`, stderr limpio, solicitudes Flask de prueba con `_en_hilo`.
- Decisión nueva al final de `docs/DECISIONES.md` (solo se agrega): la 38 cubre F4a. Los números 31 y 32 siguen reservados para las pruebas del USB.
- Estados: `normal`, `advertencia`, `sospecha`, `critico`, `no_determinado`. Los módulos de análisis no usan `critico` (nada de lo que miden es una falla confirmada); `GUIAS` conserva igual las 5 entradas por componente por contrato.

## Reglas de clasificación (vinculantes)

| Módulo | Estado | Condición |
|---|---|---|
| `espacio` | `sospecha` | espacio libre de `C:` < 5 % |
| `espacio` | `advertencia` | espacio libre de `C:` < 10 % (y ≥ 5 %) |
| `espacio` | `normal` | espacio libre ≥ 10 % |
| `espacio` | `no_determinado` | no se pudo leer el espacio de `C:` |
| `inicio` | `advertencia` | 10 o más entradas de inicio (Run de usuario y equipo, carpetas Inicio) |
| `inicio` | `normal` | menos de 10 |
| `inicio` | `no_determinado` | no se pudo leer ninguna fuente |
| `programas` | `advertencia` | 3 o más programas **con editor vacío o desconocido** instalados en los últimos 30 días |
| `programas` | `normal` | lista leída y sin esa condición |
| `programas` | `no_determinado` | no se pudo leer ninguna fuente |
| `rendimiento` | `advertencia` | se detecta al menos una causa (ver Tarea 5) |
| `rendimiento` | `normal` | ninguna causa detectada en la medición |
| `rendimiento` | `no_determinado` | no se pudo medir |

## Review Focus

1. Nombre de programa, editor o proceso con HTML (`<script>`, `&`) en la lista de programas, de inicio o de procesos: sale escapado en el informe y en la interfaz. → Tareas 4, 5, 6 y 7.
2. Sin PowerShell (WinPE, o bloqueado) o con la consulta que se cuelga: el módulo termina dentro del tiempo límite y degrada a lo que sí leyó o a `no_determinado`, sin excepción. → Tareas 3 y 4.
3. Equipo con muchísimos programas (500+): lista truncada para pantalla (se informa el total real y cuántos se muestran) sin romper rendimiento ni el JSON. → Tareas 4 y 7.
4. Fechas de instalación ausentes, mal formadas o futuras: no cuentan como "recientes" ni lanzan. → Tarea 4.
5. `/api/analisis` sin haber hecho el escaneo de hardware, y el informe/reporte antes de cualquier análisis: página amable, nunca 500. → Tareas 6 y 7.

---

### Task 1: Textos en lenguaje claro para los 4 análisis y la lista `ANALISIS`

**Files:**
- Modify: `backend/explicador.py` (4 componentes nuevos × 5 estados = 20 entradas en `GUIAS`; nombres legibles), `backend/scanner.py` (constante `ANALISIS`), `backend/test_scanner.py` (`test_explicador`)
- Modify: `docs/reglas-recomendaciones.md` (nota: los textos de análisis también viven en `explicador.py`)

**Interfaces:**
- Produces: `scanner.ANALISIS = ["espacio", "inicio", "programas", "rendimiento"]`; `explicador.GUIAS[c][e]` existe para `c` en `scanner.COMPONENTES + scanner.ANALISIS` y `e` en `scanner.ESTADOS_VALIDOS`; `explicador.NOMBRES_ANALISIS = {"espacio": "Espacio en disco", "inicio": "Programas de inicio", "programas": "Programas instalados", "rendimiento": "¿Por qué va lento?"}`.
- Las 20 entradas siguen las **mismas reglas de contenido** que las 35 existentes (forma de 5 llaves, `quien`/`urgencia` válidos, `normal` ⇒ urgencia `ninguna`/quien `nadie`/pregunta vacía, `critico` ⇒ `alta`, `sospecha` ⇒ `media`, `advertencia` ⇒ `baja` o `media`, no `normal` ⇒ pregunta no vacía, ≤ 220 caracteres por campo, palabras prohibidas) y de contenido específico: `espacio`: explica qué significa tener poco espacio libre para el uso diario (Windows necesita margen para actualizar y trabajar) y pasos que el usuario puede hacer solo (vaciar papelera, borrar descargas que ya no usa, desinstalar lo que no usa, mover fotos y videos a otro disco), nada de "borrar archivos del sistema"; `inicio`: qué es un programa de inicio (arranca solo al encender) y cómo ver/desactivar los que no necesita desde el Administrador de tareas (pestaña Inicio), sin nombrar programas concretos; `programas`: explica que la lista sirve para reconocer lo que instalaste, que "editor desconocido" no significa que sea malo, y que quitar lo que no reconoces o no usas puede aliviar el equipo (desde Configuración → Aplicaciones), con la pregunta al técnico "¿Qué hace este programa y por qué conviene quitarlo?"; `rendimiento`: explica que es una foto del momento (conviene pedirla cuando el equipo está lento) y que no mide todo; `no_determinado` de los cuatro: honesto sobre qué no se pudo leer y qué intentar.
- [ ] **Step 1: Ampliar `test_explicador`** para recorrer `scanner.COMPONENTES + scanner.ANALISIS` (hoy recorre solo los 7) con todas sus aserciones (a)–(g'), más: `scanner.ANALISIS == ["espacio","inicio","programas","rendimiento"]`, `set(scanner.ANALISIS).isdisjoint(scanner.COMPONENTES)`, y `explicador.NOMBRES_ANALISIS` tiene exactamente esas 4 llaves con nombres no vacíos. Correr y ver que falla (llaves ausentes).
- [ ] **Step 2: Implementar** las 20 entradas, `NOMBRES_ANALISIS` y `scanner.ANALISIS` (sin tocar `COMPONENTES`), y la nota en `docs/reglas-recomendaciones.md`. Correr `python test_scanner.py` → pasa, stderr limpio. Checkpoint.

### Task 2: `analisis/espacio.py`

**Files:**
- Create: `backend/analisis/__init__.py`, `backend/analisis/espacio.py`
- Test: `backend/test_scanner.py`

**Interfaces:**
- Produces, en `analisis/espacio.py`: `diagnosticar() -> dict` (contrato de 5 llaves, `componente="espacio"`); `_clasificar(libre_pct: float | None) -> tuple[str, str]` (estado, mensaje) con la tabla de arriba; lectores privados reemplazables: `_leer_disco_c() -> dict | None` (`psutil.disk_usage("C:\\")` → `{"total_gb","libre_gb","usado_gb","libre_pct"}`), `_leer_carpetas() -> list[dict]` (tamaño de `%TEMP%`, `C:\Windows\Temp`, la carpeta Descargas del usuario y la Papelera vía `SHQueryRecycleBinW` con `ctypes`; cada elemento `{"nombre": str, "ruta": str | None, "tamano_gb": float | None, "archivos": int | None}`; el recorrido de cada carpeta tiene tope de 2 s y de 200 000 archivos y marca `"parcial": True` si se cortó). `datos = {"disco_c": {...}, "carpetas": [...]}`. Mensajes en español claro: p. ej. "Te queda el 7 % libre del disco C: (34 GB de 476 GB)."; `recomendacion` por estado en una frase.
- [ ] **Step 1: Escribir `test_analisis_espacio()`** y registrarla: (a) `_clasificar(4.9)[0] == "sospecha"`, `_clasificar(5.0)[0] == "advertencia"`, `_clasificar(9.9)[0] == "advertencia"`, `_clasificar(10.0)[0] == "normal"`, `_clasificar(None)[0] == "no_determinado"`; (b) `diagnosticar()` con `_leer_disco_c` reemplazado por un dict simulado de 7 % y `_leer_carpetas` por una lista fija devuelve las 5 llaves, estado `advertencia`, `datos["disco_c"]["libre_pct"] == 7.0` y `datos["carpetas"]` igual a la lista fija; (c) con `_leer_disco_c` devolviendo `None` o lanzando → `no_determinado` sin excepción; (d) con `_leer_carpetas` lanzando → el estado sigue calculándose por el disco y `datos["carpetas"] == []`; (e) llamada real: `diagnosticar()["componente"] == "espacio"` y el estado está en `ESTADOS_VALIDOS` (sin afirmar valores de la máquina), y termina en ≤ 8 s (medir con `time.perf_counter()`).
- [ ] **Step 2: Correr y ver que falla; Step 3: implementar `espacio.py`** (comentario de cabecera: solo lectura, topes de tiempo, qué se mide y qué no). **Step 4: correr `python test_scanner.py`** → pasa. Checkpoint.

### Task 3: `analisis/inicio.py`

**Files:**
- Create: `backend/analisis/inicio.py`
- Test: `backend/test_scanner.py`

**Interfaces:**
- Produces: `diagnosticar() -> dict` (`componente="inicio"`); `_clasificar(total: int | None) -> tuple[str, str]`; lectores privados reemplazables: `_leer_run() -> list[dict]` (claves `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, `HKLM\Software\Microsoft\Windows\CurrentVersion\Run` y la de `Wow6432Node`, con `winreg`; cada entrada `{"nombre": str, "comando": str, "origen": "usuario" | "equipo"}`), `_leer_carpetas_inicio() -> list[dict]` (carpeta `Startup` del usuario y de todos los usuarios: `{"nombre", "comando": ruta del acceso directo, "origen"}`), `_contar_servicios_automaticos() -> int | None` (`psutil.win_service_iter()` con `start_type() == "automatic"`; `None` si falla). `datos = {"total": int, "entradas": [...], "servicios_automaticos": int | None}`; `entradas` con tope de 200 elementos y `"total"` con el conteo real. `total` = entradas de Run + carpetas Inicio (los servicios se informan aparte, no suman al umbral).
- [ ] **Step 1: Escribir `test_analisis_inicio()`**: (a) `_clasificar(9)[0] == "normal"`, `_clasificar(10)[0] == "advertencia"`, `_clasificar(None)[0] == "no_determinado"`; (b) `diagnosticar()` con lectores simulados (6 entradas en Run + 5 en carpetas) → `total == 11`, estado `advertencia`, `datos["entradas"]` con esos 11 elementos; (c) un lector que lanza → se ignora y las demás fuentes cuentan; todos lanzando → `no_determinado`; (d) Review Focus 1: una entrada de nombre `"<script>alert(1)</script>"` se conserva tal cual en `datos` (el escape se hace al mostrar) y no rompe nada; (e) 300 entradas simuladas → `datos["entradas"]` tiene 200 y `datos["total"] == 300`; (f) llamada real: contrato de 5 llaves, estado válido, ≤ 4 s. Registrar.
- [ ] **Step 2: Correr y ver que falla; Step 3: implementar**; **Step 4: correr `python test_scanner.py`**. Checkpoint.

### Task 4: `analisis/programas.py` (lo instalado, incluidos los ocultos)

**Files:**
- Create: `backend/analisis/programas.py`
- Test: `backend/test_scanner.py`

**Interfaces:**
- Produces: `diagnosticar() -> dict` (`componente="programas"`); `_clasificar(programas: list[dict], hoy: datetime.date) -> tuple[str, str]`; `_es_reciente(fecha: str | None, hoy: datetime.date, dias: int = 30) -> bool` (acepta `AAAAMMDD` del registro; ausente, mal formada o **futura** → `False`); lectores privados reemplazables: `_leer_registro() -> list[dict]` (las tres claves `Uninstall`: `HKLM`, `HKLM\Wow6432Node` y `HKCU`; cada programa `{"nombre", "version", "editor", "fecha": "AAAAMMDD" | None, "oculto": bool, "origen": "registro"}`; `oculto` si `SystemComponent == 1` o `ParentKeyName` existe (son parches/componentes que Windows no lista en Configuración); entradas sin `DisplayName` se descartan; duplicados exactos por (nombre, versión) se unifican), `_leer_aplicaciones_inicio() -> list[dict]` (equivalente a `shell:AppsFolder`: PowerShell `Get-StartApps` con `timeout=10` y `CREATE_NO_WINDOW`, salida JSON; `{"nombre","version": None,"editor": None,"fecha": None,"oculto": False,"origen": "tienda"}`; solo se agregan los que **no** están ya en el registro por nombre; si PowerShell falta o falla → `[]`). Orden de `datos["programas"]`: ocultos al final, el resto por nombre; tope de 300 elementos en la lista con `datos["total"]` real, `datos["ocultos"]` (conteo), `datos["recientes_sin_editor"]` (lista de nombres que cumplen la condición de `advertencia`, tope 20).
- [ ] **Step 1: Escribir `test_analisis_programas()`**: (a) `_es_reciente("20260915", date(2026,10,22)) is True`, `("20260801", …) is False`, `("20261101", …) is False` (futura), `(None, …)`, `("", …)`, `("abc", …)` → `False`; (b) `_clasificar` con 3 programas de editor vacío instalados en los últimos 30 días → `advertencia`; con 2 → `normal`; con 3 pero uno con editor `"Microsoft Corporation"` → `normal`; con lista vacía y fuentes ilegibles (indicado por el llamador) → ver (e); (c) `diagnosticar()` con lectores simulados: registro con 4 programas (uno `SystemComponent`) + tienda con 2 (uno repetido por nombre) → `datos["total"] == 5`, `datos["ocultos"] == 1`, el oculto queda al final, sin duplicado; (d) Review Focus 1: nombre `"<img src=x onerror=alert(1)>"` y editor `"A & B"` se conservan tal cual en `datos`; (e) un lector que lanza se ignora; ambos lanzando o devolviendo vacío → `no_determinado`; (f) Review Focus 3: 500 programas simulados → `datos["programas"]` tiene 300, `datos["total"] == 500` y el JSON sigue serializándose; (g) llamada real: contrato de 5 llaves, estado válido, ≤ 8 s. Registrar.
- [ ] **Step 2: Correr y ver que falla; Step 3: implementar** (cabecera: solo lectura, qué fuentes, que "oculto" significa "Windows no lo lista en Configuración", y el límite de `Get-StartApps`); **Step 4: correr `python test_scanner.py`**. Checkpoint.

### Task 5: `analisis/rendimiento.py` ("¿por qué va lento?")

**Files:**
- Create: `backend/analisis/rendimiento.py`
- Test: `backend/test_scanner.py`

**Interfaces:**
- Produces: `diagnosticar() -> dict` (`componente="rendimiento"`); `_causas(medicion: dict) -> list[dict]` (pura) donde `medicion = {"ram_uso": float | None, "ram_total_gb": float | None, "disco_c_libre_pct": float | None, "disco_tipo": "ssd" | "hdd" | "desconocido", "disco_ocupado_pct": float | None, "cpu_uso": float | None, "procesos": [{"nombre": str, "cpu": float, "ram_mb": float}], "inicio_total": int | None}` y cada causa `{"id": str, "titulo": str, "evidencia": [str]}`; `_clasificar(causas: list, medicion_valida: bool) -> tuple[str, str]`; lector privado reemplazable `_medir() -> dict` (psutil: `cpu_percent(interval=1.0)`, `virtual_memory()`, `disk_usage("C:\\")`, `psutil.disk_io_counters()` con una ventana de 1 s para el % de ocupación (si no existe → `None`), los 5 procesos con más CPU y los 5 con más RAM (`process_iter` con `oneshot`, ignorando procesos inaccesibles), `equipo.leer_hechos()["disco_sistema_tipo"]` y `inicio.diagnosticar()["datos"]["total"]` si responde).
- **Causas, en orden de prioridad (id → condición → texto):** `ram` → `ram_uso >= 90` ("La memoria RAM está casi llena: X %"); `espacio` → `disco_c_libre_pct < 10` ("Queda poco espacio libre en el disco C:"); `disco_lento` → `disco_tipo == "hdd"` y `disco_ocupado_pct >= 90` ("El disco duro está trabajando al máximo; los discos mecánicos son más lentos que los SSD"); `cpu` → `cpu_uso >= 90` y existe un proceso con `cpu >= 50` ("El procesador está muy ocupado por <proceso>"); `inicio` → `inicio_total >= 10` ("Muchos programas arrancan al encender el equipo: N"); cada causa lleva `evidencia` con los números medidos, nunca texto sin dato. Estado: `advertencia` si hay ≥ 1 causa (el mensaje nombra la **primera** como causa principal y cuántas más hay), `normal` si no hay ninguna ("En esta medición no se encontró nada que explique lentitud"), `no_determinado` si `medicion_valida` es falso (no se pudo leer RAM ni CPU). `datos = {"causas": [...], "medicion": {...}, "procesos_cpu": [...], "procesos_ram": [...]}`. El texto del módulo aclara que es una foto del momento.
- [ ] **Step 1: Escribir `test_analisis_rendimiento()`**: (a) `_causas` con `ram_uso=93` → primera causa `id == "ram"` y su evidencia contiene `"93"`; con `ram_uso=50` y `disco_c_libre_pct=8` → `espacio`; con HDD y ocupación 95 → `disco_lento`, con SSD y ocupación 95 → **no** `disco_lento`; con `cpu_uso=95` y un proceso al 60 % → `cpu` con el nombre del proceso en la evidencia, y sin proceso ≥ 50 % → no `cpu`; `inicio_total=12` → `inicio`; todo sano → `[]`; datos `None` en un campo → esa causa no se evalúa (no se afirma nada por dato ausente); (b) orden de prioridad con varias causas: `ram` antes que `espacio` antes que `disco_lento`; (c) `_clasificar([], True)[0] == "normal"`, `_clasificar([causa], True)[0] == "advertencia"`, `_clasificar([], False)[0] == "no_determinado"`; (d) `diagnosticar()` con `_medir` simulado devuelve el contrato de 5 llaves y `datos["causas"]` coherente; `_medir` lanzando → `no_determinado` sin excepción; (e) Review Focus 1: proceso llamado `"<b>x</b>"` se conserva en `datos` sin romper; (f) llamada real: contrato válido, ≤ 8 s. Registrar.
- [ ] **Step 2: Correr y ver que falla; Step 3: implementar**; **Step 4: `python test_scanner.py`**. Checkpoint.

### Task 6: `scanner.ejecutar_analisis()`, `/api/analisis`, reporte de texto e informe

**Files:**
- Modify: `backend/scanner.py`, `backend/app.py`, `backend/utils.py` (`generar_reporte_texto`), `backend/informe.py`
- Test: `backend/test_scanner.py`

**Interfaces:**
- Consumes: `scanner.ANALISIS`, los 4 módulos `analisis.*` (cada `diagnosticar()`), `explicador.guia_para`, `explicador.NOMBRES_ANALISIS`.
- Produces: `scanner.ejecutar_analisis() -> dict` → `{"timestamp": str, "analisis": {nombre: resultado_con_guia}, "resumen": {estado: n}, "tiempos": {nombre: s, "total": s}}`; cada módulo se importa de forma dinámica como `_escanear_componente` (módulo faltante, excepción o contrato incumplido → `no_determinado` con `guia`), reutilizando la misma lógica de `_con_guia`; `GET /api/analisis` → JSON de lo anterior y guarda `_ultimo_analisis`; `GET /api/informe` incluye, si hay `_ultimo_analisis`, la sección **"Análisis de Windows"** (una tarjeta por análisis con nombre, estado, mensaje, `guia.que_significa`, pasos, y listas acotadas: para `inicio` las entradas, para `programas` los ocultos y los `recientes_sin_editor`, para `rendimiento` las causas con su evidencia y los procesos, para `espacio` las carpetas; todo escapado y con tope de 30 filas por lista y la línea "y N más"), **después** de las recomendaciones; el reporte de texto agrega la sección `--- ANÁLISIS DE WINDOWS ---` con el mismo contenido resumido. Sin análisis todo se omite (nunca 500; Review Focus 5). `GET /api/guias` suma la llave `"_nombres_analisis"` (= `explicador.NOMBRES_ANALISIS`) y su prueba existente se ajusta (la respuesta tiene los 11 componentes, `_veredictos` y `_nombres_analisis`). Exceptions en `/api/analisis` → JSON 500 como las otras rutas y `_ultimo_analisis` no se pisa si `jsonify` falla.
- [ ] **Step 1: Escribir los tests** `test_ejecutar_analisis()`, `test_api_analisis()` e `test_informe_analisis()`: (a) con los 4 módulos reemplazados por falsos (uno de ellos lanzando, otro sin respetar el contrato) `ejecutar_analisis()` devuelve las 4 llaves en `analisis`, cada una con `guia`, los defectuosos como `no_determinado`, y `tiempos["total"]`; el `resumen` suma 4; (b) `GET /api/analisis` (cliente en hilo) → 200 y JSON con `analisis`; con `jsonify` fallando por un objeto no serializable → 500 y `_ultimo_analisis` intacto; (c) `GET /api/informe` con `_ultimo_analisis` simulado que contiene un programa `"<script>alert(1)</script>"` y un proceso `"A & B"` → el HTML contiene `&lt;script&gt;` y `A &amp; B`, no la etiqueta cruda; con 80 programas ocultos → máximo 30 filas y la frase `"y 50 más"`; sin `_ultimo_analisis` → no hay sección "Análisis de Windows" y la respuesta es 200; (d) `generar_reporte_texto` con y sin análisis (la sección aparece o no, sin lanzar con campos corruptos). Restaurar originales y `_ultimo_analisis` en `finally`. Registrar.
- [ ] **Step 2: Correr y ver que falla; Step 3: implementar**; **Step 4: `python test_scanner.py`** → pasa, stderr limpio. Checkpoint.

### Task 7: Interfaz: botón "Analizar mi Windows" y sección de análisis

**Files:**
- Modify: `frontend/templates/index.html`, `frontend/static/js/app.js`, `frontend/static/css/style.css`, `docs/reglas-recomendaciones.md`, `docs/DECISIONES.md` (decisión 38)

**Interfaces:**
- Consumes: `GET /api/analisis` (Tarea 6), `GET /api/guias` (ya existe; incluye los 4 análisis tras la Tarea 1), `explicador.NOMBRES_ANALISIS` (se agrega al JSON de `/api/guias` bajo `"_nombres_analisis"` — ajustar la ruta y su prueba en la Tarea 6: la respuesta suma esa llave).
- Produces: botón secundario **"Analizar mi Windows (¿por qué va lento?)"** visible en modo simple y técnico **solo cuando ya hay un escaneo real** (no en estado vacío ni en demostración); al pulsarlo se deshabilita mientras corre (barra de progreso existente) y al terminar aparece la sección "Análisis de Windows" debajo de las recomendaciones: una tarjeta por análisis con las clases de las tarjetas simples (nombre, chip de estado, `mensaje`, `que_significa`, `que_hacer`, etiquetas `quien`/urgencia) y, dentro de cada una, listas plegables con `<details><summary>` (`inicio`: entradas; `programas`: ocultos y recientes sin editor, y "ver los N programas" si hay lista; `rendimiento`: causas con su evidencia y procesos con más CPU/RAM; `espacio`: carpetas y tamaño) construidas con `crear()`/`textContent` y topes de 30 filas ("y N más"); una línea fija bajo el título: "Es una foto del momento, solo lee información y no cambia nada en tu equipo."; en modo técnico, la misma sección. Un análisis nuevo reemplaza al anterior; un escaneo de hardware nuevo **no** borra el análisis; el modo demostración y el estado vacío no muestran la sección (Review Focus 5). Errores de red → aviso existente. Decisión 38 en `DECISIONES.md`.
- [ ] **Step 1: Implementar** (HTML contenedores, JS de petición/render/estado, CSS mínimo con variables y clases existentes; `overflow-wrap: anywhere`; sin `!important`).
- [ ] **Step 2: Verificación automática**: `node --check frontend/static/js/app.js` (si hay node), `python test_scanner.py` limpio, y con un servidor propio (`python backend\lanzador.py --sin-navegador`, matar solo por PID): `GET /api/analisis` 200 con los 4 análisis, `GET /api/guias` incluye `_nombres_analisis`, `GET /api/informe` incluye "Análisis de Windows" tras el análisis. Anotar los tiempos reales de cada módulo.
- [ ] **Step 3: Verificación visual** (controlador, navegador integrado): escaneo real → botón → sección con las 4 tarjetas y listas plegables; modo simple y técnico; estado vacío y demostración sin sección; ventana angosta (~700 px); informe con la sección. Checkpoint.

---

## Self-review

- **Cobertura de la spec §5.3 (F4a):** `programas` (registro + `shell:AppsFolder` vía `Get-StartApps`, ocultos, recientes, editor desconocido) → T4; `inicio` (Run, carpetas Inicio, servicios automáticos; tareas programadas al iniciar sesión **quedan para F4b**) → T3; `rendimiento` (causa principal con evidencia) → T5; `espacio` (temporales, papelera, descargas, solo informa) → T2; textos claros y guía → T1; informe y reporte → T6; interfaz → T7. Las vistas técnicas tipo HWiNFO/CrystalDiskInfo/GMER-lite quedan para el plan de F4b.
- **Decisión de diseño:** los análisis no entran en `COMPONENTES` (no alteran veredicto, cobertura, mapa ni los "7 componentes" del proyecto) y se piden aparte; si el equipo prefiere integrarlos al escaneo principal, es un cambio posterior pequeño (mover los nombres a `COMPONENTES`).
- **Consistencia de tipos:** `diagnosticar()`/`_clasificar()`/lectores por módulo, `scanner.ANALISIS`, `explicador.NOMBRES_ANALISIS`, `ejecutar_analisis()` y las claves de `/api/analisis` coinciden entre tareas.
- **Honestidad:** umbrales documentados; ninguna causa sin evidencia medida; `programas` nunca afirma que algo sea dañino, solo que conviene reconocerlo.
