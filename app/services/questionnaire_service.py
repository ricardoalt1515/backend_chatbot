import datetime
import json
import logging
import os
import random
import re
import string
from typing import Dict, Any, Optional, List, Tuple, Union


# Verificar dependencias disponibles para generación de PDF
PDF_GENERATORS = []
try:
    import markdown2
except ImportError:
    markdown2 = None
    logging.warning("markdown2 no está instalado. Necesario para formatear propuestas.")

try:
    import pdfkit

    PDF_GENERATORS.append("pdfkit")
except ImportError:
    logging.warning("pdfkit no está instalado. No se podrá usar para generar PDFs.")

try:
    from weasyprint import HTML

    PDF_GENERATORS.append("weasyprint")
except ImportError:
    logging.warning("weasyprint no está instalado. No se podrá usar para generar PDFs.")

if not PDF_GENERATORS:
    logging.warning(
        "¡ADVERTENCIA! No hay generadores de PDF disponibles. Las propuestas solo se generarán en HTML."
    )
else:
    logging.info(f"Generadores de PDF disponibles: {', '.join(PDF_GENERATORS)}")

from app.models.conversation import Conversation, QuestionnaireState
from app.config import settings

logger = logging.getLogger("hydrous-backend")


class QuestionnaireService:
    """Servicio simplificado para manejar el cuestionario y generar propuestas"""

    def __init__(self):
        self.questionnaire_data = self._load_questionnaire_data()

    def _load_questionnaire_data(self) -> Dict[str, Any]:
        """Carga los datos del cuestionario desde un archivo JSON"""
        try:
            # Intentar cargar desde archivo
            questionnaire_path = os.path.join(
                os.path.dirname(__file__), "../data/questionnaire.json"
            )
            if os.path.exists(questionnaire_path):
                with open(questionnaire_path, "r", encoding="utf-8") as f:
                    return json.load(f)

            # Intentar con questionnaire_complete.json como alternativa
            questionnaire_complete_path = os.path.join(
                os.path.dirname(__file__), "../data/questionnaire_complete.json"
            )
            if os.path.exists(questionnaire_complete_path):
                with open(questionnaire_complete_path, "r", encoding="utf-8") as f:
                    return json.load(f)

            logger.warning(
                "Archivo de cuestionario no encontrado. Usando estructura predeterminada."
            )
            return self._build_default_questionnaire()
        except Exception as e:
            logger.error(f"Error al cargar datos del cuestionario: {str(e)}")
            return self._build_default_questionnaire()

    def _build_default_questionnaire(self) -> Dict[str, Any]:
        """Construye una versión predeterminada del cuestionario para emergencias"""
        # Estructura mínima para que el sistema funcione en caso de error
        return {
            "sectors": ["Industrial", "Comercial", "Municipal", "Residencial"],
            "subsectors": {
                "Industrial": ["Textil", "Alimentos y Bebidas", "Petroquímica"],
                "Comercial": ["Hotel", "Edificio de oficinas"],
                "Municipal": ["Gobierno de la ciudad"],
                "Residencial": ["Vivienda unifamiliar", "Edificio multifamiliar"],
            },
            "questions": {
                "Industrial_Textil": [
                    {
                        "id": "nombre_empresa",
                        "text": "¿Cuál es el nombre de tu empresa o proyecto?",
                        "type": "text",
                        "required": True,
                    },
                    {
                        "id": "ubicacion",
                        "text": "¿Cuál es la ubicación de tu empresa?",
                        "type": "text",
                        "required": True,
                    },
                    {
                        "id": "cantidad_agua_consumida",
                        "text": "¿Qué cantidad de agua consumes?",
                        "type": "text",
                        "required": True,
                    },
                ]
            },
            "facts": {
                "Industrial_Textil": [
                    "Las industrias textiles que implementan sistemas de reciclaje eficientes logran reducir su consumo de agua hasta en un 40%.",
                ]
            },
        }

    def get_sectors(self) -> List[str]:
        """Obtiene la lista de sectores disponibles"""
        return self.questionnaire_data.get("sectors", [])

    def get_subsectors(self, sector: str) -> List[str]:
        """Obtiene los subsectores para un sector dado"""
        subsectors = self.questionnaire_data.get("subsectors", {})
        return subsectors.get(sector, [])

    def get_random_fact(self, sector: str, subsector: str = None) -> Optional[str]:
        """
        Obtiene un hecho aleatorio relacionado con el sector/subsector

        Args:
            sector: Sector principal
            subsector: Subsector específico (opcional)

        Returns:
            Hecho aleatorio o None si no hay hechos disponibles
        """
        # Si no hay subsector, intentar obtener un hecho general del sector
        if not subsector:
            # Buscar primero en hechos generales del sector
            sector_facts = self.questionnaire_data.get("facts", {}).get(sector, [])
            if sector_facts:
                return random.choice(sector_facts)

            # Si no hay hechos generales, buscar en cualquier subsector del sector
            subsectors = self.get_subsectors(sector)
            for sub in subsectors:
                facts_key = f"{sector}_{sub}"
                facts = self.questionnaire_data.get("facts", {}).get(facts_key, [])
                if facts:
                    return random.choice(facts)

            return None

        # Si hay subsector, buscar hechos específicos
        facts_key = f"{sector}_{subsector}"
        facts = self.questionnaire_data.get("facts", {}).get(facts_key, [])

        # Si no hay hechos específicos para este subsector, intentar con hechos generales
        if not facts:
            facts = self.questionnaire_data.get("facts", {}).get(sector, [])

        return random.choice(facts) if facts else None

    def generate_preliminary_diagnosis(self, conversation: Conversation) -> str:
        """Genera un diagnóstico preliminar basado en las respuestas del cuestionario"""
        state = conversation.questionnaire_state
        answers = state.answers
        sector = state.sector
        subsector = state.subsector

        # Obtener información clave
        nombre_empresa = answers.get("nombre_empresa", "su empresa")
        ubicacion = answers.get("ubicacion", "su ubicación")
        consumo_agua = answers.get("cantidad_agua_consumida", "su consumo de agua")
        agua_residual = answers.get(
            "cantidad_agua_residual", "la cantidad de agua residual generada"
        )

        diagnosis = f"""
    ## Diagnóstico Preliminar para {nombre_empresa}

    Hemos completado la recopilación de información clave sobre sus necesidades de tratamiento de agua. Basándonos en los datos proporcionados, podemos ofrecer el siguiente diagnóstico preliminar:

    ### Factores Críticos Identificados

    """

        # Añadir factores críticos según el sector/subsector
        if subsector == "Textil":
            diagnosis += """
- **Alta carga de colorantes y compuestos orgánicos** típica de la industria textil
- **Variabilidad en la composición** del agua residual según ciclos de producción
- **Potencial presencia de metales pesados** provenientes de tintes y procesos
- **Necesidad de tratamiento especializado** para remoción de color
    """
        elif subsector == "Alimentos y Bebidas":
            diagnosis += """
- **Elevada carga orgánica biodegradable** (DBO/DQO)
- **Presencia significativa de grasas y aceites**
- **Sólidos suspendidos** de origen alimentario
- **Potencial variabilidad estacional** según ciclos de producción
    """
        elif sector == "Comercial":
            diagnosis += """
- **Aguas grises** de uso sanitario y limpieza
- **Carga orgánica moderada**
- **Potencial para reutilización** en aplicaciones no potables
- **Requisitos de espacio optimizado** para instalaciones comerciales
    """
        else:
            diagnosis += """
- **Perfil de contaminantes específicos** de su sector industrial
- **Necesidades de tratamiento especializado** según sus parámetros reportados
- **Oportunidades de reúso** adaptadas a sus procesos
- **Consideraciones de espacio y operación** según su instalación
    """

        # Añadir pasos de proceso recomendados
        diagnosis += """
### Pasos de Proceso Recomendados

Basado en su perfil, recomendamos un sistema de tratamiento multi-etapa que incluya:

1. **Pretratamiento**
   - Cribado para eliminar sólidos gruesos
   - Homogeneización para estabilizar flujos y cargas

2. **Tratamiento Primario**
    """

        # Personalizar tratamiento primario según subsector
        if subsector == "Textil":
            diagnosis += "   - Flotación por aire disuelto (DAF) con coagulación química para remoción de color y sólidos\n"
        elif subsector == "Alimentos y Bebidas":
            diagnosis += "   - Trampa de grasas seguida de coagulación/floculación para remoción de grasas y sólidos orgánicos\n"
        else:
            diagnosis += (
                "   - Sistema físico-químico adaptado a sus contaminantes específicos\n"
            )

        diagnosis += """
    3. **Tratamiento Secundario**
    """

        # Personalizar tratamiento secundario según subsector
        if subsector == "Textil":
            diagnosis += "   - Biorreactor de Membrana (MBR) para degradación biológica y filtración avanzada\n"
        elif subsector == "Alimentos y Bebidas":
            diagnosis += "   - Tratamiento biológico (UASB seguido de lodos activados) para remoción de materia orgánica\n"
        else:
            diagnosis += "   - Sistema biológico optimizado para su tipo específico de contaminantes orgánicos\n"

        diagnosis += """
    4. **Tratamiento Terciario**
    """

        # Personalizar tratamiento terciario según objetivo de reúso
        objetivo_reuso = answers.get("objetivo_reuso", "")
        if "riego" in str(objetivo_reuso).lower():
            diagnosis += (
                "   - Filtración multimedia y desinfección UV para uso en riego\n"
            )
        elif "sanitarios" in str(objetivo_reuso).lower():
            diagnosis += "   - Filtración y desinfección para reúso en sanitarios\n"
        elif "procesos" in str(objetivo_reuso).lower():
            diagnosis += "   - Filtración avanzada, posiblemente ósmosis inversa para reúso en procesos\n"
        else:
            diagnosis += "   - Tratamiento avanzado según sus requisitos específicos de reúso o descarga\n"

        # Estimaciones económicas preliminares
        diagnosis += """
### Estimaciones Económicas Preliminares

Con base en la información proporcionada, podemos ofrecer las siguientes estimaciones iniciales:

- **Inversión aproximada (CAPEX)**: USD $80,000 - $150,000
- **Costos operativos mensuales (OPEX)**: USD $1,500 - $3,000
- **Periodo estimado de retorno de inversión**: 2-4 años

*Nota: Estas son estimaciones preliminares. Los valores exactos serán determinados en la propuesta detallada.*

### Beneficios Principales

- **Reducción del consumo de agua fresca**: 40-60%
- **Cumplimiento normativo** con los estándares de descarga
- **Mejora de perfil de sostenibilidad** y responsabilidad ambiental
- **Potencial reducción de costos operativos** a mediano y largo plazo

### Próximos Pasos

Para avanzar con una propuesta técnica y económica detallada, necesitamos:

1. Su confirmación para proceder con la generación de la propuesta
2. Cualquier información adicional que considere relevante
3. Preferencias específicas sobre aspectos técnicos, económicos o de implementación

**PREGUNTA: ¿Desea proceder con la generación de una propuesta detallada basada en este diagnóstico preliminar?**
1. Sí, proceder con la propuesta
2. No, tengo algunas preguntas o información adicional
    """

        return diagnosis

    def get_key_questions(
        self, sector: str, subsector: str = None
    ) -> List[Dict[str, Any]]:
        """
        Obtiene las preguntas clave para un sector/subsector

        Args:
            sector: Sector principal
            subsector: Subsector específico (opcional)

        Returns:
            Lista de preguntas clave
        """
        if not subsector:
            # Si no hay subsector, devolver solo preguntas comunes
            return [
                {
                    "id": "subsector_selection",
                    "text": f"¿Cuál es el subsector específico dentro de {sector}?",
                    "type": "multiple_choice",
                    "options": self.get_subsectors(sector),
                    "explanation": "Cada subsector tiene características y necesidades específicas.",
                },
            ]

        # Obtener todas las preguntas para este sector/subsector
        questions_key = f"{sector}_{subsector}"
        return self.questionnaire_data.get("questions", {}).get(questions_key, [])

    def generate_interim_summary(self, conversation: Conversation) -> str:
        """Genera un resumen intermedio de la informacion recopilada hasta el momento"""
        state = conversation.questionnaire_state
        answers = state.answers
        sector = state.sector
        subsector = state.subsector

        summary = f"""
    ## Resumen de la Información Recopilada

    Hemos avanzado significativamente en la recopilación de datos para su solución de tratamiento de agua. A continuación, un resumen de la información proporcionada hasta el momento:

    ### Datos Básicos
    - **Sector**: {sector}
    - **Subsector**: {subsector}
    """

        # Añadir respuestas clave
        key_info = []

        if "nombre_empresa" in answers:
            key_info.append(f"- **Empresa/Proyecto**: {answers['nombre_empresa']}")

        if "ubicacion" in answers:
            key_info.append(f"- **Ubicación**: {answers['ubicacion']}")

        if "costo_agua" in answers:
            key_info.append(f"- **Costo del agua**: {answers['costo_agua']}")

        if "cantidad_agua_consumida" in answers:
            key_info.append(
                f"- **Consumo de agua**: {answers['cantidad_agua_consumida']}"
            )

        if "cantidad_agua_residual" in answers:
            key_info.append(
                f"- **Generación de agua residual**: {answers['cantidad_agua_residual']}"
            )

        if key_info:
            summary += "\n".join(key_info) + "\n"

        # Añadir parámetros técnicos si existen
        if "parametros_agua" in answers and isinstance(
            answers["parametros_agua"], dict
        ):
            summary += "\n### Parámetros Técnicos\n"
            for param, value in answers["parametros_agua"].items():
                summary += f"- **{param}**: {value}\n"

        # Dato interesante relevante
        fact = self.get_random_fact(sector, subsector)
        if fact:
            summary += f"\n*{fact}*\n"

        # Confirmación y siguiente pregunta
        summary += """
    ¿Es correcta esta información? Si necesita realizar alguna corrección, por favor indíquelo. 
    De lo contrario, continuaremos con las siguientes preguntas para completar su perfil de necesidades.

    **PREGUNTA: ¿Confirma que la información anterior es correcta?**
    1. Si, la informacion es correcta
    2. NO, necesito corregir algo
    """

        return summary

    def suggest_document_upload(self, question_id: str) -> str:
        """Sugiere la carga de documentos en momentos estratégicos"""
        document_suggestions = {
            "parametros_agua": """
    ### Análisis de Laboratorio

    Si dispone de análisis de laboratorio de su agua residual, puede subirlos ahora. 
    Estos datos nos permitirán diseñar una solución mucho más precisa y eficiente.

    Para subir un documento, utilice el botón de "Adjuntar archivo" que aparece abajo.
    """,
            "costo_agua": """
    ### Recibos de Agua

    Si tiene a mano recibos recientes de agua, puede subirlos para un análisis más preciso 
    de costos y potenciales ahorros. Esta información mejorará significativamente la 
    exactitud de nuestros cálculos de retorno de inversión.
    """,
            "sistema_existente": """
    ### Documentación Técnica

    Si dispone de documentación, diagramas o fotografías de su sistema actual, 
    nos ayudaría enormemente a entender su infraestructura existente y cómo 
    integrar nuestra solución de la manera más eficiente.
    """,
            "recibos_agua": """
    ### Recibos o Facturas

    Si puede proporcionarnos sus recibos o facturas de agua recientes, 
    podremos realizar un análisis mucho más preciso de su consumo y 
    potenciales ahorros con nuestro sistema.
    """,
            "agua_potable_analisis": """
    ### Análisis de Agua Potable

    Si cuenta con análisis recientes de la calidad de su agua potable, 
    estos datos nos ayudarán a entender mejor las características específicas 
    del agua que utiliza y optimizar su tratamiento.
    """,
            "descripcion_sistema": """
    ### Especificaciones Técnicas

    Si cuenta con especificaciones técnicas o documentación de su sistema actual,
    compartirlas nos permitiría entender mejor cómo integrar nuestra solución
    de manera óptima con su infraestructura existente.
    """,
        }

        return document_suggestions.get(question_id, "")

    def _get_question_text(self, sector: str, subsector: str, question_id: str) -> str:
        """Obtiene el texto de la pregunta a partir del ID"""
        questions_key = f"{sector}_{subsector}"
        questions = self.questionnaire_data.get("questions", {}).get(questions_key, [])

        for q in questions:
            if q.get("id") == question_id:
                return q.get("text", question_id)

        return question_id

    def format_question_for_display(
        self, question: Dict[str, Any], include_fact: bool = True
    ) -> str:
        """Formatea una pregunta para presentarla al usuario con un formato amigable"""
        # Obtener información básica de la pregunta
        q_text = question.get("text", "")
        q_explanation = question.get("explanation", "")
        q_type = question.get("type", "")

        # Construir el mensaje
        message = ""

        # 1. Añadir dato interesante si está disponible y se solicita
        if include_fact:
            fact = self.get_random_fact(
                None, None
            )  # Obtener un dato general si no hay específico
            if fact:
                message += f"*Dato interesante: {fact}*\n\n"

        # 2. Añadir explicación de por qué es importante esta pregunta
        if q_explanation:
            message += f"{q_explanation}\n\n"

        # 3. Presentar la pregunta claramente
        message += f"**PREGUNTA: {q_text}**\n\n"

        # 4. Añadir opciones numeradas para preguntas de selección
        if q_type in ["multiple_choice", "multiple_select"] and "options" in question:
            for i, option in enumerate(question["options"], 1):
                message += f"{i}. {option}\n"

        return message

    def generate_proposal(self, conversation: Conversation) -> Dict[str, Any]:
        """
        Genera una propuesta simplificada basada en la conversación
        """

        # Extraer información básica de la conversación
        answers = conversation.questionnaire_state.answers

        # Información del cliente
        client_info = {
            "name": answers.get("nombre_empresa", "Cliente"),
            "location": answers.get("ubicacion", "No especificada"),
            "sector": conversation.questionnaire_state.sector or "Industrial",
            "subsector": conversation.questionnaire_state.subsector or "",
        }

        # Información técnica
        technical_info = {
            "water_consumption": answers.get(
                "cantidad_agua_consumida", "No especificado"
            ),
            "wastewater_generation": answers.get(
                "cantidad_agua_residual", "No especificado"
            ),
            "water_cost": answers.get("costo_agua", "No especificado"),
            "objectives": answers.get(
                "objetivo_principal", "Optimización de recursos hídricos"
            ),
            "reuse_objectives": answers.get(
                "objetivo_reuso", ["Reutilización de agua"]
            ),
        }

        # Extraer la última propuesta generada por el modelo (si existe)
        last_proposal_text = ""
        for msg in reversed(conversation.messages):
            if msg.role == "assistant" and "Propuesta Preliminar" in msg.content:
                last_proposal_text = msg.content
                break

        # Construir la propuesta
        proposal = {
            "client_info": client_info,
            "technical_info": technical_info,
            "proposal_text": last_proposal_text,
            "timestamp": datetime.now().isoformat(),
            "proposal_id": f"HYD-{datetime.now().strftime('%Y%m%d')}-{conversation.id[:8].upper()}",
        }

        return proposal

    def get_introduction(self) -> Tuple[str, str]:
        """
        Obtiene el texto de introducción del cuestionario

        Returns:
            Tupla con (texto introductorio, explicación)
        """
        intro = self.questionnaire_data.get("introduction", {})
        return intro.get("text", ""), intro.get("explanation", "")

    def get_next_question(self, state: QuestionnaireState) -> Optional[Dict[str, Any]]:
        """
        Obtiene la siguiente pregunta basada en el estado actual

        Args:
            state: Estado actual del cuestionario

        Returns:
            Siguiente pregunta o None si no hay más preguntas
        """
        if not state.active:
            return None

        # Si no tenemos sector, preguntar primero por el sector
        if not state.sector:
            return {
                "id": "sector_selection",
                "text": "¿En qué sector opera tu empresa?",
                "type": "multiple_choice",
                "options": self.get_sectors(),
                "required": True,
                "explanation": "El sector determina el tipo de aguas residuales y las tecnologías más adecuadas para su tratamiento.",
            }

        # Si tenemos sector pero no subsector, preguntar por el subsector
        if not state.subsector:
            return {
                "id": "subsector_selection",
                "text": f"¿Cuál es el subsector específico dentro de {state.sector}?",
                "type": "multiple_choice",
                "options": self.get_subsectors(state.sector),
                "required": True,
                "explanation": "Cada subsector tiene características específicas que influyen en el diseño de la solución.",
            }

        # Obtener las preguntas para este sector/subsector
        question_key = f"{state.sector}_{state.subsector}"
        questions = self.questionnaire_data.get("questions", {}).get(question_key, [])

        if not questions:
            # No hay preguntas específicas para esta combinación de sector/subsector
            logger.warning(f"No se encontraron preguntas para {question_key}")
            return None

        # Determinar la siguiente pregunta no contestada
        for q in questions:
            if q["id"] not in state.answers:
                # Añadir un hecho relevante a la explicación si existe
                fact = self.get_random_fact(state.sector, state.subsector)
                if fact and "explanation" in q:
                    q = q.copy()  # Crear copia para no modificar el original
                    q["explanation"] = (
                        f"{q['explanation']}\n\n*Dato interesante: {fact}*"
                    )

                return q

        # Si llegamos aquí, todas las preguntas han sido respondidas
        return None

    def process_answer(
        self, conversation: Conversation, question_id: str, answer: Any
    ) -> None:
        """
        Procesa la respuesta a una pregunta y determina si es necesario insistir.
        Devuelve un mensaje de insistencia o None si la respuesta es aceptable.

        """
        # Validar respuesta para preguntas criticas
        insistence_message = self._validate_critical_answer(question_id, answer)
        if insistence_message:
            return insistence_message

        # Si la respuesta es aceptable, procesar normalmente
        conversation.questionnaire_state.answer[question_id] = answer

        # Actualizar conteo de preguntas respondidas si existe el atributo
        if hasattr(conversation.questionnaire_state, "questions_answered"):
            conversation.questionnaire_state.questions_answered += 1

        # Si es una respuesta al sector o subsector, actualizar esos campos
        if question_id == "sector_selection":
            # Puede ser índice numérico o texto directo
            if isinstance(answer, str) and answer.isdigit():
                sector_index = int(answer) - 1
                sectors = self.get_sectors()
                if 0 <= sector_index < len(sectors):
                    conversation.questionnaire_state.sector = sectors[sector_index]
            else:
                # Buscar coincidencia directa o parcial
                sectors = self.get_sectors()
                answer_lower = answer.lower()
                for sector in sectors:
                    if sector.lower() == answer_lower or sector.lower() in answer_lower:
                        conversation.questionnaire_state.sector = sector
                        break

        elif question_id == "subsector_selection":
            if conversation.questionnaire_state.sector:
                # Puede ser índice numérico o texto directo
                if isinstance(answer, str) and answer.isdigit():
                    subsector_index = int(answer) - 1
                    subsectors = self.get_subsectors(
                        conversation.questionnaire_state.sector
                    )
                    if 0 <= subsector_index < len(subsectors):
                        conversation.questionnaire_state.subsector = subsectors[
                            subsector_index
                        ]
                else:
                    # Buscar coincidencia directa o parcial
                    subsectors = self.get_subsectors(
                        conversation.questionnaire_state.sector
                    )
                    answer_lower = answer.lower()
                    for subsector in subsectors:
                        if (
                            subsector.lower() == answer_lower
                            or subsector.lower() in answer_lower
                        ):
                            conversation.questionnaire_state.subsector = subsector
                            break

        # Actualizar el ID de la pregunta actual para la siguiente
        next_question = self.get_next_question(conversation.questionnaire_state)
        conversation.questionnaire_state.current_question_id = (
            next_question["id"] if next_question else None
        )

        # Si no hay más preguntas, marcar el cuestionario como completado
        if next_question is None and conversation.questionnaire_state.active:
            conversation.questionnaire_state.completed = True
            conversation.questionnaire_state.active = False

    def generate_proposal(self, conversation: Conversation) -> Dict[str, Any]:
        """
        Genera una propuesta adaptativa basada en la información disponible

        Args:
            conversation: Conversación con la información recopilada

        Returns:
            Propuesta con la solución recomendada
        """
        # Extraer toda la información disponible
        info = self._extract_conversation_info(conversation)

        # Obtener datos del cliente
        client_info = {
            "name": info.get("nombre_empresa", "Cliente"),
            "location": info.get("ubicacion", "No especificada"),
            "sector": info.get("sector", "Industrial"),
            "subsector": info.get("subsector", ""),
            "contact_info": info.get("contacto", "No especificado"),
            "sistema_existente": info.get("sistema_existente", "No especificado"),
        }

        # Datos detallados del proyecto
        project_details = {
            "water_source": info.get("fuente_agua", "Municipal/Pozo"),
            "water_consumption": info.get("cantidad_agua_consumida", "No especificado"),
            "wastewater_generation": info.get(
                "cantidad_agua_residual", "No especificado"
            ),
            "water_cost": info.get("costo_agua", "No especificado"),
            "peak_flows": info.get("picos_agua_residual", "No especificado"),
            "objectives": info.get(
                "objetivo_principal", ["Mejorar eficiencia hídrica"]
            ),
            "reuse_objectives": info.get("objetivo_reuso", ["Reutilización de agua"]),
            "discharge_location": info.get("descarga_actual", "Alcantarillado"),
            "constraints": info.get("restricciones", []),
            "timeline": info.get("tiempo_proyecto", "No especificado"),
            "budget": info.get("presupuesto", "No especificado"),
        }

        # Obtener parámetros de agua detectados (mejorar la extracción)
        parameters = info.get("parameters", {})

        # Integrar datos técnicos de documentos subidos
        try:
            from app.services.document_service import document_service

            doc_insights = document_service.get_insights_for_conversation_sync(
                conversation.id
            )

            if doc_insights:
                for doc in doc_insights:
                    insights = doc.get("insights", {})
                    doc_params = insights.get("parameters", {})

                    # Solo añadir parámetros que no existan ya
                    for param, value in doc_params.items():
                        if param not in parameters:
                            parameters[param] = value

                # Añadir una nota sobre los documentos utilizados
                project_details["documents_used"] = [
                    {
                        "filename": doc.get("filename", ""),
                        "type": doc.get("insights", {}).get("document_type", "unknown"),
                    }
                    for doc in doc_insights
                ]
        except Exception as e:
            logger.warning(f"No se pudieron integrar datos de documentos: {e}")

        # Generar solución tecnológica más personalizada según el sector/subsector y parámetros
        treatment_solution = self._determine_treatment_solution(
            client_info["sector"], client_info["subsector"], parameters, project_details
        )

        # Generar análisis económico más preciso
        economic_analysis = self._generate_economic_analysis(
            project_details["water_consumption"],
            project_details["water_cost"],
            treatment_solution,
        )

        # Añadir recomendaciones específicas según el caso
        recommendations = self._generate_recommendations(
            client_info["sector"], client_info["subsector"], project_details, parameters
        )

        # Construcción de propuesta completa mejorada
        proposal = {
            "client_info": client_info,
            "project_details": project_details,
            "water_parameters": parameters,
            "recommended_solution": treatment_solution,
            "economic_analysis": economic_analysis,
            "recommendations": recommendations,
            "timestamp": datetime.now().isoformat(),
            "proposal_id": f"HYD-{datetime.now().strftime('%Y%m%d')}-{conversation.id[:8].upper()}",
        }

        return proposal

    def _extract_conversation_info(self, conversation: Conversation) -> Dict[str, Any]:
        """
        Extrae toda la información disponible en la conversación

        Args:
            conversation: Conversación actual

        Returns:
            Diccionario con toda la información recopilada
        """
        info = {}

        # Obtener sector/subsector del estado del cuestionario
        info["sector"] = conversation.questionnaire_state.sector
        info["subsector"] = conversation.questionnaire_state.subsector

        # Obtener respuestas específicas del cuestionario
        answers = conversation.questionnaire_state.answers
        for key, value in answers.items():
            if key == "nombre_empresa":
                info["name"] = value
            elif key == "ubicacion":
                info["location"] = value
            elif key == "cantidad_agua_consumida":
                info["water_consumption"] = value
            elif key == "cantidad_agua_residual":
                info["wastewater_generation"] = value
            elif key == "objetivo_principal":
                if isinstance(value, list):
                    info["objectives"] = value
                else:
                    info["objectives"] = [value]
            elif key == "objetivo_reuso":
                if isinstance(value, list):
                    info["reuse_objectives"] = value
                else:
                    info["reuse_objectives"] = [value]
            elif key == "parametros_agua" and isinstance(value, dict):
                # Si hay respuestas específicas de parámetros, añadirlas
                if "parameters" not in info:
                    info["parameters"] = {}
                info["parameters"].update(value)

        # Extraer información de parámetros individuales
        for key, value in answers.items():
            if key in ["ph", "dbo", "dqo", "sst", "sdt", "color"]:
                if "parameters" not in info:
                    info["parameters"] = {}
                info["parameters"][key] = value

        # Buscar en todos los mensajes para extraer información adicional
        all_user_messages = " ".join(
            [msg.content for msg in conversation.messages if msg.role == "user"]
        )

        # Extraer parámetros de agua de los mensajes
        message_parameters = self._extract_parameters_from_text(all_user_messages)

        # Actualizar parámetros solo si no están ya definidos
        if "parameters" not in info:
            info["parameters"] = {}

        for key, value in message_parameters.items():
            if key not in info["parameters"]:
                info["parameters"][key] = value

        return info

    def _extract_parameters_from_text(self, text: str) -> Dict[str, str]:
        """
        Extrae parámetros de agua de un texto

        Args:
            text: Texto a analizar

        Returns:
            Diccionario con parámetros detectados
        """
        parameters = {}

        # Patrones para extraer parámetros clave
        patterns = {
            "ph": r"pH\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "dbo": r"(?:DBO|BOD)[5]?\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "dqo": r"(?:DQO|COD)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "sst": r"(?:SST|TSS)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "sdt": r"(?:SDT|TDS)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "conductividad": r"(?:[Cc]onductividad|[Cc]onductivity)\s*[:=]?\s*(\d+(?:\.\d+)?)",
        }

        # Extraer valores de parámetros
        for param, pattern in patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                parameters[param] = matches[0]

        # Patrones para extraer consumos de agua
        water_consumption_pattern = r"(?:consumo|consumption).{0,30}?(\d+(?:[\.,]\d+)?)\s*(m3|m³|metros cúbicos|litros)"
        matches = re.findall(water_consumption_pattern, text, re.IGNORECASE)
        if matches:
            value, unit = matches[0]
            parameters["consumo_agua"] = f"{value.replace(',', '.')} {unit}"

        return parameters

    def _determine_treatment_solution(
        self, sector: str, subsector: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Determina la solución de tratamiento recomendada

        Args:
            sector: Sector de la empresa
            subsector: Subsector específico
            parameters: Parámetros de agua detectados

        Returns:
            Solución de tratamiento recomendada
        """
        # Soluciones por defecto para cada subsector
        default_solutions = {
            "Textil": {
                "pretreatment": "Cribado y homogeneización",
                "primary": "Flotación por aire disuelto (DAF) para remoción de sólidos y colorantes",
                "secondary": "Reactor biológico de membrana (MBR) para reducción de DBO y DQO",
                "tertiary": "Oxidación avanzada para eliminación de color residual y filtración por carbón activado",
                "efficiency": "Recuperación de hasta 70% del agua para reúso en procesos no críticos",
                "description": "Sistema optimizado para tratar aguas con alta carga de colorantes y compuestos orgánicos",
            },
            "Alimentos y Bebidas": {
                "pretreatment": "Cribado y trampa de grasas",
                "primary": "Coagulación/floculación para remoción de sólidos suspendidos",
                "secondary": "Reactor anaerobio UASB seguido de tratamiento aerobio",
                "tertiary": "Filtración y desinfección UV",
                "efficiency": "Recuperación de hasta 60% del agua y generación de biogás aprovechable",
                "description": "Sistema diseñado para aguas con alta carga orgánica biodegradable y grasas",
            },
            "Petroquímica": {
                "pretreatment": "Separación de aceites y homogeneización",
                "primary": "Flotación y precipitación química",
                "secondary": "Biorreactor con microorganismos especializados en degradación de hidrocarburos",
                "tertiary": "Filtración avanzada y adsorción por carbón activado",
                "efficiency": "Recuperación de hasta 50% del agua y recuperación de hidrocarburos",
                "description": "Sistema especializado para tratar aguas con hidrocarburos y compuestos orgánicos recalcitrantes",
            },
        }

        # Solución genérica industrial
        industrial_solution = {
            "pretreatment": "Cribado y homogeneización",
            "primary": "Coagulación/floculación y sedimentación",
            "secondary": "Tratamiento biológico aerobio",
            "tertiary": "Filtración y desinfección",
            "efficiency": "Recuperación de hasta 50% del agua para reúso",
            "description": "Sistema estándar para tratamiento de aguas residuales industriales",
        }

        # Solución genérica comercial
        commercial_solution = {
            "pretreatment": "Filtración gruesa",
            "primary": "Tratamiento fisicoquímico",
            "secondary": "Filtración biológica",
            "tertiary": "Desinfección UV",
            "efficiency": "Recuperación de hasta 80% para usos no potables",
            "description": "Sistema compacto para tratamiento de aguas grises comerciales",
        }

        # Solución para residencial
        residential_solution = {
            "pretreatment": "Filtración de sólidos",
            "primary": "Tratamiento biológico compacto",
            "secondary": "Clarificación",
            "tertiary": "Desinfección",
            "efficiency": "Recuperación de hasta 90% para riego y sanitarios",
            "description": "Sistema modular para viviendas, optimizado para espacios reducidos",
        }

        # Determinar solución base según sector
        if sector == "Industrial":
            # Buscar solución específica para el subsector
            solution = default_solutions.get(subsector, industrial_solution)
        elif sector == "Comercial":
            solution = commercial_solution
        elif sector == "Residencial":
            solution = residential_solution
        else:  # Municipal u otros
            solution = industrial_solution

        # Adaptar la solución según parámetros detectados
        if parameters:
            # Adaptar según pH
            if "ph" in parameters:
                try:
                    ph_value = float(str(parameters["ph"]).replace(",", "."))
                    if ph_value < 6 or ph_value > 9:
                        solution["pretreatment"] = (
                            f"{solution['pretreatment']} con ajuste de pH"
                        )
                except (ValueError, TypeError):
                    pass

            # Adaptar según DQO alta
            if "dqo" in parameters:
                try:
                    dqo_value = float(
                        str(parameters["dqo"]).replace(",", ".").split()[0]
                    )
                    if dqo_value > 1000:
                        solution["secondary"] = (
                            "Tratamiento biológico de alta eficiencia para carga orgánica elevada"
                        )
                except (ValueError, TypeError, IndexError):
                    pass

            # Adaptar según SST altos
            if "sst" in parameters:
                try:
                    sst_value = float(
                        str(parameters["sst"]).replace(",", ".").split()[0]
                    )
                    if sst_value > 500:
                        solution["primary"] = (
                            "Sistema avanzado de separación de sólidos (DAF de alta eficiencia)"
                        )
                except (ValueError, TypeError, IndexError):
                    pass

        return solution

    def _generate_economic_analysis(
        self, water_consumption: str, treatment_solution: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Genera un análisis económico basado en el consumo de agua y la solución

        Args:
            water_consumption: Consumo de agua reportado
            treatment_solution: Solución de tratamiento recomendada

        Returns:
            Análisis económico con CAPEX, OPEX y ROI
        """
        # Extraer valor numérico del consumo de agua
        flow_value = 100  # m³/día por defecto
        daily = True

        if isinstance(water_consumption, str):
            # Buscar valores numéricos y unidades
            match = re.search(
                r"(\d+(?:[\.,]\d+)?)\s*(m3|m³|litros|l)",
                water_consumption,
                re.IGNORECASE,
            )
            if match:
                value_str, unit = match.groups()
                value = float(value_str.replace(",", "."))

                # Convertir a m³/día si es necesario
                if unit.lower() in ["litros", "l"]:
                    value = value / 1000  # Convertir litros a m³

                # Determinar si es diario, mensual o anual
                if (
                    "día" in water_consumption.lower()
                    or "dia" in water_consumption.lower()
                    or "/d" in water_consumption.lower()
                ):
                    flow_value = value
                    daily = True
                elif (
                    "mes" in water_consumption.lower()
                    or "month" in water_consumption.lower()
                ):
                    flow_value = value / 30
                    daily = False
                elif (
                    "año" in water_consumption.lower()
                    or "anual" in water_consumption.lower()
                    or "year" in water_consumption.lower()
                ):
                    flow_value = value / 365
                    daily = False
                else:
                    # Si no especifica, asumir que es diario
                    flow_value = value
                    daily = True

        # Estimar CAPEX basado en caudal (simple aproximación)
        if daily:
            # Si es consumo diario, usar directamente
            capex_base = flow_value * 1000  # $1000 USD por m³/día
        else:
            # Si ya se convirtió a diario
            capex_base = flow_value * 1000

        # Ajustar CAPEX según la complejidad de la solución
        complexity_factor = 1.0
        if "MBR" in treatment_solution.get("secondary", ""):
            complexity_factor = 1.3  # MBR es más caro
        elif "UASB" in treatment_solution.get("secondary", ""):
            complexity_factor = 1.2  # UASB es intermedio

        if "avanzada" in treatment_solution.get("tertiary", "").lower():
            complexity_factor += 0.2  # Tratamiento terciario avanzado

        # Calcular CAPEX final con un mínimo de $30,000
        capex = max(30000, capex_base * complexity_factor)

        # Estimar OPEX mensual (aproximadamente 2% del CAPEX al mes)
        opex_monthly = capex * 0.02

        # Estimar ahorro mensual y ROI
        water_cost_per_m3 = 2.0  # $2.0 USD/m³ por defecto
        discharge_cost_per_m3 = 1.0  # $1.0 USD/m³ por defecto

        # Calcular ahorro basado en la eficiencia de recuperación
        efficiency_text = treatment_solution.get("efficiency", "")
        efficiency_match = re.search(r"(\d+)%", efficiency_text)
        efficiency = 0.5  # 50% por defecto
        if efficiency_match:
            efficiency = float(efficiency_match.group(1)) / 100

        # Calcular ahorro mensual
        if daily:
            monthly_consumption = flow_value * 30  # m³/mes
        else:
            monthly_consumption = flow_value * 30

        monthly_savings = (
            monthly_consumption * efficiency * water_cost_per_m3
        ) + (  # Ahorro en compra de agua
            monthly_consumption * 0.8 * efficiency * discharge_cost_per_m3
        )  # Ahorro en descarga

        # Calcular ROI en años
        if monthly_savings > 0:
            roi_years = capex / (monthly_savings * 12)
        else:
            roi_years = 10  # Valor por defecto

        # Limitar ROI a un rango razonable
        roi_years = max(1.0, min(10.0, roi_years))

        return {
            "capex": round(capex, 2),
            "opex_monthly": round(opex_monthly, 2),
            "opex_annual": round(opex_monthly * 12, 2),
            "monthly_savings": round(monthly_savings, 2),
            "annual_savings": round(monthly_savings * 12, 2),
            "roi": round(roi_years, 1),
            "flow_rate": flow_value,
            "water_cost": water_cost_per_m3,
            "reuse_efficiency": efficiency,
        }

    def format_proposal_summary(
        self, proposal: Dict[str, Any], conversation_id: str = None
    ) -> str:
        """
        Genera un resumen de la propuesta en formato markdown siguiendo el estilo mejorado.
        """

        client_info = proposal.get("client_info", {})
        sector = client_info.get("sector", "")
        subsector = client_info.get("subsector", "")
        name = client_info.get("name", "Cliente")

        summary = f"""
# 🧾 Propuesta de Tratamiento y Reúso de Agua

    **Cliente:** {name}  
    **Ubicación:** {client_info.get('location', 'No especificada')}  
    **Industria:** {sector} - {subsector}  
    **Volumen tratado:** {proposal.get('project_details', {}).get('water_consumption', 'No especificado')}  
    **Objetivo principal:** {proposal.get('project_details', {}).get('objectives', ['No especificado'])[0]}

## 1. 🎯 **Objetivo del Proyecto**

    {self._generate_objectives_section(proposal)}

## 2. 📈 **Diagnóstico Inicial**

    - **Consumo actual:** {proposal.get('project_details', {}).get('water_consumption', 'No especificado')}
    - **Generación de agua residual:** {proposal.get('project_details', {}).get('wastewater_generation', 'No especificado')}
    - **Descarga actual:** {proposal.get('project_details', {}).get('discharge_location', 'No especificado')}

    🧪 *{self._get_sector_specific_insight(sector, subsector)}*

## 3. 🔧 **Tren de Tratamiento Propuesto**

    | **Etapa** | **Tecnología Sugerida** | **Función** |
    |------------|------------------------|-------------|
    """

        # Añadir etapas de tratamiento dinámicamente basadas en sector/subsector
        treatment_stages = self._get_treatment_stages_for_sector(sector, subsector)
        for stage in treatment_stages:
            summary += f"| **{stage['name']}** | **{stage['technology']}** | {stage['function']} |\n"

        summary += f"""
## 4. 📐 **Dimensionamiento Preliminar**

    | **Etapa** | **Volumen Estimado** |
    |-----------|----------------------|
    """

        # Añadir dimensionamiento dinámicamente
        volumes = self._calculate_treatment_volumes(proposal)
        for stage, volume in volumes.items():
            summary += f"| {stage} | {volume} |\n"

        summary += f"""
## 5. 💸 **Costos Estimados**

### CAPEX -- Inversión Inicial

    - Rango estimado: **{proposal.get('economic_analysis', {}).get('capex', 'No especificado')} USD**

### OPEX -- Costo Operativo Mensual

    - Total estimado: **{proposal.get('economic_analysis', {}).get('opex_monthly', 'No especificado')} USD/mes**
    - Químicos: {proposal.get('economic_analysis', {}).get('chemical_cost', 'No especificado')} USD
    - Energía: {proposal.get('economic_analysis', {}).get('energy_cost', 'No especificado')} USD
    - Personal + Mantenimiento: {proposal.get('economic_analysis', {}).get('labor_cost', 0) + proposal.get('economic_analysis', {}).get('maintenance_cost', 0)} USD

## 6. 📊 **Beneficios Potenciales**

    - 🌊 **Reúso del 70-90% del agua tratada**
    - ✅ Cumplimiento normativo para descarga
    - 💧 Reducción en consumo de agua fresca
    - 💸 Ahorros significativos en mediano plazo
    - ♻️ Imagen corporativa y cumplimiento ambiental

## 7. 📌 **Siguientes Pasos Recomendados**

    1. Validar parámetros faltantes: SST, pH, temperatura
    2. Confirmar espacio disponible para layout
    3. Revisión de cotización técnica detallada (Hydrous puede apoyar)
    4. Evaluar opciones de financiamiento
    """

        # Agregar enlace de descarga si tenemos ID de conversación
        if conversation_id:
            summary += f"""
# 📥 Descargar Propuesta Completa

    Para obtener esta propuesta detallada en formato PDF, puede usar el siguiente enlace:

    **[👉 DESCARGAR PROPUESTA EN PDF](/api/chat/{conversation_id}/download-proposal-pdf)**
    """

        return summary

    # Función para obtener insight específico del sector

    def _get_sector_specific_insight(self, sector: str, subsector: str) -> str:
        """Devuelve un dato técnico relevante específico para el sector/subsector"""
        insights = {
            "Textil": "Las aguas residuales textiles típicamente contienen altas concentraciones de colorantes y requieren tratamientos específicos para remoción de color",
            "Alimentos y Bebidas": "Las aguas residuales de alimentos contienen principalmente materia orgánica biodegradable, ideal para tratamientos biológicos con recuperación energética",
            "Petroquímica": "Los efluentes petroquímicos contienen hidrocarburos y compuestos recalcitrantes que requieren tecnologías avanzadas de oxidación",
        }

        return insights.get(
            subsector,
            f"El sector {sector} presenta oportunidades significativas para la optimización del consumo hídrico",
        )

    # Añadir función para obtener etapas de tratamiento según sector/subsector
    def _get_treatment_stages_for_sector(
        self, sector: str, subsector: str
    ) -> List[Dict[str, str]]:
        """Devuelve las etapas de tratamiento recomendadas para un sector/subsector"""

        # Definir etapas por defecto
        default_stages = [
            {
                "name": "Pretratamiento",
                "technology": "Filtro rotatorio + trampa de grasas",
                "function": "Remover sólidos gruesos y materia orgánica",
            },
            {
                "name": "Tratamiento primario",
                "technology": "Coagulación/floculación",
                "function": "Remoción de sólidos suspendidos y coloides",
            },
            {
                "name": "Tratamiento biológico",
                "technology": "Sistema aerobio",
                "function": "Reducir DQO/DBO",
            },
            {
                "name": "Clarificación",
                "technology": "Sedimentación",
                "function": "Separar biomasa",
            },
            {
                "name": "Filtración",
                "technology": "Filtros multimedia",
                "function": "Pulido final",
            },
            {
                "name": "Desinfección",
                "technology": "UV",
                "function": "Eliminación de patógenos",
            },
        ]

        # Personalizar según subsector
        if subsector == "Textil":
            return [
                {
                    "name": "Pretratamiento",
                    "technology": "Cribado + homogeneización",
                    "function": "Remover sólidos y estabilizar flujo",
                },
                {
                    "name": "Tratamiento primario",
                    "technology": "DAF con coagulación específica",
                    "function": "Remoción de color y SST",
                },
                {
                    "name": "Tratamiento biológico",
                    "technology": "MBBR especializado",
                    "function": "Degradación de compuestos recalcitrantes",
                },
                {
                    "name": "Tratamiento terciario",
                    "technology": "Carbón activado + UV",
                    "function": "Remoción de color residual y desinfección",
                },
            ]
        elif subsector == "Alimentos y Bebidas":
            return [
                {
                    "name": "Pretratamiento",
                    "technology": "Tamizado + trampa de grasas",
                    "function": "Remoción de sólidos y grasas",
                },
                {
                    "name": "Ecualización",
                    "technology": "Tanque con mezclado",
                    "function": "Homogeneización de caudal y cargas",
                },
                {
                    "name": "Tratamiento anaerobio",
                    "technology": "UASB",
                    "function": "Reducción de DQO y generación de biogás",
                },
                {
                    "name": "Tratamiento aerobio",
                    "technology": "Lodos activados",
                    "function": "Pulido biológico",
                },
                {
                    "name": "Clarificación",
                    "technology": "Sedimentador",
                    "function": "Separación de biomasa",
                },
                {
                    "name": "Desinfección",
                    "technology": "UV o cloración",
                    "function": "Eliminación de patógenos",
                },
            ]

        return default_stages

    def _get_objective_description(self, objective):
        """Obtiene una descripción para cada objetivo"""
        objectives_map = {
            "Cumplimiento normativo": "Asegurar que el agua tratada cumpla con las regulaciones de descarga.",
            "Cumplimiento Regulatorio": "Asegurar que el agua tratada cumpla con las regulaciones de descarga.",
            "Reducción de la huella ambiental": "Mejorar el perfil ambiental mediante gestión eficiente del agua.",
            "Ahorro de costos": "Reducir gastos de agua y descarga mediante reutilización.",
            "Proyecto de retorno de inversión": "Garantizar recuperación de la inversión en un periodo razonable.",
            "Mayor disponibilidad de agua": "Asegurar suministro sostenible mediante recuperación y reúso.",
            "Sostenibilidad": "Mejorar la huella ambiental a través de la gestión eficiente del agua.",
            "Optimización de Costos": "Reducir gastos operativos relacionados con agua potable y descargas.",
        }

        return objectives_map.get(
            objective, "Optimizar la gestión del agua para beneficios operativos."
        )

    def generate_proposal_pdf(self, proposal: Dict[str, Any]) -> str:
        """
        Genera un PDF basado en la propuesta
        """

        try:
            # Extraer información básica
            client_info = proposal.get("client_info", {})
            client_name = client_info.get("name", "Cliente").replace(" ", "_")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Obtener el contenido de la propuesta
            proposal_text = proposal.get("proposal_text", "")

            # Si no hay texto de propuesta, crear uno básico
            if not proposal_text:
                proposal_text = f"""
# 🧾 Propuesta Preliminar de Tratamiento y Reúso de Agua

    **Cliente:** {client_info.get('name', 'Cliente')}
    **Ubicación:** {client_info.get('location', 'No especificada')}
    **Industria:** {client_info.get('sector', 'Industrial')} - {client_info.get('subsector', '')}
    **Volumen tratado:** {proposal.get('technical_info', {}).get('water_consumption', 'No especificado')}
    **Objetivo principal:** {proposal.get('technical_info', {}).get('objectives', 'Optimización de recursos hídricos')}

## 1. 🎯 Objetivo del Proyecto
    Diseñar un sistema eficiente de tratamiento y reúso de agua adaptado a las necesidades específicas del cliente.

## 2. 📈 Diagnóstico Inicial
    - **Consumo de agua:** {proposal.get('technical_info', {}).get('water_consumption', 'No especificado')}
    - **Generación de agua residual:** {proposal.get('technical_info', {}).get('wastewater_generation', 'No especificado')}
    - **Costo actual del agua:** {proposal.get('technical_info', {}).get('water_cost', 'No especificado')}

## 3. 🔧 Tren de Tratamiento Propuesto
    Pendiente de desarrollar basado en información adicional.

## 4. 📐 Dimensionamiento Preliminar
    Pendiente de desarrollar basado en información adicional.

## 5. 💸 Costos Estimados
    Pendiente de desarrollar basado en información adicional.

## 6. 📊 Beneficios Potenciales
    - 🌊 Reúso del agua
    - ✅ Cumplimiento normativo
    - 💧 Reducción en consumo de agua fresca
    - 💸 Ahorros económicos

## 7. 📌 Siguientes Pasos Recomendados
    1. Completar la recopilación de información técnica
    2. Realizar pruebas de calidad del agua
    3. Desarrollar propuesta detallada
    4. Evaluar opciones de financiamiento
    """

            # Convertir formato Markdown a HTML
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Propuesta Hydrous - {client_info.get('name', 'Cliente')}</title>
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
                    
                    body {{ 
                        font-family: 'Roboto', Arial, sans-serif; 
                        line-height: 1.6; 
                        color: #333; 
                        margin: 0;
                        padding: 0;
                        background-color: #f9fafb;
                    }}
                    
                    .container {{
                        max-width: 800px;
                        margin: 40px auto;
                        padding: 30px;
                        background-color: white;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                        border-radius: 8px;
                    }}
                    
                    h1 {{ color: #1a5276; font-size: 24px; margin-top: 30px; }}
                    h2 {{ color: #2874a6; font-size: 20px; margin-top: 25px; }}
                    
                    .header {{ 
                        background-color: #2c3e50; 
                        background-image: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
                        color: white; 
                        padding: 30px; 
                        text-align: center; 
                        margin-bottom: 30px;
                        border-radius: 8px 8px 0 0;
                    }}
                    
                    .logo-text {{
                        font-size: 32px;
                        font-weight: bold;
                        color: white;
                        margin-bottom: 10px;
                    }}
                    
                    table {{ 
                        border-collapse: collapse; 
                        width: 100%; 
                        margin: 20px 0; 
                    }}
                    
                    th, td {{ 
                        border: 1px solid #ddd; 
                        padding: 10px; 
                        text-align: left; 
                    }}
                    
                    th {{ background-color: #f2f2f2; }}
                    
                    .footer {{ 
                        text-align: center; 
                        margin-top: 40px; 
                        font-size: 0.9em; 
                        color: #777;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <div class="logo-text">HYDROUS</div>
                        <h1>Propuesta de Solución de Tratamiento de Agua</h1>
                    </div>
                    
                    <div class="content">
                        {self._markdown_to_html(proposal_text)}
                    </div>
                    
                    <div class="footer">
                        <p>Hydrous Management Group © {datetime.now().year}</p>
                        <p>Propuesta generada el {datetime.now().strftime('%d/%m/%Y')}</p>
                        <p>Documento confidencial para uso exclusivo del cliente</p>
                    </div>
                </div>
            </body>
            </html>
            """

            # Guardar como HTML
            html_path = os.path.join(
                settings.UPLOAD_DIR, f"{client_name}_propuesta_{timestamp}.html"
            )
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            # Intentar generar PDF si hay bibliotecas disponibles
            if PDF_GENERATORS:
                pdf_path = os.path.join(
                    settings.UPLOAD_DIR, f"{client_name}_propuesta_{timestamp}.pdf"
                )

                # Intentar con WeasyPrint primero
                if "weasyprint" in PDF_GENERATORS:
                    try:
                        from weasyprint import HTML

                        HTML(string=html_content).write_pdf(pdf_path)
                        return pdf_path
                    except Exception as e:
                        logger.warning(f"Error al generar PDF con WeasyPrint: {e}")

                # Si falla, intentar con pdfkit
                if "pdfkit" in PDF_GENERATORS:
                    try:
                        import pdfkit

                        pdfkit.from_string(html_content, pdf_path)
                        return pdf_path
                    except Exception as e:
                        logger.warning(f"Error al generar PDF con pdfkit: {e}")

            # Si no se pudo generar PDF, devolver HTML
            return html_path

        except Exception as e:
            logger.error(f"Error al generar propuesta: {str(e)}")
            # Devolver página de error HTML
            error_html_path = os.path.join(
                settings.UPLOAD_DIR,
                f"error_propuesta_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
            )

            with open(error_html_path, "w", encoding="utf-8") as f:
                f.write(
                    f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Error al Generar Propuesta</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; padding: 30px; }}
                        .error-box {{ background: #f8d7da; padding: 20px; border-radius: 5px; }}
                    </style>
                </head>
                <body>
                    <h1>Error al Generar la Propuesta</h1>
                    <div class="error-box">
                        <p>Se produjo un error al generar la propuesta: {str(e)}</p>
                    </div>
                    <p>Por favor, intente nuevamente o contacte con soporte técnico.</p>
                </body>
                </html>
                """
                )

            return error_html_path

    def _markdown_to_html(self, markdown_text: str) -> str:
        """Convierte Markdown a HTML de forma básica"""
        try:
            if markdown2:
                return markdown2.markdown(
                    markdown_text, extras=["tables", "fenced-code-blocks"]
                )
            else:
                # Conversión básica si no está disponible markdown2
                html = markdown_text
                # Encabezados
                html = re.sub(r"^# (.*?)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
                html = re.sub(r"^## (.*?)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
                html = re.sub(r"^### (.*?)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
                # Negrita
                html = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html)
                # Cursiva
                html = re.sub(r"\*(.*?)\*", r"<em>\1</em>", html)
                # Listas
                html = re.sub(r"^- (.*?)$", r"<li>\1</li>", html, flags=re.MULTILINE)
                # Párrafos
                html = re.sub(r"([^\n])\n([^\n])", r"\1<br>\2", html)
                html = re.sub(r"\n\n", r"</p><p>", html)
                html = "<p>" + html + "</p>"
                return html
        except Exception as e:
            logger.warning(f"Error al convertir Markdown a HTML: {e}")
            return f"<pre>{markdown_text}</pre>"


# Instancia global del servicio
questionnaire_service = QuestionnaireService()
