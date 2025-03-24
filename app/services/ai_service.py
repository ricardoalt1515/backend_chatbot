import logging
import re
from typing import List, Dict, Any, Optional, Tuple
import httpx
import time
import json
from datetime import datetime
import asyncio

from app.config import settings
from app.models.conversation import Conversation
from app.services.questionnaire_service import questionnaire_service

# Intentar importar las bibliotecas de Gemini
try:
    import google.generativeai as genai
    from google.generativeai import types as gemini_types

    gemini_available = True
except ImportError:
    gemini_available = False
    logging.warning("google-generativeai no está instalado. No se podrá usar Gemini.")

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
        super().__init__()
        # Inicializar el atributo questionnaire_service
        self.questionnaire_service = questionnaire_service
        self.provider = settings.AI_PROVIDER

        # En caso de que las bibliotecas no estén instaladas,
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

        elif self.provider == "gemini":
            if not settings.GEMINI_API_KEY:
                logger.warning(
                    "GEMINI_API_KEY no configurada. Las llamadas a la API fallarán."
                )
            self.api_key = settings.GEMINI_API_KEY
            self.model = settings.GEMINI_MODEL
            self.api_url = None  # No usamos URL directamente con Gemini

            # Inicializar cliente de Gemini si está disponible
            if gemini_available:
                genai.configure(api_key=self.api_key)
                self.gemini_client = genai
            else:
                logger.error(
                    "No se pudo importar google.generativeai. Instala la biblioteca con pip install google-generativeai"
                )
                self.gemini_client = None

        else:
            # Si el proveedor no está configurado correctamente, usamos un modo de "fallback"
            logger.warning(
                f"Proveedor de IA no soportado: {self.provider}. Usando respuestas pre-configuradas."
            )
            self.api_key = None
            self.model = None
            self.api_url = None

        # Atributos para mantener el contexto entre llamadas
        self.current_sector = None
        self.current_subsector = None

    async def handle_conversation(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Maneja la conversación del usuario y genera una respuesta
        """
        try:
            # Si el cuestionario está completado y el usuario pide el PDF
            if conversation.is_questionnaire_completed() and self._is_pdf_request(
                user_message
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

            # Construir mensajes para la API - OPTIMIZADO PARA REDUCIR TOKENS
            messages = [
                {"role": "system", "content": settings.SYSTEM_PROMPT},
            ]

            # Añadir contexto relevante de manera concisa
            context = self._create_minimal_context(conversation)
            if context:
                messages.append({"role": "system", "content": context})

            # Añadir solo los últimos N mensajes del historial para limitar tokens
            recent_messages = self._get_recent_message_history(
                conversation, max_messages=6
            )
            messages.extend(recent_messages)

            # Si es posible, agregar el último intercambio explícitamente
            if len(recent_messages) < 2:
                messages.append({"role": "user", "content": user_message})

            # Dejar que el modelo genere la respuesta completa
            response = await self.generate_response(messages)

            # Actualizar el estado del cuestionario basado en la respuesta generada
            self._update_questionnaire_state(conversation, user_message, response)

            return response

        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar su consulta. Por favor, inténtelo de nuevo."

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Genera una respuesta utilizando el proveedor de IA configurado
        Con manejo mejorado de errores de límite de tokens
        """
        max_retries = 2
        retry_count = 0
        reduced_context = False

        while retry_count <= max_retries:
            try:
                # Verificar si tenemos conexión con la API
                if not self.api_key:
                    return self._get_fallback_response(messages)

                # Si el proveedor es Gemini, usamos su API específica
                if (
                    self.provider == "gemini"
                    and gemini_available
                    and self.gemini_client
                ):
                    try:
                        # Extraer instrucciones del sistema y convertir mensajes al formato de Gemini
                        system_instruction = None
                        gemini_messages = []

                        for msg in messages:
                            if msg["role"] == "system":
                                # Gemini maneja las instrucciones del sistema de forma separada
                                # Si hay múltiples mensajes del sistema, usamos el último
                                system_instruction = gemini_types.Part.from_text(
                                    text=msg["content"]
                                )
                            else:
                                # Gemini usa "user" y "model" en lugar de "user" y "assistant"
                                gemini_role = (
                                    "user" if msg["role"] == "user" else "model"
                                )
                                gemini_messages.append(
                                    gemini_types.Content(
                                        role=gemini_role,
                                        parts=[
                                            gemini_types.Part.from_text(
                                                text=msg["content"]
                                            )
                                        ],
                                    )
                                )

                        # Configurar la generación
                        generate_config = gemini_types.GenerateContentConfig(
                            temperature=temperature,
                            max_output_tokens=max_tokens or 8192,
                            response_mime_type="text/plain",
                        )

                        # Agregar instrucción del sistema si existe
                        if system_instruction:
                            generate_config.system_instruction = [system_instruction]

                        # Hacer la solicitud a Gemini
                        model = self.gemini_client.models.get_model(self.model)
                        response = model.generate_content(
                            contents=gemini_messages,
                            generation_config=generate_config,
                        )

                        # Manejar la respuesta
                        if hasattr(response, "text"):
                            return response.text
                        elif hasattr(response, "parts") and response.parts:
                            return response.parts[0].text
                        else:
                            logger.error("Formato de respuesta de Gemini no reconocido")
                            return self._get_fallback_response(messages)

                    except Exception as e:
                        logger.error(f"Error con la API de Gemini: {str(e)}")
                        retry_count += 1
                        await asyncio.sleep(2)  # Esperar antes de reintentar
                        continue

                # Para los proveedores OpenAI/Groq, usamos el método existente
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

    # El resto de los métodos existentes de la clase se mantienen igual...
    def _extract_wait_time(self, error_message: str) -> Optional[int]:
        """Extrae el tiempo de espera sugerido del mensaje de error"""
        match = re.search(r"Please try again in (\d+\.?\d*)s", error_message)
        if match:
            try:
                return (
                    int(float(match.group(1))) + 1
                )  # Añadir 1 segundo extra por seguridad
            except:
                return None
        return None

    def _reduce_context(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Reduce drásticamente el contexto para manejar errores de límite de contexto"""
        # Conservar siempre el mensaje del sistema
        system_messages = [msg for msg in messages if msg.get("role") == "system"]
        system_message = (
            system_messages[0]
            if system_messages
            else {"role": "system", "content": "Eres un asistente de Hydrous AI."}
        )

        # Conservar solo el último mensaje del usuario
        user_messages = [msg for msg in messages if msg.get("role") == "user"]
        last_user_message = user_messages[-1] if user_messages else None

        # Construir mensajes reducidos
        reduced_messages = [system_message]
        if last_user_message:
            reduced_messages.append(last_user_message)

        return reduced_messages

    def _create_minimal_context(self, conversation: Conversation) -> str:
        """Crea un contexto mínimo con solo la información esencial"""
        state = conversation.questionnaire_state
        context = ""

        # Solo incluir datos absolutamente esenciales
        if state.sector:
            context += f"Sector: {state.sector}. "
        if state.subsector:
            context += f"Subsector: {state.subsector}. "

        # Incluir nombre del usuario y ubicación si están disponibles (son importantes)
        if "nombre_empresa" in state.answers:
            context += f"Nombre: {state.answers['nombre_empresa']}. "
        if "ubicacion" in state.answers:
            context += f"Ubicación: {state.answers['ubicacion']}. "

        return context.strip()

    def _get_recent_message_history(
        self, conversation: Conversation, max_messages: int = 6
    ) -> List[Dict[str, str]]:
        """Obtiene los mensajes más recientes del historial, limitando la cantidad"""
        recent_messages = []
        message_count = 0

        # Comenzar desde el final (mensajes más recientes)
        for msg in reversed(conversation.messages):
            if msg.role in ["user", "assistant"]:
                recent_messages.insert(0, {"role": msg.role, "content": msg.content})
                message_count += 1
                if message_count >= max_messages:
                    break

        return recent_messages

    def _get_emergency_response(self) -> str:
        """Proporciona una respuesta de emergencia cuando todo lo demás falla"""
        return """
Lo siento, estamos experimentando una alta demanda en este momento y no puedo procesar su consulta completa.

Por favor, permítame hacerle preguntas más breves para continuar con nuestra conversación de manera más eficiente:

**PREGUNTA: ¿Podría indicarme brevemente cuál es su necesidad principal respecto al tratamiento de agua?**

1. Reciclaje de agua industrial
2. Cumplimiento normativo
3. Reducción de costos operativos
4. Otra (por favor especifique brevemente)
"""

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

    def _is_pdf_request(self, message: str) -> bool:
        """
        Determina si el mensaje del usuario es una solicitud de PDF
        """
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
            "obtener",
            "enviar",
            "quiero el pdf",
            "dame la propuesta",
            "ver el documento",
        ]

        return any(keyword in message for keyword in pdf_keywords)

    def _update_questionnaire_state(
        self, conversation: Conversation, user_message: str, response: str
    ) -> None:
        """
        Actualiza el estado del cuestionario basado en la respuesta del usuario y la respuesta generada.
        Método simplificado que detecta avances en el cuestionario.
        """
        state = conversation.questionnaire_state

        # Iniciar cuestionario si no está activo
        if not state.active and not state.completed:
            state.active = True

        # Detectar sector/subsector en la respuesta generada o mensaje del usuario
        if not state.sector:
            sectors = ["Industrial", "Comercial", "Municipal", "Residencial"]
            for sector in sectors:
                if (
                    sector.lower() in user_message.lower()
                    or sector.lower() in response.lower()
                ):
                    state.sector = sector
                    state.answers["sector_selection"] = sector
                    break

        if state.sector and not state.subsector:
            # Usar el servicio importado directamente:
            subsectors = self.questionnaire_service.get_subsectors(state.sector)
            for subsector in subsectors:
                if (
                    subsector.lower() in user_message.lower()
                    or subsector.lower() in response.lower()
                ):
                    state.subsector = subsector
                    state.answers["subsector_selection"] = subsector
                    break

        # Detectar finalización del cuestionario (si la respuesta contiene una propuesta)
        proposal_indicators = [
            "Propuesta Preliminar",
            "Diagnóstico Inicial",
            "Tren de Tratamiento",
            "Costos Estimados",
            "CAPEX",
            "OPEX",
            "Beneficios Potenciales",
        ]

        if sum(1 for indicator in proposal_indicators if indicator in response) >= 3:
            state.completed = True
            state.active = False

        # Actualizar el contador de preguntas respondidas si existe el atributo
        if hasattr(state, "questions_answered"):
            # Solo incrementar si parece que la respuesta contiene una nueva pregunta
            if "PREGUNTA:" in response or "pregunta:" in response.lower():
                state.questions_answered += 1


# Instancia global del servicio
ai_service = AIService()
