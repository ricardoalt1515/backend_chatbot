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

    def enerate_preliminary_diagnosis(self, conversation: Conversation) -> str:
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

    def generate_proposal_summary(
        self, proposal: Dict[str, Any], conversation_id: str = None
    ) -> str:
        """Genera un resumen de la propuesta en formato markdown siguiendo la estructura especificada"""
        client_info = proposal.get("client_info", {})
        sector = client_info.get("sector", "")
        subsector = client_info.get("subsector", "")
        name = client_info.get("name", "Cliente")

        summary = f"""
    # PROPUESTA DE SOLUCIÓN DE TRATAMIENTO DE AGUAS RESIDUALES PARA {name.upper()}

    ## 1. Introducción a Hydrous Management Group

    Hydrous Management Group se especializa en **soluciones personalizadas de tratamiento de aguas residuales** para clientes {sector.lower()}es, con enfoque en el subsector {subsector}. Nuestra experiencia en gestión del agua ayuda a las empresas a lograr **cumplimiento normativo, reducción de costos y reutilización sostenible**.

    ## 2. Antecedentes del Proyecto

    **Cliente**: {name}  
    **Sector**: {sector} - {subsector}  
    **Ubicación**: {client_info.get('location', 'No especificada')}  
    **Consumo actual de agua**: {proposal.get('water_consumption', 'No especificado')}  
    **Generación de aguas residuales**: {proposal.get('wastewater_generation', 'No especificado')}

    ## 3. Objetivo del Proyecto

    {self._generate_objectives_section(proposal)}

    ## 4. Supuestos Clave de Diseño

    {self._generate_assumptions_section(proposal)}

    ## 5. Diseño de Procesos y Alternativas de Tratamiento

    {self._generate_treatment_process_section(proposal)}

    ## 6. Equipo y Tamaño Sugeridos

    {self._generate_equipment_section(proposal)}

    ## 7. Estimación de CAPEX y OPEX

    {self._generate_cost_section(proposal)}

    ## 8. Análisis del Retorno de la Inversión (ROI)

    {self._generate_roi_section(proposal)}

    ## 9. Preguntas y Respuestas

    Si tiene cualquier pregunta sobre esta propuesta, no dude en consultarnos.
    """

        # Agregar enlace de descarga si tenemos ID de conversación
        if conversation_id:
            summary += f"""
        **Para obtener esta propuesta detallada en formato PDF, simplemente haga clic en el siguiente enlace:**

        [📥 DESCARGAR PROPUESTA EN PDF](/api/chat/{conversation_id}/download-proposal-pdf)

        *Esta propuesta es preliminar y se basa en la información proporcionada. Los costos y especificaciones finales pueden variar tras un estudio detallado del sitio.*
        """

        return summary

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
        Procesa una respuesta y actualiza el estado del cuestionario

        Args:
            conversation: Conversación actual
            question_id: ID de la pregunta respondida
            answer: Respuesta proporcionada
        """
        # Guardar la respuesta
        conversation.questionnaire_state.answers[question_id] = answer

        # Si es una respuesta al sector o subsector, actualizar esos campos
        if question_id == "sector_selection":
            # Puede ser índice numérico o texto directo
            if isinstance(answer, str) and answer.isdigit():
                sector_index = int(answer) - 1
                sectors = self.get_sectors()
                if 0 <= sector_index < len(sectors):
                    conversation.questionnaire_state.sector = sectors[sector_index]
                    # Establecer especificamente la siguiente pregunta
                    conversation.questionnaire_state.current_question_id = (
                        "subsector_selection"
                    )
                    return
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
            "name": info.get("name", "Cliente"),
            "location": info.get("location", "No especificada"),
            "sector": info.get("sector", "Industrial"),
            "subsector": info.get("subsector", ""),
        }

        # Datos del proyecto
        project_details = {
            "water_consumption": info.get("water_consumption", "No especificado"),
            "wastewater_generation": info.get(
                "wastewater_generation", "No especificado"
            ),
            "objectives": info.get("objectives", ["Mejorar eficiencia hídrica"]),
            "reuse_objectives": info.get("reuse_objectives", ["Reutilización de agua"]),
        }

        # Obtener parámetros de agua detectados
        parameters = info.get("parameters", {})

        # Determinar la solución recomendada según sector/subsector y parámetros
        treatment_solution = self._determine_treatment_solution(
            client_info["sector"], client_info["subsector"], parameters
        )

        # Generar análisis económico
        economic_analysis = self._generate_economic_analysis(
            project_details["water_consumption"], treatment_solution
        )

        # Construcción de propuesta completa
        proposal = {
            "client_info": client_info,
            "project_details": project_details,
            "water_parameters": parameters,
            "recommended_solution": treatment_solution,
            "economic_analysis": economic_analysis,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        # Agregar información de documentos si está disponible
        try:
            from app.services.document_service import document_service

            document_insights = document_service.get_insights_for_conversation_sync(
                conversation.id
            )

            if document_insights:
                doc_section = {
                    "provided": True,
                    "count": len(document_insights),
                    "types": list(
                        set(
                            d["insights"].get("document_type", "unknown")
                            for d in document_insights
                        )
                    ),
                    "relevant_info": [],
                }

                # Recopilar información relevante de documentos
                for doc in document_insights:
                    insights = doc.get("insights", {})
                    doc_parameters = insights.get("parameters", {})

                    # Añadir parámetros detectados en documentos
                    parameters.update(doc_parameters)

                    # Añadir información relevante
                    if insights.get("relevance") in [
                        "highly_relevant",
                        "potentially_relevant",
                    ]:
                        doc_section["relevant_info"].append(
                            {
                                "filename": doc.get("filename", ""),
                                "summary": insights.get("summary", ""),
                                "key_points": insights.get("key_points", []),
                            }
                        )

                proposal["documents"] = doc_section
        except Exception as e:
            logger.error(f"Error al obtener insights de documentos: {str(e)}")

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
        Genera un resumen de la propuesta en formato markdown siguiendo EXACTAMENTE
        la estructura del documento Format Proposal.docx
        """
        client_info = proposal.get("client_info", {})
        project_details = proposal.get("project_details", {})
        solution = proposal.get("recommended_solution", {})
        economic = proposal.get("economic_analysis", {})
        water_params = proposal.get("water_parameters", {})

        # Recuperar datos básicos
        company_name = client_info.get("name", "Cliente")
        sector = client_info.get("sector", "Industrial")
        subsector = client_info.get("subsector", "")
        location = client_info.get("location", "No especificada")
        water_consumption = project_details.get("water_consumption", "No especificado")
        wastewater_generation = project_details.get(
            "wastewater_generation", "No especificado"
        )

        # Construir la propuesta siguiendo exactamente el formato especificado
        summary = f"""
# **Hydrous Management Group -- Propuesta de Tratamiento de Aguas Residuales**

## **📌 Aviso Importante**

Esta propuesta fue **generada usando IA** basada en la información
proporcionada por el usuario final y **estándares de la industria**. Si bien
se ha hecho todo lo posible para garantizar la precisión, los datos, estimaciones de costos
y recomendaciones técnicas **pueden contener errores y no son legalmente
vinculantes**. Se recomienda que todos los detalles sean **validados por Hydrous
Management Group** antes de la implementación.

Si se proporcionó un **número de teléfono o información de contacto**, un
representante de **Hydrous Management Group se pondrá en contacto** para
mayor discusión. Si no, puede contactarnos en **info@hydrous.com**
para consultas o aclaraciones adicionales.

## **1. Introducción a Hydrous Management Group**

Hydrous Management Group se especializa en **soluciones personalizadas de tratamiento de aguas residuales** 
adaptadas para clientes industriales y comerciales.
Nuestra **experiencia en gestión del agua** ayuda a las empresas a lograr
**cumplimiento normativo, reducción de costos y reutilización sostenible del agua**.

Utilizando tecnologías avanzadas de tratamiento y diseño potenciado por IA, Hydrous
ofrece soluciones de aguas residuales **eficientes, escalables y rentables** que optimizan 
el rendimiento operativo mientras minimizan el impacto ambiental.

## **2. Antecedentes del Proyecto**

Esta sección proporciona una visión general de las instalaciones del cliente, la industria
y las necesidades de tratamiento de aguas residuales.

| **Información del Cliente** | **Detalles** |
|---------------------------|-------------------------------------------|
| **Nombre del Cliente** | {company_name} |
| **Ubicación** | {location} |
| **Industria** | {sector} - {subsector} |
| **Fuente de Agua** | {project_details.get("water_source", "Suministro Municipal/Pozo")} |
| **Consumo Actual de Agua** | {water_consumption} |
| **Generación Actual de Aguas Residuales** | {wastewater_generation} |
| **Sistema de Tratamiento Existente (si existe)** | {client_info.get("sistema_existente", "No existe tratamiento")} |

## **3. Objetivo del Proyecto**

Definir claramente los **objetivos primarios** para el tratamiento de aguas residuales.

    """

        # Añadir objetivos basados en la información recopilada
        objectives = project_details.get("objectives", [])
        if not objectives or not isinstance(objectives, list):
            objectives = [
                "Cumplimiento Regulatorio",
                "Optimización de Costos",
                "Reutilización del Agua",
                "Sostenibilidad",
            ]

        for obj in objectives:
            summary += f"✅ **{obj}** -- {self._get_objective_description(obj)}\n"

        # Sección 4: Supuestos Clave de Diseño y Comparación
        summary += """
## **4. Supuestos Clave de Diseño & Comparación con Estándares de la Industria**

Esta sección compara las **características del agua residual sin tratar** proporcionadas por
el cliente con **valores estándar de la industria** para aguas residuales industriales similares. 
También describe la calidad objetivo del efluente para cumplimiento o reutilización.

| **Parámetro** | **Agua Residual Sin Tratar (Proporcionada por Cliente)** | **Estándar de la Industria para {subsector}** | **Objetivo del Efluente (Requisito Regulatorio/Reutilización)** | **Estándar de Efluente (Referencia)** |
|---------------|----------------|---------------------|------------------------|-----------------|
    """

        # Añadir parámetros de agua específicos según el subsector
        if subsector == "Textil":
            params = [
                (
                    "SST (mg/L)",
                    water_params.get("sst", "800"),
                    "500 - 1,000",
                    "≤50",
                    "10 - 50",
                ),
                (
                    "TDS (mg/L)",
                    water_params.get("sdt", "3,000"),
                    "1,500 - 5,000",
                    "Varía según reutilización",
                    "≤500 - 1,500",
                ),
                (
                    "DQO (mg/L)",
                    water_params.get("dqo", "1,100"),
                    "800 - 2,500",
                    "≤250",
                    "≤200 - 300",
                ),
                (
                    "DBO (mg/L)",
                    water_params.get("dbo", "700"),
                    "300 - 1,200",
                    "≤50",
                    "≤30 - 50",
                ),
                (
                    "pH",
                    water_params.get("ph", "4"),
                    "4.5 - 6.5",
                    "6.5 - 7.5",
                    "6.5 - 7.5",
                ),
            ]
        elif subsector == "Alimentos y Bebidas":
            params = [
                (
                    "SST (mg/L)",
                    water_params.get("sst", "600"),
                    "400 - 800",
                    "≤50",
                    "10 - 50",
                ),
                (
                    "TDS (mg/L)",
                    water_params.get("sdt", "2,000"),
                    "1,200 - 3,000",
                    "Varía según reutilización",
                    "≤500 - 1,500",
                ),
                (
                    "DQO (mg/L)",
                    water_params.get("dqo", "2,500"),
                    "1,500 - 5,000",
                    "≤250",
                    "≤200 - 300",
                ),
                (
                    "DBO (mg/L)",
                    water_params.get("dbo", "1,500"),
                    "900 - 3,000",
                    "≤50",
                    "≤30 - 50",
                ),
                (
                    "Grasas y Aceites (mg/L)",
                    water_params.get("grasas_aceites", "300"),
                    "200 - 600",
                    "≤15",
                    "≤10 - 20",
                ),
                (
                    "pH",
                    water_params.get("ph", "5.5"),
                    "4.0 - 7.0",
                    "6.5 - 7.5",
                    "6.5 - 7.5",
                ),
            ]
        else:
            params = [
                (
                    "SST (mg/L)",
                    water_params.get("sst", "Variable*"),
                    "Según subsector",
                    "≤50",
                    "10 - 50",
                ),
                (
                    "TDS (mg/L)",
                    water_params.get("sdt", "Variable*"),
                    "Según subsector",
                    "Varía según reutilización",
                    "≤500 - 1,500",
                ),
                (
                    "DQO (mg/L)",
                    water_params.get("dqo", "Variable*"),
                    "Según subsector",
                    "≤250",
                    "≤200 - 300",
                ),
                (
                    "DBO (mg/L)",
                    water_params.get("dbo", "Variable*"),
                    "Según subsector",
                    "≤50",
                    "≤30 - 50",
                ),
                (
                    "pH",
                    water_params.get("ph", "Variable*"),
                    "6.0 - 9.0",
                    "6.5 - 7.5",
                    "6.5 - 7.5",
                ),
            ]

        # Agregar filas a la tabla de parámetros
        for param, actual, industry, target, benchmark in params:
            summary += f"| {param} | {actual} | {industry} | {target} | {benchmark} |\n"

        # Sección 5: Diseño de Procesos y Alternativas
        summary += """
## **5. Diseño de Procesos & Alternativas de Tratamiento**

Esta sección describe las **tecnologías de tratamiento recomendadas** y
posibles **alternativas** para cumplir con los objetivos de tratamiento de aguas residuales.

| **Etapa de Tratamiento** | **Tecnología Recomendada** | **Opción Alternativa** |
|----------------------|----------------------------|------------------------|
    """

        # Generar etapas de tratamiento según el subsector
        if subsector == "Textil":
            treatments = [
                (
                    "**Pretratamiento**",
                    "**Flotación por Aire Disuelto (DAF)** -- Elimina grasas, aceites y sólidos suspendidos.",
                    "**Coagulación & Sedimentación** -- Menos efectiva pero de menor costo.",
                ),
                (
                    "**Ajuste de pH**",
                    "**Dosificación Química (Cal, NaOH, H₂SO₄)** -- Estabiliza niveles de pH.",
                    "**Neutralización Basada en Aireación** -- Proceso más lento pero libre de químicos.",
                ),
                (
                    "**Tratamiento Secundario (Biológico)**",
                    "**Reactor de Biopelícula de Lecho Móvil (MBBR)** -- Reducción eficiente de DQO/DBO.",
                    "**Proceso de Lodos Activados (ASP)** -- Requiere más espacio y energía.",
                ),
                (
                    "**Tratamiento Terciario (Pulido Final & Desinfección)**",
                    "**Filtración de Arena & Carbón** -- Elimina orgánicos residuales y sólidos.",
                    "**Biorreactor de Membrana (MBR)** -- Efluente de alta calidad, mayor costo.",
                ),
                (
                    "**Desinfección**",
                    "**Desinfección UV / Cloración** -- Elimina patógenos.",
                    "**Ozonización** -- Más efectiva pero intensiva en energía.",
                ),
                (
                    "**Sistema de Reutilización del Agua (Opcional)**",
                    "**Ósmosis Inversa (RO) / Ultrafiltración (UF)** -- Para reutilización de agua de alta calidad.",
                    "**Electrodiálisis (ED)** -- Alternativa para remoción selectiva de iones.",
                ),
            ]
        elif subsector == "Alimentos y Bebidas":
            treatments = [
                (
                    "**Pretratamiento**",
                    "**Trampa de Grasas y Cribado** -- Elimina grasas y sólidos gruesos.",
                    "**Flotación por Aire Disuelto (DAF)** -- Mayor eficiencia, mayor costo.",
                ),
                (
                    "**Ajuste de pH**",
                    "**Dosificación Química (Ácido/Base)** -- Estabiliza niveles de pH.",
                    "**Neutralización Biológica** -- Sostenible para fluctuaciones pequeñas.",
                ),
                (
                    "**Tratamiento Secundario (Biológico)**",
                    "**Sistema Anaerobio-Aerobio Combinado** -- Eficiente para alta carga orgánica.",
                    "**Lodos Activados Convencionales** -- Tecnología probada, mayor huella.",
                ),
                (
                    "**Tratamiento Terciario (Pulido Final)**",
                    "**Filtración Multimedia** -- Elimina sólidos residuales.",
                    "**Ultrafiltración (UF)** -- Mayor calidad de efluente.",
                ),
                (
                    "**Desinfección**",
                    "**Desinfección UV** -- Sin químicos residuales.",
                    "**Cloración** -- Económica pero con subproductos.",
                ),
                (
                    "**Manejo de Lodos**",
                    "**Deshidratación Mecánica** -- Reduce volumen para disposición.",
                    "**Digestión Aerobia** -- Estabiliza lodos biológicos.",
                ),
            ]
        else:
            treatments = [
                (
                    "**Pretratamiento**",
                    "**Sistema de Cribado y Homogeneización** -- Prepara el agua para tratamiento.",
                    "**Opción personalizada según características específicas.**",
                ),
                (
                    "**Tratamiento Primario**",
                    "**Proceso Físico-Químico** -- Remueve sólidos y contaminantes específicos.",
                    "**Tecnología adaptada a contaminantes del sector.**",
                ),
                (
                    "**Tratamiento Secundario**",
                    "**Sistema Biológico Optimizado** -- Reduce carga orgánica.",
                    "**Selección basada en biodegradabilidad de contaminantes.**",
                ),
                (
                    "**Tratamiento Terciario**",
                    "**Filtración Avanzada** -- Asegura calidad final.",
                    "**Sistema específico según requisitos de reúso/descarga.**",
                ),
                (
                    "**Desinfección**",
                    "**Sistema UV/Químico** -- Elimina patógenos residuales.",
                    "**Tecnología seleccionada según aplicación final del agua.**",
                ),
            ]

        # Agregar filas a la tabla de tratamientos
        for stage, recommended, alternative in treatments:
            summary += f"| {stage} | {recommended} | {alternative} |\n"

        # Sección 6: Equipo Sugerido y Dimensionamiento
        summary += """
## **6. Equipo Sugerido & Dimensionamiento**

Esta sección lista **equipos recomendados, capacidades, dimensiones y
posibles proveedores/modelos** cuando estén disponibles.

| **Equipo** | **Capacidad** | **Dimensiones** | **Marca/Modelo (Si Disponible)** |
|------------|---------------|-----------------|--------------------------------|
    """

        # Generar dimensiones de equipos basadas en consumo de agua
        flow_value = 100  # m³/día (valor por defecto)
        if isinstance(water_consumption, str):
            # Tratar de extraer un valor numérico del consumo de agua
            import re

            match = re.search(r"(\d+(?:\.\d+)?)", water_consumption)
            if match:
                try:
                    flow_value = float(match.group(1))
                except:
                    pass

        # Añadir equipos específicos según subsector
        if subsector == "Textil":
            equipment = [
                (
                    "**Sistema DAF**",
                    f"{flow_value/24:.1f} m³/h",
                    f"{flow_value*0.1:.1f} m² x 2.5 m altura",
                    "Marca A / Estándar Industrial",
                ),
                (
                    "**Sistema de Ajuste de pH**",
                    f"{flow_value/24:.1f} m³/h",
                    "Unidad Compacta",
                    "Estándar Industrial",
                ),
                (
                    "**Sistema MBBR**",
                    f"{flow_value/24:.1f} m³/h",
                    f"Tanque de {flow_value*0.3:.1f} m³",
                    "Marca B / Equivalente",
                ),
                (
                    "**Filtros de Arena & Carbón**",
                    f"{flow_value/24:.1f} m³/h",
                    f"Área de Filtración: {flow_value*0.01:.1f} m²",
                    "Marca C / Equivalente",
                ),
                (
                    "**Sistema UV**",
                    f"{flow_value/24:.1f} m³/h",
                    "Unidad Compacta",
                    "Marca D / Equivalente",
                ),
                (
                    "**Tanque de Agua Tratada**",
                    f"{flow_value*0.5:.1f} m³",
                    f"{flow_value*0.12:.1f} m² x 3 m altura",
                    "Estándar Industrial",
                ),
            ]
        elif subsector == "Alimentos y Bebidas":
            equipment = [
                (
                    "**Trampa de Grasas/Aceites**",
                    f"{flow_value/24:.1f} m³/h",
                    f"{flow_value*0.08:.1f} m³",
                    "Estándar Industrial",
                ),
                (
                    "**Tanque de Ecualización**",
                    f"{flow_value*0.4:.1f} m³",
                    f"{flow_value*0.1:.1f} m² x 3 m altura",
                    "Fabricación a Medida",
                ),
                (
                    "**Reactor Anaerobio**",
                    f"{flow_value/24:.1f} m³/h",
                    f"Volumen: {flow_value*0.25:.1f} m³",
                    "Marca B / Equivalente",
                ),
                (
                    "**Sistema Aerobio**",
                    f"{flow_value/24:.1f} m³/h",
                    f"Volumen: {flow_value*0.2:.1f} m³",
                    "Marca C / Equivalente",
                ),
                (
                    "**Sistema de Filtración**",
                    f"{flow_value/24:.1f} m³/h",
                    f"Área: {flow_value*0.01:.1f} m²",
                    "Marca D / Equivalente",
                ),
                (
                    "**Deshidratador de Lodos**",
                    f"{flow_value*0.01:.1f} m³/día de lodos",
                    "Unidad Compacta",
                    "Marca E / Equivalente",
                ),
            ]
        else:
            equipment = [
                (
                    "**Sistema de Pretratamiento**",
                    f"{flow_value/24:.1f} m³/h",
                    "Según requerimientos específicos",
                    "Selección según contaminantes",
                ),
                (
                    "**Sistema Primario**",
                    f"{flow_value/24:.1f} m³/h",
                    f"Área estimada: {flow_value*0.1:.1f} m²",
                    "Diseño a medida",
                ),
                (
                    "**Sistema Secundario**",
                    f"{flow_value/24:.1f} m³/h",
                    f"Volumen: {flow_value*0.3:.1f} m³",
                    "Tecnología seleccionada según caracterización",
                ),
                (
                    "**Sistema Terciario**",
                    f"{flow_value/24:.1f} m³/h",
                    f"Dimensiones según tecnología seleccionada",
                    "Según requerimientos de reúso",
                ),
                (
                    "**Tanque de Almacenamiento**",
                    f"{flow_value*0.5:.1f} m³",
                    f"Dimensiones: {flow_value*0.12:.1f} m² x 3 m altura",
                    "Estándar Industrial",
                ),
            ]

        # Agregar filas a la tabla de equipos
        for equip, capacity, dimensions, brand in equipment:
            summary += f"| {equip} | {capacity} | {dimensions} | {brand} |\n"

        # Sección 7: Estimación de CAPEX & OPEX
        summary += """
## **7. Estimación de CAPEX & OPEX**

Esta sección detalla tanto los **gastos de capital (CAPEX)** como los
**gastos operativos (OPEX)**.

**Desglose de CAPEX**

| **Categoría** | **Costo Estimado (USD)** | **Notas** |
|---------------|-------------------------|----------|
    """

        # Calcular CAPEX basado en flujo
        base_capex = flow_value * 1500  # $1500 USD por m³/día como referencia

        # Ajustar según complejidad del tratamiento
        complexity_factor = 1.0
        if "MBR" in str(solution) or subsector == "Textil":
            complexity_factor = (
                1.3  # Mayor complejidad para textil o sistemas avanzados
            )
        elif "Alimentos" in subsector:
            complexity_factor = 1.2  # Complejidad media para alimentos

        total_capex = base_capex * complexity_factor
        equipment_cost = total_capex * 0.6
        installation_cost = total_capex * 0.25
        engineering_cost = total_capex * 0.1
        contingency_cost = total_capex * 0.05

        # Agregar desglose de CAPEX
        summary += f"""| **Equipos de Tratamiento** | ${equipment_cost:,.2f} | Basado en instalaciones similares |
| **Instalación y Montaje** | ${installation_cost:,.2f} | Diseño escalable |
| **Ingeniería y Gestión** | ${engineering_cost:,.2f} | Incluye puesta en marcha |
| **Contingencia** | ${contingency_cost:,.2f} | Reserva para imprevistos |
| **CAPEX Total** | **${total_capex:,.2f}** | Rango estimado |
    """

        # OPEX Breakdown
        summary += """
**Desglose de OPEX**

| **Gasto Operativo** | **Costo Mensual Estimado (USD)** | **Notas** |
|---------------------|----------------------------------|----------|
    """

        # Calcular OPEX mensual
        energy_cost = flow_value * 3  # $3 por m³/día
        chemical_cost = flow_value * 2  # $2 por m³/día
        labor_cost = 1500 if flow_value < 200 else 3000  # Personal requerido
        maintenance_cost = total_capex * 0.01 / 12  # 1% del CAPEX anual, mensualizado
        sludge_cost = flow_value * 1  # $1 por m³/día

        total_opex_monthly = (
            energy_cost + chemical_cost + labor_cost + maintenance_cost + sludge_cost
        )

        # Agregar desglose de OPEX
        summary += f"""| **Costos de Químicos** | ${chemical_cost:,.2f} | Químicos para ajuste de pH y coagulación |
| **Costos de Energía** | ${energy_cost:,.2f} | Consumo eléctrico para aireación, bombas |
| **Costos de Mano de Obra** | ${labor_cost:,.2f} | Operador y personal de mantenimiento |
| **Disposición de Lodos** | ${sludge_cost:,.2f} | Remoción y tratamiento de lodos residuales |
| **Mantenimiento** | ${maintenance_cost:,.2f} | Repuestos y servicios preventivos |
| **OPEX Total** | **${total_opex_monthly:,.2f}/mes** | Rango estimado |
    """

        # Sección 8: Análisis del Retorno de la Inversión (ROI)
        summary += """
## **8. Análisis del Retorno de la Inversión (ROI)**

Ahorros de costos proyectados basados en **reducción de compras de agua y menores
tarifas de descarga**.

| **Parámetro** | **Costo Actual (USD/m³)** | **Costo Proyectado Después del Tratamiento** | **Ahorro Anual** |
|---------------|---------------------------|-------------------------------------------|----------------|
    """

        # Calcular ahorros y ROI
        water_cost = 2.0  # Por defecto USD/m³
        water_cost_text = client_info.get("costo_agua", "2.0 USD/m³")
        if isinstance(water_cost_text, str):
            import re

            cost_match = re.search(r"(\d+(?:\.\d+)?)", water_cost_text)
            if cost_match:
                try:
                    water_cost = float(cost_match.group(1))
                except:
                    pass

        discharge_cost = water_cost * 0.5  # Estimación de costo de descarga

        # Calcular ahorros mensuales
        water_savings_ratio = 0.6  # 60% reducción de consumo
        discharge_savings_ratio = 0.4  # 40% reducción de descarga

        monthly_water_volume = flow_value * 30  # Volumen mensual en m³
        monthly_water_savings = monthly_water_volume * water_savings_ratio * water_cost
        monthly_discharge_savings = (
            monthly_water_volume * discharge_savings_ratio * discharge_cost
        )

        annual_water_savings = monthly_water_savings * 12
        annual_discharge_savings = monthly_discharge_savings * 12
        total_annual_savings = annual_water_savings + annual_discharge_savings

        # Calcular ROI simple
        roi_years = total_capex / total_annual_savings

        # Agregar ahorros a la tabla
        summary += f"""| **Costo de Compra de Agua** | {water_cost:.2f} USD/m³ | {water_cost * (1-water_savings_ratio):.2f} USD/m³ (con reúso) | ${annual_water_savings:,.2f} |
| **Tarifas de Descarga** | ${monthly_water_volume * discharge_cost:,.2f}/mes | ${monthly_water_volume * discharge_cost * (1-discharge_savings_ratio):,.2f}/mes (carga reducida) | ${annual_discharge_savings:,.2f} |
    """

        # Añadir ROI estimado
        summary += f"""
**ROI Estimado:** **{roi_years:.1f} años** basado en ahorros de costos.

## **9. Anexo de Preguntas y Respuestas**

Adjuntar todas las **preguntas y respuestas clave** recopiladas durante la consulta como
referencia.

📩 **Para consultas o validación de esta propuesta, contacte a Hydrous Management Group en:** **info@hydrous.com**.

    """

        # Si tenemos ID de conversación, agregar enlace de descarga
        if conversation_id:
            summary += f"""
### **Descargar Propuesta Completa**

Para obtener esta propuesta detallada en formato PDF, puede usar el siguiente enlace:

[📥 **DESCARGAR PROPUESTA COMPLETA EN PDF**](/api/chat/{conversation_id}/download-proposal-pdf)
    """

        return summary

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
        Genera un PDF con la propuesta usando la plantilla oficial de Hydrous

        Args:
            proposal: Datos de la propuesta

        Returns:
            Ruta al archivo generado (PDF o HTML)
        """
        try:
            # Extraer información básica para el nombre del archivo
            client_info = proposal.get("client_info", {})
            client_name = client_info.get("name", "Cliente").replace(" ", "_")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            # Crear contenido HTML con estilo profesional
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Propuesta Hydrous - {client_info.get("name", "Cliente")}</title>
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
                    
                    body {{ 
                        font-family: 'Roboto', Arial, sans-serif; 
                        line-height: 1.6; 
                        color: #333; 
                        margin: 0;
                        padding: 0;
                    }}
                    
                    .container {{
                        max-width: 1000px;
                        margin: 0 auto;
                        padding: 20px 40px;
                    }}
                    
                    h1 {{ 
                        color: #1a5276; 
                        border-bottom: 2px solid #3498db; 
                        padding-bottom: 10px; 
                        font-size: 24px;
                        margin-top: 30px;
                    }}
                    
                    h2 {{ 
                        color: #2874a6; 
                        margin-top: 25px; 
                        font-size: 20px;
                        border-left: 4px solid #3498db;
                        padding-left: 10px;
                    }}
                    
                    .header {{ 
                        background-color: #2c3e50; 
                        background-image: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
                        color: white; 
                        padding: 30px 40px; 
                        text-align: center; 
                        margin-bottom: 30px;
                    }}
                    
                    .header h1 {{
                        border: none;
                        margin: 0;
                        padding: 0;
                        font-size: 32px;
                        color: white;
                    }}
                    
                    .footer {{ 
                        background-color: #f9f9f9; 
                        border-top: 1px solid #ddd;
                        padding: 20px; 
                        text-align: center; 
                        font-size: 0.9em; 
                        margin-top: 40px; 
                    }}
                    
                    .disclaimer {{ 
                        background-color: #f8f9fa; 
                        border-left: 4px solid #e74c3c; 
                        padding: 15px; 
                        margin: 25px 0; 
                        font-size: 0.9em;
                    }}
                    
                    table {{ 
                        border-collapse: collapse; 
                        width: 100%; 
                        margin: 20px 0; 
                    }}
                    
                    th, td {{ 
                        border: 1px solid #ddd; 
                        padding: 12px; 
                        text-align: left; 
                    }}
                    
                    th {{ 
                        background-color: #f2f2f2; 
                    }}
                    
                    tr:nth-child(even) {{
                        background-color: #f8f9fa;
                    }}
                    
                    .section {{
                        margin-bottom: 30px;
                        background-color: #fff;
                        border-radius: 5px;
                        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                        padding: 20px;
                    }}
                    
                    .highlight {{
                        background-color: #eaf2f8;
                        border-left: 4px solid #3498db;
                        padding: 15px;
                        margin: 20px 0;
                    }}
                    
                    .checkmark {{
                        color: #27ae60;
                        font-weight: bold;
                    }}
                    
                    .logo {{
                        text-align: center;
                        margin-bottom: 10px;
                    }}
                    
                    .logo-text {{
                        font-size: 40px;
                        font-weight: bold;
                        color: white;
                        letter-spacing: 2px;
                    }}
                    
                    .total-row {{
                        font-weight: bold;
                        background-color: #eaf2f8;
                    }}
                    
                    .download-button {{
                        display: inline-block;
                        background-color: #3498db;
                        color: white;
                        padding: 10px 20px;
                        text-decoration: none;
                        border-radius: 5px;
                        font-weight: bold;
                        margin: 20px 0;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <div class="logo">
                        <div class="logo-text">HYDROUS</div>
                    </div>
                    <h1>Propuesta de Tratamiento de Aguas Residuales</h1>
                    <p>Soluciones personalizadas para optimización y reutilización de agua</p>
                </div>
                
                <div class="container">
                    <div class="disclaimer">
                        <strong>📌 Aviso importante:</strong> Esta propuesta fue generada usando IA basada en la información
                        proporcionada por el usuario final y estándares de la industria. Si bien se ha hecho todo lo posible 
                        para garantizar la precisión, los datos, estimaciones de costos y recomendaciones técnicas pueden 
                        contener errores y no son legalmente vinculantes. Se recomienda que todos los detalles sean validados 
                        por Hydrous Management Group antes de la implementación.
                    </div>
                    
                    <h1>1. Introducción a Hydrous Management Group</h1>
                    <p>Hydrous Management Group se especializa en <strong>soluciones personalizadas de tratamiento de aguas residuales</strong> 
                    adaptadas para clientes industriales y comerciales. Nuestra <strong>experiencia en gestión del agua</strong> ayuda a las 
                    empresas a lograr <strong>cumplimiento normativo, reducción de costos y reutilización sostenible del agua</strong>.</p>
                    
                    <p>Utilizando tecnologías avanzadas de tratamiento y diseño potenciado por IA, Hydrous
                    ofrece soluciones de aguas residuales <strong>eficientes, escalables y rentables</strong> que optimizan 
                    el rendimiento operativo mientras minimizan el impacto ambiental.</p>
                    
                    <h1>2. Antecedentes del Proyecto</h1>
                    <p>Esta sección proporciona una visión general de las instalaciones del cliente, la industria
                    y las necesidades de tratamiento de aguas residuales.</p>
                    
                    <table>
                        <tr>
                            <th style="width: 40%;">Información del Cliente</th>
                            <th>Detalles</th>
                        </tr>
                        <tr>
                            <td><strong>Nombre del Cliente</strong></td>
                            <td>{client_info.get("name", "No especificado")}</td>
                        </tr>
                        <tr>
                            <td><strong>Ubicación</strong></td>
                            <td>{client_info.get("location", "No especificada")}</td>
                        </tr>
                        <tr>
                            <td><strong>Industria</strong></td>
                            <td>{client_info.get("sector", "Industrial")} - {client_info.get("subsector", "")}</td>
                        </tr>
                        <tr>
                            <td><strong>Fuente de Agua</strong></td>
                            <td>{proposal.get("project_details", {}).get("water_source", "Suministro Municipal/Pozo")}</td>
                        </tr>
                        <tr>
                            <td><strong>Consumo Actual de Agua</strong></td>
                            <td>{proposal.get("project_details", {}).get("water_consumption", "No especificado")}</td>
                        </tr>
                        <tr>
                            <td><strong>Generación Actual de Aguas Residuales</strong></td>
                            <td>{proposal.get("project_details", {}).get("wastewater_generation", "No especificado")}</td>
                        </tr>
                        <tr>
                            <td><strong>Sistema de Tratamiento Existente</strong></td>
                            <td>{client_info.get("sistema_existente", "No existe tratamiento")}</td>
                        </tr>
                    </table>
                    
                    <h1>3. Objetivo del Proyecto</h1>
                    <p>Definir claramente los <strong>objetivos primarios</strong> para el tratamiento de aguas residuales.</p>
                    
                    <div class="highlight">
            """

            # Añadir objetivos
            objectives = proposal.get("project_details", {}).get("objectives", [])
            if not objectives or not isinstance(objectives, list):
                objectives = [
                    "Cumplimiento Regulatorio",
                    "Optimización de Costos",
                    "Reutilización del Agua",
                    "Sostenibilidad",
                ]

            objectives_descriptions = {
                "Cumplimiento normativo": "Asegurar que el agua tratada cumpla con las regulaciones de descarga.",
                "Cumplimiento Regulatorio": "Asegurar que el agua tratada cumpla con las regulaciones de descarga.",
                "Reducción de la huella ambiental": "Mejorar el perfil ambiental mediante gestión eficiente del agua.",
                "Ahorro de costos": "Reducir gastos de agua y descarga mediante reutilización.",
                "Proyecto de retorno de inversión": "Garantizar recuperación de la inversión en un periodo razonable.",
                "Mayor disponibilidad de agua": "Asegurar suministro sostenible mediante recuperación y reúso.",
                "Sostenibilidad": "Mejorar la huella ambiental a través de la gestión eficiente del agua.",
                "Optimización de Costos": "Reducir gastos operativos relacionados con agua potable y descargas.",
            }

            for obj in objectives:
                description = objectives_descriptions.get(
                    obj, "Optimizar la gestión del agua para beneficios operativos."
                )
                html_content += f"                    <p><span class='checkmark'>✓</span> <strong>{obj}</strong> — {description}</p>\n"

            html_content += """
                    </div>
                    
                    <h1>4. Supuestos Clave de Diseño & Comparación</h1>
                    <p>Esta sección compara las <strong>características del agua residual sin tratar</strong> proporcionadas por
                    el cliente con <strong>valores estándar de la industria</strong>. También describe la calidad objetivo del efluente.</p>
                    
                    <table>
                        <tr>
                            <th>Parámetro</th>
                            <th>Agua Residual Sin Tratar</th>
                            <th>Estándar de la Industria</th>
                            <th>Objetivo del Efluente</th>
                        </tr>
            """

            # Añadir parámetros de agua según subsector
            subsector = client_info.get("subsector", "")
            water_params = proposal.get("water_parameters", {})

            if subsector == "Textil":
                params = [
                    (
                        "SST (mg/L)",
                        water_params.get("sst", "800"),
                        "500 - 1,000",
                        "≤50",
                    ),
                    (
                        "TDS (mg/L)",
                        water_params.get("sdt", "3,000"),
                        "1,500 - 5,000",
                        "Varía según reutilización",
                    ),
                    (
                        "DQO (mg/L)",
                        water_params.get("dqo", "1,100"),
                        "800 - 2,500",
                        "≤250",
                    ),
                    (
                        "DBO (mg/L)",
                        water_params.get("dbo", "700"),
                        "300 - 1,200",
                        "≤50",
                    ),
                    ("pH", water_params.get("ph", "4"), "4.5 - 6.5", "6.5 - 7.5"),
                ]
            elif subsector == "Alimentos y Bebidas":
                params = [
                    ("SST (mg/L)", water_params.get("sst", "600"), "400 - 800", "≤50"),
                    (
                        "TDS (mg/L)",
                        water_params.get("sdt", "2,000"),
                        "1,200 - 3,000",
                        "Varía según reutilización",
                    ),
                    (
                        "DQO (mg/L)",
                        water_params.get("dqo", "2,500"),
                        "1,500 - 5,000",
                        "≤250",
                    ),
                    (
                        "DBO (mg/L)",
                        water_params.get("dbo", "1,500"),
                        "900 - 3,000",
                        "≤50",
                    ),
                    (
                        "Grasas y Aceites (mg/L)",
                        water_params.get("grasas_aceites", "300"),
                        "200 - 600",
                        "≤15",
                    ),
                    ("pH", water_params.get("ph", "5.5"), "4.0 - 7.0", "6.5 - 7.5"),
                ]
            else:
                params = [
                    (
                        "SST (mg/L)",
                        water_params.get("sst", "Variable*"),
                        "Según subsector",
                        "≤50",
                    ),
                    (
                        "TDS (mg/L)",
                        water_params.get("sdt", "Variable*"),
                        "Según subsector",
                        "Varía según reutilización",
                    ),
                    (
                        "DQO (mg/L)",
                        water_params.get("dqo", "Variable*"),
                        "Según subsector",
                        "≤250",
                    ),
                    (
                        "DBO (mg/L)",
                        water_params.get("dbo", "Variable*"),
                        "Según subsector",
                        "≤50",
                    ),
                    (
                        "pH",
                        water_params.get("ph", "Variable*"),
                        "6.0 - 9.0",
                        "6.5 - 7.5",
                    ),
                ]

            # Agregar filas a la tabla
            for param, actual, industry, target in params:
                html_content += f"""
                        <tr>
                            <td><strong>{param}</strong></td>
                            <td>{actual}</td>
                            <td>{industry}</td>
                            <td>{target}</td>
                        </tr>"""

            html_content += """
                    </table>
                    
                    <h1>5. Diseño de Procesos & Alternativas de Tratamiento</h1>
                    <p>Esta sección describe las <strong>tecnologías de tratamiento recomendadas</strong> y
                    posibles <strong>alternativas</strong> para cumplir con los objetivos de tratamiento.</p>
                    
                    <table>
                        <tr>
                            <th>Etapa de Tratamiento</th>
                            <th>Tecnología Recomendada</th>
                            <th>Opción Alternativa</th>
                        </tr>
            """

            # Generar etapas de tratamiento según subsector
            if subsector == "Textil":
                treatments = [
                    (
                        "<strong>Pretratamiento</strong>",
                        "<strong>Flotación por Aire Disuelto (DAF)</strong> — Elimina grasas, aceites y sólidos suspendidos.",
                        "<strong>Coagulación & Sedimentación</strong> — Menos efectiva pero de menor costo.",
                    ),
                    (
                        "<strong>Ajuste de pH</strong>",
                        "<strong>Dosificación Química</strong> — Estabiliza niveles de pH.",
                        "<strong>Neutralización Basada en Aireación</strong> — Proceso más lento pero libre de químicos.",
                    ),
                    (
                        "<strong>Tratamiento Secundario</strong>",
                        "<strong>Reactor de Biopelícula de Lecho Móvil (MBBR)</strong> — Reducción eficiente de DQO/DBO.",
                        "<strong>Proceso de Lodos Activados (ASP)</strong> — Requiere más espacio y energía.",
                    ),
                    (
                        "<strong>Tratamiento Terciario</strong>",
                        "<strong>Filtración de Arena & Carbón</strong> — Elimina orgánicos residuales y sólidos.",
                        "<strong>Biorreactor de Membrana (MBR)</strong> — Efluente de alta calidad, mayor costo.",
                    ),
                    (
                        "<strong>Desinfección</strong>",
                        "<strong>Desinfección UV / Cloración</strong> — Elimina patógenos.",
                        "<strong>Ozonización</strong> — Más efectiva pero intensiva en energía.",
                    ),
                ]
            elif subsector == "Alimentos y Bebidas":
                treatments = [
                    (
                        "<strong>Pretratamiento</strong>",
                        "<strong>Trampa de Grasas y Cribado</strong> — Elimina grasas y sólidos gruesos.",
                        "<strong>Flotación por Aire Disuelto (DAF)</strong> — Mayor eficiencia, mayor costo.",
                    ),
                    (
                        "<strong>Ajuste de pH</strong>",
                        "<strong>Dosificación Química</strong> — Estabiliza niveles de pH.",
                        "<strong>Neutralización Biológica</strong> — Sostenible para fluctuaciones pequeñas.",
                    ),
                    (
                        "<strong>Tratamiento Secundario</strong>",
                        "<strong>Sistema Anaerobio-Aerobio Combinado</strong> — Eficiente para alta carga orgánica.",
                        "<strong>Lodos Activados Convencionales</strong> — Tecnología probada, mayor huella.",
                    ),
                    (
                        "<strong>Tratamiento Terciario</strong>",
                        "<strong>Filtración Multimedia</strong> — Elimina sólidos residuales.",
                        "<strong>Ultrafiltración (UF)</strong> — Mayor calidad de efluente.",
                    ),
                    (
                        "<strong>Desinfección</strong>",
                        "<strong>Desinfección UV</strong> — Sin químicos residuales.",
                        "<strong>Cloración</strong> — Económica pero con subproductos.",
                    ),
                ]
            else:
                treatments = [
                    (
                        "<strong>Pretratamiento</strong>",
                        "<strong>Sistema de Cribado y Homogeneización</strong> — Prepara el agua para tratamiento.",
                        "<strong>Opción personalizada según características específicas.</strong>",
                    ),
                    (
                        "<strong>Tratamiento Primario</strong>",
                        "<strong>Proceso Físico-Químico</strong> — Remueve sólidos y contaminantes específicos.",
                        "<strong>Tecnología adaptada a contaminantes del sector.</strong>",
                    ),
                    (
                        "<strong>Tratamiento Secundario</strong>",
                        "<strong>Sistema Biológico Optimizado</strong> — Reduce carga orgánica.",
                        "<strong>Selección basada en biodegradabilidad de contaminantes.</strong>",
                    ),
                    (
                        "<strong>Tratamiento Terciario</strong>",
                        "<strong>Filtración Avanzada</strong> — Asegura calidad final.",
                        "<strong>Sistema específico según requisitos de reúso/descarga.</strong>",
                    ),
                    (
                        "<strong>Desinfección</strong>",
                        "<strong>Sistema UV/Químico</strong> — Elimina patógenos residuales.",
                        "<strong>Tecnología seleccionada según aplicación final del agua.</strong>",
                    ),
                ]

            # Agregar filas de tratamiento
            for stage, recommended, alternative in treatments:
                html_content += f"""
                        <tr>
                            <td>{stage}</td>
                            <td>{recommended}</td>
                            <td>{alternative}</td>
                        </tr>"""

            # Extraer valor de flujo para dimensionamiento
            flow_value = 100  # m³/día (valor por defecto)
            water_consumption = proposal.get("project_details", {}).get(
                "water_consumption", "100 m³/día"
            )
            if isinstance(water_consumption, str):
                # Tratar de extraer un valor numérico del consumo de agua
                import re

                match = re.search(r"(\d+(?:\.\d+)?)", water_consumption)
                if match:
                    try:
                        flow_value = float(match.group(1))
                    except:
                        pass

            html_content += """
                    </table>
                    
                    <h1>6. Equipo Sugerido & Dimensionamiento</h1>
                    <p>Esta sección lista <strong>equipos recomendados, capacidades, dimensiones y
                    posibles proveedores/modelos</strong> cuando estén disponibles.</p>
                    
                    <table>
                        <tr>
                            <th>Equipo</th>
                            <th>Capacidad</th>
                            <th>Dimensiones</th>
                            <th>Marca/Modelo</th>
                        </tr>
            """

            # Añadir equipos según subsector
            if subsector == "Textil":
                equipment = [
                    (
                        f"<strong>Sistema DAF</strong>",
                        f"{flow_value/24:.1f} m³/h",
                        f"{flow_value*0.1:.1f} m² x 2.5 m altura",
                        "Marca A / Estándar Industrial",
                    ),
                    (
                        f"<strong>Sistema de Ajuste de pH</strong>",
                        f"{flow_value/24:.1f} m³/h",
                        "Unidad Compacta",
                        "Estándar Industrial",
                    ),
                    (
                        f"<strong>Sistema MBBR</strong>",
                        f"{flow_value/24:.1f} m³/h",
                        f"Tanque de {flow_value*0.3:.1f} m³",
                        "Marca B / Equivalente",
                    ),
                    (
                        f"<strong>Filtros de Arena & Carbón</strong>",
                        f"{flow_value/24:.1f} m³/h",
                        f"Área de Filtración: {flow_value*0.01:.1f} m²",
                        "Marca C / Equivalente",
                    ),
                    (
                        f"<strong>Sistema UV</strong>",
                        f"{flow_value/24:.1f} m³/h",
                        "Unidad Compacta",
                        "Marca D / Equivalente",
                    ),
                    (
                        f"<strong>Tanque de Agua Tratada</strong>",
                        f"{flow_value*0.5:.1f} m³",
                        f"{flow_value*0.12:.1f} m² x 3 m altura",
                        "Estándar Industrial",
                    ),
                ]
            elif subsector == "Alimentos y Bebidas":
                equipment = [
                    (
                        f"<strong>Trampa de Grasas/Aceites</strong>",
                        f"{flow_value/24:.1f} m³/h",
                        f"{flow_value*0.08:.1f} m³",
                        "Estándar Industrial",
                    ),
                    (
                        f"<strong>Tanque de Ecualización</strong>",
                        f"{flow_value*0.4:.1f} m³",
                        f"{flow_value*0.1:.1f} m² x 3 m altura",
                        "Fabricación a Medida",
                    ),
                    (
                        f"<strong>Reactor Anaerobio</strong>",
                        f"{flow_value/24:.1f} m³/h",
                        f"Volumen: {flow_value*0.25:.1f} m³",
                        "Marca B / Equivalente",
                    ),
                    (
                        f"<strong>Sistema Aerobio</strong>",
                        f"{flow_value/24:.1f} m³/h",
                        f"Volumen: {flow_value*0.2:.1f} m³",
                        "Marca C / Equivalente",
                    ),
                    (
                        f"<strong>Sistema de Filtración</strong>",
                        f"{flow_value/24:.1f} m³/h",
                        f"Área: {flow_value*0.01:.1f} m²",
                        "Marca D / Equivalente",
                    ),
                    (
                        f"<strong>Deshidratador de Lodos</strong>",
                        f"{flow_value*0.01:.1f} m³/día de lodos",
                        "Unidad Compacta",
                        "Marca E / Equivalente",
                    ),
                ]
            else:
                equipment = [
                    (
                        f"<strong>Sistema de Pretratamiento</strong>",
                        f"{flow_value/24:.1f} m³/h",
                        "Según requerimientos específicos",
                        "Selección según contaminantes",
                    ),
                    (
                        f"<strong>Sistema Primario</strong>",
                        f"{flow_value/24:.1f} m³/h",
                        f"Área estimada: {flow_value*0.1:.1f} m²",
                        "Diseño a medida",
                    ),
                    (
                        f"<strong>Sistema Secundario</strong>",
                        f"{flow_value/24:.1f} m³/h",
                        f"Volumen: {flow_value*0.3:.1f} m³",
                        "Tecnología seleccionada según caracterización",
                    ),
                    (
                        f"<strong>Sistema Terciario</strong>",
                        f"{flow_value/24:.1f} m³/h",
                        f"Dimensiones según tecnología seleccionada",
                        "Según requerimientos de reúso",
                    ),
                    (
                        f"<strong>Tanque de Almacenamiento</strong>",
                        f"{flow_value*0.5:.1f} m³",
                        f"Dimensiones: {flow_value*0.12:.1f} m² x 3 m altura",
                        "Estándar Industrial",
                    ),
                ]

            # Agregar filas de equipos
            for equip, capacity, dimensions, brand in equipment:
                html_content += f"""
                        <tr>
                            <td>{equip}</td>
                            <td>{capacity}</td>
                            <td>{dimensions}</td>
                            <td>{brand}</td>
                        </tr>"""

            # Calcular económicos
            base_capex = flow_value * 1500  # $1500 USD por m³/día como referencia
            complexity_factor = 1.2  # Factor moderado por defecto
            total_capex = base_capex * complexity_factor
            equipment_cost = total_capex * 0.6
            installation_cost = total_capex * 0.25
            engineering_cost = total_capex * 0.1
            contingency_cost = total_capex * 0.05

            html_content += """
                    </table>
                    
                    <h1>7. Estimación de CAPEX & OPEX</h1>
                    <p>Esta sección detalla tanto los <strong>gastos de capital (CAPEX)</strong> como los
                    <strong>gastos operativos (OPEX)</strong>.</p>
                    
                    <h2>Desglose de CAPEX</h2>
                    
                    <table>
                        <tr>
                            <th>Categoría</th>
                            <th>Costo Estimado (USD)</th>
                            <th>Notas</th>
                        </tr>
            """

            # Agregar filas de CAPEX
            html_content += f"""
                        <tr>
                            <td><strong>Equipos de Tratamiento</strong></td>
                            <td>${equipment_cost:,.2f}</td>
                            <td>Basado en instalaciones similares</td>
                        </tr>
                        <tr>
                            <td><strong>Instalación y Montaje</strong></td>
                            <td>${installation_cost:,.2f}</td>
                            <td>Diseño escalable</td>
                        </tr>
                        <tr>
                            <td><strong>Ingeniería y Gestión</strong></td>
                            <td>${engineering_cost:,.2f}</td>
                            <td>Incluye puesta en marcha</td>
                        </tr>
                        <tr>
                            <td><strong>Contingencia</strong></td>
                            <td>${contingency_cost:,.2f}</td>
                            <td>Reserva para imprevistos</td>
                        </tr>
                        <tr class="total-row">
                            <td><strong>CAPEX Total</strong></td>
                            <td><strong>${total_capex:,.2f}</strong></td>
                            <td><strong>Inversión total estimada</strong></td>
                        </tr>
            """

            # Calcular OPEX
            energy_cost = flow_value * 3  # $3 por m³/día
            chemical_cost = flow_value * 2  # $2 por m³/día
            labor_cost = 1500 if flow_value < 200 else 3000  # Personal requerido
            maintenance_cost = (
                total_capex * 0.01 / 12
            )  # 1% del CAPEX anual, mensualizado
            sludge_cost = flow_value * 1  # $1 por m³/día

            total_opex_monthly = (
                energy_cost
                + chemical_cost
                + labor_cost
                + maintenance_cost
                + sludge_cost
            )

            html_content += """
                    </table>
                    
                    <h2>Desglose de OPEX</h2>
                    
                    <table>
                        <tr>
                            <th>Gasto Operativo</th>
                            <th>Costo Mensual Estimado (USD)</th>
                            <th>Notas</th>
                        </tr>
            """

            # Agregar filas de OPEX
            html_content += f"""
                        <tr>
                            <td><strong>Costos de Químicos</strong></td>
                            <td>${chemical_cost:,.2f}</td>
                            <td>Químicos para ajuste de pH y coagulación</td>
                        </tr>
                        <tr>
                            <td><strong>Costos de Energía</strong></td>
                            <td>${energy_cost:,.2f}</td>
                            <td>Consumo eléctrico para aireación, bombas</td>
                        </tr>
                        <tr>
                            <td><strong>Costos de Mano de Obra</strong></td>
                            <td>${labor_cost:,.2f}</td>
                            <td>Operador y personal de mantenimiento</td>
                        </tr>
                        <tr>
                            <td><strong>Disposición de Lodos</strong></td>
                            <td>${sludge_cost:,.2f}</td>
                            <td>Remoción y tratamiento de lodos residuales</td>
                        </tr>
                        <tr>
                            <td><strong>Mantenimiento</strong></td>
                            <td>${maintenance_cost:,.2f}</td>
                            <td>Repuestos y servicios preventivos</td>
                        </tr>
                        <tr class="total-row">
                            <td><strong>OPEX Total</strong></td>
                            <td><strong>${total_opex_monthly:,.2f}/mes</strong></td>
                            <td><strong>Costo operativo mensual</strong></td>
                        </tr>
            """

            # Calcular ahorros y ROI
            water_cost = 2.0  # Por defecto USD/m³
            water_cost_text = client_info.get("costo_agua", "2.0 USD/m³")
            if isinstance(water_cost_text, str):
                import re

                cost_match = re.search(r"(\d+(?:\.\d+)?)", water_cost_text)
                if cost_match:
                    try:
                        water_cost = float(cost_match.group(1))
                    except:
                        pass

            discharge_cost = water_cost * 0.5  # Estimación de costo de descarga
            water_savings_ratio = 0.6  # 60% reducción de consumo
            discharge_savings_ratio = 0.4  # 40% reducción de descarga

            monthly_water_volume = flow_value * 30  # Volumen mensual en m³
            monthly_water_savings = (
                monthly_water_volume * water_savings_ratio * water_cost
            )
            monthly_discharge_savings = (
                monthly_water_volume * discharge_savings_ratio * discharge_cost
            )

            annual_water_savings = monthly_water_savings * 12
            annual_discharge_savings = monthly_discharge_savings * 12
            total_annual_savings = annual_water_savings + annual_discharge_savings

            # Calcular ROI simple
            roi_years = (
                total_capex / total_annual_savings if total_annual_savings > 0 else 10
            )
            roi_years = max(1.0, min(10.0, roi_years))  # Limitar entre 1 y 10 años

            html_content += """
                    </table>
                    
                    <h1>8. Análisis del Retorno de la Inversión (ROI)</h1>
                    <p>Ahorros de costos proyectados basados en <strong>reducción de compras de agua y menores
                    tarifas de descarga</strong>.</p>
                    
                    <table>
                        <tr>
                            <th>Parámetro</th>
                            <th>Costo Actual</th>
                            <th>Costo Proyectado Después del Tratamiento</th>
                            <th>Ahorro Anual (USD)</th>
                        </tr>
            """

            # Agregar filas de ahorros
            html_content += f"""
                        <tr>
                            <td><strong>Costo de Compra de Agua</strong></td>
                            <td>{water_cost:.2f} USD/m³</td>
                            <td>{water_cost * (1-water_savings_ratio):.2f} USD/m³ (con reúso)</td>
                            <td>${annual_water_savings:,.2f}</td>
                        </tr>
                        <tr>
                            <td><strong>Tarifas de Descarga</strong></td>
                            <td>${monthly_water_volume * discharge_cost:,.2f}/mes</td>
                            <td>${monthly_water_volume * discharge_cost * (1-discharge_savings_ratio):,.2f}/mes (carga reducida)</td>
                            <td>${annual_discharge_savings:,.2f}</td>
                        </tr>
                        <tr class="total-row">
                            <td><strong>Total Ahorros Anuales</strong></td>
                            <td></td>
                            <td></td>
                            <td><strong>${total_annual_savings:,.2f}</strong></td>
                        </tr>
                    </table>
                    
                    <div class="highlight">
                        <h2>Retorno de la Inversión</h2>
                        <p><strong>Periodo de recuperación simple:</strong> {roi_years:.1f} años</p>
                        <p><strong>ROI a 5 años:</strong> {(total_annual_savings * 5 - total_capex) / total_capex * 100:.1f}%</p>
                        <p><strong>Ahorros acumulados a 10 años:</strong> ${total_annual_savings * 10:,.2f}</p>
                    </div>
                    
                    <h1>9. Anexo de Preguntas y Respuestas</h1>
                    <h2>Preguntas Frecuentes</h2>
                    
                    <div class="section">
                        <p><strong>P: ¿Cuánto espacio se requiere para la instalación?</strong><br>
                        R: El sistema completo requiere aproximadamente {flow_value * 1.5:.0f}-{flow_value * 2:.0f} m² para una instalación típica de este tamaño, pero puede optimizarse según restricciones específicas del sitio.</p>
                        
                        <p><strong>P: ¿Cuál es el tiempo estimado de implementación?</strong><br>
                        R: El proyecto completo, desde aprobación hasta puesta en marcha, tiene un cronograma típico de 4-6 meses.</p>
                        
                        <p><strong>P: ¿Qué mantenimiento requiere el sistema?</strong><br>
                        R: El sistema requiere mantenimiento preventivo regular (diario, semanal y mensual) y revisiones mayores semestrales. Se proporcionará un manual detallado y capacitación al personal.</p>
                        
                        <p><strong>P: ¿Requiere personal especializado?</strong><br>
                        R: Se recomienda contar con un operador capacitado. Hydrous ofrece programas de capacitación completos para su personal.</p>
                    </div>
                    
                    <div class="disclaimer">
                        <p>Esta propuesta se basa en la información proporcionada y estándares de la industria. Los costos y especificaciones finales pueden variar tras un estudio detallado del sitio y análisis específicos del agua residual. Hydrous Management Group recomienda realizar pruebas piloto para validar el diseño final.</p>
                    </div>
                    
                    <p style="text-align: center; margin-top: 30px;">
                        <strong>Para consultas o validación de esta propuesta, contacte a Hydrous Management Group en:</strong><br>
                        info@hydrous.com | +1 (555) 123-4567
                    </p>
                </div>
                
                <div class="footer">
                    <p>Hydrous Management Group © {datetime.datetime.now().year}</p>
                    <p>Generado el {datetime.datetime.now().strftime('%d/%m/%Y')}</p>
                </div>
            </body>
            </html>
            """

            # Asegurar que el directorio existe
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

            # Guardar el HTML
            html_path = os.path.join(
                settings.UPLOAD_DIR, f"{client_name}_propuesta_{timestamp}.html"
            )
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            logger.info(f"HTML de propuesta generado: {html_path}")

            # Intentar generar PDF con pdfkit o weasyprint
            pdf_path = os.path.join(
                settings.UPLOAD_DIR, f"{client_name}_propuesta_{timestamp}.pdf"
            )

            # Primero intentar con pdfkit
            if "pdfkit" in PDF_GENERATORS:
                try:
                    options = {
                        "page-size": "A4",
                        "margin-top": "20mm",
                        "margin-right": "20mm",
                        "margin-bottom": "20mm",
                        "margin-left": "20mm",
                        "encoding": "UTF-8",
                        "no-outline": None,
                        "enable-local-file-access": None,
                    }

                    # Buscar wkhtmltopdf en Windows
                    path_wkhtmltopdf = None
                    if os.name == "nt":  # Windows
                        for possible_path in [
                            r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
                            r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
                        ]:
                            if os.path.exists(possible_path):
                                path_wkhtmltopdf = possible_path
                                break

                    if path_wkhtmltopdf:
                        config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
                        pdfkit.from_string(
                            html_content,
                            pdf_path,
                            options=options,
                            configuration=config,
                        )
                    else:
                        pdfkit.from_string(html_content, pdf_path, options=options)

                    logger.info(f"PDF generado correctamente con pdfkit: {pdf_path}")
                    return pdf_path
                except Exception as e:
                    logger.warning(f"Error al generar PDF con pdfkit: {str(e)}")

            # Si pdfkit falla, intentar con weasyprint
            if "weasyprint" in PDF_GENERATORS:
                try:
                    from weasyprint import HTML

                    HTML(string=html_content).write_pdf(pdf_path)
                    logger.info(
                        f"PDF generado correctamente con WeasyPrint: {pdf_path}"
                    )
                    return pdf_path
                except Exception as e:
                    logger.warning(f"Error al generar PDF con WeasyPrint: {str(e)}")

            # Si no se pudo generar PDF, devolver el HTML
            logger.warning(f"No se pudo generar PDF. Devolviendo HTML: {html_path}")
            return html_path

        except Exception as e:
            logger.error(f"Error al generar propuesta: {str(e)}")
            # Crear un HTML de error como fallback
            error_html_path = os.path.join(
                settings.UPLOAD_DIR,
                f"error_propuesta_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
            )

            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Error en Generación de Propuesta</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
                    h1 {{ color: #d9534f; }}
                    .error-code {{ background: #f8d7da; padding: 15px; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <h1>Ha ocurrido un error al generar la propuesta</h1>
                <p>No se ha podido generar la propuesta debido a un error técnico. Por favor, intente nuevamente o contacte con soporte técnico.</p>
                <div class="error-code">
                    <p><strong>Código de error:</strong> {datetime.datetime.now().strftime('%Y%m%d%H%M%S')}</p>
                    <p><strong>Detalle:</strong> {str(e)}</p>
                </div>
            </body>
            </html>
            """

            with open(error_html_path, "w", encoding="utf-8") as f:
                f.write(error_html)

            return error_html_path


# Instancia global del servicio
questionnaire_service = QuestionnaireService()
