# F3: Recomendador — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la app diga, con base en lo medido en el equipo, qué sistema operativo conviene ("según tus componentes te recomendamos…"), qué mejoras de hardware valen la pena y cómo cuidar la batería y el disco, mostrando siempre en qué dato se basa cada consejo.

**Architecture:** `backend/equipo.py` lee los datos del sistema que hoy no se leen (tipo de disco, firmware UEFI, Secure Boot, TPM, sistema operativo actual) y nunca lanza. `backend/recomendador.py` es una función pura `recomendar(resultado, hechos)` que devuelve una lista de recomendaciones. `scanner.py` agrega al resultado las llaves `hechos` y `recomendaciones` (aditivas; el contrato de 5 llaves de los módulos no cambia). El informe imprimible y la interfaz (modo simple y técnico) las muestran.

**Tech Stack:** Python 3.12, WMI (`wmi`), `winreg` y `ctypes` de la librería estándar, Flask 3, JS vanilla. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-10-21-version-portable-no-tecnicos-design.md` (§3, §5.2, §6 y §10 punto 2: Windows 7 puede aparecer como recomendación cuando el hardware lo requiera, con aviso honesto) y decisiones 28, 33 y 36 de `docs/DECISIONES.md`.

## Global Constraints

- Contrato de módulos de 5 llaves intacto; `scanner._cumple_contrato` no cambia. Las llaves nuevas viven a nivel del resultado del escaneo (`hechos`, `recomendaciones`), no dentro de los módulos.
- Ningún dato inventado: una recomendación solo se genera si el dato en que se basa se pudo leer; cada una lleva `basado_en` no vacío con los valores medidos. Dato ilegible → no se afirma nada ("no se pudo confirmar").
- Sin alarmismo, sin marcas comerciales de hardware, sin precios, sin "garantiza", "limpio", "infectado", "peligro". Los sistemas operativos (Windows 11, Windows 10, Windows 7, Ubuntu, Linux Mint, Lubuntu, MiniOS10) sí se pueden nombrar: es el contenido pedido por el equipo.
- Redacción de la recomendación de S.O. siempre en la forma: "Según tus componentes te recomendamos: …".
- Sin dependencias nuevas; solo lectura (el recomendador no cambia nada en el equipo). Los lectores de `equipo.py` no deben requerir administrador: lo que lo requiera (TPM) degrada a `None`.
- Tuteo, frases cortas, sin jerga sin explicar. Todo texto que viene del escaneo y llega a HTML se escapa (`html.escape` en Python; `textContent` o `escapar()` en JS).
- Pruebas: `cd backend; python test_scanner.py` (ver `docs/superpowers/plans/COMANDO_PRUEBAS.txt`), estilo `assert`, registradas en `__main__`, stderr limpio, solicitudes Flask de prueba con el ayudante `_en_hilo`.
- Decisiones nuevas al final de `docs/DECISIONES.md` (solo se agrega): la 37 cubre el recomendador. Los números 31 y 32 siguen reservados para las pruebas del USB.
- Estados: `normal`, `advertencia`, `sospecha`, `critico`, `no_determinado`. Componentes: `mainboard, cpu, ram, almacenamiento, fuente_poder, bateria, red`.

## Review Focus

1. TPM ilegible sin administrador: la recomendación de Windows 11 debe decir que no se pudo confirmar el TPM, nunca que el equipo "no es compatible". → Tareas 1 y 2.
2. Nombre de procesador desconocido o de una familia que no se sabe clasificar (p. ej. Celeron, Pentium, un nombre vacío): `cpu_apto_windows11` devuelve `None` y no se inventa compatibilidad. → Tarea 1.
3. Equipo de escritorio (batería `aplica: False`) o sin datos de un componente: no hay recomendación de batería ni excepciones; con TODO ausente (modo WinPE o lectores que fallan) `recomendar` devuelve una lista sin romper. → Tarea 2.
4. Dos discos (uno SSD y otro HDD): la recomendación "pasa a SSD" no debe aparecer si el disco de sistema es SSD; si no se puede saber cuál es el de sistema, se explica la limitación. → Tarea 2.
5. Windows 7: solo aparece como última opción, con su aviso de falta de actualizaciones de seguridad, y nunca como opción principal. → Tarea 2.

---

### Task 1: `equipo.py` — datos del sistema que hoy no se leen

**Files:**
- Create: `backend/equipo.py`
- Test: `backend/test_scanner.py`

**Interfaces:**
- Produces, en `backend/equipo.py`:
  - `tipo_disco(media_type: int | None, bus_type: int | None) -> str` — `"ssd"` si `media_type == 4` o `bus_type == 17` (NVMe); `"hdd"` si `media_type == 3`; `"desconocido"` en cualquier otro caso (incluido `None`).
  - `cpu_apto_windows11(nombre: str | None) -> bool | None` — `True`/`False` solo para dos familias reconocibles por el nombre: Intel Core `iN-XXXX…` (la generación es el primer grupo de dígitos antes de los últimos 3: `i5-8250U` → 8, `i7-1165G7` → 11, `i3-10110U` → 10) apto si generación ≥ 8; AMD Ryzen `Ryzen N XXXX` apto si el primer dígito del modelo de 4 cifras es ≥ 2 (`Ryzen 5 1600` → False, `Ryzen 5 3500U` → True, `Ryzen 7 PRO 5850U` → True). Cualquier otro nombre (Celeron, Pentium, Atom, vacío, `None`) → `None`.
  - `leer_hechos() -> dict` — **nunca lanza**. Llaves: `"so"`: `{"nombre": str | None, "build": str | None, "arquitectura": str | None}` (Win32_OperatingSystem); `"firmware"`: `"uefi"` | `"bios"` | `None` (kernel32 `GetFirmwareType`: 1 = BIOS, 2 = UEFI); `"secure_boot"`: `True` | `False` | `None` (registro `HKLM\SYSTEM\CurrentControlSet\Control\SecureBoot\State`, valor `UEFISecureBootEnabled`; clave ausente → `None`); `"tpm_version"`: `"2.0"` | `"1.2"` | `None` (WMI `root/cimv2/Security/MicrosoftTpm`, `Win32_Tpm.SpecVersion`; sin administrador da acceso denegado → `None`); `"discos"`: lista de `{"modelo": str, "tipo": str, "externo": bool, "tamano_gb": float | None}` (WMI `root/Microsoft/Windows/Storage` `MSFT_PhysicalDisk`, `tipo` vía `tipo_disco`; `externo` si `BusType == 7` (USB)); `"disco_sistema_tipo"`: `"ssd"` | `"hdd"` | `"desconocido"` (el tipo del disco que contiene la unidad `C:` si se puede determinar con `MSFT_Partition`/`MSFT_Disk`, si no `"desconocido"`).
- Cada lector es una función privada aparte y `leer_hechos` envuelve cada una en `try/except Exception` con `None` (o `[]`/`"desconocido"`), de modo que un lector que falla no afecta a los otros.

- [ ] **Step 1: Escribir `test_equipo()`** y registrarla en `__main__`. Aserciones: (a) `tipo_disco(4, None) == "ssd"`, `tipo_disco(None, 17) == "ssd"`, `tipo_disco(3, 11) == "hdd"`, `tipo_disco(None, None) == "desconocido"`, `tipo_disco(5, 3) == "desconocido"`; (b) `cpu_apto_windows11`: `"Intel(R) Core(TM) i5-8250U CPU @ 1.60GHz"` → `True`, `"Intel(R) Core(TM) i7-7500U CPU"` → `False`, `"11th Gen Intel(R) Core(TM) i7-1165G7 @ 2.80GHz"` → `True`, `"AMD Ryzen 7 PRO 5850U with Radeon Graphics"` → `True`, `"AMD Ryzen 5 1600 Six-Core Processor"` → `False`, `"AMD Ryzen 5 3500U with Radeon Vega Mobile Gfx"` → `True`, `"Intel(R) Celeron(R) N4020 CPU @ 1.10GHz"` → `None`, `""` → `None`, `None` → `None` (Review Focus 2); (c) `leer_hechos()` con todos los lectores privados reemplazados por funciones que lanzan `RuntimeError` devuelve un dict con las 6 llaves y valores de respaldo (`None`, `[]`, `"desconocido"`), sin excepción (restaurar los lectores en `finally`); (d) con un solo lector roto, los demás conservan su valor; (e) llamada real: `leer_hechos()` devuelve un dict con las 6 llaves y `firmware in {"uefi", "bios", None}` (no se afirma nada del hardware de la máquina de pruebas).
- [ ] **Step 2: Correr `cd backend; python test_scanner.py` y ver que falla** (módulo `equipo` inexistente).
- [ ] **Step 3: Implementar `backend/equipo.py`** con las firmas de arriba. Un comentario de cabecera explica que son datos de apoyo para el recomendador, que ninguno requiere administrador (el TPM degrada a `None`), y que `cpu_apto_windows11` es una heurística por nombre, no una consulta oficial.
- [ ] **Step 4: Correr `python test_scanner.py`** → pasa, stderr limpio. Checkpoint (`git commit`).

### Task 2: `recomendador.py` — las reglas

**Files:**
- Create: `backend/recomendador.py`
- Test: `backend/test_scanner.py`
- Modify: `docs/reglas-recomendaciones.md` (nueva sección "Recomendaciones del equipo (F3)" con la tabla condición → recomendación)

**Interfaces:**
- Consumes: el resultado de un escaneo (`resultado["componentes"][nombre]` con `estado` y `datos`, ver módulos) y `equipo.leer_hechos()` (Tarea 1).
- Produces: `recomendar(resultado: dict | None, hechos: dict | None) -> list[dict]` — nunca lanza, devuelve `[]` si no hay nada que decir. Cada recomendación: `{"id": str, "titulo": str, "detalle": str, "basado_en": list[str], "prioridad": "alta" | "media" | "baja", "quien": "tu_mismo" | "tecnico" | "nadie", "opciones": list[dict]}` donde `opciones` puede ser `[]` y cada opción es `{"nombre": str, "motivo": str, "nota": str}`. Orden de salida: prioridad `alta`, luego `media`, luego `baja`; dentro de cada una, el orden de las reglas de abajo.

**Reglas (cada regla solo se evalúa si sus datos existen; lo que no se pudo leer no se afirma):**

Datos de entrada que se usan: `ram_gb` = `componentes.ram.datos.capacidad_fisica_gb` (si falta, `capacidad_disponible_so_gb`); `ram_uso` = `ram.datos.porcentaje_uso`; `cpu_nombre` = `cpu.datos.nombre`; `arq64` = `True` si `hechos.so.arquitectura` o `cpu.datos.arquitectura` contiene `64` / `x64`, `False` si contiene `32` / `x86`, si no `None`; `apto11` = `equipo.cpu_apto_windows11(cpu_nombre)`.

1. **`so` — Sistema operativo.** Se genera si hay `ram_gb` y `arq64 is not None`. Título "Sistema operativo que conviene a tu equipo". Detalle: "Según tus componentes te recomendamos: <principal>." Opciones ordenadas (la primera es la principal), cada una con `motivo` basado en datos y, cuando aplica, una `nota` honesta:
   - **Windows 11**: solo si `arq64` y `ram_gb >= 4` y `apto11 is True` y `hechos.firmware == "uefi"` y `hechos.secure_boot is not False` y `hechos.tpm_version != "1.2"`. Si `hechos.tpm_version == "2.0"` y `secure_boot is True` → principal con motivo "Tu equipo cumple los requisitos que se pudieron comprobar". Si `tpm_version is None` (no se pudo leer, normalmente por falta de permisos de administrador) → opción presente pero con la nota "No se pudo confirmar el TPM 2.0 (se lee con permisos de administrador); confírmalo antes de instalar" y NO como principal si hay otra opción segura (Review Focus 1). Si `apto11 is False` o `tpm_version == "1.2"` o `secure_boot is False`, Windows 11 no se ofrece, y `basado_en` de la recomendación explica por qué se omitió (p. ej. "Procesador anterior a lo que pide Windows 11").
   - **Windows 10**: si `arq64` y `ram_gb >= 4`. Nota fija: "Windows 10 dejó de recibir actualizaciones de seguridad gratuitas en octubre de 2025; úsalo con cuidado y mantén tus archivos respaldados."
   - **Ubuntu** o **Linux Mint**: si `ram_gb >= 4` (nombre "Ubuntu o Linux Mint"); **Lubuntu o Linux Mint XFCE** si `ram_gb < 4` (equipos modestos).
   - **MiniOS10 (Windows 10 LTSC liviano)**: si `arq64` y `2 <= ram_gb < 4`, o si el disco de sistema es `hdd` y `ram_gb < 8`. Nota: "Es una versión modificada no oficial de Windows 10; instálala con ayuda de un técnico."
   - **Windows 7**: ÚLTIMA opción, solo si `arq64 is False` o `ram_gb < 2`. Nota: "Windows 7 no recibe actualizaciones de seguridad desde 2020. Úsalo solo si tu equipo o tus programas lo exigen, de preferencia sin internet o con mucho cuidado." (Review Focus 5.)
   - Si ninguna opción aplica (datos insuficientes) no se genera la recomendación. `basado_en`: `["RAM: X GB", "Procesador: <nombre>", "Arquitectura: 64 bits"/"32 bits", "Firmware: UEFI"/"BIOS clásica" (si se leyó), "TPM: 2.0"/"no se pudo leer" (si hay opción Windows 11 evaluada), "Disco principal: SSD/HDD" (si se leyó)]` — solo líneas con dato real.
   - `quien`: `"tecnico"` si la principal es MiniOS10, Linux o Windows 7; `"tu_mismo"` en otro caso. `prioridad`: `"baja"` (es una sugerencia, no una falla).
2. **`disco_ssd`** — si `hechos.disco_sistema_tipo == "hdd"`: "Pasa tu disco a un SSD", detalle con el beneficio real (el equipo arranca y abre programas mucho más rápido) y que se necesita copiar o reinstalar; `quien="tecnico"`, `prioridad="media"`, `basado_en=["Disco principal: HDD (disco duro mecánico)"]`. Si `disco_sistema_tipo == "desconocido"` pero `hechos.discos` internos son todos `hdd` → misma recomendación con `basado_en` "Discos internos: HDD". Si hay un SSD y un HDD y el de sistema es SSD, no se genera (Review Focus 4); si hay mezcla y el de sistema es desconocido, no se genera.
3. **`ram_ampliar`** — si `ram_gb < 8` y `ram_uso is not None` y `ram_uso >= 80`: "Amplía la memoria RAM"; `basado_en=["RAM: X GB", "Uso de RAM durante el análisis: Y %"]`; `quien="tecnico"`; `prioridad="media"`. Si además `ram_gb <= 4`, el detalle menciona que con tan poca memoria varios programas a la vez irán lentos.
4. **`respaldo`** — si `almacenamiento.estado` es `sospecha` o `critico`: "Haz hoy una copia de tus archivos importantes"; `prioridad="alta"`; `quien="tu_mismo"`; `basado_en=["Estado del disco según Windows: <estado>"]` más el mensaje del módulo.
5. **`refrigeracion`** — si `cpu.estado` es `advertencia` o `critico`: "Revisa la limpieza y la refrigeración"; `basado_en=["Temperatura del procesador: X °C"]` (si el dato existe); `quien="tecnico"`; `prioridad` `"alta"` si crítico, `"media"` si advertencia. Detalle sin alarmismo (polvo, ventilador, pasta térmica; el equipo puede bajar su velocidad solo para protegerse).
6. **`bateria`** — solo si `bateria.datos.aplica` es `True`: si `salud_porcentaje` es un número y `< 70` → "Planea cambiar la batería" (`basado_en=["Salud de la batería: X % de su capacidad original"]`, `quien="tecnico"`, `prioridad` `"media"` si `< 40` crítico en el módulo, si no `"baja"`); además, siempre que aplique, "Cuida tu batería" con hábitos: evita el calor mientras carga, no la dejes llegar a 0 % seguido, y si el equipo casi siempre está enchufado procura no mantenerla al 100 % todo el tiempo (puede ayudar a que dure más; es una buena práctica, no una falla); `basado_en` con `ciclos_carga` y `salud_porcentaje` cuando existan; `quien="tu_mismo"`; `prioridad="baja"`.

- [ ] **Step 1: Escribir `test_recomendador()`** y registrarla en `__main__`, con un ayudante local que arma un `resultado` mínimo desde un dict `{componente: (estado, datos)}`. Aserciones, todas con el valor exacto esperado: (a) equipo moderno (`ram_gb=16`, `cpu "AMD Ryzen 7 PRO 5850U…"`, `64 bits`, firmware `uefi`, `secure_boot True`, `tpm_version "2.0"`) → la recomendación `so` existe, la primera opción es `"Windows 11"`, el `detalle` empieza con `"Según tus componentes te recomendamos:"` y `basado_en` contiene una línea que incluye `"16"`; (b) mismo equipo con `tpm_version=None` → Windows 11 sigue en `opciones` pero con `nota` que contiene `"No se pudo confirmar"` y **no** es la primera opción (Review Focus 1); (c) `cpu "Intel(R) Core(TM) i5-7200U"` (→ `apto11 False`) → ninguna opción se llama `"Windows 11"`; (d) `ram_gb=2`, `64 bits`, cpu antiguo → opciones incluyen `"MiniOS10"` y la primera NO es `"Windows 7"`; `ram_gb=1`, `32 bits` → `"Windows 7"` es la **última** opción y su `nota` contiene `"actualizaciones de seguridad"` (Review Focus 5); (e) `ram_gb=8`, `64 bits` sin datos de firmware/TPM → no se lanza excepción y no aparece Windows 11 como principal; (f) `disco_sistema_tipo="hdd"` → existe `id == "disco_ssd"`; `disco_sistema_tipo="ssd"` con un segundo disco HDD en `hechos.discos` → no existe `disco_ssd` (Review Focus 4); (g) `ram_gb=4`, `ram_uso=88` → existe `ram_ampliar`; `ram_gb=16`, `ram_uso=95` → no existe; (h) `almacenamiento` en `sospecha` → existe `respaldo` con `prioridad == "alta"`; (i) `cpu` en `critico` → `refrigeracion` con `prioridad == "alta"`; en `advertencia` → `"media"`; (j) batería `aplica False` → ningún id empieza con `"bateria"`; con `salud_porcentaje=55` → existe `bateria_cambio` y `bateria_cuidado`; (k) `recomendar(None, None)` y `recomendar({}, {})` devuelven `[]` sin excepción (Review Focus 3); (l) todas las recomendaciones tienen `basado_en` como lista no vacía de `str`, `prioridad` en `{"alta","media","baja"}`, `quien` en `{"tu_mismo","tecnico","nadie"}`, y la salida está ordenada alta → media → baja; (m) palabras prohibidas: ningún texto (título, detalle, basado_en, opciones) en minúsculas contiene `peligro`, `infectad`, `limpio`, `garantiza`. Usar los ids `so`, `disco_ssd`, `ram_ampliar`, `respaldo`, `refrigeracion`, `bateria_cambio`, `bateria_cuidado`.
- [ ] **Step 2: Correr y ver que falla** (módulo inexistente).
- [ ] **Step 3: Implementar `backend/recomendador.py`** con `recomendar` y una función privada por regla, y la sección de reglas en `docs/reglas-recomendaciones.md`.
- [ ] **Step 4: Correr `python test_scanner.py`** → pasa, stderr limpio. Checkpoint.

### Task 3: El escáner adjunta `hechos` y `recomendaciones`; reporte de texto

**Files:**
- Modify: `backend/scanner.py` (`ejecutar_escaneo_completo`), `backend/utils.py` (`generar_reporte_texto`)
- Test: `backend/test_scanner.py`

**Interfaces:**
- Consumes: `equipo.leer_hechos() -> dict` (Tarea 1), `recomendador.recomendar(resultado, hechos) -> list[dict]` (Tarea 2).
- Produces: el resultado de `ejecutar_escaneo_completo()` incluye `"hechos"` (dict) y `"recomendaciones"` (list) al mismo nivel que `componentes`; `tiempos["hechos"]` con los segundos que tardó la lectura; si `equipo.leer_hechos` o `recomendador.recomendar` lanzaran, el escaneo igual completa con `hechos = {}` y `recomendaciones = []`. `generar_reporte_texto` agrega, si hay recomendaciones, una sección `--- RECOMENDACIONES ---` con por cada una: prioridad y título, `Detalle:`, `Basado en:` (una línea `- ` por dato) y, si hay opciones, `Opciones:` con una línea `- nombre: motivo (nota)` por opción.

- [ ] **Step 1: Escribir `test_escaner_recomendaciones()`**: (a) con `scanner.COMPONENTES` reemplazado por `[]`, `equipo.leer_hechos` por una función que devuelve un dict fijo y `recomendador.recomendar` por una función que registra sus argumentos y devuelve una lista fija, `ejecutar_escaneo_completo()` devuelve `hechos` y `recomendaciones` iguales a los de las funciones falsas y `tiempos` contiene `"hechos"`; (b) si `equipo.leer_hechos` lanza `RuntimeError` → `hechos == {}` y `recomendaciones == []` sin excepción (restaurar todo en `finally` y llamar `_lhm.invalidar()`); (c) `utils.generar_reporte_texto` de un resultado con una recomendación `so` con dos opciones contiene `--- RECOMENDACIONES ---`, `Basado en:`, `Opciones:` y el nombre de ambas opciones, y de un resultado sin `recomendaciones` no contiene `RECOMENDACIONES`. Registrar en `__main__`.
- [ ] **Step 2: Correr y ver que falla.**
- [ ] **Step 3: Implementar** en `scanner.py` (importar `equipo` y `recomendador`; cronometrar con el mismo patrón de `tiempos`) y en `utils.py` (la sección del reporte).
- [ ] **Step 4: Correr `python test_scanner.py`** → pasa. Checkpoint.

### Task 4: Informe imprimible e interfaz

**Files:**
- Modify: `backend/informe.py`, `frontend/static/js/app.js`, `frontend/static/css/style.css`, `frontend/templates/index.html` (solo si hace falta un contenedor), `docs/DECISIONES.md` (decisión 37)
- Test: `backend/test_scanner.py`

**Interfaces:**
- Consumes: `resultado["recomendaciones"]` (lista de la Tarea 2).
- Produces: en `informe.generar_informe_html`, una sección "Recomendaciones para tu equipo" **antes** de "Preguntas para tu técnico": por recomendación, título, prioridad en palabras ("Prioridad: alta/media/baja"), detalle, lista "Basado en:" y, si hay `opciones`, un `<details>` por opción con `<summary>` = nombre y dentro motivo y nota. Todo texto escapado. Sin recomendaciones, la sección no aparece. En el frontend (modo simple y modo técnico), el mismo bloque debajo de las tarjetas, con `<details>`/`<summary>` para las opciones (sin JS extra para abrir/cerrar), usando `textContent`/`crear()`. Si el escaneo no trae `recomendaciones` (versión vieja o modo demostración) no se dibuja el bloque y nada se rompe (el modo demostración no inventa recomendaciones). Decisión 37 en `DECISIONES.md`.

- [ ] **Step 1: Escribir los tests en `test_informe()`/nuevo `test_informe_recomendaciones()`**: (a) un resultado con una recomendación cuyo `titulo` es `"<script>alert(1)</script> & Co"` y una opción con `nota` `"<b>x</b>"` → el HTML no contiene `<script>alert(1)</script>` ni `<b>x</b>`, y contiene `&lt;script&gt;`; (b) el HTML contiene `"Recomendaciones para tu equipo"` y, para la opción, un `<details>` con su nombre; aparece **antes** de `"Preguntas para tu técnico"`; (c) sin `recomendaciones` (clave ausente o lista vacía) el HTML no contiene `"Recomendaciones para tu equipo"`; (d) tolerancia: `opciones` ausente, `basado_en` con un valor no-str, `recomendaciones` que no es lista → no lanza. Registrar en `__main__`.
- [ ] **Step 2: Correr y ver que falla.**
- [ ] **Step 3: Implementar** la sección del informe y el bloque del frontend; agregar el CSS mínimo (reusar clases y variables existentes); apéndice en `DECISIONES.md` con la decisión 37 ("Recomendador del equipo (F3)": datos medidos → recomendaciones con "basado en"; Windows 7 solo como última opción con aviso; la heurística de CPU por nombre devuelve `None` cuando no sabe; TPM requiere administrador y degrada a "no se pudo confirmar"; lista de reglas y que los textos los revisa el equipo).
- [ ] **Step 4: Verificación automática**: `node --check frontend/static/js/app.js` (si hay node), `python test_scanner.py` limpio, y con un servidor propio (`python backend\lanzador.py --sin-navegador`, matar solo por PID) `GET /api/scan` contiene `recomendaciones` y `hechos`, y `GET /api/informe` contiene "Recomendaciones para tu equipo" cuando hay al menos una.
- [ ] **Step 5: Verificación visual** (la hace el controlador con el navegador integrado): escaneo real en modo simple y técnico, apertura de las opciones del sistema operativo con `<details>`, informe, ventana angosta (~700 px) sin desbordes. Checkpoint.

---

## Self-review

- **Cobertura de la spec §5.2:** S.O. sugerido (RAM, CPU, disco, TPM, UEFI/Secure Boot, arquitectura) con "según tus componentes te recomendamos" y opciones seleccionables (`<details>`) → T1, T2, T4; mejoras de hardware (HDD→SSD, RAM, pasta/refrigeración) → T2; batería (hábitos y reemplazo) → T2; disco (respaldo urgente) → T2; "basado en" en cada una → T2; integración en el resultado, el reporte y el informe → T3, T4; Windows 7 solo como última opción con aviso (spec §10) → T2.
- **Consistencia de tipos:** `tipo_disco`, `cpu_apto_windows11`, `leer_hechos` (T1) → `recomendar` (T2) → `ejecutar_escaneo_completo` (T3) → informe/frontend (T4) usan las mismas llaves (`id`, `titulo`, `detalle`, `basado_en`, `prioridad`, `quien`, `opciones`).
- **Honestidad:** cada regla se evalúa solo con dato leído; el TPM ilegible nunca descarta Windows 11 como "incompatible"; la heurística de CPU devuelve `None` fuera de Core i y Ryzen.
- **Proporción:** las reglas se describen por condición y aserción; el código lo escribe el implementador.
