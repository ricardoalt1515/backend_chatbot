import json
import logging
import os
import random
from typing import Dict, Any, Optional, List, Tuple
import markdown2
import pdfkit  # Para convertir HTML a PDF

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

    def format_proposal_summary(self, proposal: Dict[str, Any]) -> str:
        """Formatea un resumen de la propuesta para presentar al usuario"""
        client_info = proposal["client_info"]
        project_details = proposal["project_details"]
        treatment = proposal["recommended_treatment"]
        costs = proposal["cost_estimation"]
        roi = proposal["roi_analysis"]

        # Formatear tecnologías recomendadas
        technologies = []
        for stage, details in treatment.items():
            if details and "tecnologias" in details:
                for tech in details["tecnologias"]:
                    technologies.append(f"{tech} ({stage})")

        # Formatear resumen
        summary = f"""
# RESUMEN DE LA PROPUESTA DE HYDROUS

## 📋 DATOS DEL PROYECTO
- **Cliente**: {client_info['name']}
- **Ubicación**: {client_info['location']}
- **Sector**: {client_info['sector']} - {client_info['subsector']}
- **Flujo de agua a tratar**: {project_details.get('flow_rate', 'No especificado')}

## 🎯 OBJETIVOS PRINCIPALES
{"- " + "- ".join(project_details['objectives']) if project_details.get('objectives') else "No especificados"}

## ♻️ OBJETIVOS DE REÚSO
{"- " + "- ".join(project_details['reuse_objectives']) if project_details.get('reuse_objectives') else "No especificados"}

## ⚙️ SOLUCIÓN TECNOLÓGICA RECOMENDADA
- **Pretratamiento**: {", ".join(treatment['pretratamiento']['tecnologias']) if 'pretratamiento' in treatment and treatment['pretratamiento'] and 'tecnologias' in treatment['pretratamiento'] else "No requerido"}
- **Tratamiento primario**: {", ".join(treatment['primario']['tecnologias']) if 'primario' in treatment and treatment['primario'] and 'tecnologias' in treatment['primario'] else "No requerido"}
- **Tratamiento secundario**: {", ".join(treatment['secundario']['tecnologias']) if 'secundario' in treatment and treatment['secundario'] and 'tecnologias' in treatment['secundario'] else "No requerido"}
- **Tratamiento terciario**: {", ".join(treatment['terciario']['tecnologias']) if 'terciario' in treatment and treatment['terciario'] and 'tecnologias' in treatment['terciario'] else "No requerido"}

## 💰 ANÁLISIS ECONÓMICO
- **Inversión inicial estimada**: ${costs['capex']['total']:,.2f} USD
- **Costo operativo anual**: ${costs['opex']['total_anual']:,.2f} USD/año
- **Costo operativo mensual**: ${costs['opex']['total_mensual']:,.2f} USD/mes

## 📈 RETORNO DE INVERSIÓN
- **Ahorro anual estimado**: ${roi['ahorro_anual']:,.2f} USD/año
- **Periodo de recuperación**: {roi['periodo_recuperacion']:.1f} años
- **ROI a 5 años**: {roi['roi_5_anos']:.1f}%

## 🌱 BENEFICIOS AMBIENTALES
- Reducción de la huella hídrica de tu operación
- Disminución de la descarga de contaminantes al medio ambiente
- Cumplimiento con normativas ambientales vigentes
- Contribución a la sostenibilidad del recurso hídrico

## PRÓXIMOS PASOS
¿Te gustaría recibir una propuesta detallada por correo electrónico? ¿O prefieres programar una reunión con nuestros especialistas para revisar en detalle esta recomendación y resolver cualquier duda específica?

También puedo generar un PDF con esta propuesta para que puedas descargarla y compartirla con tu equipo.
"""
        return summary

    def generate_proposal_pdf(self, proposal: Dict[str, Any]) -> str:
        """
        Genera un PDF con la propuesta formateada

        Args:
            proposal: Datos de la propuesta

        Returns:
            str: Ruta al archivo PDF generado
        """
        try:
            # Crear el contenido HTML a partir del markdown
            markdown_content = self.format_proposal_summary(proposal)
            html_content = markdown2.markdown(markdown_content)

            # Añadir estilos al HTML
            styled_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Propuesta Hydrous - {proposal['client_info']['name']}</title>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                    h2 {{ color: #2980b9; margin-top: 20px; }}
                    .header {{ background-color: #3498db; color: white; padding: 20px; text-align: center; }}
                    .footer {{ background-color: #f9f9f9; padding: 10px; text-align: center; font-size: 0.8em; margin-top: 30px; }}
                    .disclaimer {{ background-color: #f8f9fa; border-left: 4px solid #e74c3c; padding: 10px; margin: 20px 0; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>Hydrous Management Group</h1>
                    <p>Soluciones personalizadas de tratamiento de agua</p>
                </div>
                
                {html_content}
                
                <div class="footer">
                    <p>Hydrous Management Group © {datetime.datetime.now().year}</p>
                    <p>Propuesta generada con IA - Para más información contacte a info@hydrous.com</p>
                </div>
            </body>
            </html>
            """

            # Generar un nombre de archivo único
            client_name = proposal["client_info"]["name"].replace(" ", "_")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{client_name}_propuesta_{timestamp}.pdf"
            output_path = os.path.join(settings.UPLOAD_DIR, filename)

            # Convertir HTML a PDF
            pdfkit.from_string(styled_html, output_path)

            return output_path
        except Exception as e:
            logger.error(f"Error al generar PDF: {str(e)}")
            return ""

    def get_proposal_template(self) -> str:
        """
        Obtiene la plantilla de formato para propuestas

        Returns:
            str: Plantilla de formato para propuestas
        """
        return """
**Hydrous Management Group -- AI-Generated Wastewater Treatment Proposal
Guideline**

**📌 Important Disclaimer**

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
