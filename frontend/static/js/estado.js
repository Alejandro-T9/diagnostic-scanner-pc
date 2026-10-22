// frontend/static/js/estado.js — Constantes compartidas del frontend (movidas tal cual de app.js).
// Script clásico: las `const` quedan como globales para dom.js, vistas.js y app.js; el
// module.exports del final es solo para las pruebas con Node.

// Nombres legibles de cada componente (mismo orden que backend/scanner.py COMPONENTES).
const NOMBRES_COMPONENTES = {
    mainboard: "Tarjeta Madre",
    cpu: "Procesador",
    ram: "Memoria RAM",
    almacenamiento: "Almacenamiento",
    fuente_poder: "Fuente de Poder",
    bateria: "Batería",
    red: "Red",
};

// Texto corto del chip de estado (la palabra "estado" ya no hace falta,
// el color + la palabra alcanzan). Mismos 5 niveles que
// backend/scanner.py ESTADOS_VALIDOS.
const CHIP_TEXTO = {
    normal: "Normal",
    advertencia: "Advertencia",
    sospecha: "Sospecha",
    critico: "Crítico",
    no_determinado: "Sin datos",
};

// Mismo orden que _SEVERIDAD en backend/scanner.py (ver decisión 22 en
// docs/DECISIONES.md): el estado más severo presente entre los
// componentes define el veredicto global. "no_determinado" pesa menos
// que "advertencia" — evidencia real de un problema en OTRO componente
// no debe quedar tapada en el titular por un sensor que no respondió.
const SEVERIDAD = ["critico", "sospecha", "advertencia", "no_determinado", "normal"];

// Etiquetas en español para las llaves de "datos" que devuelve cada
// módulo — ver backend/modules/*.py. Una llave sin entrada acá cae al
// fallback de _etiquetaCampo() en vistas.js (reemplaza guiones bajos, capitaliza).
const ETIQUETAS_CAMPOS = {
    fabricante: "Fabricante", modelo: "Modelo", version: "Versión",
    bios_vendor: "Proveedor BIOS", bios_version: "Versión BIOS", bios_fecha: "Fecha BIOS",
    nombre: "Nombre", arquitectura: "Arquitectura",
    nucleos_fisicos: "Núcleos físicos", hilos_logicos: "Hilos lógicos",
    frecuencia_maxima_mhz: "Frecuencia máxima", temperatura_c: "Temperatura",
    temperatura_gpu_c: "Temperatura GPU", ventiladores: "Ventiladores", rpm: "Velocidad",
    capacidad_fisica_gb: "Capacidad física instalada",
    capacidad_disponible_so_gb: "Disponible para el sistema operativo",
    velocidad_mhz: "Velocidad", frecuencia_actual_mhz: "Frecuencia actual",
    configuracion_canales: "Canales", modulos_detectados: "Módulos detectados",
    porcentaje_uso: "Uso", interfaz: "Interfaz", tamano_gb: "Tamaño",
    salud: "Salud", desgaste_porcentaje: "Desgaste", externo: "Conexión USB",
    horas_encendido: "Horas de encendido", errores_lectura: "Errores de lectura",
    aplica: "Aplica", estado_carga: "Estado de carga",
    porcentaje_carga_actual: "Carga actual", ciclos_carga: "Ciclos de carga",
    salud_porcentaje: "Salud", link_activo: "Enlace activo",
    velocidad_mbps: "Velocidad", errores_rx: "Errores recibidos",
    discos_internos: "Discos internos", discos_externos: "Discos externos (no afectan el estado)",
    interfaces: "Interfaces",
    origen: "Origen", sensor: "Sensor", voltios: "Voltaje", rieles: "Sensores de voltaje",
    gpu: "GPU", driver: "Controlador (driver)",
};

const DATOS_MOCK = {
    componentes: {
        mainboard: { componente: "mainboard", estado: "normal", mensaje: "Chipset y buses estables", datos: null },
        cpu: { componente: "cpu", estado: "normal", mensaje: "4 núcleos, 45°C", datos: null },
        ram: { componente: "ram", estado: "advertencia", mensaje: "8GB detectados, uso elevado", datos: null },
        almacenamiento: { componente: "almacenamiento", estado: "sospecha", mensaje: "Salud reducida (Windows Storage Health) en 1 disco", datos: null },
        fuente_poder: { componente: "fuente_poder", estado: "normal", mensaje: "Voltajes dentro de rango", datos: null },
        bateria: { componente: "bateria", estado: "critico", mensaje: "Capacidad al 42% del diseño original", datos: null },
        red: { componente: "red", estado: "no_determinado", mensaje: "No se detectó ninguna interfaz de red física", datos: null },
    },
};

const QUIEN_TEXTO = {
    tu_mismo: "Lo puedes hacer tú",
    tecnico: "Mejor con un técnico",
    nadie: "No necesita acción",
};

// "Análisis de Windows" llega en F4a: hasta entonces su pestaña y su panel están ocultos.
const ANALISIS_DISPONIBLE = false;

if (typeof module !== "undefined") {
    module.exports = { ANALISIS_DISPONIBLE, NOMBRES_COMPONENTES, CHIP_TEXTO, SEVERIDAD, QUIEN_TEXTO, ETIQUETAS_CAMPOS, DATOS_MOCK };
}
