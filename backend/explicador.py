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

Hay 55 entradas (11 componentes x 5 estados): los 7 de hardware y los 4
análisis de Windows de F4a (espacio, inicio, programas, rendimiento). Algunas
son inalcanzables hoy porque el módulo correspondiente no produce ese estado
(p. ej. mainboard "critico" y red "critico"; los análisis nunca producen
"critico"); se redactan igual, con un texto honesto, por si el módulo cambia.
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
    # --- Análisis de Windows (F4a). Son solo lectura y nunca producen "critico". ---
    # Espacio libre del disco C: (advertencia bajo 10 %, sospecha bajo 5 %).
    "espacio": {
        "normal": {
            "que_significa": "Al disco principal (C:) le queda al menos un 10 % libre. Windows necesita ese margen para trabajar y actualizarse. Es una medición del momento; no revisa la salud del disco.",
            "que_hacer": ["De vez en cuando vacía la papelera y borra las descargas que ya no uses."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "Al disco principal le queda menos del 10 % libre. Windows necesita ese margen para trabajar y actualizarse; con poco espacio puede ir más lento o no poder instalar actualizaciones.",
            "que_hacer": ["Vacía la papelera y borra las descargas que ya no uses.", "Desinstala lo que no uses desde Configuración → Aplicaciones.", "Pasa tus fotos y videos a otro disco o memoria externa."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Qué ocupa más espacio en mi disco principal y qué puedo quitar sin riesgo?",
        },
        "sospecha": {
            "que_significa": "Al disco principal le queda menos del 5 % libre. Con tan poco margen Windows puede ir muy lento, trabarse o no poder actualizarse. Es falta de espacio, no una falla del disco.",
            "que_hacer": ["Vacía la papelera, borra las descargas que ya no uses y desinstala lo que no uses.", "Pasa tus fotos y videos a otro disco o memoria externa.", "No borres archivos del sistema; si no logras liberar espacio, pide ayuda a un técnico."],
            "quien": "tu_mismo",
            "urgencia": "media",
            "pregunta_tecnico": "¿Qué está ocupando tanto espacio y cómo liberarlo sin tocar archivos que Windows necesita?",
        },
        "critico": {
            "que_significa": "Esta revisión no tiene una prueba que llegue a nivel crítico en el espacio libre: con muy poco espacio se marca como sospecha. Si ves este resultado, trátalo como un error del análisis.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Qué medición concreta del espacio libre respalda este resultado?",
        },
        "no_determinado": {
            "que_significa": "No se pudo leer cuánto espacio libre queda en el disco principal. No significa que esté lleno: solo que el dato no se obtuvo.",
            "que_hacer": ["Cierra la aplicación, ábrela de nuevo y repite el análisis.", "Mientras tanto, abre Este equipo y mira la barra del disco C: para ver cuánto queda libre."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes ver cuánto espacio libre queda en el disco principal, ya que el programa no pudo leerlo?",
        },
    },
    # Programas de inicio: solo cuenta cuántos hay (advertencia desde 10).
    "inicio": {
        "normal": {
            "que_significa": "Hay pocos programas de inicio (menos de 10). Un programa de inicio es uno que arranca solo al encender el equipo. Es un conteo; no dice si cada uno hace falta.",
            "que_hacer": ["Si algún día el arranque se alarga, revisa la pestaña Inicio (en Windows 11, «Aplicaciones de inicio») del Administrador de tareas (Ctrl+Mayús+Esc)."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "Hay 10 o más programas de inicio, es decir, que arrancan solos al encender el equipo. Muchos juntos pueden hacer lento el arranque. Que haya muchos no significa que alguno sea malo.",
            "que_hacer": ["Abre el Administrador de tareas (Ctrl+Mayús+Esc) y entra en la pestaña Inicio (en Windows 11, «Aplicaciones de inicio»).", "Con clic derecho, usa «Deshabilitar» en los que no necesites al encender. No se borran y puedes volver a habilitarlos.", "No deshabilites el antivirus ni lo que diga controlador, audio o video. Si dudas de alguno, déjalo como está."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Cuáles de mis programas de inicio puedo desactivar sin problema y cuáles conviene dejar?",
        },
        "sospecha": {
            "que_significa": "Este análisis no produce este nivel para los programas de inicio; solo cuenta cuántos hay. Si lo ves, trátalo como un error del análisis, no como un diagnóstico.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "media",
            "pregunta_tecnico": "¿Qué medición de los programas de inicio respalda este resultado?",
        },
        "critico": {
            "que_significa": "Esta revisión no tiene una prueba que llegue a nivel crítico en los programas de inicio. Si ves este resultado, trátalo como un error del análisis, no como un diagnóstico.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Qué medición de los programas de inicio respalda este resultado?",
        },
        "no_determinado": {
            "que_significa": "No se pudo leer la lista de programas de inicio (los que arrancan solos al encender). No significa que haya demasiados: solo que el dato no se obtuvo.",
            "que_hacer": ["Cierra la aplicación, ábrela de nuevo y repite el análisis.", "Mientras tanto, mira la lista en el Administrador de tareas (Ctrl+Mayús+Esc), pestaña Inicio (en Windows 11, «Aplicaciones de inicio»)."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes revisar qué programas arrancan con el equipo, ya que esta herramienta no pudo leerlos?",
        },
    },
    # Programas instalados: avisa si hay 3 o más de editor desconocido instalados en los últimos 30 días.
    "programas": {
        "normal": {
            "que_significa": "Se leyó la lista de programas instalados y no hay varios recientes de editor desconocido (el editor es quien creó el programa). Esta revisión no busca virus.",
            "que_hacer": ["Recorre la lista de vez en cuando; lo que no uses puedes quitarlo desde Configuración → Aplicaciones."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "En los últimos 30 días se instalaron 3 o más programas de editor desconocido (quien lo creó). No significa que sean malos: muchos programas no informan su editor. Conviene reconocerlos.",
            "que_hacer": ["Revisa en la lista los programas instalados hace poco y sin editor conocido.", "Si no reconoces alguno, búscalo o pregunta a un técnico antes de quitarlo.", "Quita solo lo que sepas que no usas (Configuración → Aplicaciones)."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Cuáles de estos programas recientes conviene conservar y cuáles quitar, y por qué?",
        },
        "sospecha": {
            "que_significa": "Para los programas instalados esta revisión no usa el nivel de sospecha: solo avisa si hay varios recientes de editor desconocido. Si ves este resultado, es un error al interpretar los datos.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "media",
            "pregunta_tecnico": "¿Qué dato de los programas instalados respalda este resultado?",
        },
        "critico": {
            "que_significa": "Esta revisión no tiene una prueba que llegue a nivel crítico en los programas instalados. Si ves este resultado, trátalo como un error del análisis, no como un diagnóstico.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Qué dato de los programas instalados respalda este resultado?",
        },
        "no_determinado": {
            "que_significa": "No se pudo leer la lista de programas instalados. No significa que haya programas raros: solo que el dato no se obtuvo.",
            "que_hacer": ["Cierra la aplicación, ábrela de nuevo y repite el análisis.", "Mientras tanto, puedes ver la lista en Configuración → Aplicaciones."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes revisar qué programas hay instalados, ya que esta herramienta no pudo leer la lista?",
        },
    },
    # ¿Por qué va lento?: una foto del momento; advertencia si se detecta al menos una causa.
    "rendimiento": {
        "normal": {
            "que_significa": "En esta foto del momento no se detectó una causa clara de lentitud. Es solo lo medido ahora y no mide todo: el equipo puede ir lento por otras razones.",
            "que_hacer": ["Si se pone lento, repite el análisis justo en ese momento: así la foto será más útil."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "En esta foto del momento se detectó al menos una posible causa de lentitud (mira el detalle). Es solo lo medido ahora y no mide todo; conviene repetirlo cuando el equipo esté lento.",
            "que_hacer": ["Lee la causa que se indica y cierra lo que no uses.", "Si la lentitud sigue, repite el análisis cuando el equipo esté lento y muéstraselo a un técnico."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Esta causa explica la lentitud que noto y qué otra prueba conviene hacer?",
        },
        "sospecha": {
            "que_significa": "Para el rendimiento esta revisión solo detecta posibles causas y las marca como advertencia. Si ves este resultado, es un error al interpretar los datos.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "media",
            "pregunta_tecnico": "¿Qué medición del rendimiento respalda este resultado?",
        },
        "critico": {
            "que_significa": "Esta revisión no tiene una prueba que llegue a nivel crítico en el rendimiento. Si ves este resultado, trátalo como un error del análisis, no como un diagnóstico.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Qué medición del rendimiento respalda este resultado?",
        },
        "no_determinado": {
            "que_significa": "No se pudo medir el rendimiento del equipo en este momento. No significa que vaya mal: solo que no se obtuvo la foto.",
            "que_hacer": ["Cierra la aplicación, ábrela de nuevo y repite el análisis.", "Si va lento, abre el Administrador de tareas (Ctrl+Mayús+Esc) y mira qué programa usa más."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes medir qué hace lento el equipo, ya que esta herramienta no pudo hacerlo?",
        },
    },
    # --- Análisis de Windows (F4b). Solo lectura; nunca producen "critico". ---
    # Estabilidad: cuenta pantallazos azules, apagados inesperados y errores de disco de los últimos 30 días.
    "estabilidad": {
        "normal": {
            "que_significa": "En los últimos 30 días Windows no anotó fallas graves: ni pantallazos azules, ni apagados inesperados, ni errores de disco. Es solo lo que Windows registró.",
            "que_hacer": ["No hace falta hacer nada."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "Windows anotó algún pantallazo azul o varios apagados inesperados en los últimos 30 días. Puede ser un caso aislado, pero conviene vigilarlo.",
            "que_hacer": ["Anota cuándo se traba o se apaga solo y qué estabas haciendo.", "Haz copia de tus archivos importantes por precaución."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Qué causó los cierres inesperados que Windows registró y cómo lo confirmo?",
        },
        "sospecha": {
            "que_significa": "Windows anotó varios pantallazos azules o errores de disco en los últimos 30 días. Es un indicio de un posible problema de disco, memoria o controladores; aún no es un diagnóstico.",
            "que_hacer": ["Haz primero una copia de tus archivos importantes.", "Pide a un técnico que revise el disco y la memoria RAM."],
            "quien": "tecnico",
            "urgencia": "media",
            "pregunta_tecnico": "¿Puedes revisar el estado del disco y probar la memoria RAM, dado que Windows registró estos fallos?",
        },
        "critico": {
            "que_significa": "Esta revisión solo cuenta lo que Windows anotó y no llega a nivel crítico. Si ves este resultado, trátalo como un error del análisis.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Qué registro concreto respalda este resultado?",
        },
        "no_determinado": {
            "que_significa": "No se pudo leer el registro de eventos de Windows. No significa que haya fallas: solo que el dato no se obtuvo.",
            "que_hacer": ["Repite el análisis.", "Si quieres mirarlo tú, abre el Visor de eventos y busca errores recientes en «Sistema»."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes revisar el Visor de eventos, ya que esta herramienta no pudo leerlo?",
        },
    },
    # Controladores: dispositivos con driver faltante o con error (WMI, código de error distinto de 0).
    "controladores": {
        "normal": {
            "que_significa": "Windows no marca ningún dispositivo con problema de controlador (el programa que permite que una pieza funcione). No revisa si hay versiones más nuevas.",
            "que_hacer": ["No hace falta hacer nada."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "Windows marca uno o dos dispositivos con problema de controlador. Esa pieza puede no funcionar bien (sonido, red, video...).",
            "que_hacer": ["Abre el Administrador de dispositivos y mira cuáles tienen un signo de advertencia.", "Busca el controlador en la página del fabricante de tu equipo."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Qué controlador falta o falla en la lista de dispositivos y de dónde lo instalo?",
        },
        "sospecha": {
            "que_significa": "Windows marca tres o más dispositivos con problema de controlador. Es normal justo después de instalar Windows; si no es así, conviene arreglarlo.",
            "que_hacer": ["Instala los controladores desde la página del fabricante del equipo.", "Si no sabes cuáles, pide ayuda a un técnico."],
            "quien": "tecnico",
            "urgencia": "media",
            "pregunta_tecnico": "¿Puedes instalar los controladores que faltan y confirmar que no queden dispositivos con error?",
        },
        "critico": {
            "que_significa": "Esta revisión no llega a nivel crítico en controladores. Si ves este resultado, trátalo como un error del análisis.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Qué dispositivo concreto respalda este resultado?",
        },
        "no_determinado": {
            "que_significa": "No se pudo leer la lista de dispositivos de Windows. No significa que haya problemas: solo que el dato no se obtuvo.",
            "que_hacer": ["Repite el análisis.", "Mientras tanto, abre el Administrador de dispositivos y busca signos amarillos de advertencia."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes revisar el Administrador de dispositivos, ya que esta herramienta no pudo leerlo?",
        },
    },
    # Seguridad básica: antivirus de Windows, firewall y control de cuentas (solo lectura; no es un antivirus).
    "seguridad": {
        "normal": {
            "que_significa": "La protección básica de Windows que se pudo leer está activada. Esto no es un escaneo de virus: solo mira si las defensas de Windows están encendidas.",
            "que_hacer": ["Mantén Windows actualizado."],
            "quien": "nadie",
            "urgencia": "ninguna",
            "pregunta_tecnico": "",
        },
        "advertencia": {
            "que_significa": "Aparece apagada alguna defensa de Windows (antivirus, firewall o control de cuentas). Si usas otro antivirus, el de Windows se apaga solo y es normal.",
            "que_hacer": ["Abre Seguridad de Windows y mira qué aparece desactivado.", "Si no usas otro antivirus, activa la protección."],
            "quien": "tu_mismo",
            "urgencia": "media",
            "pregunta_tecnico": "¿Por qué está desactivada esta protección y hay otro antivirus que la reemplace?",
        },
        "sospecha": {
            "que_significa": "Para la protección básica esta revisión solo marca advertencia. Si ves este resultado, es un error al interpretar los datos.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "media",
            "pregunta_tecnico": "¿Qué dato de la protección respalda este resultado?",
        },
        "critico": {
            "que_significa": "Esta revisión no llega a nivel crítico en seguridad. Si ves este resultado, trátalo como un error del análisis.",
            "que_hacer": ["Vuelve a ejecutar el análisis.", "Si se repite, muestra el informe a un técnico."],
            "quien": "tecnico",
            "urgencia": "alta",
            "pregunta_tecnico": "¿Qué dato de la protección respalda este resultado?",
        },
        "no_determinado": {
            "que_significa": "No se pudo leer el estado de la protección de Windows. No significa que esté apagada: solo que el dato no se obtuvo.",
            "que_hacer": ["Abre Seguridad de Windows para ver el estado.", "Repite el análisis."],
            "quien": "tu_mismo",
            "urgencia": "baja",
            "pregunta_tecnico": "¿Puedes revisar el estado del antivirus y el firewall, ya que esta herramienta no pudo leerlos?",
        },
    },
}

# Nombres legibles de los análisis de Windows (los de hardware ya tienen los suyos en la interfaz).
NOMBRES_ANALISIS = {
    "espacio": "Espacio en disco",
    "inicio": "Programas de inicio",
    "programas": "Programas instalados",
    "rendimiento": "¿Por qué va lento?",
    "estabilidad": "Estabilidad del equipo",
    "controladores": "Controladores",
    "seguridad": "Seguridad básica",
}


def guia_para(componente: str, estado: str) -> dict:
    """Copia de la guía del par (componente, estado); genérica si no existe."""
    return copy.deepcopy(GUIAS.get(componente, {}).get(estado, _GENERICA))
