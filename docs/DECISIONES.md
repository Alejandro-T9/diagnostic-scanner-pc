# Registro de Decisiones Técnicas — Diagnostic Scanner PC

Este documento registra las decisiones técnicas tomadas durante el desarrollo,
con su fecha y el motivo. Se actualiza a medida que se toman decisiones nuevas
o se revisan las anteriores — no se reescribe el historial.

## 1. Stack tecnológico

**Fecha:** 2026-07-28

Alpine Linux (musl, busybox, apk, OpenRC) como sistema operativo del USB
booteable, backend en Python 3.10+ con Flask, frontend en HTML5/CSS3/JS
vanilla. Sin frameworks JS (React/Vue/Angular/Bootstrap/Tailwind/htmx), sin
CDN/npm/Node/Electron. Todo corre local y offline.

## 2. Ubicación del dashboard: local (X11 + navegador kiosk)

**Fecha:** 2026-07-28

El dashboard se muestra en la misma máquina diagnosticada, vía X11 + un
navegador liviano en modo kiosk apuntando a `localhost:5000`. Se descartó la
alternativa de "dashboard de red" (ver a través de un segundo dispositivo)
por fidelidad al modelo Hiren's Boot: standalone, sin depender de que haya
otro equipo disponible. Riesgo conocido y aceptado: detección de driver
gráfico en hardware viejo/donado; sin video ni GPU detectada, la consola de
texto sigue mostrando el estado del servidor como respaldo de diagnóstico.

## 3. Sin restricción de RAM

**Fecha:** 2026-07-28

Se eliminó la regla original de "<512MB RAM prioridad". Las laptops del
colegio tienen entre 4 y 8GB de RAM reales, por lo que el costo de memoria
de X11 + navegador (300-500MB+) no es un problema práctico.

## 4. Persistencia: stateless

**Fecha:** 2026-07-28

No se guarda nada entre reinicios — cada boot es un diagnóstico limpio,
sin estado previo que pueda quedar corrupto o desactualizado. Para no
perder el resultado de un escaneo, el dashboard tendrá un botón "Descargar
Reporte" que exporta el último resultado a un archivo `.txt` generado al
vuelo (no persistido en la imagen), que el navegador guarda donde el
usuario decida.

## 5. Build del ISO: pospuesto

**Fecha:** 2026-07-28

Se pospone `build/create_iso.sh` hasta tener los módulos de diagnóstico
base funcionando y definida la configuración exacta de X11 + navegador
kiosk (paquetes, gestor de ventanas, flags del navegador). Se hará un
smoke test de boot en hardware real del colegio antes de invertir tiempo
en el script de build completo.

## 6. Contrato de módulos de diagnóstico

**Fecha:** 2026-07-28

Cada módulo en `backend/modules/` expone una función `diagnosticar()` sin
argumentos que devuelve:

```python
{
    "componente": str,
    "estado": "ok" | "advertencia" | "critico" | "error",
    "mensaje": str,
    "datos": dict | None,
}
```

## 7. Clasificación global del equipo

**Fecha:** 2026-07-28

- **Verde:** todos los componentes en `ok`.
- **Amarillo:** al menos un `advertencia`, ningún `critico` ni `error`.
- **Rojo:** al menos un `critico` o `error`. Un componente que no se pudo
  diagnosticar (`error`) se trata con la misma severidad que uno realmente
  defectuoso (`critico`), porque es una incógnita, no una confirmación de
  buen estado.

## 8. Degradación elegante ante herramientas faltantes

**Fecha:** 2026-07-28

Si falta una herramienta del sistema (`smartctl`, `sensors`, etc.) o un
módulo de `backend/modules/` no existe/falla, ese componente queda marcado
como `"error"` sin detener el resto del escaneo. `backend/scanner.py`
importa cada módulo dinámicamente con `try/except ImportError` justamente
para esto.

## 9. Instalación de dependencias: apk, no pip

**Fecha:** 2026-07-28

`scripts/install_tools.sh` instala Flask y psutil con `apk add
py3-flask py3-psutil` (paquetes nativos musl) en vez de `pip install`.
Evita depender de un toolchain de compilación (gcc/musl-dev) para
dependencias que Alpine ya distribuye precompiladas, y evita el bloqueo de
`pip install` sin `--break-system-packages` en Alpine ≥3.19 (PEP 668).

## 10. Códigos de salida de `check_environment.sh`

**Fecha:** 2026-07-28

- **Python 3.10+, Flask o psutil faltantes → código 1 (bloqueante).** Sin
  esto el servidor Flask no arranca, no hay degradación posible.
- **Herramientas de diagnóstico faltantes → advertencia, código 0 (no
  bloqueante).** Misma filosofía que la decisión 8: una herramienta
  ausente reduce cobertura de diagnóstico, no debe impedir que el sistema
  arranque.

## 11. Migración de Alpine Linux a Debian Live

**Fecha:** 2026-08-08

Se abandona Alpine como sistema base y se migra a **Debian Live** (probado
con `debian-live-13.6.0-amd64-xfce.iso`). Supera lo dicho en la decisión 1
(stack) y la regla original "Nada de Ubuntu/Debian/systemd" — descartada
explícitamente por decisión del equipo, no por mí.

Motivos:
- La razón principal de elegir Alpine (RAM mínima) ya no aplica desde la
  decisión 3 — las laptops del colegio tienen 4-16GB reales.
- Fricción real y repetida probando en vivo: la imagen live mínima de
  Alpine no trae herramientas básicas (`lsblk`, `lscpu`, ni siquiera
  `wget`) sin conexión a internet, lo que complicó cada prueba offline.
- Debian tiene mejor soporte de hardware de fábrica (más firmware
  incluido) y el patrón "autologin + navegador en modo kiosk" está
  documentado hasta el cansancio para Debian/Ubuntu, mucho menos para
  Alpine + OpenRC.
- `apt` + `systemd` + glibc evitan los problemas de paquetes musl-only y
  la incertidumbre de mecanismos Alpine-específicos (ver decisión 13).

Qué NO cambia: el dashboard, los 7 módulos de diagnóstico, la paleta, el
contrato de módulos, la clasificación Verde/Amarillo/Rojo — todo eso es
independiente del sistema operativo base.

## 12. Instalación de dependencias en Debian: `apt`, no `apk`

**Fecha:** 2026-08-08

Supera la decisión 9. `scripts/install_tools.sh` se reescribió para
`apt-get install -y --no-install-recommends`, con
`DEBIAN_FRONTEND=noninteractive` para que ningún paquete se cuelgue
esperando una respuesta en un build desatendido. Nombres de paquete casi
idénticos a Alpine, salvo `py3-flask`/`py3-psutil` → `python3-flask`/
`python3-psutil` (convención de nombres de Debian). En Debian,
`sensors-detect` viene incluido dentro del paquete `lm-sensors` — no hace
falta el paquete aparte que sí exigía Alpine (`lm-sensors-detect`). Todo
lo que usamos vive en el repositorio `main` estándar, sin habilitar nada
extra (a diferencia de Alpine, donde `stress-ng`/`memtester` exigían el
repo `community`).

## 13. `create_iso.sh` v2: remaster de `filesystem.squashfs`, no overlay dinámico

**Fecha:** 2026-08-08

Supera parcialmente la decisión 5 (ya no está pospuesto: existe una v2 en
pruebas). Confirmado en vivo con `mount | grep squashfs`: Debian Live
monta su raíz como un `filesystem.squashfs` de solo lectura + una capa
`overlay` encima. A diferencia del mecanismo de Alpine v1 (`apkovl` +
cache, detectados por Alpine en tiempo de arranque según el hostname y la
ubicación de la cache — dos puntos marcados como inciertos en su momento),
acá **todo lo que quede horneado en un `filesystem.squashfs` nuevo es
exactamente lo que bootea**, sin detección ni adivinanza en el arranque.

Proceso: `unsquashfs` extrae el `squashfs` original a una carpeta de
trabajo → `chroot` ahí adentro (con `/proc /sys /dev` montados) →
`install_tools.sh` + copia del proyecto a `/opt/diagnostic-scanner-pc` +
servicio `systemd` + `/etc/issue` con la IP → `mksquashfs` comprime todo
de nuevo → `xorriso -boot_image any replay` arma la ISO final,
preservando el arranque BIOS/UEFI original tal cual (misma técnica que ya
se había definido para la v1 de Alpine).

## 14. Kiosk: autologin + X sin gestor de ventanas, Chromium en bucle

**Fecha:** 2026-08-08

Implementa la decisión 2 (dashboard local, X11 + navegador kiosk),
pendiente de configuración exacta hasta ahora.

- **Autologin** del usuario `user` en `tty1` vía override de
  `getty@tty1.service` (systemd) — sin esto, cada boot pediría login
  manual.
- **Sin gestor de ventanas separado** (ni XFCE completo, ni instalar uno
  nuevo tipo Openbox): `.xinitrc` lanza Chromium directo. `--kiosk` ya
  maneja pantalla completa sin decoraciones; agregar un WM solo para esto
  era complejidad sin beneficio claro.
- **Chromium corre dentro de un bucle `while true` en `.xinitrc`**: si se
  cierra (crash, `Alt+F4`, `Ctrl+W`, cualquier atajo que se nos haya
  escapado), vuelve a abrir en 2 segundos. Se prefirió esto a perseguir
  cada atajo de teclado de escape posible uno por uno — cubre el caso de
  raíz en vez de los síntomas conocidos.
- **DevTools deshabilitado** vía política administrada de Chromium
  (`/etc/chromium/policies/managed/kiosk.json`, `DeveloperToolsDisabled`),
  no por flag de línea de comandos — es el mecanismo oficial y más
  confiable para esto.
- **Menú contextual (clic derecho)** suprimido a nivel página, en
  `app.js` (`contextmenu` → `preventDefault()`). Chromium no tiene una
  política para desactivarlo en contenido web arbitrario; como el
  contenido es nuestro, se resuelve ahí.
- **Fallback a consola**: si `startx` falla (sin driver gráfico, por
  ejemplo) o Chromium/X se cierran del todo, `.bash_profile` cae a un
  mensaje de diagnóstico en la consola con la IP y la ruta al log de X
  (`/tmp/xorg.log`) — nunca queda una pantalla en blanco sin explicación.
  El servicio Flask (systemd, independiente de la sesión gráfica) sigue
  respondiendo por red aunque el kiosk visual falle.
- Los archivos viven en `build/overlay/`, que `create_iso.sh` copia tal
  cual al `chroot` — sin verificar en hardware real todavía (ver estado
  del smoke test).

## 15. Pivote de Debian Live a WinPE / Hiren's Boot PE

**Fecha:** 2026-08-12

Supera las decisiones 1 y 11 (que ya habían migrado de Alpine a Debian) —
segundo pivote de sistema base del proyecto. Motivo: las laptops del
colegio son equipos Windows, con mejor soporte de drivers nativos (WiFi,
batería, sensores) bajo Windows que bajo Linux genérico. El riesgo que la
decisión 2 ya marcaba como "conocido y aceptado" terminó siendo real en la
práctica: fricción real de detección de hardware e inestabilidad al leer
el medio de arranque en Debian Live.

Qué cambia: sistema base (Debian Live → Hiren's Boot PE), forma de leer
hardware (CLI Linux → WMI vía el paquete `wmi` de Python), Python (`apt` →
distribución embeddable portable en el USB), remaster del ISO
(`unsquashfs`/`chroot`/`mksquashfs`/`xorriso` → DISM sobre `boot.wim`,
pendiente de automatizar en Fase 2).

Qué NO cambia: el dashboard, el contrato de los 7 módulos, la paleta,
Flask, la clasificación Verde/Amarillo/Rojo.

Validado en hardware real el 2026-08-13: booteó con Ventoy en modo
WIMBOOT, corrió el Python portable, y diagnosticó correctamente una
laptop Lenovo distinta a la de desarrollo (plan completo en
`docs/superpowers/plans/2026-08-12-pivot-winpe-hirens-pe.md`).

Riesgo abierto, sin resolver: en esa misma prueba, `red.py` no detectó
ninguna interfaz de red física pese a que la laptop sí tiene tarjeta.
Falta confirmar si es un driver de red faltante en el paquete de Hiren's
PE (revisar Administrador de dispositivos) o una limitación del filtro
`PhysicalAdapter=True` de WMI bajo WinPE. Fase 2.

## 16. Bug de raíz: `sys.path` restringido por el Python embeddable

**Fecha:** 2026-08-13

Encontrado en la primera prueba en hardware real: `app.py` fallaba con
`ModuleNotFoundError: No module named 'scanner'` al correrlo con el
Python portable (`build/python-portable/`), pese a que `scanner.py` vive
en la misma carpeta que `app.py` y el mismo comando funciona sin problema
con un Python de instalación normal.

Causa: el paquete embeddable de Python trae un archivo `pythonXXX._pth`
que, cuando existe, desactiva por completo el agregado automático de la
carpeta del script a `sys.path` — comportamiento documentado de la
distribución embeddable, no un bug de Python en general. Activar
`import site` en ese archivo (necesario para que `pip` funcione, ver Fase
1 del plan WinPE) es justo lo que dispara la restricción.

Fix: `app.py` ahora inserta explícitamente su propia carpeta en
`sys.path` antes de importar `scanner`/`utils`, usando
`os.path.dirname(os.path.abspath(__file__))` — no cambia nada con un
Python normal (la carpeta ya estaba) y corrige el embeddable (antes
faltaba). Como `sys.path` es compartido por todo el proceso, un solo fix
en el punto de entrada (`app.py`) alcanza para `scanner.py` y los 7
módulos también, sin tocarlos uno por uno.

## 17. RAM: separar capacidad física de capacidad disponible al SO

**Fecha:** 2026-08-13

Encontrado en la misma prueba en hardware real: el dashboard mostraba
"Capacidad total: 5.85GB" en una laptop con 8GB instalados. `ram.py`
calculaba ese campo con `psutil.virtual_memory().total` (memoria que el
sistema operativo actual ve disponible), no con lo físicamente instalado
— y arrancar vía Ventoy en modo WIMBOOT reserva parte de la RAM para la
propia imagen de arranque, así que lo que ve el SO puede ser bastante
menor a lo instalado.

Fix: `ram.py` ahora suma `Capacity` de todos los módulos de
`Win32_PhysicalMemory` (dato físico real, no afectado por el modo de
arranque) para `capacidad_fisica_gb`, y deja `psutil` solo para
`capacidad_disponible_so_gb` y el porcentaje de uso — ambos valores se
muestran por separado en el panel de detalle, con nombres que no se
prestan a confundirlos. Confirmado en la propia PC de desarrollo: WMI
reporta 16GB físicos reales contra ~14.83GB que ve el SO en un boot
normal — la diferencia existe incluso fuera de USB, por RAM reservada de
fábrica/firmware.

## 18. Rediseño de interfaz: mapa físico + ficha + panel de detalle

**Fecha:** 2026-08-13

Reemplaza la grilla de tarjetas original (la ubicación del dashboard no
cambia, ver decisión 2 — solo su forma). Motivo: la grilla de tarjetas se
sentía genérica, sin relación visual con el objeto físico que se está
diagnosticando.

Diseño final, combinando dos propuestas visuales que gustaron por
separado:
- **Mapa físico**: un punto de estado por componente, ubicado en su
  posición aproximada real sobre una silueta de laptop (SVG), en vez de
  una lista desconectada del objeto.
- **Ficha de inspección**: una fila por componente con franja de
  severidad, ícono, mensaje y chip de estado — se lee como un informe
  técnico, no como tarjetas sueltas.
- **Selección enlazada**: pasar el mouse o hacer clic en un punto del
  mapa resalta la fila correspondiente en la ficha, y viceversa.
- **Panel de detalle al hacer clic**: expone todo el diccionario `datos`
  que cada módulo ya devolvía y que el frontend anterior ignoraba por
  completo (solo usaba `estado`/`mensaje`). Un formateador genérico en
  `app.js` recorre las llaves de `datos` sin lógica particular por
  componente, y desglosa arrays anidados (ej.
  `almacenamiento.datos.discos`, `red.datos.interfaces`) en subitems. Si
  un módulo agrega un campo nuevo a futuro, aparece solo en el detalle
  sin tocar el frontend.

Paleta de colores sin cambios (sigue siendo la definida en
`config/palette.css`) — el rediseño es de layout e información, no de
color. Validado en hardware real el 2026-08-13, con clic en los 7
componentes confirmando el panel de detalle en cada caso.

## 19. Fidelidad al documento institucional: GPU/ventiladores y recomendación accionable

**Fecha:** 2026-08-13

Al revisar el documento del Semillero (`SEMILLERO DE MANTENIMIENTO_
DIAGNOSTIC SCANNER PC.docx`) contra el estado real del software, aparecieron
dos promesas concretas de la sección OBJETIVOS (Fase II) que la app no
cumplía todavía. Se cierran ambas en esta ronda — plan completo en
`docs/superpowers/plans/2026-08-13-fidelidad-documento-y-cierre-fase2.md`.

- **"Umbrales térmicos de CPU y GPU" + "telemetría de ventiladores"**:
  `cpu.py` ahora también lee temperatura de GPU y velocidad de
  ventiladores vía LibreHardwareMonitorLib (misma librería ya integrada
  para `fuente_poder.py`, mismas DLLs en `backend/native/lhm/` — no fue
  necesario agregar una dependencia nueva). No se agregó un 8vo
  componente: son campos nuevos dentro de `cpu.py`, porque GPU/ventilador
  son telemetría de enfriamiento, mismo dominio que la temperatura de
  CPU que el módulo ya reportaba. Verificado en hardware real: en la
  laptop de desarrollo ambos se degradan a `None`/`[]` (no expone esos
  sensores) — comportamiento correcto, no un fallo.

- **"Qué acción correctiva debe ejecutarse"** (Introducción) / "emitir
  recomendaciones claras" (Antecedentes, como diferenciador frente a
  CPU-Z/HWiNFO): hasta ahora la app clasificaba y describía el hallazgo,
  pero no sugería una acción. Se agregó `recomendacion` al contrato de
  los 7 módulos (`componente`, `estado`, `mensaje`, `datos`,
  `recomendacion`) — texto fijo por módulo y por estado (`ok` = vacío,
  el resto con una acción concreta, ver la tabla completa en el plan).
  `scanner.py._cumple_contrato` exige la llave nueva; el frontend la
  muestra en el panel de detalle, destacada con un borde de acento
  (`.detalle-recomendacion`), separada del resto del detalle técnico.

Dos promesas del mismo documento quedaron **fuera de esta ronda**, a
propósito, por necesitar una decisión de alcance/arquitectura antes de
tocar código — documentadas como roadmap en el plan, no omitidas en
silencio:
- **Pruebas de estrés activas** (Fase IV: comparar antes/después) — nunca
  implementadas, ni en la versión Linux ni esta. Los 7 módulos son
  lecturas pasivas, ninguno carga el hardware activamente.
- **Comparar dos escaneos** — tensiona con la decisión 4 (persistencia
  stateless). Implementarlo bien requiere decidir si guardar el escaneo
  anterior en memoria alcanza, o si hace falta romper "stateless" más en
  serio.

Una promesa del documento (`ciclos de desgaste de RAM`) se identificó
como **no implementable de forma honesta**: no es una métrica que la RAM
de consumo exponga (a diferencia de SSD, que sí tiene wear-leveling
medible por SMART) — no hay dato real que leer, así que no se inventó
uno. Queda anotado para revisar la redacción del documento en vez de
perseguir un campo de software que no puede existir.

## 20. Clasificación de 5 niveles: NORMAL/ADVERTENCIA/SOSPECHA/CRITICO/NO_DETERMINADO

**Fecha:** 2026-08-18

Supera la decisión 6 (contrato de módulos: solo `"ok"/"advertencia"/
"critico"/"error"`) y la decisión 7 (clasificación global Verde/Amarillo/
Rojo). Motivado por una revisión técnica externa del reporte de
diagnóstico, que señaló que el sistema de 3 colores mezclaba dos cosas
distintas bajo una sola etiqueta: "no se pudo leer este sensor" y "se leyó
y está mal" caían ambos en la misma severidad, y "advertencia" agrupaba
tanto observaciones menores (uso de RAM alto) como evidencia real de un
posible problema (errores de paquetes de red, salud reducida reportada
por el propio Windows Storage Health).

**Decisión explícita e informada de divergir del documento institucional
del Semillero**: el documento define literalmente 3 categorías (Verde/
Amarillo/Rojo). Se le señaló este conflicto al usuario antes de
implementar; decidió proceder igual, priorizando que el reporte sea
técnicamente honesto sobre la fidelidad literal al texto ya entregado. El
documento no se modifica (decisión de alcance del profesor, ver decisión
en la sección de estructura del `.docx`); la app diverge conscientemente
en este punto puntual.

Los 5 estados, de mayor a menor severidad (`_SEVERIDAD` en
`backend/scanner.py`, mismo orden replicado en `frontend/static/js/
app.js` como `SEVERIDAD`):

1. **CRITICO** — confirmado defectuoso (ej. salud SMART crítica, batería
   <40% de diseño, ninguna interfaz de red con enlace).
2. **SOSPECHA** — evidencia real de un posible problema, pero no una
   falla confirmada (ej. salud SMART "reducida" según Windows, enlace de
   red activo con errores de paquetes, voltaje de CPU fuera de rango
   físico).
3. **NO_DETERMINADO** — no se pudo leer el dato (WMI sin respuesta,
   permisos, sensor ausente). Pesa más que "advertencia" (no saber es más
   serio que un problema menor ya identificado) pero menos que "sospecha"
   (evidencia real pesa más que ausencia de datos).
4. **ADVERTENCIA** — se leyó correctamente y el valor amerita monitoreo,
   sin evidencia de falla (ej. uso de RAM elevado).
5. **NORMAL** — se leyó correctamente y está dentro de rango esperado.

El veredicto global toma el estado más severo entre los 7 componentes
(mismo mecanismo de rollup que ya existía, solo con 5 niveles en vez de
3). Color nuevo: `--color-naranja` en `config/palette.css`, para
"sospecha" — "no_determinado" reutiliza `--color-texto-secundario` (gris
= neutral/desconocido) en vez de sumar un gris casi idéntico.

Dos bugs reales de la revisión externa se corrigieron en la misma ronda,
como soporte necesario para que "sospecha" signifique algo real:

- **`almacenamiento.py` mezclaba discos USB con discos internos**: el
  veredicto de almacenamiento se calculaba sobre *todos* los
  `Win32_DiskDrive`, incluida cualquier memoria USB conectada — el propio
  USB de arranque del proyecto se autoevaluaba como si fuera el disco de
  la laptop. Ahora se separan `discos_internos`/`discos_externos`
  (`interfaz == "USB"`) y solo los internos afectan `estado`; los
  externos se siguen reportando en `datos` para inventario. Verificado en
  hardware real: un pendrive Kingston conectado queda en
  `discos_externos` sin afectar el resultado, mientras el SSD Samsung
  interno sigue determinando el estado normalmente.
- **`fuente_poder.py` sonaba más autoritativo de lo que sus datos
  permiten**: el mensaje de estado normal ahora aclara explícitamente que
  la telemetría de voltaje leída es del regulador interno del procesador
  (VID/SVI2), no de los rieles de la fuente de poder, la batería ni el
  cargador — evita que un lector interprete "voltaje normal" como "fuente
  de poder healthy" cuando el módulo nunca midió eso.

Se revisaron y quedaron **fuera de esta ronda, a propósito** (mismo
patrón que la decisión 19): parseo de errores WHEA, diagnóstico de
drivers, motor de correlación entre componentes, muestreo térmico
sostenido bajo carga, y pruebas de rendimiento de disco. Motivo: exceden
el alcance de 7 componentes ya definido y entregado en el documento
institucional, y la prioridad inmediata del equipo es cerrar y usar el
proyecto, no ampliar alcance. Quedan como roadmap, no como omisión
silenciosa.

Frontend actualizado en el mismo cambio: `app.js` (`CHIP_TEXTO`,
`SEVERIDAD`, `calcularVeredicto`, `renderizarResumen`, `DATOS_MOCK`,
etiqueta de campo `externo`) y `style.css` (`.punto`/`.franja`/
`.fila-chip`/`.sello` con reglas para los 5 estados). Validado en vivo:
servidor Flask real + navegador, con datos mock ejercitando los 5 colores
y un escaneo real de hardware confirmando la separación de discos
interno/externo.

## 21. GPU como sub-info del Procesador (no 8vo componente) + corrección de `cpu.py`

**Fecha:** 2026-08-18

Motivado por una segunda revisión técnica externa del dashboard ya con el
sistema de 5 niveles. A diferencia de la ronda anterior, esta vez el
diseño propuesto por la revisión se adoptó casi sin cambios — resultó
más consistente con decisiones ya tomadas que la propuesta inicial de
este mismo equipo.

**GPU no es un 8vo componente.** Se había propuesto agregar `"gpu"` a
`COMPONENTES` en `scanner.py`; se descartó antes de programarlo. Razón:
la decisión 19 ya había resuelto esto — GPU/ventiladores viven dentro de
`cpu.py` por compartir dominio térmico, precisamente para NO romper el
contrato de 7 componentes del documento institucional. Agregar un 8vo
componente ahora habría contradicho esa decisión sin una razón nueva de
peso. En cambio, `backend/modules/gpu.py` es un módulo **auxiliar**:
expone `obtener_datos()` (no `diagnosticar()`), no está en `COMPONENTES`,
y no genera veredicto propio. `cpu.py` lo importa y anida el resultado
como `datos["gpu"]` — identidad vía `Win32_VideoController` (nombre,
driver; sin `AdapterRAM`, campo con bug documentado de Microsoft en
drivers WDDM modernos) y temperatura/uso vía LibreHardwareMonitorLib
(misma librería ya integrada).

**Sin umbrales de crítico/advertencia propios para GPU.** Se había
propuesto reusar los umbrales de CPU (70°C/85°C); se descartó. Razón:
no hay base técnica para asumir que esos límites aplican a una GPU
integrada que comparte encapsulado y presupuesto térmico con el CPU —
inventar un umbral "razonable" es exactamente el tipo de sobre-confianza
que el sistema de 5 niveles existe para evitar. GPU queda como
telemetría pura: se muestra el dato o se muestra que no está disponible,
sin clasificar.

**Bug real encontrado y corregido: `cpu.py` violaba su propia regla
nueva.** `_clasificar()` clasificaba "temperatura no disponible" como
`"normal"` — el mismo error de fondo que motivó el sistema de 5 niveles
(confundir "no se pudo medir" con "se midió y está bien"), ya corregido
en `bateria.py` y `almacenamiento.py` esta misma sesión pero pasado por
alto en `cpu.py`. Corregido a `"no_determinado"` con mensaje explícito
("detectado, pero no se pudo obtener su temperatura mediante los
sensores disponibles"). Importante: `_clasificar(nombre, temperatura)`
nunca recibió `datos_gpu` como parámetro — que la GPU no tenga sensor de
temperatura es estructuralmente imposible que arrastre el estado del
Procesador; solo la temperatura del CPU decide su propio estado.

**Bug real encontrado durante la verificación (no en la revisión
externa): sensor de uso de GPU equivocado.** LibreHardwareMonitor expone
varios sensores `Load` por GPU (motores D3D individuales — 3D, Compute,
Video, Copy — muy volátiles) más uno agregado llamado `"GPU Core"`. La
primera versión tomaba el primer sensor `Load` encontrado (`"D3D 3D"`),
y en una lectura puntual llegó a marcar 217% de uso — un contador de
Windows dando un valor puntual imposible. Corregido: se prioriza el
sensor `"GPU Core"` (nombre consistente en los 3 backends de
LibreHardwareMonitor — AMD/NVIDIA/Intel) y se descarta cualquier lectura
fuera de [0, 100] en vez de mostrarla.

**Frontend: renderer recursivo genérico, no un caso especial para
GPU.** `_renderizarCuerpoDatos()` en `app.js` ya sabía desglosar arrays
(`discos_internos`, `interfaces`) en subitems; se le agregó el mismo
tratamiento para objetos anidados sueltos, con la misma función llamada
recursivamente. Un módulo futuro puede anidar lo que necesite (ej.
`bateria.cargador`) sin volver a tocar este renderer.

Verificado en vivo, los 3 escenarios pedidos: (1) temperatura de CPU
disponible → clasifica normal/advertencia/crítico según umbral, probado
llamando `_clasificar()` directo con valores de prueba (esta laptop de
desarrollo no expone `MSAcpi_ThermalZoneTemperature`, así que este caso
no se pudo dar de forma natural en hardware real); (2) temperatura no
disponible → `NO_DETERMINADO`, mensaje sin la palabra "normal"; (3)
escaneo real completo → CPU en `NO_DETERMINADO` por su propia
temperatura ausente, GPU con nombre/driver identificados y temperatura
en `null` (se muestra como "—" en el detalle), veredicto global
`NO_DETERMINADO` sin tapar el `ADVERTENCIA` real de RAM en su propia
fila — confirma que el rollup de severidad sigue funcionando con datos
reales mixtos.

Precisión pedida en la misma revisión sobre cómo se documentó lo
anterior: de los "3 escenarios verificados", 2 fueron pruebas directas
de `_clasificar()` con valores de prueba (no hay hardware a mano que
exponga `MSAcpi_ThermalZoneTemperature`), y 1 fue una integración real
de extremo a extremo. Queda anotado acá para no repetir la imprecisión.

## 22. Prioridad de NO_DETERMINADO corregida + selección de sensor GPU endurecida

**Fecha:** 2026-08-18

Tercera revisión técnica externa sobre el mismo dashboard, ya con GPU
como sub-info del Procesador (decisión 21). A diferencia de las dos
rondas anteriores, esta vez casi todo el diseño previo se mantuvo sin
cambios — la revisión encontró dos problemas puntuales, ambos reales.

**1. Orden de severidad: `no_determinado` pasa a pesar MENOS que
`advertencia`, no más.** Supera parcialmente la decisión 20. Orden
anterior: `critico > sospecha > no_determinado > advertencia > normal`.
Orden nuevo: `critico > sospecha > advertencia > no_determinado >
normal`.

La decisión 20 justificaba el orden anterior comparando "no saber" con
"problema menor" como si fueran el mismo eje de severidad. No lo son:
uno es confianza de medición, el otro es condición del componente.
Con el orden anterior, un componente con evidencia real de un problema
(ej. SSD en `advertencia`) podía quedar tapado en el veredicto global
por un sensor sin dato en OTRO componente (ej. temperatura de CPU en
`no_determinado`) — el titular terminaba comunicando "no sé" cuando en
realidad sí había evidencia accionable. Dado que el propósito explícito
del veredicto es ayudar a decidir qué revisar físicamente antes de
abrir el equipo, la evidencia accionable debe pesar más que un vacío de
medición en un componente no relacionado.

Se mantiene sin cambios que `no_determinado` pese más que `normal`: esa
parte de la decisión 20 seguía siendo correcta — un componente sin datos
no debe pasar como "todo bien" en el veredicto.

Verificado con el ejemplo exacto de la revisión (SSD en `advertencia` +
CPU en `no_determinado` simulados) y confirmado también con datos reales
sin simular: en un escaneo real de la laptop de desarrollo, RAM salió
`advertencia` (uso elevado real) y CPU salió `no_determinado` (sin
sensor de temperatura) al mismo tiempo — el veredicto dio `ADVERTENCIA`,
no `NO_DETERMINADO`. Confirmado también en el navegador tras recargar
`app.js` (el primer intento de verificación mostró el resultado viejo
por caché del script en la pestaña ya abierta, no por un bug — quedó
como recordatorio de recargar la página después de tocar JS, no solo el
backend).

**2. Bug real en la selección de sensor de uso de GPU (decisión 21):
caía a un sensor de respaldo cuando no debía.** La versión anterior, si
`"GPU Core"` faltaba o daba un valor fuera de rango, tomaba el primer
sensor `Load` individual (ej. `"D3D 3D"`) como respaldo. Probado con
datos simulados (`GPU Core` corrupto en 217% + `D3D 3D` válido en 20%):
el resultado era `20%`, no `null` — mostrando un número real, pero del
motor equivocado, bajo el mismo campo. Corregido: sin fallback. Si
`"GPU Core"` no está presente o no da un valor en `[0, 100]`, el campo
queda en `None`. Mismo criterio aplicado a la temperatura de GPU: se
agregó una validación de rango físico (0-110°C, mismo espíritu que los
límites de voltaje de `fuente_poder.py`).

Para poder probar la selección sin mockear objetos .NET de
LibreHardwareMonitor, `gpu.py` se separó en dos partes: `_telemetria()`
solo recolecta lecturas crudas de sensores en listas de Python;
`_elegir_temperatura()`/`_elegir_uso()` deciden en cuál confiar, como
funciones puras testeables con datos simples. `gpu.py` ahora tiene un
`_demo()` ejecutable (`python modules/gpu.py`) que prueba los 3
escenarios pedidos por la revisión: sensor agregado sano, sensor
agregado corrupto (no debe caer a un motor individual), y sensor
agregado ausente (misma conclusión).

Límite reconocido y no resuelto: la coincidencia por nombre exacto
`"GPU Core"` se basa en que ese es el nombre que usa LibreHardwareMonitor
en sus 3 backends (AMD/NVIDIA/Intel) — no verificable más allá del
hardware disponible para probar (una laptop con GPU integrada AMD). En
una GPU donde ese nombre no exista, `porcentaje_uso` queda en `None` en
vez de adivinar con otro sensor — comportamiento intencional, no una
limitación a ocultar.

**Se evaluó y se descartó agregar un campo `motivo` separado del
`estado`** para distinguir "no se pudo medir" de "se pudo medir y está
mal". Ya está resuelto sin campo nuevo: cada `no_determinado` del
proyecto ya distingue el motivo en `mensaje` (ej. bateria.py: "faltan
datos de capacidad de diseño" vs. "no se pudo consultar WMI"; cpu.py:
"no se pudo obtener su temperatura" vs. mensajes de `_resultado_error`),
y el color gris de `no_determinado` ya lo separa visualmente de
advertencia/sospecha/crítico en la interfaz. Un campo estructurado
adicional habría duplicado información que ya existe.

## 23. Cierre de prototipo a producto demostrable: cobertura, trazabilidad, modo demo y regresión

**Fecha:** 2026-08-19

Cuarta revisión externa, esta vez centrada en llevar el proyecto de
"prototipo funcional" a algo defendible en la sustentación — sin agregar
sensores nuevos, explícitamente. Se adoptaron 6 de las propuestas; una
se cambió por una versión más barata con el mismo objetivo.

- **Suite de regresión** (`backend/test_scanner.py`): mismo estilo que
  el `_demo()` de `gpu.py` (asserts simples, sin framework nuevo). Cubre
  la clasificación de cada módulo con datos simulados, la consistencia
  interna de `scanner.py` (`ESTADOS_VALIDOS` vs. `_SEVERIDAD`, que GPU
  no esté en `COMPONENTES`) y el caso exacto de la decisión 22 (SSD en
  `advertencia` + CPU en `no_determinado` → veredicto `ADVERTENCIA`).
- **Cobertura del escaneo** (`scanner._calcular_cobertura`): qué
  porcentaje de los 7 componentes se pudo leer, no qué tan sano está el
  equipo — son ejes distintos (misma distinción que decisión 22).
  Derivado directo del conteo de `no_determinado` que ya existía, sin
  ningún cálculo nuevo. Se muestra en el dashboard junto al resumen y en
  el reporte descargable.
- **Tiempo por módulo** (`scanner.ejecutar_escaneo_completo`): cada
  componente se cronometra con `time.perf_counter()`. Va al reporte, no
  al dashboard — es un dato de evidencia/depuración para la
  sustentación, no algo que el técnico necesite ver en el uso diario.
  Reveló algo real en la laptop de desarrollo: `red` y `cpu` dominan el
  tiempo total (~4-11 s de un escaneo de ~5-11 s), presumiblemente por
  las llamadas a LibreHardwareMonitor — dato útil, no solo curioso.
- **ID de diagnóstico** (`scanner._generar_id_diagnostico`): string
  `DSPC-AAAAMMDD-HHMM-XXXX`, nunca persistido — no rompe la decisión 4
  (stateless). Los últimos 4 caracteres son un hash corto del contenido
  del escaneo, no aleatorios.
- **Reporte descargable ampliado** (`utils.generar_reporte_texto`):
  ahora incluye identificación del equipo (fabricante/modelo/BIOS, ya
  vivía en `mainboard.datos`), cobertura, tiempo total y por módulo, y
  una sección de limitaciones — lista los componentes en
  `no_determinado` de ESE escaneo más una lista fija de lo que el
  proyecto no mide a propósito (pruebas de estrés, WHEA, comparación
  antes/después, salud de drivers), reusando texto ya decidido en las
  decisiones 19/20/22 en vez de redactar algo nuevo.
- **Modo demo** (`app.js::verModoDemo`): botón nuevo junto a "Escanear
  Sistema". Reusa `DATOS_MOCK`, que ya ejercitaba los 5 estados a la vez
  desde la decisión 20 — no fue necesario crear datos nuevos. Banner
  fijo y visible ("⚠ Datos simulados — no es un diagnóstico real")
  mientras está activo; cualquier escaneo real lo cierra automáticamente.
  Pensado para la sustentación: no depender de que la laptop de turno
  tenga justo algo mal para poder mostrar los 5 colores.

**Cambiado respecto a lo propuesto:** en vez de reescribir los 8 módulos
para que las reglas de clasificación vivan en una tabla de datos
explícita, se documentaron las reglas ya existentes en
`docs/reglas-recomendaciones.md` (una tabla por módulo, extraída del
código real). Motivo: el código ya *es* "condición → severidad →
recomendación", solo que como funciones Python — reescribir 8 módulos
que ya funcionan por una ganancia mayormente de presentación es riesgo
real por beneficio marginal, a días de cerrar. La tabla en Markdown
cumple el mismo objetivo (defender el sistema ante el profesor) sin
tocar código que ya está probado en hardware real.

**Fuera de esta ronda, sin cambios respecto a las decisiones 19/20/22:**
WHEA, pruebas de estrés, benchmark, comparación antes/después, IA,
motor de correlación, historial de diagnósticos, base de datos, 8vo
componente. Coincide explícitamente con la revisión que motivó esta
ronda: "no agregaría todavía" — el resto de las mejoras es sobre cómo
se demuestra lo que el proyecto ya hace, no sobre agregar más para que
haga.

Verificado: `test_scanner.py` pasa completo; escaneo real en la laptop
de desarrollo confirmó cobertura 86 % (6/7, coincide con el ejemplo de
la propia revisión), tiempos reales por módulo, reporte con las
secciones nuevas, y modo demo alternando correctamente con un escaneo
real (el banner se oculta solo, la cobertura no se muestra con datos
simulados).

## 24. Bug de arranque real: `create_pe.ps1` reescrito, sin DISM, causa raíz encontrada por bisección

**Fecha:** 2026-08-19/20

Primera prueba de arranque desatendido de la ISO automatizada (decisión
del smoke test original) en la PC real del colegio. Falló, en tres
formas distintas a lo largo de tres rondas de diagnóstico — cada una
aislando una sola variable a la vez, probando en hardware real después
de cada cambio, nunca solo revisando el script.

**Ronda 1 — memoria insuficiente para WIMBOOT.** La versión original de
`create_pe.ps1` inyectaba Python portable y Chromium portable dentro de
`boot.wim` con DISM. Eso lo dejaba en ~2.25GB comprimido; en modo
WIMBOOT, Windows necesita descomprimir esa imagen completa en RAM antes
de arrancar nada. En la laptop real del colegio (8GB de RAM), el Boot
Manager falló con un error legible: `0xc0000017` ("not enough memory to
create a ramdisk device"). Fix intentado: sacar Python/Chromium/el
proyecto de `boot.wim` y volver a dejarlos sueltos en la unidad USB
(misma estructura ya validada a mano el 13 de agosto, antes de que
existiera este script) — `boot.wim` bajó a 1.81GB.

**Ronda 2 — seguía fallando, sin memoria de por medio.** Con `boot.wim`
más liviano, el arranque seguía fallando — esta vez sin error legible,
rebotando al menú de Ventoy antes de llegar siquiera a Windows Boot
Manager, en modo WIMBOOT y en modo normal por igual. Se descartó por
bisección: una ISO original de Hiren's PE sin modificar arranca bien en
la misma laptop (mismo Ventoy, mismo modo) — así que el problema no era
Ventoy ni la laptop, era algo de nuestra ISO reconstruida.

**Ronda 3 — causa raíz real: la fecha de modificación de un archivo
editado.** Se agregó un modo `-SoloDiagnostico` al script (mount+save de
`boot.wim` con DISM sin ningún cambio de contenido) para aislar si el
problema era DISM tocando el WIM o el contenido inyectado — **también
rebotaba igual**, aun sin ningún cambio real. Eso descartó "contenido" y
apuntó a DISM. Se reescribió el script para no tocar `boot.wim` en
absoluto: el autoarranque se logra editando `HBCD_PE.ini` como texto
plano — un archivo que Hiren's PE ya trae pensado exactamente para esto
(vive suelto en la raíz de la ISO, fuera de `boot.wim`; el propio
archivo original trae un ejemplo comentado usando `Y:` como letra
estable del medio de arranque, sin necesidad de recorrer letras de
unidad). Con eso, **también rebotaba** — descartando a DISM como única
causa.

Bisección final, cada build probada en hardware real: una ISO
reconstruida con `oscdimg` sin ningún cambio arranca bien. La misma ISO
con la única edición del `.ini` (línea `EXEC Y:\iniciar.bat`) rebota.
La diferencia entre ambas: el archivo editado queda con fecha de
modificación de **hoy**, rodeado de miles de archivos originales
fechados **2021**. Restaurando la fecha de modificación original del
`.ini` después de escribirle la línea nueva (`LastWriteTime`/
`CreationTime` capturados antes de editar, reaplicados después) —
**arrancó bien**, confirmado en la laptop real del colegio.

No se investigó el mecanismo exacto por el que una fecha "nueva" en un
archivo rodeado de fechas "viejas" rompe el arranque (sospecha: UDF o el
propio Ventoy son sensibles a esa discrepancia) — no hacía falta
entenderlo del todo para tener un fix que funciona y está verificado en
hardware real dos veces (con y sin la restauración de fecha, resultado
opuesto en cada caso).

**Cambios que quedaron en `create_pe.ps1`:**
- Ya no usa DISM en absoluto (`Mount-WindowsImage`/`Dismount-WindowsImage`
  desaparecieron del script) — `boot.wim` viaja intacto.
- El autoarranque se configura editando `HBCD_PE.ini`, restaurando su
  fecha de modificación original después de escribir.
- Como ya no depende de DISM, **ya no necesita PowerShell como
  Administrador** — todo el pipeline (montar la ISO original con
  `Mount-DiskImage`, copiar archivos, editar el `.ini`, generar la ISO
  con `oscdimg`) corre sin elevación. Verificado corriendo el script
  completo sin privilegios de administrador.
- Python, Chromium y el proyecto se mantienen sueltos en la unidad USB,
  sin cambios respecto a la decisión de la ronda 1.

**Resultado final, confirmado en la laptop real del colegio:** el USB
arranca sin ninguna intervención manual — Ventoy → WIMBOOT → escritorio
de Hiren's PE → el dashboard (Chromium en modo kiosk) se abre solo,
sin que el técnico toque nada. Esta era la última pieza pendiente del
proyecto (ver decisión 15 y el smoke test original) — con esto el flujo
completo, de USB conectado a diagnóstico visible en pantalla, quedó
verificado de punta a punta en hardware objetivo real, no solo en la
laptop de desarrollo.

**CORRECCIÓN (ver decisión 25): este último párrafo fue prematuro.** Lo
que se confirmó de verdad en esta ronda fue que la ISO arranca hasta el
escritorio de Hiren's PE — el autoarranque específico (`EXEC
Y:\iniciar.bat` en `HBCD_PE.ini`) NO disparó nada solo. La letra "Y:"
resultó ser una convención de Hiren's PE arrancando por su instalador
nativo, no de Ventoy. Queda como aprendizaje real, no se borra: la
ronda 4 (decisión 25) corrige esto con el fix real.

## 25. Autoarranque real: Ventoy no respeta la letra "Y:", y bug de empaquetado de `pythonnet`

**Fecha:** 2026-08-20

Continuación directa de la decisión 24. Dos hallazgos más, ambos en la
misma sesión de pruebas en la laptop real del colegio (un Lenovo
LNVNB161216 con AMD Ryzen 3 5300U — la segunda laptop real distinta a
la de desarrollo que corre este proyecto).

**1. La convención "Y:" de HBCD_PE.ini no aplica arrancando por Ventoy.**
El fix de la decisión 24 (`EXEC Y:\iniciar.bat`) hizo que la ISO
arrancara bien hasta el escritorio de Hiren's PE — pero el autoarranque
no disparó nada. Diagnosticado en vivo, en la propia laptop: abriendo
`Command Prompt` y corriendo `Y:\iniciar.bat` a mano, Windows respondió
"is not recognized" — la unidad `Y:` no existe en absoluto en esa
sesión. Buscando con un bucle de letras (`for %a in (D E F ... W) do @if
exist %a:\iniciar.bat echo ...`), el archivo apareció en `E:`. La
convención "Y:" que trae de fábrica `HBCD_PE.ini` es específica de
Hiren's PE arrancando con su propio creador de USB — Ventoy le asigna
la letra que le toque, sin garantía de cuál.

Fix: se volvió a usar DISM para escribir el autoarranque en la carpeta
de Inicio de Windows dentro de `boot.wim` (como en la v1 del script),
pero esta vez con el script recorriendo las letras de unidad posibles
(igual que ya se hacía en un intento anterior, abandonado sin necesidad
cuando se creyó que DISM era la causa raíz de la decisión 24 — no lo
era, la causa raíz siempre fue la fecha del archivo) **y** restaurando
la fecha de `boot.wim` después de que DISM lo guarda. Combina las dos
piezas ya confirmadas por separado: autoarranque que no depende de una
letra fija, y la fecha de modificación preservada.

Pendiente de confirmar en hardware real: esta versión combinada todavía
no se probó — es la próxima ISO a generar y arrancar.

**2. Bug real de empaquetado: `pythonnet` nunca se instaló en el Python
portable.** Con el USB corriendo el dashboard a mano (via `E:\iniciar.bat`),
el primer escaneo real en esta laptop mostró `Fuente de Poder` en
`NO_DETERMINADO` con el mensaje "No se pudo cargar LibreHardwareMonitorLib:
No module named 'clr'". Investigado: `build/python-portable/Lib/site-packages/`
nunca tuvo el paquete `pythonnet` instalado — solo Flask, psutil, WMI y
pywin32. Todas las pruebas anteriores de `fuente_poder.py`/`cpu.py` en
la laptop de desarrollo pasaron porque se corrían con el Python del
*sistema* (que sí tiene `pythonnet` instalado ahí, por separado), nunca
con `build/python-portable\python.exe` — el mismo intérprete que
realmente viaja en el USB. Una brecha real de verificación: probar en
la laptop de desarrollo no es lo mismo que probar con el binario exacto
que se despliega.

Fix: `build/python-portable\python.exe -m pip install pythonnet`.
Verificado con el propio Python portable (no el del sistema): `import
clr` y `clr.AddReference("LibreHardwareMonitorLib")` cargan bien, y
`fuente_poder.diagnosticar()` corrido de punta a punta devuelve
`"estado": "normal"` con los 10 sensores de voltaje reales, en vez de
`no_determinado`. Mismo mecanismo que usan `cpu.py` (GPU/ventiladores) y
`gpu.py` — el fix los cubre a los tres, no hizo falta repetirlo módulo
por módulo.

Pendiente: copiar el `python-portable` corregido a la unidad USB
(reemplaza la copia que se sincronizó antes de este fix) — se hace en
cuanto el USB vuelva a estar conectado a la PC de desarrollo.

## 26. USB de 64GB perdido/robado en el colegio; primera prueba real del autoarranque final revela que la carpeta de Inicio no dispara nada

**2026-08-21.** La USB de 64GB con la que se venían haciendo todas las
pruebas de arranque se perdió (robo, en un descuido en la técnica) antes
de poder confirmar en hardware real si el autoarranque de la decisión 25
(carpeta de Inicio de Windows dentro de `boot.wim`, vía DISM) funcionaba
de verdad — la última confirmación física había sido para el enfoque
anterior (`HBCD_PE.ini` + `Y:`), ya abandonado por la letra fija.

Se consiguió una USB de reemplazo de 16GB (bastante: la ISO final pesa
~3.3GB, más ~870MB de `python-portable`/`chromium` sueltos). Se preparó
Ventoy de nuevo y se copiaron la ISO y las carpetas sueltas ya
construidas en esta PC — nada del proyecto se había perdido, solo el
medio físico de arranque.

**Primera prueba real de la versión final (carpeta de Inicio + DISM):**
arranca bien, el escritorio de Hiren's PE carga completo (confirmado con
hora exacta), pero después de 4 minutos de espera no aparece ninguna
interfaz — el autoarranque nunca se disparó. Ejecutando `iniciar.bat` a
mano (doble clic desde el Explorador) todo funciona: Flask arranca,
Chromium abre, el diagnóstico corre bien sobre hardware real (7
componentes leídos correctamente, salvo la tarjeta de red sin enlace
activo — comportamiento esperado, no es un bug).

**Causa probable:** Hiren's PE lanza Explorer directo como shell, sin
pasar por el flujo normal de logon de Windows (winlogon/userinit) — que
es justamente lo que procesa la carpeta de Inicio en un Windows real. Es
coherente con la decisión 25: ahí, el mecanismo de `HBCD_PE.ini`
(`_SUB ExtPrograms`) **sí** disparó un intento de `EXEC` (apuntando a la
letra equivocada, pero disparó), mientras que acá la carpeta de Inicio no
disparó nada en absoluto — evidencia de que son mecanismos distintos y
solo uno de los dos está realmente confirmado como activo en este build
de Hiren's PE.

**Fix:** se vuelve a `HBCD_PE.ini` como único mecanismo de autoarranque
(se abandona la carpeta de Inicio y DISM por completo), ahora con el
mismo recorrido de letras D-W de la decisión 25 en vez de una letra fija
`Y:`. La línea activada en la sección `_SUB ExtPrograms`:

```
EXEC @%WinDir%\System32\cmd.exe /c for %D in (D E F G H I J K L M N O P Q R S T U V W) do if exist %D:\iniciar.bat call %D:\iniciar.bat
```

(`@` = correr en segundo plano, sintaxis documentada en el propio
`HBCD_PE.ini`; `%WinDir%` ya se usa en los `EXEC` nativos de la sección
de teclado del mismo archivo, así que la expansión de esa variable está
confirmada). Se preserva la fecha original de `HBCD_PE.ini` después de
editarlo (mismo mecanismo que la decisión 24/hallazgo 3).

Efecto colateral bueno: al ya no usar DISM, `create_pe.ps1` no necesita
más PowerShell como Administrador — se simplifica el script y se elimina
esa fricción.

**Bug aparte, mismo ciclo de pruebas:** en el arranque manual, Chromium
abrió antes de que Flask estuviera listo (`ERR_CONNECTION_REFUSED`,
recuperado solo ~1 minuto después). Causa: `app.py` corría con
`debug=True`, cuyo reloader de Werkzeug bifurca un segundo proceso y
tarda bastante más en bindear el puerto que un arranque sin reloader —
ya estaba documentado como pendiente en un comentario del propio
`error_500` ("se use debug=False en la build final para la USB"), pero
no se había aplicado. Fix: `debug=False` en `backend/app.py`, y el
`timeout` antes de abrir Chromium en `iniciar.bat` subido de 3 a 6
segundos como margen adicional.

Verificado en esta PC (no en hardware del colegio todavía): la ISO
reconstruida muestra `boot.wim` con su fecha original intacta (nunca se
tocó, ya no hace falta restaurarla) y `HBCD_PE.ini` con su fecha
original restaurada correctamente después de la edición; la sección
`_SUB ExtPrograms` contiene la línea `EXEC` activa. ISO y archivos
sueltos ya copiados a la USB de 16GB.

**Pendiente:** confirmar en hardware real del colegio que el
autoarranque vía `HBCD_PE.ini` dispara sin intervención manual esta vez.

## 27. Pivote a app portable sobre Windows; la ISO de Hiren's pasa a modo rescate

**Fecha:** 2026-10-21

Tras la sustentación del 16-oct-2026 (87,5/100), el jurado SENA señaló que
la app es clara para un técnico pero confunde a quien no sabe de
mantenimiento, y el equipo pidió un giro de 360°: la herramienta deja de
ser "un USB que arranca Hiren's Boot" y pasa a ser **una app portable**
que se abre desde el USB sobre el Windows que el PC ya tiene, pensada
para todo tipo de persona (quien no sabe, quien quiere llevar evidencia
al técnico, y el técnico mismo). Spec completo:
`docs/superpowers/specs/2026-10-21-version-portable-no-tecnicos-design.md`
(secciones 4 y 10).

**Decisión:**

- La app principal es portable sobre Windows 10 (1809+) y Windows 11, 64
  bits. El mismo código sigue funcionando en WinPE; los módulos que
  necesiten un Windows instalado devuelven `no_determinado` allí
  (degradación elegante, decisión 8).
- La ISO de Hiren's **no se borra**: queda en el USB como **modo
  rescate** para PCs que no arrancan. Ya no es el camino principal.
- El navegador es **Edge en modo app** (`msedge --app=http://127.0.0.1:PUERTO`),
  que ya trae Windows 10/11. Si no hay Edge se prueba Chrome y luego el
  navegador predeterminado. El Chromium portable (~800 MB) de `chromium\`
  se queda en el USB y NO debe borrarse mientras exista el modo rescate
  (`build/overlay-winpe/iniciar.bat` usa `%USB%chromium\chrome.exe`); el
  modo portable simplemente no lo usa.
- Se mantiene Python embeddable + Flask, con un lanzador
  `Iniciar_Diagnostic_Scanner.bat` que pide permisos de administrador
  (necesarios para sensores y S.M.A.R.T.).
- El servidor escucha **solo en `127.0.0.1`**, con puerto libre
  automático. Antes arrancaba con `host="0.0.0.0"`: en WinPE sin red no
  importaba, pero en un Windows normal conectado a una red expone el
  escáner a toda la red. Es un riesgo de seguridad real.

**Motivo:** responder literalmente la retroalimentación del jurado y
ampliar el público de la herramienta. Además, la última prueba real del
modo rescate lo confirma como camino frágil: en el USB de 16 GB el
autoarranque **no funcionó** (decisión 26 y respuestas del equipo del
2026-10-21) — hubo que abrir `iniciar.bat` a mano y escribir la URL de
localhost en el navegador.

**Pendiente abierto (reemplaza el *Pendiente* del final de la
decisión 26, sobre autoarranque confirmado):** el autoarranque del modo
rescate no funcionó en el USB de 16 GB y queda como **deuda abierta**, a investigar
en una tarea posterior (F1). El lanzador portable, en cambio, debe abrir
el navegador solo, sin que nadie escriba la URL.

## 28. Capa de lenguaje claro aditiva: el contrato de 5 llaves no cambia

**Fecha:** 2026-10-21

El jurado pidió que el resultado diga, junto al semáforo, qué significa,
cuál es el error y cómo solucionarlo. Hoy los textos de `mensaje` y
`recomendacion` son técnicos y cortos ("Salud reducida (Windows Storage
Health) en 1 disco"), y el contrato fijo de los módulos (decisión 6:
`componente, estado, mensaje, datos, recomendacion`, validado por
`scanner._cumple_contrato`) está cubierto por pruebas.

**Decisión:** la capa de lenguaje claro es **aditiva**; el contrato de 5
llaves **no cambia**.

- Cada módulo puede agregar un `codigo` de hallazgo (opcional).
- Un nuevo `explicador.py` traduce ese código a
  `guia = {que_pasa, que_hacer[], quien, urgencia}`, y `scanner` pega la
  guía al resultado.
- Toda la información visible tiene dos niveles: *Modo simple* (por
  defecto) y *Modo técnico* (lo que existe hoy más los datos nuevos),
  con un interruptor para alternarlos.
- Tono de los textos: tuteo ("Selecciona", "tu PC"), frases cortas, sin
  jerga; la jerga va al modo técnico.
- Una prueba verifica que todo par (componente, estado) posible tiene
  guía, para que nunca quede un "Crítico" sin explicación.

**Motivo:** mejorar la lectura sin romper nada de lo ya probado, y que
cada afirmación del modo simple se pueda rastrear a un dato medido
(sin textos vagos ni alarmistas). Implementación en F2.

## 29. Registro de equipos opt-in en SQLite (enmienda a la decisión 4)

**Fecha:** 2026-10-21

La decisión 4 fijó la app como **stateless**: no se guarda nada entre
ejecuciones. El equipo ahora pidió una base de datos para registrar PCs
(por ejemplo, una empresa que lleva su inventario e informes), lo que
choca con esa decisión.

**Decisión:** se enmienda la decisión 4 de forma acotada. El registro es
**opt-in**: por defecto la app sigue sin guardar nada; solo se persiste
algo si el usuario pulsa "Guardar en el registro".

- Almacenamiento en **SQLite** (`sqlite3` ya viene con Python: cero
  dependencias nuevas), en un archivo local en el USB o en una carpeta
  elegida por el usuario.
- Cada guardado es una foto del escaneo (JSON completo) con fecha, lo que
  da historial por equipo y tendencias (por ejemplo, la salud de la
  batería bajando).
- La identidad de un PC se toma del UUID de `Win32_ComputerSystemProduct`
  más el serial de BIOS y de placa; si son genéricos (tipo "To be filled
  by O.E.M.") se avisa y se usa el nombre elegido por el usuario.
- Exportación: CSV del inventario e informe HTML imprimible por equipo.
- Riesgo asumido: si se pierde el USB (ya pasó, decisión 26), se pierde
  también el registro. Mitigación: ruta del registro configurable y botón
  de copia de respaldo. No hay cifrado en la v1; queda documentado.

**Motivo:** cubrir el inventario sin dependencias nuevas y sin perder la
ventaja de la decisión 4 para quien no quiere guardar nada. Implementación
en F5.

## 30. Apagado automático por latido y ventana propia del navegador

**Fecha:** 2026-10-21

El lanzador portable (`backend/lanzador.py`) debe cerrarse solo cuando el
usuario cierra la ventana de la app, sin dejar un servidor huérfano en
segundo plano ni pedirle nada al usuario.

**Decisión:**

- **Latido:** el frontend ya consulta `/api/status` cada 2 s; el servidor
  anota la hora de cada consulta (`after_request`) y usa eso como latido.
  Sin latido nuevo, el lanzador apaga el servidor.
- **Gracia inicial de 60 s**, contada desde que se lanza el navegador (no
  desde el arranque del servidor), para que Edge tenga tiempo de abrir.
- **Tolerancia de 150 s** de silencio: Chromium frena los temporizadores
  de una ventana minimizada u oculta a ~1 por minuto, así que un latido
  cada 2 s no es fiable con la ventana en segundo plano.
- **Suspensión/hibernación:** `time.monotonic()` sigue contando mientras
  el equipo duerme, por lo que al despertar parecían haber pasado >150 s
  sin latido y el programa se cerraba antes de que la página pudiera
  consultar de nuevo. Si el propio bucle de vigilancia estuvo parado más
  de 10 s (`latido_tras_pausa`), se renueva el latido para dar margen al
  navegador.
- **Perfil temporal** con `--user-data-dir`: sin él, Edge delega en un
  proceso ya abierto y el proceso lanzado termina al instante. El perfil
  se borra al salir.
- **`--sin-navegador`:** no abre ventana; sirve para pruebas de humo
  (servidor + `/api/status`) sin interfaz.
- **El sondeo de arranque ignora los proxies del sistema** (`ProxyHandler({})`):
  un proxy configurado en Windows puede tragarse las peticiones a 127.0.0.1.
- **`abrir_ventana` cae al navegador predeterminado** si el `.exe` de
  Edge/Chrome no se puede ejecutar (`OSError`).
- Si el hilo del servidor muere por su cuenta, `main()` devuelve 1 con un
  mensaje de error corto, en vez de salir como si todo hubiera ido bien.

**Motivo:** cerrar la ventana debe bastar para terminar el programa, y
las medidas de la prueba real en el USB (tareas 9 y 10 del plan) se
registrarán en decisiones posteriores (31 y 32).

## 33. Implementación de la capa de lenguaje claro (enmienda a la 28)

**Fecha:** 2026-10-22

La decisión 28 preveía que cada módulo agregara un `codigo` de hallazgo
que `explicador.py` tradujera. Al implementarla en F2 se simplificó.

**Decisión:**

- La guía se busca por **(componente, estado)**; los módulos **no** agregan
  `codigo`. Son 35 entradas (7 componentes x 5 estados).
- Cada guía tiene las llaves `que_significa, que_hacer, quien, urgencia,
  pregunta_tecnico`.
- `explicador.py` es la **única fuente** de los textos simples y de
  `FRASES_VEREDICTO`; el frontend los recibe por `/api/guias` (las frases
  de veredicto van en `_veredictos`) y no repite ningún texto.
- El equipo revisa la redacción de los textos.
- El informe imprimible vive en `backend/informe.py` (`/api/informe`):
  HTML autocontenido, todo texto del escaneo escapado, fecha en hora local.

**Motivo:** el par (componente, estado) ya basta para dar una explicación
honesta y evita tocar los 7 módulos y su contrato probado; tener los textos
en un solo archivo facilita la revisión del equipo.

Pendiente de decisión del equipo: ver si "red sin enlace" (CRITICO) debe
ser ADVERTENCIA — el titular "Tu PC tiene un problema serio" puede alarmar
en equipos con Wi-Fi apagado.

## 34. Estado inicial sin datos simulados

**Fecha:** 2026-10-22

**Decisión:** al arrancar, la interfaz **no muestra ningún dato** hasta que
haya un escaneo real. `DATOS_MOCK` solo se pinta tras pulsar "Ver Modo
Demostración", siempre con el aviso de datos simulados, y el botón del
informe se oculta en la demo. Además, en el modo simple un componente
`no_determinado` se lista aparte ("No se pudieron revisar"), no bajo
"Necesitan atención": no indica una falla.

**Motivo:** la regla "ningún dato inventado". Se encontró al probar en el
navegador: la pantalla inicial mostraba datos de demostración como si fueran
reales (corregido en el commit 034afa6).

## 35. Brave como tercer navegador de la ventana (enmienda a la 30)

**Fecha:** 2026-10-22

**Decisión:** el lanzador busca el navegador para la ventana de la app en
este orden: Edge, Chrome, Brave (en `ProgramFiles`, `ProgramFiles(x86)` y
`LocalAppData`), y por último el navegador predeterminado.

**Motivo:** la laptop del equipo no tiene Edge; sin Brave la app caía al
navegador predeterminado sin ventana propia.

## 36. Red sin enlace pasa de CRITICO a ADVERTENCIA (enmienda a la 20)

**Fecha:** 2026-10-22

**Decisión:** si ninguna interfaz de red física tiene enlace activo, `red`
se clasifica **ADVERTENCIA** (antes CRITICO). El resto no cambia: sin
interfaz física detectada es NO_DETERMINADO; con enlace y errores de
paquetes es SOSPECHA; con enlace y contador de errores ilegible es
NO_DETERMINADO; con enlace y cero errores es NORMAL.

**Motivo:** el titular de un CRITICO ("Tu PC tiene un problema serio")
alarmaba en equipos que simplemente tenían el Wi-Fi apagado o no tenían
cable. El equipo decidió que sin enlace es una advertencia. Resuelve el
punto pendiente de la decisión 33.

**Consecuencias:**

- `red` ya no puede producir CRITICO. Se conserva la llave `critico` en
  `_RECOMENDACIONES` y en `GUIAS` porque todo componente tiene los 5
  estados por contrato; ahora es un estado inalcanzable con texto honesto
  (como `mainboard` "critico").
- Los textos de `GUIAS["red"]` se intercambiaron: la explicación calmada
  de "no hay enlace" (urgencia baja, lo revisa la propia persona y solo
  si persiste un técnico) vive en `advertencia`; `critico` pasó a ser el
  texto de "estado inalcanzable".
- Se actualizaron `docs/reglas-recomendaciones.md` y `test_red`, que ahora
  también comprueba que ninguna combinación de interfaces da CRITICO.

## 37. Recomendador del equipo (F3)

**Fecha:** 2026-10-22

**Decisión:** el escaneo completo ahora devuelve `recomendaciones` (y los
`hechos` del equipo en que se basan). Cada recomendación sale solo de datos
medidos y trae su lista "basado en", una prioridad (alta, media, baja), quién
la hace y, si aplica, opciones de sistema operativo. Se muestran en los modos
simple y técnico de la interfaz y en el informe imprimible.

**Motivo:** una persona sin conocimientos técnicos necesita saber qué hacer
con su equipo (qué sistema operativo le conviene, si le sirve un SSD o más
RAM, qué hacer con la batería o un disco con problemas), y por qué se le
sugiere, sin que el programa afirme lo que no pudo medir.

**Consecuencias:**

- Módulos nuevos: `equipo.py` (lee los hechos del sistema: ninguna lectura
  es obligatoria como administrador; el TPM solo se puede leer con esos
  permisos y, si no, queda en "falta confirmar") y `recomendador.py` (reglas puras, nunca lanzan).
- Opciones de S.O., en orden: Windows 11 (cuando se cumplen los requisitos o
  solo el TPM / Arranque seguro no se pudieron leer), Windows 10 (con su nota
  de fin de actualizaciones de seguridad), Ubuntu / Linux Mint o Lubuntu /
  Linux Mint XFCE según la RAM, MiniOS10 para hardware modesto (con su nota
  de versión no oficial y ayuda de un técnico) y Windows 7 solo como ÚLTIMA
  opción y solo para 32 bits o menos de 2 GB, siempre con su aviso de
  seguridad.
- `cpu_apto_windows11` es una heurística por nombre del procesador; devuelve
  `None` cuando no sabe y entonces no se afirma ni se descarta nada.
- Los textos de las recomendaciones los revisa el equipo.
- El informe imprimible muestra la sección "Recomendaciones para tu equipo"
  antes de "Preguntas para tu técnico", con las opciones desplegadas para
  que salgan en el papel. El modo demostración no inventa recomendaciones.
- Rendimiento: la primera versión de `leer_hechos` tardaba ~5,5 s sin
  administrador (el TPM tardaba ~5 s en dar "acceso denegado"). Ahora sin
  administrador el TPM ni se consulta, las dos lecturas de discos comparten
  una conexión WMI y usan consultas filtradas (disco de C: y su disco físico):
  `leer_hechos` baja a ~0,4 s y el escaneo completo a ~5 s, la mayor parte
  del procesador (~3 s, ya existente). `tiempos` trae `hechos` y
  `recomendaciones` por separado.
- Enmendada por la decisión 38 (sistema operativo actual, textos en lenguaje simple).
- Endurecimiento: una RAM de 0 GB (lectura sin capacidad) cuenta como dato
  ausente; los textos de Linux dan solo hechos medidos (sin "funciona con
  fluidez"); la recomendación de respaldo nombra el disco afectado en vez de
  copiar el mensaje técnico del módulo.

## 38. El recomendador tiene en cuenta el sistema operativo actual (enmienda a la 37)

**Fecha:** 2026-10-22

**Motivo:** la revisión final de F3 encontró que la regla de sistema operativo
ignoraba el SO instalado: a un equipo que ya tiene Windows 11 se le podía
recomendar Windows 10, o "falta confirmar el TPM", o nada de Windows 11 si su
procesador era nuevo y la heurística no lo conocía. Además, varios textos usaban
términos sin explicar (firmware, TPM, Secure Boot) y las razones de exclusión de
Windows 11 afirmaban más de lo que se midió (`GetFirmwareType` dice cómo arrancó
el SO actual, no lo que el firmware admite).

**Consecuencias:**

- Si el SO actual es Windows 11 en un Windows real, Windows 11 es la opción
  principal ("Ya lo tienes instalado en este equipo."), sin notas de "falta
  confirmar" y sin Windows 10; las demás opciones siguen las reglas por RAM.
- `equipo.leer_hechos()` trae una clave nueva, `entorno` ("windows" | "winpe" |
  `None`, de `utils.detectar_entorno()`); la regla solo se aplica con
  `"windows"`, porque WinPE también se anuncia como Windows 11.
- TPM, Arranque seguro (Secure Boot) y modo de arranque (UEFI/BIOS) se
  explican en palabras simples; con datos por confirmar, "quién" pasa a ser
  técnico (sin administrador la persona no puede comprobarlo sola).
- Las razones de omisión de Windows 11 hablan de lo que el equipo hace "hoy"
  (solo texto: reglas y umbrales sin cambios).
- La nota de MiniOS10 dice sin rodeos que no viene de Microsoft, que no se puede
  verificar y que necesita licencia válida. La nota de Windows 10 ya no fija una fecha.
- Si algún dato dice ARM, la arquitectura se trata como desconocida y no se da
  consejo de sistema operativo pensado para x64.
- Decisiones abiertas del equipo: (1) si MiniOS10 se queda en la lista;
  (2) si "Arranque seguro desactivado" debe seguir excluyendo a Windows 11
  (Microsoft exige que el equipo sea "capaz", no que esté "activado").

## 39. Rediseño de la interfaz: armazón con pestañas, fichas de componente y paleta clara/oscura

**Fecha:** 2026-10-22

**Motivo:**

- Comentarios del equipo tras probar la app y del jurado del SENA: no gustó cómo
  se organizan los botones ni la estructura general, el PC con círculos por
  componente "parece una formación de fútbol" y se pidió una estética más
  profesional (y que se analizara la paleta). La interfaz había crecido por capas
  (mapa físico, decisión 18; lista; panel de detalle; modo simple; recomendaciones)
  hasta ser una sola página larga con tres botones de peso parecido al final, y
  F4–F6 iban a agregar más secciones.
- Análisis de la paleta anterior (oscura, tipo "GitHub oscuro"), medido, no a ojo
  (detalle en `docs/superpowers/specs/2026-10-22-rediseno-interfaz-design.md` §2):
  - El texto sí cumple: 14,6:1 (texto), 5,6:1 (secundario) y 5,1–6,9:1 (colores de
    estado) sobre la tarjeta. La legibilidad no era el problema.
  - Con protanopia/deuteranopia los colores de estado casi colapsan: verde↔amarillo
    1,1–1,2:1, naranja↔rojo 1,06–1,12:1, amarillo↔naranja 1,3–1,5:1 (para
    distinguir elementos hace falta ≥ 3:1). El estado no puede depender solo del color.
  - Amarillo y naranja son vecinos (tonos 41° y 23°): en chips pequeños se leen casi igual.
  - El borde medía 1,42:1 contra la tarjeta (las tarjetas se "pegaban" al fondo).
  - Tema oscuro único: se ve "técnico/gamer", se imprime mal y no coincide con el
    informe imprimible (blanco).

**Decisión:**

- Estructura (enfoque B del spec): una sola página con **barra superior** (marca,
  acción principal "Revisar mi PC", interruptor Simple/Técnico, tema y menú "Más"
  con informe, reporte y demostración) y **pestañas** Resumen, Componentes,
  Recomendaciones y Análisis de Windows (hash en la URL, teclado con flechas).
  Sin escaneo solo Resumen es accionable, con la invitación a revisar.
- **Se retira el mapa de puntos** del PC: lo reemplazan las fichas de componente del
  Resumen (ícono, nombre, estado, una medida clave). **Esto reemplaza la parte del
  mapa físico de la decisión 18**; la ficha de inspección y el panel de detalle de
  esa decisión siguen en pie, ahora como la tabla técnica con fila expandible de la
  pestaña Componentes. Las tarjetas simples con guía se conservan en el modo simple.
  La selección enlazada de la decisión 18 (pasar el mouse por el mapa resalta la fila
  y al revés) queda retirada junto con el mapa: ahora se llega al componente desde las
  fichas y los «Ver …» del Resumen, y el foco cae en el componente elegido.
- Paleta: **tema claro por defecto** y **oscuro opcional** (botón en la barra,
  recordado en `localStorage` dentro de `try/catch`; `prefers-color-scheme` no se
  sigue a propósito para que la app se vea igual en todos los equipos del colegio).
  La fuente única de tokens (colores, espaciado, radios, sombras, tipografía) sigue
  siendo `config/palette.css`, con los mismos nombres en ambos temas. La paleta final
  difiere un poco del spec §2: en el tema claro el amarillo es `#946200` (spec
  `#9A6700`) y el borde de controles `#7B8797` (spec `#8793A3`), oscurecidos para
  pasar 4,5:1 (texto) y 3:1 (borde) sobre `--color-fondo`.
- **Cinco formas de estado** (SVG en línea propios, trazo de 1,75 px, `currentColor`):
  círculo con visto (normal), triángulo con exclamación (advertencia), rombo con
  exclamación (sospecha), octógono con cruz (crítico) y círculo discontinuo con
  interrogación (sin datos). Siempre van junto a la palabra del estado y al color.
  El informe imprimible usa las mismas cinco siluetas, así se distinguen también en
  blanco y negro. El informe también cambió el texto de su estado vacío (ahora remite a
  «Revisar mi PC») y su etiqueta del estado `no_determinado` pasó de «No determinado» a
  «Sin datos», igual que en la app.
- **Prueba automática de contraste** (`test_paleta`): en ambos temas, texto ≥ 4,5:1,
  colores de estado y acento ≥ 4,5:1 sobre tarjeta y fondo, bordes de controles ≥ 3:1,
  chips y franjas de aviso ≥ 4,5:1, mismos nombres de token en los dos temas y toda
  `var(--x)` de la hoja definida.
- El `app.js` único se divide en `estado.js` (constantes), `iconos.js`, `dom.js`
  (utilidades de DOM y chip), `modelo.js` (lógica **pura**, probada con Node:
  veredicto, medida clave, datos del equipo, "lo primero", pestañas, tema),
  `vistas.js` (dibuja cada pestaña) y `app.js` (armazón y eventos), cargados con
  `<script>` en ese orden, sin empaquetador. Todo texto del escaneo entra por
  `textContent`; la única inserción de HTML son los íconos constantes de `dom.js`.
- Pestaña **Análisis de Windows** oculta (`hidden`) hasta la fase F4a: la constante
  `ANALISIS_DISPONIBLE = false` de `estado.js` la controla (F4a la cambia a `true` y
  llena `#panel-analisis`).
- Se conservan las garantías previas: nunca datos de ejemplo mostrados como reales
  (en la demostración la pestaña Recomendaciones solo invita a revisar), escape de
  todo texto, estado vacío, aviso de datos simulados y modo recordado.

**Consecuencias:**

- Pruebas nuevas: `frontend/tests/modelo.test.js` (se corre con
  `node frontend/tests/modelo.test.js` y también desde `test_frontend_node`), contraste
  y tokens en `test_paleta`, `test_frontend_sin_innerhtml_inseguro`,
  `test_indice_estructura`, `test_indice_recomendaciones`, `test_sin_codigo_del_mapa`
  y `test_informe_estados_con_forma` (que además compara el informe con la paleta clara).
- Backend sin cambios de contrato; solo `informe.py` cambió su CSS y sus íconos.
- Límites conocidos: la verificación visual con capturas es manual, no automática.
  Lista que debe repetirse al tocar la interfaz: recorrido de las tres pestañas visibles (Análisis de Windows sigue oculta hasta F4a) en
  tema claro y oscuro a 1280×720 y a unos 700 px sin desplazamiento horizontal;
  veredicto visible sin desplazarse; estado vacío, demostración y escaneo real;
  informe en pantalla y en vista de impresión; captura en escala de grises con los
  cinco estados distinguibles.
- `prefers-color-scheme` intencionalmente no se sigue (ver arriba).
