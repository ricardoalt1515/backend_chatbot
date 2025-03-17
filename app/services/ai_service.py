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
            if conversation_id not in self.collected_info:
                self.collected_info[conversation_id] = {
                    "sector": None,
                    "subsector": None,
                    "key_parameters": {},
                    "has_sufficient_info": False,
                    "documents_analyzed": [],
                }

            # Verificar si debemos iniciar cuestionario basado en la intención del usuario
            should_start = self._detect_questionnaire_intent(user_message)
            if should_start and not conversation.is_questionnaire_active():
                conversation.start_questionnaire()

            # Obtener información de documentos si existen
            document_insights = await self._get_document_insights(conversation.id)

            # Detectar sector/subsector en la conversación
            sector, subsector = self._detect_sector_subsector(conversation)

            # Actualizar estado del cuestionario con información detectada
            if sector and not conversation.questionnaire_state.sector:
                conversation.questionnaire_state.sector = sector
                conversation.questionnaire_state.answers["sector_selection"] = sector

            if sector and subsector and not conversation.questionnaire_state.subsector:
                conversation.questionnaire_state.subsector = subsector
                conversation.questionnaire_state.answers["subsector_selection"] = (
                    subsector
                )

            # Preparar mensajes para enviar al modelo
            messages = [{"role": "system", "content": settings.SYSTEM_PROMPT}]

            # Añadir información de documentos si existe
            if document_insights:
                messages.append(
                    {
                        "role": "system",
                        "content": f"INFORMACIÓN DE DOCUMENTOS:\n{document_insights}",
                    }
                )

            # Añadir información sobre sector/subsector detectados
            if sector:
                context = f"El usuario pertenece al sector {sector}"
                if subsector:
                    context += f", subsector {subsector}"

                # Añadir preguntas relevantes como contexto
                relevant_questions = self._get_relevant_questions(sector, subsector)
                if relevant_questions:
                    context += f"\n\nPREGUNTAS RELEVANTES PARA ESTE SECTOR:\n{relevant_questions}"

                messages.append({"role": "system", "content": context})

            # Añadir el historial reciente de mensajes (últimos 8 intercambios)
            recent_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in conversation.messages[
                    -16:
                ]  # Máximo 8 intercambios (16 mensajes)
                if msg.role in ["user", "assistant"]  # Solo mensajes visibles
            ]

            # Añadir estos mensajes recientes
            messages.extend(recent_messages)

            # Si no está el mensaje del usuario en los mensajes recientes, añadirlo
            if not recent_messages or recent_messages[-1]["role"] != "user":
                messages.append({"role": "user", "content": user_message})

            # Generar respuesta
            response = await self.generate_response(messages)

            # Actualizar información recopilada
            self._update_collected_info(conversation, user_message, response)

            # Verificar si tenemos suficiente información para una propuesta
            info = self.collected_info[conversation_id]
            if self._check_sufficient_info(info) and not info["has_sufficient_info"]:
                info["has_sufficient_info"] = True
                # Podríamos sugerir generar propuesta en futuras interacciones

            return response

        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return f"Lo siento, ha ocurrido un error inesperado. Por favor, intenta de nuevo. Error: {str(e)[:100]}..."

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
