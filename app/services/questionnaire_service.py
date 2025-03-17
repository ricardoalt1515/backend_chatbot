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
        """
        Formatea un resumen de la propuesta para presentar al usuario

        Args:
            proposal: Datos de la propuesta
            conversation_id: ID de conversación para incluir enlace de descarga

        Returns:
            Resumen de la propuesta en formato markdown
        """
        client_info = proposal["client_info"]
        project_details = proposal.get("project_details", {})
        solution = proposal.get("recommended_solution", {})
        economics = proposal.get("economic_analysis", {})

        # Crear resumen en formato markdown
        summary = f"""
# PROPUESTA DE SOLUCIÓN DE TRATAMIENTO DE AGUAS RESIDUALES

## 1. Resumen Ejecutivo

Basado en la información proporcionada para **{client_info["name"]}** en el sector **{client_info["sector"]}**, hemos diseñado una solución personalizada de tratamiento de aguas residuales que permitirá:

* Tratar eficientemente un caudal de aproximadamente **{economics.get("flow_rate", "N/A")} m³/día**
* Recuperar hasta un **{int(economics.get("reuse_efficiency", 0.5) * 100)}%** del agua para reúso
* Lograr un retorno de inversión estimado en **{economics.get("roi", "N/A")} años**

## 2. Solución Técnica Propuesta

La solución incluye un sistema integral con las siguientes etapas:

1. **Pretratamiento**: {solution.get("pretreatment", "No especificado")}
2. **Tratamiento Primario**: {solution.get("primary", "No especificado")}
3. **Tratamiento Secundario**: {solution.get("secondary", "No especificado")}
4. **Tratamiento Terciario**: {solution.get("tertiary", "No especificado")}

## 3. Beneficios Destacados

* **Ahorro económico**: Aproximadamente ${economics.get("annual_savings", 0):,.2f} USD anuales
* **Reducción de la huella hídrica**: Menor consumo de agua potable
* **Cumplimiento normativo**: Descarga de agua tratada dentro de parámetros legales
* **Sostenibilidad**: {solution.get("description", "Solución adaptada a sus necesidades específicas")}

## 4. Análisis Económico

| Concepto | Valor Estimado |
|----------|----------------|
| Inversión inicial (CAPEX) | ${economics.get("capex", 0):,.2f} USD |
| Costos operativos (OPEX) | ${economics.get("opex_monthly", 0):,.2f} USD/mes |
| Ahorro mensual estimado | ${economics.get("monthly_savings", 0):,.2f} USD/mes |
| Periodo de recuperación | {economics.get("roi", "N/A")} años |
"""

        # Agregar enlace de descarga si tenemos ID de conversación
        if conversation_id:
            summary += f"""
## 5. Descargar Propuesta Detallada

Para obtener la propuesta completa con todos los detalles técnicos y económicos, puede descargarla en formato PDF:

**[📥 DESCARGAR PROPUESTA COMPLETA](/api/chat/{conversation_id}/download-proposal-pdf)**

*Esta propuesta es preliminar y se basa en la información proporcionada. Los costos y especificaciones finales pueden variar tras un estudio detallado del sitio.*
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
