import logging
import httpx
import json
import time
import re
from typing import List, Dict, Any, Optional

from app.config import settings
from app.models.conversation import Conversation

logger = logging.getLogger("hydrous-backend")


class AIService:
    """Servicio para interactuar con modelos de IA"""

    def __init__(self):
        """Inicialización del servicio de IA"""
        self.provider = settings.AI_PROVIDER

        # En caso de que las bibliotecas no estén instaladas,
        # utilizaremos httpx para hacer las solicitudes directamente

        if self.provider == "groq":
            if not settings.GROQ_API_KEY:
                logger.warning(
                    "GROQ_API_KEY no configurada. Las llamadas a la API fallarán."
                )
            self.api_key = settings.GROQ_API_KEY
            self.model = settings.GROQ_MODEL
            self.api_url = "https://api.groq.com/openai/v1/chat/completions"
            self.gemini_client = None

        elif self.provider == "openai":
            if not settings.OPENAI_API_KEY:
                logger.warning(
                    "OPENAI_API_KEY no configurada. Las llamadas a la API fallarán."
                )
            self.api_key = settings.OPENAI_API_KEY
            self.model = settings.OPENAI_MODEL
            self.api_url = "https://api.openai.com/v1/chat/completions"
            self.gemini_client = None

        elif self.provider == "gemini":
            if not settings.GEMINI_API_KEY:
                logger.warning(
                    "GEMINI_API_KEY no configurada. Las llamadas a la API fallarán."
                )
            self.api_key = settings.GEMINI_API_KEY
            self.model = settings.GEMINI_MODEL
            self.api_url = "gemini_api"  # Valor ficticio pero necesario
            self.gemini_client = None
            try:
                from google import genai

                genai.configure(api_key=self.api_key)
                self.gemini_client = genai.GenerativeModel(self.model)
                logger.info(
                    f"Cliente de Gemini inicializado correctamente con modelo {self.model}"
                )
            except ImportError:
                logger.error(
                    "No se pudo importar la biblioteca de Google Generative AI. Instálela con 'pip install google-generative-ai'"
                )
            except Exception as e:
                logger.error(f"Error al inicializar el cliente de Gemini: {e}")

        else:
            # Si el proveedor no está configurado correctamente, usamos un modo de "fallback"
            logger.warning(
                f"Proveedor de IA no soportado: {self.provider}. Usando respuestas pre-configuradas."
            )
            self.api_key = None
            self.model = None
            self.api_url = None
            self.gemini_client = None

    async def handle_conversation(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """Maneja una conversación y genera una respuesta"""
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
            messages = [{"role": "system", "content": settings.SYSTEM_PROMPT}]

            # Añadir historial reciente para dar contexto
            recent_messages = []
            for msg in conversation.messages[
                -8:
            ]:  # Últimos 8 mensajes para mantener el contexto manejable
                if msg.role in ["user", "assistant"]:  # Excluir mensajes del sistema
                    recent_messages.append({"role": msg.role, "content": msg.content})

            # Añadir mensajes recientes si hay
            if recent_messages:
                messages.extend(recent_messages)

            # Si el último mensaje no era del usuario, añadir el mensaje actual
            if not recent_messages or recent_messages[-1]["role"] != "user":
                messages.append({"role": "user", "content": user_message})

            # Generar respuesta
            response = await self._generate_response(messages)

            # Actualizar estado del cuestionario si la respuesta parece ser una propuesta
            if self._contains_proposal_markers(response):
                conversation.questionnaire_state.completed = True
                conversation.questionnaire_state.active = False

            return response

        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar su consulta. Por favor, inténtelo de nuevo."

    async def _generate_response(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Genera una respuesta utilizando el proveedor de IA configurado
        """
        # Si estamos usando Gemini
        if self.provider == "gemini" and self.gemini_client is not None:
            try:
                # Formatear mensajes para Gemini
                # Extraer el mensaje del sistema para usarlo como contexto
                system_message = ""
                user_messages = []

                for msg in messages:
                    if msg["role"] == "system":
                        system_message = msg["content"]
                    elif msg["role"] == "user":
                        user_messages.append({"text": msg["content"]})
                    elif msg["role"] == "assistant":
                        user_messages.append(
                            {"text": f"Respuesta previa: {msg['content']}"}
                        )

                # Combinar el mensaje del sistema con el último mensaje del usuario
                if user_messages and system_message:
                    user_messages[-1][
                        "text"
                    ] = f"{system_message}\n\nPregunta del usuario: {user_messages[-1]['text']}"

                # Si no hay mensajes del usuario, usar solo el sistema
                if not user_messages and system_message:
                    user_messages = [{"text": system_message}]

                # Si después de todo esto no hay mensajes, devolver respuesta por defecto
                if not user_messages:
                    return self._get_fallback_response()

                # Obtener la respuesta de Gemini
                try:
                    generation_config = {
                        "temperature": temperature,
                        "max_output_tokens": max_tokens or 1024,
                    }

                    # Crear el contenido para la generación
                    content = user_messages[-1]["text"]

                    # Generar respuesta
                    response = self.gemini_client.generate_content(
                        content, generation_config=generation_config
                    )

                    return response.text
                except Exception as e:
                    logger.error(f"Error al llamar a la API de Gemini: {str(e)}")
                    return self._get_fallback_response()

            except Exception as e:
                logger.error(f"Error al generar respuesta con Gemini: {str(e)}")
                return self._get_fallback_response()

        # Para Groq y OpenAI
        try:
            # Verificar si tenemos conexión con la API
            if not self.api_key or not self.api_url or self.api_url == "gemini_api":
                return self._get_fallback_response()

            # Hacer solicitud a la API
            async with httpx.AsyncClient() as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }

                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens or 1024,
                }

                response = await client.post(
                    self.api_url, json=payload, headers=headers, timeout=30.0
                )

                if response.status_code != 200:
                    logger.error(
                        f"Error en la API de {self.provider}: {response.status_code} - {response.text}"
                    )
                    return self._get_fallback_response()

                response_data = response.json()
                raw_response = response_data["choices"][0]["message"]["content"]
                return raw_response

        except Exception as e:
            logger.error(f"Error al generar respuesta con {self.provider}: {str(e)}")
            return self._get_fallback_response()

    def _is_pdf_request(self, message: str) -> bool:
        """Determina si el mensaje es una solicitud de PDF"""
        message = message.lower()
        pdf_keywords = [
            "pdf",
            "descargar",
            "propuesta",
            "documento",
            "guardar",
            "archivo",
            "exportar",
            "bajar",
        ]

        return any(keyword in message for keyword in pdf_keywords)

    def _contains_proposal_markers(self, response: str) -> bool:
        """Detecta si la respuesta contiene marcadores de una propuesta completa"""
        markers = [
            "Propuesta Preliminar",
            "Antecedentes del Proyecto",
            "Objetivo del Proyecto",
            "Parámetros de Diseño",
            "Proceso de Tratamiento",
            "Costos Estimados",
        ]

        return sum(1 for marker in markers if marker in response) >= 3

    def _get_fallback_response(self) -> str:
        """Proporciona una respuesta predefinida en caso de error"""
        return """
Gracias por su consulta. Estoy aquí para ayudarle con su proyecto de tratamiento y reciclaje de agua.

Para ofrecerle la mejor solución personalizada, necesitaría conocer más sobre sus necesidades específicas.

**PREGUNTA: ¿Podría indicarme el nombre de su empresa y su ubicación?**

Esto nos ayudará a entender mejor el contexto regional y las normativas aplicables a su caso.
"""


# Instancia global del servicio
ai_service = AIService()
