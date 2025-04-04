# app/services/ai_service.py
import logging
import httpx
import os
import json  # Asegúrate de importar json
from typing import List, Dict, Any, Optional

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.main_prompt import get_master_prompt

# Ya no necesitas questionnaire_service si el JSON está aquí

logger = logging.getLogger("hydrous")


class AIService:
    """Servicio simplificado para interactuar con LLMs, con control mínimo de flujo."""

    def __init__(self):
        """Inicialización del servicio AI"""
        self.master_prompt = get_master_prompt()

        # --- Cambio Clave 1: Cargar JSON Estructurado ---
        questionnaire_path = os.path.join(
            os.path.dirname(__file__), "cuestionario.json"  # Usa el JSON plano
        )
        self.questionnaire_steps: List[Dict[str, Any]] = []
        try:
            with open(questionnaire_path, "r", encoding="utf-8") as f:
                self.questionnaire_steps = json.load(f)
            logger.info(
                f"Cuestionario ESTRUCTURADO cargado con {len(self.questionnaire_steps)} pasos."
            )
        except Exception as e:
            logger.error(f"Error fatal al cargar cuestionario JSON: {e}")
            # Este es un error crítico, el servicio no puede funcionar sin el cuestionario
            raise ValueError("No se pudo cargar el cuestionario estructurado.") from e

        # --- Cargar Formato de Propuesta (sin cambios) ---
        proposal_format_path = os.path.join(
            os.path.dirname(__file__), "../prompts/Format Proposal.txt"
        )
        self.proposal_format_content = ""
        try:
            if os.path.exists(proposal_format_path):
                with open(proposal_format_path, "r", encoding="utf-8") as f:
                    self.proposal_format_content = f.read()
        except Exception as e:
            logger.warning(f"No se pudo cargar el formato de propuesta: {e}")

        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_URL

    def _get_next_question_index(
        self,
        current_idx: int,
        answers: Dict[str, Any],
        sector: Optional[str],
        subsector: Optional[str],
    ) -> Optional[int]:
        """Encuentra el índice de la siguiente pregunta RELEVANTE a hacer. (Versión Simplificada)"""
        search_idx = current_idx + 1
        while search_idx < len(self.questionnaire_steps):
            q_data = self.questionnaire_steps[search_idx]
            q_id = q_data.get("id", f"step_{search_idx}")

            # --- Lógica de Salto Mínima ---
            # 1. Saltar si depende de una respuesta anterior que no se dio como se esperaba
            ask_condition = q_data.get(
                "ask_if_answered"
            )  # Ej: { "id": "q24_existing_infra", "value": "Si" }
            if ask_condition:
                condition_id = ask_condition.get("id")
                condition_value = ask_condition.get("value")
                answer_data = answers.get(condition_id, {})
                if not answer_data or answer_data.get("answer") != condition_value:
                    logger.debug(f"Skipping Q {q_id} (ask_if condition not met)")
                    search_idx += 1
                    continue

            # 2. Saltar si es irrelevante para el sector/subsector
            relevant_s = q_data.get("relevant_sector")
            relevant_ss = q_data.get("relevant_subsector")
            is_relevant = True
            if relevant_s and sector not in relevant_s:
                is_relevant = False
            if (
                is_relevant
                and relevant_ss
                and subsector
                and subsector not in relevant_ss
            ):
                is_relevant = False

            if not is_relevant:
                logger.debug(f"Skipping Q {q_id} (relevance)")
                search_idx += 1
                continue
            # --- Fin Lógica de Salto ---

            # Si pasó los filtros, esta es la siguiente pregunta
            return search_idx

        return None  # No hay más preguntas

    async def handle_conversation(
        self, conversation: Conversation, user_message: str = None
    ) -> str:
        """Maneja la conversación, controlando mínimamente el flujo del cuestionario."""
        try:
            # --- Obtener Estado Actual (Desde metadata) ---
            last_presented_q_index = conversation.metadata.get(
                "current_q_index", -1
            )  # Índice de la última pregunta *presentada*
            answers = conversation.metadata.get("answers", {})
            sector = conversation.metadata.get("selected_sector")
            subsector = conversation.metadata.get("selected_subsector")

            # --- Procesar Respuesta Anterior (si aplica) ---
            if user_message and last_presented_q_index >= 0:
                if last_presented_q_index < len(self.questionnaire_steps):
                    last_q_data = self.questionnaire_steps[last_presented_q_index]
                    last_q_id = last_q_data.get("id")
                    last_q_type = last_q_data.get("type")

                    # --- Lógica Mínima de Procesamiento y Almacenamiento ---
                    answer_text_to_store = user_message  # Valor por defecto
                    is_valid_response = True  # Bandera para saber si avanzar

                    if last_q_type == "multiple_choice" and last_q_data.get("options"):
                        try:
                            choice_idx = int(user_message.strip()) - 1
                            if 0 <= choice_idx < len(last_q_data["options"]):
                                answer_text_to_store = last_q_data["options"][
                                    choice_idx
                                ]  # Guarda el texto
                            else:
                                is_valid_response = False
                                # Pedir reintento (simplificado: solo devuelve mensaje de error)
                                error_msg = f"Número inválido. Por favor, elige entre 1 y {len(last_q_data['options'])}."
                                # Re-presentar la misma pregunta sería mejor, pero requiere más lógica
                                # Devolvemos el error y *no avanzamos* el índice en metadata
                                conversation.metadata["last_error"] = (
                                    error_msg  # Opcional: guardar error
                                )
                                return error_msg  # Salir temprano sin avanzar
                        except ValueError:
                            is_valid_response = False
                            error_msg = (
                                "Por favor, responde solo con el número de la opción."
                            )
                            conversation.metadata["last_error"] = error_msg
                            return error_msg  # Salir temprano

                    # (Añadir lógica similar MÍNIMA para multiple_select si lo usas)

                    if is_valid_response and last_q_id:
                        answers[last_q_id] = {"answer": answer_text_to_store}
                        logger.debug(
                            f"Stored answer for {last_q_id}: {answer_text_to_store}"
                        )
                        # Actualizar sector/subsector si corresponde
                        if last_q_data.get("is_subsector_selector"):
                            if last_q_id.startswith("q1_"):
                                conversation.metadata["selected_sector"] = (
                                    answer_text_to_store
                                )
                                sector = answer_text_to_store
                            else:
                                conversation.metadata["selected_subsector"] = (
                                    answer_text_to_store
                                )
                                subsector = answer_text_to_store
                        # Limpiar el último error si la respuesta fue válida
                        conversation.metadata.pop("last_error", None)

                else:
                    logger.warning(
                        f"last_presented_q_index ({last_presented_q_index}) fuera de rango."
                    )
            # --- Fin Procesamiento Respuesta ---

            # --- Encontrar Siguiente Pregunta ---
            next_q_index = self._get_next_question_index(
                last_presented_q_index, answers, sector, subsector
            )

            # --- Fin del Cuestionario / Generar Propuesta ---
            if next_q_index is None:
                is_confirmed = False
                # Comprobar si la última pregunta presentada fue la de confirmación y la respuesta fue afirmativa
                if last_presented_q_index >= 0 and last_presented_q_index < len(
                    self.questionnaire_steps
                ):
                    last_q_data = self.questionnaire_steps[last_presented_q_index]
                    if (
                        last_q_data.get("type") == "confirmation"
                        and user_message
                        and user_message.lower().strip()
                        in ["si", "sí", "ok", "continuar", "proceder", "1", "yes"]
                    ):
                        is_confirmed = True

                if is_confirmed:
                    logger.info("Generando propuesta final...")
                    # Preparar prompt para la propuesta
                    proposal_prompt = self._prepare_proposal_prompt(answers)
                    final_proposal = await self._call_llm_api(proposal_prompt)
                    conversation.metadata["has_proposal"] = True
                    conversation.metadata["proposal_content"] = final_proposal
                    # Devolver un marcador o la propuesta directamente
                    # return "[PROPOSAL_COMPLETE]\n\n" + final_proposal
                    # O un mensaje indicando que se generó
                    return (
                        "¡Propuesta generada! Aquí tienes el resumen ejecutivo: (El frontend debería manejar la descarga/visualización completa)\n\n"
                        + final_proposal
                    )  # O solo las primeras líneas
                else:
                    # El cuestionario terminó pero no se confirmó la propuesta O la última no fue confirmación
                    return "Hemos completado todas las preguntas. Si necesitas generar la propuesta basada en el resumen anterior, por favor confirma."

            # --- Preparar y Llamar a la IA para la Siguiente Pregunta ---
            next_question_data = self.questionnaire_steps[next_q_index]
            conversation.metadata["current_q_index"] = (
                next_q_index  # Actualizar índice para el *próximo* turno
            )
            conversation.metadata["answers"] = (
                answers  # Guardar respuestas actualizadas
            )

            # Preparar los mensajes específicos para esta pregunta
            messages_for_ai = self._prepare_messages_for_step(
                next_question_data,
                answers,
                sector,
                subsector,
                next_q_index + 1,  # Paso actual (1-based)
                len(self.questionnaire_steps),  # Total estimado
            )

            # Llamar a la API
            ai_response = await self._call_llm_api(messages_for_ai)

            # (Opcional: quitar marcador [PROPOSAL_COMPLETE] si la IA lo añade por error aquí)
            if "[PROPOSAL_COMPLETE" in ai_response:
                logger.warning("La IA generó marcador de propuesta antes de tiempo.")
                # Considera limpiar la respuesta o manejarlo

            return ai_response

        except Exception as e:
            logger.exception(f"Error grave en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error inesperado al procesar tu consulta."

    def _prepare_messages_for_step(
        self,
        question_data: Dict[str, Any],
        answers: Dict[str, Any],
        sector: Optional[str],
        subsector: Optional[str],
        step_number: int,
        total_steps: int,
    ) -> List[Dict[str, str]]:
        """Prepara los mensajes para la IA enfocados en UN SOLO paso del cuestionario."""

        q_id = question_data["id"]
        q_text = (
            question_data["question_text"]
            if question_data["type"] != "info"
            else question_data.get("text", "")
        )
        q_expl = question_data.get("explanation", "")
        q_opts = question_data.get("options")
        q_type = question_data["type"]
        insight_topic = question_data.get("insight_topic")

        # --- Prompt del Sistema (Contexto General + Tarea Específica) ---
        system_prompt = f"""{self.master_prompt}

Contexto Actual:
- Sector: {sector or 'No definido'} | Subsector: {subsector or 'No definido'}
- Paso: {step_number} / ~{total_steps}
- Respuestas Clave Anteriores (Resumen): { {k: str(v.get('answer', 'N/A'))[:50] for k, v in answers.items() if k.startswith('q')} }

Tu tarea AHORA es realizar la siguiente acción específica:
"""
        # --- Instrucción Específica (User Prompt) ---
        user_prompt_parts = []

        # Formateo de opciones (Python lo hace aquí)
        formatted_options_string = None
        is_mcq = q_type == "multiple_choice" or q_type == "multiple_select"
        if is_mcq and q_opts:
            numbered_options = [f"{i+1}. {opt}" for i, opt in enumerate(q_opts)]
            formatted_options_string = "\n".join(numbered_options)

        # Construcción de la instrucción basada en el tipo
        if q_type == "info":
            user_prompt_parts.append(
                f'Presenta la siguiente información al usuario (ID: {q_id}): "{q_text}"'
            )
            if q_expl:
                user_prompt_parts.append(f'Incluye esta explicación: "{q_expl}"')
        elif q_type == "summary":
            user_prompt_parts.append(
                f"Genera un resumen conciso de las respuestas anteriores (ID: {q_id}). Usa el contexto proporcionado. Empieza con: \"{question_data.get('prompt_text', 'Resumen:')}\""
            )
        elif q_type == "confirmation":
            user_prompt_parts.append(
                f'Haz *exactamente* la siguiente pregunta de confirmación (ID: {q_id}): "{q_text}"'
            )
            if q_expl:
                user_prompt_parts.append(f'Añade la explicación: "{q_expl}"')
        elif q_type == "form_group":
            fields_str = ", ".join(
                [f"'{f['label']}'" for f in question_data.get("fields", [])]
            )
            user_prompt_parts.append(
                f'Pide al usuario que proporcione información para los siguientes campos relacionados (ID: {q_id}): "{q_text}". Menciona que necesitamos datos sobre: {fields_str}.'
            )
            if q_expl:
                user_prompt_parts.append(f'Explica por qué son importantes: "{q_expl}"')
        elif q_type == "request_upload":
            user_prompt_parts.append(
                f"Pide amablemente al usuario que suba un archivo si lo tiene (ID: {q_id}): \"{q_text}\". Indica que puede escribir 'omitir' o 'continuar' si no lo tiene o no desea subirlo."
            )
            if q_expl:
                user_prompt_parts.append(f'Explica la utilidad del archivo: "{q_expl}"')
        else:  # Pregunta estándar (text, multiple_choice, multiple_select, etc.)
            entity_type = "empresa/instalación"  # Placeholder
            if sector == "Municipal":
                entity_type = "municipio/localidad"
            if sector == "Residencial":
                entity_type = "vivienda/edificio"
            q_text = q_text.replace("[TIPO_ENTIDAD]", entity_type)
            user_prompt_parts.append(
                f'Haz *exactamente* la siguiente pregunta (ID: {q_id}): "{q_text}"'
            )
            if q_expl:
                user_prompt_parts.append(f'Añade esta explicación: "{q_expl}"')
            if formatted_options_string:
                user_prompt_parts.append(
                    "Presenta estas opciones numeradas EXACTAMENTE así:\n"
                    + formatted_options_string
                )
                if q_type == "multiple_choice":
                    user_prompt_parts.append(
                        "Instruye al usuario para que responda SÓLO con el número."
                    )
                else:  # multiple_select
                    user_prompt_parts.append(
                        "Instruye al usuario para que responda con los números deseados, separados por comas."
                    )

        # Añadir Insight si aplica
        if insight_topic:
            user_prompt_parts.append(
                f"\nAñade un dato interesante breve sobre '{insight_topic}' relevante para el sector/subsector del cliente."
            )

        # Regla Final Importante
        user_prompt_parts.append(
            "\nIMPORTANTE: NO hagas NINGUNA otra pregunta ni comentario adicional. Céntrate únicamente en la tarea descrita."
        )

        user_prompt = "\n".join(user_prompt_parts)

        # Devolver la lista de mensajes para la API
        # Enviamos solo el system prompt y el user prompt específico del paso
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _prepare_proposal_prompt(self, answers: Dict[str, Any]) -> List[Dict[str, str]]:
        """Prepara los mensajes específicos para generar la propuesta."""
        system_prompt = f"""
{self.master_prompt}

TAREA FINAL: Generar una propuesta preliminar DETALLADA y PROFESIONAL.
BASATE ÚNICAMENTE en las respuestas del usuario y el formato de propuesta proporcionado.
NO inventes datos. Si falta información crucial, indícalo. Incluye descargos de responsabilidad sobre estimaciones.
"""
        if self.proposal_format_content:
            system_prompt += (
                "\n\n<formato_propuesta>\n"
                + self.proposal_format_content
                + "\n</formato_propuesta>"
            )
        else:
            system_prompt += "\n\nESTRUCTURA REQUERIDA:\n- Important Disclaimer\n- Introduction to Hydrous...\n- Project Background\n- Objective...\n- Key Design Assumptions...\n- Process Design...\n- Suggested Equipment...\n- Estimated CAPEX & OPEX...\n- ROI Analysis (o indicar si faltan datos)\n- Next Steps"  # Añadir estructura básica si falta el archivo

        user_prompt = "Genera la propuesta completa usando las siguientes respuestas recopiladas del usuario:\n\n"
        for q_id, data in answers.items():
            q_text = next(
                (
                    q.get("question_text", q_id)
                    for q in self.questionnaire_steps
                    if q.get("id") == q_id
                ),
                q_id,
            )
            user_prompt += f"- {q_text}: {data.get('answer', 'N/A')}\n"
            # Podrías añadir info de archivos aquí si la guardaste bien

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    async def _call_llm_api(self, messages: List[Dict[str, str]]) -> str:
        """Llama a la API del LLM (sin cambios respecto a tu código original, excepto logging)"""
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.6,
                    "max_tokens": 3500,
                }  # Temp un poco más baja para seguir instrucciones

                logger.debug(
                    f"Llamando a API LLM con payload: {json.dumps(payload, indent=2)}"
                )  # Log payload
                response = await client.post(
                    self.api_url, json=payload, headers=headers, timeout=90.0
                )  # Aumentar timeout

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    logger.debug(
                        f"Respuesta de LLM recibida: {content[:200]}..."
                    )  # Log inicio de respuesta
                    return content
                else:
                    logger.error(
                        f"Error en API LLM: {response.status_code} - {response.text}"
                    )
                    return "Lo siento, ha habido un problema con el servicio de IA. Por favor, inténtalo de nuevo más tarde."
        except httpx.ReadTimeout:
            logger.error("Error en _call_llm_api: Timeout esperando respuesta del LLM.")
            return "Lo siento, el servicio de IA tardó demasiado en responder. Por favor, inténtalo de nuevo."
        except Exception as e:
            logger.exception(f"Error inesperado en _call_llm_api: {str(e)}")
            return "Lo siento, ha ocurrido un error inesperado al comunicarse con el servicio de IA."

    # Remover o ajustar _contains_proposal_markers si se usa marcador explícito o estado


# Instancia global (si usas este patrón)
ai_service = AIService()
