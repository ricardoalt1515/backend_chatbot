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

        # Confirmación y siguiente pregunta
        summary += """
    ¿Es correcta esta información? Si necesita realizar alguna corrección, por favor indíquelo. 
    De lo contrario, continuaremos con las siguientes preguntas para completar su perfil de necesidades.
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
        """Formatea la propuesta final siguiendo exactamente la estructura especificada"""
        client_info = proposal.get("client_info", {})
        sector = client_info.get("sector", "")
        subsector = client_info.get("subsector", "")
        name = client_info.get("name", "Cliente")

        # 1. Introducción a Hydrous Management Group
        summary = f"""
    # PROPUESTA DE SOLUCIÓN DE TRATAMIENTO DE AGUAS RESIDUALES PARA {name.upper()}

    ## 1. Introducción al Grupo de Gestión Hidráulica

    Hydrous Management Group es una empresa líder especializada en soluciones personalizadas de tratamiento de aguas residuales para clientes industriales y comerciales. Con más de 15 años de experiencia en el sector, hemos desarrollado sistemas eficientes y económicamente viables para una amplia gama de industrias.

    Nuestra misión es **optimizar el uso del agua** a través de tecnologías innovadoras y sostenibles, ayudando a nuestros clientes a:
    - Cumplir con la normativa ambiental vigente
    - Reducir costos operativos asociados al consumo de agua
    - Mejorar su perfil de sostenibilidad y responsabilidad ambiental
    - Explorar nuevas oportunidades de negocio a través del reúso del agua

    ## 2. Antecedentes del Proyecto

    **Cliente**: {name}  
    **Sector**: {sector} - {subsector}  
    **Ubicación**: {client_info.get('location', 'No especificada')}

    **Situación actual**:
    - Consumo actual de agua: {proposal.get('water_consumption', 'No especificado')}
    - Generación de aguas residuales: {proposal.get('wastewater_generation', 'No especificado')}
    - Costo actual del agua: {client_info.get('costo_agua', 'No especificado')}
    """

        # Añadir sistema existente si existe
        if (
            "sistema_existente" in client_info
            and client_info["sistema_existente"] == "Sí"
        ):
            summary += f"- Sistema de tratamiento existente: {client_info.get('descripcion_sistema', 'Sistema básico')}\n"
        else:
            summary += "- No cuenta con sistema de tratamiento de aguas residuales actualmente\n"

        # 3. Objetivo del Proyecto
        summary += """
    ## 3. Objetivo del Proyecto

    El objetivo principal de este proyecto es diseñar e implementar un sistema de tratamiento de aguas residuales que permita:
    """

        # Objetivos específicos según la información
        objectives = []

        if "objetivo_principal" in client_info:
            objetivo = client_info["objetivo_principal"]
            if "normativo" in objetivo.lower():
                objectives.append(
                    "- **Garantizar el cumplimiento normativo** de los parámetros de descarga establecidos por la legislación local"
                )
            elif "costo" in objetivo.lower() or "ahorro" in objetivo.lower():
                objectives.append(
                    "- **Optimizar costos operativos** a través de la reducción del consumo de agua fresca y las tarifas de descarga"
                )
            elif "ambiente" in objetivo.lower() or "ambiental" in objetivo.lower():
                objectives.append(
                    "- **Mejorar el perfil ambiental** de la instalación y reducir su huella hídrica"
                )
        else:
            objectives.append(
                "- **Optimizar la gestión del agua** en la instalación para lograr beneficios económicos y ambientales"
            )

        # Objetivos de reúso
        if "objetivo_reuso" in client_info:
            objetivo_reuso = client_info["objetivo_reuso"]
            if isinstance(objetivo_reuso, list):
                for reuso in objetivo_reuso:
                    if "sanitarios" in reuso.lower():
                        objectives.append(
                            "- **Reutilizar el agua tratada en instalaciones sanitarias**, reduciendo el consumo de agua potable"
                        )
                    elif "riego" in reuso.lower():
                        objectives.append(
                            "- **Aprovechar el agua tratada para riego de áreas verdes**, mejorando la sostenibilidad del sitio"
                        )
                    elif "industrial" in reuso.lower():
                        objectives.append(
                            "- **Reincorporar el agua tratada en procesos industriales**, creando un ciclo más cerrado"
                        )
            else:
                if "sanitarios" in objetivo_reuso.lower():
                    objectives.append(
                        "- **Reutilizar el agua tratada en instalaciones sanitarias**, reduciendo el consumo de agua potable"
                    )
                elif "riego" in objetivo_reuso.lower():
                    objectives.append(
                        "- **Aprovechar el agua tratada para riego de áreas verdes**, mejorando la sostenibilidad del sitio"
                    )
                elif "industrial" in objetivo_reuso.lower():
                    objectives.append(
                        "- **Reincorporar el agua tratada en procesos industriales**, creando un ciclo más cerrado"
                    )

        # Añadir ROI si hay información de costos
        if "costo_agua" in client_info:
            objectives.append(
                f"- **Lograr un retorno de inversión atractivo** dentro de un periodo estimado de {self._calculate_roi_years(proposal)} años"
            )

        # Añadir objetivos generales si no hay específicos
        if not objectives:
            objectives = [
                "- **Cumplir con la normativa ambiental** aplicable para descarga de aguas residuales",
                "- **Reducir el consumo de agua fresca** mediante la implementación de sistemas de reúso",
                "- **Optimizar costos operativos** relacionados con el manejo del agua",
                "- **Mejorar la sostenibilidad** de las operaciones a través de una gestión más eficiente del agua",
            ]

        summary += "\n".join(objectives) + "\n"

        # 4. Supuestos Clave de Diseño
        summary += """
    ## 4. Supuestos Clave de Diseño y Comparación con Estándares de la Industria

    ### Parámetros de Diseño
    """

        # Crear tabla de parámetros
        summary += """
|   Parámetro | Valor Actual | Estándar de la Industria | Objetivo de Tratamiento |
|   -----------|--------------|--------------------------|-------------------------|
    """

        # Añadir parámetros específicos según subsector
        water_params = proposal.get("water_parameters", {})

        if subsector == "Textil":
            params_list = [
                (
                    "DQO (mg/L)",
                    water_params.get("dqo", "800-1,500*"),
                    "800-2,500",
                    "<150",
                ),
                ("SST (mg/L)", water_params.get("sst", "350-600*"), "300-800", "<50"),
                (
                    "Color",
                    water_params.get("color", "Intenso*"),
                    "Variable según colorantes",
                    "No aparente",
                ),
                ("pH", water_params.get("ph", "6.0-9.0*"), "5.5-10.0", "6.5-8.5"),
            ]
        elif subsector == "Alimentos y Bebidas":
            params_list = [
                (
                    "DQO (mg/L)",
                    water_params.get("dqo", "1,200-3,000*"),
                    "800-5,000",
                    "<150",
                ),
                (
                    "DBO (mg/L)",
                    water_params.get("dbo", "700-1,800*"),
                    "500-2,500",
                    "<30",
                ),
                ("SST (mg/L)", water_params.get("sst", "400-800*"), "250-1,000", "<50"),
                (
                    "Grasas y Aceites (mg/L)",
                    water_params.get("grasas_aceites", "50-250*"),
                    "50-500",
                    "<15",
                ),
                ("pH", water_params.get("ph", "4.5-8.0*"), "4.0-11.0", "6.5-8.5"),
            ]
        else:
            params_list = [
                (
                    "DQO (mg/L)",
                    water_params.get("dqo", "Variable*"),
                    "Según subsector",
                    "<150",
                ),
                (
                    "SST (mg/L)",
                    water_params.get("sst", "Variable*"),
                    "Según subsector",
                    "<50",
                ),
                ("pH", water_params.get("ph", "Variable*"), "6.0-9.0", "6.5-8.5"),
            ]

        for param, actual, industry, target in params_list:
            summary += f"| {param} | {actual} | {industry} | {target} |\n"

        # Añadir nota sobre valores estimados
        if not water_params:
            summary += "\n*Valores estimados basados en estándares de la industria. Se recomienda realizar análisis específicos.\n"

        # 5. Diseño de Procesos y Alternativas
        summary += """
    ## 5. Diseño de Procesos y Alternativas de Tratamiento

    ### Diagrama de Proceso Recomendado
Agua Residual → [PRETRATAMIENTO] → [TRATAMIENTO PRIMARIO] → [TRATAMIENTO SECUNDARIO] → [TRATAMIENTO TERCIARIO] → Agua Tratada
↓                      ↓                       ↓                        ↓
Cribado              Coagulación             Tratamiento              Filtración
Homogeneización         Floculación              Biológico             Desinfección

### Detalle de Etapas de Tratamiento
"""

        # Detallar etapas según subsector
        if subsector == "Textil":
            summary += """
#### Pretratamiento
- **Sistema de cribado automático**: Elimina sólidos gruesos y protege equipos posteriores.
- **Tanque de homogeneización**: Capacidad para 8-12 horas de retención, con sistema de agitación y control de pH.
- **Justificación**: Neutraliza las variaciones de pH típicas del sector textil y estabiliza el flujo para procesos posteriores.

#### Tratamiento Primario
- **Sistema DAF (Flotación por Aire Disuelto)**: Remoción de sólidos suspendidos y parte del color mediante microburbujas y coagulantes.
- **Dosificación química optimizada**: Incluye coagulantes y floculantes específicos para la industria textil.
- **Justificación**: Elimina hasta el 80% de los sólidos suspendidos y 30-40% del color, preparando el agua para el tratamiento biológico.

#### Tratamiento Secundario
- **Reactor Biológico de Membrana (MBR)**: Combina degradación biológica y filtración por membrana en un solo paso.
- **Alternativa**: Reactor de Biopelícula de Lecho Móvil (MBBR) si se prefiere menor complejidad operativa.
- **Justificación**: Degrada eficientemente la materia orgánica (>95% DBO) y proporciona excelente calidad de efluente sin clarificador secundario.

#### Tratamiento Terciario
- **Sistema de Oxidación Avanzada**: Elimina color residual y compuestos recalcitrantes mediante ozono o UV/peróxido.
- **Filtración por Carbón Activado**: Adsorción de compuestos orgánicos residuales y mejora de calidad final.
- **Justificación**: Necesario para remoción efectiva de colorantes y compuestos difíciles de biodegradar, permitiendo el reúso del agua.
"""
        elif subsector == "Alimentos y Bebidas":
            summary += """
#### Pretratamiento
- **Sistema de cribado fino**: Elimina sólidos y residuos de alimentos.
- **Trampa de grasas y aceites**: Remoción de grasas mediante flotación natural.
- **Tanque de ecualización**: Capacidad para 8-12 horas, con sistema de mezcla para prevenir sedimentación.
- **Justificación**: Crucial para manejar las altas cargas de grasas y sólidos característicos del sector alimentario.

#### Tratamiento Primario
- **Flotación por Aire Disuelto (DAF)**: Remoción eficiente de grasas residuales y sólidos suspendidos.
- **Alternativa**: Sedimentación primaria con remoción de lodos.
- **Justificación**: Elimina hasta el 90% de grasas y aceites, preparando el agua para tratamiento biológico.

#### Tratamiento Secundario
- **Sistema Anaerobio-Aerobio**: Reactor UASB seguido de lodos activados para alta eficiencia.
- **Alternativa**: Lodos activados de aireación extendida para instalaciones más pequeñas.
- **Justificación**: El tratamiento anaerobio inicial reduce significativamente la carga orgánica y genera biogás aprovechable.

#### Tratamiento Terciario
- **Filtración multimedia**: Remoción de sólidos residuales.
- **Desinfección UV**: Eliminación de patógenos sin subproductos químicos.
- **Justificación**: Asegura cumplimiento normativo y permite reúso seguro en diversas aplicaciones.
"""
        else:
            summary += """
#### Pretratamiento
- **Sistema de cribado**: Diseñado según las características específicas del agua residual.
- **Tanque de homogeneización**: Con capacidad adecuada para estabilizar flujos y cargas.
- **Justificación**: Fundamental para asegurar condiciones estables en procesos posteriores.

#### Tratamiento Primario
- **Sistema físico-químico**: Adaptado a contaminantes específicos de su sector.
- **Justificación**: Elimina contaminantes particulados y prepara el agua para tratamiento biológico.

#### Tratamiento Secundario
- **Sistema biológico optimizado**: Seleccionado según carga orgánica y características específicas.
- **Justificación**: Degrada eficientemente la materia orgánica biodegradable.

#### Tratamiento Terciario
- **Filtración avanzada**: Asegura remoción de sólidos residuales.
- **Tratamiento específico adicional**: Según requerimientos particulares de reúso o descarga.
- **Justificación**: Garantiza la calidad final requerida para su aplicación específica.
"""

        # 6. Equipo y tamaño sugeridos
        summary += """
## 6. Equipo y Tamaño Sugeridos

El dimensionamiento preliminar de los equipos se ha realizado considerando los flujos reportados y las características del agua residual.

### Dimensiones Aproximadas de Equipos Principales
"""

        # Calcular dimensiones según flujo
        flow_value = 100  # valor por defecto en m³/día
        flow_text = proposal.get("water_consumption", "100 m³/día")

        if isinstance(flow_text, str):
            import re

            match = re.search(r"(\d+(?:\.\d+)?)", flow_text)
            if match:
                flow_value = float(match.group(1))

        # Tabla de equipos
        summary += """
    | Equipo | Capacidad/Dimensión | Características Principales | Cantidad |
    |--------|---------------------|----------------------------|----------|
    """

        # Equipos según subsector
        if subsector == "Textil":
            summary += f"""| Tanque de homogeneización | {round(flow_value * 0.4, 1)} m³ | Tiempo retención 8-10h, agitación, ajuste pH | 1 |
| Sistema DAF | {round(flow_value / 20, 1)} m³/h | Incluye sistema dosificación química | 1 |
| Reactor MBR | {round(flow_value * 0.25, 1)} m³ | Membranas sumergidas, sopladores | 1 |
| Sistema oxidación avanzada | {round(flow_value / 24, 1)} m³/h | UV/Ozono combinado | 1 |
| Filtros carbón activado | {round(flow_value * 0.02, 1)} m² | Múltiples cartuchos, automatizado | 1 set |
| Tanque agua tratada | {round(flow_value * 0.5, 1)} m³ | Incluye sistema bombeo | 1 |
    """
        elif subsector == "Alimentos y Bebidas":
            summary += f"""| Trampa de grasas | {round(flow_value * 0.15, 1)} m³ | Diseño optimizado, limpieza automatizada | 1 |
| Tanque ecualización | {round(flow_value * 0.35, 1)} m³ | Tiempo retención 8h, agitación | 1 |
| Sistema DAF | {round(flow_value / 20, 1)} m³/h | Alta eficiencia remoción grasas | 1 |
| Reactor UASB | {round(flow_value * 0.2, 1)} m³ | Incluye sistema captación biogás | 1 |
| Tanque aireación | {round(flow_value * 0.3, 1)} m³ | Difusores burbuja fina, sopladores | 1 |
| Clarificador secundario | {round(flow_value * 0.15, 1)} m³ | Diseño cónico, extracción lodos | 1 |
| Sistema filtración | {round(flow_value / 24, 1)} m³/h | Multimedia con retrolavado automático | 1 |
| Sistema UV | {round(flow_value / 24, 1)} m³/h | Certificado para reúso | 1 |
    """
        else:
            summary += f"""| Pretratamiento | {round(flow_value / 20, 1)} m³/h | Diseñado según características específicas | 1 set |
| Tratamiento primario | {round(flow_value * 0.25, 1)} m³ | Adaptado a contaminantes específicos | 1 set |
| Tratamiento secundario | {round(flow_value * 0.35, 1)} m³ | Sistema biológico optimizado | 1 set |
| Tratamiento terciario | {round(flow_value / 24, 1)} m³/h | Según requerimientos de reúso/descarga | 1 set |
| Tanque agua tratada | {round(flow_value * 0.5, 1)} m³ | Incluye sistema bombeo | 1 |
    """

        # 7. Estimación de CAPEX y OPEX
        summary += """
## 7. Estimación de CAPEX y OPEX

### Inversión Inicial (CAPEX)
    """

        # Tabla de CAPEX
        summary += """
    | Concepto | Costo Estimado (USD) | Observaciones |
    |----------|----------------------|---------------|
    """

        # Calcular costos según flujo y subsector
        base_cost = flow_value * 1000  # $1000 USD por m³/día - base general

        if subsector == "Textil":
            equipment_cost = round(base_cost * 0.65, 0)
            installation_cost = round(base_cost * 0.20, 0)
            engineering_cost = round(base_cost * 0.10, 0)
            extras_cost = round(base_cost * 0.05, 0)
        elif subsector == "Alimentos y Bebidas":
            equipment_cost = round(base_cost * 0.60, 0)
            installation_cost = round(base_cost * 0.25, 0)
            engineering_cost = round(base_cost * 0.10, 0)
            extras_cost = round(base_cost * 0.05, 0)
        else:
            equipment_cost = round(base_cost * 0.65, 0)
            installation_cost = round(base_cost * 0.20, 0)
            engineering_cost = round(base_cost * 0.10, 0)
            extras_cost = round(base_cost * 0.05, 0)

        total_capex = (
            equipment_cost + installation_cost + engineering_cost + extras_cost
        )

        summary += f"""| Equipos principales | ${equipment_cost:,.2f} | Incluye todos los equipos listados en sección anterior |
    |Instalación y montaje | ${installation_cost:,.2f} | Obra civil, montaje, tuberías, instrumentación |
    | Ingeniería y permisos | ${engineering_cost:,.2f} | Diseño detallado, gestión de proyecto, permisos |
    | Puesta en marcha y capacitación | ${extras_cost:,.2f} | Incluye pruebas, ajustes, entrenamiento personal |
    | **TOTAL CAPEX** | **${total_capex:,.2f}** | **Inversión total estimada** |
    """

        summary += """
    ### Costos Operativos (OPEX)
    """

        # Tabla de OPEX
        summary += """
    | Concepto | Costo Mensual (USD) | Observaciones |
    |----------|---------------------|---------------|
    """

        # Calcular OPEX
        energy_cost = round(flow_value * 2.5, 0)
        chemical_cost = round(flow_value * 1.5, 0)
        maintenance_cost = round(total_capex * 0.005, 0)  # 0.5% del CAPEX mensual
        labor_cost = 1500 if flow_value < 200 else 2500
        sludge_cost = round(flow_value * 1.0, 0)

        total_monthly = (
            energy_cost + chemical_cost + maintenance_cost + labor_cost + sludge_cost
        )
        total_annual = total_monthly * 12

        summary += f"""| Energía eléctrica | ${energy_cost:,.2f} | Basado en consumo estimado de equipos |
    | Productos químicos | ${chemical_cost:,.2f} | Coagulantes, floculantes, otros insumos |
    | Mantenimiento | ${maintenance_cost:,.2f} | Repuestos, servicios técnicos |
    | Mano de obra | ${labor_cost:,.2f} | Personal operador y supervisión |
    | Gestión de lodos | ${sludge_cost:,.2f} | Disposición adecuada de residuos |
    | **TOTAL MENSUAL** | **${total_monthly:,.2f}** | **Costo operativo mensual** |
    | **TOTAL ANUAL** | **${total_annual:,.2f}** | **Costo operativo anual** |
    """

        # 8. Análisis de ROI
        summary += """
    ## 8. Análisis del Retorno de la Inversión (ROI)

    ### Proyección de Ahorros
    """

        # Tabla de ahorros
        summary += """
    | Concepto | Ahorro Mensual (USD) | Ahorro Anual (USD) |
    |----------|----------------------|-------------------|
    """

        # Calcular ahorros según consumo y costos
        water_cost = 2.0  # valor por defecto en USD/m³
        water_cost_text = client_info.get("costo_agua", "2.0 USD/m³")

        if isinstance(water_cost_text, str):
            import re

            match = re.search(r"(\d+(?:\.\d+)?)", water_cost_text)
            if match:
                water_cost = float(match.group(1))

        # Calcular ahorros
        water_reduction = flow_value * 0.6 * 30 * water_cost  # 60% reducción, 30 días
        discharge_reduction = (
            flow_value * 0.4 * 30 * water_cost * 0.5
        )  # 40% reducción, 50% del costo
        operational_benefits = flow_value * 30 * 0.2  # Beneficios adicionales

        total_monthly_savings = (
            water_reduction + discharge_reduction + operational_benefits
        )
        total_annual_savings = total_monthly_savings * 12

        summary += f"""| Reducción consumo agua | ${water_reduction:,.2f} | ${water_reduction*12:,.2f} |
    | Reducción costos descarga | ${discharge_reduction:,.2f} | ${discharge_reduction*12:,.2f} |
    | Beneficios operacionales | ${operational_benefits:,.2f} | ${operational_benefits*12:,.2f} |
    | **TOTAL AHORROS** | **${total_monthly_savings:,.2f}** | **${total_annual_savings:,.2f}** |
    """

        # Cálculo ROI
        summary += """
    ### Retorno de la Inversión
    """

        roi_years = total_capex / total_annual_savings
        roi_months = roi_years * 12

        summary += f"""- **Periodo de recuperación simple**: {roi_years:.1f} años ({int(roi_months)} meses)
    - **ROI a 5 años**: {(total_annual_savings * 5 - total_capex) / total_capex * 100:.1f}%
    - **Ahorros acumulados a 10 años**: ${total_annual_savings * 10:,.2f}

    *Nota: El análisis no considera el valor del dinero en el tiempo, inflación o posibles incrementos en el costo del agua.*
    """

        # 9. Preguntas y Respuestas
        summary += """
    ## 9. Preguntas y Respuestas

    ### Preguntas Frecuentes

    **P: ¿Cuánto espacio se requiere para la instalación?**  
    R: El sistema completo requiere aproximadamente 100-150 m² para una instalación típica de este tamaño, pero puede optimizarse según restricciones específicas del sitio.

    **P: ¿Cuál es el tiempo estimado de implementación?**  
    R: El proyecto completo, desde aprobación hasta puesta en marcha, tiene un cronograma típico de 4-6 meses.

    **P: ¿Qué mantenimiento requiere el sistema?**  
    R: El sistema requiere mantenimiento preventivo regular (diario, semanal y mensual) y revisiones mayores semestrales. Se proporcionará un manual detallado y capacitación al personal.

    **P: ¿Requiere personal especializado?**  
    R: Se recomienda contar con un operador capacitado. Hydrous ofrece programas de capacitación completos para su personal.
    """

        # Añadir descargo de responsabilidad y enlace para descargar
        summary += """
    ### Descargo de Responsabilidad

    Esta propuesta se basa en la información proporcionada y estándares de la industria. Los costos y especificaciones finales pueden variar tras un estudio detallado del sitio y análisis específicos del agua residual. Hydrous Management Group recomienda realizar pruebas piloto para validar el diseño final.
    """

        # Agregar enlace de descarga si tenemos ID de conversación
        if conversation_id:
            summary += f"""
    **Para obtener esta propuesta detallada en formato PDF, simplemente haga clic en el siguiente enlace:**

    [📥 DESCARGAR PROPUESTA EN PDF](/api/chat/{conversation_id}/download-proposal-pdf)
    """

        return summary

    def generate_proposal_pdf(self, proposal: Dict[str, Any]) -> str:
        """
        Genera un PDF con la propuesta usando una plantilla simplificada

        Args:
            proposal: Datos de la propuesta

        Returns:
            Ruta al archivo generado (PDF o HTML)
        """
        try:
            # Extraer información básica para el nombre del archivo
            client_name = proposal["client_info"]["name"].replace(" ", "_")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            # Crear contenido HTML simplificado
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Propuesta Hydrous - {proposal["client_info"]["name"]}</title>
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
                        max-width: 1200px;
                        margin: 0 auto;
                        padding: 20px;
                    }}
                    
                    h1 {{ 
                        color: #1a5276; 
                        border-bottom: 2px solid #3498db; 
                        padding-bottom: 10px; 
                        font-size: 28px;
                    }}
                    
                    h2 {{ 
                        color: #2874a6; 
                        margin-top: 25px; 
                        font-size: 22px;
                        border-left: 4px solid #3498db;
                        padding-left: 10px;
                    }}
                    
                    .header {{ 
                        background-color: #2c3e50; 
                        background-image: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
                        color: white; 
                        padding: 30px; 
                        text-align: center; 
                        margin-bottom: 30px;
                    }}
                    
                    .header h1 {{
                        border: none;
                        margin: 0;
                        padding: 0;
                        font-size: 32px;
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
                    
                    .objective {{
                        margin: 10px 0;
                        padding-left: 25px;
                        position: relative;
                    }}
                    
                    .objective:before {{
                        content: "✅";
                        position: absolute;
                        left: 0;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>Hydrous Management Group</h1>
                    <p>Soluciones personalizadas de tratamiento y reciclaje de agua</p>
                </div>
                
                <div class="container">
                    <div class="disclaimer">
                        <strong>📌 Aviso importante:</strong> Esta propuesta es preliminar y se basa en la información proporcionada. Los datos, estimaciones de costos y recomendaciones técnicas pueden variar tras un estudio detallado del sitio.
                    </div>
                    
                    <div class="section">
                        <h1>1. Datos del Cliente y Proyecto</h1>
                        
                        <table>
                            <tr>
                                <th style="width: 40%;">Información</th>
                                <th>Detalle</th>
                            </tr>
                            <tr>
                                <td><strong>Cliente</strong></td>
                                <td>{proposal["client_info"]["name"]}</td>
                            </tr>
                            <tr>
                                <td><strong>Ubicación</strong></td>
                                <td>{proposal["client_info"]["location"]}</td>
                            </tr>
                            <tr>
                                <td><strong>Sector</strong></td>
                                <td>{proposal["client_info"]["sector"]}</td>
                            </tr>
                            <tr>
                                <td><strong>Subsector</strong></td>
                                <td>{proposal["client_info"]["subsector"]}</td>
                            </tr>
                            <tr>
                                <td><strong>Consumo de Agua</strong></td>
                                <td>{proposal["project_details"].get("water_consumption", "No especificado")}</td>
                            </tr>
                            <tr>
                                <td><strong>Generación de Aguas Residuales</strong></td>
                                <td>{proposal["project_details"].get("wastewater_generation", "No especificado")}</td>
                            </tr>
                        </table>
                    </div>
                    
                    <div class="section">
                        <h1>2. Objetivos del Proyecto</h1>
                        
                        <h2>2.1. Objetivos Principales</h2>
                        <ul>
            """

            # Añadir objetivos
            for objective in proposal["project_details"].get(
                "objectives", ["Mejorar eficiencia hídrica"]
            ):
                html_content += f'            <li class="objective">{objective}</li>\n'

            html_content += """
                        </ul>
                        
                        <h2>2.2. Objetivos de Reúso</h2>
                        <ul>
            """

            # Añadir objetivos de reúso
            for reuse in proposal["project_details"].get(
                "reuse_objectives", ["Reutilización de agua"]
            ):
                html_content += f'            <li class="objective">{reuse}</li>\n'

            html_content += f"""
                        </ul>
                    </div>
                    
                    <div class="section">
                        <h1>3. Solución Técnica Propuesta</h1>
                        
                        <p>{proposal["recommended_solution"].get("description", "Solución personalizada para sus necesidades específicas")}</p>
                        
                        <h2>3.1. Proceso de Tratamiento</h2>
                        
                        <table>
                            <tr>
                                <th>Etapa</th>
                                <th>Descripción</th>
                            </tr>
                            <tr>
                                <td><strong>Pretratamiento</strong></td>
                                <td>{proposal["recommended_solution"].get("pretreatment", "No especificado")}</td>
                            </tr>
                            <tr>
                                <td><strong>Tratamiento Primario</strong></td>
                                <td>{proposal["recommended_solution"].get("primary", "No especificado")}</td>
                            </tr>
                            <tr>
                                <td><strong>Tratamiento Secundario</strong></td>
                                <td>{proposal["recommended_solution"].get("secondary", "No especificado")}</td>
                            </tr>
                            <tr>
                                <td><strong>Tratamiento Terciario</strong></td>
                                <td>{proposal["recommended_solution"].get("tertiary", "No especificado")}</td>
                            </tr>
                        </table>
                        
                        <div class="highlight">
                            <p><strong>Eficiencia de Recuperación:</strong> {proposal["recommended_solution"].get("efficiency", "50% del agua para reúso")}</p>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h1>4. Análisis Económico</h1>
                        
                        <h2>4.1. Inversión y Costos</h2>
                        
                        <table>
                            <tr>
                                <th>Concepto</th>
                                <th>Monto (USD)</th>
                            </tr>
                            <tr>
                                <td><strong>CAPEX (Inversión Inicial)</strong></td>
                                <td>${proposal["economic_analysis"].get("capex", 0):,.2f}</td>
                            </tr>
                            <tr>
                                <td><strong>OPEX (Costo Operativo Mensual)</strong></td>
                                <td>${proposal["economic_analysis"].get("opex_monthly", 0):,.2f}</td>
                            </tr>
                            <tr>
                                <td><strong>OPEX (Costo Operativo Anual)</strong></td>
                                <td>${proposal["economic_analysis"].get("opex_annual", 0):,.2f}</td>
                            </tr>
                        </table>
                        
                        <h2>4.2. Beneficios Económicos</h2>
                        
                        <table>
                            <tr>
                                <th>Concepto</th>
                                <th>Monto (USD)</th>
                            </tr>
                            <tr>
                                <td><strong>Ahorro Mensual Estimado</strong></td>
                                <td>${proposal["economic_analysis"].get("monthly_savings", 0):,.2f}</td>
                            </tr>
                            <tr>
                                <td><strong>Ahorro Anual Estimado</strong></td>
                                <td>${proposal["economic_analysis"].get("annual_savings", 0):,.2f}</td>
                            </tr>
                            <tr>
                                <td><strong>Periodo de Recuperación de Inversión</strong></td>
                                <td>{proposal["economic_analysis"].get("roi", "N/A")} años</td>
                            </tr>
                        </table>
                    </div>
                    
                    <div class="section">
                        <h1>5. Parámetros de Agua y Calidad</h1>
            """

            # Añadir parámetros detectados si existen
            if proposal.get("water_parameters"):
                html_content += """
                        <table>
                            <tr>
                                <th>Parámetro</th>
                                <th>Valor Detectado</th>
                                <th>Valor Objetivo Después del Tratamiento</th>
                            </tr>
                """

                for param, value in proposal["water_parameters"].items():
                    # Determinar valor objetivo según el parámetro
                    target_value = ""
                    if param.lower() == "ph":
                        target_value = "6.5 - 8.5"
                    elif param.lower() in ["dbo", "sst"]:
                        target_value = "≤ 30 mg/L"
                    elif param.lower() == "dqo":
                        target_value = "≤ 150 mg/L"
                    elif param.lower() == "sdt":
                        target_value = "≤ 500 mg/L"
                    else:
                        target_value = "Según normativa aplicable"

                    html_content += f"""
                            <tr>
                                <td><strong>{param.upper()}</strong></td>
                                <td>{value}</td>
                                <td>{target_value}</td>
                            </tr>
                    """

                html_content += """
                        </table>
                """
            else:
                html_content += """
                        <p>No se proporcionaron parámetros específicos del agua. Se recomienda realizar un análisis detallado para ajustar la solución propuesta.</p>
                """

            # Añadir referencia a documentos si existen
            if proposal.get("documents", {}).get("provided", False):
                doc_count = proposal["documents"].get("count", 0)
                doc_types = proposal["documents"].get("types", [])

                html_content += f"""
                        <h2>5.1. Documentos Analizados</h2>
                        <p>Se analizaron {doc_count} documentos proporcionados ({", ".join(doc_types)}) para la elaboración de esta propuesta.</p>
                """

                # Añadir información relevante de documentos
                relevant_info = proposal["documents"].get("relevant_info", [])
                if relevant_info:
                    html_content += """
                        <h3>Información Relevante de Documentos</h3>
                        <ul>
                    """

                    for info in relevant_info:
                        html_content += f"""
                            <li><strong>{info.get("filename", "")}</strong>: {info.get("summary", "")}</li>
                        """

                    html_content += """
                        </ul>
                    """

            html_content += """
                    </div>
                    
                    <div class="section">
                        <h1>6. Próximos Pasos</h1>
                        
                        <ol>
                            <li><strong>Estudio detallado del sitio</strong> para ajustar las especificaciones técnicas.</li>
                            <li><strong>Diseño detallado</strong> de la solución adaptada a su caso específico.</li>
                            <li><strong>Propuesta técnica-económica final</strong> con cotización detallada.</li>
                            <li><strong>Implementación y puesta en marcha</strong> del sistema de tratamiento.</li>
                            <li><strong>Capacitación</strong> para el personal operativo.</li>
                            <li><strong>Servicio de mantenimiento</strong> y optimización continua.</li>
                        </ol>
                    </div>
                    
                    <div class="disclaimer">
                        <p>Esta propuesta es preliminar y se basa en la información proporcionada. Los costos y especificaciones finales pueden variar tras un estudio detallado del sitio. Para más información, contacte a Hydrous Management Group.</p>
                    </div>
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

            # Guardar el HTML como respaldo
            html_path = os.path.join(
                settings.UPLOAD_DIR, f"{client_name}_propuesta_{timestamp}.html"
            )
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            logger.info(f"HTML de propuesta generado: {html_path}")

            # Intentar generar PDF con el primer método disponible
            if "pdfkit" in PDF_GENERATORS:
                try:
                    pdf_path = os.path.join(
                        settings.UPLOAD_DIR, f"{client_name}_propuesta_{timestamp}.pdf"
                    )

                    # Opciones para mejorar el renderizado
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

                    # Intentar detectar la ruta de wkhtmltopdf en Windows
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
                        logger.info(f"wkhtmltopdf encontrado en: {path_wkhtmltopdf}")
                        config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
                        pdfkit.from_string(
                            html_content,
                            pdf_path,
                            options=options,
                            configuration=config,
                        )
                    else:
                        # Intentar con la configuración por defecto
                        logger.info("Usando configuración por defecto de wkhtmltopdf")
                        pdfkit.from_string(html_content, pdf_path, options=options)

                    logger.info(f"PDF generado exitosamente con pdfkit: {pdf_path}")
                    return pdf_path
                except Exception as e:
                    logger.warning(f"Error al generar PDF con pdfkit: {str(e)}")

            if "weasyprint" in PDF_GENERATORS:
                try:
                    pdf_path = os.path.join(
                        settings.UPLOAD_DIR, f"{client_name}_propuesta_{timestamp}.pdf"
                    )

                    # Generar PDF con WeasyPrint
                    HTML(string=html_content).write_pdf(pdf_path)

                    logger.info(f"PDF generado exitosamente con WeasyPrint: {pdf_path}")
                    return pdf_path
                except Exception as e:
                    logger.warning(f"Error al generar PDF con WeasyPrint: {str(e)}")

            # Si no se pudo generar PDF, devolver la ruta del HTML
            logger.warning(f"No se pudo generar PDF. Se devolverá HTML: {html_path}")
            return html_path

        except Exception as e:
            logger.error(f"Error general al generar propuesta: {str(e)}")

            # Crear HTML de error
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
