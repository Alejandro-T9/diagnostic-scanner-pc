# Reglas de clasificación y recomendación

> **Textos en lenguaje simple:** las explicaciones para personas sin
> conocimientos técnicos (qué significa, qué hacer, quién, urgencia y qué
> preguntarle al técnico) viven en `backend/explicador.py`, no en este
> documento. Si cambia un umbral aquí, revisa también esos textos.
>
> Los textos de los análisis de Windows (F4a: `espacio`, `inicio`,
> `programas`, `rendimiento`, lista `scanner.ANALISIS`) también viven en
> `backend/explicador.py`, con sus umbrales (10 %/5 % libre, 10 entradas de
> inicio, 3 programas recientes de editor desconocido).

Este documento describe, en forma de tabla, la regla real que usa cada
módulo de `backend/modules/` para pasar de un dato medido a un estado y
una recomendación. No es una especificación que el código lea en tiempo
de ejecución — cada módulo ya implementa esto en su función
`_clasificar()` y su diccionario `_RECOMENDACIONES`; esta tabla es una
vista de lectura rápida sobre ese código, pensada para explicar y
defender el sistema sin tener que abrir los 8 archivos.

**Advertencia de mantenimiento:** si se cambia un umbral o un mensaje en
el código, hay que actualizar esta tabla a mano — no se genera sola. Si
en algún momento diverge del código, el código manda.

Los 5 estados posibles, de mayor a menor severidad en el veredicto
global (ver `backend/scanner.py::_SEVERIDAD` y decisión 22 en
`DECISIONES.md`): **CRITICO → SOSPECHA → ADVERTENCIA → NO_DETERMINADO →
NORMAL**.

## Tarjeta Madre (`mainboard.py`)

| Condición | Estado | Recomendación |
|---|---|---|
| Fabricante o modelo son texto de relleno de fábrica ("To Be Filled By O.E.M.", etc.) | ADVERTENCIA | Verificar visualmente la placa — datos de fábrica sin configurar pueden indicar una placa reacondicionada. |
| Fabricante y modelo válidos | NORMAL | — |
| WMI no responde o no devuelve la placa | NO_DETERMINADO | No se pudo leer la placa base — revisar conexión de WMI. |

## Procesador (`cpu.py`)

| Condición | Estado | Recomendación |
|---|---|---|
| Temperatura > 85 °C | CRITICO | Detener el uso del equipo y revisar refrigeración antes de continuar — riesgo de daño térmico. |
| Temperatura entre 70 °C y 85 °C | ADVERTENCIA | Verificar el sistema de enfriamiento — pasta térmica o ventilador podrían necesitar mantenimiento. |
| Temperatura < 70 °C | NORMAL | — |
| Sin sensor de temperatura expuesto | NO_DETERMINADO | No se pudo evaluar completamente el procesador — si persiste, revisar sensores térmicos o la conexión de WMI. |

GPU (`gpu.py`) y ventiladores viven dentro de este componente como datos
adicionales, **sin regla de clasificación propia** — ver sección aparte
más abajo. Solo la temperatura del CPU decide el estado del Procesador.

## Memoria RAM (`ram.py`)

| Condición | Estado | Recomendación |
|---|---|---|
| Uso > 95 % | CRITICO | Uso de RAM crítico — el equipo puede volverse inestable, revisar procesos o memoria física instalada. |
| Uso entre 80 % y 95 % | ADVERTENCIA | Cerrar procesos innecesarios o considerar ampliar RAM si el uso alto es constante. |
| Uso < 80 % | NORMAL | — |

## Almacenamiento (`almacenamiento.py`)

Solo considera discos **internos** (interfaz ≠ USB) — los externos se
reportan aparte y nunca afectan este estado (decisión 20).

| Condición | Estado | Recomendación |
|---|---|---|
| Algún disco interno con salud "crítica" (Windows Storage Health) | CRITICO | Reemplazar la unidad antes de seguir en uso — riesgo real de pérdida de datos. |
| Algún disco interno con salud "reducida" | SOSPECHA | Programar respaldo de datos como precaución — Windows reporta salud reducida en el disco. |
| Sin discos internos, o salud no legible | NO_DETERMINADO | No se pudo determinar la salud del disco — revisar conexión física o de WMI. |
| Todos los discos internos con salud normal | NORMAL | — |

## Fuente de Poder (`fuente_poder.py`)

Mide voltaje del regulador del procesador (VID/SVI2), no rieles físicos
de la fuente ni la batería ni el cargador — ver mensaje del estado
normal en el propio módulo.

| Condición | Estado | Recomendación |
|---|---|---|
| Algún sensor fuera de rango físico (≤ 0 V o > 20 V) | SOSPECHA | Voltaje fuera de rango físico esperado — revisar la fuente de poder o el regulador interno. |
| Todos los sensores dentro de rango | NORMAL | — |
| Ningún sensor de voltaje disponible | NO_DETERMINADO | Diagnóstico de voltajes no disponible en este modo. |

## Batería (`bateria.py`)

| Condición | Estado | Recomendación |
|---|---|---|
| Salud < 40 % de la capacidad de diseño | CRITICO | Reemplazar la batería antes de reasignar el equipo. |
| Salud entre 40 % y 70 % | ADVERTENCIA | Monitorear la batería — podría necesitar reemplazo en los próximos meses. |
| Salud > 70 % | NORMAL | — |
| Sin batería detectada (equipo de escritorio) | NORMAL | — (no aplica no es lo mismo que no se pudo leer) |
| Batería detectada pero sin datos de capacidad de diseño | NO_DETERMINADO | No se pudo leer la batería — revisar conexión de WMI. |

## Red (`red.py`)

| Condición | Estado | Recomendación |
|---|---|---|
| Ninguna interfaz con enlace activo | ADVERTENCIA | Revisa que el cable o el Wi-Fi estén conectados; si sigue sin conexión, revisa la tarjeta de red o su driver. |
| Enlace activo con errores de paquetes | SOSPECHA | Revisar cables/antena — hay enlace pero con errores de paquetes, evidencia de un posible problema. |
| Enlace activo sin errores | NORMAL | — |
| Ninguna interfaz de red detectada | NO_DETERMINADO | No se detectó ninguna interfaz de red — revisar hardware o driver. |

La red no tiene ruta a CRITICO (decisión 36): sin enlace puede ser solo un
cable desconectado o el Wi-Fi apagado.

## GPU (`gpu.py` — telemetría auxiliar del Procesador, sin regla propia)

No genera estado ni recomendación: es información de apoyo dentro de
`datos.gpu` del Procesador (decisión 21). Nombre y driver se muestran si
`Win32_VideoController` responde; temperatura y uso solo si
LibreHardwareMonitor expone un sensor confiable (`"GPU Core"` para uso,
con validación de rango físico en ambos) — si no, el campo queda en
`null` en vez de mostrar un dato de otro sensor o inventado (decisión
22).

## Análisis de Windows (`backend/analisis/`, F4a)

Solo lectura, sin administrador, y nunca emiten CRITICO. No están en `scanner.COMPONENTES` (lista `scanner.ANALISIS`).

| Módulo | Condición | Estado | Recomendación |
|---|---|---|---|
| `espacio.py` | Libre de la unidad del sistema (normalmente C:) < 5 % | SOSPECHA | Libera espacio cuanto antes: vacía la papelera, borra descargas viejas y pasa tus archivos a otro disco. |
| `espacio.py` | Libre entre 5 % y 10 % | ADVERTENCIA | Conviene liberar espacio pronto: empieza por la papelera y las descargas que ya no uses. |
| `espacio.py` | Libre ≥ 10 % | NORMAL | — (no hace falta hacer nada) |
| `espacio.py` | No se pudo leer el disco | NO DETERMINADO | Mira en Este equipo cuánto espacio queda libre y repite el análisis. |
| `inicio.py` | 10 o más programas de inicio **habilitados** | ADVERTENCIA | Desactiva en el Administrador de tareas los que no necesites al encender. |
| `inicio.py` | Menos de 10 habilitados | NORMAL | — |
| `inicio.py` | No se pudo leer ninguna fuente | NO DETERMINADO | Mira la lista en el Administrador de tareas, pestaña Inicio, y repite el análisis. |
| `programas.py` | 3 o más programas **visibles** de editor vacío o desconocido, instalados en los últimos 30 días | ADVERTENCIA | Revisa en la lista los programas instalados hace poco y sin editor conocido; eso no significa que sean malos. Si no reconoces alguno, búscalo o pregunta a un técnico antes de quitarlo. |
| `programas.py` | Lista leída y sin esa condición | NORMAL | Recorre la lista de vez en cuando; lo que no uses puedes quitarlo desde Configuración → Aplicaciones. Esta revisión no busca virus. |
| `programas.py` | No se pudo leer ninguna fuente | NO DETERMINADO | Mira la lista en Configuración → Aplicaciones y repite el análisis. |

`espacio` también informa (sin afectar el estado) el tamaño de `%TEMP%`, `Windows\Temp`, Descargas y la Papelera;
cada recorrido tiene topes de tiempo y de archivos y marca `parcial` si se cortó. `inicio` suma las claves Run
(usuario, equipo y 32 bits) y las carpetas Inicio; las entradas que el usuario ya deshabilitó en el Administrador
de tareas (`StartupApproved`, primer byte 0x03/0x07) se listan pero no cuentan. Los servicios de arranque
automático se informan aparte y no suman al umbral.

## Recomendaciones del equipo (F3)

Las calcula `backend/recomendador.py` (`recomendar(resultado, hechos)`) con los
resultados del análisis y los hechos de `backend/equipo.py`. Son sugerencias
adicionales a las recomendaciones por componente de arriba. Cada regla solo
corre si existen los datos que usa: lo que no se pudo leer no se afirma. Salida
ordenada por prioridad (alta, media, baja) y, dentro de cada una, en el orden
de esta tabla. Datos usados: `ram_gb` = RAM física (si falta o es 0, la que ve el SO; si tampoco hay, no hay recomendación `so`);
`arq64` = 64 bits si el SO o el procesador lo dicen (32 bits solo si dicen 32/x86); si algún dato dice ARM, la
arquitectura se trata como desconocida y no hay recomendación `so`. `entorno` (`utils.detectar_entorno()`):
"windows" o "winpe", `None` si no se pudo leer.

| Id | Condición | Recomendación | Prioridad | Quién |
|---|---|---|---|---|
| `so` | Hay `ram_gb` y se conoce la arquitectura | Sistema operativo que conviene (opciones abajo) | BAJA | Técnico si la principal es MiniOS10, Linux o Windows 7, o si Windows 11 tiene datos por confirmar (TPM / Arranque seguro: sin administrador la persona no puede comprobarlo sola); si no, Tú mismo |
| `disco_ssd` | Disco de sistema HDD; o desconocido con todos los discos internos HDD (con un SSD mezclado no se genera) | Pasa tu disco a un SSD | MEDIA | Técnico |
| `ram_ampliar` | `ram_gb` < 8 y uso de RAM ≥ 80 % (si `ram_gb` ≤ 4, el texto lo destaca) | Amplía la memoria RAM | MEDIA | Técnico |
| `respaldo` | Almacenamiento en SOSPECHA o CRITICO | Haz hoy una copia de tus archivos importantes | ALTA | Tú mismo |
| `refrigeracion` | Procesador en ADVERTENCIA o CRITICO | Revisa la limpieza y la refrigeración | ALTA si CRITICO, MEDIA si ADVERTENCIA | Técnico |
| `bateria_cambio` | Batería aplica y salud < 70 % | Planea cambiar la batería | MEDIA si salud < 40 %, si no BAJA | Técnico |
| `bateria_cuidado` | Batería aplica (siempre que aplique) | Cuida tu batería (buenos hábitos; no es una falla) | BAJA | Tú mismo |

Opciones de `so` (la primera es la principal; cada una lleva `motivo` con datos
medidos y, cuando corresponde, una `nota` con sus límites):

| Opción | Se ofrece si | Nota |
|---|---|---|
| Windows 11 | **Si ya está instalado** (`entorno` = "windows" y el nombre del SO actual contiene "Windows 11"; en WinPE no, porque también dice "Windows 11"): siempre es la principal, motivo "Ya lo tienes instalado en este equipo.", `basado_en` con "Sistema actual: <nombre>", detalle "Windows 11 (ya lo tienes instalado)", sin notas de "falta confirmar", sin Windows 10 y sin comprobar procesador/firmware/TPM (aunque el procesador sea desconocido para la heurística); las demás opciones siguen las reglas normales por RAM. **Si no**: 64 bits, `ram_gb` ≥ 4, procesador apto (heurística de `equipo.cpu_apto_windows11`), firmware UEFI, Secure Boot no desactivado y TPM distinto de 1.2. Siempre es la principal si se ofrece. Un dato ilegible (TPM o Secure Boot sin permisos) no la descarta: se ofrece con la nota "Falta confirmar…" y el detalle dice "Windows 11 (falta confirmar el TPM 2.0)". Solo se omite por datos realmente leídos (procesador antiguo, BIOS clásica, Secure Boot desactivado, TPM 1.2) o por firmware/procesador no comprobables; `basado_en` dice por qué. | Solo si falta confirmar TPM/Secure Boot: explica en palabras simples qué es ("Falta confirmar el TPM 2.0, un chip de seguridad que Windows 11 pide. Se puede leer abriendo el programa como administrador, o un técnico puede revisarlo."; igual para el Arranque seguro) |
| Windows 10 | 64 bits y `ram_gb` ≥ 4 | "Ya no recibe actualizaciones de seguridad gratuitas en la mayoría de los equipos" (sin fecha concreta) |
| Ubuntu o Linux Mint | `ram_gb` ≥ 4. Motivo: "Con X GB de RAM tu equipo cumple lo que suelen pedir estas versiones de Linux." (solo el dato medido, sin prometer fluidez) | En 32 bits: pocas versiones compatibles, lo confirma un técnico |
| Lubuntu o Linux Mint XFCE | `ram_gb` < 4. Motivo: versiones livianas pensadas para equipos con poca memoria, con el dato de RAM | Igual que la anterior |
| MiniOS10 | 64 bits, `ram_gb` ≥ 2 y (`ram_gb` < 4, o disco de sistema HDD con `ram_gb` < 8) | Versión modificada de Windows 10 que no viene de Microsoft: no se puede verificar qué se le quitó, necesita licencia de Windows válida; solo con un técnico de confianza (¿se queda en la lista? decisión del equipo, ver 38) |
| Windows 7 | Siempre al final; solo si 32 bits o `ram_gb` < 2 | Sin actualizaciones de seguridad desde 2020; solo si el equipo o los programas lo exigen, de preferencia sin internet |

`basado_en` solo lleva líneas con dato real (sistema actual si ya es Windows 11, RAM, procesador,
arquitectura, "Modo de arranque: UEFI (el moderno)" o "BIOS clásica (el antiguo)",
"TPM (chip de seguridad)" —o "no se pudo leer"—, tipo de disco principal).
Las razones por las que se omite Windows 11 hablan de lo que el equipo hace HOY:
`GetFirmwareType` dice cómo arrancó el SO actual, no lo que el firmware admite, así que se redactan como
"arranca hoy en modo BIOS clásico" / "el Arranque seguro está desactivado hoy" y remiten a un técnico.

Limitación conocida: con discos mezclados (SSD + HDD) y disco de sistema desconocido no se genera
`disco_ssd` (no se sabe cuál es el principal).

En `respaldo`, `basado_en` lleva el estado del disco en lenguaje simple y una
línea "Disco afectado: <modelo>" por cada disco interno con ese estado. No
copia el `mensaje` del módulo de almacenamiento, que usa términos técnicos
("Salud reducida (Windows Storage Health) en: ...").

`programas` junta el registro de "Desinstalar" (equipo, 32 bits y usuario) con `Get-StartApps` de PowerShell
(tiempo límite 10 s; sin PowerShell solo usa el registro). "Editor desconocido" = vacío, `unknown` o `desconocido`.
Una fecha ausente, mal formada o futura nunca cuenta como reciente. Los **ocultos** (`SystemComponent` o
`ParentKeyName`: parches y componentes que Windows no lista en Configuración) se cuentan y se muestran al final de
la lista, pero no cuentan para el aviso. La lista se corta en 300 elementos (el total real se informa) y los
nombres recientes sin editor en 20.
