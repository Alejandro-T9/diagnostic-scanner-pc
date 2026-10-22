# Plan F7+: mantenimiento seguro, instaladores y mejoras del proyecto

Fecha: 2026-10-22. Parte de lo que ya existe (F0–F6, decisiones 27–43) y de lo que hay hoy en la carpeta «post install colegio» del USB.

## 1. Qué hay hoy en «post install colegio» y qué hacemos con cada cosa

| Elemento | Hallazgo | Propuesta |
|---|---|---|
| Faronics Deep Freeze (`Faronics_DFS`) | Software comercial con licencia del colegio. Si el equipo está «congelado», todo cambio se pierde al reiniciar (incluida la instalación posterior). | **Detectarlo** en Post-instalación y avisar «Deep Freeze instalado: descongela antes de instalar». Solo detectar; la clave no se guarda en el proyecto. |
| `COMANDOS.txt` | Contiene la clave de Deep Freeze **en texto plano** dentro del USB. Cualquiera que lo abra la ve. También hay comandos de activación por script de terceros. | Mover la clave fuera del USB compartido (cuaderno o gestor de contraseñas). Los comandos de diagnóstico son valiosos y se convierten en funciones de la app (§2). **La app no incluirá activadores** (política vigente). |
| Office LTSC 2021 «Perpetual VL» (ISO multilenguaje) | Imagen de volumen que solo es legal con una licencia por volumen del colegio. | Averiguar si el colegio tiene licenciamiento educativo. Si no, usar **LibreOffice** (gratis, legal, abre .docx/.xlsx/.pptx) como opción por defecto de la carpeta de instaladores. |
| WinRAR 5.50 «Por Todoteg» (repack) | Versión de 2017 con una falla crítica conocida (CVE-2018-20250, ejecución de código al abrir ciertos .ace/.rar) y es un paquete no oficial. | **Reemplazar por 7-Zip** (gratis, oficial). La app marcará WinRAR < 5.70 como «versión con fallas conocidas». |
| Firefox ESR 115 | Línea ESR ya sin actualizaciones de seguridad. Sirve para Windows 7/8.1, no para Windows 10/11. | Usar Firefox ESR 140 o actual para Windows 10/11; dejar 115 solo para Windows 7 (con el aviso que ya existe). |
| Foxit PDF Reader | Gratuito oficial. | Se queda. |
| Arduino IDE 2.3.10 | Oficial y gratuito; es para la clase de electrónica. | Se queda como «opcional por perfil de sala». |
| Wub (Windows Update Blocker) | Apaga Windows Update: deja el equipo sin parches. | No automatizarlo. Mejor: **detectar** «Windows Update desactivado» y recomendar pausar solo mientras dure la jornada. |
| Optimizar PC V5.8 | Herramienta de terceros no verificable. | Reemplazar por el **módulo de mantenimiento propio** (§2), que muestra qué va a hacer y lo deshace. |
| MiniOS10 LTSC (ISO) | Windows 10 modificado no oficial (decisión del equipo pendiente). | Sustituir por el medio **oficial** de Windows 10 (Media Creation Tool) cuando haya licencia, o dejarlo con la nota honesta actual. |

## 2. Fase 7a — «Mantenimiento seguro» (la optimización automática)

Pestaña nueva **Mantenimiento**. Principios: todo es **opcional, con vista previa, confirmación por acción, punto de restauración antes de empezar y registro de lo hecho** (con «deshacer» donde se pueda). Nunca desactiva el antivirus ni Windows Update, nunca toca el registro a ciegas.

Acciones, de menor a mayor riesgo (todas salen de `COMANDOS.txt` o de buenas prácticas):

1. **Limpieza de temporales**: muestra cuántos GB libera (carpetas Temp del usuario y de Windows, papelera, caché de miniaturas) y borra solo lo marcado. Riesgo bajo.
2. **Programas de inicio**: lista los que se pueden desactivar (usa `StartupApproved`, 100 % reversible) con una casilla; nunca ofrece antivirus, audio, video ni nada con «driver». Riesgo bajo, con deshacer.
3. **Plan de energía**: pasar a «Alto rendimiento» en equipos de escritorio; en portátiles solo recomendar (gasta batería). Reversible.
4. **Reparación de Windows**: `sfc /scannow` y `DISM /CheckHealth → /ScanHealth → /RestoreHealth` con barra de progreso y registro. Requiere administrador; tarda de 10 a 40 min.
5. **Revisión de disco sin reiniciar**: `chkdsk /scan` (solo lectura) y `winsat disk` para medir velocidad; se muestran como resultado en lenguaje claro.
6. **Memoria RAM**: programa `mdsched` (reinicia, por eso solo con confirmación y recordatorio de guardar).
7. **Herramienta de software malintencionado de Microsoft** (`mrt`) lanzada con un clic.
8. **Actualización problemática** (ej. la del mouse en Windows 11 del `COMANDOS.txt`): ofrecer desinstalar un parche concreto solo si el técnico lo escribe y confirma.

Entregable de F7a: `backend/mantenimiento.py` (acciones como funciones pequeñas con `vista_previa()` y `ejecutar()`), rutas `/api/mantenimiento/...`, pestaña, pruebas con comandos simulados, decisión 44. **Antes/después**: la app guarda el análisis antes y después de optimizar, para mostrar la mejora (espacio liberado, programas de inicio, velocidad de disco).

## 3. Fase 7b — Instalador offline legítimo

- Carpeta `instaladores/` en el USB con un archivo `instaladores.json`: nombre, archivo, argumentos de instalación silenciosa, **hash SHA-256**, versión y a qué perfil pertenece (sala general, electrónica…).
- La app compara los programas instalados con el perfil y propone: «Faltan: navegador, PDF, compresor, oficina». Cada instalación pide **confirmación** y verifica el hash antes de ejecutar (si no coincide, no instala).
- Sugerencia de contenido legal: Firefox ESR vigente, Foxit Reader, **7-Zip**, **LibreOffice**, Arduino IDE (solo electrónica), VLC.
- Solo instala lo que el equipo puso en la carpeta; no descarga nada solo y no incluye activadores ni versiones modificadas.
- Entregable: `backend/instalador.py`, sección en Post-instalación, pruebas con instaladores falsos y hash incorrecto, decisión 45.

## 4. Fase 7c — Controladores y respaldo

- **Controladores faltantes**: junto a cada dispositivo con error mostrar su *Hardware ID* (para buscarlo) y, si existe la carpeta `drivers/` del USB, ofrecer instalarlos con `pnputil /add-driver` con confirmación.
- **Antes de formatear**: tamaño de Documentos, Escritorio, Imágenes y perfiles de navegadores, y copia guiada a un disco externo con `robocopy` (con confirmación y comprobación de espacio). Reduce el riesgo de perder archivos del dueño.

## 5. Más mejoras detectadas

1. **Comparar dos revisiones del mismo equipo** (antes y después de una reparación) usando el registro. Es la mejor prueba para el jurado y para evitar fraudes de técnicos.
2. **Acta imprimible** para SOPORTE TÉCNICO (HTML a PDF) con espacio de firma y un **código SHA-256 del informe**, para demostrar que no se alteró.
3. **Informe de la jornada**: cuántos PC se revisaron, cuántos con problemas, tiempos y mejoras, a partir del registro (CSV ya existe).
4. **Batería real**: `powercfg /batteryreport` (no pide administrador) da capacidad de diseño frente a la actual; mejora el módulo de batería.
5. **Detecciones de solo lectura en Post-instalación** (rápidas): Deep Freeze instalado, servicio de Windows Update desactivado, WinRAR o Firefox desactualizados.
6. **Versión y registro de cambios** dentro de la app («Acerca de»), para saber qué copia tiene cada USB.
7. **Calidad**: probar en Windows 10 real, a 1366×768 con escala de 125–150 %, con NVDA; revisar que el antivirus no bloquee la lectura de sensores.
8. **Entregables**: actualizar póster, pendón y pptx a la v2; video corto de demostración; guion de la exposición con las funciones nuevas.
9. **Seguridad del propio USB**: el registro de equipos no tiene contraseña; considerar cifrar el archivo con una clave del técnico si se guardan datos de personas.

## 6. Orden recomendado

| # | Qué | Esfuerzo | Por qué primero |
|---|---|---|---|
| 1 | Detecciones de solo lectura (§5.5) + batería real (§5.4) | Bajo | Rápido y sin riesgo |
| 2 | F7a Mantenimiento seguro (limpieza, inicio, energía, SFC/DISM, chkdsk/winsat) | Medio-alto | Es la «optimización automática» que se pidió |
| 3 | Comparar antes/después y acta con hash (§5.1–2) | Medio | Cierra la historia de evidencia contra fraudes |
| 4 | F7b Instalador offline con hash | Medio | Convierte la carpeta del colegio en algo seguro y repetible |
| 5 | F7c Controladores y respaldo | Medio | Cubre lo que más se pierde al formatear |
| 6 | Pruebas en Windows 10, NVDA, entregables v2 | Medio | Necesita tiempo del equipo físico |

## 7. Lo que NO se hará (y por qué)

- Activadores, cracks o comandos de activación de Windows/Office: ilegal y fuera de la política del proyecto. Si Windows no está activado, la app recomienda una licencia legítima.
- Desactivar el antivirus, el firewall o Windows Update, o «bloqueadores» de actualizaciones.
- Descargar programas de internet sin confirmar ni comprobar su hash.
- Instalar versiones modificadas («repacks», «Por Todoteg», «OptiOS»).
