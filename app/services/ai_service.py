# app/services/ai_service.py
import logging
import httpx
from typing import List, Dict, Any
import json

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.main_prompt import get_master_prompt

logger = logging.getLogger("hydrous")


class AIService:
    """Servicio simplificado para interactuar con LLMs"""

    def __init__(self):
        # Cargar el prompt maestro
        self.master_prompt = get_master_prompt()

        # Configuración de API
        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_URL

    async def handle_conversation(
        self, conversation: Conversation, user_message: str = None
    ) -> str:
        """Maneja una conversación y genera una respuesta"""
        try:
            # Preparar los mensajes para la API
            messages = self._prepare_messages(conversation, user_message)

            # Llamar a la API del LLM
            response = await self._call_llm_api(messages)

            # Detectar si contiene una propuesta completa para PDF
            if "[PROPOSAL_COMPLETE:" in response:
                conversation.metadata["has_proposal"] = True

            return response
        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, inténtalo de nuevo."

    def _prepare_messages(
        self, conversation: Conversation, user_message: str = None
    ) -> List[Dict[str, str]]:
        """Prepara los mensajes para la API del LLM"""
        # Mensaje inicial del sistema con el prompt maestro
        messages = [{"role": "system", "content": self.master_prompt}]

        # Añadir mensajes anteriores de la conversación (excepto los de sistema)
        for msg in conversation.messages:
            if msg.role != "system":
                messages.append({"role": msg.role, "content": msg.content})

        # Si hay un nuevo mensaje del usuario, añadirlo
        if user_message:
            messages.append({"role": "user", "content": user_message})

        return messages

    async def _call_llm_api(self, messages: List[Dict[str, str]]) -> str:
        """Llama a la API del LLM"""
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }

                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 3000,
                }

                response = await client.post(
                    self.api_url, json=payload, headers=headers, timeout=60.0
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


# Instancia global
ai_service = AIService()
