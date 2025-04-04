# questionnaires.py

# ==============================================================================
# ¡¡¡IMPORTANTE!!!
# REEMPLAZA ESTA LISTA CON LAS PREGUNTAS REALES DE TU CUESTIONARIO
# EN EL ORDEN EXACTO EN QUE DEBEN HACERSE.
# ASEGÚRATE DE QUE CADA 'key' SEA ÚNICA.
# ==============================================================================
DEFAULT_QUESTIONS = [
    {
        "id": 1,
        "key": "sector",  # Clave para guardar la respuesta
        "question_text": "¿En qué sector opera tu empresa?",
        "explanation": "Esto nos ayuda a entender el contexto general de tus necesidades y las regulaciones aplicables.",
        "type": "multiple_choice",
        "options": [
            "1. Industrial",
            "2. Comercial",
            "3. Municipal",
            "4. Residencial",
        ],
    },
    {
        "id": 2,
        "key": "subsector_industrial",  # Ejemplo
        "question_text": "Dentro del sector Industrial, ¿cuál es tu subsector principal?",
        "explanation": "Diferentes industrias (ej. Textil, Alimentos) tienen distintos tipos de aguas residuales y requisitos de tratamiento.",
        "type": "multiple_choice",
        "options": [
            "1. Alimentos y Bebidas",
            "2. Textil",
            "3. Química",
            "4. Manufactura General",
            "5. Minería",
            "6. Otro (especificar)",
        ],
        # Nota: Podrías añadir lógica más compleja para saltar preguntas
        # basadas en respuestas anteriores, pero empieza simple.
    },
    {
        "id": 3,
        "key": "location",
        "question_text": "¿Cuál es la ubicación (ciudad/estado/país) de sus instalaciones?",
        "explanation": "La ubicación es clave para entender las normativas de descarga locales, costos de agua/energía y factores climáticos.",
        "type": "text",
    },
    {
        "id": 4,
        "key": "flow_rate_avg",
        "question_text": "¿Cuál es el caudal diario promedio de aguas residuales que generan (en m³/día o galones/día)?",
        "explanation": "Este es uno de los datos más críticos para dimensionar correctamente todos los componentes del sistema de tratamiento.",
        "type": "number_unit",  # Indica que se espera un número y tal vez una unidad
    },
    {
        "id": 5,
        "key": "wastewater_source",
        "question_text": "¿Cuál es el origen principal de estas aguas residuales (proceso industrial, sanitario, mezcla, etc.)?",
        "explanation": "El origen determina en gran medida las características contaminantes del agua.",
        "type": "text_long",
    },
    {
        "id": 6,
        "key": "analysis_available",
        "question_text": "¿Disponen de análisis fisicoquímicos recientes de sus aguas residuales (DQO, DBO, TSS, pH, nutrientes, metales, etc.)?",
        "explanation": "Tener análisis detallados es ideal para un diseño preciso. Si no los tienes, podemos trabajar con valores típicos de tu industria.",
        "type": "multiple_choice",
        "options": [
            "1. Sí, tenemos análisis completos.",
            "2. Sí, tenemos algunos parámetros.",
            "3. No, no disponemos de análisis recientes.",
        ],
        # Aquí podrías tener lógica para pedir subir archivo si responden "1" o "2"
    },
    # ===> AÑADE AQUÍ EL RESTO DE TUS PREGUNTAS <===
    # Sigue el mismo formato: id, key, question_text, explanation, type, options (si aplica)
    # Ejemplo de pregunta final antes de la propuesta
    {
        "id": 99,  # Asegúrate que sea el último ID antes de la propuesta
        "key": "final_confirmation",
        "question_text": "Hemos recopilado la información inicial clave. ¿Hay algún detalle adicional importante, objetivo específico (ej. reutilización para riego, cumplimiento de norma X) o corrección que quieras mencionar antes de que prepare un resumen y una propuesta conceptual?",
        "explanation": "Este es el momento ideal para añadir cualquier matiz o prioridad que no hayamos cubierto explícitamente.",
        "type": "text_long",
    },
]
# ==============================================================================

TOTAL_QUESTIONS = len(DEFAULT_QUESTIONS)  # Calcula el número total

# ==============================================================================
# PLANTILLA DE PROPUESTA - AJÚSTALA SEGÚN TU FORMATO EXACTO
# Usa {claves_del_cuestionario} para insertar las respuestas
# ==============================================================================
PROPOSAL_TEMPLATE = """
**Propuesta Conceptual de Solución de Tratamiento de Agua - Hydrous AI**

**1. Introducción a Hydrous Management Group:**
Hydrous Management Group se especializa en el diseño e implementación de soluciones innovadoras y eficientes para el tratamiento y reciclaje de aguas residuales industriales, comerciales y municipales. Nuestro enfoque basado en datos y tecnología de vanguardia nos permite crear sistemas a medida que optimizan el uso del agua, aseguran el cumplimiento normativo y generan ahorros significativos para nuestros clientes.

**2. Antecedentes del Proyecto:**
- **Cliente (Sector/Ubicación):** Opera en el sector '{sector}' {',(subsector ' + subsector_industrial + ')' if subsector_industrial else ''} ubicado en '{location}'.
- **Volumen de Agua:** Genera un caudal promedio estimado de '{flow_rate_avg}'.
- **Origen del Agua:** Principalmente de '{wastewater_source}'.
- **Datos Analíticos:** Estado actual de análisis fisicoquímicos: '{analysis_available}'.
- **Objetivo Principal (Inferido/Declarado):** [IA debe inferir basado en respuestas y la pregunta 'final_confirmation', ej: Cumplir normativas de descarga, reducir consumo de agua fresca mediante reutilización, minimizar costos operativos, etc.]

**3. Objetivo del Proyecto:**
Diseñar conceptualmente un sistema de tratamiento de aguas residuales descentralizado y personalizado para las instalaciones del cliente, capaz de tratar el caudal mencionado y alcanzar los objetivos de calidad de agua requeridos para [IA: descarga segura / reutilización específica].

**4. Supuestos Clave y Datos de Diseño:**
- **Caudal de Diseño:** {flow_rate_avg} (Se recomienda validar con mediciones precisas).
- **Características Estimadas del Agua Residual (Basado en sector '{subsector_industrial or sector}' y respuestas. Indicar si son supuestos):**
    - DQO: [IA estima/pregunta] mg/L
    - DBO₅: [IA estima/pregunta] mg/L
    - Sólidos Suspendidos Totales (TSS): [IA estima/pregunta] mg/L
    - pH: [IA estima/pregunta]
    - Nitrógeno Total (N): [IA estima/pregunta] mg/L
    - Fósforo Total (P): [IA estima/pregunta] mg/L
    - [Otros parámetros relevantes si se mencionaron o son típicos del sector, ej. Aceites y Grasas, Metales, Color, etc.]
- **Normativa de Referencia:** [IA: Mencionar normativa local/nacional relevante si es posible basada en 'location', o indicar que se requiere confirmación].

**5. Diseño de Proceso Recomendado (Conceptual):**
Basado en la información proporcionada y las características esperadas del agua, se propone el siguiente tren de tratamiento multietapa:
- **Pretratamiento:** [IA recomienda: ej. Cribado grueso/fino, desbaste, tamizado] para eliminar sólidos grandes.
- **Tratamiento Primario:** [IA recomienda: ej. Tanque de homogeneización/ecualización, ajuste de pH, DAF (Flotación por Aire Disuelto) si hay grasas/sólidos finos, sedimentación primaria] para estabilizar flujo y remover sólidos/grasas.
- **Tratamiento Secundario (Biológico):** [IA recomienda: ej. MBBR (Reactor de Lecho Móvil), MBR (Biorreactor de Membrana), Lodos Activados Convencionales, SBR (Reactor Biológico Secuencial)] para eliminar materia orgánica disuelta (DBO/DQO).
- **Tratamiento Terciario (si aplica para reutilización o normas estrictas):** [IA recomienda: ej. Filtración avanzada (arena, multimedia, ultrafiltración), desinfección (Cloro, UV, Ozono)] para pulir efluente y eliminar patógenos.
- **Tratamiento Avanzado (si aplica para reutilización de alta calidad o ZLD):** [IA recomienda: ej. Ósmosis Inversa (RO), electrodesionización (EDI), evaporación] para desalinización y concentración.
- **Línea de Lodos:** [IA menciona brevemente: ej. Espesamiento, deshidratación (filtro prensa, centrífuga), digestión] para manejar los lodos generados.

**Justificación:** Cada etapa se selecciona para abordar contaminantes específicos presentes en aguas del sector '{subsector_industrial or sector}', asegurando eficiencia y cumplimiento. [IA: Añadir breve justificación específica].

**6. Equipos y Dimensionamiento Preliminar (Muy Aproximado):**
- Tanque de Ecualización: ~[IA estima volumen] m³
- Reactor Biológico: ~[IA estima volumen o carga]
- Clarificador / Módulo MBR / DAF: ~[IA estima área o flujo]
- Sistema de Desinfección: ~[IA estima capacidad]
*Estos tamaños son conceptuales y requieren ingeniería de detalle.*

**7. Estimación de Costos (Orden de Magnitud):**
- **CAPEX (Inversión Inicial Estimada):** [IA genera rango amplio, ej. $XXX,XXX - $Y,YYY,YYY USD]*. Depende fuertemente de la tecnología final, ubicación, y proveedor.
- **OPEX (Costos Operativos Anuales Estimados):** [IA genera rango, ej. $AA,AAA - $BB,BBB USD]*. Incluye energía, químicos, manejo de lodos, personal, mantenimiento.
***Descargo de responsabilidad:** Estas cifras son estimaciones muy preliminares para fines de planificación inicial. Se requiere un estudio de viabilidad e ingeniería de detalle para costos precisos.*

**8. Análisis ROI (Potencial):**
- **Ahorro Potencial:** Reducción de costos de agua fresca (si hay reutilización), disminución de tasas de descarga, posible recuperación de subproductos.
- **Cumplimiento y Riesgo:** Evitación de multas por incumplimiento, mejora de imagen corporativa y sostenibilidad.
- **Período de Retorno (Estimado):** [IA puede intentar estimar un rango muy amplio si hay datos suficientes sobre costos de agua/descarga, o indicar que requiere análisis detallado].

**9. Próximos Pasos Recomendados:**
1.  **Validación de Datos:** Realizar/recopilar análisis fisicoquímicos detallados del agua residual.
2.  **Medición de Caudales:** Confirmar caudales promedio y máximos.
3.  **Estudio de Tratabilidad/Prueba Piloto:** (Recomendado) Para validar el rendimiento de las tecnologías seleccionadas con el agua real.
4.  **Ingeniería Básica y de Detalle:** Desarrollar planos, especificaciones técnicas y obtener cotizaciones firmes.
5.  **Análisis de Permisos:** Investigar y gestionar los permisos ambientales necesarios.

**10. Confidencialidad:**
Toda la información proporcionada por el cliente se trata con estricta confidencialidad y se utiliza exclusivamente para el propósito de desarrollar esta propuesta conceptual.

---
*Generado por Hydrous AI Solution Designer. Esta propuesta es conceptual y no constituye una oferta formal. Se requiere verificación y diseño detallado.*
"""
# ==============================================================================
