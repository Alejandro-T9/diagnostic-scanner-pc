"""
backend/explicador.py — Textos en lenguaje simple para cada resultado del análisis.

Esta tabla es la ÚNICA fuente de los textos "para personas sin conocimientos
técnicos": el informe y, vía /api/guias, el frontend leen de aquí. No se
repiten en otro lado. Los umbrales citados (70/85 °C, 80/95 %, 40/70 %) son
los de backend/modules/*.py — si cambian allá, hay que cambiarlos acá y en
docs/reglas-recomendaciones.md.

El equipo revisa la redacción (spec §8). Reglas de estilo: frases cortas,
tuteo, sin jerga (si hay un término técnico, se explica en la misma frase),
sin alarmismo, sin marcas ni precios, y nunca afirmar que la PC está
"limpia", "segura" o "infectada": esta herramienta mide hardware, no busca
virus. Si el dato no se pudo leer, se dice tal cual y qué puede intentar la
persona.

Hay 35 entradas (7 componentes x 5 estados). Algunas son inalcanzables hoy
porque el módulo correspondiente no produce ese estado (p. ej. mainboard
"critico" y red "critico"); se redactan igual, con un texto honesto, por si el módulo cambia.
"""

import copy

QUIEN_VALIDOS = {"tu_mismo", "tecnico", "nadie"}
URGENCIAS_VALIDAS = {"ninguna", "baja", "media", "alta"}

# Palabras con que el informe y el reporte de texto nombran a quien hace el paso.
QUIEN_TEXTO = {"tu_mismo": "Tú mismo", "tecnico": "Un técnico", "nadie": "Nadie"}

# Frase corta del veredicto global (llaves = scanner._SEVERIDAD en mayúsculas).
FRASES_VEREDICTO = {
    "NORMAL": "Tu PC está bien",
    "ADVERTENCIA": "Tu PC necesita atención",
    "SOSPECHA": "Tu PC necesita atención",
    "CRITICO": "Tu PC tiene un problema serio",
    "NO_DETERMINADO": "No pudimos revisar todo",
}

_GENERICA = {
    "que_significa": "No pudimos interpretar este resultado para darte una explicación sencilla.",
    "que_hacer": [
        "Vuelve a ejecutar el análisis.",
        "Si se repite, muestra el informe completo a un técnico.",
    ],
    "quien": "tecnico",
    "urgencia": "baja",
    "pregunta_tecnico": "¿Puedes explicarme qué significa este resultado y qué medición lo respalda?",
}

GUIAS = {
    # Tarjeta madre: solo se mira si fabricante y modelo vienen con datos reales o con texto de relleno.
    "mainboard": {
        "normal": {
            "que_significa": "La placa principal (la pieza donde se conectan todas las demás) informa su fabricante y modelo. Esto solo indica que se identifica; no prueba que funcione bien.",
            "que_hacer": ["Mantén el equipo en un lugar ventilado y evita golpes."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "La placa principal no informa su fabricante o modelo reales: trae textos de relleno. Puede pasar por cómo se configuró de fábrica o porque el equipo no entregó el dato, y no prueba por sí solo una falla.",
            "que_hacer": ["Pide a un técnico que mire la placa y confirme su marca y modelo."],
            "quien": "tecnico",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Qué marca y modelo de placa ves por dentro, y por qué el equipo no los informa?",
        },
        "sospecha": {
            "que_significa": "Esta revisión no tiene una prueba que marque sospecha en la placa principal. Si ves este resultado, es un error al interpretar los datos, no un diagnóstico.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "media",
            "pregunta_tecnico": "¿Qué medición concreta de la placa principal respalda este resultado?",
        },
        "critico": {
            "que_significa": "Esta revisión no tiene una prueba que llegue a nivel crítico en la placa principal. Si ves este resultado, trátalo como un error del análisis, no como un diagnóstico.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Qué medición concreta de la placa principal respalda este resultado?",
        },
        "no_determinado": {
            "que_significa": "No se pudo leer la información de la placa principal. No significa que esté dañada: solo que el equipo no entregó esos datos.",
            "que_hacer": ["Cierra la aplicación, ábrela de nuevo y repite el análisis.", "Si sigue igual, pide a un técnico que la identifique por dentro."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes identificar la placa directamente, ya que el programa no pudo leerla?",
        },
    },
    # Procesador: solo su temperatura decide el estado (advertencia desde 70 °C, crítico sobre 85 °C).
    "cpu": {
        "normal": {
            "que_significa": "El procesador (el \"cerebro\" del equipo) está por debajo de 70 °C, una temperatura normal. Es la medición que decide su estado.",
            "que_hacer": ["Limpia el polvo de las rejillas de ventilación de vez en cuando."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "El procesador está entre 70 °C y 85 °C. Es una temperatura alta pero aún no crítica, y puede ser normal si el equipo estaba trabajando mucho.",
            "que_hacer": ["Cierra los programas que no uses, espera unos minutos y repite el análisis.", "Si sigue alta con el equipo en reposo, pide que revisen su ventilación."],
            "quien": "tu_mismo",
            "urgencia": "media",
            "pregunta_tecnico": "¿Qué temperatura marca con el equipo en reposo y qué parte de la refrigeración necesita atención?",
        },
        "sospecha": {
            "que_significa": "Para el procesador esta revisión solo mide la temperatura y la clasifica en otros niveles. Si ves este resultado, es un error al interpretar los datos.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "media",
            "pregunta_tecnico": "¿Qué medición del procesador respalda este resultado?",
        },
        "critico": {
            "que_significa": "El procesador superó los 85 °C. Mantenida, una temperatura así puede dañarlo o hacer que el equipo se apague solo.",
            "que_hacer": ["Guarda tu trabajo y apaga el equipo para que se enfríe.", "Pide a un técnico que revise la refrigeración antes de volver a usarlo con normalidad."],
            "quien": "tecnico",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Qué parte de la refrigeración falla y cómo lo comprobaste antes de cambiar algo?",
        },
        "no_determinado": {
            "que_significa": "No se pudo leer la temperatura del procesador. Sin permisos de administrador, algunos sensores del equipo no se pueden leer.",
            "que_hacer": ["Cierra la aplicación y ábrela de nuevo, aceptando el aviso de Windows que pide permisos de administrador. Suele resolverlo.", "Si sigue igual, puede que tu equipo no entregue ese dato; no indica una falla."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes medir la temperatura del procesador con tu propio instrumento, ya que este programa no pudo?",
        },
    },
    # Memoria RAM: solo mide cuánta se usa en el momento (advertencia desde 80 %, crítico sobre 95 %).
    "ram": {
        "normal": {
            "que_significa": "La memoria RAM (donde el equipo guarda lo que está usando en este momento) se usa por debajo del 80 %. Mide cuánta se usa; no prueba que las piezas de memoria estén sanas.",
            "que_hacer": ["Cierra los programas y pestañas que no estés usando."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "La memoria RAM se está usando entre el 80 % y el 95 %. El equipo puede ir más lento, aunque a veces es solo porque hay muchos programas abiertos.",
            "que_hacer": ["Cierra los programas y pestañas que no necesites y repite el análisis.", "Si el uso es alto siempre, incluso con pocos programas, pregunta a un técnico si hace falta más memoria."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Cuánta memoria usa el equipo con pocos programas abiertos y qué prueba muestra que hace falta ampliarla?",
        },
        "sospecha": {
            "que_significa": "Para la memoria RAM esta revisión solo mide el porcentaje de uso y lo clasifica en otros niveles. Si ves este resultado, es un error al interpretar los datos.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "media",
            "pregunta_tecnico": "¿Qué medición de la memoria respalda este resultado?",
        },
        "critico": {
            "que_significa": "La memoria RAM se está usando por encima del 95 %. El equipo puede ponerse muy lento o trabarse. Es lo medido en este momento, no un daño comprobado.",
            "que_hacer": ["Guarda tu trabajo y cierra los programas que no necesites.", "Reinicia el equipo y vuelve a analizar para ver si el uso sigue igual de alto."],
            "quien": "tu_mismo",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Qué programa consume tanta memoria, o qué prueba muestra que las memorias instaladas no alcanzan?",
        },
        "no_determinado": {
            "que_significa": "No se pudo leer la información de la memoria RAM. No significa que esté dañada: solo que el equipo no entregó esos datos.",
            "que_hacer": ["Cierra la aplicación, ábrela de nuevo y repite el análisis.", "Si sigue igual, consulta a un técnico."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes revisar la memoria con una prueba propia, ya que el programa no pudo leerla?",
        },
    },
    # Almacenamiento: salud del disco interno según Windows (S.M.A.R.T.); los discos USB no cuentan.
    "almacenamiento": {
        "normal": {
            "que_significa": "Windows informa que el disco (donde se guardan tus archivos) está sano. Es el chequeo de salud que Windows hace al disco; no reemplaza tener copias de tus archivos.",
            "que_hacer": ["Haz una copia de seguridad de tus archivos importantes con regularidad."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "Para el disco esta revisión no usa el nivel de advertencia: o Windows lo marca con salud reducida, o crítica. Si ves este resultado, es un error al interpretar los datos.",
            "que_hacer": ["Haz una copia de seguridad de tus archivos importantes.", "Vuelve a ejecutar el análisis."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Qué dice el estado de salud del disco que respalda este resultado?",
        },
        "sospecha": {
            "que_significa": "Windows marca la salud del disco como reducida: no está del todo sano. No quiere decir que vaya a fallar mañana, pero conviene proteger tus archivos.",
            "que_hacer": ["Copia tus archivos importantes a otro disco o memoria externa.", "Pide a un técnico que revise el disco antes de decidir si cambiarlo."],
            "quien": "tu_mismo",
            "urgencia": "media",
            "pregunta_tecnico": "¿Qué prueba muestra que el disco debe cambiarse y no solo respaldarse?",
        },
        "critico": {
            "que_significa": "Windows marca la salud del disco como crítica: hay riesgo real de perder los archivos guardados en él.",
            "que_hacer": ["Antes que nada, copia tus archivos importantes a otro disco o memoria externa.", "Después, pide a un técnico que cambie el disco. Mientras tanto, úsalo lo menos posible."],
            "quien": "tecnico",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Puedes recuperar mis archivos antes de tocar el disco, y qué prueba muestra que debe cambiarse?",
        },
        "no_determinado": {
            "que_significa": "No se encontró ningún disco interno, o se encontró pero no se pudo leer su salud. En ambos casos no podemos decir si está sano.",
            "que_hacer": ["Cierra la aplicación, ábrela de nuevo y repite el análisis. Si el equipo tiene disco y sigue igual, puede ayudar aceptar el aviso de permisos de Windows.", "Mientras tanto, mantén copia de tus archivos importantes."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes revisar el disco con una prueba propia, ya que el programa no pudo leer su salud?",
        },
    },
    # Fuente de poder: solo lee voltajes del procesador; no mide cargador, batería ni la fuente en sí.
    "fuente_poder": {
        "normal": {
            "que_significa": "Los voltajes del procesador que se pudieron leer están dentro de lo posible. No se mide el cargador, la batería ni la fuente de energía, así que esto no prueba que estén bien.",
            "que_hacer": ["Revisa que el cable del cargador no esté pelado ni doblado."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "Para la fuente de poder esta revisión no usa el nivel de advertencia. Si ves este resultado, es un error al interpretar los datos.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Qué medición de voltaje respalda este resultado?",
        },
        "sospecha": {
            "que_significa": "Un sensor de voltaje dio una lectura imposible (cero o más de 20 voltios). Puede ser un fallo del sensor o de la alimentación; esta revisión no distingue cuál.",
            "que_hacer": ["Repite el análisis para ver si la lectura se repite.", "Si se repite, pide a un técnico que mida la alimentación con un instrumento."],
            "quien": "tecnico",
            "urgencia": "media",
            "pregunta_tecnico": "¿Qué medición propia muestra que falla la alimentación y no solo el sensor?",
        },
        "critico": {
            "que_significa": "Para la fuente de poder esta revisión no tiene una prueba que llegue a nivel crítico. Si ves este resultado, trátalo como un error del análisis.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Qué medición de voltaje respalda este resultado?",
        },
        "no_determinado": {
            "que_significa": "No se pudo leer ningún sensor de voltaje: las laptops a menudo no los ofrecen, o el programa no pudo cargar su lector de sensores. No indica una falla.",
            "que_hacer": ["Puedes intentar cerrar la aplicación y abrirla de nuevo aceptando el aviso de Windows de permisos.", "Si no cambia, este dato no se puede revisar con esta herramienta; si dudas de la alimentación, consulta a un técnico."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes medir la alimentación del equipo con un instrumento, ya que el programa no pudo?",
        },
    },
    # Batería: compara lo que carga hoy con lo que cargaba nuevo (advertencia hasta 70 %, crítico bajo 40 %).
    "bateria": {
        "normal": {
            "que_significa": "La batería conserva más del 70 % de la capacidad con la que salió de fábrica (o el equipo no tiene batería, como los de escritorio).",
            "que_hacer": ["Evita que el equipo se caliente mucho mientras carga."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "La batería conserva entre el 40 % y el 70 % de su capacidad original. Dura menos que cuando era nueva, algo normal con el uso.",
            "que_hacer": ["Si te alcanza para lo que haces, puedes seguir usándola; ten el cargador a mano.", "Si ya te queda corta, consulta a un técnico por el cambio."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Qué porcentaje de capacidad mides en la batería y por qué conviene cambiarla ahora?",
        },
        "sospecha": {
            "que_significa": "Para la batería esta revisión solo compara su capacidad actual con la original y la clasifica en otros niveles. Si ves este resultado, es un error al interpretar los datos.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "media",
            "pregunta_tecnico": "¿Qué medición de la batería respalda este resultado?",
        },
        "critico": {
            "que_significa": "La batería conserva menos del 40 % de su capacidad original. Es probable que dure bastante menos que cuando era nueva.",
            "que_hacer": ["Usa el equipo conectado al cargador.", "Consulta a un técnico para cambiar la batería."],
            "quien": "tecnico",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Qué porcentaje de capacidad mide la batería y cuánto dura realmente sin cargador?",
        },
        "no_determinado": {
            "que_significa": "Se detectó una batería, pero no se pudieron leer los datos de su capacidad. Sin ellos no sabemos qué tan gastada está.",
            "que_hacer": ["Cierra la aplicación, ábrela de nuevo y repite el análisis.", "Mientras tanto, fíjate cuánto dura tu batería en el uso diario."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes medir la capacidad de la batería con una herramienta propia?",
        },
    },
    # Red: mira si hay enlace (cable o Wi-Fi) y si la tarjeta registra paquetes con errores. Sin enlace = advertencia (decisión 36); "critico" es inalcanzable.
    "red": {
        "normal": {
            "que_significa": "La tarjeta de red tiene enlace con tu router o red (por cable o Wi-Fi) y no registra errores en los paquetes de datos. No se comprueba que el internet funcione ni su velocidad.",
            "que_hacer": ["Mantén al día las actualizaciones de Windows, que pueden incluir mejoras del software de la tarjeta de red."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "Ninguna tarjeta de red física tiene conexión en este momento. Puede ser simplemente que no haya cable ni Wi-Fi conectado.",
            "que_hacer": ["Revisa que el cable esté conectado, o que el Wi-Fi esté activado y el modo avión apagado, y repite.", "Si sigue sin conexión, pide a un técnico que revise la tarjeta y su software de control (driver)."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Qué prueba muestra que falla la tarjeta o su driver y no la red a la que me conecto?",
        },
        "sospecha": {
            "que_significa": "Hay conexión, pero la tarjeta registró paquetes con errores (los paquetes son los pedazos en que viajan los datos). Esta revisión no dice la causa; lo habitual es revisar el cable o la señal.",
            "que_hacer": ["Acércate al router o prueba otro cable de red, y repite el análisis.", "Si los errores siguen, pide a un técnico que revise la tarjeta de red."],
            "quien": "tu_mismo",
            "urgencia": "media",
            "pregunta_tecnico": "¿Qué prueba muestra que el problema está en la tarjeta del equipo y no en el cable o el router?",
        },
        "critico": {
            "que_significa": "Esta revisión no tiene una prueba que llegue a nivel crítico en la red: si no hay conexión, se marca como advertencia. Si ves este resultado, trátalo como un error del análisis, no como un diagnóstico.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Qué medición concreta de la red respalda este resultado?",
        },
        "no_determinado": {
            "que_significa": "No se detectó ninguna tarjeta de red, o hay conexión pero no se pudo leer su conteo de errores. Sin ese dato no podemos decir si funciona bien.",
            "que_hacer": ["Cierra la aplicación, ábrela de nuevo y repite el análisis.", "Si no aparece ninguna tarjeta de red, consulta a un técnico."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes comprobar la tarjeta de red con una prueba propia, ya que el programa no pudo leerla?",
        },
    },
}


def guia_para(componente: str, estado: str) -> dict:
    """Copia de la guía del par (componente, estado); genérica si no existe."""
    return copy.deepcopy(GUIAS.get(componente, {}).get(estado, _GENERICA))
