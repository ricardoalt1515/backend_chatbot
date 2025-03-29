import logging
import httpx
from typing import List, Dict, Any

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.main_prompt import get_master_prompt
from app.services import questionnaire_service

logger = logging.getLogger("hydrous")


class AIService:
    """Servicio actualizado para interactuar con la API Responses de OpenAI"""

    def __init__(self):
        """Inicialización del servicio AI con la API Responses"""
        self.master_prompt = get_master_prompt()
        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_RESPONSES_URL  # Nueva URL de API Responses

    async def handle_conversation(
        self, conversation: Conversation, user_message: str = None
    ) -> str:
        """
        Maneja una conversación con la API de Responses de OpenAI
        """
        try:
            questionnaire_data = await self._load_questionnaire_data()

            if user_message:
                conversation.update_questionnaire_state(
                    user_message, questionnaire_data
                )

            response_id = conversation.metadata.get(
                "response_id"
            )  # Recuperar contexto previo
            messages = self._prepare_messages(
                conversation, user_message, questionnaire_data
            )

            response, new_response_id = await self._call_llm_api(messages, response_id)

            # Guardar el nuevo response_id para mantener el contexto
            conversation.metadata["response_id"] = new_response_id

            return response
        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar tu consulta."

    def _prepare_messages(
        self,
        conversation: Conversation,
        user_message: str = None,
        questionnaire_data: Dict[str, Any] = None,
    ) -> List[Dict[str, str]]:
        """Prepara los mensajes para la API de Responses"""
        messages = [{"role": "system", "content": self.master_prompt}]

        context_summary = conversation.questionnaire_state.get_context_summary()
        if context_summary:
            messages.append(
                {"role": "system", "content": f"CONTEXTO: {context_summary}"}
            )

        if user_message:
            messages.append({"role": "user", "content": user_message})

        return messages

    async def _call_llm_api(
        self, messages: List[Dict[str, str]], previous_response_id: str = None
    ) -> (str, str):
        """Llama a la API de Responses de OpenAI"""
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }

                payload = {
                    "model": self.model,
                    "messages": messages,
                    "store": True,  # Guardar el contexto en OpenAI
                }

                if previous_response_id:
                    payload["previous_response_id"] = previous_response_id

                response = await client.post(
                    self.api_url, json=payload, headers=headers, timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()
                    return (
                        data["message"]["content"],
                        data["id"],
                    )  # Retorna la respuesta y el nuevo response_id
                else:
                    logger.error(
                        f"Error en API Responses: {response.status_code} - {response.text}"
                    )
                    return "Error con el servicio de IA.", None
        except Exception as e:
            logger.error(f"Error en _call_llm_api: {str(e)}")
            return "Error de comunicación con la IA.", None


# Instancia global
ai_service = AIService()
