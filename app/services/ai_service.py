# app/services/ai_service.py
import logging
import httpx
from typing import List, Dict, Any

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.main_prompt import get_master_prompt
from app.services.storage_service import storage_service
from app.services import questionnaire_service

logger = logging.getLogger("hydrous")


class AIService:
    """Servicio simplificado para interactuar con LLMs"""

    def __init__(self):
        """Inicialización del servicio AI"""
        # Cargar el prompt maestro
        self.master_prompt = get_master_prompt()

        # Configuración de API
        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_URL

    async def handle_conversation(
        self, conversation: Conversation, user_message: str = None
    ) -> str:
        """
        Maneja una conversación y genera una respuesta
        """
        try:
            # Cargar datos del cuestionario
            questionnaire_data = await self._load_questionnaire_data()

            # Actualizar estadod el cuestionario si hay un nuevo mensaje
            if user_message:
                conversation.update_questionnaire_state(
                    user_message, questionnaire_data
                )

            # Preparar los mensajes para la API
            messages = self._prepare_messages(
                conversation, user_message, questionnaire_data
            )

            # Llamar a la API del LLM
            response = await self._call_llm_api(messages)

            # Detectar si el mensaje contiene una propuesta completa
            if self._contains_proposal_markers(response):
                conversation.metadata["has_proposal"] = True
                conversation.questionnaire_state.complete_questionnaire()

            return response

        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, inténtalo de nuevo."

    async def _load_questionnaire_data(self) -> Dict[str, Any]:
        """Carga los datos del cuestionario"""
        # Implementación simplificada - en un entorno real podrías cargar desde una base de datos
        try:
            # Cargar desde archivo JSON en app/prompts/questionnaire_complete.json
            import json
            import os

            questionnaire_path = os.path.join(
                os.path.dirname(__file__), "../prompts/questionnaire_complete.json"
            )

            with open(questionnaire_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error al cargar datos del cuestionario: {str(e)}")
            return {}

    def _prepare_messages(
        self,
        conversation: Conversation,
        user_message: str = None,
        questionnaire_data: Dict[str, Any] = None,
    ) -> List[Dict[str, str]]:
        """Prepara los mensajes para la API del LLM"""
        # Mensaje inicial del sistema con el prompt maestro
        messages = [{"role": "system", "content": self.master_prompt}]

        # Añadir contexto de cuestionario al prompt del sistema si está disponible
        if questionnaire_data:
            try:
                current_question = conversation.get_current_question(questionnaire_data)
                if current_question:
                    context_message = {
                        "role": "system",
                        "content": f"La pregunta actual es: {current_question['text']}",
                    }
                    messages.append(context_message)
            except Exception as e:
                logger.warning(f"Error al obtener pregunta actual: {str(e)}")

        # Añadir mensajes anteriores de la conversación (limitar para evitar exceder tokens)
        for msg in conversation.messages[-15:]:
            if msg.role != "system":  # No duplicar mensajes del sistema
                messages.append({"role": msg.role, "content": msg.content})

        # Si hay un nuevo mensaje y no es igual al último, añadirlo
        if user_message and (
            not messages
            or messages[-1]["role"] != "user"
            or messages[-1]["content"] != user_message
        ):
            messages.append({"role": "user", "content": user_message})

        return messages

    async def _call_llm_api(self, messages: List[Dict[str, str]]) -> str:
        """Llama a la API del LLM"""
        try:
            # Llamar a la API usando httpx
            async with httpx.AsyncClient() as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }

                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 1500,
                }

                response = await client.post(
                    self.api_url, json=payload, headers=headers, timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    return content
                else:
                    logger.error(
                        f"Error en API LLM: {response.status_code} - {response.text}"
                    )
                    return "Lo siento, ha habido un problema con el servicio. Por favor, inténtalo de nuevo más tarde."

        except Exception as e:
            logger.error(f"Error en _call_llm_api: {str(e)}")
            return "Lo siento, ha ocurrido un error al comunicarse con el servicio. Por favor, inténtalo de nuevo."

    def _contains_proposal_markers(self, text: str) -> bool:
        """Detecta si el texto contiene marcadores de una propuesta completa"""
        markers = [
            "Propuesta",
            "Antecedentes del Proyecto",
            "Objetivo del Proyecto",
            "Parámetros de Diseño",
            "Proceso de Tratamiento",
        ]

        marker_count = sum(1 for marker in markers if marker in text)
        return marker_count >= 3


# Instancia global
ai_service = AIService()
