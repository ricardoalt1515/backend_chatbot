import logging
import os
from openai import OpenAI
from typing import List, Dict, Any

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.main_prompt import get_master_prompt
from app.services import questionnaire_service

logger = logging.getLogger("hydrous")


class AIService:
    """Servicio simplificado para interactuar con LLMs usando API de Responses"""

    def __init__(self):
        """Inicialización del servicio AI"""
        self.client = OpenAI(api_key=settings.API_KEY)  # Nuevo cliente de OpenAI
        self.model = settings.MODEL  # Por ejemplo, "gpt-4o"
        self.master_prompt = get_master_prompt()

    async def _load_questionnaire_data(self):
        """Carga los datos del cuestionario desde JSON"""
        try:
            questionnaire_path = os.path.join(
                os.path.dirname(__file__), "../prompts/questionnaire_complete.json"
            )

            if os.path.exists(questionnaire_path):
                with open(questionnaire_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                logger.warning(
                    f"No se encontró el archivo de cuestionario en {questionnaire_path}"
                )
                return {}

        except Exception as e:
            logger.error(f"Error al cargar datos del cuestionario: {str(e)}")
            return {}

    async def handle_conversation(
        self, conversation: Conversation, user_message: str = None
    ) -> str:
        """Maneja la conversación y genera una respuesta con la nueva API de Responses"""

        try:
            # Cargar datos del cuestionario
            questionnaire_data = await self._load_questionnaire_data()

            # Actualizar estado del cuestionario
            if user_message:
                conversation.update_questionnaire_state(
                    user_message, questionnaire_data
                )

            # Preparar el input con el contexto relevante
            messages = self._prepare_messages(
                conversation, user_message, questionnaire_data
            )

            # Llamar a la API de OpenAI usando Responses
            response = await self._call_llm_api(conversation, messages)

            # Detectar si hay una propuesta y agregar enlace de descarga
            if "[PROPOSAL_COMPLETE:" in response or self._contains_proposal_markers(
                response
            ):
                conversation.metadata["has_proposal"] = True
                conversation.questionnaire_state.is_complete = True
                backend_url = settings.BACKEND_URL

                response += f"""
## 📥 Descargar Propuesta en PDF
    Puedes descargar la propuesta aquí:
    **👉 [DESCARGAR PDF]({backend_url}/api/chat/{conversation.id}/download-pdf)**
    """

            return response

        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, hubo un problema procesando tu consulta."

    async def _call_llm_api(
        self, conversation: Conversation, messages: List[Dict[str, str]]
    ) -> str:
        """Llama a la nueva API de OpenAI Responses"""
        try:
            response = self.client.responses.create(
                model=self.model,
                input=messages,
                text={"format": {"type": "text"}},
                reasoning={},
                tools=[],
                temperature=0.7,
                max_output_tokens=1500,
                top_p=1,
                store=True,  # Esto asegura que OpenAI mantenga el contexto
            )

            return response.text.value  # La respuesta generada

        except Exception as e:
            logger.error(f"Error en _call_llm_api: {str(e)}")
            return "Lo siento, hubo un problema con el servicio de IA."


ai_service = AIService()
