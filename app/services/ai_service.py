# app/services/ai_service.py
import logging
import httpx
import os
import json  # Importar json
from typing import List, Dict, Any, Optional  # Asegurarse que Optional esté importado

from app.config import settings
from app.models.conversation import Conversation

# Importar el prompt LLM-Driven (ajusta el nombre si usaste V4)
from app.prompts.main_prompt_llm_driven import (
    get_llm_driven_master_prompt,
)


# Importar QuestionnaireService SOLO para IDs iniciales/texto de preguntas en metadata
from app.services.questionnaire_service import questionnaire_service

logger = logging.getLogger("hydrous")


class AIServiceLLMDriven:

    def __init__(self):
        # Cargar configuración API
        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_URL
        if not self.api_key:
            logger.critical("¡Clave API de IA no configurada!")
        if not self.api_url:
            logger.critical("¡URL de API de IA no configurada!")
        # El prompt maestro ahora se genera dinámicamente en _prepare_messages

    async def _call_llm_api(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1500,
        temperature: float = 0.6,
    ) -> str:
        """Llama a la API del LLM con logging y manejo de errores detallado."""
        if not self.api_key or not self.api_url:
            error_msg = "Error de configuración: Clave API o URL no proporcionada."
            logger.error(error_msg)
            # Devolver mensaje de error que se mostrará al usuario
            return "Error de Configuración Interna [AIC01]."

        response_text = ""  # Para guardar el texto de respuesta en caso de error JSON
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

                logger.info(
                    f"DBG_AI_CALL: Iniciando llamada a API LLM. URL: {self.api_url}, Model: {self.model}, #Msgs: {len(messages)}"
                )
                # Loggear parte del payload para depuración (ej. último mensaje)
                if messages:
                    logger.debug(f"DBG_AI_CALL: Último mensaje enviado: {messages[-1]}")

                response = await client.post(
                    self.api_url, json=payload, headers=headers, timeout=90.0
                )
                response_text = (
                    response.text
                )  # Guardar texto crudo para posible error JSON
                logger.info(
                    f"DBG_AI_CALL: Llamada a API completada. Status: {response.status_code}"
                )

                response.raise_for_status()  # Lanza excepción en errores HTTP 4xx/5xx

                logger.debug("DBG_AI_CALL: Procesando respuesta JSON...")
                data = response.json()  # Puede lanzar JSONDecodeError
                logger.debug(
                    f"DBG_AI_CALL: JSON recibido OK (primeros 500 chars): {str(data)[:500]}"
                )

                choices = data.get("choices")
                if not choices:
                    logger.warning(
                        f"DBG_AI_CALL: Respuesta LLM sin 'choices'. JSON: {data}"
                    )
                    return "(Respuesta inválida del asistente [AIC02])"  # Mensaje más específico

                message_data = choices[0].get("message", {})
                content = message_data.get("content", "")

                if not content:
                    logger.warning(
                        "DBG_AI_CALL: Respuesta del LLM con contenido vacío."
                    )
                    # Podríamos devolver un mensaje específico o dejar que el flujo continúe
                    # y chat.py maneje la respuesta vacía si es necesario.
                    # Devolver un placeholder podría ser más claro que un string vacío.
                    return "(El asistente no proporcionó texto en la respuesta)"

                logger.info(
                    f"DBG_AI_CALL: Contenido LLM extraído exitosamente (longitud: {len(content)})."
                )
                return content.strip()

        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            logger.error(
                f"DBG_AI_CALL: Error HTTP {e.response.status_code} en API LLM: {error_body}",
                exc_info=True,
            )
            # Devolver mensaje de error claro al usuario
            user_error_msg = (
                f"Error de comunicación con la IA ({e.response.status_code})."
            )
            # Incluir más detalles si es un error común (ej. rate limit, auth)
            if e.response.status_code == 429:
                user_error_msg += " Límite de solicitudes excedido. Espera un momento."
            elif e.response.status_code in [401, 403]:
                user_error_msg += " Problema de autenticación con la API."
            return user_error_msg
        except httpx.RequestError as e:
            logger.error(
                f"DBG_AI_CALL: Error de red llamando a API LLM: {e}", exc_info=True
            )
            return f"Error de red al contactar la IA. Verifica tu conexión."
        except json.JSONDecodeError as e:
            logger.error(
                f"DBG_AI_CALL: Error decodificando JSON de API LLM: {e}", exc_info=True
            )
            logger.error(
                f"DBG_AI_CALL: Cuerpo de respuesta (texto crudo): {response_text}"
            )
            return "Error interno al procesar la respuesta de la IA [AIC03]."
        except Exception as e:
            logger.error(
                f"DBG_AI_CALL: Error inesperado en _call_llm_api: {str(e)}",
                exc_info=True,
            )
            return (
                "Lo siento, ocurrió un error inesperado en el servicio de IA [AIC04]."
            )

    def _prepare_messages(self, conversation: Conversation) -> List[Dict[str, str]]:
        """Prepara los mensajes para la API, incluyendo el prompt dinámico."""
        logger.debug("DBG_AI_PREP: Iniciando preparación de mensajes...")
        try:
            # Generar el prompt maestro con el estado actual y el cuestionario
            # Usar metadata directamente, asegurarse que no sea None
            current_metadata = conversation.metadata if conversation.metadata else {}
            system_prompt = get_llm_driven_master_prompt(current_metadata)

            if "[ERROR" in system_prompt:
                logger.error(
                    f"Error detectado en system_prompt al cargar plantillas/cuestionario: {system_prompt}"
                )
                # Es crítico, lanzar excepción para detener el flujo
                raise ValueError(
                    "Fallo al generar system_prompt debido a error en carga de archivos."
                )

            messages = [{"role": "system", "content": system_prompt}]

            # Añadir historial de conversación (si existe)
            if conversation.messages:
                MAX_HISTORY_MSGS = 15  # Ajustar según necesidad y límites de tokens
                start_index = max(0, len(conversation.messages) - MAX_HISTORY_MSGS)
                for msg in conversation.messages[start_index:]:
                    # Asegurarse que msg es un objeto con atributos role y content
                    # (Si viene de BD, podría ser un dict)
                    role = getattr(msg, "role", None)
                    content = getattr(msg, "content", None)
                    if role and content and role != "system":
                        messages.append({"role": role, "content": content})
                    else:
                        logger.warning(
                            f"Mensaje inválido o de sistema en historial omitido: {msg}"
                        )

                logger.debug(
                    f"DBG_AI_PREP: Mensajes preparados (Total: {len(messages)}). Historial añadido."
                )
            else:
                logger.debug(
                    "DBG_AI_PREP: Mensajes preparados (Total: 1). Sin historial previo."
                )

            return messages
        except Exception as e:
            logger.error(f"Error fatal en _prepare_messages: {e}", exc_info=True)
            # Lanzar excepción para que handle_conversation la capture
            raise ValueError(f"Fallo al preparar mensajes: {e}")

    async def handle_conversation(self, conversation: Conversation) -> str:
        """
        Prepara los mensajes y obtiene la respuesta del LLM.
        Actualiza el estado mínimo en metadata basado en la respuesta del LLM.
        """
        logger.info(
            f"DBG_AI_HANDLE: Iniciando handle_conversation para conv {conversation.id if conversation else 'N/A'}"
        )
        if not conversation:
            # ... (manejo error conversación None) ...
            pass
        if not isinstance(conversation.metadata, dict):
            # ... (manejo error metadata inválida) ...
            pass

        llm_response = "Error inesperado en handle_conversation [AIH03]."
        try:
            # 1. Preparar mensajes
            logger.debug("DBG_AI_HANDLE: Llamando a _prepare_messages...")
            messages = self._prepare_messages(conversation)
            logger.info(
                f"DBG_AI_HANDLE: Mensajes preparados OK (Total: {len(messages)})."
            )

            # 2. Determinar si esperamos la propuesta final
            # (Hacemos esto ANTES de llamar a la IA para saber qué esperar)
            expecting_proposal = conversation.metadata.get("is_complete", False)
            logger.debug(
                f"DBG_AI_HANDLE: ¿Esperando propuesta final? {expecting_proposal}"
            )

            # 3. Llamar al LLM
            logger.debug("DBG_AI_HANDLE: Llamando a _call_llm_api...")
            # Ajustar tokens si esperamos propuesta
            max_tokens_call = 3500 if expecting_proposal else 1500
            temperature_call = 0.5 if expecting_proposal else 0.6
            llm_response = await self._call_llm_api(
                messages, max_tokens=max_tokens_call, temperature=temperature_call
            )
            logger.info(
                f"DBG_AI_HANDLE: Respuesta LLM recibida (primeros 50 chars): '{llm_response[:50]}'"
            )

            # 4. Procesar respuesta y actualizar metadata
            possible_error_prefixes = (
                "Error",
                "Lo siento",
                "(Respuesta inválida",
                "(El asistente no",
            )
            if not llm_response.startswith(possible_error_prefixes):
                logger.debug(
                    f"DBG_AI_HANDLE: Actualizando metadata para {conversation.id}..."
                )
                try:
                    is_proposal_marker_present = "[PROPOSAL_COMPLETE:" in llm_response

                    # Si esperábamos la propuesta final:
                    if expecting_proposal:
                        if is_proposal_marker_present:
                            # ¡Éxito! LLM generó propuesta y marcador
                            proposal_clean_text = llm_response.split(
                                "[PROPOSAL_COMPLETE:"
                            )[0].strip()
                            conversation.metadata["proposal_text"] = proposal_clean_text
                            conversation.metadata["has_proposal"] = True
                            # is_complete ya debería ser True
                            logger.info(
                                f"Propuesta con marcador detectada y guardada para {conversation.id}"
                            )
                            # Devolver mensaje fijo para pedir descarga
                            llm_response_to_user = "¡Excelente! Hemos completado el cuestionario. Estoy generando tu propuesta personalizada en formato PDF, espera un momento..."
                        else:
                            # ¡Fallo! LLM generó algo pero olvidó el marcador
                            logger.error(
                                f"¡FALLO! LLM generó propuesta para {conversation.id} pero olvidó el marcador final. Respuesta: {llm_response[:200]}..."
                            )
                            conversation.metadata["has_proposal"] = (
                                False  # Marcar como no lista
                            )
                            # Devolver mensaje de error
                            llm_response_to_user = "Lo siento, hubo un problema al generar el formato final de la propuesta. Intenta de nuevo o contacta a soporte [AIH07]."
                    else:
                        # No esperábamos propuesta, es una pregunta normal
                        # Extraer resumen de la pregunta hecha
                        lines = llm_response.split("\n")
                        last_q_summary = conversation.metadata.get(
                            "current_question_asked_summary", "Desconocida"
                        )
                        question_found_in_response = False
                        for line in lines:
                            if line.strip().startswith("**PREGUNTA:**"):
                                last_q_summary = (
                                    line.strip()
                                    .replace("**PREGUNTA:**", "")
                                    .strip()[:100]
                                )
                                question_found_in_response = True
                                # Actualizar ID actual si es el inicio
                                if (
                                    conversation.metadata.get("current_question_id")
                                    is None
                                ):
                                    initial_q_ids = [
                                        q["id"]
                                        for q in questionnaire_service.structure.get(
                                            "initial_questions", []
                                        )
                                        if "id" in q
                                    ]
                                    if initial_q_ids:
                                        conversation.metadata["current_question_id"] = (
                                            initial_q_ids[0]
                                        )
                                break
                        if question_found_in_response:
                            conversation.metadata["current_question_asked_summary"] = (
                                last_q_summary
                            )
                            logger.info(
                                f"Metadata[current_question_asked_summary] actualizada a: '{last_q_summary}'"
                            )
                        # Devolver la respuesta normal del LLM (pregunta + insight)
                        llm_response_to_user = llm_response

                    logger.debug(
                        f"DBG_AI_HANDLE: Metadata actualizada OK para {conversation.id}."
                    )

                except Exception as meta_err:
                    logger.error(
                        f"Error actualizando metadata para {conversation.id}: {meta_err}",
                        exc_info=True,
                    )
                    # Si falla la actualización, devolver la respuesta original del LLM por si acaso
                    llm_response_to_user = llm_response
            else:
                # La respuesta del LLM ya era un mensaje de error
                logger.warning(
                    f"DBG_AI_HANDLE: Respuesta de LLM fue un error, no se actualiza metadata: '{llm_response}'"
                )
                llm_response_to_user = llm_response  # Pasar el error al usuario

        # ... (Manejo de excepciones de preparación/inesperado como antes) ...
        except ValueError as e:
            logger.error(
                f"DBG_AI_HANDLE: Error preparando mensajes: {e}", exc_info=True
            )
            llm_response_to_user = f"Error interno preparando la solicitud [AIH05]."
        except Exception as e:
            logger.error(
                f"DBG_AI_HANDLE: Error inesperado en handle_conversation: {e}",
                exc_info=True,
            )
            llm_response_to_user = (
                "Lo siento, ocurrió un error general al procesar tu solicitud [AIH06]."
            )

        logger.info(
            f"DBG_AI_HANDLE: Finalizando handle_conversation para {conversation.id}. Respuesta a devolver (primeros 50): '{llm_response_to_user[:50]}'"
        )
        # Devolver el mensaje final (sea pregunta, propuesta lista, o error)
        return llm_response_to_user

    async def generate_proposal_text_only(self, conversation: Conversation) -> str:
        """Llama al LLM específicamente para generar solo el texto de la propuesta."""
        logger.info(
            f"DBG_AI_PROP: Iniciando generación de SOLO TEXTO de propuesta para {conversation.id}"
        )
        if not conversation or not conversation.metadata:
            logger.error(
                "generate_proposal_text_only llamada sin conversación/metadata válida."
            )
            return "Error: Datos de conversación inválidos para generar propuesta."
        if not conversation.metadata.get("collected_data"):
            logger.error(
                f"No hay datos recolectados en metadata para generar propuesta {conversation.id}"
            )
            return (
                "Error: No se encontraron datos suficientes para generar la propuesta."
            )

        # Preparar datos recolectados para el prompt
        collected_data = conversation.metadata.get("collected_data", {})
        collected_data_summary = "\n### Datos Recopilados del Usuario:\n"
        for q_id, answer in collected_data.items():
            # Usar una etiqueta simple o ID
            q_details = questionnaire_service.get_question_details(q_id)
            q_text = q_details.get("text", q_id) if q_details else q_id
            q_text = re.sub(r"{.*?}", "", q_text).strip()  # Limpiar placeholders
            collected_data_summary += f"- **{q_text}:** {answer}\n"

        # Cargar prompt base (sin marcador final) y plantilla de propuesta
        # Usar una versión del prompt que NO pida el marcador [PROPOSAL_COMPLETE]
        # Podríamos tener una función get_proposal_generation_prompt()
        system_prompt_base = get_llm_driven_master_prompt(
            conversation.metadata
        )  # Usamos el prompt actual por ahora
        # QUITAR la instrucción del marcador final del prompt base si es posible,
        # o instruir explícitamente que NO lo añada.

        # Construir instrucción específica para generar SOLO texto
        instruction = "[INSTRUCCIÓN MUY IMPORTANTE]:\n"
        instruction += "1. Tu ÚNICA tarea es generar el texto completo de la propuesta técnica y económica.\n"
        instruction += f"2. Utiliza los siguientes 'Datos Recopilados del Usuario': {collected_data_summary}\n"
        instruction += f"3. Sigue ESTRICTAMENTE la 'Plantilla de Propuesta' proporcionada en el prompt del sistema (entre <plantilla_propuesta>).\n"
        instruction += f"4. Incluye TODAS las secciones requeridas por la plantilla (Intro, Antecedentes, ..., ROI, Q&A).\n"
        instruction += "5. Rellena la plantilla usando los datos recopilados. Si faltan datos, usa placeholders claros como '[Dato no proporcionado]' o rangos típicos si los conoces.\n"
        instruction += "6. **NO AÑADAS NINGÚN MARCADOR como [PROPOSAL_COMPLETE] al final.** Solo genera el texto de la propuesta."

        logger.debug(
            f"Instrucción LLM para generar SOLO texto propuesta: {instruction}"
        )

        # Usar prompt base V4/V5 pero SOBRESCRIBIR la instrucción final
        # Es crucial que el system_prompt aquí NO tenga la instrucción original que pide el marcador.
        # Idealmente, refactorizar el prompt para separar reglas base de la instrucción final.

        # Solución temporal: Usar el prompt base pero asegurar que la instrucción final sea la de arriba.
        messages = [
            {
                "role": "system",
                "content": system_prompt_base.split("**INSTRUCCIÓN:**")[0],
            },  # Tomar solo la parte de reglas/plantilla
            {
                "role": "user",
                "content": instruction,
            },  # Usar nuestra instrucción específica
        ]

        # Llamar al LLM con tokens suficientes para la propuesta
        proposal_text = await self._call_llm_api(
            messages, max_tokens=3500, temperature=0.5
        )

        # Verificar si aún así añadió el marcador y quitarlo si es necesario
        if "[PROPOSAL_COMPLETE:" in proposal_text:
            logger.warning(
                "LLM añadió el marcador aunque se le pidió que no lo hiciera. Eliminándolo."
            )
            proposal_text = proposal_text.split("[PROPOSAL_COMPLETE:")[0].strip()

        logger.info(
            f"Texto de propuesta (solo texto) generado para {conversation.id} (Longitud: {len(proposal_text)})"
        )
        # Devolver solo el texto limpio
        return proposal_text


# Instancia global
# Asegúrate de que el nombre de la clase aquí coincida con el usado en el import de chat.py
# Si chat.py importa 'ai_service', la instancia debe llamarse así.
ai_service = AIServiceLLMDriven()
