# Diagnostic Scanner PC 2.0 — App portable para todo tipo de usuario

**Fecha:** 2026-10-21
**Estado:** aprobado por el equipo el 2026-10-21 (con las respuestas de la sección 10). Nada construido todavía.
**Origen:** retroalimentación del jurado SENA tras la sustentación del 16-oct-2026 (87,5/100) + ideas del equipo (José Alejandro, Juan Esteban, Dany Arley).

Convención: lo que dijo el equipo va sin marca. Lo que es **decisión mía (Claude)** o **suposición mía** está marcado como `[MI LLAMADA]` o `[SUPOSICIÓN]` para que lo revisen.

---

## 1. Por qué (intención)

El jurado dijo, en resumen: la app es muy clara *para un técnico*, pero alguien que no sabe de mantenimiento se confunde. Si dice "Normal", que diga al lado qué componentes están bien y qué recomendaciones hay. Si dice "Crítico", que diga cuál es el error y cómo solucionarlo. "Solo falta una pizca de sal."

El equipo fue más lejos y pidió un **giro de 360°**:

1. La app deja de ser "un USB que arranca Hiren's Boot" y pasa a ser **una app portable** que se abre desde el USB sobre el Windows que ya tiene el PC.
2. Debe servir a **todo tipo de persona**:
   - quien no sabe y quiere entender su PC o arreglarlo solo;
   - quien quiere saber *por qué va lento* o *cómo mejorarlo*;
   - quien va a llevar el PC a un técnico y quiere **llevar evidencia** para que no le cobren de más ni le hagan cosas innecesarias;
   - el técnico que quiere trabajar más rápido.
3. Debe **reunir en una sola herramienta** lo que hoy hacen CPU-Z, LibreHardwareMonitor, HWiNFO, CrystalDiskInfo, GMER y comandos del sistema (por ejemplo `shell:AppsFolder`, que muestra todas las apps instaladas, incluso ocultas).
4. Debe dar **recomendaciones concretas** (qué S.O. instalar, cuidar la batería, etc.).
5. Una **base de datos** para registrar PCs (una empresa podría llevar su inventario e informes).
6. Que ayude también con **tareas de post-install**.

Es una mejora para el equipo y también para entregar.

## 2. Qué estado tiene hoy el proyecto (hallazgos de la revisión del código)

- 7 módulos en `backend/modules/` con contrato fijo de 5 llaves (`componente, estado, mensaje, datos, recomendacion`), validado por `scanner._cumple_contrato`. Sistema de 5 estados. Todo sobre WMI + LibreHardwareMonitorLib (LHM 0.9.6, vía pythonnet).
- Frontend en JS vanilla: mapa físico + lista + panel de detalle. Los textos de `mensaje` y `recomendacion` son **técnicos y cortos** ("Salud reducida (Windows Storage Health) en 1 disco"). Es justo lo que el jurado señaló.
- `app.py` arranca con `host="0.0.0.0"`. En WinPE sin red no importaba; **en un Windows normal conectado a una red expone el escáner a toda la red**. Hay que cambiarlo a `127.0.0.1` (ver §6).
- Decisión 4 del proyecto: **stateless**, no se guarda nada. Choca con la base de datos pedida (ver §5.5).
- Hay 10 hallazgos de la revisión del 15-sep sin corregir; varios importan mucho más ahora que la app correrá en Windows real (aislar excepciones de `gpu.py`, abrir LHM una sola vez en vez de 3, `threaded=True`, `/api/reporte` sin try/except, `pythoncom` sin declarar en `requirements.txt`).
- Hay código viejo muerto (Alpine/Debian): `scripts/*.sh`, `build/create_iso.sh`, `build/overlay/`.

## 3. Objetivos, no-objetivos y anti-objetivos

### Objetivos
- **O1.** Un usuario sin conocimientos abre la app, pulsa un botón, y en 1–2 minutos entiende: *cómo está su PC, qué está mal, qué puede hacer él y qué debería hacer un técnico*.
- **O2.** Cada componente y cada estado tiene, junto al semáforo, un texto claro: **qué significa**, **qué hacer**, **quién debe hacerlo** (tú mismo / un técnico / no es urgente).
- **O3.** Un **informe para llevar al técnico** que lista los hallazgos reales con evidencia, para poder comparar lo que dice el técnico con lo que dice el PC.
- **O4.** Funciona **desde el USB sobre Windows 10/11** sin instalar nada.
- **O5.** Funciones tipo CPU-Z / HWiNFO / CrystalDiskInfo / autoruns / `shell:AppsFolder`, todas **solo lectura**.
- **O6.** Recomendaciones basadas **solo en datos medidos** (S.O. sugerido, mejoras de hardware, cuidado de batería).
- **O7.** Registro opcional de equipos (inventario + historial + informes).
- **O8.** Ayuda de post-install con confirmación del usuario en cada acción.

### No-objetivos (por ahora)
- No es un antivirus ni un detector de rootkits de nivel kernel (ver §5.4: lo que sí hace es detectar *señales de alerta*, y lo dice).
- No repara ni borra nada por su cuenta en las fases 1–5 (**solo lectura**). Las acciones (fase 6) siempre piden confirmación.
- No corre en Windows 7/8 ni en Linux/macOS. `[MI LLAMADA]` Python 3.12 no corre en Windows 7; soportar Win7 obligaría a un Python 3.8 y a rehacer dependencias. Windows 7 queda fuera.
- No envía datos a internet. Todo es local.
- No se agregan frameworks JS ni dependencias nuevas de Python sin discutirlas (regla del README).

### Anti-objetivos (fracaso aunque "funcione")
- Que la app **invente** datos o diagnostique con falsa seguridad. Si un dato no se puede leer, dice "no se pudo leer", no "todo bien" (regla ya existente, se mantiene).
- Que el texto "simple" sea **vago o alarmista** ("tu PC está en peligro") o que empuje a pagar. Cada afirmación debe poder rastrearse a un dato medido.
- Que la app dañe el PC de un usuario sin experiencia (por eso solo lectura al inicio, y confirmación explícita después).
- Que se vea como una app para técnicos con otro color: el modo simple debe ser **realmente** otro nivel de lectura.

## 4. Decisiones de arquitectura

Estas van a `docs/DECISIONES.md` (append-only) cuando se aprueben: 27 (pivote a portable), 28 (capa de lenguaje claro aditiva), 29 (registro opt-in, enmienda a la 4).

| # | Decisión | Quién |
|---|---|---|
| D1 | La app principal pasa a ser portable sobre Windows. El mismo código sigue funcionando en WinPE; los módulos nuevos que necesiten un Windows instalado devuelven `no_determinado` en WinPE (decisión 8, degradación elegante). | Equipo (pivote) + `[MI LLAMADA]` conservar compatibilidad |
| D2 | La ISO de Hiren's **no se borra**: queda en el USB como "modo rescate" para PCs que no arrancan. No es el camino principal. | `[MI LLAMADA]` — el equipo dijo "dejar a un lado"; esto no lo elimina |
| D3 | El navegador es **Edge en modo app** (`msedge --app=http://127.0.0.1:PUERTO`), que ya trae Windows 10/11. Se descarta el Chromium portable de ~800 MB. Si no hay Edge, se prueba Chrome y luego el navegador predeterminado. | `[MI LLAMADA]` |
| D4 | Se mantiene Python embeddable + Flask. Lanzador `Iniciar_Diagnostic_Scanner.bat` que pide permisos de administrador (necesarios para sensores y S.M.A.R.T.). | `[MI LLAMADA]` |
| D5 | El servidor escucha **solo en 127.0.0.1**, con puerto libre automático. | `[MI LLAMADA]` — es un riesgo de seguridad real |
| D6 | El contrato de módulo de 5 llaves **no cambia**. La capa de lenguaje claro es **aditiva**: cada módulo agrega un `codigo` de hallazgo (opcional) y un nuevo `explicador.py` lo traduce a `guia = {que_pasa, que_hacer[], quien, urgencia}`. `scanner` pega la guía al resultado. | `[MI LLAMADA]` |
| D7 | Toda la información visible tiene **dos niveles**: *Modo simple* (por defecto) y *Modo técnico* (lo que existe hoy más los datos nuevos). Un interruptor los alterna. | `[MI LLAMADA]` |
| D8 | El registro de equipos usa **SQLite** (`sqlite3` ya viene en Python: **cero dependencias nuevas**), archivo local en el USB (o carpeta elegida). Es **opt-in**: nada se guarda si el usuario no pulsa "Guardar en el registro". | `[MI LLAMADA]`, enmienda a decisión 4 |
| D9 | Informes en **HTML imprimible** (se guarda como PDF desde el navegador) y **CSV** para el inventario. Sin librerías de PDF. | `[MI LLAMADA]` |
| D10 | Tono de los textos: tuteo ("Selecciona", "tu PC"), frases cortas, sin jerga; la jerga va al modo técnico. (La interfaz actual usa voseo, "Seleccioná"; se corrige.) | `[MI LLAMADA]` |

## 5. Alcance por bloque

### 5.1 Lenguaje claro (la recomendación literal del jurado)
- Sello global en palabras: *"Tu PC está bien"* / *"Tu PC necesita atención"* / *"Tu PC tiene un problema serio"* / *"No pudimos revisar todo"*.
- Resumen: *"Estos componentes están bien: …. Estos necesitan atención: …"*.
- Por componente y estado, tarjeta con **Qué significa · Qué hacer · Quién lo hace · Qué tan urgente**. Para estados normales, también una frase de qué hacer para *mantenerlo* bien.
- Vocabulario de cada componente ("¿qué es la RAM?") en un "¿Qué es esto?" desplegable.
- Cobertura de pruebas: una prueba verifica que **todo par (componente, estado) posible tiene una guía**; así nunca queda un "Crítico" sin explicación.

### 5.2 Recomendador
Reglas sobre datos medidos (ejemplos, a afinar en el plan detallado):
- **Sistema operativo sugerido** (RAM, CPU, tipo de disco, TPM, UEFI/Secure Boot, arquitectura): lista ordenada con *por qué*, p. ej. Windows 11 si cumple requisitos; Windows 10 con la advertencia de que su soporte general terminó el 14-oct-2025; Windows 10 LTSC o MiniOS10 para equipos modestos; distros Linux ligeras (Lubuntu, Linux Mint XFCE) para equipos muy limitados. **Decisión del equipo:** Windows 7 sí puede aparecer como *recomendación* cuando el hardware lo requiera (equipos muy antiguos, 32 bits, drivers solo para Win7), siempre con la aclaración honesta de que ya no recibe actualizaciones de seguridad y que se use sin internet o con cuidado. Las recomendaciones se redactan como "según tus componentes te recomendamos (X)".
- **Mejoras de hardware** con mayor retorno: HDD → SSD, RAM insuficiente, pasta térmica si hay temperatura alta sostenida.
- **Batería:** hábitos concretos según ciclos y salud (p. ej. no mantenerla al 100% conectada siempre, evitar calor, cuándo reemplazarla).
- **Disco:** respaldo urgente si hay señales de falla; liberar espacio.
- Cada recomendación incluye **"basado en:"** con el dato real que la dispara.

### 5.3 Módulos nuevos en Windows en vivo (solo lectura)
Cada uno cumple el contrato y se agrega a `COMPONENTES` solo cuando tiene pruebas.

| Módulo | Qué muestra | Referencia |
|---|---|---|
| `programas` | Todo lo instalado: registro (Uninstall), apps de Microsoft Store, lo de `shell:AppsFolder`, **ocultos**, instalados recientemente, de editor desconocido | `shell:AppsFolder`, Programas y características |
| `inicio` | Qué arranca con Windows (Run, carpeta Inicio, tareas al iniciar sesión, servicios automáticos) y cuánto lo retrasa | Administrador de tareas / Autoruns |
| `rendimiento` ("¿por qué va lento?") | Procesos que más consumen, disco al 100%, HDD vs SSD, RAM justa, poco espacio libre, demasiados programas de inicio → una **causa principal** con evidencia | — |
| `estabilidad` | Pantallazos azules, apagones inesperados y errores de disco recientes (Visor de eventos) | BlueScreenView / Visor de eventos |
| `controladores` | Dispositivos con driver faltante o con error | Administrador de dispositivos |
| `seguridad_basica` | Defender activo, firewall, actualizaciones pendientes, UAC | Centro de seguridad |
| `alertas` (tipo GMER-lite) | **Señales de alerta**: procesos o inicios desde carpetas temporales/Descargas, ejecutables sin firma, archivo `hosts` modificado, proxy no esperado, programas con conexiones raras | GMER / Autoruns |
| `espacio` | Qué ocupa espacio, temporales, papelera, descargas grandes (solo informa) | — |
| Vistas "técnicas" | Inventario detallado (CPU-Z/HWiNFO), sensores en vivo con gráficas (LHM), tabla S.M.A.R.T. (CrystalDiskInfo) | CPU-Z, HWiNFO, CrystalDiskInfo |

### 5.4 Honestidad sobre los límites
GMER detecta *hooks* y rootkits a nivel de kernel; un programa en Python **no puede** hacer eso de forma fiable. `alertas` se presenta como "señales de alerta que merecen revisión", nunca como "tu PC está limpio". Si no hay alertas dice "no encontramos señales de alerta en lo que sabemos revisar", con la lista de lo que **no** revisa. Lo mismo para el módulo de seguridad: lee el estado, no lo cambia.

### 5.5 Registro de equipos (enmienda a decisión 4)
- Identidad de un PC: UUID de Win32_ComputerSystemProduct + serial de BIOS + serial de placa (si son genéricos tipo "To be filled by O.E.M.", se avisa y se usa el nombre elegido).
- Datos que el usuario escribe: nombre, ubicación/sala, responsable, notas.
- Cada guardado = una **foto** del escaneo (JSON completo) con fecha → historial por equipo y tendencias (p. ej. la salud de la batería bajando).
- Pantalla *Inventario*: tabla de todos los equipos, filtro por estado, "mantenimiento pendiente".
- Exportar: **CSV** del inventario; **informe HTML imprimible** por equipo.
- Riesgo asumido: si se pierde el USB (ya pasó, decisión 26), se pierde también el registro. Mitigación: ruta del registro configurable y botón "copia de respaldo". No hay cifrado en la v1; se documenta.

### 5.6 Ayuda de post-install (la fase más delicada)
- *Lista de verificación automática* de un equipo recién instalado: controladores completos, Windows actualizado, Defender activo, programas básicos presentes, espacio, nombre del equipo. Marca lo que ya está y lo que falta.
- *Instalación de programas básicos* (7-Zip, LibreOffice, Foxit Reader, VLC, navegador) desde una carpeta `instaladores\` del USB (offline) o con `winget` si existe y hay internet. **Siempre con confirmación**, una a una.
- *Registro de la intervención* ligado a la ficha del equipo, y los datos listos para llenar el formato **SOPORTE TÉCNICO** (equipo, serial, S.O., fecha).
- **Fuera de alcance, siempre:** activadores, cracks, desactivar el antivirus. (Posición ya acordada con el equipo.)

### 5.7 Interfaz
- Pantalla inicial: un botón grande **"Revisar mi PC"** y la elección de modo.
- Resultado en tres capas: (1) sello y frase, (2) tarjetas por componente con guía, (3) detalle técnico plegable.
- Tab *Informe para el técnico* (§1, O3), con "preguntas que puedes hacerle a tu técnico" generadas **de los hallazgos reales** `[SUPOSICIÓN]` que esto sea útil para la persona que no confía en el técnico; a confirmar con el equipo.
- Se conserva la paleta (`config/palette.css`) y el mapa físico como vista alterna. Sin frameworks.

## 6. Restricciones
- Reglas del README: sin frameworks JS, sin dependencias nuevas sin hablarlo, ningún dato inventado (sensor ausente → `null`/`no_determinado`), decisión nueva → `DECISIONES.md` con fecha y motivo.
- Contrato de módulos intacto (5 llaves).
- TDD como en las correcciones del 15-sep: `test_scanner.py` (estilo assert, sin framework). Cada módulo nuevo: función de clasificación **pura** testeable sin hardware.
- Administrador obligatorio para sensores/S.M.A.R.T.; sin admin la app debe seguir abriendo y marcar lo que no pudo leer.
- Riesgo a verificar: antivirus/Defender y el driver de sensores que carga LHM. LHM 0.9.6; `[SUPOSICIÓN]` esta versión ya usa PawnIO y no WinRing0, **pendiente de comprobar** en un Windows con Defender activo antes de prometerlo.
- Espacio del USB (7,46 GB, ~4 GB ocupados): quitar Chromium (~800 MB) libera lugar para `instaladores\`.
- Compatibilidad objetivo: Windows 10 (1809+) y Windows 11, 64 bits.

## 7. Fases y orden propuesto

Cada fase termina con algo que funciona y se puede probar, y se cierra con una entrada en `DECISIONES.md`.

| Fase | Contenido | Entrega |
|---|---|---|
| **F0 Cimientos** | Decisiones 27–29 · `127.0.0.1` · aislar `gpu.py` · LHM una sola vez · `threaded=True` · `/api/reporte` robusto · `pythoncom` en requirements · quitar código muerto Alpine/Debian | App más sólida, sin cambios visibles |
| **F1 Portable** | Lanzador `.bat` con elevación · Edge en modo app · detección `entorno` (windows/winpe) · estructura de carpetas del USB · prueba en Windows real | **Se abre desde el USB sobre Windows** |
| **F2 Lenguaje claro** | `explicador.py` + `guia` · modo simple/técnico · sello en palabras · tarjetas · informe HTML imprimible · test de cobertura | **Responde la recomendación del jurado** |
| **F3 Recomendador** | S.O. sugerido · mejoras · batería · "basado en:" | Recomendaciones concretas |
| **F4a Lentitud y apps** | `programas`, `inicio`, `rendimiento`, `espacio` | "¿Por qué va lento?" |
| **F4b Salud y alertas** | `estabilidad`, `controladores`, `seguridad_basica`, `alertas`; vistas técnicas (inventario, sensores en vivo, S.M.A.R.T.) | Tipo HWiNFO / CrystalDiskInfo / GMER-lite |
| **F5 Registro** | SQLite · inventario · historial · CSV · informe por equipo | Base de datos de PCs |
| **F6 Post-install** | Lista de verificación · instaladores del USB · registro de intervención · datos para SOPORTE TÉCNICO | Ayuda de post-install |
| **F7 Cierre** | Manual y folleto actualizados · pruebas en PCs reales del colegio · USB final · bitácora | Entregable final |

Mínimo defendible si falta tiempo (año escolar termina el 18-nov-2026): **F0 + F1 + F2 + F3**. Es lo que el jurado pidió literalmente.

## 8. Qué se deja al constructor
- Umbrales exactos de cada regla del recomendador y del módulo `rendimiento` (se documentan en `docs/reglas-recomendaciones.md`, que se amplía).
- Redacción final de cada texto de la guía (la redacción la revisa el equipo antes de cerrar F2).
- Detalle de las consultas del Visor de eventos y de las rutas del registro de Windows.
- Diseño visual final (siguiendo la paleta existente).

## 9. Cómo se sabe que funcionó
- Una persona sin conocimientos técnicos, con el USB y sin ayuda, abre la app, entiende el resultado y puede decir qué haría.
- Ningún par (componente, estado) queda sin guía (prueba automática).
- La app abre y no rompe en un Windows 10 y en un Windows 11 reales, con y sin permisos de administrador.
- `python test_scanner.py` pasa completo en cada fase.

## 10. Respuestas del equipo (2026-10-21)
1. La ISO de Hiren's sirve como rescate, **pero en la prueba real hubo que abrir `iniciar.bat` a mano y escribir la URL de localhost**: el autoarranque no funcionó en ese USB (16 GB). Esto refuerza D3/D4: el lanzador portable debe abrir el navegador solo. Queda como deuda de F1 verificar también el modo rescate.
2. Win7 como recomendación, redactada como "según tus componentes te recomendamos…" (ver §5.2).
3. Equipo de pruebas: **solo la laptop de José Alejandro (Windows 11 Pro)**. No hay Windows 10 real; las pruebas en Win10 y en PCs del colegio se harán cuando haya jornada, o en máquina virtual `[SUPOSICIÓN]` si el equipo lo permite. Los scripts deben evitar APIs que solo existan en Win11.
4. Orden F0 a F7 aprobado.
