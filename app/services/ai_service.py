# app/services/ai_service.py
import logging
import httpx
import os
import json  # Para formatear datos
from typing import List, Dict, Any, Optional

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.main_prompt import get_master_prompt  # NUEVO PROMPT

# Importar el servicio de cuestionario simplificado
from app.services.questionnaire_service import questionnaire_service

logger = logging.getLogger("hydrous")


class AIService:

    def __init__(self):
        self.master_prompt_template = (
            get_master_prompt()
        )  # Cargar prompt para enfoque híbrido

        # Cargar formato de propuesta (sin cambios)
        proposal_format_path = os.path.join(
            os.path.dirname(__file__), "../prompts/Format Proposal.txt"
        )
        self.proposal_format_content = ""
        # ... (lógica para cargar proposal_format_content igual que antes) ...
        try:
            if os.path.exists(proposal_format_path):
                with open(proposal_format_path, "r", encoding="utf-8") as f:
                    self.proposal_format_content = f.read()
            else:
                logger.error(
                    f"Archivo de formato de propuesta no encontrado en: {proposal_format_path}"
                )
                self.proposal_format_content = "# Formato de Propuesta No Encontrado\n"
        except Exception as e:
            logger.error(f"Error al cargar formato de propuesta: {e}", exc_info=True)
            self.proposal_format_content = "Error al cargar formato."

        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_URL
        # ... (verificaciones de API Key/URL igual que antes) ...
        if not self.api_key:
            logger.critical("¡Clave API de IA no configurada!")
        if not self.api_url:
            logger.critical("¡URL de API de IA no configurada!")

    async def _call_llm_api(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1500,
        temperature: float = 0.5,
    ) -> str:
        """Llama a la API del LLM (sin cambios respecto a la versión anterior)."""
        # ... (La función _call_llm_api se mantiene igual que en tu última versión) ...
        if not self.api_key or not self.api_url:
            error_msg = "Error de configuración: Clave API o URL no proporcionada."
            logger.error(error_msg)
            return error_msg
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                logger.debug(
                    f"Llamando a API LLM: {self.api_url} con modelo {self.model}. Mensajes: {len(messages)}"
                )
                response = await client.post(
                    self.api_url, json=payload, headers=headers, timeout=90.0
                )
                response.raise_for_status()
                data = response.json()
                content = (
                    data.get("choices", [{}])[0].get("message", {}).get("content", "")
                )
                logger.debug(
                    f"Respuesta LLM recibida (primeros 100 chars): {content[:100]}"
                )
                if not content:
                    logger.warning("Respuesta del LLM vacía.")
                    return "(El asistente no proporcionó una respuesta)"
                return content.strip()
        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            logger.error(
                f"Error HTTP en API LLM: {e.response.status_code} - {error_body}",
                exc_info=True,
            )
            return f"Error al contactar el servicio de IA ({e.response.status_code}). Detalles: {error_body[:500]}"
        except httpx.RequestError as e:
            logger.error(f"Error de red llamando a API LLM: {e}", exc_info=True)
            return f"Error de red al contactar el servicio de IA: {e}"
        except Exception as e:
            logger.error(f"Error inesperado en _call_llm_api: {str(e)}", exc_info=True)
            return "Lo siento, ha ocurrido un error inesperado al procesar la solicitud con la IA."

    def _determine_next_question_id_simple(
        self, metadata: Dict[str, Any]
    ) -> Optional[str]:
        """Lógica MUY simplificada para obtener el siguiente ID (solo secuencia inicial)."""
        current_q_id = metadata.get("current_question_id")
        initial_q_ids = [
            q["id"]
            for q in questionnaire_service.structure.get("initial_questions", [])
            if "id" in q
        ]

        if current_q_id is None:
            return initial_q_ids[0] if initial_q_ids else None
        if current_q_id == "INIT_0":
            return "INIT_1"
        if current_q_id == "INIT_1":
            return "INIT_2"
        if current_q_id == "INIT_2":
            # Aquí necesitaríamos la lógica para encontrar la primera pregunta del sector/subsector
            # Por ahora, simulamos que después de INIT_2 viene IAB_1 si es A&B
            if (
                metadata.get("selected_sector") == "Industrial"
                and metadata.get("selected_subsector") == "Alimentos y Bebidas"
            ):
                return "IAB_1"  # Ejemplo
            else:
                # TODO: Implementar lógica completa de ruta o marcar como completo si es 'Otro'
                logger.warning(
                    f"_determine_next_question_id_simple: Lógica de ruta post-inicial no implementada para {metadata.get('selected_sector')}/{metadata.get('selected_subsector')}"
                )
                return None  # Marcar como fin temporalmente
        # TODO: Añadir lógica para el resto de la secuencia del cuestionario seleccionado
        # Esta función debería volverse más robusta o usar la lista 'questionnaire_path' en metadata
        logger.warning(
            f"Lógica de secuencia no definida para pregunta actual: {current_q_id}"
        )
        return None  # Fin temporal

    def _build_llm_messages(
        self, conversation: Conversation, instruction: str
    ) -> List[Dict[str, str]]:
        """Construye la lista de mensajes para la API del LLM."""
        messages = [{"role": "system", "content": self.master_prompt_template}]

        # Añadir historial relevante (simplificado - últimos N mensajes)
        MAX_HISTORY_MSGS = 10  # Ajustar según sea necesario
        start_index = max(0, len(conversation.messages) - MAX_HISTORY_MSGS)
        for msg in conversation.messages[start_index:]:
            # Evitar añadir mensajes de sistema duplicados si los hubiera
            if msg.role != "system":
                messages.append({"role": msg.role, "content": msg.content})

        # Añadir la instrucción específica como último mensaje del sistema
        messages.append({"role": "system", "content": instruction})

        return messages

    async def get_next_response(self, conversation: Conversation) -> str:
        """
        Determina el siguiente paso (pregunta o propuesta), construye el prompt
        con la instrucción adecuada y obtiene la respuesta del LLM.
        """
        metadata = conversation.metadata
        last_user_message = (
            conversation.messages[-1].content
            if conversation.messages and conversation.messages[-1].role == "user"
            else None
        )

        # --- Lógica de Transición y Actualización de Estado Simple ---
        current_q_id = metadata.get("current_question_id")
        if current_q_id and last_user_message:
            # Procesar respuesta anterior y actualizar metadata
            # Nota: La validación/procesamiento ahora es mínima aquí, el LLM interpretará
            processed_answer = last_user_message.strip()  # Simple strip
            metadata["collected_data"][current_q_id] = processed_answer
            logger.info(
                f"DBG_AI: Dato guardado para {current_q_id}: '{processed_answer}'"
            )
            # Actualizar sector/subsector en metadata
            if current_q_id == "INIT_1":
                # Asumir que el usuario respondió con el texto o número correcto
                # Necesitaríamos mapear número a texto si el usuario responde con número
                # Por simplicidad, asumimos que processed_answer es el nombre del sector
                if processed_answer.isdigit():  # Si respondió número
                    q_details = questionnaire_service.get_question_details("INIT_1")
                    try:
                        idx = int(processed_answer) - 1
                        if (
                            q_details
                            and q_details.get("options")
                            and 0 <= idx < len(q_details["options"])
                        ):
                            metadata["selected_sector"] = q_details["options"][idx]
                            logger.info(
                                f"DBG_AI: Sector actualizado a '{metadata['selected_sector']}' (desde número)"
                            )
                        else:
                            logger.warning(
                                f"DBG_AI: Número de opción inválido '{processed_answer}' para INIT_1"
                            )
                            # ¿Qué hacer? Podríamos pedir que repita. Por ahora, dejamos None.
                    except ValueError:
                        metadata["selected_sector"] = None  # No fue número válido
                elif processed_answer in [
                    "Industrial",
                    "Comercial",
                    "Municipal",
                    "Residencial",
                ]:
                    metadata["selected_sector"] = processed_answer
                    logger.info(
                        f"DBG_AI: Sector actualizado a '{metadata['selected_sector']}' (desde texto)"
                    )
                else:
                    logger.warning(
                        f"DBG_AI: Respuesta '{processed_answer}' no reconocida como sector válido para INIT_1"
                    )
                    metadata["selected_sector"] = None

            elif current_q_id == "INIT_2":
                # Lógica similar para subsector (más compleja por ser condicional)
                sector = metadata.get("selected_sector")
                if sector:
                    q_details = questionnaire_service.get_question_details("INIT_2")
                    conditions = q_details.get("conditions", {}) if q_details else {}
                    options = conditions.get(sector, [])
                    if processed_answer.isdigit():
                        try:
                            idx = int(processed_answer) - 1
                            if options and 0 <= idx < len(options):
                                metadata["selected_subsector"] = options[idx]
                                logger.info(
                                    f"DBG_AI: Subsector actualizado a '{metadata['selected_subsector']}' (desde número)"
                                )
                            else:
                                logger.warning(
                                    f"DBG_AI: Número de opción inválido '{processed_answer}' para INIT_2/{sector}"
                                )
                        except ValueError:
                            pass  # Ignorar si no es número
                    else:  # Intentar coincidencia por texto
                        matched = False
                        for opt in options:
                            if processed_answer.lower() == opt.lower():
                                metadata["selected_subsector"] = opt
                                logger.info(
                                    f"DBG_AI: Subsector actualizado a '{metadata['selected_subsector']}' (desde texto)"
                                )
                                matched = True
                                break
                        if not matched:
                            logger.warning(
                                f"DBG_AI: Respuesta '{processed_answer}' no reconocida como subsector válido para INIT_2/{sector}"
                            )
                            metadata["selected_subsector"] = None  # O quizás "Otro"?

        # --- Determinar Siguiente Paso ---
        next_q_id = self._determine_next_question_id_simple(metadata)

        if next_q_id:
            # --- Construir Instrucción para la Siguiente Pregunta ---
            metadata["current_question_id"] = next_q_id  # Actualizar ID actual
            next_q_details = questionnaire_service.get_question_details(next_q_id)
            if not next_q_details:
                logger.error(
                    f"No se encontraron detalles para la siguiente pregunta: {next_q_id}"
                )
                return "Lo siento, hubo un problema interno al preparar la siguiente pregunta."

            instruction = "[INSTRUCCIÓN SIGUIENTE]:\n"
            # 1. Generar Insight (si hubo respuesta previa)
            if current_q_id and last_user_message:
                instruction += f"1. Basado en la última respuesta del usuario ('{last_user_message}') a la pregunta '{questionnaire_service.get_question_details(current_q_id).get('text', current_q_id)}', genera un breve insight educativo relevante (1-2 frases) para el sector '{metadata.get('selected_sector', 'N/A')}' / subsector '{metadata.get('selected_subsector', 'N/A')}'. Formatea el insight con '> 📊 *Insight:* ...'.\n"
            else:
                instruction += "1. Omite el insight educativo (es el inicio o no hubo respuesta previa).\n"

            # 2. Formular la Pregunta
            q_text_template = next_q_details.get("text", "")
            q_explanation = next_q_details.get("explanation", "")
            q_type = next_q_details.get("type")

            instruction += f"2. A continuación del insight (o directamente si no hubo), formula la pregunta con ID '{next_q_id}'.\n"
            instruction += f"3. El texto base de la pregunta es: '{q_text_template}'. "
            # Instruir reemplazo de placeholders
            placeholders = {
                "sector": metadata.get("selected_sector"),
                "subsector": metadata.get("selected_subsector"),
            }
            placeholders_to_replace = {
                f"{{{k}}}": v
                for k, v in placeholders.items()
                if v and f"{{{k}}}" in q_text_template
            }
            if placeholders_to_replace:
                instruction += f"Reemplaza los siguientes placeholders en el texto: {placeholders_to_replace}. "
            instruction += "Formatea el texto final de la pregunta con '**PREGUNTA:** {texto_final}'.\n"

            # 4. Añadir Opciones (si aplica)
            options = []
            if q_type == "multiple_choice" or q_type == "yes_no":
                options = next_q_details.get("options", [])
            elif q_type == "conditional_multiple_choice":
                conditions = next_q_details.get("conditions", {})
                sector_key = metadata.get("selected_sector")  # Usar valor ya guardado
                if sector_key and sector_key in conditions:
                    options = conditions[sector_key]
                else:
                    logger.warning(
                        f"No se encontraron opciones condicionales para {next_q_id} con sector '{sector_key}'"
                    )

            if options:
                options_str = ", ".join([f'"{opt}"' for opt in options])
                instruction += f"4. Después del texto de la pregunta, presenta las siguientes opciones NUMERADAS (1., 2., 3., etc.): [{options_str}]. Añade la indicación '(responde solo con el número)'.\n"
            elif q_type == "multiple_open":
                sub_q_labels = [
                    sq.get("label", "")
                    for sq in next_q_details.get("sub_questions", [])
                ]
                instruction += f"4. Indica al usuario que proporcione los siguientes datos (puede listar los labels: {sub_q_labels}).\n"
            elif q_type == "document_upload":
                instruction += "4. Indica al usuario que puede usar el botón de adjuntar archivo.\n"
            else:  # Open, Confirmation
                instruction += (
                    "4. No se requieren opciones especiales para esta pregunta.\n"
                )

            # 5. Añadir Explicación
            if q_explanation:
                instruction += f"5. Finalmente, incluye la explicación de por qué se pregunta: '{q_explanation}'. Formatea con '*¿Por qué preguntamos esto?* 🤔\\n*{q_explanation}*'.\n"
            else:
                instruction += "5. No hay explicación adicional para esta pregunta.\n"

            # 6. Instrucción Final
            instruction += (
                "6. NO hagas ninguna otra pregunta. Espera la respuesta del usuario."
            )

            logger.debug(f"Instrucción LLM para pregunta {next_q_id}: {instruction}")

            # Construir mensajes y llamar al LLM
            messages_to_send = self._build_llm_messages(conversation, instruction)
            llm_response = await self._call_llm_api(
                messages_to_send, max_tokens=500, temperature=0.6
            )  # Menos tokens para preguntas
            metadata["last_llm_response_type"] = "question"

        else:
            # --- Cuestionario Terminado: Construir Instrucción para Propuesta ---
            if not metadata.get("is_complete"):  # Marcar como completo si llegamos aquí
                metadata["is_complete"] = True
                logger.info(f"Marcando conversación {conversation.id} como completa.")

            # Preparar datos recolectados para el prompt
            collected_data_summary = "\n### Datos Recopilados del Usuario:\n"
            for q_id, answer in metadata["collected_data"].items():
                q_details = questionnaire_service.get_question_details(q_id)
                q_text = q_details.get("text", q_id) if q_details else q_id
                collected_data_summary += f"- **{q_text}:** {answer}\n"

            instruction = "[INSTRUCCIÓN SIGUIENTE]:\n"
            instruction += "El cuestionario ha finalizado.\n"
            # Insight final opcional
            if current_q_id and last_user_message:
                instruction += f"1. Basado en la última respuesta ('{last_user_message}'), genera un breve comentario de cierre o agradecimiento.\n"
            else:
                instruction += "1. Omite el comentario de cierre.\n"

            instruction += (
                "2. **Genera la propuesta técnica y económica preliminar COMPLETA.**\n"
            )
            instruction += f"   - Utiliza los siguientes 'Datos Recopilados del Usuario': {collected_data_summary}\n"
            instruction += f"   - Sigue ESTRICTAMENTE la 'Plantilla de Propuesta' proporcionada en el prompt inicial del sistema (entre <plantilla_propuesta>).\n"
            instruction += "   - Aplica tus conocimientos técnicos para proponer soluciones, estimar tamaños/costos (con descargos de responsabilidad) y calcular ROI.\n"
            instruction += "   - **IMPRESCINDIBLE:** Finaliza TODA la respuesta SOLO con la etiqueta `[PROPOSAL_COMPLETE: Propuesta lista para PDF]` y NADA MÁS después."

            logger.debug(f"Instrucción LLM para propuesta: {instruction}")

            # Añadir plantilla al prompt base si no está ya incluida
            system_prompt_with_template = self.master_prompt_template
            if "<plantilla_propuesta>" not in system_prompt_with_template:
                system_prompt_with_template += (
                    "\n\n<plantilla_propuesta>\n"
                    + self.proposal_format_content
                    + "\n</plantilla_propuesta>"
                )

            # Construir mensajes y llamar al LLM (con más tokens)
            # Podríamos enviar solo el system prompt + la instrucción + datos, sin historial previo
            messages_to_send = [
                {"role": "system", "content": system_prompt_with_template},
                {
                    "role": "user",
                    "content": instruction,
                },  # La instrucción contiene los datos
            ]
            llm_response = await self._call_llm_api(
                messages_to_send, max_tokens=3500, temperature=0.5
            )

            # Guardar propuesta en metadata y marcar como lista
            if "[PROPOSAL_COMPLETE:" in llm_response:
                metadata["proposal_text"] = llm_response
                metadata["has_proposal"] = True
                metadata["last_llm_response_type"] = "proposal_generated"
                # Devolver un mensaje indicando que está lista para descargar
                llm_response = "✅ ¡Excelente! Hemos recopilado toda la información necesaria.\n\nHe generado una propuesta preliminar basada en tus respuestas.\n\n**Escribe 'descargar propuesta' o 'PDF' para obtener el documento.**"
            else:
                logger.error(
                    f"La propuesta generada por el LLM NO contiene el marcador final! Respuesta: {llm_response[:200]}..."
                )
                metadata["last_llm_response_type"] = "proposal_error"
                llm_response = "Lo siento, tuve un problema al generar el formato final de la propuesta. Intentaré de nuevo o contacta a soporte. (Error: Marcador final faltante)"

        # Devolver la respuesta generada por el LLM
        return llm_response


# Instancia global para el enfoque híbrido
ai_service = AIService()
