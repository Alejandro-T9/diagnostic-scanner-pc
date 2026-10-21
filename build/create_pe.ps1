# build/create_pe.ps1 — Automatiza el remaster de Hiren's Boot PE con
# arranque 100% automático hacia Diagnostic Scanner PC.
#
# IMPORTANTE — cinco hallazgos reales en hardware, en cinco rondas de
# prueba con bisección (aislando una variable por vez, cada hipótesis
# confirmada booteando de verdad, nunca solo revisando el script):
#
# 1. La primera versión inyectaba Python portable y Chromium portable
#    DENTRO de boot.wim con DISM. boot.wim pesaba ~2.25GB comprimido, y
#    en modo WIMBOOT Windows tiene que descomprimir esa imagen completa
#    en RAM antes de arrancar nada — en una laptop de 8GB, el Boot
#    Manager falló con 0xc0000017 ("not enough memory to create a
#    ramdisk device").
#
# 2. Se redujo boot.wim (nada de Chromium/Python adentro) pero SIGUIÓ
#    fallando — esta vez sin error legible, rebotando al menú de Ventoy
#    antes de llegar siquiera a Windows Boot Manager.
#
# 3. La causa real: una ISO reconstruida con oscdimg SIN ningún cambio
#    arranca bien. Pero CUALQUIER archivo editado (probado con boot.wim
#    vía DISM, y por separado con HBCD_PE.ini como texto plano) rompe el
#    arranque — coincidencia clave: en ambos casos, el archivo editado
#    quedaba con fecha de modificación de HOY, rodeado de miles de
#    archivos originales fechados 2021. Restaurando la fecha original
#    del archivo después de editarlo, arranca bien (no se investigó el
#    mecanismo exacto — sospecha: UDF o el propio Ventoy son sensibles a
#    un archivo con fecha más nueva que el resto del volumen). Una copia
#    SIN editar (Copy-Item de la ISO completa) no tiene este problema:
#    Copy-Item preserva LastWriteTime del origen automáticamente: el
#    riesgo es solo para archivos realmente MODIFICADOS después de
#    copiarlos (DISM, o una edición de texto).
#
# 4. Con (3) resuelto usando HBCD_PE.ini + "Y:\iniciar.bat" (Y: es la
#    letra que el propio archivo de ejemplo de Hiren's PE usa para su
#    medio de arranque), el arranque funcionó Y el autoarranque SÍ
#    disparó un intento de EXEC — pero apuntaba a la letra equivocada.
#    Motivo real: esa convención "Y:" es de Hiren's PE arrancando con su
#    instalador de USB nativo, NO se cumple arrancando vía Ventoy.
#    Confirmado en hardware real: Ventoy le asignó "E:" al medio de
#    arranque en esa prueba (podría ser cualquier letra en la siguiente).
#
# 5. Se cambió de estrategia para (4): en vez de arreglar la letra fija,
#    se movió el autoarranque a la carpeta de Inicio de Windows DENTRO de
#    boot.wim (vía DISM), con un script que recorre las letras posibles.
#    Probado en hardware real: el arranque y el escritorio cargan bien,
#    pero el autoarranque NUNCA se disparó (4 minutos de espera, nada).
#    Motivo probable: Hiren's PE no corre el flujo normal de logon de
#    Windows (winlogon/userinit) que es lo que procesa la carpeta de
#    Inicio en un Windows real — el shell (Explorer) se lanza directo,
#    sin ese paso. En cambio, el mecanismo de (4) SÍ es real: HBCD_PE.ini
#    (sección "_SUB ExtPrograms") si disparó el intento de EXEC, solo con
#    la letra equivocada. Por eso esta versión vuelve a HBCD_PE.ini como
#    ÚNICO mecanismo de autoarranque, ahora con el mismo recorrido de
#    letras de (5) en vez de una letra fija — y ya no hace falta DISM en
#    absoluto (HBCD_PE.ini vive suelto en la ISO, no dentro de boot.wim),
#    lo que también elimina el requisito de PowerShell como Administrador.
#
# Python, Chromium y el proyecto siguen sueltos en la unidad USB (no
# dentro de la ISO) — ver docs/DECISIONES.md.
#
# Necesita: el componente "Deployment Tools" del Windows ADK instalado
# (trae oscdimg.exe). El instalador del ADK no agrega oscdimg al PATH
# automáticamente (confirmado) — se referencia acá por su ruta de
# instalación estándar directamente. NO hace falta PowerShell como
# Administrador (ya no se usa DISM).
#
# Uso:
#   .\create_pe.ps1 -IsoOriginal "C:\Users\User\Downloads\HBCD_PE_x64.iso"

param(
    [Parameter(Mandatory = $true)]
    [string]$IsoOriginal
)

$ErrorActionPreference = "Stop"

$RutaProyecto = (Get-Item "$PSScriptRoot\..").FullName
$DirTrabajo = "C:\pe-build"
$IsoFinal = "$RutaProyecto\build\diagnostic-scanner-pc-pe.iso"
$OscdimgExe = "C:\Program Files (x86)\Windows Kits\10\Assessment and Deployment Kit\Deployment Tools\amd64\Oscdimg\oscdimg.exe"

# Recorre las letras posibles en vez de asumir una fija -- Ventoy NO
# garantiza una letra fija para el medio de arranque (ver hallazgo 4).
# "@" = correr en segundo plano (no bloquea el resto de ExtPrograms),
# sintaxis de modificadores documentada en el propio HBCD_PE.ini.
$LineaExecAutoarranque = "`tEXEC @%WinDir%\System32\cmd.exe /c for %D in (D E F G H I J K L M N O P Q R S T U V W) do if exist %D:\iniciar.bat call %D:\iniciar.bat"

function Morir($mensaje) {
    Write-Host "[ERROR] $mensaje" -ForegroundColor Red
    exit 1
}

function VerificarRequisitos {
    if (-not (Test-Path $IsoOriginal)) { Morir "No existe el archivo: $IsoOriginal" }
    if (-not (Test-Path $OscdimgExe)) {
        Morir "No se encontró oscdimg.exe en $OscdimgExe — instalá el componente 'Deployment Tools' del Windows ADK."
    }
}

function MontarIsoOriginal {
    Write-Host "[INFO] Montando la ISO original..."
    Mount-DiskImage -ImagePath $IsoOriginal | Out-Null
    $volumen = (Get-DiskImage -ImagePath $IsoOriginal | Get-Volume)
    $script:LetraIso = $volumen.DriveLetter
    if (-not (Test-Path "$($script:LetraIso):\HBCD_PE.ini")) {
        Morir "No encontré HBCD_PE.ini en la ISO montada — ¿es una ISO de Hiren's Boot PE válida?"
    }
}

function CopiarIsoCompletaAWorkdir {
    Write-Host "[INFO] Copiando el contenido completo de la ISO original a un directorio de trabajo..."
    $dirIsoTrabajo = "$DirTrabajo\iso-nueva"
    Remove-Item $dirIsoTrabajo -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $dirIsoTrabajo -Force | Out-Null
    # Copy-Item preserva LastWriteTime del origen automáticamente -- ver
    # hallazgo 3. Como acá no se edita nada todavía, no hace falta
    # restaurar fecha de ningún archivo en este paso.
    Copy-Item "$($script:LetraIso):\*" $dirIsoTrabajo -Recurse -Force
    $script:DirIsoTrabajo = $dirIsoTrabajo
}

function ActivarAutoarranque {
    Write-Host "[INFO] Activando autoarranque en HBCD_PE.ini..."
    $iniPath = "$($script:DirIsoTrabajo)\HBCD_PE.ini"
    if (-not (Test-Path $iniPath)) { Morir "No encontré HBCD_PE.ini en el directorio de trabajo." }
    Set-ItemProperty -Path $iniPath -Name IsReadOnly -Value $false

    # Se captura ACÁ, antes de editar -- ver hallazgo 3: hay que
    # restaurar esta fecha después de guardar, o el arranque se rompe.
    $fecha = (Get-Item $iniPath).LastWriteTime
    $creacion = (Get-Item $iniPath).CreationTime

    $contenido = Get-Content -Path $iniPath -Raw
    $marcador = "_SUB ExtPrograms"
    if (-not $contenido.Contains($marcador)) {
        Morir "No encontré la sección '_SUB ExtPrograms' en HBCD_PE.ini -- estructura inesperada."
    }
    $idx = $contenido.IndexOf($marcador) + $marcador.Length
    $contenidoNuevo = $contenido.Substring(0, $idx) + "`r`n" + $LineaExecAutoarranque + $contenido.Substring($idx)

    Set-Content -Path $iniPath -Value $contenidoNuevo -NoNewline

    # Restaurar la fecha original -- ver nota CRÍTICA (hallazgo 3). Sin
    # esto, el arranque se rompe (confirmado en hardware real).
    $item = Get-Item $iniPath
    $item.LastWriteTime = $fecha
    $item.CreationTime = $creacion
}

function ArmarIsoFinal {
    Write-Host "[INFO] Generando la ISO final con oscdimg..."
    $etfsboot = "$($script:DirIsoTrabajo)\boot\etfsboot.com"
    $efisys = "$($script:DirIsoTrabajo)\efi\microsoft\boot\efisys.bin"
    if (-not (Test-Path $etfsboot)) { Morir "No encontré boot\etfsboot.com — estructura de ISO inesperada." }

    if (Test-Path $efisys) {
        # BIOS + UEFI (boot híbrido) — la mayoría de las ISOs WinPE modernas lo traen.
        & $OscdimgExe -m -o -u2 -udfver102 `
            -bootdata:"2#p0,e,b$etfsboot#pEF,e,b$efisys" `
            $script:DirIsoTrabajo $IsoFinal
    } else {
        # Solo BIOS, por si la ISO no trae arranque UEFI.
        & $OscdimgExe -m -o -u2 -udfver102 -b$etfsboot $script:DirIsoTrabajo $IsoFinal
    }
    if ($LASTEXITCODE -ne 0) { Morir "oscdimg falló al generar la ISO." }
}

function Limpiar {
    Write-Host "[INFO] Desmontando la ISO original..."
    Dismount-DiskImage -ImagePath $IsoOriginal -ErrorAction SilentlyContinue | Out-Null
}

try {
    VerificarRequisitos
    MontarIsoOriginal
    CopiarIsoCompletaAWorkdir
    ActivarAutoarranque
    ArmarIsoFinal
    Write-Host "[OK] ISO generada: $IsoFinal" -ForegroundColor Green
    Write-Host "[INFO] Probala booteando esta ISO nueva (no la original) en la PC del colegio con Ventoy."
} finally {
    Limpiar
}
