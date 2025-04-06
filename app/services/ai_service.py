# app/services/ai_service.py
import logging
import httpx
import os
import json
from typing import List, Dict, Any, Optional

from app.config import settings
from app.models.conversation import Conversation

# Importar el nuevo prompt
from app.prompts.main_prompt_llm_driven import get_llm_driven_master_prompt

# Ya no necesitamos QuestionnaireService aquí

logger = logging.getLogger("hydrous")


class AIServiceLLMDriven:

    def __init__(self):
        # Cargar configuración API (igual que antes)
        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_URL
        if not self.api_key:
            logger.critical("¡Clave API de IA no configurada!")
        if not self.api_url:
            logger.critical("¡URL de API de IA no configurada!")
        # Nota: El prompt ahora se genera dinámicamente en _prepare_messages

    async def _call_llm_api(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1500,
        temperature: float = 0.6,
    ) -> str:
        """Llama a la API del LLM (Sin cambios respecto a versiones anteriores)."""
        # ... (pegar aquí la función _call_llm_api completa de la versión híbrida) ...
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
                # Añadir manejo robusto por si 'choices' no está o está vacío
                choices = data.get("choices")
                if not choices:
                    logger.warning(f"Respuesta LLM no contiene 'choices': {data}")
                    return "(El asistente no proporcionó una respuesta válida)"
                message_data = choices[0].get("message", {})
                content = message_data.get("content", "")
                # -------
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

    def _prepare_messages(self, conversation: Conversation) -> List[Dict[str, str]]:
        """Prepara los mensajes para la API, incluyendo el prompt dinámico."""

        # 1. Generar el prompt maestro con el estado actual y el cuestionario
        system_prompt = get_llm_driven_master_prompt(conversation.metadata)

        messages = [{"role": "system", "content": system_prompt}]

        # 2. Añadir historial de conversación (últimos N mensajes)
        MAX_HISTORY_MSGS = 15  # Ajustar
        start_index = max(0, len(conversation.messages) - MAX_HISTORY_MSGS)
        for msg in conversation.messages[start_index:]:
            if msg.role != "system":  # Evitar duplicar system prompts
                messages.append({"role": msg.role, "content": msg.content})

        logger.debug(
            f"Mensajes preparados para LLM (Total: {len(messages)}). Último user: {messages[-1]['content'] if messages[-1]['role']=='user' else 'N/A'}"
        )
        return messages

    async def handle_conversation(self, conversation: Conversation) -> str:
        """
        Prepara los mensajes con el prompt dinámico y obtiene la respuesta del LLM.
        Actualiza el estado mínimo en metadata basado en la respuesta.
        """
        if not conversation or not conversation.messages:
            logger.error("handle_conversation llamada sin conversación o mensajes.")
            return "Error interno: No se pudo procesar la conversación."

        # 1. Preparar mensajes (incluye prompt dinámico con estado)
        messages = self._prepare_messages(conversation)

        # 2. Llamar al LLM
        llm_response = await self._call_llm_api(messages)

        # 3. Actualizar estado MÍNIMO en metadata (basado en lo que el LLM dijo)
        #    Esto es menos preciso que el enfoque anterior, confiamos en el LLM.
        try:
            # Intentar extraer la última pregunta formulada por el LLM (simplificado)
            lines = llm_response.split("\n")
            last_q_summary = "Desconocida"
            for line in reversed(lines):
                if line.strip().startswith("**PREGUNTA:**"):
                    last_q_summary = (
                        line.strip().replace("**PREGUNTA:**", "").strip()[:100]
                    )  # Resumen corto
                    break
            conversation.metadata["current_question_asked_summary"] = last_q_summary
            logger.info(
                f"Metadata[current_question_asked_summary] actualizada a: '{last_q_summary}'"
            )

            # Actualizar sector/subsector si el LLM los mencionó en su respuesta (más frágil)
            # O mejor, hacerlo en chat.py después de recibir la respuesta del usuario
            # Por ahora, solo actualizamos el resumen de la pregunta.

            # Marcar como completo si la respuesta contiene el marcador final
            if "[PROPOSAL_COMPLETE:" in llm_response:
                conversation.metadata["is_complete"] = True
                conversation.metadata["has_proposal"] = True
                conversation.metadata["proposal_text"] = (
                    llm_response  # Guardar texto completo
                )
                logger.info(
                    f"Propuesta detectada y guardada en metadata para {conversation.id}"
                )
                # Devolver un mensaje indicando que está lista (el LLM debería haber terminado con el marcador)
                # Si queremos un mensaje más amigable, podríamos quitar el marcador aquí y poner texto fijo
                # llm_response = "¡Propuesta generada! Puedes pedir el PDF."

        except Exception as e:
            logger.error(
                f"Error actualizando metadata después de respuesta LLM: {e}",
                exc_info=True,
            )

        return llm_response


# Instancia global
ai_service = AIServiceLLMDriven()  # Nombre de instancia genérico
