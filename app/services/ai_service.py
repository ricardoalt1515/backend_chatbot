import logging
import re
from typing import List, Dict, Any, Optional
import httpx
import random

from app.config import settings
from app.models.conversation import Conversation, QuestionnaireState
from app.services.questionnaire_service import questionnaire_service
from app.models import message

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
        # Verificar si el mensaje del usuario debe iniciar el cuestionario
        should_start = False
        if (
            not conversation.is_questionnaire_active()
            and not conversation.is_questionnaire_completed()
        ):
            should_start = self._should_start_questionnaire(user_message)
            if should_start:
                conversation.start_questionnaire()
                # No añadimos ningun mensaje especial, dejamos que el modelo la Maneje

            # Preparar mensajes para el modelo de IA
            messages_for_ai = [
                {"role": "system", "content": settings.SYSTEM_PROMPT_WITH_QUESTIONNAIRE}
            ]

            # Añadir contexto adicional con el estado del cuestionario
            if (
                conversation.is_questionnaire_active()
                or conversation.is_questionnaire_completed()
            ):
                questionnaire_context = self._generate_questionnaire_context(
                    conversation
                )
                messages_for_ai.append(
                    {"role": "system", "content": questionnaire_context}
                )

            # añadir historial de mensajes
            for msg in conversation.messages:
                if msg.role != "system":  # Excluimos los mensajes de sistema originales
                    messages_for_ai.append({"role": msg.role, "content": msg.content})

            # añadir el mensaje actual del usuario
            messages_for_ai.append({"role": "user", "content": user_message})

            # Si acabamos de iniciar el cuestionario, podemos añadir una pista para el modelo
            if should_start:
                messages_for_ai.append(
                    {
                        "role": "system",
                        "content": "El usuario ha mostrado interes en soluciones de agua. Inicia el proceso de cuestionario con el saludo estandar y la primera pregunta sobre el sector.",
                    }
                )
            # Generar respuesta con el modelo de IA
            response = await self.generate_response(messages_for_ai)

            # Procesar la respuest para actualizar el estado del cuestionario si es necesario
            self._update_questionnaire_state_from_response(conversation, response)

            return response

        def _generate_questionnaire_context(self, conversation: Conversation) -> str:
            """
            Genera un contexto informativo sobre el estado actual del cuestionario

            Args:
                conversation: Objeto de conversacion actual
            Returns:
                str: Contexto para el modelo de IA
            """
            state = conversation.questionnaire_state
            context = "INFORMACION DEL ESTADO DEL CUESTIONARIO:\n"

            if state.sector:
                context += f"Sector seleccionado: {state.sector}\n"

            if state.subsector:
                context += f"Subsector seleccionado: {state.subsector}\n"

            if state.current_question_id:
                context += f"ID de la pregunta actual: {state.current_question_id}\n"

            if state.answers:
                context += "Respuestas proporcionadas hasta ahora:\n"
                for q_id, answer in state.answers.items():
                    context += f"- Pregunta '{q_id}': {answer}\n"

            if state.completed:
                context += "El cuestionario ha sido completado. Debes proporcionar una propuesta final.\n"
            elif state.active:
                context += "El cuestionario esta activo. Debes seguir haciendo las preguntas en orden.\n"

                # Determinar cual deberia ser la siguiente pregunta
                if not state.sector:
                    context += f"La siguiente pregunta debe ser sobre el subsector dentro de {state.sector}.\n"
                elif not state.subsector:
                    context += f"La siguiente pregunta debe ser sobre el subsector especifico dentro de {state.sector}.\n"
                else:
                    # Determinar la proxima pregunta basada en las anteriores
                    question_key = f"{state.sector}_{state.subsecotr}"
                    questions = questionnaire_service.questionnaire_data.get(
                        "questions", {}
                    ).get(question_key, [])

                    if questions:
                        # Encontrar la primera pregunta no respondida
                        for question in questions:
                            if question["id"] not in state.answers:
                                context += f"La siguiente pregunta debe ser: {question['text']}\n"
                                if (
                                    question.get("type") == "multiple_choice"
                                    and "options" in question
                                ):
                                    context += "Las opciones son:\n"
                                    for i, option in enumerate(question["options"], 1):
                                        context += f"{i}. {option}\n"
                                break

        return context

    def _update_questionnaire_state_from_response(
        self, conversation: Conversation, response: str
    ) -> None:
        """
        Actualiza el estado del cuestionario basado en la respuesta del modelo

        Args:
            conversation: Objeto de conversación actual
            response: Respuesta generada por el modelo

        """
        # Este modelo implementa una logica simplificada para detectar cuando
        # el cuestionario ha sido completado basado en la respuesta generada

        # Si ya esta completado, no hacemos nada
        if conversation.is_questionnaire_completed():
            return

        # Si el cuestionario esta activo, intentamos procesar la respuesta
        if conversation.is_questionnaire_active():
            # Buscar frases que indiquen que se ha completado
            completion_phrases = [
                "propuesta personalizada",
                "resumen de la propuesta",
                "gracias por completar el cuestionario",
                "basado en sus respuestas",
                "basandonos en tus resouestas",
                "hemos preparado una propuesta",
                "analisis economico",
                "retorno de inversion",
                "proximos pasos",
            ]

            # Si encontramos indicadores de que el cuestionario ha terminado
            if any(phrase in response.lower() for phrase in completion_phrases):
                conversation.complete_questionnaire()

    async def _handle_questionnaire_flow(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Maneja el flujo del cuestionario de manera más flexible y conversacional

        Args:
            conversation: Objeto de conversación actual
            user_message: Respuesta del usuario a la pregunta anterior

        Returns:
            str: Siguiente pregunta o resumen final
        """
        # Procesar respuesta a la pregunta anterior si existe
        previous_question_id = conversation.questionnaire_state.current_question_id
        if previous_question_id:
            # Determinar el tipo de pregunta para procesar adecuadamente la respuesta
            question_info = self._get_question_info(
                conversation.questionnaire_state, previous_question_id
            )

            if question_info:
                question_type = question_info.get("type", "text")
                options = question_info.get("options", [])

                # Procesar la respuesta según el tipo de pregunta
                processed_answer = self._process_user_answer(
                    user_message, question_type, options
                )

                # Guardar la respuesta procesada
                questionnaire_service.process_answer(
                    conversation, previous_question_id, processed_answer
                )
            else:
                # Si no encontramos info de la pregunta, guardamos la respuesta tal cual
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
        con un enfoque más sensible al contexto

        Args:
            user_message: Mensaje del usuario

        Returns:
            bool: True si se debe iniciar el cuestionario
        """
        user_message = user_message.lower()

        # Palabras clave que indican interés en soluciones de agua, tratamiento o cuestionario
        keywords = [
            "solución",
            "soluciones",
            "tratamiento",
            "sistema",
            "agua",
            "aguas",
            "residuales",
            "reciclaje",
            "reciclar",
            "reutilizar",
            "reutilización",
            "cuestionario",
            "preguntas",
            "evaluar",
            "evaluación",
            "diagnóstico",
            "proyecto",
            "propuesta",
            "cotización",
            "presupuesto",
            "implementar",
            "necesito",
            "quiero",
            "busco",
            "interesa",
            "información",
            "requiero",
            "filtración",
            "tratamiento",
            "purificación",
            "industrial",
            "planta",
        ]

        # Patrones que indican interés específico
        patterns = [
            r"(?:necesito|quiero|busco|me\s+interesa).*(?:solución|sistema|tratamiento).*agua",
            r"(?:tratar|reciclar|reutilizar).*agua",
            r"(?:iniciar|comenzar|empezar|hacer).*(?:cuestionario|evaluación|diagnóstico)",
            r"(?:proyecto|propuesta|cotización).*(?:agua|tratamiento|reciclaje)",
            r"(?:cuánto|precio|costo|presupuesto).*(?:sistema|tratamiento|planta)",
            r"(?:cómo|opciones|alternativas).*(?:reciclar|tratar|purificar).*agua",
            r"(?:información|datos).*(?:tratamiento|purificación|sistema)",
            r"(?:estoy\s+interesado|me\s+gustaría).*(?:implementar|instalar)",
            r"(?:tengo|genero).*aguas\s+residuales",
        ]

        # Frases explícitas que siempre deberían iniciar el cuestionario
        explicit_phrases = [
            "hacer el cuestionario",
            "iniciar cuestionario",
            "comenzar evaluación",
            "quiero una propuesta",
            "necesito un presupuesto",
            "quiero instalar",
            "necesito un sistema",
            "tengo un proyecto",
            "busco soluciones",
            "cuánto cuesta",
            "opciones de tratamiento",
        ]

        # Verificar frases explícitas primero
        for phrase in explicit_phrases:
            if phrase in user_message:
                return True

        # Verificar patrones
        pattern_match = any(re.search(pattern, user_message) for pattern in patterns)
        if pattern_match:
            return True

        # Verificar palabras clave con un umbral más sensible
        keyword_count = sum(1 for keyword in keywords if keyword in user_message)

        # Decidir basado en umbral
        return (
            keyword_count >= 3
        )  # Requiere al menos 3 palabras clave para mayor precisión

    def _process_user_answer(
        self, user_message: str, question_type: str, options: List[str]
    ) -> Any:
        """
        Procesa la respuesta del usuario de manera más flexible

        Args:
            user_message: Respuesta del usuario
            question_type: Tipo de pregunta (text, multiple_choice, multiple_select)
            options: Lista de opciones disponibles para la pregunta

        Returns:
            Any: Respuesta procesada
        """
        user_message = user_message.strip()

        # Para preguntas de texto, devolver el mensaje tal cual
        if question_type == "text":
            return user_message

        # Para preguntas de selección única
        if question_type == "multiple_choice" and options:
            # Primero verificar si es un número válido
            if user_message.isdigit():
                option_index = int(user_message) - 1
                if 0 <= option_index < len(options):
                    return str(
                        option_index + 1
                    )  # Devolver el índice como string (1-based)

            # Si no es un número, buscar la opción por texto
            user_message_lower = user_message.lower()
            for i, option in enumerate(options, 1):
                if (
                    option.lower() in user_message_lower
                    or user_message_lower in option.lower()
                ):
                    return str(i)  # Devolver el índice como string (1-based)

            # Si no encontramos coincidencia, devolver el texto original
            return user_message

        # Para preguntas de selección múltiple
        if question_type == "multiple_select" and options:
            # Verificar si son números separados por comas
            if all(
                part.strip().isdigit()
                for part in user_message.split(",")
                if part.strip()
            ):
                selected_indices = [
                    part.strip() for part in user_message.split(",") if part.strip()
                ]
                return ",".join(selected_indices)

            # Si no son números, buscar coincidencias por texto
            selected_indices = []
            user_message_lower = user_message.lower()

            for i, option in enumerate(options, 1):
                if option.lower() in user_message_lower:
                    selected_indices.append(str(i))

            if selected_indices:
                return ",".join(selected_indices)

            # Si no encontramos coincidencias, devolver el texto original
            return user_message

        # Para cualquier otro caso, devolver el mensaje original
        return user_message

    def _get_question_info(
        self, questionnaire_state: QuestionnaireState, question_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Obtiene la información completa de una pregunta por su ID

        Args:
            questionnaire_state: Estado actual del cuestionario
            question_id: ID de la pregunta

        Returns:
            Optional[Dict[str, Any]]: Información de la pregunta o None si no se encuentra
        """
        # Manejar preguntas especiales de selección de sector y subsector
        if question_id == "sector_selection":
            return {
                "id": "sector_selection",
                "text": "¿En qué sector opera tu empresa?",
                "type": "multiple_choice",
                "options": questionnaire_service.get_sectors(),
                "required": True,
            }
        elif question_id == "subsector_selection" and questionnaire_state.sector:
            return {
                "id": "subsector_selection",
                "text": f"¿Cuál es el giro específico de tu Empresa dentro del sector {questionnaire_state.sector}?",
                "type": "multiple_choice",
                "options": questionnaire_service.get_subsectors(
                    questionnaire_state.sector
                ),
                "required": True,
            }

        # Buscar en las preguntas regulares del cuestionario
        if questionnaire_state.sector and questionnaire_state.subsector:
            question_key = (
                f"{questionnaire_state.sector}_{questionnaire_state.subsector}"
            )
            questions = questionnaire_service.questionnaire_data.get(
                "questions", {}
            ).get(question_key, [])

            for question in questions:
                if question["id"] == question_id:
                    return question

        return None

    def _format_question(self, question: Dict[str, Any]) -> str:
        """
        Formatea una pregunta para presentarla al usuario de manera más conversacional

        Args:
            question: Datos de la pregunta

        Returns:
            str: Pregunta formateada
        """
        if not question:
            return "¡Genial! Ya tengo toda la información que necesitaba. Permíteme un momento para preparar mi recomendación personalizada para ti."

        # Elegir un prefijo aleatorio para hacer más conversacional
        prefixes = [
            "Ahora, ",
            "Perfecto. ",
            "Excelente. ",
            "Gracias por esa información. ",
            "Entendido. ",
            "Muy bien. ",
        ]

        prefix = random.choice(prefixes)

        # Formatear la pregunta principal
        result = f"{prefix}{question['text']}"

        # Añadir explicación si existe, con formato mejorado
        if question.get("explanation"):
            result += f"\n\n*Nota: {question['explanation']}*"

        # Formatear opciones para preguntas de selección
        if question["type"] == "multiple_choice" and "options" in question:
            result += "\n\n"
            for i, option in enumerate(question["options"], 1):
                result += f"{i}. {option}\n"
            result += "\nPuedes responder con el número o el nombre de la opción que corresponda."

        elif question["type"] == "multiple_select" and "options" in question:
            result += "\n\n"
            for i, option in enumerate(question["options"], 1):
                result += f"{i}. {option}\n"
            result += "\nPuedes seleccionar varias opciones separando los números con comas o mencionando los nombres directamente."

        # Añadir un dato interesante si es una pregunta importante
        try:
            sector = questionnaire_service.questionnaire_data.get(
                "sectors", ["Industrial"]
            )[0]
            subsector = questionnaire_service.questionnaire_data.get(
                "subsectors", {}
            ).get(sector, ["General"])[0]
            fact = questionnaire_service.get_random_fact(sector, subsector)

            if (
                fact and random.random() < 0.5
            ):  # Solo añadir el dato el 50% de las veces para no ser repetitivo
                result += f"\n\n*Dato interesante: {fact}*"
        except Exception as e:
            # En caso de error al obtener un dato, simplemente no lo añadimos
            logger.debug(f"Error obteniendo dato interesante: {str(e)}")

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
