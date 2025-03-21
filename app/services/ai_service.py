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

        # Atributos para mantener el contexto entre llamadas
        self.current_sector = None
        self.current_subsector = None

    def _detect_questionnaire_intent(self, message: str) -> bool:
        """
        Como el cuestionario siempre debe iniciarse, este método siempre devuelve True
        """
        return True  # Siempre iniciar el cuestionario, sin importar el mensaje

    def get_initial_greeting(self) -> str:
        """
        Devuelve el mensaje de saludo inicial y primera pregunta del cuestionario
        """
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

    def format_response_with_questions(
        self,
        previous_answer_comment,
        interesting_fact,
        question_context,
        question_text,
        options=None,
        document_suggestion=None,
    ):
        """
        Formatea una respuesta siguiendo la estructura establecida en el prompt original

        Args:
            previous_answer_comment: Comentario sobre la respuesta anterior
            interesting_fact: Dato interesante relacionado con el sector/industria
            question_context: Explicación de por qué la pregunta es importante
            question_text: Texto de la pregunta
            options: Lista de opciones para preguntas de selección múltiple
            document_suggestion: Sugerencia para subir un documento (opcional)

        Returns:
            str: Respuesta formateada según la estructura requerida
        """
        # 1. Comentario sobre respuesta anterior
        response = f"{previous_answer_comment}\n\n"

        # 2. Dato interesante en cursiva
        if interesting_fact:
            response += f"*{interesting_fact}*\n\n"

        # 3. Explicación de por qué la pregunta es importante
        if question_context:
            response += f"{question_context}\n\n"

        # 4. La pregunta al final, en negrita y precedida por "PREGUNTA"
        response += f"**PREGUNTA: {question_text}**\n\n"

        # 5. Opciones numeradas para preguntas de opción múltiple
        if options:
            for i, option in enumerate(options, 1):
                response += f"{i}. {option}\n"

        # Añadir sugerencia de documento si es aplicable
        if document_suggestion:
            response += f"\n\n{document_suggestion}"

        return response

    def should_suggest_document(self, question_id: str) -> Optional[str]:
        """
        Determina si se debe sugerir subir un documento para esta pregunta
        y devuelve el texto de la sugerencia

        Args:
            question_id: ID de la pregunta actual

        Returns:
            str: Texto de sugerencia o None si no aplica
        """
        suggestions = {
            "parametros_agua": """
### 📄 Análisis de Laboratorio

Si dispone de análisis recientes de su agua residual, puede subirlos ahora usando el botón de adjuntar archivo.
Estos datos nos permitirán diseñar una solución mucho más precisa y eficiente para su caso específico.
""",
            "costo_agua": """
### 📄 Facturas de Agua

Si tiene a mano recibos recientes de agua, puede subirlos para un análisis más preciso de costos y potenciales ahorros.
Esta información mejorará significativamente la exactitud de nuestros cálculos de retorno de inversión.
""",
            "sistema_existente": """
### 📄 Documentación Técnica

Si dispone de documentación, diagramas o fotografías de su sistema actual, nos ayudaría enormemente a entender 
su infraestructura existente y cómo integrar nuestra solución de la manera más eficiente.
""",
            "recibos_agua": """
### 📄 Historial de Consumo

Compartir sus recibos de agua de los últimos meses nos permitirá analizar patrones de consumo
y calcular con mayor precisión los ahorros potenciales que podría obtener.
""",
            "agua_potable_analisis": """
### 📄 Análisis de Agua Actual

Si cuenta con análisis de la calidad de su agua actual, subir estos documentos nos permitirá
entender mejor las características específicas y diseñar una solución más efectiva.
""",
        }

        return suggestions.get(question_id)

    def _generate_previous_answer_comment(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Genera un comentario personalizado sobre la respuesta anterior del usuario

        Args:
            conversation: Conversación actual
            user_message: Mensaje del usuario

        Returns:
            str: Comentario personalizado según el contexto
        """
        # Obtener el ID de la pregunta que se acaba de responder
        prev_question_id = conversation.questionnaire_state.current_question_id
        sector = conversation.questionnaire_state.sector
        subsector = conversation.questionnaire_state.subsector

        # Si no hay pregunta previa, es el inicio del cuestionario
        if not prev_question_id:
            return "Gracias por contactarnos. Me ayudará conocer algunos detalles sobre su empresa para ofrecerle la mejor solución personalizada."

        # Comentarios específicos para preguntas comunes
        if prev_question_id == "sector_selection":
            return f"Gracias por indicar que opera en el sector {sector}. Esto nos permite entender el contexto general de sus necesidades de tratamiento de agua."

        elif prev_question_id == "subsector_selection":
            return f"Excelente. El subsector {subsector} dentro del sector {sector} presenta desafíos y oportunidades específicas en el tratamiento de aguas residuales."

        elif prev_question_id == "nombre_empresa":
            empresa = conversation.questionnaire_state.answers.get(
                "nombre_empresa", "su empresa"
            )
            return f"Gracias por compartir que su empresa es {empresa}. Personalizaremos nuestra propuesta para adaptarla a sus necesidades específicas."

        elif prev_question_id == "ubicacion":
            ubicacion = conversation.questionnaire_state.answers.get(
                "ubicacion", "su ubicación"
            )
            return f"Entendido. La ubicación en {ubicacion} es importante ya que las regulaciones y condiciones ambientales varían según la región."

        elif prev_question_id == "costo_agua":
            costo = conversation.questionnaire_state.answers.get(
                "costo_agua", "el costo indicado"
            )
            return f"El costo de {costo} es un dato clave para calcular el retorno de inversión y los ahorros potenciales de un sistema de reciclaje."

        elif prev_question_id == "cantidad_agua_consumida":
            consumo = conversation.questionnaire_state.answers.get(
                "cantidad_agua_consumida", "el consumo indicado"
            )
            return f"Un consumo de {consumo} nos permite dimensionar adecuadamente la solución y calcular los beneficios económicos potenciales."

        elif prev_question_id == "cantidad_agua_residual":
            residual = conversation.questionnaire_state.answers.get(
                "cantidad_agua_residual", "la cantidad indicada"
            )
            return f"Perfecto. La generación de {residual} de agua residual es fundamental para el diseño del sistema de tratamiento."

        elif prev_question_id == "parametros_agua":
            return "Los parámetros del agua que ha proporcionado son cruciales para determinar las tecnologías y procesos de tratamiento específicos que necesita."

        elif prev_question_id == "objetivo_principal":
            objetivo = conversation.questionnaire_state.answers.get(
                "objetivo_principal", "su objetivo"
            )
            return f"Comprendo que su objetivo principal es {objetivo}. Esto guiará nuestra propuesta hacia los aspectos más relevantes para usted."

        elif prev_question_id == "objetivo_reuso":
            return "Sus objetivos de reúso de agua nos ayudan a diseñar un sistema que produzca agua con la calidad adecuada para las aplicaciones que necesita."

        elif prev_question_id == "sistema_existente":
            if "sistema_existente" in conversation.questionnaire_state.answers:
                respuesta = conversation.questionnaire_state.answers.get(
                    "sistema_existente"
                )
                if respuesta == "Sí" or respuesta == "Si" or respuesta == "1":
                    return "Es útil saber que ya cuenta con un sistema. Podemos evaluar cómo mejorarlo o complementarlo para optimizar sus resultados."
                else:
                    return "Entiendo que actualmente no cuenta con un sistema de tratamiento. Diseñaremos una solución completa desde cero."

        # Para otras preguntas, generar un comentario genérico pero positivo
        return "Gracias por su respuesta. Cada dato que proporciona nos acerca más a diseñar la solución óptima para sus necesidades específicas."

    def _generate_interim_summary(self, conversation: Conversation) -> str:
        """
        Genera un resumen intermedio de la información recopilada hasta el momento

        Args:
            conversation: Conversación actual

        Returns:
            str: Texto del resumen formateado
        """
        state = conversation.questionnaire_state
        answers = state.answers
        sector = state.sector
        subsector = state.subsector

        summary = f"""
## Resumen de la Información Recopilada

Hemos avanzado en la recopilación de datos para su solución de tratamiento de agua. A continuación, un resumen de la información proporcionada hasta el momento:

### Datos Básicos
- **Sector**: {sector}
- **Subsector**: {subsector}
"""

        # Añadir respuestas clave en orden lógico
        key_fields = [
            ("nombre_empresa", "Empresa/Proyecto"),
            ("ubicacion", "Ubicación"),
            ("costo_agua", "Costo del agua"),
            ("cantidad_agua_consumida", "Consumo de agua"),
            ("cantidad_agua_residual", "Generación de agua residual"),
            ("objetivo_principal", "Objetivo principal"),
            ("objetivo_reuso", "Objetivos de reúso"),
            ("sistema_existente", "Sistema existente"),
        ]

        info_added = False
        for field_id, field_name in key_fields:
            if field_id in answers:
                summary += f"- **{field_name}**: {answers[field_id]}\n"
                info_added = True

        if not info_added:
            summary += "- Aún no se han recopilado datos específicos.\n"

        # Añadir parámetros técnicos si existen
        if "parametros_agua" in answers and isinstance(
            answers["parametros_agua"], dict
        ):
            summary += "\n### Parámetros Técnicos\n"
            for param, value in answers["parametros_agua"].items():
                summary += f"- **{param}**: {value}\n"

        # Dato interesante relevante
        fact = questionnaire_service.get_random_fact(sector, subsector)
        if fact:
            summary += f"\n*{fact}*\n"

        # Confirmación y siguiente pregunta
        summary += """
¿Es correcta esta información? Si necesita realizar alguna corrección, por favor indíquelo.
De lo contrario, continuaremos con las siguientes preguntas para completar su perfil de necesidades.

**PREGUNTA: ¿Confirma que la información anterior es correcta?**
1. Sí, la información es correcta
2. No, necesito corregir algo
"""

        return summary

    def _update_questionnaire_state(
        self, conversation: Conversation, user_message: str
    ) -> None:
        """
        Actualiza el estado del cuestionario basado en la respuesta del usuario

        Args:
            conversation: Conversación actual
            user_message: Mensaje del usuario
        """
        state = conversation.questionnaire_state

        # Si hay una pregunta actual, procesar la respuesta
        if state.current_question_id:
            # Si es selección de sector
            if state.current_question_id == "sector_selection":
                sector = self._extract_sector(user_message)
                if sector:
                    state.sector = sector
                    state.answers[state.current_question_id] = sector
                    # Incrementar el contador si se añade atributo questions_answered a QuestionnaireState
                    if hasattr(state, "questions_answered"):
                        state.questions_answered += 1

            # Si es selección de subsector
            elif state.current_question_id == "subsector_selection":
                subsector = self._extract_subsector(user_message, state.sector)
                if subsector:
                    state.subsector = subsector
                    state.answers[state.current_question_id] = subsector
                    # Incrementar el contador si se añade atributo questions_answered a QuestionnaireState
                    if hasattr(state, "questions_answered"):
                        state.questions_answered += 1

            # Si es una pregunta de confirmación de resumen
            elif state.current_question_id == "confirm_summary":
                # Verificar si el usuario confirma o quiere corregir algo
                if self._is_affirmative_response(user_message):
                    # El usuario confirma, continuamos con el cuestionario
                    state.current_question_id = (
                        state.previous_question_id
                    )  # Para obtener la siguiente pregunta
                else:
                    # El usuario quiere corregir algo, ofreceremos opciones
                    return  # La lógica para correcciones se manejará en otro método

            # Para preguntas de opción múltiple
            elif self._is_multiple_choice_question(
                state.current_question_id, state.sector, state.subsector
            ):
                # Convertir respuesta numérica a texto de opción
                answer = self._extract_option_from_multiple_choice(
                    state.current_question_id,
                    user_message,
                    state.sector,
                    state.subsector,
                )
                if answer:
                    state.answers[state.current_question_id] = answer
                    # Incrementar el contador si se añade atributo questions_answered a QuestionnaireState
                    if hasattr(state, "questions_answered"):
                        state.questions_answered += 1
                else:
                    # Si no se pudo extraer una opción, guardar la respuesta literal
                    state.answers[state.current_question_id] = user_message
                    # Incrementar el contador si se añade atributo questions_answered a QuestionnaireState
                    if hasattr(state, "questions_answered"):
                        state.questions_answered += 1

            # Para cualquier otra pregunta, guardar la respuesta directamente
            else:
                state.answers[state.current_question_id] = user_message
                # Incrementar el contador si se añade atributo questions_answered a QuestionnaireState
                if hasattr(state, "questions_answered"):
                    state.questions_answered += 1

    def _is_multiple_choice_question(
        self, question_id: str, sector: str, subsector: str
    ) -> bool:
        """
        Determina si una pregunta es de opción múltiple

        Args:
            question_id: ID de la pregunta
            sector: Sector seleccionado
            subsector: Subsector seleccionado

        Returns:
            bool: True si es pregunta de opción múltiple
        """
        if question_id in ["sector_selection", "subsector_selection"]:
            return True

        # Obtener las preguntas para este sector/subsector
        questions_key = f"{sector}_{subsector}"
        questions = questionnaire_service.questionnaire_data.get("questions", {}).get(
            questions_key, []
        )

        for q in questions:
            if q.get("id") == question_id and q.get("type") in [
                "multiple_choice",
                "multiple_select",
            ]:
                return True

        return False

    def _extract_option_from_multiple_choice(
        self, question_id: str, user_message: str, sector: str, subsector: str
    ) -> Optional[str]:
        """
        Extrae la opción seleccionada de una pregunta de opción múltiple

        Args:
            question_id: ID de la pregunta
            user_message: Mensaje del usuario
            sector: Sector seleccionado
            subsector: Subsector seleccionado

        Returns:
            str: Texto de la opción seleccionada o None si no se puede determinar
        """
        # Casos especiales
        if question_id == "sector_selection":
            return self._extract_sector(user_message)
        elif question_id == "subsector_selection":
            return self._extract_subsector(user_message, sector)

        # Obtener opciones para esta pregunta
        questions_key = f"{sector}_{subsector}"
        questions = questionnaire_service.questionnaire_data.get("questions", {}).get(
            questions_key, []
        )

        for q in questions:
            if q.get("id") == question_id and "options" in q:
                options = q["options"]

                # Verificar si es una respuesta numérica
                if user_message.strip().isdigit():
                    index = int(user_message.strip()) - 1
                    if 0 <= index < len(options):
                        return options[index]

                # Buscar coincidencia textual
                user_message_lower = user_message.lower()
                for option in options:
                    if option.lower() in user_message_lower:
                        return option

        return None

    def _is_affirmative_response(self, message: str) -> bool:
        """
        Determina si una respuesta es afirmativa

        Args:
            message: Mensaje del usuario

        Returns:
            bool: True si la respuesta es afirmativa
        """
        affirmative_terms = [
            "sí",
            "si",
            "s",
            "yes",
            "correcto",
            "exacto",
            "cierto",
            "afirmativo",
            "está bien",
            "esta bien",
            "confirmo",
            "1",
            "ok",
            "okay",
            "vale",
            "proceder",
        ]

        message_lower = message.lower()

        return any(term in message_lower for term in affirmative_terms)

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
        for sector in sectors:
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

    def _get_next_question(
        self, conversation: Conversation
    ) -> Optional[Dict[str, Any]]:
        """Obtiene la siguiente pregunta según el estado del cuestionario"""
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

        # Si estamos en un resumen, preguntar confirmación
        if state.current_question_id == "confirm_summary":
            return {
                "id": "confirm_summary",
                "text": "¿Confirma que la información proporcionada es correcta?",
                "type": "multiple_choice",
                "options": [
                    "Sí, la información es correcta",
                    "No, necesito corregir algo",
                ],
                "explanation": "Es importante verificar que la información recopilada sea precisa para diseñar la mejor solución para su caso.",
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

    def _handle_post_proposal_questions(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Maneja preguntas específicas después de presentar la propuesta final

        Args:
            conversation: Conversación actual
            user_message: Mensaje del usuario

        Returns:
            str: Respuesta a la pregunta post-propuesta
        """
        # Detectar tipo de pregunta
        message_lower = user_message.lower()

        # Preguntas sobre tecnología
        if any(
            tech in message_lower
            for tech in [
                "tecnología",
                "tecnologia",
                "sistema",
                "tratamiento",
                "proceso",
                "cómo funciona",
                "como funciona",
            ]
        ):
            return """
## Tecnología de Tratamiento

El sistema propuesto utiliza un enfoque multietapa que incluye:

1. **Pretratamiento**: Elimina sólidos gruesos y estabiliza el flujo para un tratamiento óptimo.
2. **Tratamiento primario**: Utiliza procesos físico-químicos para remover sólidos suspendidos y compuestos específicos.
3. **Tratamiento secundario**: Emplea procesos biológicos optimizados para degradar compuestos orgánicos.
4. **Tratamiento terciario**: Aplica filtración avanzada y desinfección para conseguir la calidad requerida.

Cada etapa está dimensionada específicamente para sus volúmenes y características de agua, maximizando la eficiencia y minimizando costos operativos.

¿Hay algún aspecto específico de la tecnología que le gustaría conocer con más detalle?
"""

        # Preguntas sobre costos
        elif any(
            cost in message_lower
            for cost in [
                "costo",
                "precio",
                "inversión",
                "inversion",
                "financiamiento",
                "financiacion",
                "pagar",
                "económico",
                "economico",
            ]
        ):
            return """
## Detalles Económicos

La propuesta incluye:

- **Inversión inicial (CAPEX)**: Incluye equipos, instalación, programación y puesta en marcha.
- **Costos operativos (OPEX)**: Incluye consumo energético, químicos, mantenimiento y mano de obra.
- **Retorno de inversión**: Basado en ahorros directos (agua, descargas) e indirectos (cumplimiento, imagen).

Ofrecemos diferentes opciones de financiamiento, incluyendo compra directa, leasing o modalidades de pago por uso (OPEX puro).

El análisis detallado del ROI está disponible en el documento PDF de la propuesta. ¿Le gustaría conocer opciones específicas de financiamiento para su caso?
"""

        # Preguntas sobre implementación
        elif any(
            impl in message_lower
            for impl in [
                "implementar",
                "instalar",
                "tiempo",
                "plazo",
                "cuando",
                "cuándo",
                "espacio",
                "construcción",
                "construir",
            ]
        ):
            return """
## Implementación del Sistema

El proceso de implementación típicamente incluye:

1. **Fase de diseño detallado**: 2-4 semanas
2. **Fabricación y preparación**: 6-10 semanas
3. **Instalación in situ**: 2-4 semanas
4. **Puesta en marcha y ajustes**: 1-2 semanas

El espacio requerido depende de su volumen de agua, pero para su caso estimamos aproximadamente 50-100 m² para la instalación completa.

Nuestro equipo maneja todo el proceso, incluyendo permisos, instalación y capacitación de personal. ¿Tiene alguna restricción particular de tiempo o espacio para la implementación?
"""

        # Otras preguntas o comentarios
        else:
            return """
Gracias por su interés en nuestra propuesta. 

Para cualquier otra consulta específica sobre aspectos técnicos, económicos, de implementación o mantenimiento, estamos a su disposición. Nuestra propuesta es totalmente personalizable y podemos ajustar cualquier parámetro para satisfacer sus necesidades particulares.

Si desea avanzar con el proyecto, el siguiente paso sería una reunión técnica para afinar detalles y establecer un cronograma de implementación. También podemos organizar una visita a instalaciones similares para que pueda ver nuestras soluciones en funcionamiento.

¿En qué otro aspecto podemos ayudarle?
"""

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

    def generate_subsector_question(self, sector: str) -> str:
        """
        Genera la pregunta para seleccionar el subsector basado en el sector elegido

        Args:
            sector: Sector seleccionado

        Returns:
            str: Pregunta formateada sobre el subsector
        """
        subsector_options = questionnaire_service.get_subsectors(sector)
        interesting_fact = questionnaire_service.get_random_fact(sector)

        return self.format_response_with_questions(
            f"Gracias por indicar que opera en el sector {sector}. Esto nos permite entender el contexto general de sus necesidades de tratamiento de agua.",
            interesting_fact,
            "Cada subsector tiene características y necesidades específicas para el tratamiento de agua. Identificar su subsector nos permitirá personalizar aún más la solución.",
            f"¿Cuál es el subsector específico dentro de {sector}?",
            subsector_options,
        )

    async def handle_conversation(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Maneja el flujo de conversación siguiendo el cuestionario estructurado

        Args:
            conversation: Conversación actual
            user_message: Mensaje del usuario

        Returns:
            str: Respuesta formateada del chatbot
        """
        # Si el cuestionario está activo, procesarlo siguiendo la estructura requerida
        if conversation.is_questionnaire_active():
            # Actualizar el estado basado en la respuesta del usuario
            self._update_questionnaire_state(conversation, user_message)

            # Verificar si debemos mostrar un resumen intermedio
            if (
                hasattr(conversation.questionnaire_state, "questions_answered")
                and hasattr(conversation.questionnaire_state, "last_summary_at")
                and conversation.questionnaire_state.questions_answered > 0
                and conversation.questionnaire_state.questions_answered % 5 == 0
                and conversation.questionnaire_state.last_summary_at
                != conversation.questionnaire_state.questions_answered
            ):
                # Mostrar resumen cada 5 preguntas
                conversation.questionnaire_state.last_summary_at = (
                    conversation.questionnaire_state.questions_answered
                )
                return self._generate_interim_summary(conversation)

            # Obtener la siguiente pregunta
            next_question = self._get_next_question(conversation)

            # Si no hay más preguntas, generar propuesta final
            if not next_question:
                conversation.complete_questionnaire()
                proposal = questionnaire_service.generate_proposal(conversation)
                return questionnaire_service.format_proposal_summary(
                    proposal, conversation.id
                )

            # Generar respuesta estructurada para la siguiente pregunta
            interesting_fact = questionnaire_service.get_random_fact(
                conversation.questionnaire_state.sector,
                conversation.questionnaire_state.subsector,
            )

            previous_comment = self._generate_previous_answer_comment(
                conversation, user_message
            )
            question_context = next_question.get("explanation", "")
            question_text = next_question.get("text", "")

            options = None
            if (
                next_question.get("type") in ["multiple_choice", "multiple_select"]
                and "options" in next_question
            ):
                options = next_question["options"]

            # Verificar si debemos sugerir subir un documento
            document_suggestion = self.should_suggest_document(
                next_question.get("id", "")
            )

            # Formatear respuesta siguiendo exactamente la estructura requerida
            response = self.format_response_with_questions(
                previous_comment,
                interesting_fact,
                question_context,
                question_text,
                options,
                document_suggestion,
            )

            # Actualizar la pregunta actual para la siguiente interacción
            if hasattr(conversation.questionnaire_state, "previous_question_id"):
                conversation.questionnaire_state.previous_question_id = (
                    conversation.questionnaire_state.current_question_id
                )
            conversation.questionnaire_state.current_question_id = next_question.get(
                "id"
            )

            return response

        # Si el cuestionario está completado, manejar consultas post-propuesta
        elif conversation.is_questionnaire_completed():
            # Detectar si es una solicitud de PDF
            if self._is_pdf_request(user_message):
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
            return self._handle_post_proposal_questions(conversation, user_message)

        # Esto no debería ocurrir con el flujo modificado, pero por si acaso
        # Reiniciar el cuestionario
        conversation.start_questionnaire()
        return self.get_initial_greeting()

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

    # Los métodos de AIService básico ya están heredados
    # Aquí solo implementamos métodos adicionales o sobreescribimos cuando sea necesario

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
