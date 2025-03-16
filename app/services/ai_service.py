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
        Maneja la conversación de manera optimizada, reduciendo tokens y mejorando la calidad

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

        # 1. Determinar la etapa actual de la conversación
        current_stage = self._determine_conversation_stage(conversation)

        # 2. Obtener el prompt adecuado para la etapa
        stage_prompt = self._get_prompt_for_stage(current_stage)

        # 3. Preparar los mensajes para el modelo de IA
        messages_for_ai = [{"role": "system", "content": stage_prompt}]

        # 4. Añadir contexto relevante según la etapa
        if current_stage in ["QUESTIONNAIRE", "ANALYSIS", "PROPOSAL"]:
            # Obtener solo las preguntas relevantes (actual y siguientes)
            relevant_questions = self._get_relevant_questions_context(conversation)
            if relevant_questions:
                messages_for_ai.append(
                    {"role": "system", "content": relevant_questions}
                )

            # Añadir resumen compacto de respuestas anteriores
            answers_summary = self._get_compact_answers_summary(conversation)
            if answers_summary:
                messages_for_ai.append({"role": "system", "content": answers_summary})

        # 5. Añadir ejemplo de few-shot si está disponible para esta etapa
        few_shot_example = self._get_few_shot_example(current_stage)
        if few_shot_example:
            messages_for_ai.append({"role": "system", "content": few_shot_example})

        # 6. Añadir historial comprimido de la conversación
        compressed_history = self._compress_conversation_history(conversation)
        messages_for_ai.extend(compressed_history)

        # 7. Añadir el mensaje actual del usuario si no está incluido en el historial
        if (
            not compressed_history
            or compressed_history[-1]["role"] != "user"
            or compressed_history[-1]["content"] != user_message
        ):
            messages_for_ai.append({"role": "user", "content": user_message})

        # 8. Instrucción final si acabamos de iniciar el cuestionario
        if should_start:
            messages_for_ai.append(
                {
                    "role": "system",
                    "content": "El usuario ha mostrado interés en soluciones de tratamiento de agua. Comienza con el saludo estándar y la primera pregunta sobre el sector.",
                }
            )

        # 9. Optimización: Calcular tokens aproximados y registrar para análisis
        if token_counter_available:
            try:
                token_count = count_tokens(messages_for_ai, self.model)
                cost_estimate = estimate_cost(token_count, self.model)
                logger.info(
                    f"Tokens enviados: {token_count} en etapa {current_stage} (est. costo: ${cost_estimate:.5f})"
                )
            except Exception as e:
                logger.warning(f"Error al contar tokens: {str(e)}")
                # Aproximación rápida
                total_tokens = sum(
                    len(msg["content"].split()) * 1.35 for msg in messages_for_ai
                )
                logger.info(
                    f"Tokens aproximados: {int(total_tokens)} en etapa {current_stage}"
                )
        else:
            # Aproximación rápida si no está disponible el contador de tokens
            total_tokens = sum(
                len(msg["content"].split()) * 1.35 for msg in messages_for_ai
            )
            logger.info(
                f"Tokens aproximados enviados al modelo: {int(total_tokens)} en etapa {current_stage}"
            )

        # 10. Generar respuesta con el modelo de IA
        start_time = time.time()
        response = await self.generate_response(messages_for_ai)
        elapsed_time = time.time() - start_time
        logger.info(f"Respuesta generada en {elapsed_time:.2f} segundos")

        # 11. Actualizar el estado del cuestionario basado en la interacción
        self._update_questionnaire_state(conversation, user_message, response)

        return response

    def _determine_conversation_stage(self, conversation: Conversation) -> str:
        """
        Determina la etapa actual de la conversación para seleccionar el prompt adecuado

        Args:
            conversation: Objeto de conversación actual

        Returns:
            str: Etapa actual de la conversación (INIT, SECTOR, SUBSECTOR, etc.)
        """
        state = conversation.questionnaire_state

        # Si el cuestionario no está activo
        if not state.active:
            if state.completed:
                return "PROPOSAL"
            else:
                return "INIT"

        # Si el cuestionario está activo pero no tenemos sector
        if not state.sector:
            return "INIT"

        # Si tenemos sector pero no subsector
        if state.sector and not state.subsector:
            return "SECTOR"

        # Si tenemos ambos pero pocas respuestas (inicio del cuestionario)
        answer_count = len(state.answers)
        if answer_count < 10:
            return "QUESTIONNAIRE"

        # Si tenemos suficientes respuestas para iniciar análisis
        if 10 <= answer_count < 15:
            return "ANALYSIS"

        # Si tenemos muchas respuestas, probablemente estamos cerca de terminar
        if answer_count >= 15:
            return "PROPOSAL"

        # Default
        return "QUESTIONNAIRE"

    def _get_prompt_for_stage(self, stage: str) -> str:
        """
        Obtiene el prompt adecuado para la etapa actual de la conversación

        Args:
            stage: Etapa actual de la conversación

        Returns:
            str: Prompt para la etapa actual
        """
        # Siempre incluimos el prompt base y las instrucciones de formato
        prompt = settings.STAGED_PROMPTS["BASE"] + "\n\n"

        # Añadimos el prompt específico para la etapa
        if stage in settings.STAGED_PROMPTS:
            prompt += settings.STAGED_PROMPTS[stage] + "\n\n"

        # Añadimos instrucciones de formato
        prompt += settings.STAGED_PROMPTS["FORMAT"]

        return prompt

    def _get_few_shot_example(self, stage: str) -> Optional[str]:
        """
        Obtiene un ejemplo de few-shot para la etapa actual si está disponible

        Args:
            stage: Etapa actual de la conversación

        Returns:
            Optional[str]: Ejemplo de few-shot o None si no hay ejemplo
        """
        return settings.FEW_SHOT_EXAMPLES.get(stage)

    def _compress_conversation_history(
        self, conversation: Conversation, max_messages: int = 10
    ) -> List[Dict[str, str]]:
        """
        Comprime el historial de la conversación para reducir tokens

        Args:
            conversation: Objeto de conversación actual
            max_messages: Número máximo de mensajes a incluir

        Returns:
            List[Dict[str, str]]: Historial comprimido
        """
        messages = [msg for msg in conversation.messages if msg.role != "system"]

        # Si tenemos pocos mensajes, los devolvemos todos
        if len(messages) <= max_messages:
            return [{"role": msg.role, "content": msg.content} for msg in messages]

        # Si tenemos muchos mensajes, seleccionamos los más importantes
        compressed_history = []

        # Siempre incluimos los primeros 2 mensajes (saludo inicial)
        for msg in messages[:2]:
            compressed_history.append({"role": msg.role, "content": msg.content})

        # Incluimos los últimos N-2 mensajes para mantener el contexto reciente
        for msg in messages[-(max_messages - 2) :]:
            compressed_history.append({"role": msg.role, "content": msg.content})

        # Si hemos omitido mensajes, añadimos un resumen
        if len(messages) > max_messages:
            omitted_count = len(messages) - max_messages
            summary = {
                "role": "system",
                "content": f"[Se han omitido {omitted_count} mensajes anteriores para optimizar. La conversación ha incluido preguntas sobre {conversation.questionnaire_state.sector}/{conversation.questionnaire_state.subsector} y el usuario ha proporcionado información sobre su proyecto.]",
            }
            compressed_history.insert(
                2, summary
            )  # Insertar después de los 2 primeros mensajes

        return compressed_history

    def _get_relevant_questions_context(self, conversation: Conversation) -> str:
        """
        Obtiene solo las preguntas relevantes del cuestionario para la etapa actual

        Args:
            conversation: Objeto de conversación actual

        Returns:
            str: Contexto de preguntas relevantes
        """
        state = conversation.questionnaire_state

        # Si no tenemos sector/subsector, no hay preguntas específicas
        if not state.sector or not state.subsector:
            return ""

        # Obtener la pregunta actual
        current_question_id = state.current_question_id
        if not current_question_id:
            return ""

        # Obtener todas las preguntas para este sector/subsector
        question_key = f"{state.sector}_{state.subsector}"
        all_questions = questionnaire_service.questionnaire_data.get(
            "questions", {}
        ).get(question_key, [])
        if not all_questions:
            return ""

        # Encontrar la pregunta actual y las siguientes 2 preguntas
        relevant_questions = []
        found_current = False
        count_after = 0

        for question in all_questions:
            if found_current and count_after < 2:
                # Incluimos hasta 2 preguntas después de la actual
                relevant_questions.append(question)
                count_after += 1

            if question["id"] == current_question_id:
                # Encontramos la pregunta actual
                relevant_questions.append(question)
                found_current = True

        # Si no encontramos la pregunta actual, devolvemos vacío
        if not found_current:
            return ""

        # Formateamos las preguntas relevantes
        context = "PREGUNTAS RELEVANTES DEL CUESTIONARIO:\n\n"
        for i, q in enumerate(relevant_questions):
            # Marcar la pregunta actual
            prefix = ">>> PREGUNTA ACTUAL: " if i == 0 else f"Pregunta siguiente {i}: "

            context += f"{prefix}{q.get('text', '')}\n"

            # Añadir explicación si existe
            if "explanation" in q:
                context += f"Explicación: {q['explanation']}\n"

            # Añadir opciones si existen
            if (
                q.get("type") in ["multiple_choice", "multiple_select"]
                and "options" in q
            ):
                context += "Opciones:\n"
                for j, option in enumerate(q["options"], 1):
                    context += f"{j}. {option}\n"

            context += "\n"

        return context

    def _get_compact_answers_summary(self, conversation: Conversation) -> str:
        """
        Genera un resumen compacto de las respuestas proporcionadas

        Args:
            conversation: Objeto de conversación actual

        Returns:
            str: Resumen de respuestas en formato compacto
        """
        state = conversation.questionnaire_state

        # Si no hay respuestas, devolvemos un string vacío
        if not state.answers:
            return ""

        # Creamos un resumen en formato JSON compacto
        answers_list = []

        for q_id, answer in state.answers.items():
            # Intentamos encontrar el texto de la pregunta
            question_text = q_id  # Por defecto, usamos el ID

            if q_id == "sector_selection":
                question_text = "Sector"
            elif q_id == "subsector_selection":
                question_text = "Subsector"
            else:
                # Buscar en las preguntas del sector/subsector
                if state.sector and state.subsector:
                    question_key = f"{state.sector}_{state.subsector}"
                    questions = questionnaire_service.questionnaire_data.get(
                        "questions", {}
                    ).get(question_key, [])

                    for q in questions:
                        if q.get("id") == q_id:
                            question_text = q.get("text", "").split("?")[
                                0
                            ]  # Tomamos solo la primera parte
                            break

            # Añadimos la respuesta al resumen
            answers_list.append(f"- {question_text}: {answer}")

        # Formatear el resumen
        summary = "RESUMEN DE RESPUESTAS DEL USUARIO:\n\n"
        summary += "\n".join(answers_list)

        return summary

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
            str: Texto de la respuesta generada con formato adecuado para el frontend
        """
        try:
            # Verificar si tenemos conexión con la API
            if not self.api_key or not self.api_url:
                return self._get_fallback_response(messages)

            # Añadir instrucción específica para evitar uso excesivo de Markdown
            messages.append(
                {
                    "role": "system",
                    "content": """
                INSTRUCCIÓN IMPORTANTE DE FORMATO:
                1. No uses encabezados Markdown (como # o ##) excepto para la propuesta final.
                2. No uses listas con formato Markdown (- o *), usa listas numeradas estándar (1., 2., etc.).
                3. Para enfatizar texto, usa formato de texto plano como "IMPORTANTE:" en lugar de **texto**.
                4. Evita el uso de tablas en formato Markdown.
                5. Si necesitas separar secciones, usa líneas en blanco simples en lugar de líneas horizontales (---).
                6. Para la propuesta final está bien usar formato Markdown adecuado.
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
        # Si el texto parece ser una propuesta (tiene encabezados y secciones),
        # mantener el formato Markdown para que se pueda renderizar adecuadamente
        if "RESUMEN DE LA PROPUESTA" in text or "# RESUMEN DE LA PROPUESTA" in text:
            return text

        # Para el resto de respuestas, simplificar el formato Markdown:

        # 1. Reemplazar encabezados Markdown con texto plano enfatizado
        for i in range(5, 0, -1):  # De h5 a h1
            heading = "#" * i
            text = re.sub(
                f"^{heading}\\s+(.+)$", r"IMPORTANTE: \1", text, flags=re.MULTILINE
            )

        # 2. Reemplazar listas con viñetas por listas con números o texto plano
        text = re.sub(r"^[\*\-]\s+(.+)$", r"• \1", text, flags=re.MULTILINE)

        # 3. Eliminar líneas horizontales
        text = re.sub(r"^[\-\_]{3,}$", "", text, flags=re.MULTILINE)

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


# Clase extendida del servicio de IA (se utilizará en lugar de la estándar)
class AIWithQuestionnaireService(AIService):
    """Versión del servicio de IA con funcionalidad de cuestionario integrada"""

    def __init__(self):
        super().__init__()


# Instancia global del servicio
ai_service = AIWithQuestionnaireService()
