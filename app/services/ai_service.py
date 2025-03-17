import logging
import re
from typing import List, Dict, Any, Optional, Tuple
import httpx
import time

from app.config import settings
from app.models.conversation import Conversation
from app.services.questionnaire_service import questionnaire_service

# Intento importar el contador de tokens si está disponible
try:
    from app.utils.token_counter import count_tokens, estimate_cost

    token_counter_available = True
except ImportError:
    token_counter_available = False

logger = logging.getLogger("hydrous-backend")


class AIService:
    """Servicio simplificado para interactuar con modelos de IA"""

    def __init__(self):
        self.provider = settings.AI_PROVIDER

        # Configuración básica según el proveedor
        if self.provider == "groq":
            if not settings.GROQ_API_KEY:
                logger.warning(
                    "GROQ_API_KEY no configurada. Las llamadas a la API fallarán."
                )
            self.api_key = settings.GROQ_API_KEY
            self.model = settings.GROQ_MODEL
            self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        else:  # openai por defecto
            if not settings.OPENAI_API_KEY:
                logger.warning(
                    "OPENAI_API_KEY no configurada. Las llamadas a la API fallarán."
                )
            self.api_key = settings.OPENAI_API_KEY
            self.model = settings.OPENAI_MODEL
            self.api_url = "https://api.openai.com/v1/chat/completions"

        # Registro de información recopilada por conversación
        self.collected_info = {}

    async def handle_conversation(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """Maneja la conversación con un enfoque natural y conversacional"""
        try:
            conversation_id = conversation.id

            # Inicializar seguimiento de información para esta conversación
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

            # Preparar instruccion especifica segun la etapa
            instruction = self._get_stage_instruction(conversation_id)

            # Construir los mensajes para el modelo
            message = [
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
            logger.error(f"Erro al manejar la conversacion: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar tu mensaje. Por favor, intente nuevamente"

    def _update_conversation_state(
        self, conversation: Conversation, user_message: str
    ) -> None:
        """Actualiza el estado de la conversacion basado en la respuesta del usuario"""
        conversation_id = conversation.id
        state = self.conversation_states[conversation_id]
        current_stage = state["current_stage"]

        # Procesar respuesta según la etapa actual
        if current_stage == "GREETING":
            # Si el usuario responde al saludo, avanzar a sector
            state["current_stage"] = "SECTOR"

        elif current_stage == "SECTOR":
            # Extraer sector de la respuesta
            sector = self._extract_sector(user_message)
            if sector:
                state["sector"] = sector
                conversation.questionnaire_state.sector = sector
                state["current_stage"] = "SUBSECTOR"

        elif current_stage == "SUBSECTOR":
            # Extraer subsector de la respuesta
            subsector = self._extract_subsector(user_message, state["sector"])
            if subsector:
                state["subsector"] = subsector
                conversation.questionnaire_state.subsector = subsector
                state["current_stage"] = "QUESTIONNAIRE"
                state["current_question_index"] = 0

        elif current_stage == "QUESTIONNAIRE":
            # Guardar respuesta a la pregunta actual
            if state["current_question_index"] >= 0:
                questions = self._get_questions_for_sector_subsector(
                    state["sector"], state["subsector"]
                )
                if state["current_question_index"] < len(questions):
                    current_question = questions[state["current_question_index"]]
                    question_id = current_question["id"]

                    # Guardar la respuesta en el estado del cuestionario
                    conversation.questionnaire_state.answers[question_id] = user_message
                    state["asked_questions"].append(question_id)

                    # Avanzar a la siguiente pregunta
                    state["current_question_index"] += 1

                    # Si llegamos al final del cuestionario, preparar diagnóstico
                    if state["current_question_index"] >= len(questions):
                        state["current_stage"] = "DIAGNOSIS"

    def extract_sector(self, message: str) -> Optional[str]:
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

    def _detect_questionnaire_intent(self, message: str) -> bool:
        """Detecta si el usuario quiere iniciar un cuestionario o solicitar ayuda"""
        message = message.lower()
        intent_keywords = [
            "ayuda",
            "solución",
            "sistema",
            "tratamiento",
            "agua",
            "residual",
            "reciclaje",
            "propuesta",
            "necesito",
            "quiero",
            "información",
        ]

        # Si contiene al menos 2 palabras clave, consideramos que hay intención
        keyword_count = sum(1 for word in intent_keywords if word in message)
        return keyword_count >= 2

    def _detect_sector_subsector(
        self, conversation: Conversation
    ) -> Tuple[Optional[str], Optional[str]]:
        """Detecta el sector y subsector del usuario a partir de la conversación"""
        # Primero verificamos si ya están establecidos en el estado del cuestionario
        if conversation.questionnaire_state.sector:
            return (
                conversation.questionnaire_state.sector,
                conversation.questionnaire_state.subsector,
            )

        # Si no, intentamos detectarlos en los mensajes
        sectors = ["Industrial", "Comercial", "Municipal", "Residencial"]
        all_messages = " ".join(
            [msg.content for msg in conversation.messages if msg.role == "user"]
        )

        # Detectar sector
        detected_sector = None
        for sector in sectors:
            if sector.lower() in all_messages.lower():
                detected_sector = sector
                break

        # Buscar respuestas numéricas (1-4) que puedan indicar selección de sector
        if not detected_sector and len(conversation.messages) >= 2:
            for msg in reversed(conversation.messages):
                if msg.role == "user" and msg.content.strip() in ["1", "2", "3", "4"]:
                    idx = int(msg.content.strip()) - 1
                    if 0 <= idx < len(sectors):
                        detected_sector = sectors[idx]
                        break

        # Si encontramos sector, intentar detectar subsector
        detected_subsector = None
        if detected_sector:
            subsectors = questionnaire_service.get_subsectors(detected_sector)
            for subsector in subsectors:
                if subsector.lower() in all_messages.lower():
                    detected_subsector = subsector
                    break

            # Buscar respuestas numéricas que puedan indicar selección de subsector
            if not detected_subsector:
                for msg in reversed(conversation.messages):
                    if msg.role == "user" and msg.content.strip().isdigit():
                        idx = int(msg.content.strip()) - 1
                        if 0 <= idx < len(subsectors):
                            detected_subsector = subsectors[idx]
                            break

        return detected_sector, detected_subsector

    def _get_relevant_questions(
        self, sector: str, subsector: Optional[str] = None
    ) -> str:
        """Obtiene las preguntas más relevantes para el sector/subsector"""
        try:
            # Construir la clave para buscar preguntas específicas
            question_key = f"{sector}"
            if subsector:
                question_key += f"_{subsector}"

            questions = questionnaire_service.questionnaire_data.get(
                "questions", {}
            ).get(question_key, [])

            # Seleccionar solo las preguntas más importantes (máximo 5)
            key_questions = questions[:5] if questions else []

            if not key_questions:
                return ""

            # Formatear como texto
            result = ""
            for q in key_questions:
                result += f"- {q.get('text', '')}\n"

            return result

        except Exception as e:
            logger.error(f"Error al obtener preguntas relevantes: {str(e)}")
            return ""

    async def _get_document_insights(self, conversation_id: str) -> str:
        """Obtiene insights de documentos asociados a la conversación"""
        try:
            from app.services.document_service import document_service

            return await document_service.get_document_insights_summary(conversation_id)
        except Exception as e:
            logger.error(f"Error al obtener insights de documentos: {str(e)}")
            return ""

    def _update_collected_info(
        self, conversation: Conversation, user_message: str, ai_response: str
    ) -> None:
        """Actualiza la información recopilada basada en la interacción"""
        conversation_id = conversation.id
        info = self.collected_info.get(
            conversation_id,
            {
                "sector": None,
                "subsector": None,
                "key_parameters": {},
                "has_sufficient_info": False,
                "documents_analyzed": [],
            },
        )

        # Actualizar sector/subsector
        sector, subsector = self._detect_sector_subsector(conversation)
        if sector:
            info["sector"] = sector
        if subsector:
            info["subsector"] = subsector

        # Extraer parámetros clave del mensaje del usuario
        parameters = self._extract_key_parameters(user_message)
        if parameters:
            info["key_parameters"].update(parameters)

        # Verificar si la respuesta del AI indica que se ha completado el cuestionario
        completion_indicators = [
            "propuesta completa",
            "generar pdf",
            "suficiente información",
            "descargar propuesta",
        ]

        if any(indicator in ai_response.lower() for indicator in completion_indicators):
            # Marcar como completado si detectamos indicadores de finalización
            conversation.questionnaire_state.completed = True

        # Actualizar información recopilada
        self.collected_info[conversation_id] = info

    def _extract_key_parameters(self, message: str) -> Dict[str, str]:
        """Extrae parámetros clave del mensaje del usuario"""
        parameters = {}

        # Patrones para diferentes parámetros
        patterns = {
            "water_consumption": r"(\d+(?:\.\d+)?)\s*(?:m3|m³|metros cúbicos|litros)/(?:día|dia|mes)",
            "ph": r"(?:pH|PH)[:\s]+(\d+(?:\.\d+)?)",
            "dbo": r"(?:DBO|Demanda Bioquímica)[:\s]+(\d+(?:\.\d+)?)",
            "dqo": r"(?:DQO|Demanda Química)[:\s]+(\d+(?:\.\d+)?)",
            "sst": r"(?:SST|Sólidos Suspendidos)[:\s]+(\d+(?:\.\d+)?)",
        }

        for param, pattern in patterns.items():
            matches = re.findall(pattern, message, re.IGNORECASE)
            if matches:
                parameters[param] = matches[0]

        return parameters

    def _check_sufficient_info(self, info: Dict[str, Any]) -> bool:
        """Determina si tenemos suficiente información para generar una propuesta"""
        # Criterios simplificados para determinar si tenemos suficiente información
        if not info["sector"]:
            return False

        # Al menos 2 parámetros clave o documentos analizados
        if len(info["key_parameters"]) < 2 and len(info["documents_analyzed"]) == 0:
            return False

        return True

    async def generate_response(self, messages: List[Dict[str, str]]) -> str:
        """Genera respuesta usando la API del proveedor configurado"""
        try:
            # Verificar si tenemos conexión con la API
            if not self.api_key or not self.api_url:
                return "Lo siento, no puedo conectar con el servicio de IA en este momento. Por favor, verifica la configuración de las claves API."

            # Añadir instrucción para evitar respuestas vacías
            messages.append(
                {
                    "role": "system",
                    "content": """
                INSTRUCCIONES FINALES:
                1. Proporciona respuestas claras y útiles.
                2. Formula UNA SOLA pregunta a la vez.
                3. Explica brevemente por qué haces cada pregunta.
                4. Comparte datos interesantes sobre ahorro de agua cuando sea relevante.
                5. Cuando tengas suficiente información, ofrece generar una propuesta técnica.
                """,
                }
            )

            # Estimar tokens (si está disponible)
            if token_counter_available:
                try:
                    token_count = count_tokens(messages, self.model)
                    cost_estimate = estimate_cost(token_count, self.model)
                    logger.info(
                        f"Tokens enviados: {token_count} (est. costo: ${cost_estimate:.5f})"
                    )
                except Exception as e:
                    logger.warning(f"Error al contar tokens: {str(e)}")

            # Hacer solicitud a la API
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }

                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 1000,
                }

                # Intentar hasta 3 veces con tiempo de espera entre reintentos
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = await client.post(
                            self.api_url, json=payload, headers=headers
                        )

                        if response.status_code == 200:
                            response_data = response.json()

                            # Verificar que tenemos datos válidos
                            if not response_data or "choices" not in response_data:
                                logger.error(
                                    f"Respuesta de API inválida: {response_data}"
                                )
                                return "Lo siento, obtuve una respuesta inválida. Por favor, intenta de nuevo."

                            raw_response = response_data["choices"][0]["message"][
                                "content"
                            ]

                            # Verificar que tenemos una cadena válida
                            if not raw_response or not isinstance(raw_response, str):
                                logger.error(
                                    f"Contenido de respuesta inválido: {raw_response}"
                                )
                                return "Recibí una respuesta vacía. Por favor, intenta reformular tu pregunta."

                            return raw_response

                        # Manejar errores comunes
                        elif response.status_code == 401:
                            logger.error("Error de autenticación con API")
                            return "Error de autenticación con el servicio de IA. Verifica tu clave API."

                        elif response.status_code == 429:
                            wait_time = (2**attempt) + 1  # Backoff exponencial
                            logger.warning(
                                f"Rate limit alcanzado. Esperando {wait_time}s..."
                            )
                            if attempt < max_retries - 1:
                                time.sleep(wait_time)
                                continue
                            else:
                                return "El servicio de IA está experimentando mucho tráfico. Por favor, intenta más tarde."

                        else:
                            logger.error(
                                f"Error de API: {response.status_code} - {response.text}"
                            )
                            return f"Error al conectar con el servicio de IA (código {response.status_code})."

                    except httpx.ReadTimeout:
                        wait_time = (2**attempt) + 1
                        logger.warning(f"Timeout. Esperando {wait_time}s...")
                        if attempt < max_retries - 1:
                            time.sleep(wait_time)
                            continue
                        else:
                            return "El servicio de IA está tardando demasiado en responder. Por favor, intenta más tarde."

                    except Exception as e:
                        logger.error(f"Error en solicitud HTTP: {str(e)}")
                        return f"Error de conexión: {str(e)[:100]}..."

                # Si llegamos aquí, es que fallaron todos los intentos
                return "No se pudo obtener respuesta después de varios intentos. Por favor, intenta más tarde."

        except Exception as e:
            logger.error(f"Error general en generate_response: {str(e)}")
            return f"Lo siento, ocurrió un error al procesar tu solicitud: {str(e)[:100]}... Por favor, intenta de nuevo más tarde."

    def _format_question(self, question: Dict[str, Any]) -> str:
        """
        Formatea una pregunta del cuestionario con un enfoque conversacional
        siguiendo exactamente la estructura deseada.
        Este método se mantiene para compatibilidad con el código existente.
        """
        # Obtener datos básicos de la pregunta
        q_text = question.get("text", "")
        q_type = question.get("type", "text")
        q_explanation = question.get("explanation", "")

        # Iniciar con una introducción amigable
        message = ""

        # Añadir un dato interesante relacionado con el sector/subsector
        sector = getattr(self, "current_sector", None)
        subsector = getattr(self, "current_subsector", None)
        if sector and subsector:
            fact = questionnaire_service.get_random_fact(sector, subsector)
            if fact:
                message += f"*Dato interesante: {fact}*\n\n"

        # Añadir explicación de por qué esta pregunta es importante
        if q_explanation:
            message += f"{q_explanation}\n\n"

        # Destacar claramente la pregunta al final con formato específico
        message += f"**PREGUNTA: {q_text}**\n\n"

        # Añadir opciones numeradas para preguntas de selección
        if q_type in ["multiple_choice", "multiple_select"] and "options" in question:
            for i, option in enumerate(question["options"], 1):
                message += f"{i}. {option}\n"

        return message


# Clase extendida del servicio de IA (se utilizará en lugar de la estándar)
class AIWithQuestionnaireService(AIService):
    """Versión del servicio de IA con funcionalidad de cuestionario integrada"""

    def __init__(self):
        super().__init__()
        # Este constructor ahora está simplificado


# Instancia global del servicio
ai_service = AIWithQuestionnaireService()
