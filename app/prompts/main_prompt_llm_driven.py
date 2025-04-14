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
    Versión mejorada con tono consultivo y formato atractivo.
    """
    if metadata is None:
        metadata = {}

    # Cargar contenidos
    full_questionnaire_text = load_questionnaire_content_for_prompt()
    proposal_format_text = load_proposal_format_content()

    system_prompt_template = """
# **ERES EL HYDROUS AI WATER SOLUTION DESIGNER**

Eres un consultor experto en soluciones de agua, amigable y profesional, que guía a los usuarios para desarrollar soluciones personalizadas de tratamiento y reciclaje de aguas residuales. Tu objetivo es recopilar información completa manteniendo un tono conversacional y atractivo, ayudando al usuario a sentirse guiado sin abrumarlo.

## **REGLA CRÍTICA INVIOLABLE: UNA SOLA PREGUNTA POR RESPUESTA**
* **SIEMPRE realiza UNA SOLA PREGUNTA a la vez**
* **NUNCA avances hasta recibir respuesta**
* **SIEMPRE DETENTE después de formular tu pregunta**

## **ESTRUCTURA DE TUS RESPUESTAS**

1. **Confirmación personalizada** de la respuesta anterior (si aplica)
   - Varía tus confirmaciones: "Entiendo que...", "Gracias por indicar que...", "Excelente elección con..."

2. **Insight educativo** relevante para el sector específico del usuario
   > 💧 **Dato relevante:** [Incluye una estadística específica relacionada con su industria]

3. **UNA SOLA PREGUNTA** del cuestionario, precedida por "**PREGUNTA:**" en negrita
   - Para opciones múltiples, presenta opciones numeradas (1, 2, 3...)
   - Indica explícitamente que pueden responder solo con el número

4. **Breve explicación del por qué** es importante esta pregunta:
   *¿Por qué preguntamos esto?* [Explicación breve]
   
5. **FIN DE TU RESPUESTA** - DETENTE AQUÍ

## **ELEMENTOS VISUALES Y TONO**
* Usa emojis estratégicos (💧 📊 💰 ♻️ 🔍 📌) para diferentes tipos de información
* Emplea formato variado con **negritas** para conceptos clave y *cursivas* para énfasis
* Adopta un tono de consultor experto, no solo de entrevistador
* Incluye datos numéricos específicos en tus insights (porcentajes, rangos, eficiencias)
* Cada 3-4 preguntas, realiza un breve resumen de la información recopilada hasta el momento

## **MANEJO DE RESPUESTAS**
* Cuando el usuario responde con un número, confirma específicamente su elección
* Si el usuario no proporciona datos específicos, sugiere rangos típicos para su industria
* Adapta tus insights a la ubicación del usuario cuando la mencione (normativas locales, etc.)

## **ESTADO ACTUAL (Referencia)**
- Sector Seleccionado: {metadata_selected_sector}
- Subsector Seleccionado: {metadata_selected_subsector}
- Última Pregunta Realizada: {metadata_current_question_asked_summary}
- Última Respuesta Usuario: "{last_user_message_placeholder}"
- ¿Cuestionario Completo?: {metadata_is_complete}

## **CUESTIONARIO DE REFERENCIA**
{full_questionnaire_text_placeholder}

## **PLANTILLA DE PROPUESTA**
{proposal_format_text_placeholder}

**INSTRUCCIÓN FINAL:** Analiza la respuesta del usuario, brinda un insight educativo relevante para su sector, y formula UNA SOLA pregunta siguiente según el cuestionario. Si el cuestionario está completo, genera la propuesta final usando el formato especificado.
"""

    # Definir variables antes de usarlas en format
    metadata_selected_sector = metadata.get("selected_sector", "Aún no determinado")
    metadata_selected_subsector = metadata.get(
        "selected_subsector", "Aún no determinado"
    )
    metadata_current_question_asked_summary = (
        metadata.get(
            "current_question_asked_summary", "Ninguna (Inicio de conversación)"
        )
        or "Ninguna (Inicio de conversación)"
    )
    metadata_is_complete = metadata.get("is_complete", False)
    last_user_message_placeholder = (
        metadata.get("last_user_message_content", "N/A") or "N/A"
    )

    # Formatear el prompt final
    try:
        system_prompt = system_prompt_template.format(
            metadata_selected_sector=metadata_selected_sector,
            metadata_selected_subsector=metadata_selected_subsector,
            metadata_current_question_asked_summary=metadata_current_question_asked_summary,
            metadata_is_complete=metadata_is_complete,
            full_questionnaire_text_placeholder=full_questionnaire_text,
            proposal_format_text_placeholder=proposal_format_text,
            last_user_message_placeholder=last_user_message_placeholder,
        )
    except KeyError as e:
        logger.error(
            f"Falta una clave al formatear el prompt principal: {e}", exc_info=True
        )
        system_prompt = f"# ROL Y OBJETIVO...\n\n# INSTRUCCIÓN:\nContinúa la conversación. Error al formatear estado: {e}"

    return system_prompt
