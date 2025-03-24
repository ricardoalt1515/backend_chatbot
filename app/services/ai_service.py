import logging
import httpx
from typing import List, Dict, Any, Optional
import re

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.master_prompt import get_master_prompt

logger = logging.getLogger("hydrous")


class SimpleAIService:
    """Servicio simplificado para interactuar con API de LLM"""

    def __init__(self):
        """Inicialización del servicio AI"""
        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_URL
        self.master_prompt = get_master_prompt()

    async def handle_conversation(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Maneja una nueva entrada del usuario y genera una respuesta

        Args:
            conversation: Conversación actual
            user_message: Mensaje del usuario

        Returns:
            str: Respuesta generada por el LLM
        """
        try:
            # Preparar mensajes para la API
            messages = self._prepare_messages(conversation, user_message)

            # Generar respuesta
            response = await self._generate_response(messages)

            # Detectar si la respuesta contiene una propuesta completa
            if self._contains_proposal(response):
                conversation.metadata["has_proposal"] = True

            return response

        except Exception as e:
            logger.error(f"Error al manejar conversación: {str(e)}")
            return "Lo siento, ocurrió un error al procesar tu consulta. Por favor, inténtalo nuevamente."

    def _prepare_messages(
        self, conversation: Conversation, user_message: str
    ) -> List[Dict[str, str]]:
        """Prepara los mensajes para la API del LLM"""
        # Mensaje del sistema con el prompt maestro
        messages = [{"role": "system", "content": self.master_prompt}]

        # Añadir historial de mensajes (limitado para evitar exceder tokens)
        for msg in conversation.messages[-10:]:
            if msg.role != "system":  # No duplicar mensajes del sistema
                messages.append({"role": msg.role, "content": msg.content})

        # Si el último mensaje no es del usuario, añadir el mensaje actual
        if not messages or messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": user_message})

        return messages

    async def _generate_response(self, messages: List[Dict[str, str]]) -> str:
        """Genera una respuesta usando la API del LLM"""
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
                    "max_tokens": 1500,
                }

                response = await client.post(
                    self.api_url, json=payload, headers=headers, timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    logger.error(f"Error API: {response.status_code} - {response.text}")
                    return "Lo siento, ocurrió un problema con el servicio. Por favor, intenta nuevamente más tarde."

        except Exception as e:
            logger.error(f"Error al generar respuesta: {str(e)}")
            return "Lo siento, no puedo procesar tu solicitud en este momento."

    def _contains_proposal(self, response: str) -> bool:
        """Detecta si la respuesta contiene una propuesta completa"""
        proposal_markers = [
            "Propuesta",
            "Antecedentes del Proyecto",
            "Objetivo del Proyecto",
            "Proceso de Tratamiento",
            "Costos Estimados",
        ]

        marker_count = sum(1 for marker in proposal_markers if marker in response)
        return marker_count >= 3


# Instancia global
ai_service = SimpleAIService()
