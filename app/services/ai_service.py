import logging
import re
from typing import List, Dict, Any, Optional
import httpx

from app.config import settings
from app.models.conversation import Conversation
from app.services.questionnaire_service import questionnaire_service

logger = logging.getLogger("hydrous-backend")


class AIService:
    """Servicio para interactuar con modelos de IA"""

    def __init__(self):
        self.provider = settings.AI_PROVIDER

        # En caso de que las bibliotecas groq y openai no estén instaladas,
        # utilizaremos httpx para hacer las solicitudes directamente
        self.groq_api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.openai_api_url = "https://api.openai.com/v1/chat/completions"

        if self.provider == "groq":
            if not settings.GROQ_API_KEY:
                logger.warning(
                    "GROQ_API_KEY no configurada. Las llamadas a la API fallarán."
                )
            self.api_key = settings.GROQ_API_KEY
            self.model = settings.GROQ_MODEL
            self.api_url = self.groq_api_url

        elif self.provider == "openai":
            if not settings.OPENAI_API_KEY:
                logger.warning(
                    "OPENAI_API_KEY no configurada. Las llamadas a la API fallarán."
                )
            self.api_key = settings.OPENAI_API_KEY
            self.model = settings.OPENAI_MODEL
            self.api_url = self.openai_api_url

        else:
            # Si el proveedor no está configurado correctamente, usamos un modo de "fallback"
            logger.warning(
                f"Proveedor de IA no soportado: {self.provider}. Usando respuestas pre-configuradas."
            )
            self.api_key = None
            self.model = None
            self.api_url = None

    async def handle_conversation(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Maneja la conversación incluyendo el flujo del cuestionario si está activo

        Args:
            conversation: Objeto de conversación actual
            user_message: Mensaje del usuario

        Returns:
            str: Respuesta generada para el usuario
        """
        # Si el cuestionario está activo, procesarlo como parte del cuestionario
        if conversation.is_questionnaire_active():
            return await self._handle_questionnaire_flow(conversation, user_message)

        # Verificar si el mensaje del usuario debe iniciar el cuestionario
        if (
            hasattr(settings, "ENABLE_QUESTIONNAIRE")
            and settings.ENABLE_QUESTIONNAIRE
            and self._should_start_questionnaire(user_message)
        ):
            conversation.start_questionnaire()
            intro_text, explanation = questionnaire_service.get_introduction()
            next_question = questionnaire_service.get_next_question(
                conversation.questionnaire_state
            )

            # Combinar introducción con primera pregunta
            response = f"{intro_text}\n\n{explanation}\n\n"
            if next_question:
                response += self._format_question(next_question)
                conversation.questionnaire_state.current_question_id = next_question[
                    "id"
                ]

            return response

        # Si no es parte del cuestionario, procesar normalmente con el modelo de IA
        messages_for_ai = [
            {"role": msg.role, "content": msg.content} for msg in conversation.messages
        ]
        messages_for_ai.append({"role": "user", "content": user_message})

        return await self.generate_response(messages_for_ai)

    async def _handle_questionnaire_flow(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Maneja el flujo del cuestionario

        Args:
            conversation: Objeto de conversación actual
            user_message: Respuesta del usuario a la pregunta anterior

        Returns:
            str: Siguiente pregunta o resumen final
        """
        # Procesar respuesta a la pregunta anterior si existe
        previous_question_id = conversation.questionnaire_state.current_question_id
        if previous_question_id:
            questionnaire_service.process_answer(
                conversation, previous_question_id, user_message
            )

        # Obtener siguiente pregunta
        next_question = questionnaire_service.get_next_question(
            conversation.questionnaire_state
        )

        if not next_question:
            # Si no hay siguiente pregunta, generar propuesta
            if not conversation.is_questionnaire_completed():
                conversation.complete_questionnaire()

            # Generar y formatear propuesta
            proposal = questionnaire_service.generate_proposal(conversation)
            return questionnaire_service.format_proposal_summary(proposal)

        # Actualizar la pregunta actual y devolver la siguiente pregunta formateada
        conversation.questionnaire_state.current_question_id = next_question["id"]
        return self._format_question(next_question)

    def _should_start_questionnaire(self, user_message: str) -> bool:
        """
        Determina si el mensaje del usuario debería iniciar el cuestionario

        Args:
            user_message: Mensaje del usuario

        Returns:
            bool: True si se debe iniciar el cuestionario
        """
        user_message = user_message.lower()

        # Palabras clave que indican interés en soluciones de agua, tratamiento o cuestionario
        keywords = [
            "solución",
            "tratamiento",
            "agua",
            "aguas residuales",
            "reciclaje",
            "cuestionario",
            "comenzar",
            "evaluar",
            "proyecto",
            "propuesta",
        ]

        # Patrones que indican interés específico
        patterns = [
            r"(?:necesito|quiero|busco|interesa).*(?:solución|sistema|tratamiento).*agua",
            r"(?:tratar|reciclar|reutilizar).*agua",
            r"(?:iniciar|comenzar|empezar|hacer).*(?:cuestionario|evaluación|diagnóstico)",
            r"(?:proyecto|propuesta).*(?:agua|tratamiento|reciclaje)",
        ]

        # Verificar palabras clave
        keyword_count = sum(1 for keyword in keywords if keyword in user_message)

        # Verificar patrones
        pattern_match = any(re.search(pattern, user_message) for pattern in patterns)

        # Decidir basado en umbral y patrones
        return keyword_count >= 2 or pattern_match

    def _format_question(self, question: Dict[str, Any]) -> str:
        """
        Formatea una pregunta para presentarla al usuario

        Args:
            question: Datos de la pregunta

        Returns:
            str: Pregunta formateada
        """
        if not question:
            return "Lo siento, no tengo más preguntas para ti en este momento."

        result = question["text"]

        # Añadir explicación si existe
        if question.get("explanation"):
            result += f"\n\n*{question['explanation']}*"

        # Formatear opciones para preguntas de selección
        if question["type"] == "multiple_choice" and "options" in question:
            result += "\n\n"
            for i, option in enumerate(question["options"], 1):
                result += f"{i}. {option}\n"
            result += (
                "\nPor favor, responde con el número de la opción que corresponda."
            )

        elif question["type"] == "multiple_select" and "options" in question:
            result += "\n\n"
            for i, option in enumerate(question["options"], 1):
                result += f"{i}. {option}\n"
            result += "\nPuedes seleccionar varias opciones separando los números con comas (ej: 1,3,4)."

        return result

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Genera una respuesta utilizando el proveedor de IA configurado

        Args:
            messages: Lista de mensajes para la conversación
            temperature: Temperatura para la generación (0.0-1.0)
            max_tokens: Número máximo de tokens para la respuesta

        Returns:
            str: Texto de la respuesta generada
        """
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

                if response.status_code != 200:
                    logger.error(
                        f"Error en la API de {self.provider}: {response.status_code} - {response.text}"
                    )
                    return self._get_fallback_response(messages)

                response_data = response.json()
                return response_data["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"Error al generar respuesta con {self.provider}: {str(e)}")
            return self._get_fallback_response(messages)

    def _get_fallback_response(self, messages: List[Dict[str, Any]]) -> str:
        """
        Genera una respuesta de fallback cuando no podemos conectar con la API

        Args:
            messages: Lista de mensajes para intentar determinar una respuesta contextual

        Returns:
            str: Texto de respuesta pre-configurada
        """
        # Intentar obtener el último mensaje del usuario
        last_user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_message = msg.get("content", "").lower()
                break

        # Respuestas pre-configuradas según palabras clave
        if (
            "hola" in last_user_message
            or "saludos" in last_user_message
            or not last_user_message
        ):
            return (
                "¡Hola! Soy el asistente virtual de Hydrous especializado en soluciones de reciclaje de agua. "
                "¿En qué puedo ayudarte hoy?"
            )

        elif any(
            word in last_user_message
            for word in ["filtro", "filtración", "purificación"]
        ):
            return (
                "Nuestros sistemas de filtración avanzada eliminan contaminantes, sedimentos y patógenos "
                "del agua. Utilizamos tecnología de membranas, carbón activado y filtros biológicos para "
                "adaptarnos a diferentes necesidades. ¿Te gustaría más información sobre algún sistema específico?"
            )

        elif any(
            word in last_user_message for word in ["aguas grises", "duchas", "lavadora"]
        ):
            return (
                "Nuestros sistemas de tratamiento de aguas grises reciclan el agua de duchas, lavabos y lavadoras "
                "para su reutilización en inodoros, riego o limpieza. Son modulares y se adaptan a diferentes "
                "espacios. ¿Necesitas información para un proyecto residencial o comercial?"
            )

        elif any(
            word in last_user_message for word in ["lluvia", "pluvial", "captación"]
        ):
            return (
                "Los sistemas de captación de agua de lluvia de Hydrous incluyen filtración, almacenamiento "
                "y distribución. Pueden integrarse con otros sistemas de tratamiento para maximizar la "
                "eficiencia hídrica. ¿Te interesa una instalación doméstica o industrial?"
            )

        elif (
            "precio" in last_user_message
            or "costo" in last_user_message
            or "valor" in last_user_message
        ):
            return (
                "Los precios varían según el tipo de sistema y las necesidades específicas de tu proyecto. "
                "Podemos programar una consulta con nuestros especialistas para evaluar tus requerimientos "
                "y ofrecerte un presupuesto personalizado. ¿Te gustaría que un representante te contacte?"
            )

        else:
            return (
                "Gracias por tu pregunta. Para brindarte la información más precisa sobre nuestras "
                "soluciones de reciclaje de agua, te recomendaría hablar directamente con uno de nuestros "
                "especialistas. ¿Te gustaría que programemos una consulta personalizada?"
            )


# Clase extendida del servicio de IA (se utilizará en lugar de la estándar)
class AIWithQuestionnaireService(AIService):
    """Versión del servicio de IA con funcionalidad de cuestionario integrada"""

    def __init__(self):
        super().__init__()


# Instancia global del servicio
ai_service = AIWithQuestionnaireService()
