import datetime
import json
import logging
import os
import random
import re
import string
from typing import Dict, Any, Optional, List, Tuple

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
    """Servicio para manejar el cuestionario y sus respuestas"""

    def __init__(self):
        self.questionnaire_data = self._load_questionnaire_data()

    def _load_questionnaire_data(self) -> Dict[str, Any]:
        """Carga los datos del cuestionario desde un archivo JSON"""
        try:
            # En producción esto se cargaría desde un archivo
            questionnaire_path = os.path.join(
                os.path.dirname(__file__), "../data/questionnaire.json"
            )
            if os.path.exists(questionnaire_path):
                with open(questionnaire_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
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
            "subsectors": {"Industrial": ["Textil"]},
            "questions": {
                "Industrial_Textil": [
                    {
                        "id": "nombre_empresa",
                        "text": "Nombre usuario/cliente/nombre de la empresa",
                        "type": "text",
                        "required": True,
                    }
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

    def get_random_fact(self, sector: str, subsector: str) -> Optional[str]:
        """Obtiene un hecho aleatorio relacionado con el sector/subsector"""
        facts_key = f"{sector}_{subsector}"
        facts = self.questionnaire_data.get("facts", {}).get(facts_key, [])
        return random.choice(facts) if facts else None

    def get_introduction(self) -> Tuple[str, str]:
        """Obtiene el texto de introducción del cuestionario"""
        intro = self.questionnaire_data.get("introduction", {})
        return intro.get("text", ""), intro.get("explanation", "")

    def get_questionnaire_context(self, state: QuestionnaireState) -> str:
        """
        Obtiene el contexto relevante del cuestionario basado en el estado actual

        Args:
            state: Estado actual del cuestionario

        Returns:
            str: Contexto relevante para el modelo de IA
        """
        # Si no se ha seleccionado sector, enviar introducción y selección de sector
        if not state.sector:
            return self._get_introduction_and_sectors()

        # Si se ha seleccionado sector pero no subsector, enviar selección de subsector
        if state.sector and not state.subsector:
            return self._get_subsector_selection(state.sector)

        # Si se tiene sector y subsector, enviar solo las preguntas relevantes
        # y la pregunta actual marcada como "ACTUAL"
        return self._get_sector_subsector_questions(
            state.sector, state.subsector, state.current_question_id
        )

    def _get_introduction_and_sectors(self) -> str:
        """Obtiene la introducción y la selección de sectores"""
        intro_text, explanation = self.get_introduction()
        sectors = self.get_sectors()

        context = f"""
{intro_text}

{explanation}

**¿En qué sector opera tu empresa?**

"""
        # Añadir los sectores numerados
        for i, sector in enumerate(sectors, 1):
            context += f"{i}. {sector}\n"

        return context

    def _get_subsector_selection(self, sector: str) -> str:
        """Obtiene la selección de subsectores para un sector"""
        subsectors = self.get_subsectors(sector)

        context = f"""
**Sector: {sector}**

**¿Cuál es el giro específico de tu Empresa dentro del sector {sector}?**

"""
        # Añadir los subsectores numerados
        for i, subsector in enumerate(subsectors, 1):
            context += f"{i}. {subsector}\n"

        return context

    def _get_sector_subsector_questions(
        self, sector: str, subsector: str, current_question_id: Optional[str] = None
    ) -> str:
        """
        Obtiene las preguntas para un sector/subsector específico

        Args:
            sector: Sector seleccionado
            subsector: Subsector seleccionado
            current_question_id: ID de la pregunta actual (para marcarla)

        Returns:
            str: Contexto de las preguntas
        """
        question_key = f"{sector}_{subsector}"
        questions = self.questionnaire_data.get("questions", {}).get(question_key, [])

        if not questions:
            return f"No se encontraron preguntas para {sector} - {subsector}"

        context = f"""
**Sector: {sector}**
**Subsector: {subsector}**

**"Para continuar, quiero conocer algunos datos clave sobre tu empresa,
como la ubicación y el costo del agua. Estos factores pueden influir en
la viabilidad de distintas soluciones. Por ejemplo, en ciertas regiones,
el agua puede ser más costosa o escasa, lo que hace que una solución de
tratamiento o reutilización sea aún más valiosa. ¡Vamos con las
siguientes preguntas!"**

"""

        # Añadir todas las preguntas, marcando la actual
        for question in questions:
            q_id = question.get("id", "")
            q_text = question.get("text", "")
            q_type = question.get("type", "text")
            q_explanation = question.get("explanation", "")

            # Marcar la pregunta actual
            if q_id == current_question_id:
                context += f">>> PREGUNTA ACTUAL: {q_text} <<<\n"
            else:
                context += f"- {q_text}\n"

            # Añadir explicación si existe
            if q_explanation:
                context += f"  (Explicación: {q_explanation})\n"

            # Añadir opciones para preguntas de selección
            if (
                q_type in ["multiple_choice", "multiple_select"]
                and "options" in question
            ):
                context += "  Opciones:\n"
                for i, option in enumerate(question["options"], 1):
                    context += f"  {i}. {option}\n"

            context += "\n"

        return context

    def get_next_question(self, state: QuestionnaireState) -> Optional[Dict[str, Any]]:
        """Obtiene la siguiente pregunta basada en el estado actual"""
        if not state.active:
            return None

        if not state.sector:
            return {
                "id": "sector_selection",
                "text": "¿En qué sector opera tu empresa?",
                "type": "multiple_choice",
                "options": self.get_sectors(),
                "required": True,
                "explanation": "El sector determina el tipo de aguas residuales y las tecnologías más adecuadas para su tratamiento.",
            }

        if not state.subsector:
            return {
                "id": "subsector_selection",
                "text": f"¿Cuál es el giro específico de tu Empresa dentro del sector {state.sector}?",
                "type": "multiple_choice",
                "options": self.get_subsectors(state.sector),
                "required": True,
                "explanation": "Cada subsector tiene características específicas que influyen en el diseño de la solución.",
            }

        # Obtener las preguntas para este sector/subsector
        question_key = f"{state.sector}_{state.subsector}"
        questions = self.questionnaire_data.get("questions", {}).get(question_key, [])

        if not questions:
            # No hay preguntas para esta combinación de sector/subsector
            logger.warning(f"No se encontraron preguntas para {question_key}")
            return None

        # Determinar la siguiente pregunta no contestada
        for q in questions:
            if q["id"] not in state.answers:
                fact = self.get_random_fact(state.sector, state.subsector)

                # Añadir un hecho relevante a la explicación si existe
                if fact and q.get("explanation"):
                    q["explanation"] = (
                        f"{q['explanation']}\n\n*Dato interesante: {fact}*"
                    )

                return q

        # Si llegamos aquí, es que todas las preguntas han sido respondidas
        return None

    def process_answer(
        self, conversation: Conversation, question_id: str, answer: Any
    ) -> None:
        """Procesa una respuesta y actualiza el estado del cuestionario"""
        # Guardar la respuesta
        conversation.questionnaire_state.answers[question_id] = answer

        # Si es una respuesta al sector o subsector, actualizar esos campos
        if question_id == "sector_selection":
            sector_index = int(answer) - 1 if answer.isdigit() else 0
            sectors = self.get_sectors()
            if 0 <= sector_index < len(sectors):
                conversation.questionnaire_state.sector = sectors[sector_index]
            else:
                # Si se proporcionó el nombre en lugar del índice
                if answer in sectors:
                    conversation.questionnaire_state.sector = answer
        elif question_id == "subsector_selection":
            if conversation.questionnaire_state.sector:
                subsector_index = int(answer) - 1 if answer.isdigit() else 0
                subsectors = self.get_subsectors(
                    conversation.questionnaire_state.sector
                )
                if 0 <= subsector_index < len(subsectors):
                    conversation.questionnaire_state.subsector = subsectors[
                        subsector_index
                    ]
                else:
                    # Si se proporcionó el nombre en lugar del índice
                    if answer in subsectors:
                        conversation.questionnaire_state.subsector = answer

        # Actualizar el ID de la pregunta actual
        next_question = self.get_next_question(conversation.questionnaire_state)
        conversation.questionnaire_state.current_question_id = (
            next_question["id"] if next_question else None
        )

        # Verificar si hemos completado el cuestionario
        if next_question is None:
            conversation.questionnaire_state.completed = True

    def is_questionnaire_complete(self, conversation: Conversation) -> bool:
        """Verifica si el cuestionario está completo"""
        return conversation.questionnaire_state.completed

    def generate_proposal(self, conversation: Conversation) -> Dict[str, Any]:
        """Genera una propuesta basada en las respuestas del cuestionario"""
        answers = conversation.questionnaire_state.answers
        sector = conversation.questionnaire_state.sector
        subsector = conversation.questionnaire_state.subsector

        # Extraer información básica
        client_name = answers.get("nombre_empresa", "Cliente")
        location = answers.get("ubicacion", "No especificada")

        # Determinar los objetivos del proyecto
        objectives = []
        if "objetivo_principal" in answers:
            obj_principal = answers["objetivo_principal"]
            if obj_principal.isdigit():
                obj_index = int(obj_principal) - 1
                options = self._get_options_for_question(
                    "objetivo_principal", sector, subsector
                )
                if 0 <= obj_index < len(options):
                    objectives.append(options[obj_index])
            else:
                objectives.append(obj_principal)

        # Determinar objetivos de reúso
        reuse_objectives = []
        if "objetivo_reuso" in answers:
            reuse = answers["objetivo_reuso"]
            if isinstance(reuse, list):
                for r in reuse:
                    if r.isdigit():
                        r_index = int(r) - 1
                        options = self._get_options_for_question(
                            "objetivo_reuso", sector, subsector
                        )
                        if 0 <= r_index < len(options):
                            reuse_objectives.append(options[r_index])
                    else:
                        reuse_objectives.append(r)
            elif reuse.isdigit():
                r_index = int(reuse) - 1
                options = self._get_options_for_question(
                    "objetivo_reuso", sector, subsector
                )
                if 0 <= r_index < len(options):
                    reuse_objectives.append(options[r_index])
            else:
                reuse_objectives.append(reuse)

        # Extraer parámetros de agua residual
        wastewater_params = {}
        for param in ["sst", "dbo", "dqo", "ph", "color", "metales_pesados"]:
            if param in answers and answers[param]:
                wastewater_params[param] = answers[param]

        # Determinar flujo de agua
        flow_rate = answers.get("cantidad_agua_residual", "No especificado")

        # Generar recomendación de tratamiento básica
        treatment_recommendation = {
            "pretratamiento": {
                "descripcion": "Eliminación de sólidos gruesos y materiales flotantes",
                "tecnologias": ["Rejillas", "Tamices", "Desarenadores"],
                "eficiencia_esperada": "Eliminación del 90-95% de sólidos gruesos",
            },
            "primario": {
                "descripcion": "Remoción de sólidos suspendidos y parte de la materia orgánica",
                "tecnologias": [
                    "Flotación por aire disuelto (DAF)",
                    "Coagulación/Floculación",
                ],
                "eficiencia_esperada": "Reducción de 60-70% de SST, 30-40% de DQO",
            },
            "secundario": {
                "descripcion": "Degradación biológica de materia orgánica",
                "tecnologias": [
                    "Reactor biológico de membrana (MBR)",
                    "Reactor de biopelícula de lecho móvil (MBBR)",
                ],
                "eficiencia_esperada": "Reducción de 90-95% de DBO, 70-85% de DQO",
            },
            "terciario": {
                "descripcion": "Remoción de color y contaminantes residuales",
                "tecnologias": [
                    "Oxidación avanzada",
                    "Carbón activado",
                    "Nanofiltración",
                ],
                "eficiencia_esperada": "Reducción de 95-99% del color, 80-90% de contaminantes traza",
            },
        }

        # Estimar costos básicos
        cost_estimation = {
            "capex": {
                "equipos": 50000.0,
                "instalacion": 20000.0,
                "ingenieria": 10000.0,
                "total": 80000.0,
            },
            "opex": {
                "energia": 1000.0,
                "quimicos": 500.0,
                "mano_obra": 1500.0,
                "mantenimiento": 500.0,
                "total_mensual": 3500.0,
                "total_anual": 42000.0,
            },
        }

        # Calcular ROI básico
        roi = {
            "ahorro_anual": 60000.0,
            "periodo_recuperacion": 1.5,
            "roi_5_anos": 275.0,
        }

        # Construir propuesta completa
        proposal = {
            "client_info": {
                "name": client_name,
                "location": location,
                "sector": sector,
                "subsector": subsector,
            },
            "project_details": {
                "flow_rate": flow_rate,
                "objectives": objectives,
                "reuse_objectives": reuse_objectives,
            },
            "wastewater_parameters": wastewater_params,
            "recommended_treatment": treatment_recommendation,
            "cost_estimation": cost_estimation,
            "roi_analysis": roi,
            "disclaimer": self.questionnaire_data.get("proposal_template", {}).get(
                "disclaimer", ""
            ),
        }

        return proposal

    def _get_options_for_question(
        self, question_id: str, sector: str, subsector: str
    ) -> List[str]:
        """Obtiene las opciones para una pregunta específica"""
        question_key = f"{sector}_{subsector}"
        questions = self.questionnaire_data.get("questions", {}).get(question_key, [])

        for q in questions:
            if q["id"] == question_id and "options" in q:
                return q["options"]

        return []

    def format_proposal_summary(
        self, proposal: Dict[str, Any], conversation_id: str = None
    ) -> str:
        """
        Formatea un resumen de la propuesta para presentar al usuario con formato markdown

        Args:
            proposal: Datos de la propuesta
            conversation_id: ID de conversación para incluir enlace de descarga

        Returns:
            str: Resumen de la propuesta en formato markdown
        """
        client_info = proposal["client_info"]
        project_details = proposal.get("project_details", {})

        summary = f"""
# PROPUESTA DE SOLUCIÓN DE TRATAMIENTO DE AGUAS RESIDUALES

## 1. Introducción a Hydrous Management Group

Hydrous Management Group se especializa en **soluciones personalizadas de tratamiento de aguas residuales** para clientes industriales y comerciales. Nuestra **experiencia en gestión del agua** ayuda a las empresas a lograr **cumplimiento normativo, reducción de costos y reutilización sostenible del agua**.

## 2. Antecedentes del Proyecto

**Cliente**: {client_info['name']}  
**Ubicación**: {client_info['location']}  
**Sector**: {client_info['sector']}  
**Subsector**: {client_info['subsector']}

{project_details.get("flow_rate", "Caudal: Por determinar")}

## 3. Objetivo del Proyecto

- ✅ **Cumplimiento Normativo**: Garantizar que las aguas residuales tratadas cumplan con las regulaciones de descarga.
- ✅ **Optimización de Costos**: Reducir los costos de compra de agua y de descarga.
- ✅ **Reutilización del Agua**: Tratar las aguas residuales para su uso en procesos industriales.
- ✅ **Sostenibilidad**: Mejorar la huella ambiental mediante una gestión eficiente de los recursos.

## 4. Tecnologías de Tratamiento Recomendadas

1. **Tratamiento Primario**: {self._get_recommended_technology(proposal, "primario")}
2. **Tratamiento Biológico**: {self._get_recommended_technology(proposal, "secundario")}
3. **Tratamiento Terciario**: {self._get_recommended_technology(proposal, "terciario")}
4. **Sistema de Control**: PLC centralizado con monitoreo en tiempo real

## 5. Estimación de Costos

**CAPEX (Inversión Inicial)**: ${self._get_capex_total(proposal):,.2f} USD  
**OPEX (Costos Operativos)**: ${self._get_opex_monthly(proposal):,.2f} USD/mes

## 6. Análisis del Retorno de Inversión

**Periodo de Recuperación Simple**: {self._calculate_roi_years(proposal)} años  
**Ahorro Anual Estimado**: ${self._get_annual_savings(proposal):,.2f} USD

## 7. Preguntas y Respuestas

Si tiene preguntas adicionales sobre esta propuesta, no dude en consultarnos.
"""

        # Agregar enlace de descarga si tenemos ID de conversación
        if conversation_id:
            summary += f"""
## Descargar Propuesta Completa

**Para obtener esta propuesta detallada en formato PDF, simplemente haga clic en el siguiente enlace:**

[📥 DESCARGAR PROPUESTA EN PDF](/api/chat/{conversation_id}/download-proposal-pdf)

*Esta propuesta es preliminar y se basa en la información proporcionada. Los costos y especificaciones finales pueden variar tras un estudio detallado del sitio.*
"""

        return summary

    def _get_recommended_technology(
        self, proposal: Dict[str, Any], treatment_stage: str
    ) -> str:
        """Obtiene la tecnología recomendada para una etapa de tratamiento"""
        treatment = proposal.get("recommended_treatment", {})

        if treatment and treatment_stage in treatment:
            return treatment[treatment_stage].get("tecnologias", ["No especificado"])[0]

        # Valores por defecto según etapa
        default_technologies = {
            "primario": "Sistema DAF (Flotación por Aire Disuelto)",
            "secundario": "Reactor de Biopelícula de Lecho Móvil (MBBR)",
            "terciario": "Filtración de Arena y Carbón + Desinfección UV",
        }

        return default_technologies.get(treatment_stage, "Tecnología por determinar")

    def _get_capex_total(self, proposal: Dict[str, Any]) -> float:
        """Obtiene el CAPEX total de la propuesta"""
        cost_estimation = proposal.get("cost_estimation", {})
        capex = cost_estimation.get("capex", {})

        if "total" in capex:
            return capex["total"]

        # Calcular suma de componentes
        total = 0
        for item, cost in capex.items():
            if item != "total":
                total += cost

        # Si no hay datos, estimar basado en caudal
        if total == 0:
            project_details = proposal.get("project_details", {})
            flow_rate = project_details.get("flow_rate", "100 m³/día")

            flow_value = 100  # valor por defecto en m³/día
            if isinstance(flow_rate, str):
                match = re.search(r"(\d+(?:\.\d+)?)", flow_rate)
                if match:
                    flow_value = float(match.group(1))

            # Estimación simple: $1,000 USD por m³/día
            total = flow_value * 1000

        return total

    def _get_opex_monthly(self, proposal: Dict[str, Any]) -> float:
        """Obtiene el OPEX mensual de la propuesta"""
        cost_estimation = proposal.get("cost_estimation", {})
        opex = cost_estimation.get("opex", {})

        if "total_mensual" in opex:
            return opex["total_mensual"]

        # Calcular suma de componentes mensuales
        total = 0
        for item, cost in opex.items():
            if item not in ["total_mensual", "total_anual"]:
                total += cost

        # Si no hay datos, estimar basado en caudal
        if total == 0:
            project_details = proposal.get("project_details", {})
            flow_rate = project_details.get("flow_rate", "100 m³/día")

            flow_value = 100  # valor por defecto en m³/día
            if isinstance(flow_rate, str):
                match = re.search(r"(\d+(?:\.\d+)?)", flow_rate)
                if match:
                    flow_value = float(match.group(1))

            # Estimación simple: $7 USD por m³/día al mes
            total = flow_value * 7

        return total

    def _get_annual_savings(self, proposal: Dict[str, Any]) -> float:
        """Obtiene los ahorros anuales de la propuesta"""
        roi = proposal.get("roi_analysis", {})

        if "ahorro_anual" in roi:
            return roi["ahorro_anual"]

        # Estimar basado en CAPEX y periodo de recuperación
        capex = self._get_capex_total(proposal)
        recovery_period = float(
            self._calculate_roi_years(proposal).split("-")[0].strip()
        )

        # Si tenemos periodo de recuperación, estimar ahorro
        if recovery_period > 0:
            return capex / recovery_period

        # Alternativa: estimar basado en caudal
        project_details = proposal.get("project_details", {})
        flow_rate = project_details.get("flow_rate", "100 m³/día")

        flow_value = 100  # valor por defecto en m³/día
        if isinstance(flow_rate, str):
            match = re.search(r"(\d+(?:\.\d+)?)", flow_rate)
            if match:
                flow_value = float(match.group(1))

        # Estimación simple: ahorro anual de $365 USD por m³/día
        return flow_value * 365

    def _calculate_roi_years(self, proposal: Dict[str, Any]) -> str:
        """Calcula los años para el ROI basado en los datos disponibles"""
        roi = proposal.get("roi_analysis", {})
        if "periodo_recuperacion" in roi:
            return str(roi["periodo_recuperacion"])

        # Calcular basado en CAPEX y ahorro anual
        cost_estimation = proposal.get("cost_estimation", {})
        capex = cost_estimation.get("capex", {}).get("total", 0)

        if not capex:
            return "2.5 - 3.5"

        ahorro_anual = roi.get("ahorro_anual", 0)

        if not ahorro_anual:
            return "2.5 - 3.5"

        # Calcular periodo de recuperación simple
        recovery_period = capex / ahorro_anual

        return f"{recovery_period:.1f}"

    def generate_proposal_pdf(self, proposal: Dict[str, Any]) -> str:
        """
        Genera un PDF con la propuesta formateada siguiendo el formato oficial de Hydrous

        Args:
            proposal: Datos de la propuesta

        Returns:
            str: Ruta al archivo generado (PDF o HTML)
        """
        try:
            # Registrar inicio de generación de propuesta
            logger.info(
                f"Iniciando generación de propuesta para cliente: {proposal['client_info']['name']}"
            )

            # Obtener nombre del cliente para el nombre del archivo
            client_name = proposal["client_info"]["name"].replace(" ", "_")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            # Asegurar que el directorio existe
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

            # Crear el contenido HTML basado en el formato oficial de Hydrous
            html_content = self._generate_proposal_html(proposal)

            # Guardar el HTML como respaldo y para visualización directa
            html_path = os.path.join(
                settings.UPLOAD_DIR, f"{client_name}_propuesta_{timestamp}.html"
            )
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            logger.info(f"HTML de propuesta generado: {html_path}")

            # Intentar generar el PDF
            pdf_path = os.path.join(
                settings.UPLOAD_DIR, f"{client_name}_propuesta_{timestamp}.pdf"
            )

            # Método 1: Usar pdfkit si está disponible
            if "pdfkit" in PDF_GENERATORS:
                try:
                    logger.info("Intentando generar PDF con pdfkit...")

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

                    # Intentar detectar la ruta de wkhtmltopdf
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

            # Método 2: Usar WeasyPrint como alternativa
            if "weasyprint" in PDF_GENERATORS:
                try:
                    logger.info("Intentando generar PDF con WeasyPrint...")

                    # Crear objeto HTML desde el string
                    html = HTML(string=html_content)

                    # Generar PDF
                    html.write_pdf(pdf_path)

                    logger.info(f"PDF generado exitosamente con WeasyPrint: {pdf_path}")
                    return pdf_path
                except Exception as e:
                    logger.warning(f"Error al generar PDF con WeasyPrint: {str(e)}")

            # Si ambos métodos fallan, devolver la ruta del HTML
            logger.warning(
                f"No se pudo generar el PDF. Se devolverá el HTML: {html_path}"
            )
            return html_path

        except Exception as e:
            logger.error(f"Error general al generar el documento: {str(e)}")
            # En caso de error total, generar un HTML básico de error
            error_html_path = os.path.join(settings.UPLOAD_DIR, "error_propuesta.html")
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head><title>Error en Generación de Propuesta</title></head>
            <body>
                <h1>Ha ocurrido un error al generar la propuesta</h1>
                <p>Por favor, contacte al soporte técnico con el siguiente código: {datetime.datetime.now().strftime('%Y%m%d%H%M%S')}</p>
                <p>Error: {str(e)}</p>
            </body>
            </html>
            """
            with open(error_html_path, "w", encoding="utf-8") as f:
                f.write(error_html)
            return error_html_path

    def _generate_proposal_html(self, proposal: Dict[str, Any]) -> str:
        """
        Genera el contenido HTML de la propuesta siguiendo el formato oficial

        Args:
            proposal: Datos de la propuesta

        Returns:
            str: Contenido HTML de la propuesta
        """
        # Extraer información básica
        client_info = proposal["client_info"]

        # Crear tablas y secciones en formato HTML
        project_background_table = self._generate_project_background_table(proposal)
        parameters_table = self._generate_parameters_table(proposal)
        process_table = self._generate_process_table(proposal)
        equipment_table = self._generate_equipment_table(proposal)
        capex_table = self._generate_capex_table(proposal)
        opex_table = self._generate_opex_table(proposal)
        roi_table = self._generate_roi_table(proposal)

        # Construir el HTML completo
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Propuesta Hydrous - {client_info['name']}</title>
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
                    <strong>📌 Aviso importante:</strong> Esta propuesta fue generada mediante IA con base en la información proporcionada y estándares de la industria. Si bien se ha hecho todo lo posible para garantizar la precisión, los datos, estimaciones de costos y recomendaciones técnicas pueden contener errores y no son legalmente vinculantes. Se recomienda que todos los detalles sean validados por Hydrous Management Group antes de su implementación.
                </div>
                
                <div class="section">
                    <h1>1. Introducción a Hydrous Management Group</h1>
                    <p>Hydrous Management Group se especializa en <strong>soluciones personalizadas de tratamiento de aguas residuales</strong> diseñadas para clientes industriales y comerciales. Nuestra <strong>experiencia en gestión del agua</strong> ayuda a las empresas a lograr <strong>cumplimiento normativo, reducción de costos y reutilización sostenible del agua</strong>.</p>
                    
                    <p>Utilizando tecnologías avanzadas de tratamiento y diseño impulsado por IA, Hydrous ofrece <strong>soluciones eficientes, escalables y rentables</strong> para aguas residuales que optimizan el rendimiento operativo y minimizan el impacto ambiental.</p>
                </div>
                
                <div class="section">
                    <h1>2. Antecedentes del Proyecto</h1>
                    <p>Esta sección proporciona una visión general de la instalación, industria y necesidades de tratamiento de aguas residuales del cliente.</p>
                    
                    {project_background_table}
                </div>
                
                <div class="section">
                    <h1>3. Objetivo del Proyecto</h1>
                    <p>Los objetivos principales para el tratamiento de aguas residuales son:</p>
                    
                    <div class="objective"><strong>Cumplimiento Normativo</strong> — Garantizar que las aguas residuales tratadas cumplan con las regulaciones de descarga.</div>
                    <div class="objective"><strong>Optimización de Costos</strong> — Reducir los costos de compra de agua y de descarga.</div>
                    <div class="objective"><strong>Reutilización del Agua</strong> — Tratar las aguas residuales para su uso en procesos industriales.</div>
                    <div class="objective"><strong>Sostenibilidad</strong> — Mejorar la huella ambiental mediante una gestión eficiente de los recursos.</div>
                </div>
                
                <div class="section">
                    <h1>4. Supuestos Clave de Diseño y Comparación con Estándares de la Industria</h1>
                    <p>Esta sección compara las <strong>características de las aguas residuales sin tratar</strong> proporcionadas por el cliente con los <strong>valores estándar de la industria</strong> para aguas residuales industriales similares. También describe la calidad del efluente objetivo para cumplimiento o reutilización.</p>
                    
                    {parameters_table}
                </div>
                
                <div class="section">
                    <h1>5. Diseño del Proceso y Alternativas de Tratamiento</h1>
                    <p>Esta sección describe las <strong>tecnologías de tratamiento recomendadas</strong> y posibles <strong>alternativas</strong> para cumplir con los objetivos de tratamiento de aguas residuales.</p>
                    
                    {process_table}
                </div>
                
                <div class="section">
                    <h1>6. Equipamiento y Dimensionamiento Sugeridos</h1>
                    <p>Esta sección enumera el <strong>equipamiento recomendado, capacidades, dimensiones y posibles proveedores/modelos</strong> cuando están disponibles.</p>
                    
                    {equipment_table}
                </div>
                
                <div class="section">
                    <h1>7. CAPEX y OPEX Estimados</h1>
                    <p>Esta sección detalla tanto el <strong>gasto de capital (CAPEX)</strong> como el <strong>gasto operativo (OPEX)</strong>.</p>
                    
                    <h2>Desglose de CAPEX</h2>
                    {capex_table}
                    
                    <h2>Desglose de OPEX</h2>
                    {opex_table}
                </div>
                
                <div class="section">
                    <h1>8. Análisis del Retorno de Inversión (ROI)</h1>
                    <p>Ahorros de costos proyectados basados en <strong>reducción de compras de agua y menores tarifas de descarga</strong>.</p>
                    
                    {roi_table}
                    
                    <div class="highlight">
                        <p><strong>ROI Estimado:</strong> {self._calculate_roi_years(proposal)} años basado en ahorros de costos.</p>
                    </div>
                </div>
                
                <div class="section">
                    <h1>9. Preguntas y Respuestas</h1>
                    <p>Todas las <strong>preguntas y respuestas clave</strong> recopiladas durante la consulta se adjuntan como anexo para referencia.</p>
                    
                    <p>Para consultas o validación de esta propuesta, contacte a Hydrous Management Group en: <strong>info@hydrous.com</strong>.</p>
                </div>
                
                <div class="disclaimer">
                    <p>Esta propuesta es preliminar y se basa en la información proporcionada. Los costos y especificaciones finales pueden variar tras un estudio detallado del sitio.</p>
                </div>
            </div>
            
            <div class="footer">
                <p>Hydrous Management Group © {datetime.datetime.now().year}</p>
                <p>Generado el {datetime.datetime.now().strftime('%d/%m/%Y')}</p>
            </div>
        </body>
        </html>
        """

        return html

    def _generate_project_background_table(self, proposal: Dict[str, Any]) -> str:
        """Genera la tabla de antecedentes del proyecto"""
        client_info = proposal["client_info"]
        project_details = proposal.get("project_details", {})

        # Obtener datos o usar valores por defecto
        flow_rate = project_details.get("flow_rate", "No especificado")

        # Estimar algunos valores si no están disponibles
        wastewater_flow = flow_rate
        if flow_rate != "No especificado":
            match = re.search(r"(\d+(?:\.\d+)?)", flow_rate)
            if match:
                flow_value = float(match.group(1))
                # Asumir que el agua residual es ~80% del consumo de agua
                wastewater_flow = f"{int(flow_value * 0.8)} m³/día"

        # Describir sistema existente (si hay alguno)
        existing_system = "No hay sistema de tratamiento existente"
        if "sistema_existente" in proposal.get("client_info", {}):
            existing_system = "Sistema de tratamiento básico (detalles a confirmar)"

        return f"""
        <table>
            <tr>
                <th style="width: 40%;">Información del Cliente</th>
                <th>Detalles</th>
            </tr>
            <tr>
                <td><strong>Nombre del Cliente</strong></td>
                <td>{client_info.get('name', 'No especificado')}</td>
            </tr>
            <tr>
                <td><strong>Ubicación</strong></td>
                <td>{client_info.get('location', 'No especificado')}</td>
            </tr>
            <tr>
                <td><strong>Industria</strong></td>
                <td>{client_info.get('sector', 'No especificado')} - {client_info.get('subsector', 'No especificado')}</td>
            </tr>
            <tr>
                <td><strong>Fuente de Agua</strong></td>
                <td>{proposal.get('water_source', 'Suministro Municipal')}</td>
            </tr>
            <tr>
                <td><strong>Consumo Actual de Agua</strong></td>
                <td>{flow_rate}</td>
            </tr>
            <tr>
                <td><strong>Generación Actual de Aguas Residuales</strong></td>
                <td>{wastewater_flow}</td>
            </tr>
            <tr>
                <td><strong>Sistema de Tratamiento Existente (si lo hay)</strong></td>
                <td>{existing_system}</td>
            </tr>
        </table>
        """

    def _generate_parameters_table(self, proposal: Dict[str, Any]) -> str:
        """Genera la tabla de parámetros y comparación con estándares"""
        wastewater_params = proposal.get("wastewater_parameters", {})
        client_info = proposal.get("client_info", {})
        subsector = client_info.get("subsector", "")

        # Definir parámetros estándar por sector/subsector
        industry_standards = {
            "Textil": {
                "sst": "400 - 1,000",
                "dbo": "300 - 800",
                "dqo": "800 - 2,500",
                "ph": "6.0 - 9.0",
                "color": "Intenso (varios colorantes)",
            },
            "Alimentos y Bebidas": {
                "sst": "300 - 800",
                "dbo": "500 - 1,200",
                "dqo": "800 - 2,000",
                "ph": "4.0 - 6.5",
                "grasas_aceites": "50 - 200",
            },
            "Farmacéutica": {
                "sst": "100 - 400",
                "dbo": "200 - 600",
                "dqo": "400 - 1,000",
                "ph": "6.0 - 8.0",
            },
        }

        # Definir metas de efluente estándar
        effluent_goals = {
            "sst": "≤ 30",
            "dbo": "≤ 30",
            "dqo": "≤ 120",
            "ph": "6.5 - 8.5",
            "color": "Sin color aparente",
            "grasas_aceites": "≤ 15",
        }

        # Establecer parámetros según el subsector o usar valores genéricos
        standard_values = industry_standards.get(
            subsector,
            {
                "sst": "200 - 600",
                "dbo": "200 - 600",
                "dqo": "400 - 1,200",
                "ph": "6.0 - 9.0",
            },
        )

        # Construir filas de la tabla
        rows = ""
        for param, value in wastewater_params.items():
            param_name = self._get_parameter_display_name(param)
            industry_std = standard_values.get(param.lower(), "No disponible")
            effluent_goal = effluent_goals.get(param.lower(), "Según normativa")
            industry_effluent = "Cumple normativa"

            rows += f"""
            <tr>
                <td><strong>{param_name}</strong></td>
                <td>{value}</td>
                <td>{industry_std}</td>
                <td>{effluent_goal}</td>
                <td>{industry_effluent}</td>
            </tr>
            """

        # Si no hay parámetros, añadir filas estándar
        if not rows:
            rows = f"""
            <tr>
                <td><strong>SST (mg/L)</strong></td>
                <td>Por determinar</td>
                <td>{standard_values.get("sst", "200 - 600")}</td>
                <td>≤ 30</td>
                <td>≤ 30</td>
            </tr>
            <tr>
                <td><strong>DBO (mg/L)</strong></td>
                <td>Por determinar</td>
                <td>{standard_values.get("dbo", "200 - 600")}</td>
                <td>≤ 30</td>
                <td>≤ 30</td>
            </tr>
            <tr>
                <td><strong>DQO (mg/L)</strong></td>
                <td>Por determinar</td>
                <td>{standard_values.get("dqo", "400 - 1,200")}</td>
                <td>≤ 120</td>
                <td>≤ 120</td>
            </tr>
            <tr>
                <td><strong>pH</strong></td>
                <td>Por determinar</td>
                <td>{standard_values.get("ph", "6.0 - 9.0")}</td>
                <td>6.5 - 8.5</td>
                <td>6.5 - 8.5</td>
            </tr>
            """

        return f"""
        <table>
            <tr>
                <th>Parámetro</th>
                <th>Agua Residual Cruda (Proporcionado por Cliente)</th>
                <th>Estándar de la Industria para {subsector}</th>
                <th>Meta de Efluente (Regulación/Requisito de Reúso)</th>
                <th>Estándar de la Industria para Efluente (Referencia)</th>
            </tr>
            {rows}
        </table>
        """

    def _generate_process_table(self, proposal: Dict[str, Any]) -> str:
        """Genera la tabla de procesos y alternativas de tratamiento"""
        subsector = proposal.get("client_info", {}).get("subsector", "")

        # Definir tecnologías recomendadas por subsector
        recommended_technologies = {
            "Textil": [
                {
                    "stage": "Tratamiento Primario (Pre-Tratamiento)",
                    "recommended": "Flotación por Aire Disuelto (DAF)",
                    "description": "Elimina grasas, aceites y sólidos suspendidos",
                    "alternative": "Coagulación y Sedimentación",
                    "alt_description": "Menos eficiente pero menor costo",
                },
                {
                    "stage": "Ajuste de pH",
                    "recommended": "Dosificación Química (Cal, NaOH, H₂SO₄)",
                    "description": "Estabiliza niveles de pH",
                    "alternative": "Neutralización basada en Aireación",
                    "alt_description": "Proceso más lento pero sin químicos",
                },
                {
                    "stage": "Tratamiento Secundario (Biológico)",
                    "recommended": "Reactor de Biopelícula de Lecho Móvil (MBBR)",
                    "description": "Reducción eficiente de DQO/DBO",
                    "alternative": "Proceso de Lodos Activados (ASP)",
                    "alt_description": "Requiere más espacio y energía",
                },
                {
                    "stage": "Tratamiento Terciario (Pulido Final)",
                    "recommended": "Sistema de Oxidación Avanzada + Filtración de Carbón",
                    "description": "Elimina color residual y compuestos persistentes",
                    "alternative": "Biorreactor de Membrana (MBR)",
                    "alt_description": "Efluente de alta calidad, mayor costo",
                },
            ],
            "Alimentos y Bebidas": [
                {
                    "stage": "Tratamiento Primario (Pre-Tratamiento)",
                    "recommended": "Trampa de Grasas + DAF",
                    "description": "Elimina grasas, aceites y sólidos suspendidos",
                    "alternative": "Filtración Rotativa + Sedimentación",
                    "alt_description": "Menos eficiente para grasas pero menor costo",
                },
                {
                    "stage": "Tratamiento Secundario (Biológico)",
                    "recommended": "Reactor Anaerobio de Flujo Ascendente (UASB)",
                    "description": "Eficiente para alta carga orgánica con producción de biogás",
                    "alternative": "Proceso de Lodos Activados (ASP)",
                    "alt_description": "Menor eficiencia energética pero más simple",
                },
            ],
        }

        # Usar tecnologías específicas del subsector o genéricas
        technologies = recommended_technologies.get(
            subsector,
            [
                {
                    "stage": "Tratamiento Primario (Pre-Tratamiento)",
                    "recommended": "Flotación por Aire Disuelto (DAF)",
                    "description": "Elimina grasas, aceites y sólidos suspendidos",
                    "alternative": "Coagulación y Sedimentación",
                    "alt_description": "Menos eficiente pero menor costo",
                },
                {
                    "stage": "Tratamiento Secundario (Biológico)",
                    "recommended": "Reactor de Biopelícula de Lecho Móvil (MBBR)",
                    "description": "Reducción eficiente de DQO/DBO",
                    "alternative": "Proceso de Lodos Activados (ASP)",
                    "alt_description": "Requiere más espacio y energía",
                },
                {
                    "stage": "Tratamiento Terciario (Pulido Final)",
                    "recommended": "Filtración de Arena y Carbón",
                    "description": "Elimina orgánicos y sólidos residuales",
                    "alternative": "Biorreactor de Membrana (MBR)",
                    "alt_description": "Efluente de alta calidad, mayor costo",
                },
                {
                    "stage": "Desinfección",
                    "recommended": "Desinfección UV / Cloración",
                    "description": "Elimina patógenos",
                    "alternative": "Ozonización",
                    "alt_description": "Más efectiva pero intensiva en energía",
                },
            ],
        )

        # Construir filas de la tabla
        rows = ""
        for tech in technologies:
            rows += f"""
            <tr>
                <td><strong>{tech['stage']}</strong></td>
                <td><strong>{tech['recommended']}</strong> — {tech['description']}</td>
                <td><strong>{tech['alternative']}</strong> — {tech['alt_description']}</td>
            </tr>
            """

        return f"""
        <table>
            <tr>
                <th>Etapa de Tratamiento</th>
                <th>Tecnología Recomendada</th>
                <th>Opción Alternativa</th>
            </tr>
            {rows}
        </table>
        """

    def _generate_equipment_table(self, proposal: Dict[str, Any]) -> str:
        """Genera la tabla de equipamiento y dimensionamiento"""
        project_details = proposal.get("project_details", {})
        flow_rate = project_details.get("flow_rate", "Por determinar")

        # Estimar dimensiones según el caudal
        flow_value = 100  # valor por defecto en m³/día
        if isinstance(flow_rate, str):
            match = re.search(r"(\d+(?:\.\d+)?)", flow_rate)
            if match:
                flow_value = float(match.group(1))

        # Calcular dimensiones estimadas
        daf_capacity = f"{round(flow_value / 16, 1)} m³/h"
        mbbr_volume = f"{round(flow_value * 0.4, 0)} m³"
        filter_area = f"{round(flow_value * 0.02, 1)} m²"

        return f"""
        <table>
            <tr>
                <th>Equipo</th>
                <th>Capacidad</th>
                <th>Dimensiones</th>
                <th>Marca/Modelo (Si Disponible)</th>
            </tr>
            <tr>
                <td><strong>Sistema DAF</strong></td>
                <td>{daf_capacity}</td>
                <td>Por definir según espacio</td>
                <td>Estándar Industrial</td>
            </tr>
            <tr>
                <td><strong>Sistema de Ajuste de pH</strong></td>
                <td>Basado en flujo</td>
                <td>Unidad Compacta</td>
                <td>Estándar Industrial</td>
            </tr>
            <tr>
                <td><strong>Sistema MBBR</strong></td>
                <td>{mbbr_volume}</td>
                <td>Dimensiones de Tanque: Por definir</td>
                <td>Estándar Industrial o Equivalente</td>
            </tr>
            <tr>
                <td><strong>Filtro de Arena y Carbón</strong></td>
                <td>Caudal: {round(flow_value / 24, 1)} m³/h</td>
                <td>Área de filtro: {filter_area}</td>
                <td>Estándar Industrial o Equivalente</td>
            </tr>
        </table>
        """

    def _generate_capex_table(self, proposal: Dict[str, Any]) -> str:
        """Genera la tabla de CAPEX"""
        cost_estimation = proposal.get("cost_estimation", {})
        capex = cost_estimation.get("capex", {})

        # Si no hay datos específicos, generar estimados basados en el caudal
        if not capex:
            project_details = proposal.get("project_details", {})
            flow_rate = project_details.get("flow_rate", "100 m³/día")

            flow_value = 100  # valor por defecto en m³/día
            if isinstance(flow_rate, str):
                match = re.search(r"(\d+(?:\.\d+)?)", flow_rate)
                if match:
                    flow_value = float(match.group(1))

            # Estimar costos basados en el caudal
            daf_cost = round(flow_value * 300, 0)
            mbbr_cost = round(flow_value * 500, 0)
            tertiary_cost = round(flow_value * 200, 0)

            return f"""
            <table>
                <tr>
                    <th>Categoría</th>
                    <th>Costo Estimado (USD)</th>
                    <th>Notas</th>
                </tr>
                <tr>
                    <td><strong>Sistema DAF</strong></td>
                    <td>${daf_cost:,.0f}</td>
                    <td>Basado en instalaciones similares</td>
                </tr>
                <tr>
                    <td><strong>Sistema MBBR</strong></td>
                    <td>${mbbr_cost:,.0f}</td>
                    <td>Diseño escalable</td>
                </tr>
                <tr>
                    <td><strong>Filtración y Desinfección</strong></td>
                    <td>${tertiary_cost:,.0f}</td>
                    <td>Varía según necesidades de reúso</td>
                </tr>
                <tr style="font-weight: bold; background-color: #f2f2f2;">
                    <td><strong>CAPEX TOTAL</strong></td>
                    <td>${daf_cost + mbbr_cost + tertiary_cost:,.0f}</td>
                    <td>Rango estimado</td>
                </tr>
            </table>
            """

        # Si hay datos específicos, usarlos
        rows = ""
        total = 0
        for item, cost in capex.items():
            if item != "total":
                rows += f"""
                <tr>
                    <td><strong>{item.replace('_', ' ').title()}</strong></td>
                    <td>${cost:,.2f}</td>
                    <td>Basado en estimaciones preliminares</td>
                </tr>
                """
                total += cost

        return f"""
        <table>
            <tr>
                <th>Categoría</th>
                <th>Costo Estimado (USD)</th>
                <th>Notas</th>
            </tr>
            {rows}
            <tr style="font-weight: bold; background-color: #f2f2f2;">
                <td><strong>CAPEX TOTAL</strong></td>
                <td>${capex.get('total', total):,.2f}</td>
                <td>Rango estimado</td>
            </tr>
        </table>
        """

    def _generate_opex_table(self, proposal: Dict[str, Any]) -> str:
        """Genera la tabla de OPEX"""
        cost_estimation = proposal.get("cost_estimation", {})
        opex = cost_estimation.get("opex", {})

        # Si no hay datos específicos, generar estimados basados en el caudal
        if not opex:
            project_details = proposal.get("project_details", {})
            flow_rate = project_details.get("flow_rate", "100 m³/día")

            flow_value = 100  # valor por defecto en m³/día
            if isinstance(flow_rate, str):
                match = re.search(r"(\d+(?:\.\d+)?)", flow_rate)
                if match:
                    flow_value = float(match.group(1))

            # Estimar costos operativos mensuales basados en el caudal
            chemical_cost = round(flow_value * 2, 0)
            energy_cost = round(flow_value * 3, 0)
            labor_cost = round(1500 + (flow_value * 0.5), 0)
            sludge_cost = round(flow_value * 1.5, 0)

            total_monthly = chemical_cost + energy_cost + labor_cost + sludge_cost

            return f"""
            <table>
                <tr>
                    <th>Gasto Operativo</th>
                    <th>Costo Mensual Estimado (USD)</th>
                    <th>Notas</th>
                </tr>
                <tr>
                    <td><strong>Costos de Químicos</strong></td>
                    <td>${chemical_cost:,.0f}</td>
                    <td>Químicos para ajuste de pH y coagulación</td>
                </tr>
                <tr>
                    <td><strong>Costos de Energía</strong></td>
                    <td>${energy_cost:,.0f}</td>
                    <td>Consumo de energía para aireación, bombas</td>
                </tr>
                <tr>
                    <td><strong>Costos de Mano de Obra</strong></td>
                    <td>${labor_cost:,.0f}</td>
                    <td>Personal operador y de mantenimiento</td>
                </tr>
                <tr>
                    <td><strong>Eliminación de Lodos</strong></td>
                    <td>${sludge_cost:,.0f}</td>
                    <td>Remoción y tratamiento de lodos residuales</td>
                </tr>
                <tr style="font-weight: bold; background-color: #f2f2f2;">
                    <td><strong>OPEX TOTAL</strong></td>
                    <td>${total_monthly:,.0f}/mes</td>
                    <td>Rango estimado</td>
                </tr>
            </table>
            """

        # Si hay datos específicos, usarlos
        rows = ""
        total_monthly = 0
        for item, cost in opex.items():
            if item not in ["total_mensual", "total_anual"]:
                rows += f"""
                <tr>
                    <td><strong>{item.replace('_', ' ').title()}</strong></td>
                    <td>${cost:,.2f}</td>
                    <td>Estimación mensual</td>
                </tr>
                """
                total_monthly += cost

        return f"""
        <table>
            <tr>
                <th>Gasto Operativo</th>
                <th>Costo Mensual Estimado (USD)</th>
                <th>Notas</th>
            </tr>
            {rows}
            <tr style="font-weight: bold; background-color: #f2f2f2;">
                <td><strong>OPEX TOTAL</strong></td>
                <td>${opex.get('total_mensual', total_monthly):,.2f}/mes</td>
                <td>Rango estimado</td>
            </tr>
        </table>
        """

    def _generate_roi_table(self, proposal: Dict[str, Any]) -> str:
        """Genera la tabla de análisis ROI"""
        roi = proposal.get("roi_analysis", {})

        # Si no hay datos específicos, generar estimados
        if not roi:
            cost_estimation = proposal.get("cost_estimation", {})
            capex = cost_estimation.get("capex", {}).get("total", 100000)

            project_details = proposal.get("project_details", {})
            flow_rate = project_details.get("flow_rate", "100 m³/día")

            flow_value = 100  # valor por defecto en m³/día
            if isinstance(flow_rate, str):
                match = re.search(r"(\d+(?:\.\d+)?)", flow_rate)
                if match:
                    flow_value = float(match.group(1))

            # Estimar ahorros basados en el caudal
            water_savings = round(flow_value * 0.6 * 365 * 2, 0)  # 60% de reúso a $2/m³
            discharge_savings = round(
                flow_value * 0.4 * 365 * 1, 0
            )  # 40% de reducción a $1/m³

            total_savings = water_savings + discharge_savings

            return f"""
            <table>
                <tr>
                    <th>Parámetro</th>
                    <th>Costo Actual (USD/m³)</th>
                    <th>Costo Proyectado Después del Tratamiento</th>
                    <th>Ahorro Anual</th>
                </tr>
                <tr>
                    <td><strong>Costo de Compra de Agua</strong></td>
                    <td>$2.00/m³</td>
                    <td>$0.80/m³ (con reúso)</td>
                    <td>${water_savings:,.0f}</td>
                </tr>
                <tr>
                    <td><strong>Tarifas de Descarga</strong></td>
                    <td>$1.00/m³</td>
                    <td>$0.60/m³ (carga reducida)</td>
                    <td>${discharge_savings:,.0f}</td>
                </tr>
                <tr style="font-weight: bold; background-color: #f2f2f2;">
                    <td colspan="3"><strong>AHORRO TOTAL ANUAL</strong></td>
                    <td>${total_savings:,.0f}</td>
                </tr>
            </table>
            """

        # Si hay datos específicos, usarlos
        ahorro_anual = roi.get("ahorro_anual", 0)

        # Estimar desglose de ahorros
        water_savings = round(ahorro_anual * 0.6, 2)
        discharge_savings = round(ahorro_anual * 0.4, 2)

        return f"""
        <table>
            <tr>
                <th>Parámetro</th>
                <th>Costo Actual (USD/m³)</th>
                <th>Costo Proyectado Después del Tratamiento</th>
                <th>Ahorro Anual</th>
            </tr>
            <tr>
                <td><strong>Costo de Compra de Agua</strong></td>
                <td>Estimado</td>
                <td>Reducción con reúso</td>
                <td>${water_savings:,.2f}</td>
            </tr>
            <tr>
                <td><strong>Tarifas de Descarga</strong></td>
                <td>Estimado</td>
                <td>Reducción con tratamiento</td>
                <td>${discharge_savings:,.2f}</td>
            </tr>
            <tr style="font-weight: bold; background-color: #f2f2f2;">
                <td colspan="3"><strong>AHORRO TOTAL ANUAL</strong></td>
                <td>${ahorro_anual:,.2f}</td>
            </tr>
        </table>
        """

    def _get_parameter_display_name(self, param_code: str) -> str:
        """Obtiene el nombre de visualización para un código de parámetro"""
        param_names = {
            "sst": "SST (mg/L)",
            "SST": "SST (mg/L)",
            "sdt": "SDT (mg/L)",
            "SDT": "SDT (mg/L)",
            "dbo": "DBO (mg/L)",
            "DBO": "DBO (mg/L)",
            "dqo": "DQO (mg/L)",
            "DQO": "DQO (mg/L)",
            "ph": "pH",
            "pH": "pH",
            "color": "Color",
            "grasas_aceites": "Grasas y Aceites (mg/L)",
            "metales_pesados": "Metales Pesados (mg/L)",
            "conductividad": "Conductividad (μS/cm)",
        }

        return param_names.get(param_code, param_code.upper())

    def get_proposal_template(self) -> str:
        """
        Obtiene la plantilla de formato para propuestas

        Returns:
            str: Plantilla de formato para propuestas
        """
        return """
    **Hydrous Management Group -- AI-Generated Wastewater Treatment Proposal
    Guideline**

    **Important Disclaimer**

    This proposal was **generated using AI** based on the information
    provided by the end user and **industry-standard benchmarks**. While
    every effort has been made to ensure accuracy, the data, cost estimates,
    and technical recommendations **may contain errors and are not legally
    binding**. It is recommended that all details be **validated by Hydrous
    Management Group** before implementation.

    If a **phone number or contact information** was provided, a
    representative from **Hydrous Management Group will reach out** for
    further discussion. If not, you may contact us at **info@hydrous.com**
    for additional inquiries or clarification.

    **1. Introduction to Hydrous Management Group**

    Hydrous Management Group specializes in **customized wastewater
    treatment solutions** tailored for industrial and commercial clients.
    Our **expertise in water management** helps businesses achieve
    **regulatory compliance, cost reductions, and sustainable water reuse**.

    (... resto del formato de propuesta ...)
    """


# Instancia global del servicio
questionnaire_service = QuestionnaireService()
