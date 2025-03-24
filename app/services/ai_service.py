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
            self.api_key = settings.GEMINI_API_KEY
            self.model = settings.GEMINI_MODEL
            self.gemini_client = None
            try:
                from google import genai

                genai.configure(api_key=self.api_key)
                self.gemini_client = genai.GenerativeModel(self.model)
            except ImportError:
                logger.error(
                    "No se pudo importar la biblioteca de Google Generative AI. Instálela con 'pip install google-generative-ai'"
                )
            except Exception as e:
                logger.error(f"Error al inicializar el cliente de Gemini: {e}")
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

    async def _generate_response(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Genera una respuesta utilizando el proveedor de IA configurado
        Con manejo mejorado de errores de límite de tokens

        Args:
            messages: Lista de mensajes para el modelo
            temperature: Nivel de creatividad (0.0 a 1.0)
            max_tokens: Número máximo de tokens en la respuesta

        Returns:
            str: Texto de respuesta generada
        """
        # Caso especial para Gemini
        if (
            self.provider == "gemini"
            and hasattr(self, "gemini_client")
            and self.gemini_client
        ):
            try:
                # Formatear los mensajes para Gemini
                gemini_messages = []
                system_content = ""

                # Extraer el mensaje del sistema primero (si existe)
                for msg in messages:
                    if msg["role"] == "system":
                        system_content = msg["content"]
                        break

                # Formatear el resto de mensajes para Gemini
                for msg in messages:
                    if msg["role"] == "system":
                        continue  # Ya procesamos el mensaje del sistema

                    role = "user" if msg["role"] == "user" else "model"
                    gemini_messages.append({"role": role, "parts": [msg["content"]]})

                # Si no hay mensajes después del formateo, usar mensaje del sistema como prompt inicial
                if not gemini_messages and system_content:
                    # Usar el sistema como primer mensaje del usuario
                    gemini_messages.append({"role": "user", "parts": [system_content]})
                elif system_content and len(gemini_messages) > 0:
                    # Prepend system message to first user message if it exists
                    first_user_idx = next(
                        (
                            i
                            for i, msg in enumerate(gemini_messages)
                            if msg["role"] == "user"
                        ),
                        None,
                    )
                    if first_user_idx is not None:
                        gemini_messages[first_user_idx]["parts"][
                            0
                        ] = f"{system_content}\n\n{gemini_messages[first_user_idx]['parts'][0]}"

                # Asegurarse de que la conversación termine con un mensaje del usuario para generar respuesta
                if gemini_messages and gemini_messages[-1]["role"] == "model":
                    # Si el último mensaje es del modelo, no podemos generar respuesta
                    logger.warning(
                        "La conversación termina con un mensaje del modelo. Añadiendo mensaje de usuario genérico."
                    )
                    gemini_messages.append(
                        {"role": "user", "parts": ["Por favor continúa."]}
                    )

                # Configurar generación
                generation_config = {
                    "temperature": temperature,
                    "max_output_tokens": max_tokens or 1024,
                    "top_p": 0.95,
                    "top_k": 64,
                }

                # Determinar si usamos chat o generación directa
                if len(gemini_messages) > 1:  # Múltiples turnos de conversación
                    # Separar el último mensaje (prompt actual) del historial
                    history = gemini_messages[:-1]
                    current_msg = gemini_messages[-1]["parts"][0]

                    # Iniciar chat con historial
                    chat = self.gemini_client.start_chat(history=history)
                    response = chat.send_message(
                        current_msg, generation_config=generation_config
                    )
                else:  # Un solo mensaje
                    # Generar directamente con el mensaje
                    prompt = gemini_messages[0]["parts"][0]
                    response = self.gemini_client.generate_content(
                        prompt, generation_config=generation_config
                    )

                # Extraer y devolver texto
                if hasattr(response, "text"):
                    return response.text
                elif hasattr(response, "parts"):
                    return "".join([part.text for part in response.parts])
                else:
                    logger.error("Formato de respuesta de Gemini desconocido")
                    return self._get_fallback_response()

            except Exception as e:
                logger.error(f"Error al generar respuesta con Gemini: {str(e)}")
                return self._get_fallback_response()

        # Para proveedores compatibles con OpenAI (Groq, OpenAI, etc.)
        max_retries = 2
        retry_count = 0
        reduced_context = False

        while retry_count <= max_retries:
            try:
                # Verificar si tenemos conexión con la API
                if not self.api_key or not self.api_url:
                    return self._get_fallback_response(messages)

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

                    if response.status_code == 429:  # Rate limit o token limit
                        response_data = response.json()
                        error_message = response_data.get("error", {}).get(
                            "message", ""
                        )

                        if (
                            "tokens per minute" in error_message
                            or "rate_limit_exceeded" in error_message
                        ):
                            # Esperar antes de reintentar si es un error de límite de velocidad
                            wait_time = self._extract_wait_time(error_message) or 20
                            logger.warning(
                                f"Límite de tokens alcanzado. Esperando {wait_time} segundos..."
                            )
                            time.sleep(wait_time)
                            retry_count += 1
                            continue

                        elif (
                            "maximum context length" in error_message
                            or "context_length_exceeded" in error_message
                        ):
                            if not reduced_context:
                                # Reducir el contexto a solo lo esencial
                                messages = self._reduce_context(messages)
                                reduced_context = True
                                continue
                            else:
                                logger.error(
                                    "No se pudo reducir suficientemente el contexto."
                                )
                                return self._get_emergency_response()

                    elif response.status_code != 200:
                        logger.error(
                            f"Error en la API de {self.provider}: {response.status_code} - {response.text}"
                        )
                        return self._get_fallback_response(messages)

                    response_data = response.json()
                    raw_response = response_data["choices"][0]["message"]["content"]
                    return raw_response

            except Exception as e:
                logger.error(
                    f"Error al generar respuesta con {self.provider}: {str(e)}"
                )
                retry_count += 1
                if retry_count > max_retries:
                    return self._get_fallback_response(messages)
                time.sleep(2)  # Pequeña pausa antes de reintentar

        return self._get_fallback_response(messages)

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
