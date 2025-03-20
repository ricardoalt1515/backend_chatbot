import logging
import re
from typing import List, Dict, Any, Optional, Tuple
import httpx
import time
import json
from datetime import datetime
import random

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

        # Mensaje de saludo inical
        self.INITIAL_GREETING = """
        # Bienvenido a Hydrous Managment Group

        Soy el Diseñador de Soluciones de Agua con IA de Hydrous, su asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales. Como herramienta de Hydrous, estoy aquí para guiarlo paso a paso en la evaluación de las necesidades de agua de su sitio, la exploración de posibles soluciones y la identificación de oportunidades de ahorro, cumplimiento normativo y sostenibilidad.

        Para desarrollar la mejor solución para sus instalaciones, formularé sistemáticamente preguntas específicas para recopilar los datos necesarios y crear una propuesta personalizada. Mi objetivo es ayudarle a optimizar la gestión del agua, reducir costes y explorar nuevas fuentes de ingresos con soluciones basadas en Hydrous.
        """

    def format_response_with_questions(
        self,
        previous_answer_comment,
        interesting_fact,
        question_context,
        question_text,
        options=None,
    ):
        """Formatea una respuesta siguiendo la estructura exacta establecida"""
        # Asegurar que no se duplique el prefijo PREGUNTA:
        if question_text.startswith("PREGUNTA:"):
            question_text = question_text.replace("PREGUNTA:", "").strip()

        # 1. Comentario sobre respuesta anterior
        response = f"{previous_answer_comment}\n\n"

        # 2. Dato interesante en cursiva
        if interesting_fact:
            response += f"*{interesting_fact}*\n\n"

        # 3. Explicación de por qué la pregunta es importante
        if question_context:
            response += f"{question_context}\n\n"

        # 4. La pregunta al FINAL, en negrita y precedida por "PREGUNTA:"
        response += f"**PREGUNTA: {question_text}**\n\n"

        # 5. Opciones numeradas para preguntas de opción múltiple
        if options:
            for i, option in enumerate(options, 1):
                response += f"{i}. {option}\n"

        return response

    def should_suggest_document(self, question_id):
        """Determina si se debe sugerir subir un documento en esta pregunta"""
        document_suggestion_questions = [
            "parametros_agua",
            "costo_agua",
            "sistema_existente",
            "recibos_agua",
            "descripcion_sistema",
            "agua_potable_analisis",
        ]

        return question_id in document_suggestion_questions

    async def handle_conversation(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Maneja el flujo de conversación asegurando la estructura deseada y el formato correcto
        siguiendo estrictamente el prompt especificado
        """
        try:
            # Si es un nuevo inicio de conversación o se detecta intención de cuestionario
            if (
                not conversation.is_questionnaire_active()
                and not conversation.is_questionnaire_completed()
            ):
                # Detectar si el usuario quiere iniciar el cuestionario
                if self._detect_questionnaire_intent(user_message):
                    conversation.start_questionnaire()
                    # Mostrar el saludo inicial EXACTO según el prompt
                    return """
Soy el diseñador de soluciones de agua de Hydrous AI, su asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales. Como herramienta de Hydrous, estoy aquí para guiarlo paso a paso en la evaluación de las necesidades de agua de su sitio, la exploración de posibles soluciones y la identificación de oportunidades de ahorro de costos, cumplimiento y sostenibilidad.

Para desarrollar la mejor solución para sus instalaciones, haré sistemáticamente preguntas específicas para recopilar los datos necesarios y crear una propuesta personalizada. Mi objetivo es ayudarlo a optimizar la gestión del agua, reducir costos y explorar nuevas fuentes de ingresos con soluciones respaldadas por Hydrous.

*Las soluciones de reciclaje de agua pueden reducir el consumo de agua fresca hasta en un 70% en instalaciones industriales similares.*

El tratamiento adecuado del agua no solo es beneficioso para el medio ambiente, sino que puede representar un ahorro significativo en costos operativos a mediano y largo plazo.

**PREGUNTA: ¿En qué sector opera su empresa?**
1. Industrial
2. Comercial
3. Municipal
4. Residencial
                    """
                else:
                    # Procesar consulta general sin iniciar cuestionario
                    messages = [{"role": "system", "content": settings.SYSTEM_PROMPT}]

                    # Añadir contexto reciente
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

            # Si el cuestionario está activo, procesar la respuesta según el flujo estructurado
            if conversation.is_questionnaire_active():
                # Almacenar el estado actual antes de procesar la respuesta
                current_question_id = (
                    conversation.questionnaire_state.current_question_id
                )

                # Procesar la respuesta del usuario
                self._update_questionnaire_state(conversation, user_message)

                # Verificar que el estado se haya actualizado correctamente
                # Si parece haberse perdido, restaurarlo
                if (
                    not conversation.questionnaire_state.current_question_id
                    and not conversation.is_questionnaire_completed()
                ):
                    logger.warning(
                        f"Detectada pérdida potencial de estado. Restaurando ID de pregunta anterior: {current_question_id}"
                    )
                    conversation.questionnaire_state.current_question_id = (
                        current_question_id
                    )

                # Verificar si es momento de mostrar un resumen intermedio (cada 5 preguntas)
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

                # Verificar si hemos completado el cuestionario
                next_question = self._get_next_question(conversation)
                if not next_question:
                    # Marcar como recopilación completa
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
                        return questionnaire_service.generate_final_confirmation(
                            conversation
                        )
                    else:
                        # El usuario tiene preguntas sobre el diagnóstico
                        return self._handle_diagnosis_questions(
                            conversation, user_message
                        )

                # Verificar si estamos en fase de confirmación final
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

                # Si llegamos aquí, procesamos la siguiente pregunta normalmente
                if next_question:
                    # Obtener un dato interesante relevante para el sector/subsector
                    interesting_fact = questionnaire_service.get_random_fact(
                        conversation.questionnaire_state.sector,
                        conversation.questionnaire_state.subsector,
                    )

                    # Generar comentario personalizado sobre la respuesta anterior
                    previous_comment = self._generate_previous_answer_comment(
                        conversation, user_message
                    )

                    # Obtener explicación de la pregunta
                    question_context = next_question.get("explanation", "")

                    # Preparar la pregunta y opciones si es multiple choice
                    question_text = next_question.get("text", "")
                    options = None
                    if (
                        next_question.get("type")
                        in ["multiple_choice", "multiple_select"]
                        and "options" in next_question
                    ):
                        options = next_question["options"]

                    # Formatear respuesta siguiendo EXACTAMENTE la estructura solicitada
                    response = self.format_response_with_questions(
                        previous_comment,
                        interesting_fact,
                        question_context,
                        question_text,
                        options,
                    )

                    # Determinar si debemos sugerir carga de documentos
                    if self.should_suggest_document(next_question.get("id", "")):
                        document_suggestion = (
                            questionnaire_service.suggest_document_upload(
                                next_question.get("id", "")
                            )
                        )
                        response += f"\n\n{document_suggestion}"

                    # Actualizar la pregunta actual
                    conversation.questionnaire_state.current_question_id = (
                        next_question.get("id", "")
                    )

                    return response
                else:
                    # Si no hay siguiente pregunta pero el cuestionario sigue activo
                    # puede ser un error, intentar recuperarlo
                    logger.warning(
                        "No se encontró siguiente pregunta pero el cuestionario sigue activo"
                    )
                    return "Parece que hemos tenido un problema al procesar su respuesta. ¿Podría confirmar que desea continuar con el cuestionario o generar una propuesta con los datos recopilados hasta ahora?"

            # Gestión de consultas post-propuesta (cuando el cuestionario está completo)
            if conversation.is_questionnaire_completed():
                # Detectar si es una solicitud de PDF
                if self._is_pdf_request(user_message):
                    # Generar enlace para descargar PDF
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

                # Responder a preguntas sobre la propuesta
                messages = [
                    {"role": "system", "content": settings.SYSTEM_PROMPT},
                    {
                        "role": "system",
                        "content": "El usuario ha completado el cuestionario y se le ha presentado una propuesta. Responde a sus preguntas adicionales sobre la propuesta, manteniendo un tono profesional y ofreciendo detalles técnicos cuando sea necesario.",
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

            # Fallback para otros casos no contemplados
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

            # Generar respuesta genérica
            return await self.generate_response(messages)

        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error procesando su mensaje. ¿Podría reformular su pregunta o intentarlo de nuevo?"

    async def _handle_diagnosis_questions(
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

    async def _handle_additional_information(
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

    def _generate_previous_answer_comment(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Genera un comentario personalizado sobre la respuesta anterior del usuario
        con variedad para evitar repetición
        """
        # Obtener el ID de la pregunta que se acaba de responder
        prev_question_id = conversation.questionnaire_state.current_question_id

        # Lista de inicios variados para evitar repetir siempre "Entendido."
        starters = [
            "Gracias por esa información.",
            "Excelente, esto es útil.",
            "Perfecto, he registrado su respuesta.",
            "Bien, esta información nos ayuda mucho.",
            "Comprendo, esto es importante para nuestra evaluación.",
            "Muy bien, esto nos da más contexto.",
            "Entendido, esto es valioso para nuestro análisis.",
            "Apreciamos esa información.",
            "Esto es exactamente lo que necesitábamos saber.",
            "Gracias, esto esclarece su situación específica.",
        ]

        # Elegir aleatoriamente un inicio
        starter = random.choice(starters)

        # Comentarios específicos según el tipo de pregunta
        if prev_question_id == "sector_selection":
            return f"{starter} El sector que ha indicado es fundamental para adaptar nuestra solución a sus necesidades específicas."

        elif prev_question_id == "subsector_selection":
            sector = conversation.questionnaire_state.sector
            subsector = conversation.questionnaire_state.subsector
            return f"{starter} El subsector {subsector} dentro del sector {sector} presenta desafíos y oportunidades particulares en el tratamiento de agua."

        elif prev_question_id == "nombre_empresa":
            return f"{starter} Tener el nombre de su empresa nos ayudará a personalizar nuestra propuesta."

        elif prev_question_id == "ubicacion":
            return f"{starter} La ubicación es un factor importante que influye en la disponibilidad de agua y las normativas aplicables."

        elif prev_question_id == "costo_agua":
            return f"{starter} El costo del agua es un factor clave para calcular el retorno de inversión de las soluciones que propongamos."

        elif prev_question_id == "cantidad_agua_consumida":
            return f"{starter} El consumo de agua que ha indicado es esencial para dimensionar adecuadamente la solución."

        elif prev_question_id == "cantidad_agua_residual":
            return f"{starter} Esta información sobre generación de aguas residuales es fundamental para el diseño del sistema de tratamiento."

        elif prev_question_id == "parametros_agua":
            return f"{starter} Los parámetros que ha proporcionado son muy valiosos para determinar las tecnologías de tratamiento más adecuadas."

        elif prev_question_id == "objetivo_principal":
            return f"{starter} Entendemos su objetivo principal. Esto nos ayudará a enfocar nuestra propuesta en los aspectos más relevantes para su caso."

        # Para otros casos, usar un comentario general pero variado
        general_comments = [
            f"{starter} Cada dato que proporciona nos acerca más a diseñar la solución óptima para su caso.",
            f"{starter} Con esta información podemos ajustar mejor nuestra propuesta a sus necesidades.",
            f"{starter} Esto nos ayuda a entender mejor su situación específica.",
            f"{starter} Sus respuestas nos permiten personalizar la solución de manera más efectiva.",
        ]

        return random.choice(general_comments)

    def _detect_questionnaire_intent(self, message: str) -> bool:
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
            "formulario",
            "preguntas",
            "agua",
            "tratamiento",
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
            "hola",
            "saludos",
        ]

        # Si contiene alguna palabra clave explícita, iniciar cuestionario
        for keyword in explicit_keywords:
            if keyword in message:
                return True

        # Contar palabras clave relacionadas con agua
        water_keyword_count = sum(1 for keyword in water_keywords if keyword in message)

        # Si contiene al menos 2 palabras clave de agua, iniciar cuestionario
        if water_keyword_count >= 1:
            return True

        # Verificar frases explícitas junto con alguna palabra clave de agua
        for phrase in explicit_phrases:
            if phrase in message:
                return True

        # Para mensajes muy cortos o saludos, probablemente es un inicio de conversación
        if len(message.split()) <= 3:
            return True

        return False

    def _is_pdf_request(self, message: str) -> bool:
        """
        Determina si el mensaje del usuario es una solicitud de PDF con detección mejorada

        Args:
            message: Mensaje del usuario

        Returns:
            bool: True si es una solicitud de PDF
        """
        message = message.lower()

        # Palabras clave específicas relacionadas con documentos/PDF
        pdf_keywords = [
            "pdf",
            "descargar",
            "download",
            "propuesta",
            "documento",
            "guardar",
            "archivo",
            "exportar",
            "bajar",
            "obtener",
            "enviar",
            "mandar",
            "recibir",
            "adjuntar",
        ]

        # Frases específicas de solicitud
        pdf_phrases = [
            "quiero el pdf",
            "dame la propuesta",
            "ver el documento",
            "obtener el archivo",
            "descargar la propuesta",
            "enviame el pdf",
            "generar documento",
            "necesito la propuesta",
            "envíame la propuesta",
            "dame el documento",
            "puedo tener",
            "puedo obtener",
            "me gustaría el pdf",
            "puedes enviarme",
            "necesito descargar",
            "puedo descargar",
            "el enlace no funciona",
        ]

        # Detectar palabras clave individuales
        if any(keyword in message for keyword in pdf_keywords):
            return True

        # Detectar frases específicas
        for phrase in pdf_phrases:
            if phrase in message:
                return True

        # Detectar patrones de pregunta sobre el documento
        if any(
            pattern in message
            for pattern in [
                "como obtengo",
                "cómo descargo",
                "donde está",
                "dónde puedo",
                "link de",
                "enlace para",
            ]
        ):
            if any(
                doc_word in message
                for doc_word in ["pdf", "documento", "propuesta", "informe"]
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

    def _get_current_question(
        self, conversation: Conversation
    ) -> Optional[Dict[str, Any]]:
        """Obtiene la pregunta actual según el ID almacenado"""
        state = conversation.questionnaire_state
        current_id = state.current_question_id

        if not current_id:
            return None

        # Si es sector o subsector, devolver la pregunta correspondiente
        if current_id == "sector_selection":
            return {
                "id": "sector_selection",
                "text": "¿En qué sector opera su empresa?",
                "type": "multiple_choice",
                "options": questionnaire_service.get_sectors(),
                "explanation": "El sector nos ayudará a entender mejor su contexto y necesidades específicas.",
            }

        if current_id == "subsector_selection":
            return {
                "id": "subsector_selection",
                "text": f"¿Cuál es el subsector específico dentro de {state.sector}?",
                "type": "multiple_choice",
                "options": questionnaire_service.get_subsectors(state.sector),
                "explanation": "Cada subsector tiene características y necesidades específicas para el tratamiento de agua.",
            }

        # Buscar en las preguntas específicas del sector/subsector
        questions_key = f"{state.sector}_{state.subsector}"
        questions = questionnaire_service.questionnaire_data.get("questions", {}).get(
            questions_key, []
        )

        for question in questions:
            if question["id"] == current_id:
                return question

        return None

    def _update_questionnaire_state(
        self, conversation: Conversation, user_message: str
    ) -> None:
        """
        Actualiza el estado del cuestionario basado en la respuesta del usuario
        con manejo mejorado de opciones múltiples
        """
        state = conversation.questionnaire_state
        current_question_id = state.current_question_id

        # Si no hay pregunta actual, no hay nada que procesar
        if not current_question_id:
            return

        # Si es seleccion de sector
        if current_question_id == "sector_selection":
            # Puede ser indice numerico o texto directo
            if user_message.strip().isdigit():
                sector_index = int(user_message.strip()) - 1
                sectors = questionnaire_service.get_sectors()
                if 0 <= sector_index < len(sectors):
                    state.sector = sectors[sector_index]
                    state.answers[current_question_id] = sectors[sector_index]

                    # Asegurar que pasamos a la siguiente pregunta cambiando el current_question_id a None
                    # o directamente establecer la siguiente pregunta
                    state.current_question_id = "subsector_selection"
                    return

        # Obtener la pregunta actual
        current_question = self._get_current_question(conversation)

        if not current_question:
            logger.warning(
                f"No se pudo encontrar la pregunta actual con ID: {current_question_id}"
            )
            return

        # Si es selección de sector
        if current_question_id == "sector_selection":
            # Puede ser índice numérico o texto directo
            if user_message.strip().isdigit():
                sector_index = int(user_message.strip()) - 1
                sectors = questionnaire_service.get_sectors()
                if 0 <= sector_index < len(sectors):
                    state.sector = sectors[sector_index]
                    state.answers[current_question_id] = sectors[sector_index]
                    return

            # Si no es un índice válido, buscar coincidencia en el texto
            sectors = questionnaire_service.get_sectors()
            for sector in sectors:
                if sector.lower() in user_message.lower():
                    state.sector = sector
                    state.answers[current_question_id] = sector
                    return

            # Si no se encontró coincidencia, registrar respuesta directa
            state.answers[current_question_id] = user_message

        # Si es selección de subsector
        elif current_question_id == "subsector_selection" and state.sector:
            # Puede ser índice numérico o texto directo
            if user_message.strip().isdigit():
                subsector_index = int(user_message.strip()) - 1
                subsectors = questionnaire_service.get_subsectors(state.sector)
                if 0 <= subsector_index < len(subsectors):
                    state.subsector = subsectors[subsector_index]
                    state.answers[current_question_id] = subsectors[subsector_index]
                    return

            # Si no es un índice válido, buscar coincidencia en el texto
            subsectors = questionnaire_service.get_subsectors(state.sector)
            for subsector in subsectors:
                if subsector.lower() in user_message.lower():
                    state.subsector = subsector
                    state.answers[current_question_id] = subsector
                    return

            # Si no se encontró coincidencia, registrar respuesta directa
            state.answers[current_question_id] = user_message

        # Si es una pregunta de opción múltiple
        elif (
            current_question.get("type") in ["multiple_choice", "multiple_select"]
            and "options" in current_question
        ):
            options = current_question["options"]

            # Intentar procesar como índice
            if user_message.strip().isdigit():
                index = int(user_message.strip()) - 1
                if 0 <= index < len(options):
                    selected_option = options[index]
                    state.answers[current_question_id] = selected_option
                    return

            # Si no es un índice válido, buscar coincidencia en el texto
            for option in options:
                if option.lower() in user_message.lower():
                    state.answers[current_question_id] = option
                    return

            # Si no se encontró coincidencia, registrar respuesta directa
            state.answers[current_question_id] = user_message

        # Para cualquier otra pregunta, guardar la respuesta directamente
        else:
            state.answers[current_question_id] = user_message

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
        # Corregir problema de duplicación de PREGUNTA:
        text = re.sub(r"PREGUNTA:\s*PREGUNTA:", "PREGUNTA:", text)

        # Asegurar que los enlaces Markdown esten correctamente formateados
        text = re.sub(r"\[([^\]]+)\]\s*\(([^)]+)\)", r"[\1](\2)", text)

        # Asegurar que los encabezados tengan espacio despues del #
        for i in range(6, 0, -1):  # de h6 a h1
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

        elif self._is_pdf_request(last_user_message):
            return (
                "Para generar una propuesta detallada y descargarla en PDF, necesitamos "
                "recopilar información específica sobre tu proyecto a través de nuestro "
                "cuestionario. ¿Te gustaría comenzar ahora?"
            )

        else:
            return (
                "Gracias por tu mensaje. Para brindarte la mejor solución de reciclaje de agua, "
                "te recomendaría completar nuestro cuestionario personalizado. Así podré entender "
                "mejor tus necesidades específicas. ¿Te gustaría comenzar?"
            )


# Instancia global del servicio
ai_service = AIService()
