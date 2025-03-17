import logging
import re
from typing import List, Dict, Any, Optional, Tuple
import httpx
import time

from config import settings
from models.conversation import Conversation
from services.questionnaire_service import questionnaire_service
from services import document_service

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

        # Configuración básica según el proveedor
        if self.provider == "groq":
            self.api_key = settings.GROQ_API_KEY
            self.model = settings.GROQ_MODEL
            self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        else:  # openai por defecto
            self.api_key = settings.OPENAI_API_KEY
            self.model = settings.OPENAI_MODEL
            self.api_url = "https://api.openai.com/v1/chat/completions"

        # Registro de información recopilada por conversación
        self.collected_info = {}

    async def handle_conversation(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Maneja la conversación de manera optimizada, reduciendo tokens y mejorando la calidad

        """
        conversation_id = conversation.id

        # Inicializar seguimiento de informacion para esta conversacion
        if conversation_id not in self.collected_info:
            self.collected_info[conversation_id] = {
                "sector": None,
                "subsector": None,
                "key_parameters": {},
                "has_sufficient_info": False,
                "documens_analyzed": [],
            }

            # Verificar si debemos iniciar cuestionario basado en la intencion del usuario
            should_start = self._detect_questionnaire_intent(user_message)
            if should_start and not conversation.is_questionnaire_active():
                conversation.start_questionnaire()

            # Obtener informacion de documentos si existen
            document_insights = await self._get_document_insights(conversation.id)

            # Preparar mensajes para el modelo
            messages = self._prepare_conversation_messages(
                conversation, document_insights
            )

            # añadir el mensaje actual del usuario
            messages.append({"role": "user", "content": user_message})

            # Generar respuesta
            response = await self.generate_response(messages)

            # Actualizar informacion recopilada
            self._update_collected_info(conversation_id, user_message, response)

            # verificar si tenemos suficiente informacion para una propuesta
            info = self.collected_info[conversation_id]
            if elf._check_sufficient_info(info) and not info["has_sufficient_info"]:
                info["has_sufficient_info"] = True
                # Podríamos añadir un mensaje adicional ofreciendo generar propuesta

            return response

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

    def _prepare_conversation_messages(
        self, conversation: Conversation, document_insights: str
    ) -> List[Dict[str, str]]:
        """Prepara los mensajes para enviar al modelo de IA"""
        # Mensaje del sistema con el prompt base
        messages = [{"role": "system", "content": settings.SYSTEM_PROMPT}]

        # Añadir información de documentos si existe
        if document_insights:
            messages.append(
                {
                    "role": "system",
                    "content": f"INFORMACIÓN DE DOCUMENTOS ANALIZADOS:\n{document_insights}",
                }
            )

        # Añadir contexto relevante del cuestionario si está activo
        if conversation.is_questionnaire_active():
            sector = conversation.questionnaire_state.sector
            subsector = conversation.questionnaire_state.subsector

            if sector:
                questions_context = self._get_sector_questions(sector, subsector)
                messages.append({"role": "system", "content": questions_context})

        # Añadir historial de mensajes reciente (últimos 10 mensajes)
        recent_messages = [
            msg
            for msg in conversation.messages[-10:]
            if msg.role in ["user", "assistant"]
        ]
        for msg in recent_messages:
            messages.append({"role": msg.role, "content": msg.content})

        return messages

    def _get_sector_questions(self, sector: str, subsector: str = None) -> str:
        """Obtiene preguntas relevantes para el sector/subsector como contexto"""
        # Simplificación: cargamos solo las preguntas más importantes para este sector
        relevant_questions = questionnaire_service.get_key_questions(sector, subsector)

        context = f"PREGUNTAS CLAVE PARA {sector}"
        if subsector:
            context += f" - {subsector}"
        context += ":\n\n"

        for q in relevant_questions:
            context += f"- {q['text']}\n"

        return context

    async def _get_document_insights(self, conversation_id: str) -> str:
        """Obtiene insights de documentos asociados a la conversación"""
        try:
            from app.services.document_service import document_service

            return await document_service.get_document_insights_summary(conversation_id)
        except Exception as e:
            logger.error(f"Error al obtener insights de documentos: {str(e)}")
            return ""

    def _update_collected_info(
        self, conversation_id: str, user_message: str, ai_response: str
    ) -> None:
        """Actualiza la información recopilada basada en la interacción"""
        info = self.collected_info[conversation_id]

        # Detectar sector (simplificado)
        if not info["sector"]:
            sectors = ["Industrial", "Comercial", "Municipal", "Residencial"]
            for sector in sectors:
                if sector.lower() in user_message.lower():
                    info["sector"] = sector
                    break

        # Detectar subsector si ya tenemos sector
        elif info["sector"] and not info["subsector"]:
            subsectors = questionnaire_service.get_subsectors(info["sector"])
            for subsector in subsectors:
                if subsector.lower() in user_message.lower():
                    info["subsector"] = subsector
                    break

        # Detectar parámetros clave (simplificado)
        self._extract_key_parameters(info, user_message)

    def _extract_key_parameters(self, info: Dict[str, Any], message: str) -> None:
        """Extrae parámetros clave del mensaje del usuario"""
        # Simplificado: detectar valores numéricos con unidades
        import re

        # Buscar patrones de consumo de agua
        water_pattern = (
            r"(\d+(?:\.\d+)?)\s*(?:m3|m³|metros cúbicos|litros)/(?:día|dia|mes)"
        )
        water_matches = re.findall(water_pattern, message, re.IGNORECASE)
        if water_matches and "water_consumption" not in info["key_parameters"]:
            info["key_parameters"]["water_consumption"] = water_matches[0]

        # Buscar patrones de parámetros de calidad de agua (pH, DBO, etc.)
        ph_pattern = r"ph\s*(?:de|:)?\s*(\d+(?:\.\d+)?)"
        ph_matches = re.findall(ph_pattern, message, re.IGNORECASE)
        if ph_matches and "ph" not in info["key_parameters"]:
            info["key_parameters"]["ph"] = ph_matches[0]

    def _check_sufficient_info(self, info: Dict[str, Any]) -> bool:
        """Determina si tenemos suficiente información para generar una propuesta"""
        # Criterios simplificados
        if not info["sector"]:
            return False

        # Necesitamos al menos 3 parámetros clave
        if len(info["key_parameters"]) < 3:
            return False

        return True

    async def generate_response(self, messages: List[Dict[str, str]]) -> str:
        """Genera respuesta usando la API del proveedor configurado"""
        # Este método puede permanecer similar al original
        # Añadir lógica para manejar errores y reintentos

    def _should_show_summary(self, conversation: Conversation) -> bool:
        """Determina si es momento de mostrar un resumen intermedio"""
        answers_count = len(conversation.questionnaire_state.answers)
        # Mostrar resumen cada 5-7 preguntas (excluyendo sector/subsector)
        return (answers_count - 2) % 6 == 0 and answers_count > 2

    def _generate_interim_summary(self, conversation: Conversation) -> str:
        """Genera un resumen intermedio de la información recopilada"""
        state = conversation.questionnaire_state
        answers = state.answers

        summary = "## Resumen de la información proporcionada hasta ahora\n\n"

        # Información básica
        if "nombre_empresa" in answers:
            summary += f"**Empresa:** {answers['nombre_empresa']}\n"
        if "ubicacion" in answers:
            summary += f"**Ubicación:** {answers['ubicacion']}\n"

        # Información sobre agua
        if "costo_agua" in answers:
            summary += f"**Costo del agua:** {answers['costo_agua']}\n"
        if "cantidad_agua_consumida" in answers:
            summary += f"**Consumo de agua:** {answers['cantidad_agua_consumida']}\n"
        if "cantidad_agua_residual" in answers:
            summary += f"**Generación de agua residual:** {answers['cantidad_agua_residual']}\n"

        # Añadir más campos según corresponda
        if "num_personas" in answers:
            summary += f"**Personal/visitantes:** {answers['num_personas']}\n"
        if "sistema_existente" in answers:
            summary += f"**Sistema existente:** {'Sí' if answers['sistema_existente'] == 'Sí' else 'No'}\n"

        summary += "\n¿Esta información es correcta? Si hay algo que desees modificar, házme saber. De lo contrario, continuaremos con las siguientes preguntas.\n\n"

        # Obtener la siguiente pregunta para mostrarla después del resumen
        next_question = questionnaire_service.get_next_question(state)
        if next_question:
            state.current_question_id = next_question["id"]
            summary += self._format_question(next_question)

        return summary

    def _generate_preliminary_analysis(self, conversation: Conversation) -> str:
        """Genera un análisis preliminar basado en los datos recopilados"""
        state = conversation.questionnaire_state
        answers = state.answers

        analysis = "# Análisis Preliminar de Necesidades de Tratamiento\n\n"

        analysis += "Basado en la información que has proporcionado, puedo ofrecer el siguiente análisis preliminar:\n\n"

        # Identificar factores clave según el sector
        analysis += "## Factores clave identificados\n\n"

        # Añadir factores según el tipo de industria
        if state.sector == "Industrial" and state.subsector == "Textil":
            # Factores específicos de la industria textil
            analysis += "- **Aguas residuales con colorantes**: Típico de la industria textil, requiere tratamiento para remoción de color.\n"
            if "parametros_agua" in answers and isinstance(
                answers["parametros_agua"], dict
            ):
                if "color" in answers["parametros_agua"]:
                    analysis += f"- **Alta carga de colorantes**: El agua residual textil contiene colorantes que requieren tratamiento específico.\n"
                if "dqo" in answers["parametros_agua"]:
                    analysis += f"- **DQO elevada**: {answers['parametros_agua']['dqo']} indica necesidad de tratamiento biológico avanzado.\n"

        # Proponer tren de tratamiento preliminar
        analysis += "\n## Propuesta preliminar de tratamiento\n\n"
        analysis += "Para tu caso especifico, recomendaria un sistema de tratamiento con las siguientes etapas:\n\n"

        # Información de consumo de agua
        if "cantidad_agua_consumida" in answers:
            analysis += f"- **Consumo de agua**: {answers['cantidad_agua_consumida']} indica una operación de {self._classify_water_consumption(answers['cantidad_agua_consumida'])} escala.\n"

        # Información de aguas residuales
        if "cantidad_agua_residual" in answers:
            analysis += f"- **Generación de agua residual**: {answers['cantidad_agua_residual']} requerirá un sistema de tratamiento dimensionado adecuadamente.\n"

        # Objetivos de reúso
        if "objetivo_reuso" in answers:
            analysis += "- **Oportunidades de reúso**: Basado en tus objetivos, podemos diseñar un sistema que permita la reutilización del agua tratada.\n"

        # Proponer tren de tratamiento preliminar
        analysis += "\n## Propuesta preliminar de tratamiento\n\n"
        analysis += "Para tu caso específico, recomendaría un sistema de tratamiento con las siguientes etapas:\n\n"

        # Ejemplo de tren de tratamiento para textil
        if state.sector == "Industrial" and state.subsector == "Textil":
            analysis += (
                "1. **Pretratamiento**: Cribado y homogeneización del agua residual\n"
            )
            analysis += "2. **Tratamiento primario**: Sistema DAF (Flotación por Aire Disuelto) para remoción de sólidos y parte del color\n"
            analysis += "3. **Tratamiento secundario**: Reactor biológico de membrana (MBR) para reducción de DBO y DQO\n"
            analysis += "4. **Tratamiento terciario**: Oxidación avanzada para remoción de color residual\n"
            analysis += "5. **Pulido final**: Filtración por carbón activado y/o ósmosis inversa (según necesidades de reúso)\n"
        else:
            # Tratamiento genérico para otros sectores
            analysis += "1. **Pretratamiento**: Cribado y homogeneización\n"
            analysis += "2. **Tratamiento primario**: Coagulación/floculación\n"
            analysis += "3. **Tratamiento secundario**: Sistema biológico\n"
            analysis += "4. **Tratamiento terciario**: Filtración y desinfección\n"

        analysis += "\n## Próximos pasos\n\n"
        analysis += "Para ofrecerte una propuesta detallada, me gustaría confirmar algunos datos adicionales o hacer algunas aclaraciones:\n\n"

        # Identificar datos faltantes críticos
        missing_data = []
        if "parametros_agua" not in answers or not answers["parametros_agua"]:
            missing_data.append(
                "**Parámetros de calidad del agua**: Sería ideal contar con datos de DQO, DBO, sólidos suspendidos, etc."
            )
        if "objetivo_principal" not in answers:
            missing_data.append(
                "**Objetivo principal del proyecto**: ¿Es cumplimiento normativo, reducción de costos, sostenibilidad, u otro?"
            )
        if "presupuesto" not in answers:
            missing_data.append(
                "**Presupuesto estimado**: Nos ayudaría a ajustar la propuesta a tus posibilidades económicas."
            )

        if missing_data:
            analysis += "**Información adicional que sería útil:**\n"
            for item in missing_data:
                analysis += f"- {item}\n"

        analysis += "\n¿Te gustaría que proceda a generar una propuesta completa con la información disponible, o prefieres proporcionar algunos datos adicionales antes?"

        return analysis

    def _classify_water_consumption(self, consumption_str: str) -> str:
        """Clasifica el consumo de agua en pequeña, mediana o gran escala"""
        # Extraer valor numérico con regex
        import re

        match = re.search(r"(\d+[\.,]?\d*)", consumption_str)
        if not match:
            return "media"

        value = float(match.group(1).replace(",", "."))

        # Clasificar según unidades comunes (m³/día)
        if "m3" in consumption_str.lower() or "m³" in consumption_str:
            if "día" in consumption_str.lower() or "dia" in consumption_str.lower():
                if value < 50:
                    return "pequeña"
                elif value < 200:
                    return "mediana"
                else:
                    return "gran"

        # Por defecto
        return "media"

    def _handle_post_questionnaire(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """Maneja preguntas después de completar el cuestionario"""
        # Identificar el tipo de pregunta/solicitud
        if any(
            keyword in user_message.lower()
            for keyword in ["costo", "precio", "presupuesto", "inversión"]
        ):
            return self._respond_about_costs(conversation)
        elif any(
            keyword in user_message.lower()
            for keyword in ["tiempo", "plazo", "implementación", "cuándo"]
        ):
            return self._respond_about_timeline(conversation)
        elif any(
            keyword in user_message.lower()
            for keyword in ["tecnología", "equipo", "sistema", "cómo funciona"]
        ):
            return self._respond_about_technology(conversation)
        else:
            # Respuesta general sobre la propuesta
            return (
                "Basado en la información que has proporcionado, hemos desarrollado una propuesta personalizada "
                "para tu sistema de tratamiento de aguas residuales. La propuesta incluye el dimensionamiento, "
                "tecnologías recomendadas, costos estimados y potencial retorno de inversión.\n\n"
                "Para consultar la propuesta completa, escribe 'descargar propuesta' o haz clic en el enlace "
                "que te proporcioné anteriormente.\n\n"
                "¿Hay algún aspecto específico de la propuesta sobre el que te gustaría obtener más información?"
            )

    def _respond_about_costs(self, conversation: Conversation) -> str:
        """Proporciona información sobre costos de la solución"""
        return (
            "## Información sobre Costos\n\n"
            "La inversión inicial (CAPEX) para un sistema de tratamiento como el propuesto para tu caso suele estar "
            "en el rango de $80,000 a $150,000 USD, dependiendo de la capacidad específica y las tecnologías implementadas.\n\n"
            "Los costos operativos (OPEX) suelen estar entre $3,000 y $4,500 USD mensuales, incluyendo energía, "
            "productos químicos, mantenimiento y personal.\n\n"
            "El retorno de inversión típico para estos sistemas en la industria textil se sitúa entre 1.5 y 3 años, "
            "gracias al ahorro en agua fresca y tarifas de descarga.\n\n"
            "Para obtener una estimación detallada específica para tu proyecto, por favor revisa la propuesta completa. "
            "¿Te gustaría descargar la propuesta en PDF?"
        )

    def _respond_about_timeline(self, conversation: Conversation) -> str:
        """Proporciona información sobre los plazos de implementación"""
        return (
            "## Plazos de Implementación\n\n"
            "La implementación de un sistema de tratamiento como el propuesto generalmente sigue estas etapas y plazos:\n\n"
            "1. **Diseño detallado**: 2-4 semanas\n"
            "2. **Fabricación de equipos**: 6-10 semanas\n"
            "3. **Instalación**: 3-6 semanas\n"
            "4. **Puesta en marcha y ajustes**: 2-3 semanas\n\n"
            "En total, desde la aprobación del proyecto hasta tener el sistema operativo, "
            "el plazo típico es de 13 a 23 semanas (aproximadamente 3-6 meses).\n\n"
            "¿Necesitas que el sistema esté operativo en alguna fecha específica?"
        )

    def _respond_about_technology(self, conversation: Conversation) -> str:
        """Proporciona información sobre las tecnologías propuestas"""
        # Adaptar según el sector/subsector
        if (
            conversation.questionnaire_state.sector == "Industrial"
            and conversation.questionnaire_state.subsector == "Textil"
        ):
            return (
                "## Tecnologías Recomendadas para Industria Textil\n\n"
                "El sistema propuesto incluye estas tecnologías principales:\n\n"
                "1. **Sistema DAF (Flotación por Aire Disuelto)**: Elimina hasta el 95% de los sólidos suspendidos y parte "
                "de los colorantes mediante microburbujas que adhieren los contaminantes y los llevan a la superficie.\n\n"
                "2. **Reactor Biológico de Membrana (MBR)**: Combina tratamiento biológico con filtración por membrana, "
                "logrando reducción de DBO/DQO superior al 95% y produciendo un efluente de alta calidad.\n\n"
                "3. **Sistema de Oxidación Avanzada**: Utiliza procesos químicos o UV para degradar colorantes "
                "persistentes y compuestos orgánicos difíciles de eliminar por métodos biológicos.\n\n"
                "4. **Ósmosis Inversa (opcional)**: Para aplicaciones que requieren agua de muy alta calidad "
                "para su reutilización en procesos críticos.\n\n"
                "¿Te gustaría obtener más información sobre alguna de estas tecnologías en particular?"
            )
        else:
            # Respuesta genérica para otros sectores
            return (
                "## Tecnologías de Tratamiento Recomendadas\n\n"
                "El sistema propuesto se basa en un enfoque de múltiples barreras, con tecnologías adaptadas "
                "específicamente para tu sector y necesidades.\n\n"
                "Las tecnologías incluyen pretratamiento físico, tratamiento fisicoquímico, "
                "sistemas biológicos avanzados y, según necesidad, tratamiento terciario para "
                "aplicaciones de reúso específicas.\n\n"
                "Para más detalles sobre las tecnologías recomendadas para tu caso específico, "
                "te recomiendo revisar la propuesta completa. ¿Te gustaría descargarla ahora?"
            )

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
                    state.answers["sector_selection"] = sector
                    break

            # Verificar respuestas numéricas (1-4)
            if user_message.strip() in ["1", "2", "3", "4"]:
                index = int(user_message.strip()) - 1
                if 0 <= index < len(sectors):
                    state.sector = sectors[index]
                    state.answers["sector_selection"] = sectors[index]

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
                    state.answers["subsector_selection"] = subsector
                    break

            # Verificar respuestas numéricas
            if user_message.strip().isdigit():
                index = int(user_message.strip()) - 1
                if 0 <= index < len(subsectors):
                    state.subsector = subsectors[index]
                    state.answers["subsector_selection"] = subsectors[index]

        # Si tenemos una pregunta actual, intentar guardar la respuesta
        elif (
            state.current_question_id and state.current_question_id not in state.answers
        ):
            # Guardar respuesta directamente si no es option múltiple/selección
            question_key = f"{state.sector}_{state.subsector}"
            questions = questionnaire_service.questionnaire_data.get(
                "questions", {}
            ).get(question_key, [])

            # Encontrar la pregunta actual
            current_question = None
            for q in questions:
                if q.get("id") == state.current_question_id:
                    current_question = q
                    break

            # Si encontramos la pregunta, procesar la respuesta
            if current_question:
                q_type = current_question.get("type", "text")

                # Procesar según el tipo de pregunta
                if q_type == "multiple_choice" and "options" in current_question:
                    # Si es respuesta numérica, convertir a la opción correspondiente
                    if user_message.strip().isdigit():
                        option_index = int(user_message.strip()) - 1
                        if 0 <= option_index < len(current_question["options"]):
                            state.answers[state.current_question_id] = current_question[
                                "options"
                            ][option_index]
                        else:
                            state.answers[state.current_question_id] = user_message
                    else:
                        state.answers[state.current_question_id] = user_message

                elif q_type == "multiple_select" and "options" in current_question:
                    # Para múltiples selecciones, intentar identificar opciones seleccionadas
                    selected_options = []

                    # Comprobar respuestas numéricas separadas por comas
                    if re.match(r"^\d+(,\s*\d+)*$", user_message):
                        indices = [
                            int(idx.strip()) - 1 for idx in user_message.split(",")
                        ]
                        for idx in indices:
                            if 0 <= idx < len(current_question["options"]):
                                selected_options.append(
                                    current_question["options"][idx]
                                )
                    else:
                        # Guardar respuesta textual
                        selected_options = [user_message]

                    state.answers[state.current_question_id] = selected_options

                else:
                    # Para preguntas de texto, guardar directamente
                    state.answers[state.current_question_id] = user_message

                # La respuesta está guardada, avanzar a la siguiente pregunta en el siguiente turno

        # Detectar si el cuestionario ha terminado y se ha generado una propuesta
        proposal_indicators = [
            "RESUMEN DE LA PROPUESTA",
            "ANALISIS ECONOMICO",
            "DESCARGAR PROPUESTA EN PDF",
        ]

        if any(indicator in ai_response for indicator in proposal_indicators):
            state.completed = True

            # Reemplazar el placeholder CONVERSATION_ID con el ID real de la conversación
            if "CONVERSATION_ID" in ai_response and conversation.id:
                update_response = ai_response.replace(
                    "CONVERSATION_ID", conversation.id
                )

                # Necesitamos actualizar el mensaje en conversation
                if (
                    conversation.messages
                    and conversation.messages[-1].role == "assistant"
                ):
                    conversation.messages[-1].content = update_response

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

    def _format_question(self, question: Dict[str, Any]) -> str:
        """
        Formatea una pregunta del cuestionario con un enfoque conversacional
        siguiendo exactamente la estructura deseada.
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

        # Añadir sugerencia de documentos para preguntas especificas
        question_id = question.get("id", "")

        # Lista de preguntas donde sugerir documentos
        document_suggestion_questions = [
            "sistema_existente",
            "descripcion_sistema",
            "parametros_agua",
            "agua_potable_analisis",
            "recibos agua",
            "ubicacion",
        ]

        if question_id in document_suggestion_questions:
            document_suggestion = ""

            if (
                question_id == "sistema_existente"
                or question_id == "descripcion_sistema"
            ):
                document_suggestion = "\n\n*Si dispones de algún diagrama, imagen o documento técnico de tu sistema actual, puedes compartirlo para un análisis más preciso.*"
            elif (
                question_id == "parametros_agua"
                or question_id == "agua_potable_analisis"
            ):
                document_suggestion = "\n\n*Si cuentas con análisis de laboratorio o informes técnicos de la calidad del agua, puedes adjuntarlos para un diseño más exacto de la solución.*"
            elif question_id == "recibos_agua":
                document_suggestion = "\n\n*Puedes adjuntar una foto o escaneo de tus recibos de agua para un cálculo más preciso del potencial ahorro.*"
            elif question_id == "ubicacion":
                document_suggestion = "\n\n*Si tienes un plano o imagen de las instalaciones, puedes compartirlo para ayudarnos a entender mejor el contexto.*"

            message += document_suggestion

        return message

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
                1. Usa formato Markdown para mejorar la presentacion y claridad del cotenido.
                2. Utiliza encabezados Markdown (# para titulos principales, ## para subtitulos) para estructurar el texto.
                3. Resalta las PREGUNTAS usando encabezados de nivel 2 (##) y colócalas SIEMPRE al final del mensaje.
                4. Usa listas con viñetas (- o *) para enumerar opciones cuando sea apropiado.
                5. tiliza **negrita** para enfatizar información importante.
                6. Utiliza *cursiva* para destacar datos interesantes.
                7. Puedes usar tablas Markdown para presentar informacion comparativa
                8. Para los enlaces, usa el formato [text] (url).
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
