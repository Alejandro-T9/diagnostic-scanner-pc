"""
backend/modules/ — Paquete de módulos de diagnóstico de hardware.

Cada módulo de este paquete corresponde a UNO de los 7 componentes físicos
definidos en el alcance del proyecto. Los 7 están implementados sobre WMI
(Windows/WinPE) — ver docs/DECISIONES.md y
docs/superpowers/plans/2026-08-12-pivot-winpe-hirens-pe.md para el pivote
desde la versión anterior basada en Linux.

Contrato que debe cumplir cada módulo para integrarse con scanner.py:
    - Exponer una función diagnosticar() sin argumentos.
    - Esa función debe devolver un diccionario con las 5 llaves mínimas:
      "componente" (str), "estado" (str: "normal" / "advertencia" /
      "sospecha" / "critico" / "no_determinado" — ver scanner.py
      ESTADOS_VALIDOS y docs/DECISIONES.md), "mensaje" (str), "datos"
      (dict o None) y "recomendacion" (str, puede ser "").

Módulos (archivo -> componente que diagnostica, fuente de datos WMI):
    mainboard.py       -> Tarjeta madre: fabricante, modelo, BIOS (Win32_BaseBoard, Win32_BIOS)
    cpu.py              -> Procesador: núcleos, hilos, temperatura, GPU y ventiladores (Win32_Processor, MSAcpi_ThermalZoneTemperature, LibreHardwareMonitorLib)
    ram.py               -> Memoria RAM: capacidad, velocidad, uso (Win32_PhysicalMemory, psutil)
    almacenamiento.py    -> Discos/SSD: identidad y salud S.M.A.R.T., solo discos internos (Win32_DiskDrive, MSFT_PhysicalDisk, MSFT_StorageReliabilityCounter)
    fuente_poder.py      -> Voltajes de CPU/placa vía LibreHardwareMonitorLib (sin clase WMI confiable, ver Fase 2)
    bateria.py           -> Batería: ciclos de carga, salud (Win32_Battery, BatteryStaticData/BatteryFullChargedCapacity/BatteryCycleCount)
    red.py                -> Tarjeta de red: enlace, velocidad, errores (Win32_NetworkAdapter, Win32_PerfFormattedData_Tcpip_NetworkInterface)
"""