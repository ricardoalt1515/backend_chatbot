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

# Lista de preguntas críticas que requieren respuestas completas
CRITICAL_QUESTIONS = {
    "cantidad_agua_consumida": {
        "explanation": "el consumo de agua es fundamental para dimensionar correctamente el sistema",
        "fallback": "un rango aproximado (por ejemplo: entre 10-50 m³/día) nos permitiría avanzar",
        "validation": lambda x: any(
            term in x.lower() for term in ["m3", "m³", "litro", "l/", "metro"]
        ),
    },
    "costo_agua": {
        "explanation": "el costo del agua es clave para calcular el retorno de inversión",
        "fallback": "incluso un valor aproximado nos ayudaría a estimar los ahorros potenciales",
        "validation": lambda x: any(
            term in x.lower() for term in ["$", "peso", "mxn", "usd", "dolar"]
        ),
    },
    "ubicacion": {
        "explanation": "la ubicación influye en las normativas aplicables y disponibilidad de recursos",
        "fallback": "al menos la ciudad o municipio nos permitiría contextualizar mejor la solución",
        "validation": lambda x: len(x) > 5,  # Verificación básica de longitud
    },
}


class AIService:
    """Servicio para interactuar con modelos de IA"""

    def __init__(self):
        super().__init__()
        # Inicializar el atributo questionnaire_service
        from app.services.questionnaire_service import questionnaire_service

        self.questionnaire_service = questionnaire_service
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
        question_id,
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
        # Obtener emoji apropidado para la pregunta
        emoji = self._select_emoji_for_question_type(question_id)

        # 1. Comentario sobre respuesta anterior
        response = f"{previous_answer_comment}\n\n"

        # 2. Dato interesante en cursiva
        if interesting_fact:
            response += f"💡 *{interesting_fact}*\n\n"

        # 3. Explicación de por qué la pregunta es importante
        if question_context:
            response += f"{question_context}\n\n"

        # 4. La pregunta al final, en negrita y precedida por emoji contextual
        response += f"**{emoji} PREGUNTA: {question_text}**\n\n"

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
            # Aquí está el cambio, usar el servicio importado directamente:
            subsectors = questionnaire_service.get_subsectors(state.sector)
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

    def _safe_extract_from_response(
        self, user_message: str, default_value: Any = None
    ) -> Any:
        """
        Extrae información de una respuesta del usuario de forma segura,
        manejando posibles errores

        Args:
            user_message: Mensaje del usuario
            default_value: Valor por defecto si no se puede extraer información

        Returns:
            Any: Información extraída o valor por defecto
        """
        try:
            # Intentar extraer información
            # Implementación específica según el contexto
            return extracted_value
        except Exception as e:
            logger.warning(f"Error al extraer información de respuesta: {e}")
            return default_value

    def _validate_questionnaire_state(self, conversation: Conversation) -> bool:
        """
        Valida que el estado del cuestionario sea consistente
        y recupera errores cuando sea posible

        Args:
            conversation: Conversación actual

        Returns:
            bool: True si el estado es válido, False en caso contrario
        """
        state = conversation.questionnaire_state

        # Verificar consistencia básica
        if (
            state.active
            and not state.sector
            and state.current_question_id != "sector_selection"
        ):
            # Inconsistencia: cuestionario activo sin sector y no estamos preguntando por sector
            logger.warning("Inconsistencia detectada: cuestionario activo sin sector")

            # Corregir el estado
            state.current_question_id = "sector_selection"
            return False

        if (
            state.active
            and state.sector
            and not state.subsector
            and state.current_question_id != "subsector_selection"
        ):
            # Inconsistencia: tenemos sector pero no subsector y no estamos preguntando por subsector
            logger.warning("Inconsistencia detectada: falta subsector")

            # Corregir el estado
            state.current_question_id = "subsector_selection"
            return False

        return True

    async def handle_conversation(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Método simplificado que aprovecha las capacidades inherentes del modelo
        en lugar de intentar replicarlas con lógica compleja.
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

            # Construir mensajes para la API
            messages = [
                {"role": "system", "content": settings.SYSTEM_PROMPT},
            ]

            # Añadir información de contexto actual como parte del sistema
            if (
                conversation.questionnaire_state.sector
                or conversation.questionnaire_state.subsector
            ):
                context_info = "Información de contexto:\n"
                if conversation.questionnaire_state.sector:
                    context_info += f"- Sector identificado: {conversation.questionnaire_state.sector}\n"
                if conversation.questionnaire_state.subsector:
                    context_info += (
                        f"- Subsector: {conversation.questionnaire_state.subsector}\n"
                    )

                # Añadir información de respuestas clave si existen
                answers = conversation.questionnaire_state.answers
                key_answers = []

                if "nombre_empresa" in answers:
                    key_answers.append(
                        f"- Nombre empresa/usuario: {answers['nombre_empresa']}"
                    )
                if "ubicacion" in answers:
                    key_answers.append(f"- Ubicación: {answers['ubicacion']}")
                if "costo_agua" in answers:
                    key_answers.append(f"- Costo agua: {answers['costo_agua']}")
                if "cantidad_agua_consumida" in answers:
                    key_answers.append(
                        f"- Consumo agua: {answers['cantidad_agua_consumida']}"
                    )

                if key_answers:
                    context_info += "\nDatos proporcionados:\n" + "\n".join(key_answers)

                messages.append({"role": "system", "content": context_info})

            # Añadir todo el historial de conversación relevante
            for msg in conversation.messages:
                if msg.role in [
                    "user",
                    "assistant",
                ]:  # Solo incluir mensajes de usuario y asistente
                    messages.append({"role": msg.role, "content": msg.content})

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

    def _handle_post_proposal_questions(
        self, conversation: Conversation, user_message: str
    ) -> str:
        """
        Maneja preguntas o solicitudes después de generar la propuesta

        Args:
            conversation: Conversación actual
            user_message: Mensaje del usuario

        Returns:
            str: Respuesta personalizada
        """
        # Detectar tipo de pregunta/solicitud
        message_lower = user_message.lower()

        # Solicitud de explicación técnica
        if any(
            term in message_lower
            for term in [
                "explicar",
                "detallar",
                "cómo funciona",
                "tecnología",
                "proceso",
            ]
        ):
            return self._generate_technical_explanation(conversation)

        # Solicitud de información de costos
        elif any(
            term in message_lower
            for term in ["costo", "precio", "inversión", "financiamiento", "pago"]
        ):
            return self._generate_cost_explanation(conversation)

        # Solicitud sobre plazos
        elif any(
            term in message_lower
            for term in ["tiempo", "plazo", "cuándo", "implementación", "instalación"]
        ):
            return self._generate_timeline_explanation(conversation)

        # Solicitud sobre personalización
        elif any(
            term in message_lower
            for term in ["modificar", "cambiar", "ajustar", "personalizar"]
        ):
            return self._generate_customization_explanation(conversation)

        # Si no es ninguna de las anteriores, respuesta general
        return """
Gracias por su interés en nuestra propuesta. Estaré encantado de aclarar cualquier duda o proporcionar información adicional sobre los aspectos técnicos, costos, plazos de implementación o cualquier ajuste que desee realizar.

La propuesta que ha recibido es preliminar y puede personalizarse según sus necesidades específicas. ¿Hay algún aspecto particular sobre el que desearía más detalles?

1. Detalles técnicos del sistema propuesto
2. Información sobre costos y financiamiento
3. Plazos de implementación y fases del proyecto
4. Opciones de personalización o ajustes a la solución
5. Requisitos de mantenimiento y operación
"""

    def _generate_technical_explanation(self, conversation: Conversation) -> str:
        """Genera una explicación técnica detallada del sistema propuesto"""

        state = conversation.questionnaire_state
        sector = state.sector
        subsector = state.subsector

        explanation = f"""
## Detalles Técnicos del Sistema Propuesto

El sistema de tratamiento diseñado para su operación {sector} - {subsector} consta de varias etapas interconectadas, cada una con un propósito específico:

### 1. Pretratamiento
"""

        # Personalizar según sector/subsector
        if subsector == "Textil":
            explanation += """
El agua residual primero pasa por un sistema de cribado automático para remover fibras y partículas grandes, seguido de un tanque de homogeneización con agitación que equilibra los picos de caudal y concentración, especialmente importantes en la industria textil donde los lotes de producción pueden variar significativamente.

### 2. Tratamiento Primario
Se implementa un sistema de Flotación por Aire Disuelto (DAF) con dosificación de coagulantes específicos para colorantes, que puede remover hasta el 95% de los colorantes y 85% de los sólidos suspendidos. Esta etapa es crucial para la industria textil debido a la alta carga de colorantes.

### 3. Tratamiento Secundario
Utilizamos un Reactor de Biopelícula de Lecho Móvil (MBBR) con microorganismos especializados en degradar compuestos orgánicos recalcitrantes típicos de la industria textil. Esta tecnología requiere menos espacio que los lodos activados convencionales mientras proporciona mayor eficiencia.

### 4. Tratamiento Terciario
El sistema incluye filtración por carbón activado para eliminar colorantes residuales y compuestos orgánicos, seguido de desinfección UV que no genera subproductos indeseables.
"""
        elif subsector == "Alimentos y Bebidas":
            explanation += """
El agua residual primero pasa por un sistema de cribado seguido de una trampa de grasas y aceites de alto rendimiento, crítica para la industria alimentaria, que puede remover hasta un 95% de grasas y aceites.

### 2. Tratamiento Primario
Se implementa un sistema de coagulación/floculación optimizado para materia orgánica de origen alimenticio, seguido de sedimentación acelerada que reduce significativamente la carga orgánica.

### 3. Tratamiento Secundario
Se utiliza un sistema combinado anaerobio-aerobio, comenzando con un reactor UASB (Upflow Anaerobic Sludge Blanket) que además de tratar el agua genera biogás aprovechable energéticamente, seguido de un sistema de lodos activados de alta eficiencia.

### 4. Tratamiento Terciario
El sistema incluye filtración multimedia y desinfección UV para garantizar la calidad microbiológica del efluente, fundamental en la industria alimentaria.
"""
        else:
            # Versión genérica para otros sectores
            explanation += """
El agua residual primero pasa por sistemas de cribado y homogeneización adaptados a su caudal específico, diseñados para manejar las variaciones propias de su operación.

### 2. Tratamiento Primario
Se implementa un sistema físico-químico personalizado para los contaminantes específicos de su sector, garantizando alta eficiencia en la remoción de sólidos y contaminantes clave.

### 3. Tratamiento Secundario
Utilizamos un sistema biológico optimizado para la biodegradabilidad específica de sus contaminantes, con diseño modular que permite ajustar la capacidad según sus necesidades.

### 4. Tratamiento Terciario
El sistema incluye etapas de pulido final adaptadas a sus objetivos de reúso o descarga, garantizando el cumplimiento de los parámetros requeridos.
"""

        explanation += """
### Características Adicionales del Sistema

- **Control automatizado**: Todo el sistema está equipado con sensores y controladores que permiten un funcionamiento óptimo con mínima intervención humana.
- **Módulos de telemetría**: Permiten el monitoreo remoto y alertas en tiempo real para garantizar un funcionamiento constante.
- **Diseño modular**: Facilita futuras ampliaciones o modificaciones según evolucionen sus necesidades.
- **Eficiencia energética**: Incorpora variadores de frecuencia y sistemas de recuperación de energía donde es aplicable.

¿Desea información adicional sobre alguna etapa específica del tratamiento o alguna tecnología en particular?
"""

        return explanation

    def _generate_cost_explanation(self, conversation: Conversation) -> str:
        """Genera una explicación detallada sobre costos y financiamiento"""

        # Extraer información económica si existe
        proposal = None
        try:
            proposal = questionnaire_service.generate_proposal(conversation)
        except:
            pass

        economic = proposal.get("economic_analysis", {}) if proposal else {}
        capex = economic.get("capex", 100000)
        opex_monthly = economic.get("opex_monthly", 2000)
        roi = economic.get("roi", 3)

        explanation = f"""
## Información Detallada sobre Costos e Inversión

### Estructura de Costos

La inversión en el sistema de tratamiento propuesto se divide en:

1. **Inversión inicial (CAPEX)**: Aproximadamente USD ${capex:,.2f}
   - Equipamiento: 60-65% del CAPEX
   - Obra civil e instalación: 25-30% del CAPEX
   - Ingeniería y puesta en marcha: 10-15% del CAPEX

2. **Costos operativos mensuales (OPEX)**: Aproximadamente USD ${opex_monthly:,.2f}/mes
   - Consumo energético: 30-35% del OPEX
   - Químicos y consumibles: 20-25% del OPEX
   - Mantenimiento preventivo: 15-20% del OPEX
   - Personal operativo: 25-30% del OPEX

### Retorno de la Inversión (ROI)

Con base en la información proporcionada, estimamos un periodo de recuperación de inversión de aproximadamente {roi:.1f} años, considerando:

- Ahorro en compra de agua fresca
- Reducción en costos de descarga
- Menor riesgo de multas ambientales
- Posible valorización de subproductos

### Opciones de Financiamiento

Hydrous Management Group colabora con diversas instituciones financieras que ofrecen opciones específicas para proyectos de sostenibilidad:

1. **Leasing de equipos**: Permite distribuir el costo a lo largo de 3-5 años
2. **Financiamiento verde**: Tasas preferenciales para proyectos ambientales
3. **Esquema BOT (Build-Operate-Transfer)**: Hydrous construye y opera el sistema inicialmente
4. **Pagos por desempeño**: Estructuración de pagos basados en resultados y ahorros obtenidos

¿Desea información más específica sobre alguna opción de financiamiento o un desglose más detallado de costos?
"""

        return explanation

    def _generate_timeline_explanation(self, conversation: Conversation) -> str:
        """Genera una explicación sobre los plazos de implementación"""

        explanation = """
## Plazos de Implementación del Proyecto

El desarrollo e implementación de su sistema de tratamiento de agua se estructura en las siguientes fases:

### Fase 1: Ingeniería de Detalle (4-6 semanas)
- Caracterización detallada del agua residual
- Dimensionamiento preciso de equipos
- Diseño de planos constructivos
- Desarrollo de P&ID (Diagramas de Tuberías e Instrumentación)

### Fase 2: Adquisición y Fabricación (8-12 semanas)
- Procura de equipos principales
- Fabricación de componentes especializados
- Control de calidad en fábrica
- Preparación del sitio para instalación

### Fase 3: Instalación y Montaje (4-6 semanas)
- Obra civil (si es requerida)
- Montaje de equipos
- Interconexión de sistemas
- Instalación eléctrica y automatización

### Fase 4: Puesta en Marcha (3-4 semanas)
- Pruebas hidráulicas
- Arranque secuencial de procesos
- Inoculación de sistemas biológicos
- Ajuste de parámetros operativos

### Fase 5: Capacitación y Entrega (2 semanas)
- Entrenamiento del personal operativo
- Entrega de manuales y documentación
- Establecimiento de rutinas de mantenimiento
- Validación de parámetros de calidad del agua

**Tiempo total estimado: 21-30 semanas** (5-7 meses)

Existe la posibilidad de implementar un enfoque modular o por etapas si se requiere una puesta en operación más rápida de ciertas partes del sistema.

¿Le interesa alguna opción para acelerar la implementación o tiene requerimientos particulares de tiempos para alguna etapa específica?
"""

        return explanation

    def _generate_customization_explanation(self, conversation: Conversation) -> str:
        """Genera una explicación sobre opciones de personalización"""

        state = conversation.questionnaire_state
        sector = state.sector
        subsector = state.subsector

        explanation = f"""
## Opciones de Personalización de la Solución

La propuesta presentada puede adaptarse según sus necesidades específicas. Estas son las principales áreas donde podemos realizar ajustes:

### Capacidad y Dimensionamiento
- **Escalamiento modular**: Implementación por fases para distribuir la inversión
- **Modificación de capacidad**: Ajuste del dimensionamiento según proyecciones de crecimiento
- **Redundancia de sistemas**: Incorporación de equipos de respaldo en componentes críticos

### Tecnologías Alternativas
"""

        # Opciones específicas según el sector/subsector
        if subsector == "Textil":
            explanation += """
- **Tratamiento de color**: Alternativas como ozono, procesos electroquímicos o adsorción avanzada
- **Manejo de salinidad**: Incorporación de tecnologías de membrana si la conductividad es un parámetro crítico
- **Recuperación de calor**: Sistemas para aprovechar la energía térmica del agua residual
"""
        elif subsector == "Alimentos y Bebidas":
            explanation += """
- **Recuperación de subproductos**: Sistemas para extraer materiales valorizables presentes en el agua
- **Maximización del biogás**: Tecnologías avanzadas para optimizar la generación energética
- **Tratamiento de alta carga**: Opciones para manejar picos estacionales de producción
"""
        else:
            explanation += """
- **Tecnologías específicas**: Soluciones adaptadas a contaminantes particulares de su industria
- **Sistemas compactos**: Alternativas para minimizar el espacio requerido
- **Soluciones híbridas**: Combinación de diferentes tecnologías para optimizar resultados
"""

        explanation += """
### Automatización y Control
- **Nivel de automatización**: Desde sistemas básicos hasta completamente automatizados
- **Integración con sistemas existentes**: Compatibilidad con plataformas SCADA o ERP actuales
- **Monitoreo remoto**: Diferentes niveles de telemetría y control a distancia

### Modelos de Servicio
- **Mantenimiento**: Opciones desde capacitación a personal propio hasta contratos de servicio integral
- **Modelos de operación**: Posibilidad de contrato BOT (Build-Operate-Transfer) o servicio por volumen tratado
- **Garantías extendidas**: Ampliación de coberturas y plazos según sus necesidades

¿Hay algún aspecto específico de la solución propuesta que le gustaría personalizar o alguna restricción particular que debamos considerar?
"""

        return explanation

    def _validate_critical_answer(self, question_id: str, answer: str) -> Optional[str]:
        """
        Valida si la respuesta a una pregunta crítica es adecuada.
        Devuelve un mensaje de insistencia si es necesario, o None si la respuesta es válida.
        """

        if question_id not in CRITICAL_QUESTIONS:
            return None

        if not answer or not CRITICAL_QUESTIONS[question_id]["validation"](answer):
            explanation = CRITICAL_QUESTIONS[question_id]["explanation"]
            fallback = CRITICAL_QUESTIONS[question_id]["fallback"]

            return (
                f"Entiendo que puede ser difícil proporcionar este dato con exactitud, pero {explanation}. "
                f"Si no tienes el dato exacto, {fallback}. Esta información nos permitirá "
                f"diseñar una solución mucho más precisa y adaptada a tus necesidades reales."
            )

        return None

    def _detect_user_type(self, conversation: Conversation) -> str:
        """
        Detecta si el usuario es profesiona, semi-profesional o no profesional
        basado en su lenguaje y conocimientos técnicos
        """
        # Extraer todos los mensajes del usuario
        user_messages = " ".join(
            [msg.content for msg in conversation.messages if msg.role == "user"]
        )

        # Indicadores de usuario profesional
        professional_indicators = [
            "lps",
            "m3/día",
            "DQO",
            "DBO",
            "SST",
            "conductividad",
            "pH",
            "ósmosis",
            "MBBR",
            "MBR",
            "DAF",
            "efluente",
            "PTAR",
            "coagulación",
            "NOM-",
            "reactor",
            "anaerobio",
            "biológico",
            "cumplimiento normativo",
            "parámetros técnicos",
        ]

        # Indicadores de semi-profesional
        semi_indicators = [
            "tratamiento",
            "litros por segundo",
            "metros cúbicos",
            "agua residual",
            "filtración",
            "norma",
            "agua industrial",
            "descarga",
            "reutilización",
            "bombas",
            "tanques",
            "sistema",
            "automatización",
        ]

        # Contar Indicadores
        prof_count = sum(
            1
            for term in professional_indicators
            if term.lower() in user_messages.lower()
        )

        semi_count = sum(
            1 for term in semi_indicators if term.lower() in user_messages.lower()
        )

        # Clasificar usuario
        if prof_count >= 3:
            return "professional"
        elif semi_count >= 3 or prof_count >= 1:
            return "semi-profesional"
        else:
            return "non-professional"

    def _format_positive_validation(self, previous_message: str) -> str:
        """
        Genera una validación positiva personalizada basada en la respuesta anterior.
        """
        validations = [
            "¡Excelente! Gracias por compartir esta información.",
            "¡Perfecto! Estos datos son muy valiosos para diseñar tu solución.",
            "Gracias por proporcionarnos este detalle importante.",
            "Muy bien. Esta información nos ayuda a entender mejor tus necesidades.",
            "¡Genial! Con estos datos avanzamos significativamente en el diseño de tu solución.",
        ]

        # Seleccionar una validación aleatoria, se podría mejorar para que sea más contextual
        import random

        return random.choice(validations)

    # Mejorar la selección de emojis según el tipo de pregunta
    def _select_emoji_for_question_type(self, question_id: str) -> str:
        """
        Selecciona un emoji apropiado según el tipo de pregunta.
        """
        emoji_map = {
            "nombre_empresa": "🏢",
            "ubicacion": "📍",
            "costo_agua": "💰",
            "cantidad_agua_consumida": "🚰",
            "cantidad_agua_residual": "💧",
            "num_personas": "👥",
            "parametros_agua": "🔬",
            "usos_agua": "🔄",
            "fuente_agua": "🌊",
            "objetivo_principal": "🎯",
            "objetivo_reuso": "♻️",
            "descarga_actual": "📤",
            "restricciones": "⚠️",
            "sistema_existente": "⚙️",
            "presupuesto": "💵",
            "tiempo_proyecto": "⏱️",
            "sector_selection": "🏭",
            "subsector_selection": "🔍",
        }

        return emoji_map.get(question_id, "📋")

    def _optimize_context_length(
        self, conversation: Conversation
    ) -> List[Dict[str, str]]:
        """
        Optimiza el contexto de la conversación para manejar conversaciones largas

        Args:
            conversation: Conversación actual

        Returns:
            List: Lista optimizada de mensajes para el contexto
        """
        messages = []

        # Siempre incluir el mensaje del sistema
        system_messages = [msg for msg in conversation.messages if msg.role == "system"]
        if system_messages:
            messages.append({"role": "system", "content": system_messages[0].content})

        # Si el cuestionario está activo, priorizar información relevante
        if conversation.is_questionnaire_active():
            # Incluir el último intercambio completo (3-4 mensajes)
            recent_exchanges = [
                msg
                for msg in conversation.messages[-6:]
                if msg.role in ["user", "assistant"]
            ]
            messages.extend(
                [{"role": msg.role, "content": msg.content} for msg in recent_exchanges]
            )

            # Añadir resumen del estado actual
            state = conversation.questionnaire_state
            state_summary = f"""
    Información recopilada hasta ahora:
    - Sector: {state.sector}
    - Subsector: {state.subsector}
    - Preguntas respondidas: {state.questions_answered}
    - Pregunta actual: {state.current_question_id}
    """
            messages.append({"role": "system", "content": state_summary})
        else:
            # Para conversaciones normales, incluir mensajes recientes
            recent_messages = [
                msg
                for msg in conversation.messages[-8:]
                if msg.role in ["user", "assistant"]
            ]
            messages.extend(
                [{"role": msg.role, "content": msg.content} for msg in recent_messages]
            )

        return messages


# Instancia global del servicio
ai_service = AIWithQuestionnaireService()
