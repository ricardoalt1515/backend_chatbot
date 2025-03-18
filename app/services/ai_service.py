import logging
import re
from typing import List, Dict, Any, Optional, Tuple
import httpx
import time
import json
from datetime import datetime

from app.config import settings
from app.models.conversation import Conversation
from app.services.questionnaire_service import questionnaire_service
from routes import documents

# Intento importar el contador de tokens si está disponible
try:
    from app.utils.token_counter import count_tokens, estimate_cost

    token_counter_available = True
except ImportError:
    token_counter_available = False

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

        # Mensaje de saludo inical
        self.INITIAL_GREETING = """
        # Bienvenido a Hydrous Managment Group

        Soy el Diseñador de Soluciones de Agua con IA de Hydrous, su asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales. Como herramienta de Hydrous, estoy aquí para guiarlo paso a paso en la evaluación de las necesidades de agua de su sitio, la exploración de posibles soluciones y la identificación de oportunidades de ahorro, cumplimiento normativo y sostenibilidad.

        Para desarrollar la mejor solución para sus instalaciones, formularé sistemáticamente preguntas específicas para recopilar los datos necesarios y crear una propuesta personalizada. Mi objetivo es ayudarle a optimizar la gestión del agua, reducir costes y explorar nuevas fuentes de ingresos con soluciones basadas en Hydrous.

        *Las soluciones de reciclaje de agua pueden reducir el consumo de agua fresca hasta en un 70% en instalaciones industriales similares.*

        **PREGUNTA: ¿En qué sector opera su empresa?**
        1. Industrial
        2. Comercial
        3. Municipal
        4. Residencial
        """

        # Atributos para mantener el contexto entre llamadas
        self.current_sector = None
        self.current_subsector = None

    def format_response_with_questions(
        self,
        previous_answer_comment,
        interesting_fact,
        question_context,
        question_text,
        options=None,
    ):
        """Formatea una rispuesta siguiendo la estructura establecida"""
        response = f"{previous_answer_comment}\n\n"

        if interesting_fact:
            response += f"*{interesting_fact}*\n\n"

        if question_context:
            response += f"{question_context}\n\n"

        response += f"**PREGUNTA: {question_text}**\n\n"

        if options:
            for i, option in enumerate(options, 1):
                response += f"{i}. {option}\n"

        return response

    def should_suggest_document(self, question_id):
        """Determina si se debe sugerir subir un documento en esta pregunta"""
        document_suggestion_question = [
            "parametros de agua",
            "costo de agua",
            "sistema_existente",
            "recibos_agua",
            "descripcion_sistema",
            "agua_potable_analisis",
        ]

        return question_id in document_suggestion_question

    async def handle_conversation(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """Maneja la conversación siguiendo el enfoque estructurado del cuestionario"""
        # Si no está activo el cuestionario, iniciarlo si detectamos intención
        if (
            not conversation.is_questionnaire_active()
            and not conversation.is_questionnaire_completed()
        ):
            if self._detect_questionnaire_intent(user_message):
                conversation.start_questionnaire()

        # Procesar la respuesta del usuario si el cuestionario está activo
        if conversation.is_questionnaire_active():
            # Actualizar estado con la respuesta actual
            self._update_questionnaire_state(conversation, user_message)

            # Verificar si completamos el cuestionario con esta respuesta
            next_question = self._get_next_question(conversation)
            if not next_question:
                # Marcar como recopilación completa pero aún no finalizado
                conversation.questionnaire_state.recopilacion_completa = True
                # Generar diagnóstico preliminar
                return questionnaire_service.generate_preliminary_diagnosis(
                    conversation
                )

            # Verificar si acabamos de responder el diagnóstico preliminar
            if getattr(
                conversation.questionnaire_state, "recopilacion_completa", False
            ) and not getattr(
                conversation.questionnaire_state, "confirmacion_mostrada", False
            ):
                # Verificar si el usuario quiere proceder con la propuesta
                if any(
                    keyword in user_message.lower()
                    for keyword in [
                        "proceder",
                        "generar",
                        "propuesta",
                        "continuar",
                        "siguiente",
                        "sí",
                        "si",
                    ]
                ):
                    # Mostrar pantalla de confirmación final
                    conversation.questionnaire_state.confirmacion_mostrada = True
                    return self.generate_final_confirmation(conversation)
                else:
                    # El usuario tiene preguntas o dudas sobre el diagnóstico
                    return self._handle_diagnosis_questions(conversation, user_message)

            # Verificar si estamos en la fase de confirmación final
            if (
                getattr(
                    conversation.questionnaire_state, "confirmacion_mostrada", False
                )
                and not conversation.is_questionnaire_completed()
            ):
                # Si el usuario confirma, completar cuestionario y generar propuesta
                if any(
                    keyword in user_message.lower()
                    for keyword in [
                        "generar propuesta",
                        "proceder",
                        "continuar",
                        "adelante",
                        "confirmo",
                    ]
                ):
                    conversation.complete_questionnaire()
                    # Generar propuesta final
                    proposal = questionnaire_service.generate_proposal(conversation)
                    return questionnaire_service.format_proposal_summary(
                        proposal, conversation.id
                    )
                else:
                    # El usuario quiere proporcionar información adicional
                    return self._handle_additional_information(
                        conversation, user_message
                    )

            # Verificar si es momento de mostrar un resumen intermedio
            answers_count = len(conversation.questionnaire_state.answers)
            if (
                answers_count > 0
                and answers_count % 5 == 0
                and not getattr(conversation.questionnaire_state, "last_summary", 0)
                == answers_count
            ):
                # Almacenar que ya mostramos resumen para este número de respuestas
                conversation.questionnaire_state.last_summary = answers_count
                return questionnaire_service.generate_interim_summary(conversation)

            # Proceder con la siguiente pregunta del cuestionario
            if next_question:
                # Determinar si debemos sugerir carga de documentos
                document_suggestion = ""
                if self.should_suggest_document(next_question.get("id", "")):
                    document_suggestion = questionnaire_service.suggest_document_upload(
                        next_question.get("id", "")
                    )

                # Obtener un dato interesante relevante
                interesting_fact = questionnaire_service.get_random_fact(
                    conversation.questionnaire_state.sector,
                    conversation.questionnaire_state.subsector,
                )

                # Comentario sobre respuesta anterior (simplificado)
                previous_comment = "Gracias por su respuesta."

                # Preparar el contexto de la pregunta
                question_context = next_question.get("explanation", "")

                # Preparar opciones si es múltiple elección
                options = None
                if (
                    next_question.get("type") in ["multiple_choice", "multiple_select"]
                    and "options" in next_question
                ):
                    options = next_question["options"]

                # Formatear la respuesta según la estructura definida
                response = self.format_response_with_question(
                    previous_comment,
                    interesting_fact,
                    question_context,
                    next_question.get("text", ""),
                    options,
                )

                # Añadir sugerencia de documento si corresponde
                if document_suggestion:
                    response = f"{response}\n\n{document_suggestion}"

                # Actualizar la pregunta actual
                conversation.questionnaire_state.current_question_id = (
                    next_question.get("id", "")
                )

                return response

        # Si el cuestionario está completo, manejar preguntas sobre la propuesta
        if conversation.is_questionnaire_completed():
            # Preparar los mensajes para el modelo
            messages = [
                {"role": "system", "content": settings.SYSTEM_PROMPT},
                {
                    "role": "system",
                    "content": "El usuario ya ha completado el cuestionario y se le ha presentado una propuesta. Responde a sus preguntas adicionales sobre la propuesta, manteniendo un tono profesional y ofreciendo detalles técnicos cuando sea necesario.",
                },
            ]

            # Añadir parte del historial reciente para contexto
            recent_messages = [
                msg
                for msg in conversation.messages[-6:]
                if msg.role in ["user", "assistant"]
            ]
            for msg in recent_messages:
                messages.append({"role": msg.role, "content": msg.content})

            # Añadir el mensaje actual
            messages.append({"role": "user", "content": user_message})

            # Generar respuesta para preguntas post-propuesta
            return await self.generate_response(messages)

        # Fallback para otros casos
        messages = [{"role": "system", "content": settings.SYSTEM_PROMPT}]

        # Añadir parte del historial reciente
        recent_messages = [
            msg
            for msg in conversation.messages[-6:]
            if msg.role in ["user", "assistant"]
        ]
        for msg in recent_messages:
            messages.append({"role": msg.role, "content": msg.content})

        # Añadir el mensaje actual
        messages.append({"role": "user", "content": user_message})

        # Generar respuesta
        return await self.generate_response(messages)

    def _handle_diagnosis_questions(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """Maneja preguntas o comentarios sobre el diagnóstico preliminar"""
        # Preparar mensaje para el modelo
        messages = [
            {"role": "system", "content": settings.SYSTEM_PROMPT},
            {
                "role": "system",
                "content": """
            El usuario está haciendo preguntas o comentarios sobre el diagnóstico preliminar que acabas de presentar.
            Responde sus preguntas de forma informativa, centrándote en aclarar dudas técnicas o explicar mejor el proceso.
            Si el usuario parece satisfecho con el diagnóstico, pregúntale si desea proceder con la generación de una propuesta detallada.
            """,
            },
        ]

        # Añadir contexto de últimos mensajes
        recent_messages = [
            msg
            for msg in conversation.messages[-6:]
            if msg.role in ["user", "assistant"]
        ]
        for msg in recent_messages:
            messages.append({"role": msg.role, "content": msg.content})

        # Añadir mensaje actual
        messages.append({"role": "user", "content": user_message})

        # Generar respuesta
        return await self.generate_response(messages)

    def _handle_additional_information(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """Procesa información adicional proporcionada después de la confirmación"""
        # Analizar el mensaje para identificar información adicional
        additional_info = self._extract_additional_information(
            user_message, conversation
        )

        # Si se encontró información adicional, confirmarla
        if additional_info:
            # Actualizar datos en el estado del cuestionario
            for key, value in additional_info.items():
                conversation.questionnaire_state.answers[key] = value

            return f"""
        Gracias por proporcionar esta información adicional. He actualizado los siguientes datos en su perfil:

        {chr(10).join([f"- **{k}**: {v}" for k, v in additional_info.items()])}

        ¿Desea proporcionar algún otro dato o prefiere proceder con la generación de la propuesta?
        """

        # Si no se identificó información estructurada, preguntar si desea proceder
        return """
        He tomado nota de sus comentarios. ¿Desea proceder ahora con la generación de la propuesta técnica y económica detallada?

        Para continuar, simplemente indique "Generar propuesta" o proporcione cualquier información adicional específica que considere relevante.
        """

    def _extract_additional_information(
        self, message: str, conversation: Conversation
    ) -> Dict[str, Any]:
        """Extrae información adicional del mensaje del usuario"""
        additional_info = {}

        # Patrones para detectar información
        patterns = {
            "costo_agua": r"(?:costo|precio).*agua.*(\d+(?:\.\d+)?)",
            "cantidad_agua_consumida": r"(?:consumo|gasto).*agua.*(\d+(?:\.\d+)?)",
            "cantidad_agua_residual": r"(?:agua residual|efluente).*(\d+(?:\.\d+)?)",
            "presupuesto": r"(?:presupuesto|inversión).*(\d+(?:\.\d+)?)",
        }

        # Buscar coincidencias
        for key, pattern in patterns.items():
            import re

            matches = re.search(pattern, message, re.IGNORECASE)
            if matches:
                additional_info[key] = matches.group(0)

        # Detectar restricciones o preferencias generales
        if any(word in message.lower() for word in ["espacio", "área", "terreno"]):
            additional_info["restricciones"] = "Restricciones de espacio mencionadas"

        if any(
            word in message.lower()
            for word in ["tiempo", "urgente", "pronto", "rápido"]
        ):
            additional_info["tiempo_proyecto"] = "Restricciones de tiempo mencionadas"

        return additional_info

    def _determine_conversation_phase(self, conversation: Conversation) -> str:
        """Determina la fase actual de la conversación según el progreso"""
        state = conversation.questionnaire_state

        # Si el cuestionario no está activo o está completo
        if not state.active:
            if state.completed:
                return "PROPOSAL"
            else:
                return "INTRO"

        # Si no tenemos sector o subsector, estamos en la fase inicial
        if not state.sector or not state.subsector:
            return "INITIAL"

        # Determinar la fase según el número de respuestas
        answers_count = len(state.answers)

        # Restar 2 para no contar sector/subsector
        actual_answers = answers_count - 2 if answers_count >= 2 else 0

        if actual_answers < 5:
            return "DATA_COLLECTION_BASIC"
        elif actual_answers < 10:
            return "DATA_COLLECTION_TECHNICAL"
        elif actual_answers < 15:
            return "DATA_COLLECTION_ADVANCED"
        else:
            return "ANALYSIS"

    def _should_start_questionnaire(self, message: str) -> bool:
        """
        Determina si el mensaje del usuario debería iniciar el cuestionario

        Args:
            message: Mensaje del usuario

        Returns:
            bool: True si se debe iniciar el cuestionario
        """
        message = message.lower()

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
            if keyword in message:
                return True

        # Contar palabras clave relacionadas con agua
        water_keyword_count = sum(1 for keyword in water_keywords if keyword in message)

        # Si contiene al menos 2 palabras clave de agua, iniciar cuestionario
        if water_keyword_count >= 2:
            return True

        # Verificar frases explícitas junto con alguna palabra clave de agua
        for phrase in explicit_phrases:
            if phrase in message and any(
                keyword in message for keyword in water_keywords
            ):
                return True

        return False

    def _get_next_question(
        self, conversation: Conversation
    ) -> Optional[Dict[str, Any]]:
        """Obtiene la siguiente pregunta segun el estado del cuestionario"""
        state = conversation.questionnaire_state

        # Si no tenemos sector, preguntar por sector
        if not state.sector:
            return {
                "id": "sector_selection",
                "text": "¿En qué sector opera su empresa?",
                "type": "multiple_choice",
                "options": questionnaire_service.get_sectors(),
                "explanation": "El sector nos ayudará a entender mejor su contexto y necesidades específicas.",
            }

        # Si tenemos sector pero no subsector, preguntar por subsector
        if state.sector and not state.subsector:
            return {
                "id": "subsector_selection",
                "text": f"¿Cuál es el subsector específico dentro de {state.sector}?",
                "type": "multiple_choice",
                "options": questionnaire_service.get_subsectors(state.sector),
                "explanation": "Cada subsector tiene características y necesidades específicas para el tratamiento de agua.",
            }

        # Obtener las preguntas para este sector/subsector
        questions_key = f"{state.sector}_{state.subsector}"
        questions = questionnaire_service.questionnaire_data.get("questions", {}).get(
            questions_key, []
        )

        # Encontrar la siguiente pregunta no respondida
        for question in questions:
            if question["id"] not in state.answers:
                return question

        # Si todas las preguntas han sido respondidas, no hay siguiente pregunta
        return None

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
            str: Texto de la respuesta generada con formato adecuado para el frontend
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
                raw_response = response_data["choices"][0]["message"]["content"]

                # Procesar el texto para mantener un formato consistente
                processed_response = self._process_response_format(raw_response)

                return processed_response

        except Exception as e:
            logger.error(f"Error al generar respuesta con {self.provider}: {str(e)}")
            return self._get_fallback_response(messages)

    def _process_response_format(self, text: str) -> str:
        """
        Procesa el texto de respuesta para asegurar un formato adecuado para el frontend

        Args:
            text: Texto original de la respuesta

        Returns:
            str: Texto procesado con formato adecuado
        """
        # No realizamos modificaciones al texto, permitiendo el uso completo de Markdown
        # Solo realizamos algunas mejoras menor para garantizar formato consistente

        # Asegurar que los enlaces Markdown esten correctamente formateados
        text = re.sub(r"\[([^\]]+)\]\s*\(([^)]+)\)", r"[\1](\2)", text)

        # Asegurar que los encabezados tengan espacio despues del #
        for i in range(6, 0, -1):  # de h5 a h1
            heading = "#" * i
            text = re.sub(
                f"^{heading}([^#\s])", f"{heading} \\1", text, flags=re.MULTILINE
            )

        return text

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
                "¡Hola! Soy el Diseñador de Soluciones de Agua con IA de Hydrous, especializado en soluciones de reciclaje de agua. "
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

        else:
            return (
                "Gracias por tu pregunta. Para brindarte la mejor solución de reciclaje de agua, "
                "te recomendaría completar nuestro cuestionario personalizado. Así podré entender "
                "mejor tus necesidades específicas. ¿Te gustaría comenzar?"
            )


# Clase extendida del servicio de IA (se utilizará en lugar de la estándar)
class AIWithQuestionnaireService(AIService):
    """Versión del servicio de IA con funcionalidad de cuestionario integrada"""

    def __init__(self):
        super().__init__()
        # Inicializar el seguimiento de estado de las conversaciones
        self.conversation_states = {}

    async def handle_conversation(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """Maneja la conversación con enfoque guiado por cuestionario"""
        try:
            conversation_id = conversation.id

            # Inicializar estado de conversación si es nuevo
            if conversation_id not in self.conversation_states:
                self.conversation_states[conversation_id] = {
                    "current_stage": "GREETING",
                    "sector": None,
                    "subsector": None,
                    "current_question_index": -1,
                    "asked_questions": [],
                    "ready_for_proposal": False,
                }

            # Actualizar el estado con la respuesta del usuario
            self._update_conversation_state(conversation, user_message)

            # Preparar contexto para el modelo
            context = await self._prepare_context(conversation)

            # Preparar instrucción específica según la etapa
            instruction = self._get_stage_instruction(conversation_id)

            # Construir los mensajes para el modelo
            messages = [
                {"role": "system", "content": settings.SYSTEM_PROMPT},
                {"role": "system", "content": context},
                {"role": "system", "content": instruction},
            ]

            # Incluir historial de mensajes relevante
            recent_messages = self._get_recent_messages(conversation)
            messages.extend(recent_messages)

            # Incluir el mensaje actual del usuario
            messages.append({"role": "user", "content": user_message})

            # Generar respuesta
            response = await self.generate_response(messages, temperature=0.7)

            # Verificar si debemos avanzar a la siguiente etapa
            self._update_stage_if_needed(conversation_id, response)

            return response

        except Exception as e:
            logger.error(f"Error al manejar la conversación: {str(e)}")
            # Fallback a respuesta simple en caso de error
            return "Lo siento, tuve un problema procesando tu mensaje. ¿Podrías reformularlo o intentar de nuevo?"

    def generate_final_confirmation(self, conversation: Conversation) -> str:
        """Genera un mensaje de confirmación final antes de generar la propuesta"""
        state = conversation.questionnaire_state
        answers = state.answers

        confirmation = f"""
        # Confirmación Final antes de Generar Propuesta

        Gracias por proporcionar información sobre su proyecto de tratamiento de agua para {state.sector} - {state.subsector}. Antes de proceder con la generación de la propuesta técnica y económica detallada, me gustaría verificar lo siguiente:

        ## Información Clave Recopilada
        """

        # Lista de verificación de datos críticos
        essential_data = [
            ("nombre_empresa", "Nombre de la empresa/proyecto"),
            ("ubicacion", "Ubicación"),
            ("costo_agua", "Costo actual del agua"),
            ("cantidad_agua_consumida", "Consumo de agua"),
            ("cantidad_agua_residual", "Generación de agua residual"),
        ]

        # Verificar cuáles tenemos y cuáles faltan
        have_data = []
        missing_data = []

        for key, label in essential_data:
            if key in answers and answers[key]:
                have_data.append(f"✅ **{label}**: {answers[key]}")
            else:
                missing_data.append(f"❌ **{label}**: Información no proporcionada")

        # Información técnica específica según sector
        if state.subsector == "Textil":
            tech_data = [
                ("parametros_agua", "Parámetros del agua (pH, DQO, color, etc.)"),
                ("objetivo_reuso", "Objetivos de reúso del agua tratada"),
                (
                    "sistema_existente",
                    "Información sobre sistema existente (si aplica)",
                ),
            ]
        else:
            tech_data = [
                ("parametros_agua", "Parámetros del agua (pH, DQO, SST, etc.)"),
                ("objetivo_reuso", "Objetivos de reúso del agua tratada"),
                (
                    "sistema_existente",
                    "Información sobre sistema existente (si aplica)",
                ),
            ]

        # Verificar información técnica
        for key, label in tech_data:
            if key in answers and answers[key]:
                if (
                    key == "parametros_agua"
                    and isinstance(answers[key], dict)
                    and answers[key]
                ):
                    params = ", ".join([f"{k}: {v}" for k, v in answers[key].items()])
                    have_data.append(f"✅ **{label}**: {params}")
                else:
                    have_data.append(f"✅ **{label}**: Proporcionado")
            else:
                missing_data.append(
                    f"⚠️ **{label}**: Información no proporcionada (recomendable pero no crítica)"
                )

        # Añadir datos disponibles
        if have_data:
            confirmation += (
                """
        ### Información Disponible:
    """
                + "\n".join(have_data)
                + "\n"
            )

        # Añadir datos faltantes y recomendaciones
        if missing_data:
            confirmation += (
                """
    ### Información Faltante:
    """
                + "\n".join(missing_data)
                + "\n"
            )

            confirmation += """
        ### Recomendaciones:
        - Los datos faltantes marcados con ❌ son importantes para generar una propuesta precisa
        - La información marcada con ⚠️ mejoraría la calidad de la propuesta, pero no es crítica
        - Puede proporcionar esta información ahora o podemos proceder con estimaciones basadas en estándares de la industria
    """

        # Suposiciones que se harán
        confirmation += """
        ## Suposiciones para la Propuesta

        Para generar la propuesta, se utilizarán las siguientes suposiciones donde falte información específica:
    """

        assumptions = []

        if "parametros_agua" not in answers or not isinstance(
            answers["parametros_agua"], dict
        ):
            if state.subsector == "Textil":
                assumptions.append(
                    "- Se utilizarán valores típicos de DQO (800-1,500 mg/L), SST (200-600 mg/L) y pH (6.0-9.0) para efluentes textiles"
                )
            elif state.subsector == "Alimentos y Bebidas":
                assumptions.append(
                    "- Se utilizarán valores típicos de DQO (1,200-3,000 mg/L), DBO (600-1,800 mg/L) y SST (400-800 mg/L) para el sector alimentario"
                )
            else:
                assumptions.append(
                    "- Se utilizarán parámetros estándar para aguas residuales industriales de su sector"
                )

        if "costo_agua" not in answers:
            assumptions.append("- Se asumirá un costo promedio del agua para su región")

        if not assumptions:
            assumptions.append(
                "- La propuesta se basará exclusivamente en la información proporcionada sin suposiciones significativas"
            )

        confirmation += "\n".join(assumptions) + "\n"

        # Preguntas finales antes de proceder
        confirmation += """
        ## Preguntas Finales

        Antes de proceder con la generación de la propuesta:

        1. ¿Desea proporcionar alguna información adicional que considere relevante?
        2. ¿Hay algún aspecto específico que le gustaría que enfatizáramos en la propuesta?
        3. ¿Tiene alguna restricción particular de espacio, presupuesto o tiempo de implementación?

        Por favor, responda a estas preguntas o simplemente indique "Generar propuesta" si desea proceder con la información actual.
        """

        return confirmation

    def _update_conversation_state(
        self, conversation: Conversation, user_message: str
    ) -> None:
        """Actualiza el estado del cuestionario basado en la respuesta del usuario"""
        state = conversation.questionnaire_state

        # Si hay una pregunta actual, procesar la respuesta
        if state.current_question_id:
            # Si es selección de sector
            if state.current_question_id == "sector_selection":
                sector = self._extract_sector(user_message)
                if sector:
                    state.sector = sector
                    state.answers[state.current_question_id] = sector

            # Si es selección de subsector
            elif state.current_question_id == "subsector_selection":
                subsector = self._extract_subsector(user_message, state.sector)
                if subsector:
                    state.subsector = subsector
                    state.answers[state.current_question_id] = subsector

            # Para cualquier otra pregunta, guardar la respuesta directamente
            else:
                state.answers[state.current_question_id] = user_message

    def _extract_sector(self, message: str) -> Optional[str]:
        """Extrae el sector industrial de la respuesta del usuario"""
        message = message.lower()
        sectors = ["industrial", "comercial", "municipal", "residencial"]

        # Verificar respuesta numérica (1-4)
        if message.strip() in ["1", "2", "3", "4"]:
            index = int(message.strip()) - 1
            if 0 <= index < len(sectors):
                return sectors[index].capitalize()

        # Buscar coincidencia textual
        for i, sector in enumerate(sectors, 1):
            if sector in message:
                return sector.capitalize()

        return None

    def _extract_subsector(self, message: str, sector: str) -> Optional[str]:
        """Extrae el subsector de la respuesta del usuario"""
        message = message.lower()

        # Obtener subsectores para el sector seleccionado
        subsectors = questionnaire_service.get_subsectors(sector)

        # Verificar respuesta numérica
        if message.strip().isdigit():
            index = int(message.strip()) - 1
            if 0 <= index < len(subsectors):
                return subsectors[index]

        # Buscar coincidencia textual
        for subsector in subsectors:
            if subsector.lower() in message:
                return subsector

        return None

    async def _prepare_context(self, conversation: Conversation) -> str:
        """Prepara el contexto relevante para el modelo"""
        conversation_id = conversation.id
        state = self.conversation_states[conversation_id]

        context_parts = []

        # Incluir documentos si existen
        try:
            from app.services.document_service import document_service

            documents_context = await document_service.get_document_insights_summary(
                conversation_id
            )
            if documents_context:
                context_parts.append(
                    f"INFORMACIÓN DE DOCUMENTOS PROPORCIONADOS:\n{documents_context}"
                )
        except Exception as e:
            logger.warning(f"Error al obtener contexto de documentos: {str(e)}")

        # Incluir contexto según la etapa
        if (
            state["current_stage"] == "QUESTIONNAIRE"
            and state["sector"]
            and state["subsector"]
        ):
            # Obtener información de las preguntas
            questions = self._get_questions_for_sector_subsector(
                state["sector"], state["subsector"]
            )

            if state["current_question_index"] < len(questions):
                current_question = questions[state["current_question_index"]]

                # Incluir la pregunta actual y su contexto
                question_context = f"PREGUNTA ACTUAL:\n"
                question_context += f"ID: {current_question.get('id', '')}\n"
                question_context += f"Texto: {current_question.get('text', '')}\n"

                if current_question.get("explanation"):
                    question_context += (
                        f"Explicación: {current_question.get('explanation')}\n"
                    )

                if (
                    current_question.get("type")
                    in ["multiple_choice", "multiple_select"]
                    and "options" in current_question
                ):
                    question_context += "Opciones:\n"
                    for i, option in enumerate(current_question["options"], 1):
                        question_context += f"{i}. {option}\n"

                context_parts.append(question_context)

                # Añadir un dato interesante relevante
                interesting_fact = questionnaire_service.get_random_fact(
                    state["sector"], state["subsector"]
                )
                if interesting_fact:
                    context_parts.append(
                        f"DATO INTERESANTE PARA COMPARTIR:\n{interesting_fact}"
                    )

        # Para etapa de diagnóstico o propuesta, incluir resumen de respuestas
        if state["current_stage"] in ["DIAGNOSIS", "PROPOSAL"]:
            answers_summary = self._generate_answers_summary(conversation)
            context_parts.append(
                f"RESUMEN DE INFORMACIÓN RECOPILADA:\n{answers_summary}"
            )

        return "\n\n".join(context_parts)

    def _get_stage_instruction(self, conversation_id: str) -> str:
        """Obtiene instrucción específica para la etapa actual"""
        state = self.conversation_states[conversation_id]
        current_stage = state["current_stage"]

        if current_stage == "GREETING":
            return """
            INSTRUCCIÓN: Inicia la conversación con el saludo estándar indicado en tu configuración. 
            Preséntate como el Diseñador de Soluciones de Agua con IA de Hydrous y explica tu propósito.
            Concluye preguntando al usuario en qué sector opera su empresa, proporcionando las opciones numeradas:
            1. Industrial
            2. Comercial
            3. Municipal
            4. Residencial
            
            IMPORTANTE: Asegúrate de SOLO preguntar por el sector en este mensaje, sin formular preguntas adicionales.
            """

        elif current_stage == "SECTOR":
            return """
            INSTRUCCIÓN: El usuario está respondiendo a la pregunta sobre su sector. 
            Agradece su respuesta y pregunta por el subsector específico dentro del sector indicado.
            Proporciona las opciones numeradas para que pueda seleccionar fácilmente.
            
            IMPORTANTE: SOLO pregunta por el subsector en este mensaje, sin añadir preguntas adicionales.
            """

        elif current_stage == "SUBSECTOR":
            return """
            INSTRUCCIÓN: El usuario está respondiendo a la pregunta sobre su subsector.
            Agradece su respuesta y comienza el cuestionario específico para su sector/subsector.
            Formula ÚNICAMENTE la primera pregunta del cuestionario correspondiente.
            
            Incluye:
            1. Una breve introducción al cuestionario
            2. Un dato interesante relacionado con su industria
            3. La explicación de por qué esta primera pregunta es importante
            4. La pregunta claramente formulada (con opciones numeradas si aplica)
            
            IMPORTANTE: SOLO UNA pregunta por mensaje.
            """

        elif current_stage == "QUESTIONNAIRE":
            return """
            INSTRUCCIÓN: El usuario está respondiendo al cuestionario.
            Agradece su respuesta a la pregunta anterior y formula ÚNICAMENTE la siguiente pregunta del cuestionario.
            
            Incluye:
            1. Un breve comentario sobre su respuesta anterior
            2. Un dato interesante relacionado con la industria o el tema de la pregunta
            3. La explicación de por qué esta pregunta es importante
            4. La pregunta claramente formulada (con opciones numeradas si aplica)
            
            IMPORTANTE: SOLO UNA pregunta por mensaje. No avances a la siguiente hasta recibir respuesta.
            """

        elif current_stage == "DIAGNOSIS":
            return """
            INSTRUCCIÓN: El cuestionario ha sido completado. Presenta un diagnóstico preliminar basado en la información recopilada.
            
            Incluye:
            1. Un agradecimiento por completar el cuestionario
            2. Un resumen de los datos clave proporcionados
            3. Identificación de factores críticos basados en sus respuestas
            4. Un diagnóstico preliminar de sus necesidades de tratamiento de agua
            5. Un esquema general de las etapas de tratamiento recomendadas
            
            Concluye preguntando si desea proceder con la generación de una propuesta detallada.
            """

        elif current_stage == "PROPOSAL":
            return """
            INSTRUCCIÓN: Genera una propuesta completa siguiendo el formato oficial de Hydrous:
            
            1. Introducción a Hydrous Management Group
            2. Antecedentes del Proyecto (resumir información del cliente)
            3. Objetivo del Proyecto
            4. Supuestos clave de diseño y comparación con estándares de la industria
            5. Diseño de procesos y alternativas de tratamiento
            6. Equipo y tamaño sugeridos
            7. Estimación de CAPEX y OPEX
            8. Análisis del retorno de la inversión (ROI)
            9. Preguntas y respuestas
            
            Incluye un enlace para descargar la propuesta en PDF y un descargo de responsabilidad.
            """

        else:  # FOLLOWUP
            return """
            INSTRUCCIÓN: Responde a las preguntas adicionales del usuario sobre la propuesta.
            Mantén un tono profesional y preciso, ofreciendo información adicional cuando sea posible.
            Si el usuario solicita modificaciones, explica qué aspectos pueden ajustarse y cómo afectarían al diseño o los costos.
            """

    def _get_questions_for_sector_subsector(
        self, sector: str, subsector: str
    ) -> List[Dict[str, Any]]:
        """Obtiene las preguntas para un sector/subsector específico"""
        # Construir la clave para acceder a las preguntas
        questions_key = f"{sector}_{subsector}"

        # Obtener las preguntas del cuestionario
        return questionnaire_service.questionnaire_data.get("questions", {}).get(
            questions_key, []
        )

    def _get_recent_messages(self, conversation: Conversation) -> List[Dict[str, str]]:
        """Obtiene los mensajes recientes de la conversación"""
        # Incluir solo los últimos 8 mensajes para mantener el contexto relevante
        recent_messages = []
        messages = [
            msg for msg in conversation.messages if msg.role in ["user", "assistant"]
        ]

        for msg in messages[-8:]:
            recent_messages.append({"role": msg.role, "content": msg.content})

        return recent_messages

    def _generate_answers_summary(self, conversation: Conversation) -> str:
        """Genera un resumen de las respuestas proporcionadas"""
        answers = conversation.questionnaire_state.answers
        sector = conversation.questionnaire_state.sector
        subsector = conversation.questionnaire_state.subsector

        if not answers:
            return "No se ha recopilado información suficiente."

        summary = (
            f"Sector: {sector}\nSubsector: {subsector}\n\nRespuestas proporcionadas:\n"
        )

        # Obtener preguntas para este sector/subsector
        questions_key = f"{sector}_{subsector}"
        questions = questionnaire_service.questionnaire_data.get("questions", {}).get(
            questions_key, []
        )

        # Crear un mapeo de ID a texto de pregunta
        question_texts = {q["id"]: q["text"] for q in questions}

        # Añadir cada respuesta al resumen
        for question_id, answer in answers.items():
            question_text = question_texts.get(question_id, question_id)
            summary += f"- {question_text}: {answer}\n"

        return summary

    def _update_stage_if_needed(self, conversation_id: str, response: str) -> None:
        """Actualiza la etapa si la respuesta indica que debemos avanzar"""
        state = self.conversation_states[conversation_id]

        # Avanzar de diagnóstico a propuesta si el usuario lo solicita
        if state["current_stage"] == "DIAGNOSIS" and any(
            keyword in response.lower()
            for keyword in [
                "generar propuesta",
                "ver propuesta",
                "proceder",
                "continuar",
            ]
        ):
            state["current_stage"] = "PROPOSAL"

        # Avanzar de propuesta a seguimiento después de mostrar la propuesta completa
        elif (
            state["current_stage"] == "PROPOSAL" and "PROPUESTA DE SOLUCIÓN" in response
        ):
            state["current_stage"] = "FOLLOWUP"

    # Método para completar flujo de cuestionario
    def complete_questionnaire(self, conversation: Conversation) -> None:
        """Marca el cuestionario como completado y actualiza el estado"""
        conversation_id = conversation.id
        if conversation_id in self.conversation_states:
            self.conversation_states[conversation_id]["current_stage"] = "PROPOSAL"
            self.conversation_states[conversation_id]["ready_for_proposal"] = True

        # Actualizar también el estado en el objeto conversación
        conversation.complete_questionnaire()


# Instancia global del servicio
ai_service = AIWithQuestionnaireService()
