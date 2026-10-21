# F0 + F1: Cimientos y app portable — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dejar el backend sólido y seguro para correr en un Windows normal, y que la app se abra desde el USB con doble clic (pidiendo administrador) en una ventana propia, sin escribir URLs a mano.

**Architecture:** Un único lector de sensores LibreHardwareMonitor (`modules/_lhm.py`) alimenta a `cpu`, `gpu` y `fuente_poder` (hoy abren la librería 3 veces por escaneo). Un lanzador en Python (`backend/lanzador.py`) elige puerto libre, levanta Flask solo en `127.0.0.1`, abre Edge/Chrome en modo app y se apaga solo cuando la ventana deja de hacer ping a `/api/status`. Un `.bat` solo se encarga de pedir administrador y llamar al lanzador. El modo WinPE (`build/overlay-winpe/iniciar.bat`) sigue funcionando sin cambios.

**Tech Stack:** Python 3.12 (embeddable en el USB), Flask 3, psutil, wmi, pythonnet, LibreHardwareMonitorLib 0.9.6, JS vanilla. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-10-21-version-portable-no-tecnicos-design.md` (secciones 4, 6, 7 y 10)

## Global Constraints

- Sin frameworks JS y sin dependencias nuevas de Python (regla del README). `pywin32` ya llega por `wmi`; declararlo no es una dependencia nueva.
- El contrato de módulos de 5 llaves (`componente, estado, mensaje, datos, recomendacion`) **no cambia**.
- Ningún dato inventado: sensor ausente → `None` / `no_determinado`.
- El servidor escucha solo en `127.0.0.1` (decisión D5).
- La app debe seguir abriendo sin permisos de administrador; lo que no pueda leer lo marca `no_determinado`.
- Windows 10 (1809+) y 11, 64 bits. Evitar APIs solo-Win11. Equipo de pruebas disponible: la laptop de José Alejandro (Windows 11 Pro).
- El modo WinPE sigue usando `http://localhost:5000`: `DSPC_PORT` por defecto 5000.
- Toda decisión nueva va a `docs/DECISIONES.md` (solo se agrega, fecha incluida).
- Pruebas: `python test_scanner.py` desde `backend/` (estilo `assert`, sin pytest). Cada tarea termina con ese archivo pasando completo.
- "Checkpoint" = `git commit` si el equipo aprueba `git init` (Tarea 1); si no, copia comprimida de `diagnostic_scanner_pc\` fuera de la carpeta del proyecto.

## Review Focus

Entradas y condiciones que la spec implica pero ninguna tarea del flujo feliz prueba; cada una tiene su prueba en la tarea indicada.

1. Ventana minimizada o en segundo plano más de 5 min (Chromium frena los temporizadores a ~1 por minuto): la app **no** debe apagarse sola. → Tarea 7.
2. Sin Edge ni Chrome instalados: debe abrir el navegador predeterminado, no fallar. → Tarea 7.
3. Puerto 5000 ocupado (otra app, o una segunda copia del escáner): elegir otro puerto libre, sin excepción. → Tarea 5.
4. Usuario rechaza el aviso de administrador, o Defender bloquea el driver de sensores: la app abre, `cpu`/`fuente_poder` degradan a `no_determinado` y el resto sigue. → Tareas 4 y 8.
5. Ruta del USB con espacios y caracteres no ASCII (por ejemplo `E:\Mi USB ñandú\`): el `.bat` y el lanzador deben funcionar. → Tarea 8 (verificación manual) y Tarea 9.

---

### Task 1: Línea base de pruebas y decisiones 27–29

**Files:**
- Modify: `docs/DECISIONES.md` (agregar al final)
- Modify: `README.md` (sección "Cómo ejecutarlo": una línea que apunta al modo portable, se completa en Tarea 8)

**Interfaces:**
- Produces: la decisión **27** (pivote a app portable; Edge en modo app; ISO de Hiren's queda como modo rescate; `127.0.0.1`), **28** (capa de lenguaje claro aditiva, contrato de 5 llaves intacto; implementación en F2) y **29** (registro opt-in en SQLite, enmienda a la 4; implementación en F5). Las tareas siguientes citan "decisión 27".

- [ ] **Step 1: Averiguar con qué Python corren las pruebas.** Probar `python -c "import flask, wmi, psutil, pythoncom, clr"` en la laptop; si falla, usar el Python portable del USB con el wrapper `-c "import sys; sys.path.insert(0, r'...\backend'); exec(open(r'...\backend\test_scanner.py').read())"` (el embeddable ignora el directorio del script). Anotar en el plan, bajo este paso, el comando exacto que funciona.
- [ ] **Step 2: Correr `python test_scanner.py` y confirmar que imprime `todos los casos OK`** (línea base; si no pasa, parar y avisar).
- [ ] **Step 3: Pedir al equipo la aprobación de `git init`** en `diagnostic_scanner_pc\` (no hay repo y ya hubo dos reformateos). Si la dan: `git init`, `.gitignore` con `build/python-portable/`, `build/chromium/`, `*.iso`, `__pycache__/`, y primer commit "baseline antes de F0". Si no, usar copias zip como Checkpoint.
- [ ] **Step 4: Agregar las decisiones 27, 28 y 29 a `docs/DECISIONES.md`** con el mismo formato de las existentes (título numerado, `**Fecha:** 2026-10-21`, contexto, decisión, motivo). La 27 menciona que el autoarranque del modo rescate **no funcionó** en el USB de 16 GB (hubo que abrir `iniciar.bat` y escribir la URL a mano), lo que reemplaza el "decisión 27 pendiente" de memoria.
- [ ] **Step 5: Verificar** con `grep -n "^## 2[789]\." docs/DECISIONES.md` → 3 líneas. Checkpoint.

### Task 2: Archivar código obsoleto de Alpine/Debian

**Files:**
- Move to `_archivo_obsoleto/` (nueva carpeta en la raíz del proyecto): `scripts/check_environment.sh`, `scripts/install_tools.sh`, `build/create_iso.sh`, `build/overlay/`, `.claude/settings.local.json`
- Modify: `README.md` si menciona alguno de esos archivos

**Interfaces:**
- Produces: árbol sin código muerto; nada se borra (el equipo no tiene control de versiones, se **mueve**, no se elimina).

- [ ] **Step 1: `grep -rn "check_environment\|install_tools\|create_iso.sh\|build/overlay/" --include=*.py --include=*.md --include=*.ps1 --include=*.bat .`** y confirmar que ningún archivo vivo los usa (solo `docs/DECISIONES*.md`, que es histórico y no se edita).
- [ ] **Step 2: Mover los archivos** a `_archivo_obsoleto/` conservando subcarpetas; agregar `_archivo_obsoleto/LEEME.txt` con una línea: "Código de las bases Alpine/Debian descartadas (decisiones 11–15). No se usa."
- [ ] **Step 3: Correr `python test_scanner.py`** → `todos los casos OK`. Checkpoint.

### Task 3: Aislar excepciones de `gpu.py`

**Files:**
- Modify: `backend/modules/gpu.py` (`obtener_datos`)
- Test: `backend/test_scanner.py`

**Interfaces:**
- Produces: `gpu.obtener_datos() -> dict` **nunca lanza**, aunque `_identidad()` o `_telemetria()` lancen cualquier `Exception`; devuelve el mismo dict de 4 llaves con `None` en lo que falló.

- [ ] **Step 1: Escribir `test_gpu_aislamiento()`** en `test_scanner.py`: con `gpu._identidad` reemplazado por una función que lanza `RuntimeError("boom")`, `gpu.obtener_datos()` devuelve `{"nombre": None, "driver": None, ...}` sin excepción; con `gpu._telemetria` lanzando, `temperatura_c` y `porcentaje_uso` son `None` pero `nombre`/`driver` conservan su valor. Restaurar los originales en `finally`. Registrarla en el bloque `__main__`.
- [ ] **Step 2: Correr y ver que falla** (`RuntimeError` propagado).
- [ ] **Step 3: Implementar:** en `obtener_datos`, envolver cada llamada (`_identidad`, `_telemetria`) en su propio `try/except Exception` con el valor de respaldo `None`; el docstring ya promete "nunca lanza".
- [ ] **Step 4: Correr `python test_scanner.py`** → pasa. Checkpoint.

### Task 4: Lector único de sensores LibreHardwareMonitor

**Files:**
- Create: `backend/modules/_lhm.py`
- Modify: `backend/modules/cpu.py` (`_obtener_ventiladores`), `backend/modules/gpu.py` (`_telemetria`), `backend/modules/fuente_poder.py` (`diagnosticar`, `_leer_voltajes`), `backend/scanner.py` (`ejecutar_escaneo_completo`)
- Test: `backend/test_scanner.py`

**Interfaces:**
- Produces, en `modules/_lhm.py`:
  - `leer_sensores(lector=None) -> list[dict]` — cada sensor es `{"tipo_hardware": str, "hardware": str, "tipo": str, "nombre": str, "valor": float | None}` (`tipo` = `str(SensorType)`, p. ej. `"Fan"`, `"Temperature"`, `"Voltage"`, `"Load"`; los sub-hardware se aplanan y heredan el `tipo_hardware` de su padre). Abre la librería **una sola vez**, con Cpu, Gpu y Motherboard habilitados (sin Memory, ver el comentario existente en `fuente_poder._leer_voltajes`), y guarda el resultado en caché del proceso. Nunca lanza: ante cualquier fallo devuelve `[]` y registra el mensaje. `lector` es un callable sin argumentos que reemplaza la lectura real (para pruebas).
  - `error_carga() -> str | None` — mensaje del último fallo de carga/lectura, o `None`.
  - `invalidar() -> None` — borra la caché y el error.
  - `filtrar(sensores: list[dict], tipo: str, hardware_contiene: str | None = None) -> list[dict]` — por `tipo` exacto y, si se da, subcadena en `tipo_hardware`.
- `scanner.ejecutar_escaneo_completo` llama `_lhm.invalidar()` al empezar cada escaneo.

- [ ] **Step 1: Escribir `test_lhm()`** en `test_scanner.py` con estos casos: (a) con un `lector` falso que cuenta llamadas, dos `leer_sensores(lector=falso)` seguidos invocan el lector **1** vez, y tras `invalidar()` una tercera lo invoca **2** veces en total; (b) `filtrar` con `tipo="Fan"` devuelve solo ventiladores y con `hardware_contiene="Gpu"` solo los de GPU; (c) un `lector` que lanza `RuntimeError("driver bloqueado")` hace que `leer_sensores` devuelva `[]` y `error_carga()` contenga `"driver bloqueado"`. Agregar `test_fuente_poder_sin_sensores()`: con `_lhm` sin sensores y un `error_carga` simulado, `fuente_poder.diagnosticar()["estado"] == "no_determinado"` y el mensaje incluye el error (Review Focus 4). Registrar ambas en `__main__`.
- [ ] **Step 2: Correr y ver que falla** (módulo `_lhm` inexistente).
- [ ] **Step 3: Implementar `modules/_lhm.py`.** La lectura real es el único código no testeable: mover aquí el bloque `import clr … Computer() … Open() … Close()` de los tres módulos, con `Update()` por hardware y sub-hardware, sin lógica de selección. Mantener el `sys.path.append(_LIB_DIR)` de los módulos actuales.
- [ ] **Step 4: Migrar los tres módulos** para consumir `_lhm`: `cpu._obtener_ventiladores` → `filtrar(..., "Fan")` → `[{"nombre", "rpm"}]` (misma forma de salida de hoy); `gpu._telemetria` → `_elegir_temperatura` y `_elegir_uso` con los valores de `filtrar(..., "Temperature"/"Load", "Gpu")` (las funciones `_elegir_*` y sus pruebas existentes no cambian); `fuente_poder.diagnosticar` → rieles desde `filtrar(..., "Voltage")` con `{"origen", "sensor", "voltios"}`; si no hay sensores y `error_carga()` no es `None`, `_resultado_error(f"No se pudo cargar LibreHardwareMonitorLib: {error}")`; si no hay error, el mensaje actual "No se encontró ningún sensor de voltaje…".
- [ ] **Step 5: Correr `python test_scanner.py`** → pasa.
- [ ] **Step 6: Medir el beneficio en hardware real.** Antes de migrar (con el código anterior, en un stash o copia) y después, correr `python -c "import scanner; print(scanner.ejecutar_escaneo_completo()['tiempos'])"` desde `backend/` y anotar `total`, `cpu` y `fuente_poder`. Esperado: `total` menor o igual y los mismos estados por componente. Si algún estado cambia, parar y revisar. Checkpoint.

### Task 5: Ayudas de `utils.py`: puerto libre, entorno y administrador

**Files:**
- Modify: `backend/utils.py`
- Test: `backend/test_scanner.py`

**Interfaces:**
- Produces, en `utils.py`:
  - `puerto_libre(preferido: int = 5000) -> int` — `preferido` si se puede enlazar en `127.0.0.1`; si no, un puerto libre asignado por el sistema.
  - `es_winpe(minint_existe: bool, unidad_sistema: str) -> bool` — `True` si `minint_existe` o `unidad_sistema.upper().startswith("X:")`.
  - `detectar_entorno() -> str` — `"winpe"` o `"windows"`; lee la clave `HKLM\SYSTEM\CurrentControlSet\Control\MiniNT` con `winreg` y la variable `SystemDrive`, y delega en `es_winpe`.
  - `es_administrador() -> bool` — `ctypes.windll.shell32.IsUserAnAdmin()`; `False` ante cualquier excepción.

- [ ] **Step 1: Escribir `test_utils_entorno()`**: `es_winpe(True, "C:") is True`, `es_winpe(False, "x:") is True`, `es_winpe(False, "C:") is False`; `detectar_entorno() in {"winpe", "windows"}`; `isinstance(utils.es_administrador(), bool)`; y el caso de Review Focus 3: ocupar un puerto con un `socket` enlazado a `127.0.0.1` y comprobar que `utils.puerto_libre(ese_puerto)` devuelve un puerto **distinto** y mayor que 0, mientras que con un puerto libre devuelve el mismo. Registrar en `__main__`.
- [ ] **Step 2: Correr y ver que falla.**
- [ ] **Step 3: Implementar las cuatro funciones** en `utils.py` (`puerto_libre` con `socket.bind(("127.0.0.1", p))`, y en caso de `OSError` `bind(("127.0.0.1", 0))`).
- [ ] **Step 4: Correr `python test_scanner.py`** → pasa. Checkpoint.

### Task 6: `app.py` seguro y robusto

**Files:**
- Modify: `backend/app.py`, `backend/requirements.txt`
- Test: `backend/test_scanner.py`

**Interfaces:**
- Consumes: `utils.detectar_entorno()`, `utils.es_administrador()` (Tarea 5).
- Produces: constante `app.HOST = "127.0.0.1"`; `GET /api/status` agrega las llaves `entorno: str` y `administrador: bool`; `GET /api/reporte` devuelve JSON 500 `{"estado": "error", "mensaje": …}` si falla; `/api/scan` solo guarda `_ultimo_escaneo` si la respuesta se pudo serializar.

- [ ] **Step 1: Escribir `test_app_rutas()`** con `app.app.test_client()`: (a) `app.HOST == "127.0.0.1"`; (b) `GET /api/status` → 200 y el JSON contiene `entorno` y `administrador` (bool); (c) con `scanner.ejecutar_escaneo_completo` reemplazado por una función que devuelve `{"x": object()}`, `GET /api/scan` → 500 y `app._ultimo_escaneo is None`; (d) con `utils.generar_reporte_texto` reemplazado por una función que lanza, `GET /api/reporte` → 500 con `application/json`. Restaurar los originales en `finally`. Registrar en `__main__`.
- [ ] **Step 2: Correr y ver que falla.**
- [ ] **Step 3: Implementar en `app.py`:** definir `HOST`; en `api_scan` armar `respuesta = jsonify(resultado)` antes de asignar `_ultimo_escaneo`; envolver `api_reporte` en `try/except Exception`; ampliar `api_status`; el bloque `__main__` pasa a `app.run(host=HOST, port=int(os.environ.get("DSPC_PORT", 5000)), debug=False, threaded=True)`. Agregar `pywin32>=306` a `requirements.txt` con un comentario de que `app.py` importa `pythoncom` (ya llegaba por `wmi`).
- [ ] **Step 4: Correr `python test_scanner.py`** → pasa. Checkpoint.

### Task 7: Lanzador `backend/lanzador.py`

**Files:**
- Create: `backend/lanzador.py`
- Test: `backend/test_scanner.py`

**Interfaces:**
- Consumes: `app.app`, `app.HOST`, `utils.puerto_libre`.
- Produces:
  - `elegir_navegador(variables: Mapping[str, str], existe=os.path.exists) -> str | None` — primer `.exe` existente en este orden: Edge en `ProgramFiles(x86)` y `ProgramFiles`, luego Chrome en `ProgramFiles`, `ProgramFiles(x86)` y `LocalAppData`; `None` si no hay ninguno.
  - `comando_app(exe: str, url: str, perfil: str) -> list[str]` — `[exe, "--app=<url>", "--user-data-dir=<perfil>", "--no-first-run", "--window-size=1280,800"]` (el perfil propio fuerza una instancia nueva, así Edge no delega en un proceso ya abierto).
  - `debe_apagar(ahora: float, ultimo_latido: float | None, inicio: float, tolerancia_s: float = 150.0, gracia_inicial_s: float = 60.0) -> bool` — sin ningún latido todavía: apagar si `ahora - inicio > gracia_inicial_s`; con latido: apagar si `ahora - ultimo_latido > tolerancia_s`. (150 s por la limitación de temporizadores de Chromium en ventanas ocultas.)
  - `main() -> int` — elige puerto (`puerto_libre(5000)`), levanta Flask con `werkzeug.serving.make_server(HOST, puerto, app, threaded=True)` en un hilo, registra un `after_request` que marca el latido cuando `request.path == "/api/status"`, espera a que `/api/status` responda (hasta 30 s), abre el navegador (`subprocess.Popen(comando_app(...))` con perfil en una carpeta temporal, o `webbrowser.open(url)` si `elegir_navegador` devuelve `None`), vigila `debe_apagar` cada segundo y llama `servidor.shutdown()` al terminar.
- El archivo inserta `BASE_DIR` en `sys.path` al inicio, igual que `app.py` (el Python embeddable ignora la carpeta del script).

- [ ] **Step 1: Escribir `test_lanzador()`**: (a) `elegir_navegador` con `existe` simulado: solo Edge en `ProgramFiles(x86)` → esa ruta; solo Chrome en `LocalAppData` → esa ruta; ninguno → `None` (Review Focus 2); Edge y Chrome presentes → Edge; (b) `comando_app("C:\\e.exe", "http://127.0.0.1:5000", "C:\\tmp\\p")` contiene `"--app=http://127.0.0.1:5000"` y `"--user-data-dir=C:\\tmp\\p"`; (c) `debe_apagar` (Review Focus 1): sin latido y 10 s desde el inicio → `False`; sin latido y 61 s → `True`; latido hace 100 s (ventana minimizada, temporizadores frenados) → `False`; latido hace 151 s → `True`. Registrar en `__main__`.
- [ ] **Step 2: Correr y ver que falla.**
- [ ] **Step 3: Implementar `lanzador.py`** con las firmas de arriba; `if __name__ == "__main__": sys.exit(main())`.
- [ ] **Step 4: Correr `python test_scanner.py`** → pasa.
- [ ] **Step 5: Prueba de humo a mano** en la laptop: `python backend\lanzador.py` → se abre una ventana de la app sin barra de direcciones, el panel carga, el escaneo funciona; cerrar la ventana y comprobar que en ≤ ~2,5 min la consola termina sola. Anotar el resultado. Checkpoint.

### Task 8: Lanzador `.bat` con administrador y aviso en la interfaz

**Files:**
- Create: `Iniciar_Diagnostic_Scanner.bat` (raíz del proyecto; el mismo archivo se copia a la raíz del USB)
- Modify: `frontend/templates/index.html`, `frontend/static/js/app.js` (`actualizarStatus`), `frontend/static/css/style.css`, `README.md`

**Interfaces:**
- Consumes: `/api/status` con `administrador` y `entorno` (Tarea 6).

- [ ] **Step 1: Escribir el `.bat`.** Comportamiento: (1) si no es administrador (`net session >nul 2>&1`) y no recibió el argumento `elevado`, relanzarse con `powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevado' -Verb RunAs -ErrorAction Stop"`; si PowerShell devuelve error (el usuario rechazó) continuar **sin** administrador en vez de salir; (2) detectar el diseño: si existe `%~dp0diagnostic_scanner_pc\backend\lanzador.py` es el USB (`python-portable\python.exe`), si existe `%~dp0backend\lanzador.py` es desarrollo (`python` del PATH); si falta el Python o el lanzador, mostrar un mensaje claro en español con la ruta que buscó y `pause`; (3) ejecutar `"%PYTHON%" "%LANZADOR%"`. Todas las rutas entre comillas y `%~dp0` tal cual (Review Focus 5). Comentarios en español como el resto de los `.bat`.
- [ ] **Step 2: Aviso en la interfaz.** En `index.html`, agregar `<div class="aviso-demo" id="aviso-admin">` (reusar el estilo de `aviso-demo` en `style.css`) con el texto "Sin permisos de administrador: algunos sensores (temperaturas, voltajes, S.M.A.R.T.) no se podrán leer. Cierra y abre de nuevo aceptando el aviso de Windows."; en `actualizarStatus`, mostrarlo cuando `datos.administrador === false` y `datos.entorno === "windows"`, ocultarlo en cualquier otro caso. No tocar el resto del JS.
- [ ] **Step 3: Verificación manual en la laptop, con ruta difícil.** Copiar el proyecto a `C:\Prueba ñandú\diagnostic_scanner_pc\` y el `.bat` a `C:\Prueba ñandú\`; ejecutar: (a) aceptar el aviso de Windows → abre sin el banner naranja y `cpu`/`fuente_poder` muestran sensores; (b) rechazar el aviso → abre con el banner y el escaneo termina sin error (algunos `no_determinado`). Registrar ambos resultados. Borrar `C:\Prueba ñandú\` al terminar.
- [ ] **Step 4: En `README.md`**, agregar la sección "Modo portable (recomendado)" que explica el doble clic y el aviso de administrador. Checkpoint.

### Task 9: Despliegue en el USB de 16 GB y verificación

**Files:**
- Modify (en el USB, no en el proyecto): `<USB>:\diagnostic_scanner_pc\` (sincronizar), `<USB>:\Iniciar_Diagnostic_Scanner.bat` (copiar a la raíz)

**Interfaces:**
- Consumes: todo lo anterior. Diseño final del USB: raíz con `Iniciar_Diagnostic_Scanner.bat`, `diagnostic_scanner_pc\`, `python-portable\`, y lo existente (`iniciar.bat`, `fondo.jpg`, ISO, `chromium\`, `registros\`) intacto.

- [ ] **Step 1: Pedir al equipo conectar el USB** y confirmar la letra de unidad. Revisar que `iniciar.bat`, `fondo.jpg`, `diagnostic_scanner_pc\` y `python-portable\` estén en la raíz (lección del 15-sep).
- [ ] **Step 2: Sincronizar** `backend\`, `frontend\`, `config\` (y `Iniciar_Diagnostic_Scanner.bat` a la raíz) con `robocopy` sin `/MIR` en la raíz del USB (para no borrar nada que el proyecto no conoce); no tocar `HBCD_PE.ini` ni la ISO.
- [ ] **Step 3: Comparar** que los `.py`, `.js`, `.html` y `.css` del USB sean idénticos a los del proyecto (`fc` o hash).
- [ ] **Step 4: Ejecutar `Iniciar_Diagnostic_Scanner.bat` desde el USB** en la laptop: aceptar administrador, hacer un escaneo, bajar el reporte. Confirmar que **no** se abrió ningún navegador con `localhost:5000` escrito a mano y que el reporte se descarga.
- [ ] **Step 5: Probar con Defender activo** (el estado normal de la laptop): ¿Defender bloquea el driver de sensores? Registrar sí/no y el texto exacto de cualquier alerta. Esto confirma o descarta la suposición sobre LHM 0.9.6 y el driver de sensores.
- [ ] **Step 6: Anotar en `docs/DECISIONES.md`** (decisión 30) lo medido: tiempo de escaneo antes/después, comportamiento con Defender y con/sin administrador. Checkpoint.

### Task 10: Investigar el autoarranque del modo rescate (solo diagnóstico)

**Files:**
- Modify: `docs/DECISIONES.md` (decisión 31 con los hallazgos)

**Interfaces:**
- Produces: un diagnóstico escrito; **no** incluye arreglo. El arreglo se planifica aparte con ese diagnóstico.

- [ ] **Step 1: Con el USB conectado, listar la raíz y la carpeta de la ISO** y comprobar que `diagnostic-scanner-pc-pe.iso` es la ISO construida (3,1 GB) y no la original de Hiren's (3,3 GB).
- [ ] **Step 2: Montar la ISO** y leer `HBCD_PE.ini`: ¿existe el bloque `_SUB ExtPrograms` con el bucle `EXEC` por las letras D–W que llaman `iniciar.bat`? ¿Conserva la fecha de modificación original (decisión 24)?
- [ ] **Step 3: Comparar contra la letra real que usa Ventoy** para la partición de datos en un arranque del USB de 16 GB (preguntar al equipo qué letra mostró el explorador de WinPE) y contra `iniciar.bat` en la raíz.
- [ ] **Step 4: Escribir los hallazgos** (causa probable o "no concluyente, falta una prueba de arranque con tal dato") en la decisión 31. Checkpoint.

---

## Self-review

- **Cobertura de la spec (F0 y F1):** decisiones 27–29 (T1) · `127.0.0.1` (T6) · aislar `gpu.py` (T3) · LHM una sola vez (T4) · `/api/reporte` robusto (T6) · `pythoncom`/`pywin32` en requirements (T6) · código muerto (T2) · `threaded=True` explícito (T6) · lanzador con elevación, Edge en modo app, detección de entorno, aviso sin administrador (T5, T7, T8) · estructura del USB y prueba en Windows real (T9) · deuda del modo rescate (T10). Lo de `DATOS_MOCK` y el voseo de la interfaz queda para F2 a propósito.
- **Consistencia de tipos:** `leer_sensores`/`filtrar`/`error_carga`/`invalidar` (T4), `puerto_libre`/`es_winpe`/`detectar_entorno`/`es_administrador` (T5), `app.HOST` (T6) y `elegir_navegador`/`comando_app`/`debe_apagar`/`main` (T7) se usan con las mismas firmas donde se consumen.
- **Proporción:** solo las pruebas llevan aserciones concretas; el código de producción queda descrito por firma, salvo la lectura real de LHM, que es movimiento de código existente.
