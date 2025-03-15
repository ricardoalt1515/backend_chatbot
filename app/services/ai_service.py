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
        Maneja la conversación delegando la lógica al modelo de IA, proporcionando
        contexto selectivo y relevante según el estado del cuestionario.

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

        # Preparar mensajes para el modelo de IA
        messages_for_ai = [
            {"role": "system", "content": settings.SYSTEM_PROMPT_WITH_QUESTIONNAIRE}
        ]

        # Añadir contexto selectivo del cuestionario según el estado actual
        if conversation.is_questionnaire_active():
            # 1. Contexto general sobre el estado actual del cuestionario
            questionnaire_context = questionnaire_service.get_questionnaire_context(
                conversation.questionnaire_state
            )
            messages_for_ai.append(
                {
                    "role": "system",
                    "content": f"ESTADO DEL CUESTIONARIO ACTUAL:\n{questionnaire_context}",
                }
            )

            # 2. Añadir la seccion especifica del cuestionario que se esta utilizando
            current_section = questionnaire_service.get_questionnaire_context(
                conversation.questionnaire_state
            )
            messages_for_ai.append(
                {
                    "role": "system",
                    "content": f"SECCION ACTUAL DEL CUESTIONARIO(SIGUE EXACTAMENTE ESTE ORDEN DE PREGUNTAS):\n{current_section}",
                }
            )

            # 3. Si estamos cerca de completar el cuestionario, Añadir instrucciones de diagnóstico
            if len(conversation.questionnaire_state.answers) > 5:
                messages_for_ai.append(
                    {
                        "role": "system",
                        "content": """
                    INSTRUCCIONES PARA DIAGNOSTICO PRELIMINAR:
                    A medida que recopiles mas informacion, comienza a identificar los factores claves:
                    - Alta carga organica
                    - Presencia de metales
                    - Necesidad de reutilizacion avanzada
                    - Requisitos de descarga cero

                    Si faltan datos criticos, solicita cortésmente que el usuario los obtenga (pruebas de laboratorio, mediciones de flujo).
                    Haz suposiciones razonables si no se proporcionan datos, pero dejalas claras (por ejemplo, "Suponiendo un TSS tipico de 600 mg/L para su industria...").
                    """,
                    }
                )

            # 4. Si estamos cerca de completar el cuestionario, Añadir plantilla de propuesta
            if len(conversation.questionnaire_state.answers) > 10:
                proposal_template = questionnaire_service.get_proposal_template()
                messages_for_ai.append(
                    {
                        "role": "system",
                        "content": f"FORMATO DE PROPUESTA A UTILIZAR CUANDO SE COMPLETE EL CUESTIONARIO:\n{proposal_template}",
                    }
                )

        # Si el cuestionario esta completado, incluir indicaciones para la propuesta
        if conversation.is_questionnaire_completed():
            messages_for_ai.append(
                {
                    "role": "system",
                    "content": """
                INSTRUCCIONES PARA GENERAR PROPUESTA FINAL:
                El cuestionario ha sido completado. Debes:
                1. Resumir los datos clave recopilados.
                2. Presentar un enfoque de tratamiento recomendado (pretratamiento, primario, secundario, terciario).
                3. Justificar cada etapa del tratamiento basado en los datos del usuario.
                4. Proporcionar estimaciones de CAPEX y OPEX con los descargos de responsabilidad adecuados.
                5. Incluir un analisis de ROI aproximado.
                6. Ofrecer la opcion de descargar la propuesta como PDF.

                si el usuario solicita el PDF, indicale que puede descargar la propuesta usando el enlace de descarga.
                """,
                }
            )

        # Añadir historial de mensajes (excluyendo mensajes del sistema)
        for msg in conversation.messages:
            if msg.role != "system":
                messages_for_ai.append({"role": msg.role, "content": msg.content})

        # Añadir el mensaje actual del usuario
        messages_for_ai.append({"role": "user", "content": user_message})

        # Si acabamos de iniciar el cuestionario, dar instrucciones específicas al modelo
        if should_start:
            messages_for_ai.append(
                {
                    "role": "system",
                    "content": """
                    El usuario ha mostrado interes en soluciones de tratamiento de agua. Inicia la conversacion con:
                    
                    1. El saludo estandar completo(Soy el Diseñador de Soluciones de Agua con IA de Hydrous...).
                    2. Pregunta por el sector al que pertenece su empresa (Industrial, Comercial, Municipal o Residencial).
                    3. Asegurate de proporcionar las opciones numeradas (1. Industrial, 2. Comercial, etc.).
                    4. Manten un tono conversacional y amigable.

                    NO procedas a mas preguntas hasta que el usuario responda esta primera pregunta.
                    """,
                }
            )

        # Añadir instrucciones de formato para evitar problemas de Markdown

        # Generar respuesta con el modelo de IA
        response = await self.generate_response(messages_for_ai)

        # Actualizar el estado del cuestionario basado en la interacción
        self._update_questionnaire_state(conversation, user_message, response)

        return response

    def _generate_state_context(self, conversation: Conversation) -> str:
        """
        Genera un contexto informativo sobre el estado actual del cuestionario

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
            context += "- El cuestionario ha sido completado. Debes generar una propuesta final según el formato proporcionado.\n"
        elif state.active:
            context += "- El cuestionario está activo. Continúa con la siguiente pregunta según el documento del cuestionario.\n"

        return context

    def _update_questionnaire_state(
        self, conversation: Conversation, user_message: str, ai_response: str
    ) -> None:
        """
        Actualiza el estado del cuestionario basado en la interacción reciente

        Args:
            conversation: Objeto de conversación actual
            user_message: Mensaje del usuario
            ai_response: Respuesta generada por el modelo
        """
        state = conversation.questionnaire_state

        # Si el cuestionario no está activo, no hay nada que actualizar
        if not state.active and not state.completed:
            return

        # Detectar selección de sector
        if not state.sector:
            # Verificar si el modelo está preguntando por el sector
            if "¿En qué sector opera tu empresa?" in ai_response:
                return  # Esperando respuesta de sector

            # Intentar identificar el sector en la respuesta del usuario
            sectors = ["Industrial", "Comercial", "Municipal", "Residencial"]
            for sector in sectors:
                if sector.lower() in user_message.lower():
                    state.sector = sector
                    break

            # Verificar respuestas numéricas (1-4)
            if user_message.strip() in ["1", "2", "3", "4"]:
                index = int(user_message.strip()) - 1
                if 0 <= index < len(sectors):
                    state.sector = sectors[index]

        # Detectar selección de subsector
        elif state.sector and not state.subsector:
            # Verificar si el modelo está preguntando por el subsector
            if "giro específico" in ai_response or "subsector" in ai_response:
                return  # Esperando respuesta de subsector

            # Obtener los subsectores para el sector seleccionado
            subsectors = questionnaire_service.get_subsectors(state.sector)

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

        # Detectar si el cuestionario ha terminado y se ha generado una propuesta
        if (
            "RESUMEN DE LA PROPUESTA" in ai_response
            or "ANÁLISIS ECONÓMICO" in ai_response
        ):
            state.completed = True
            # No desactivamos el cuestionario para mantener el contexto

        # Actualizar pregunta actual si es necesario
        if state.active and not state.completed:
            # Si tenemos sector y subsector, actualizar información de preguntas
            if state.sector and state.subsector:
                # Este método es simplificado, idealmente deberíamos identificar exactamente
                # qué pregunta está siendo respondida, pero por ahora mantenemos el enfoque mínimo
                question_key = f"{state.sector}_{state.subsector}"
                questions = questionnaire_service.questionnaire_data.get(
                    "questions", {}
                ).get(question_key, [])

                # Si hay una pregunta en la respuesta del modelo, esa es la actual
                for question in questions:
                    q_text = question.get("text", "")
                    if q_text in ai_response and question["id"] not in state.answers:
                        state.current_question_id = question["id"]
                        return

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
        Genera una respuesta utilizando el proveedor de IA configurado y
        asegura que el formato sea compatible con el frontend

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

            # Añadir instruccion especifica para evitar uso excesivo de Markdown
            messages.append(
                {
                    "role": "system",
                    "content": """
                INSTRUCCION IMPORTANTE DE FORMATO:
                1. No uses encabezados Markdown (como # o ##) excepto para la propuesta final.
                2. No uses listas con formato Markdown (- o *), usa listas numeradas estandar (1., 2., etc.).
                3. Para enfatizar texto, usa un formato de texto plano como "IMPORTANTE" en lugar de **texto**.
                4. Evita el uso de tablas en formato Markdown.
                5. Si necesitas separar secciones, usa lineas en blanco simples en lugar de lines horizontales (---).
                6. Para la propuesta final esta bien usar formato Markdown adecuado.
                """,
                }
            )

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

                # Procesar el texto para mantener un formato asistente
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
        # Si el texto parece ser una propuesta, mantener el formato Markdown
        if "RESUMEN DE LA PROPUESTA" in text or "# RESUMEN DE LA PROPUESTA" in text:
            return text

        # 1. Reemplazar encabezados Markdown con texto plano enfatizado
        for i in range(5, 0, -1):  # De h5 a h1
            heading = "#" * i
            text = re.sub(
                f"^{heading}\\s+(.+)$", r"IMPORTANTE: \1", text, flags=re.MULTILINE
            )

        # 2. Reemplazar listas con viñetas
        text = re.sub(r"^[\*\-]\s+(.+)$", r"• \1", text, flags=re.MULTILINE)

        # 3. Mantener texto en negrita pero simplificar su uso (opcional)
        # text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)

        # 4. Eliminar líneas horizontales
        text = re.sub(r"^[\-\_]{3,}$", "", text, flags=re.MULTILINE)

        # 5. Eliminar bloques de código si no son necesarios
        # text = re.sub(r"```[a-z]*\n((.|\n)*?)```", r"\1", text)

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


# Instancia global del servicio de IA
ai_service = AIService()
