import logging
import re
from typing import List, Dict, Any, Optional, Tuple
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
            
        # Patrones para detectar intención de interrupción del cuestionario
        self.interruption_patterns = [
            r"(?:cancelar|salir|terminar|detener|parar|abandonar).*(?:cuestionario|formulario|preguntas)",
            r"(?:no|ya no).*(?:quiero|deseo|me interesa).*(?:seguir|continuar|responder)",
            r"(?:quiero|necesito).*(?:hablar|consultar).*(?:otra cosa|otro tema)",
            r"(?:cambia|cambiemos).*(?:tema|asunto)",
            r"(?:volvamos|volver).*(?:después|luego)",
        ]
        
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
        # Comprobar si el usuario quiere interrumpir el cuestionario
        if conversation.is_questionnaire_active() and self._is_interruption_intent(user_message):
            return await self._handle_questionnaire_interruption(conversation)
            
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
        Maneja el flujo del cuestionario de manera más conversacional

        Args:
            conversation: Objeto de conversación actual
            user_message: Respuesta del usuario a la pregunta anterior

        Returns:
            str: Siguiente pregunta o resumen final
        """
        # Obtener información de la pregunta actual
        previous_question_id = conversation.questionnaire_state.current_question_id
        
        if not previous_question_id:
            # Si por alguna razón no hay pregunta actual pero el cuestionario está activo
            return self._handle_questionnaire_error(conversation)
            
        # Procesar la respuesta del usuario
        process_result = questionnaire_service.process_answer(
            conversation, previous_question_id, user_message
        )
        
        # Si el procesamiento falló, solicitar clarificación
        if process_result is not True:
            return f"{questionnaire_service.get_clarification_phrase()} responder de nuevo? {process_result}"

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
        
        # Formatear la siguiente pregunta con transición suave
        return questionnaire_service.format_question_with_transition(
            next_question, user_message
        )
        
    def _is_interruption_intent(self, user_message: str) -> bool:
        """
        Determina si el mensaje del usuario indica intención de interrumpir el cuestionario

        Args:
            user_message: Mensaje del usuario

        Returns:
            bool: True si se detecta intención de interrumpir
        """
        user_message = user_message.lower()
        
        # Verificar patrones de interrupción
        for pattern in self.interruption_patterns:
            if re.search(pattern, user_message):
                return True
                
        return False
        
    async def _handle_questionnaire_interruption(self, conversation: Conversation) -> str:
        """
        Maneja una interrupción del cuestionario por parte del usuario

        Args:
            conversation: Objeto de conversación actual

        Returns:
            str: Mensaje de respuesta sobre la interrupción
        """
        # Guardar el estado para posible reanudación
        conversation.questionnaire_state.active = False
        
        return (
            "Entiendo que prefieres pausar el cuestionario por ahora. No hay problema. "
            "He guardado tu progreso y podemos continuar en otro momento si lo deseas. "
            "¿En qué más puedo ayudarte respecto a nuestras soluciones de reciclaje de agua?"
        )
        
    def _handle_questionnaire_error(self, conversation: Conversation) -> str:
        """
        Maneja errores en el flujo del cuestionario

        Args:
            conversation: Objeto de conversación actual

        Returns:
            str: Mensaje de respuesta sobre el error
        """
        # Reiniciar el estado del cuestionario
        next_question = questionnaire_service.get_next_question(
            conversation.questionnaire_state
        )
        
        if next_question:
            conversation.questionnaire_state.current_question_id = next_question["id"]
            return (
                "Parece que hubo un pequeño problema técnico con nuestro cuestionario. "
                "Vamos a retomarlo desde aquí:\n\n" + self._format_question(next_question)
            )
        else:
            # Si no hay pregunta siguiente, terminar el cuestionario
            conversation.questionnaire_state.active = False
            return (
                "Parece que hubo un problema con el cuestionario. "
                "¿Te gustaría reiniciarlo o prefieres que conversemos de otra forma sobre "
                "nuestras soluciones de tratamiento de agua?"
            )
            
    def _should_start_questionnaire(self, user_message: str) -> bool:
        """
        Determina si el mensaje del usuario debería iniciar el cuestionario.
        Detecta intenciones relacionadas con evaluación, soluciones personalizadas o cuestionario.

        Args:
            user_message: Mensaje del usuario

        Returns:
            bool: True si se debe iniciar el cuestionario
        """
        user_message = user_message.lower()

        # Palabras clave que indican interés en soluciones de agua, tratamiento o cuestionario
        keywords = [
            "solución", "tratamiento", "agua", "aguas residuales", "reciclaje",
            "cuestionario", "comenzar", "evaluar", "proyecto", "propuesta",
            "personalizado", "diseño", "sistema", "ayuda", "necesito"
        ]

        # Patrones que indican interés específico
        patterns = [
            r"(?:necesito|quiero|busco|interesa).*(?:solución|sistema|tratamiento).*agua",
            r"(?:tratar|reciclar|reutilizar).*agua",
            r"(?:iniciar|comenzar|empezar|hacer).*(?:cuestionario|evaluación|diagnóstico)",
            r"(?:proyecto|propuesta).*(?:agua|tratamiento|reciclaje)",
            r"(?:diseñar|crear|implementar).*(?:sistema|solución).*agua",
            r"(?:ayuda|ayúdame).*(?:elegir|seleccionar|encontrar).*(?:sistema|solución)",
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
                "\nPor favor, responde con el número o el nombre de la opción que corresponda."
            )

        elif question["type"] == "multiple_select" and "options" in question:
            result += "\n\n"
            for i, option in enumerate(question["options"], 1):
                result += f"{i}. {option}\n"
            result += "\nPuedes seleccionar varias opciones separando los números con comas (ej: 1,3,4) o escribiendo sus nombres."

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
                    "Authorization": f"Bearer {self.
