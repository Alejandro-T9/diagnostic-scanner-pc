"""
backend/analisis/ — Análisis de Windows (F4a): espacio, inicio, programas, rendimiento.

Cada módulo responde al mismo contrato de 5 llaves que los de modules/
(componente/estado/mensaje/datos/recomendacion), pero:
- son de SOLO LECTURA: no borran, cambian ni desinstalan nada, y no piden
  administrador;
- nunca emiten `critico` (nada de lo que miden es una falla confirmada);
- NO están en scanner.COMPONENTES (eso es solo hardware); la lista de
  análisis es scanner.ANALISIS y se ejecutan aparte.
"""
