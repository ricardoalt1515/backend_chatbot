import logging
import httpx
import json
from typing import List, Dict, Any, Optional

from app.config import settings
from app.models.conversation import Conversation

logger = logging.getLogger("hydrous-backend")


class AIService:
    """Servicio simplificado para interactuar con modelos de IA"""

    def __init__(self):
        """Inicialización del servicio AI"""
        self.provider = settings.AI_PROVIDER

        # Configurar endpoints de API según el proveedor
        if self.provider == "groq":
            if not settings.GROQ_API_KEY:
                logger.warning(
                    "GROQ_API_KEY no configurada. Las llamadas a la API fallarán."
                )
            self.api_key = settings.GROQ_API_KEY
            self.model = settings.GROQ_MODEL
            self.api_url = "https://api.groq.com/openai/v1/chat/completions"

        elif self.provider == "openai":
            if not settings.OPENAI_API_KEY:
                logger.warning(
                    "OPENAI_API_KEY no configurada. Las llamadas a la API fallarán."
                )
            self.api_key = settings.OPENAI_API_KEY
            self.model = settings.OPENAI_MODEL
            self.api_url = "https://api.openai.com/v1/chat/completions"

        elif self.provider == "gemini":
            if not settings.GEMINI_API_KEY:
                logger.warning(
                    "GEMINI_API_KEY no configurada. las llamadas a la API fallaran."
                )
        else:
            logger.warning(
                f"Proveedor de IA no soportado: {self.provider}. Usando respuestas predefinidas."
            )
            self.api_key = None
            self.model = None
            self.api_url = None

    async def handle_conversation(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Maneja la conversación del usuario y genera una respuesta

        Args:
            conversation: Conversación actual
            user_message: Mensaje del usuario

        Returns:
            str: Respuesta generada por el modelo
        """
        try:
            # Verificar si el mensaje es una solicitud de PDF
            if (
                self._is_pdf_request(user_message)
                and conversation.questionnaire_state.completed
            ):
                download_url = f"/api/chat/{conversation.id}/download-proposal-pdf"
                return f"""
# 📄 Propuesta Lista para Descargar

He preparado su propuesta personalizada basada en la información proporcionada. Puede descargarla como PDF usando el siguiente enlace:

## [👉 DESCARGAR PROPUESTA EN PDF]({download_url})

Este documento incluye:
- Análisis de sus necesidades específicas
- Solución tecnológica recomendada
- Estimación de costos y retorno de inversión
- Pasos siguientes recomendados

¿Necesita alguna aclaración sobre la propuesta o tiene alguna otra pregunta?
"""

            # Construir mensajes para la API
            messages = self._prepare_messages(conversation, user_message)

            # Enviar a la API y obtener respuesta
            response = await self._generate_response(messages)

            # Actualizar cuestionario completado si la respuesta contiene propuesta
            if self._contains_proposal_markers(response):
                conversation.questionnaire_state.completed = True
                conversation.questionnaire_state.active = False

            return response

        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar su consulta. Por favor, inténtelo de nuevo."

    def _prepare_messages(
        self, conversation: Conversation, user_message: str
    ) -> List[Dict[str, Any]]:
        """
        Prepara los mensajes para enviar a la API

        Args:
            conversation: Conversación actual
            user_message: Mensaje del usuario

        Returns:
            List[Dict[str, Any]]: Lista de mensajes formateados para la API
        """
        # Iniciar con el mensaje del sistema
        messages = [{"role": "system", "content": settings.SYSTEM_PROMPT}]

        # Agregar contexto de la conversación (últimos mensajes)
        history = []
        for msg in conversation.messages[
            -10:
        ]:  # Incluir solo los últimos 10 mensajes para limitar tokens
            if msg.role in ["user", "assistant"]:  # Excluir mensajes del sistema
                history.append({"role": msg.role, "content": msg.content})

        # Añadir historial si hay mensajes
        if history:
            messages.extend(history)

        # Si el último mensaje no es del usuario, añadir el mensaje actual
        if not history or history[-1]["role"] != "user":
            messages.append({"role": "user", "content": user_message})

        return messages

    async def _generate_response(self, messages: List[Dict[str, Any]]) -> str:
        """
        Genera una respuesta usando el modelo de IA configurado

        Args:
            messages: Lista de mensajes para el modelo

        Returns:
            str: Respuesta generada
        """
        # Verificar si tenemos configuración de API
        if not self.api_key:
            return self._get_fallback_response()

        try:
            # Manejar las llamadas a la API según el proveedor
            if self.provider == "gemini":
                return await self._generate_gemini_response(messages)
            else:  # Para Groq y OpenAI (misma estructura de API)
                return await self._generate_openai_compatible_response(messages)

        except Exception as e:
            logger.error(f"Error al generar respuesta: {str(e)}")
            return self._get_fallback_response()

    async def _generate_openai_compatible_response(
        self, messages: List[Dict[str, Any]]
    ) -> str:
        """
        Genera respuesta usando APIs compatibles con OpenAI (Groq, OpenAI)

        Args:
            messages: Lista de mensajes para el modelo

        Returns:
            str: Respuesta generada
        """
        if not self.api_url:
            return self._get_fallback_response()

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
                response_data = response.json()
                return response_data["choices"][0]["message"]["content"]
            else:
                logger.error(
                    f"Error en la API: {response.status_code} - {response.text}"
                )
                return self._get_fallback_response()

    async def _generate_gemini_response(self, messages: List[Dict[str, Any]]) -> str:
        """
        Genera respuesta usando la API de Gemini

        Args:
            messages: Lista de mensajes para el modelo

        Returns:
            str: Respuesta generada
        """
        try:
            # Importar la biblioteca de Gemini
            from google import genai

            # Configurar cliente con API key
            genai.configure(api_key=self.api_key)

            # Convertir mensajes del formato OpenAI/Groq al formato de Gemini
            gemini_content = []

            # Primero, buscar el mensaje del sistema
            system_content = None
            for msg in messages:
                if msg["role"] == "system":
                    system_content = msg["content"]
                    break

            # Luego, procesar los mensajes de usuario/asistente
            for msg in messages:
                if msg["role"] == "user":
                    gemini_content.append(
                        {"role": "user", "parts": [{"text": msg["content"]}]}
                    )
                elif msg["role"] == "assistant":
                    gemini_content.append(
                        {"role": "model", "parts": [{"text": msg["content"]}]}
                    )

            # Crear el cliente de Gemini
            model = genai.GenerativeModel(
                model_name=self.model, system_instruction=system_content
            )

            # Generar la respuesta
            chat = model.start_chat(
                history=gemini_content[:-1] if gemini_content else []
            )
            response = chat.send_message(
                gemini_content[-1]["parts"][0]["text"] if gemini_content else "Hola"
            )

            return response.text

        except ImportError:
            logger.error(
                "La biblioteca 'google-generativeai' no está instalada. Por favor, instálela con 'pip install google-generativeai'"
            )
            return "Error: La biblioteca de Gemini no está instalada en el servidor."
        except Exception as e:
            logger.error(f"Error al generar respuesta con Gemini: {str(e)}")
            return f"Error al generar respuesta con Gemini: {str(e)}"

    def _is_pdf_request(self, message: str) -> bool:
        """
        Detecta si el mensaje es una solicitud de PDF

        Args:
            message: Mensaje del usuario

        Returns:
            bool: True si parece una solicitud de PDF
        """
        message = message.lower()
        pdf_keywords = [
            "pdf",
            "descargar",
            "documento",
            "propuesta",
            "guardar",
            "exportar",
            "bajar",
        ]

        return any(keyword in message for keyword in pdf_keywords)

    def _contains_proposal_markers(self, response: str) -> bool:
        """
        Detecta si la respuesta contiene marcadores de una propuesta completa

        Args:
            response: Respuesta del modelo

        Returns:
            bool: True si contiene marcadores de propuesta
        """
        markers = [
            "Propuesta Técnica Preliminar",
            "Antecedentes del Proyecto",
            "Parámetros de Diseño",
            "Proceso de Tratamiento Propuesto",
            "Costos Estimados",
            "Análisis ROI",
        ]

        return sum(1 for marker in markers if marker in response) >= 3

    def _get_fallback_response(self) -> str:
        """
        Proporciona una respuesta predefinida en caso de error

        Returns:
            str: Respuesta predefinida
        """
        return """
Gracias por su consulta. Estoy aquí para ayudarle con su proyecto de tratamiento y reciclaje de agua.

Para ofrecerle la mejor solución personalizada, necesitaría conocer más sobre sus necesidades específicas.

**PREGUNTA: ¿Podría indicarme el nombre de su empresa y su ubicación?**

Esto nos ayudará a entender mejor el contexto regional y las normativas aplicables a su caso.
"""


# Instancia global del servicio
ai_service = AIService()
