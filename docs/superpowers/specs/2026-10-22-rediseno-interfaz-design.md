# Rediseño de la interfaz — estructura, estética y paleta

**Fecha:** 2026-10-22
**Estado:** borrador del equipo de desarrollo, listo para plan. El equipo pidió "continuar" sin más preguntas: todo lo marcado `[MI LLAMADA]` es decisión mía y se puede revertir.
**Origen:** retroalimentación del equipo tras probar la app (22-oct-2026) y comentario del jurado SENA: *"no me gustó cómo se organizan los botones y toda la estructura general; el PC con los círculos de cada componente parece una formación de fútbol; que la estética sea más profesional; analiza tú mismo la paleta."*

## 1. Por qué

La interfaz actual creció por capas (mapa físico → lista → panel de detalle → modo simple → recomendaciones…): es **una sola página larga** con un interruptor de modo suelto, tres botones de peso parecido al final y un mapa de puntos sobre una silueta de laptop. F4–F6 van a agregar análisis de Windows, inventario e instalación: sin una estructura, esa página se vuelve inmanejable. El mapa de puntos no comunica (solo repite la lista) y se ve juvenil. La estética oscura estilo terminal comunica "herramienta de técnico", justo lo que el jurado pidió dejar atrás para el público general.

## 2. Hallazgos del análisis de la paleta (medidos, no a ojo)

Paleta actual (`config/palette.css`, tipo "GitHub oscuro"): fondo `#0D1117`, tarjeta `#161B22`, texto `#E6EDF3`, texto secundario `#8B949E`, verde `#3FB950`, amarillo `#D29922`, naranja `#DB6D28`, rojo `#F85149`, acento `#58A6FF`, borde `#30363D`.

| Hallazgo | Dato | Consecuencia |
|---|---|---|
| El **texto** cumple contraste | 14,6:1 (texto), 5,6:1 (secundario), 5,1–6,9:1 (colores de estado) sobre la tarjeta | La legibilidad no es el problema; no se "arregla" cambiando tonos de texto |
| Los **4 colores de estado se confunden con daltonismo rojo-verde** (≈ 8 % de los hombres) | Simulación protanopia/deuteranopia: verde↔amarillo 1,1–1,2:1, naranja↔rojo 1,06–1,12:1, amarillo↔naranja 1,3–1,5:1 (se necesita ≥ 3:1 para distinguir elementos) | El estado **no puede depender solo del color**: cada estado necesita una **forma/icono propio** además del texto |
| **Amarillo y naranja son vecinos** | Tonos (hue) 41° y 23° | En chips pequeños se leen casi igual; refuerza la necesidad de iconos distintos |
| El borde es casi invisible | 1,42:1 contra la tarjeta | Decorativo: aceptable, pero las tarjetas se "pegan" al fondo; se separan con sombra suave y espacio |
| Tema oscuro único | — | Se ve "técnico/gamer", se imprime mal y no coincide con el informe imprimible (blanco) |
| Sin color de marca | El acento es el azul de enlaces | Falta una identidad (barra superior, logo) que dé seriedad |

`[MI LLAMADA]` **Paleta propuesta** (tokens en `config/palette.css`, que sigue siendo la fuente única): tema **claro por defecto** (más sobrio y profesional para el público general, coincide con el informe impreso) y tema **oscuro opcional** (útil en proyector y para el técnico). Valores claros, todos con ≥ 4,5:1 sobre tarjeta blanca (calculados): fondo `#F4F6F9`, tarjeta `#FFFFFF`, texto `#1B2430` (15,6:1), texto secundario `#566273` (6,2:1), marino de marca `#0F2A47` (14,6:1, barra superior), acento `#1F5FBF` (6,1:1), verde `#1A7F4B` (5,0:1), ámbar `#9A6700` (4,9:1), naranja `#B54708` (5,4:1), rojo `#B42318` (6,6:1), borde `#D5DBE3`. Los valores oscuros se derivan del mismo criterio (se fijan en el plan con la prueba automática de contraste). Con daltonismo estos cuatro colores también se acercan: por eso **la forma y el texto son obligatorios** (§4.3), no un extra.

## 3. Objetivos, no-objetivos y anti-objetivos

### Objetivos
- **O1.** Una estructura clara: una **barra superior** con la identidad y la **acción principal** ("Revisar mi PC"), **pestañas** para cada área (Resumen, Componentes, Recomendaciones, Análisis de Windows; más adelante Equipos y Post-install) y los botones secundarios agrupados, no sueltos.
- **O2.** **Se elimina el mapa de puntos.** En su lugar, una cuadrícula de **fichas de componente** (icono, nombre, estado con forma propia, una medida clave).
- **O3.** Estética profesional y consistente: sistema de espaciado, tipografía, radios, sombras e iconos propios; tema claro por defecto y oscuro opcional.
- **O4.** Paleta auditada con una **prueba automática de contraste** que impide volver a romperla.
- **O5.** El estado de cada componente se distingue por **forma + texto + color** (accesible).
- **O6.** Cualquier dato accesible en ≤ 2 clics; el veredicto visible sin desplazarse en 1280×720 y en ventana angosta (~700 px).
- **O7.** El rediseño **deja los huecos** para F4–F6 (pestañas y contenedores) sin rehacerse.

### No-objetivos
- No se reescribe la lógica de diagnóstico, recomendaciones ni informes (backend intacto).
- No se agregan frameworks JS ni librerías externas (reglas del README); iconos como SVG en línea propios.
- No se cambia el sistema de 5 estados ni los textos de `explicador.py` (revisados por el equipo).
- No se rediseña el informe imprimible más que lo necesario para usar los mismos tokens.

### Anti-objetivos (fracaso aunque "funcione")
- Que sea solo un cambio de colores sobre la misma estructura.
- Que al quitar el mapa se pierda información o se necesiten más clics para llegar a un componente.
- Que se pierdan garantías ya logradas: **nunca datos de ejemplo mostrados como reales**, escape de todo texto del sistema, `localStorage` en `try/catch`, estado vacío, modo demostración con su aviso, recuerda el modo elegido.
- Que el estado dependa solo del color, o que el contraste de texto baje de 4,5:1 (3:1 para elementos de interfaz).
- Que se vea "bonito" pero la persona sin conocimientos no sepa cuál es el botón principal.

## 4. Diseño

### 4.1 Aproximaciones consideradas

| | Qué es | Ventajas | Costos |
|---|---|---|---|
| **A. Retoque in situ** | Nueva paleta, fichas en lugar del mapa, reagrupar botones, misma página larga | Barato, bajo riesgo | La página sigue creciendo con F4–F6; no resuelve la organización que se pidió |
| **B. Estructura con pestañas en una sola página** `[MI LLAMADA — recomendada]` | Barra superior + pestañas (hash `#resumen`, `#componentes`…), vistas separadas, tokens de tema | Resuelve la organización, deja lugar para F4–F6, se puede construir por etapas siempre funcionando, sin frameworks | Reorganiza `app.js` (hoy ~25 KB) y el HTML; más pruebas visuales |
| **C. Varias páginas del servidor** | Una ruta HTML por área | Separación total | Pierde el estado en memoria entre pantallas, más recargas, más código de rutas |

Se elige **B**: es lo único que resuelve "cómo se organiza todo" y deja espacio para lo que viene, con riesgo controlado porque se hace por etapas (cada etapa deja la app funcionando).

### 4.2 Estructura de pantalla

- **Barra superior** (color marino de marca): marca (icono de chip + "Diagnostic Scanner PC"), control segmentado **Simple | Técnico**, botón de tema (claro/oscuro), botón principal **"Revisar mi PC"** (tras el primer escaneo dice "Volver a revisar"; deshabilitado con indicador mientras corre) y un menú **"Más"** con: *Informe para el técnico*, *Descargar reporte (.txt)* y *Ver demostración*.
- **Avisos** (administrador, demostración): franja fina bajo la barra, con icono.
- **Pestañas:** `Resumen · Componentes · Recomendaciones · Análisis de Windows`. Sin escaneo, solo Resumen es accionable (las demás muestran la invitación a revisar); *Análisis de Windows* se habilita tras el primer escaneo. Navegación por teclado (roles `tablist`/`tab`/`tabpanel`, flechas), recuerda la pestaña con el hash de la URL. Espacio reservado para `Equipos` (F5) y `Post-install` (F6).
- **Pie** discreto: "Todo se procesa en este equipo; no se envía nada por internet."

### 4.3 Estados con forma propia (accesibilidad)

Cada estado tiene icono, silueta, color y texto, todo a la vez: `normal` círculo con visto, `advertencia` triángulo con exclamación, `sospecha` rombo con exclamación, `critico` octágono con cruz, `no_determinado` círculo discontinuo con interrogación. Las fichas y los chips usan fondo teñido suave + icono + texto; el borde lateral de una tarjeta usa el color pero **nunca es la única señal**. Una prueba de captura en escala de grises debe permitir distinguir los 5 estados.

### 4.4 Vista Resumen

- **Tarjeta principal ("hero"):** icono grande de estado y titular en palabras (el de `FRASES_VEREDICTO`), la línea "Están bien… / Necesitan atención… / No se pudieron revisar…", la frase de cobertura y el botón secundario **"Abrir informe para el técnico"**.
- **Datos del equipo** (de `hechos` y de los módulos; solo lo leído): fabricante/modelo, sistema operativo, procesador, RAM, disco.
- **"Lo primero que conviene hacer"**: hasta 3 elementos ordenados (estados de mayor urgencia y recomendaciones de prioridad alta/media), cada uno con enlace a su pestaña; si no hay nada, "Por ahora no hay nada urgente".
- **Cuadrícula de 7 fichas** (2–4 columnas según ancho): icono del componente, nombre, estado (forma + texto) y una **medida clave real** (p. ej. "54 °C", "16 GB, 54 % en uso", "85 % de salud") tomada de `datos`; sin dato → "—". Clic → pestaña Componentes, con ese componente abierto.

### 4.5 Vista Componentes

- **Modo simple:** las tarjetas actuales con guía (qué significa, qué hacer, quién, urgencia), ordenadas por gravedad, con el nuevo estilo.
- **Modo técnico:** una **tabla** (Componente · Estado · Medición clave · Mensaje) con fila expandible que muestra el detalle técnico actual (`datos` desglosados y la guía). Sin mapa.

### 4.6 Vistas Recomendaciones y Análisis de Windows

- *Recomendaciones:* el bloque actual (tarjetas con "Basado en" y opciones desplegables) en su propia pestaña.
- *Análisis de Windows:* contenedor con la invitación "Analizar mi Windows" y el área de resultados; la lógica la agrega F4a (Tarea 7), que ya no necesita decidir dónde poner nada.

### 4.7 Sistema visual

- Tokens en `config/palette.css` (colores claros y oscuros, `prefers-color-scheme` + selector manual `data-theme`, recordado en `localStorage` dentro de `try/catch`), más tokens de **espaciado** (escala de 4 px), **radios** (8/12 px), **sombras** (2 niveles), **tipografía** (pila del sistema con Segoe UI; 15–16 px base; escala 12/14/16/20/24/32) y **duraciones**. Sin fuentes externas.
- Iconos: conjunto propio en SVG en línea (7 componentes, 5 estados, tema, menú, flechas), un solo trazo de 1,75 px, `currentColor`.
- Respeta `prefers-reduced-motion`. Foco visible en todo control. Objetivos táctiles ≥ 40 px.
- El informe imprimible usa los mismos tokens claros.

## 5. Restricciones

- Reglas del README: sin frameworks JS, sin librerías ni CDN, sin dependencias nuevas.
- Navegadores objetivo: Edge, Chrome y Brave de los últimos años (Chromium ≥ 93); sin funciones experimentales.
- No cambia el contrato de la API (`/api/scan`, `/api/status`, `/api/guias`, `/api/informe`, `/api/reporte`, `/api/analisis` si existe). Todo texto del sistema se escapa; sin `innerHTML` con datos sin escapar.
- La app sigue funcionando sin escaneo (estado vacío) y sin guías (degradación).
- Decisión nueva al final de `docs/DECISIONES.md`: la **39** (rediseño; reemplaza lo dicho sobre el mapa físico en la decisión 18). Números 31 y 32 siguen reservados.
- El `app.js` actual (≈ 25 KB) se **divide en varios archivos** con una responsabilidad cada uno (constantes/iconos, estado de la aplicación, vistas, utilidades de DOM) cargados con `<script>` en orden; sin empaquetador.

## 6. Cómo se sabe que funcionó

- Un usuario sin conocimientos abre la app, ve **una acción principal** y llega a cualquier información en ≤ 2 clics.
- Prueba automática: todos los pares texto/fondo y elemento/fondo de `palette.css` cumplen ≥ 4,5:1 (texto) y ≥ 3:1 (bordes de controles y estados) en tema claro y oscuro.
- Captura en escala de grises: los 5 estados se distinguen sin color.
- Verificación visual (navegador integrado) en 1280×720 y ~700 px, tema claro y oscuro: sin desbordes, veredicto visible sin desplazarse.
- `python test_scanner.py` limpio; garantías previas intactas (sin datos de ejemplo como reales, escape, estado vacío, demostración).

## 7. Etapas (siempre funcionando)

1. **Tokens y tema:** paleta clara/oscura, prueba de contraste, selector de tema (la interfaz actual ya hereda los colores).
2. **Iconos y estados con forma:** conjunto SVG, chips y fichas con forma + texto.
3. **Armazón:** barra superior, pestañas, menú "Más", avisos; las secciones actuales se reubican bajo pestañas sin cambiar su lógica.
4. **Vista Resumen:** hero, datos del equipo, "lo primero", fichas (reemplazan el mapa).
5. **Vista Componentes:** tarjetas simples restauradas y tabla técnica con fila expandible; se elimina el mapa y el código muerto.
6. **Pestañas Recomendaciones y Análisis:** contenedores y estado vacío.
7. **Informe y cierre:** tokens en el informe, decisión 39, documentación y limpieza.

## 8. Qué se deja al constructor

Diseño fino de cada icono, tamaños exactos de la escala, cómo dividir los archivos JS, y el detalle de las animaciones (sobrias y opcionales).
