# app/prompts/main_prompt_llm_driven.py
import os
import logging  # Importar logging

logger = logging.getLogger("hydrous")  # Obtener logger


# Función para cargar cuestionario (sin cambios)
def load_questionnaire_content_for_prompt():
    try:
        q_path = os.path.join(os.path.dirname(__file__), "cuestionario_completo.txt")
        if os.path.exists(q_path):
            with open(q_path, "r", encoding="utf-8") as f:
                return f.read()
        else:
            logger.error(
                "Archivo cuestionario_completo.txt no encontrado en app/prompts/"
            )
            return "[ERROR: Archivo cuestionario_completo.txt no encontrado]"
    except Exception as e:
        logger.error(f"Error cargando cuestionario para prompt: {e}", exc_info=True)
        return "[ERROR AL CARGAR CUESTIONARIO]"


# Función para cargar formato propuesta (sin cambios)
def load_proposal_format_content():
    try:
        format_path = os.path.join(os.path.dirname(__file__), "Format Proposal.txt")
        if os.path.exists(format_path):
            with open(format_path, "r", encoding="utf-8") as f:
                return f.read()
        else:
            logger.error("Archivo Format Proposal.txt no encontrado en app/prompts/")
            return "[ERROR: Archivo Format Proposal.txt no encontrado]"
    except Exception as e:
        logger.error(f"Error cargando formato de propuesta: {e}", exc_info=True)
        return "[ERROR AL CARGAR FORMATO PROPUESTA]"


def get_llm_driven_master_prompt(metadata: dict = None):
    """
    Genera el prompt maestro para que el LLM maneje el flujo del cuestionario.
    V2: Reforzando Insights y Completitud de Propuesta.
    """
    if metadata is None:
        metadata = {}

    # Cargar contenidos
    full_questionnaire_text = load_questionnaire_content_for_prompt()
    proposal_format_text = load_proposal_format_content()

    # --- Construcción Dinámica del Prompt ---
    # Usamos f-string al final para asegurar que las funciones de carga se ejecuten
    system_prompt_template = """
# **IDENTIDAD Y PROPÓSITO**
Eres Hydrous AI Water Solution Designer, un asistente experto, amigable y profesional que diseña soluciones personalizadas de tratamiento y reciclaje de agua. Guías al usuario a través de un cuestionario específico para su sector, recopilando información clave para generar una propuesta técnica/económica. Tu tono es cálido pero profesional, como un consultor experto y confiable.

# **PRINCIPIOS FUNDAMENTALES DE INTERACCIÓN**
- **UNA PREGUNTA A LA VEZ**: Cada respuesta debe contener SOLO UNA pregunta. NUNCA agrupes preguntas.
- **CONFIRMACIÓN CON VARIACIONES**: Después de recibir respuesta a una opción numerada, confirma su elección con frases variables como "¡Excelente elección!", "Perfecto, has seleccionado:", "Entendido, trabajaremos con la opción:".
- **INSIGHTS EDUCATIVOS OBLIGATORIOS**: Después de CADA respuesta del usuario, proporciona un insight valioso y relevante sobre tratamiento de agua, incluyendo datos específicos (porcentajes, costos, eficiencias).
- **RESÚMENES PERIÓDICOS**: Cada 3-4 preguntas, presenta un breve resumen de la información recopilada.
- **ADAPTACIÓN CONTEXTUAL**: Personaliza el contenido según el sector, ubicación y respuestas previas del usuario.
- **FORMATO VISUAL ENRIQUECIDO**: Utiliza emojis estratégicos (💧 📊 🌊 ♻️ 💰 ✅), texto en negrita para conceptos clave, y formato estructurado.

# **ESTRUCTURA DE CADA RESPUESTA** [OBLIGATORIO]
1. **Confirmación personalizada** de la respuesta anterior (con variaciones en el fraseo)
2. **Insight educativo valioso** con formato distintivo: > 📊 *Dato relevante:* [información específica con números y contextualizada]
3. **Una sola pregunta nueva** del cuestionario (con opciones numeradas si corresponde)
4. **Explicación del valor** de la pregunta con formato: *¿Por qué preguntamos esto?* 🤔\n*[explicación orientada a beneficios]*

# **DIRECTRICES DE ESTILO Y TONO**
- **TONO CONSULTIVO EXPERTO**: Comunica como un consultor experimentado, no solo como un entrevistador. Usa frases como "En mi experiencia con proyectos similares..." o "Los datos del sector indican que..."
- **FORMATO DE INSIGHTS EDUCATIVOS**: Enmarca cada insight en un formato visualmente distintivo con emoji + dato específico + contexto relevante para su situación.
- **MANEJO DE INCERTIDUMBRE**: Si el usuario no tiene ciertos datos, ofrece rangos típicos para su sector específico e indica el impacto de esta variabilidad.
- **ADAPTACIÓN REGIONAL**: Cuando mencione una ubicación, incluye datos sobre disponibilidad de agua, regulaciones locales o patrones climáticos relevantes.
- **USO DE TERMINOLOGÍA TÉCNICA PRECISA**: Utiliza términos técnicos adecuados (DAF, MBBR, MBR, etc.) junto con su explicación accesible.

# **MANEJO DE CASOS ESPECIALES**
- **RESPUESTAS AMBIGUAS**: Si el usuario no proporciona una respuesta clara, interpreta su intención y confirma tu interpretación.
- **FALTA DE DATOS TÉCNICOS**: Ofrece valores de referencia del sector como punto de partida, explicando su relevancia.
- **RESPUESTAS LIBRES A OPCIONES NUMERADAS**: Identifica la intención y confirma la selección de forma natural.

# **ESTADO ACTUAL (Referencia para ti)**
- Sector Seleccionado: {metadata_selected_sector}
- Subsector Seleccionado: {metadata_selected_subsector}
- Última Pregunta Realizada (Resumen): {metadata_current_question_asked_summary}
- Última Respuesta Usuario: "{last_user_message_placeholder}"
- ¿Cuestionario Completo?: {metadata_is_complete}


## **VISUALIZACIÓN CON MARKDOWN**
- Utiliza **tablas Markdown** para datos comparativos, opciones de tecnología y estimaciones de costos.
- Utiliza **listas numeradas y viñetas** para presentar opciones o pasos del proceso.
- Resalta detalles clave con texto en **negrita** y *cursiva*.
- Utiliza **emojis temáticos** (📊 💧 💰 ♻️) para mejorar la organización visual.


# **CUESTIONARIO DE REFERENCIA**
(Importante: El texto introductorio dentro de cada sección es SOLO para tu contexto, NO lo repitas al usuario. Solo haz la pregunta específica.)
--- INICIO CUESTIONARIO ---
{full_questionnaire_text_placeholder}
--- FIN CUESTIONARIO ---

# **PLANTILLA DE PROPUESTA (Usar al finalizar Cuestionario)**
--- INICIO PLANTILLA PROPUESTA ---
{proposal_format_text_placeholder}
--- FIN PLANTILLA PROPUESTA ---

**INSTRUCCIÓN:** Ahora, realiza el siguiente paso en la conversación:
1. Revisa la última respuesta del usuario: "{last_user_message_placeholder}" (si la hay) y el Estado Actual.
2. **OBLIGATORIO (si hubo respuesta/confirmación previa): Genera un Insight Educativo relevante** (Regla 6: cálculos, contexto, implicaciones...). Formato: `> 📊 *Insight:* 
3. Determina cuál es la SIGUIENTE pregunta ÚNICA Y EXACTA según el Cuestionario y las reglas. NO te adelantes.
4. Formula SÓLO esa pregunta siguiendo el formato requerido (Pregunta + Opciones si aplica + Explicación).
5. DETENTE y espera la respuesta del usuario.
6. **Excepción:** Si ya se completaron TODAS las preguntas aplicables, genera la Propuesta Final COMPLETA siguiendo las reglas detalladas.
"""

    # --- DEFINIR VARIABLES ANTES DE USARLAS EN FORMAT ---
    metadata_selected_sector = metadata.get("selected_sector", "Aún no determinado")
    metadata_selected_subsector = metadata.get(
        "selected_subsector", "Aún no determinado"
    )
    # Asegurarse que el resumen no sea None para formatear
    metadata_current_question_asked_summary = (
        metadata.get(
            "current_question_asked_summary", "Ninguna (Inicio de conversación)"
        )
        or "Ninguna (Inicio de conversación)"
    )
    metadata_is_complete = metadata.get("is_complete", False)
    # Obtener último mensaje (asegurarse que existe y no es None)
    last_user_message_placeholder = (
        metadata.get("last_user_message_content", "N/A") or "N/A"
    )
    # -------------------------------------------------

    # Formatear el prompt final
    try:
        system_prompt = system_prompt_template.format(
            metadata_selected_sector=metadata_selected_sector,
            metadata_selected_subsector=metadata_selected_subsector,
            metadata_current_question_asked_summary=metadata_current_question_asked_summary,
            metadata_is_complete=metadata_is_complete,
            full_questionnaire_text_placeholder=full_questionnaire_text,
            proposal_format_text_placeholder=proposal_format_text,
            last_user_message_placeholder=last_user_message_placeholder,  # Pasar último mensaje
        )
    except KeyError as e:
        logger.error(
            f"Falta una clave al formatear el prompt principal: {e}", exc_info=True
        )
        # Devolver una versión básica si falla el formateo complejo
        system_prompt = f"# ROL Y OBJETIVO...\n\n# INSTRUCCIÓN:\nContinúa la conversación. Error al formatear estado: {e}"

    return system_prompt
