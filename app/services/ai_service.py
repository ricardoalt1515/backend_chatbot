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
        Maneja la conversación delegando la mayor parte de la lógica al modelo de IA

        Args:
            conversation: Objeto de conversación actual
            user_message: Mensaje del usuario

        Returns:
            str: Respuesta generada para el usuario
        """
        # Verificar si debemos iniciar un cuestionario basado en el mensaje del usuario
        should_start = False
        if (
            not conversation.is_questionnaire_active()
            and not conversation.is_questionnaire_completed()
        ):
            should_start = self._should_start_questionnaire(user_message)
            if should_start:
                conversation.start_questionnaire()

        # Preparar mensajes para el modelo de IA con el prompt específico
        messages_for_ai = [
            {"role": "system", "content": settings.SYSTEM_PROMPT_WITH_QUESTIONNAIRE}
        ]

        # Añadir documentos de referencia como contexto
        # 1. Añadir el cuestionario completo como contexto adicional
        if conversation.is_questionnaire_active():
            # Filtrar por sector/subsector si ya se han seleccionado
            questionnaire_context = questionnaire_service.get_questionnaire_as_context(
                conversation.questionnaire_state.sector,
                conversation.questionnaire_state.subsector,
            )
            messages_for_ai.append(
                {
                    "role": "system",
                    "content": f"REFERENCIA DEL CUESTIONARIO:\n{questionnaire_context}",
                }
            )

        # 2. Añadir el formato de propuesta como contexto adicional
        if conversation.is_questionnaire_completed() or (
            conversation.is_questionnaire_active()
            and len(conversation.questionnaire_state.answers) > 10
        ):
            proposal_format = questionnaire_service.get_proposal_format()
            messages_for_ai.append(
                {
                    "role": "system",
                    "content": f"FORMATO DE PROPUESTA:\n{proposal_format}",
                }
            )

        # Añadir la información de estado actual del cuestionario
        if (
            conversation.is_questionnaire_active()
            or conversation.is_questionnaire_completed()
        ):
            state_context = self._generate_state_context(conversation)
            messages_for_ai.append({"role": "system", "content": state_context})

        # Añadir historial de mensajes
        for msg in conversation.messages:
            if msg.role != "system":  # Excluimos los mensajes de sistema originales
                messages_for_ai.append({"role": msg.role, "content": msg.content})

        # Añadir el mensaje actual del usuario
        messages_for_ai.append({"role": "user", "content": user_message})

        # Si acabamos de iniciar el cuestionario, dar una pista al modelo
        if should_start:
            messages_for_ai.append(
                {
                    "role": "system",
                    "content": "El usuario ha mostrado interés en soluciones de tratamiento de agua. Inicia el proceso de cuestionario con el saludo estándar y la primera pregunta sobre el sector.",
                }
            )

        # Generar respuesta con el modelo de IA
        response = await self.generate_response(messages_for_ai)

        # Procesamiento posterior mínimo para actualizar el estado
        self._update_questionnaire_state(conversation, user_message, response)

        return response

    def _generate_state_context(self, conversation: Conversation) -> str:
        """
        Genera un contexto sobre el estado actual del cuestionario

        Args:
            conversation: Objeto de conversación actual

        Returns:
            str: Contexto sobre el estado actual
        """
        state = conversation.questionnaire_state
        context = "ESTADO ACTUAL DEL CUESTIONARIO:\n"

        if state.sector:
            context += f"- Sector seleccionado: {state.sector}\n"

        if state.subsector:
            context += f"- Subsector seleccionado: {state.subsector}\n"

        if state.answers:
            context += "- Respuestas proporcionadas hasta ahora:\n"
            for q_id, answer in state.answers.items():
                context += f"  • Pregunta '{q_id}': {answer}\n"

        if state.completed:
            context += "- El cuestionario ha sido completado. Genera una propuesta final usando el formato de propuesta proporcionado.\n"
        elif state.active:
            context += "- El cuestionario está activo. Continúa con la siguiente pregunta según el documento del cuestionario.\n"

        return context

    def _update_questionnaire_state(
        self, conversation: Conversation, user_message: str, ai_response: str
    ) -> None:
        """
        Actualiza el estado del cuestionario basado en la interacción

        Args:
            conversation: Objeto de conversación actual
            user_message: Mensaje del usuario
            ai_response: Respuesta generada por el modelo
        """
        state = conversation.questionnaire_state

        # Si el cuestionario está activo
        if state.active and not state.completed:
            # Lógica simplificada para detectar sector/subsector
            if not state.sector:
                # Intentar identificar el sector en la respuesta del usuario
                sectors = ["Industrial", "Comercial", "Municipal", "Residencial"]
                for sector in sectors:
                    if sector.lower() in user_message.lower():
                        state.sector = sector
                        break
                # También verificar respuestas numéricas (1-4)
                if user_message.strip() in ["1", "2", "3", "4"]:
                    index = int(user_message.strip()) - 1
                    if 0 <= index < len(sectors):
                        state.sector = sectors[index]

            # Similar para subsector, si ya tenemos sector pero no subsector
            elif state.sector and not state.subsector:
                subsectors = []
                if state.sector == "Industrial":
                    subsectors = [
                        "Alimentos y Bebidas",
                        "Textil",
                        "Petroquímica",
                        "Farmacéutica",
                        "Minería",
                        "Petróleo y Gas",
                        "Metal/Automotriz",
                        "Cemento",
                    ]
                elif state.sector == "Comercial":
                    subsectors = [
                        "Hotel",
                        "Edificio de oficinas",
                        "Centro comercial/Comercio minorista",
                        "Restaurante",
                    ]
                elif state.sector == "Municipal":
                    subsectors = [
                        "Gobierno de la ciudad",
                        "Pueblo/Aldea",
                        "Autoridad de servicios de agua",
                    ]
                elif state.sector == "Residencial":
                    subsectors = ["Vivienda unifamiliar", "Edificio multifamiliar"]

                # Buscar coincidencia por texto
                for subsector in subsectors:
                    if subsector.lower() in user_message.lower():
                        state.subsector = subsector
                        break

                # Verificar respuestas numéricas
                if user_message.strip().isdigit():
                    index = int(user_message.strip()) - 1
                    if 0 <= index < len(subsectors):
                        state.subsector = subsectors[index]

            # Detectar si el cuestionario ha sido completado (propuesta generada)
            if (
                "RESUMEN DE LA PROPUESTA" in ai_response
                or "CAPEX & OPEX" in ai_response
            ):
                state.completed = True
                state.active = False

    def _should_start_questionnaire(self, user_message: str) -> bool:
        """
        Determina si el mensaje del usuario debería iniciar el cuestionario

        Args:
            user_message: Mensaje del usuario

        Returns:
            bool: True si se debe iniciar el cuestionario
        """
        user_message = user_message.lower()

        # Palabras clave directamente relacionadas con iniciar el proceso
        explicit_keywords = [
            "cuestionario",
            "empezar",
            "comenzar",
            "iniciar",
            "evaluación",
            "diagnóstico",
            "propuesta",
        ]

        # Palabras clave relacionadas con soluciones de agua
        water_keywords = [
            "agua",
            "tratamiento",
            "residual",
            "reciclaje",
            "filtración",
            "sistemas",
            "solución",
            "ahorro",
            "optimización",
        ]

        # Verificar frases explícitas
        explicit_phrases = [
            "necesito una solución",
            "quiero información",
            "ayúdame con",
            "busco opciones",
            "cómo puedo",
        ]

        # Si contiene alguna palabra clave explícita, iniciar cuestionario
        for keyword in explicit_keywords:
            if keyword in user_message:
                return True

        # Contar palabras clave relacionadas con agua
        water_keyword_count = sum(
            1 for keyword in water_keywords if keyword in user_message
        )

        # Si contiene al menos 2 palabras clave de agua, iniciar cuestionario
        if water_keyword_count >= 2:
            return True

        # Verificar frases explícitas junto con alguna palabra clave de agua
        for phrase in explicit_phrases:
            if phrase in user_message and any(
                keyword in user_message for keyword in water_keywords
            ):
                return True

        return False

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
