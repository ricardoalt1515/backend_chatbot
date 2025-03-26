# app/services/ai_service.py
import logging
import httpx
from typing import List, Dict, Any
import os

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.main_prompt import get_master_prompt
from app.services import questionnaire_service

logger = logging.getLogger("hydrous")

# Importación condicional de google-generativeai
try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning(
        "google-generativeai no está instalado. El proveedor Gemini no estará disponible."
    )


class AIService:
    """Servicio simplificado para interactuar con LLMs"""

    def __init__(self):
        """Inicialización del servicio AI"""
        # Cargar el prompt maestro
        self.master_prompt = get_master_prompt()

        # Configuración de API
        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_provider = settings.API_PROVIDER
        self.api_url = settings.API_URL

        # Inicializar gemini si esta disponible y seleccionado
        if self.api_provider == "gemini" and GEMINI_AVAILABLE:
            genai.configure(api_key=settings.GEMINI_API_KEY)

    async def handle_conversation(
        self, conversation: Conversation, user_message: str = None
    ) -> str:
        """
        Maneja una conversación y genera una respuesta
        """
        try:
            # Cargar datos del cuestionario
            questionnaire_data = await self._load_questionnaire_data()

            # Actualizar estado del cuestionario si hay un nuevo mensaje
            if user_message:
                conversation.update_questionnaire_state(
                    user_message, questionnaire_data
                )

            # Preparar los mensajes para la API
            messages = self._prepare_messages(
                conversation, user_message, questionnaire_data
            )

            # Verificar el proveedor de API y llamar al metodo correspondiente
            response = ""
            if self.api_provider == "gemini" and GEMINI_AVAILABLE:
                response = await self._call_gemini_api(messages)
            else:
                # para openai o groq
                response = await self._call_llm_api(messages)

            # Detectar si el mensaje contiene una propuesta completa
            if self._contains_proposal_markers(response):
                conversation.metadata["has_proposal"] = True
                conversation.questionnaire_state.is_complete = True

            return response

        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, inténtalo de nuevo."

    def _prepare_messages(
        self,
        conversation: Conversation,
        user_message: str = None,
        questionnaire_data: Dict[str, Any] = None,
    ) -> List[Dict[str, str]]:
        """Prepara los mensajes para la API del LLM con mejor contexto"""
        # Mensaje inicial del sistema con el prompt maestro
        messages = [{"role": "system", "content": self.master_prompt}]

        # Añadir contexto actual a las instrucciones del sistema
        context_summary = conversation.questionnaire_state.get_context_summary()
        if context_summary:
            context_message = {
                "role": "system",
                "content": f"CONTEXTO ACTUAL:\n{context_summary}\n\nUtiliza esta información para personalizar tus respuestas. Si mencionan una ubicación específica, utiliza tu conocimiento interno sobre esa ubicación para proporcionar información relevante sobre estrés hídrico, clima y normativas locales.",
            }
            messages.append(context_message)

        # Añadir información sobre la pregunta actual
        if questionnaire_data:
            current_question = conversation.get_current_question(questionnaire_data)
            if current_question:
                question_info = {
                    "role": "system",
                    "content": f"La pregunta actual es: {current_question['text']}\n\nEsta pregunta corresponde a la sección {conversation.questionnaire_state.sector if conversation.questionnaire_state.sector else 'inicial'} del cuestionario.",
                }
                messages.append(question_info)

        # Añadir mensajes anteriores de la conversación (limitar para evitar exceder tokens)
        for msg in conversation.messages[-10:]:
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

    async def _load_questionnaire_data(self) -> Dict[str, Any]:
        """Carga los datos del cuestionario"""
        try:
            # Cargar desde archivo JSON en app/prompts/questionnaire_complete.json
            import json
            import os

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

    async def _call_gemini_api(self, messages: List[Dict[str, str]]) -> str:
        """Llama a la API de Gemini"""
        try:
            if not GEMINI_AVAILABLE:
                return "Lo siento, Gemini no está disponible. Por favor, configura otro proveedor."

            # Configurar el modelo
            model = genai.GenerativeModel(settings.GEMINI_MODEL)

            # Convertir mensajes al formato que espera Gemini
            gemini_messages = []
            for msg in messages:
                role = msg["role"]
                content = msg["content"]

                if role == "system":
                    # Gemini no tiene un rol de "system" explícito, lo convertimos a "user"
                    # pero marcado como instrucción del sistema
                    gemini_messages.append(
                        {"role": "user", "parts": [f"[SYSTEM INSTRUCTION] {content}"]}
                    )
                elif role == "user":
                    gemini_messages.append({"role": "user", "parts": [content]})
                elif role == "assistant":
                    gemini_messages.append({"role": "model", "parts": [content]})

            # Crear una conversación con Gemini
            chat = model.start_chat(
                history=gemini_messages[:-1] if gemini_messages else []
            )

            # Obtener la última pregunta del usuario
            last_message = (
                gemini_messages[-1]
                if gemini_messages
                else {"role": "user", "parts": ["Hola"]}
            )

            # Generar respuesta
            response = chat.send_message(last_message["parts"][0])

            # Extraer el texto de la respuesta
            return response.text

        except Exception as e:
            logger.error(f"Error en _call_gemini_api: {str(e)}")
            return f"Lo siento, ha ocurrido un error al comunicarse con Gemini: {str(e)}. Por favor, inténtalo de nuevo."

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
