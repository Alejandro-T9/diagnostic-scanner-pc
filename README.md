# Diagnostic Scanner PC

Herramienta de diagnóstico de hardware que arranca desde un USB booteable
con **WinPE (Hiren's Boot PE)** — sin instalar nada en el equipo revisado y
sin depender de una conexión a internet. Desarrollada para el **Semillero
de Mantenimiento** de la **I.E. Carlos Lleras Restrepo**, como proyecto de
grado de Sistemas Tele Informáticos.

El equipo arranca desde el USB, el panel de diagnóstico se abre solo en
pantalla completa (modo kiosco), y en segundos entrega un veredicto sobre
7 componentes físicos que ayuda a decidir qué revisar antes de intervenir
el equipo.

> El proyecto pasó por dos bases distintas antes de esta (Alpine Linux →
> Debian Live → WinPE). El motivo de cada cambio está documentado con
> fecha en [`docs/DECISIONES.md`](docs/DECISIONES.md) — ese archivo es la
> fuente de verdad histórica del proyecto, no se reescribe, solo se agrega.

## Stack técnico

| Capa | Tecnología |
|---|---|
| Sistema operativo del USB | WinPE (Hiren's Boot PE), arrancado vía Ventoy en modo WIMBOOT |
| Backend | Python 3.12 (distribución embeddable portable), Flask, psutil |
| Acceso a hardware | WMI (paquete `wmi`) para la mayoría de los datos; LibreHardwareMonitorLib vía `pythonnet` para voltajes/GPU/ventiladores, que WMI no expone |
| Frontend | Jinja2 + HTML5 + CSS3 + JavaScript vanilla (sin frameworks, sin CDN) |
| Modo kiosco | Chromium portable, pantalla completa, autoarranque configurado en la propia ISO |
| Empaquetado del USB | `oscdimg` (Windows ADK) para generar la ISO booteable |

Todo corre local y offline, sin Docker/Kubernetes, sin base de datos
externa, sin nada guardado entre un arranque y el siguiente (diseño
*stateless* — decisión 4 en `DECISIONES.md`).

## Estructura del proyecto

```
diagnostic_scanner_pc/
├── backend/
│   ├── app.py                  Servidor Flask: rutas HTML + API REST
│   ├── scanner.py              Orquestador: llama a cada módulo, arma el reporte
│   ├── utils.py                Timestamp, verificación de WMI, reporte descargable
│   ├── informe.py              Informe imprimible (HTML autocontenido, con la paleta clara)
│   ├── test_scanner.py         Suite de regresión (clasificación, paleta, interfaz, informe)
│   ├── requirements.txt        Flask, psutil, wmi, pythonnet
│   ├── native/lhm/             LibreHardwareMonitorLib.dll y dependencias (.NET)
│   └── modules/                Un archivo por componente físico (ver más abajo)
├── frontend/
│   ├── templates/               base.html, index.html (Jinja2)
│   └── static/
│       ├── css/style.css        Estilos del dashboard (importa config/palette.css)
│       └── js/                  estado, iconos, dom, modelo (lógica pura), vistas y app (ver "La interfaz")
├── frontend/tests/modelo.test.js  Pruebas de la lógica pura del frontend (se corren con Node)
├── config/
│   └── palette.css              Tokens de diseño (colores claro/oscuro, espaciado, tipografía), fuente única
├── build/
│   ├── create_pe.ps1            Arma la ISO de WinPE con autoarranque configurado
│   ├── overlay-winpe/iniciar.bat Lanza Flask + Chromium en modo kiosco
│   └── python-portable/         Distribución embeddable de Python (no versionar)
├── docs/
│   ├── DECISIONES.md            Registro histórico de decisiones técnicas
│   └── reglas-recomendaciones.md Tabla de condición → severidad → recomendación, por módulo
└── README.md
```

## Componentes diagnosticados

| Módulo | Componente |
|---|---|
| `mainboard.py` | Tarjeta madre: fabricante, modelo, BIOS |
| `cpu.py` | Procesador: núcleos, hilos, uso, frecuencia, temperatura — incluye GPU integrada y ventiladores como datos asociados |
| `gpu.py` | Auxiliar de `cpu.py` (no es un componente del contrato): identidad y telemetría de la GPU |
| `ram.py` | Memoria RAM: capacidad física vs. disponible al sistema operativo, uso |
| `almacenamiento.py` | Discos internos: modelo, tamaño, salud S.M.A.R.T. — los discos USB se reportan aparte y no afectan el estado |
| `fuente_poder.py` | Telemetría de voltaje del regulador del procesador (vía LibreHardwareMonitorLib) |
| `bateria.py` | Batería: ciclos de carga, salud vs. capacidad de diseño |
| `red.py` | Tarjeta de red: enlace, velocidad, errores de paquetes |

## Sistema de clasificación

Reemplaza el esquema original de 3 colores — motivo completo en la
decisión 20 de `DECISIONES.md`. Cinco estados posibles, de mayor a menor
severidad para el veredicto global:

- 🔴 **CRÍTICO** — falla confirmada.
- 🟠 **SOSPECHA** — evidencia real de un posible problema, sin ser falla confirmada.
- 🟡 **ADVERTENCIA** — se leyó bien, amerita monitoreo, sin indicio de falla.
- ⚪ **NO_DETERMINADO** — no se pudo leer el dato. No es lo mismo que "está mal".
- 🟢 **NORMAL** — se leyó bien y está dentro de rango esperado.

## Modo portable (recomendado)

Funciona en cualquier PC con **Windows 10 u 11**, sin instalar nada:

1. Conectar el USB (o abrir la carpeta del proyecto).
2. Doble clic en **`Iniciar_Diagnostic_Scanner.bat`**.
3. Windows pedirá permiso de administrador: **aceptarlo**, así se pueden leer
   temperaturas, voltajes y S.M.A.R.T. Si se rechaza, la aplicación abre
   igual pero con lecturas reducidas y un aviso de advertencia en la parte
   superior (algunos componentes saldrán `NO_DETERMINADO`).
4. Se abre una ventana propia con el panel; al cerrarla, el programa se
   apaga solo en unos 2-3 minutos (la consola negra puede seguir abierta
   hasta entonces: no está trabada).

La ISO de WinPE (ver "Generar el USB booteable") queda como **modo de
rescate**, para equipos que ya no arrancan Windows.

## Cómo ejecutarlo en una PC normal (fuera del USB)

Sirve para desarrollo, revisión o mostrarlo sin arrancar desde el USB.
Requiere Windows (usa WMI) y Python 3.10 o superior instalado.

```bash
cd backend
pip install -r requirements.txt
python app.py
```

El servidor queda escuchando en `http://127.0.0.1:5000` — abrir esa
dirección en el navegador. Al abrir no se muestra ningún dato hasta que
haya una revisión real (ver "La interfaz" más abajo).

> En una PC que no sea exactamente igual a una laptop del colegio, es
> normal que algunos componentes salgan `NO_DETERMINADO` (por ejemplo, si
> esa PC no expone ciertos sensores) — no es un error del programa, ver
> la sección "Limitaciones" de `docs/reglas-recomendaciones.md`.

### Verificar que todo funciona

```bash
cd backend
python test_scanner.py                  # debe imprimir solo: test_scanner.py: todos los casos OK
cd ..
node frontend/tests/modelo.test.js      # lógica pura del frontend (también la llama test_scanner.py si hay node)
```

## La interfaz

Una sola página con tema **claro por defecto** (el oscuro es opcional y se
recuerda en el navegador):

- **Barra superior:** la marca, el interruptor **Simple | Técnico**, el botón de
  tema y la acción principal **"Revisar mi PC"** (después pasa a "Volver a
  revisar"). El menú **"Más"** agrupa lo secundario: *Informe para el técnico*
  (solo con una revisión real), *Descargar reporte (.txt)* y *Ver demostración*.
- **Pestañas:** **Resumen** (veredicto en palabras, datos del equipo, "lo primero que
  conviene hacer" y una ficha por componente), **Componentes** (tarjetas con la guía
  en modo simple; tabla técnica con filas expandibles en modo técnico) y
  **Recomendaciones** (sugerencias del equipo, F3). La pestaña *Análisis de Windows*
  está oculta hasta la fase F4a.
- **Estados con forma:** cada estado lleva su propia silueta (círculo, triángulo,
  rombo, octógono, círculo discontinuo) además del color y la palabra, para no
  depender solo del color. El informe imprimible usa las mismas formas.
- **Sin datos inventados:** antes de la primera revisión solo se ve la invitación a
  revisar; *Ver demostración* muestra datos simulados con su aviso y sin recomendaciones.

Los colores y demás tokens de diseño viven solo en `config/palette.css`
(`test_paleta` verifica los contrastes en ambos temas). El historial de por qué
quedó así está en la decisión 39 de `docs/DECISIONES.md`.

## Generar el USB booteable

```powershell
.\build\create_pe.ps1 -IsoOriginal "ruta\a\HBCD_PE_x64.iso"
```

Requiere el componente "Deployment Tools" del Windows ADK instalado (trae
`oscdimg.exe`). No hace falta PowerShell como Administrador — ya no se usa
DISM (decisión 26). Genera `build/diagnostic-scanner-pc-pe.iso`; después
hay que copiar esa ISO más las carpetas `build/python-portable/`,
`build/chromium-extracted/chrome-win/` (renombrada `chromium`), el
proyecto (`backend/`, `frontend/`, `config/` como `diagnostic_scanner_pc/`)
y `build/overlay-winpe/iniciar.bat` sueltos a la raíz del USB — detalle
completo y por qué en las decisiones 24, 25 y 26 de `DECISIONES.md`.

## Reglas para desarrolladores

- Cada módulo en `backend/modules/` expone `diagnosticar() -> dict`, sin
  argumentos, con las 5 llaves `componente`, `estado` (`normal`/
  `advertencia`/`sospecha`/`critico`/`no_determinado`), `mensaje`, `datos`,
  `recomendacion`.
- Un módulo faltante o que lanza una excepción no debe tumbar el resto del
  escaneo — `scanner.py` ya lo tolera, no lo dupliques en el módulo.
- Sin datos inventados: un sensor ausente se refleja como `null`/
  `no_determinado`, nunca como un valor plausible o como "normal".
- Cero frameworks JS, cero dependencias nuevas de Python fuera de
  `requirements.txt` sin discutirlo antes.
- Decisión arquitectónica nueva → se documenta en `docs/DECISIONES.md`, con
  fecha y motivo. No se reescribe el historial, solo se agrega.

## Licencia

MIT — proyecto académico, de uso libre para el Semillero de Mantenimiento y
cualquiera que quiera adaptarlo.
