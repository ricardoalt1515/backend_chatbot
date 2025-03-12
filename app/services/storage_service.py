import json
import logging
import os
import random
from typing import Dict, Any, Optional, List, Tuple

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
        """Procesa una respuesta y actualiza el estado del cuestionario de manera más inteligente"""
        # Guardar la respuesta
        conversation.questionnaire_state.answers[question_id] = answer

        # Procesar respuestas a las preguntas especiales (sector y subsector)
        if question_id == "sector_selection":
            # Intentar determinar el sector a partir de la respuesta
            sectors = self.get_sectors()

            if isinstance(answer, str):
                # Si es un número, usarlo como índice
                if answer.isdigit():
                    sector_index = int(answer) - 1
                    if 0 <= sector_index < len(sectors):
                        conversation.questionnaire_state.sector = sectors[sector_index]
                # Si no es un número, buscar coincidencia por texto
                else:
                    answer_lower = answer.lower()
                    for sector in sectors:
                        if (
                            sector.lower() in answer_lower
                            or answer_lower in sector.lower()
                        ):
                            conversation.questionnaire_state.sector = sector
                            break

            # Si no se pudo determinar el sector, usar el primero como fallback
            if not conversation.questionnaire_state.sector and sectors:
                conversation.questionnaire_state.sector = sectors[0]

        elif question_id == "subsector_selection":
            if conversation.questionnaire_state.sector:
                subsectors = self.get_subsectors(
                    conversation.questionnaire_state.sector
                )

                if isinstance(answer, str):
                    # Si es un número, usarlo como índice
                    if answer.isdigit():
                        subsector_index = int(answer) - 1
                        if 0 <= subsector_index < len(subsectors):
                            conversation.questionnaire_state.subsector = subsectors[
                                subsector_index
                            ]
                    # Si no es un número, buscar coincidencia por texto
                    else:
                        answer_lower = answer.lower()
                        for subsector in subsectors:
                            if (
                                subsector.lower() in answer_lower
                                or answer_lower in subsector.lower()
                            ):
                                conversation.questionnaire_state.subsector = subsector
                                break

                # Si no se pudo determinar el subsector, usar el primero como fallback
                if not conversation.questionnaire_state.subsector and subsectors:
                    conversation.questionnaire_state.subsector = subsectors[0]

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
        """Formatea un resumen de la propuesta para presentar al usuario de manera más atractiva"""
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

        # Crear una introducción personalizada
        intro = f"¡Excelente, {client_info['name']}! Gracias por completar el cuestionario. Basado en tus respuestas, he preparado una propuesta personalizada para tu proyecto de tratamiento de aguas residuales en el sector {client_info['sector']} - {client_info['subsector']}."

        # Formatear resumen con más detalle y mejor presentación
        summary = f"""
{intro}

**RESUMEN DE LA PROPUESTA DE HYDROUS**

**DATOS DEL PROYECTO**
• Cliente: {client_info['name']}
• Ubicación: {client_info['location']}
• Sector: {client_info['sector']} - {client_info['subsector']}
• Flujo de agua a tratar: {project_details.get('flow_rate', 'No especificado')}

**OBJETIVOS PRINCIPALES**
{("• " + "\n• ".join(project_details['objectives'])) if project_details.get('objectives') else "No especificados"}

**OBJETIVOS DE REÚSO**
{("• " + "\n• ".join(project_details['reuse_objectives'])) if project_details.get('reuse_objectives') else "No especificados"}

**SOLUCIÓN TECNOLÓGICA RECOMENDADA**
• **Pretratamiento**: {", ".join(treatment['pretratamiento']['tecnologias']) if 'pretratamiento' in treatment and treatment['pretratamiento'] and 'tecnologias' in treatment['pretratamiento'] else "No requerido"}
• **Tratamiento primario**: {", ".join(treatment['primario']['tecnologias']) if 'primario' in treatment and treatment['primario'] and 'tecnologias' in treatment['primario'] else "No requerido"}
• **Tratamiento secundario**: {", ".join(treatment['secundario']['tecnologias']) if 'secundario' in treatment and treatment['secundario'] and 'tecnologias' in treatment['secundario'] else "No requerido"}
• **Tratamiento terciario**: {", ".join(treatment['terciario']['tecnologias']) if 'terciario' in treatment and treatment['terciario'] and 'tecnologias' in treatment['terciario'] else "No requerido"}

**ANÁLISIS ECONÓMICO**
• Inversión inicial estimada: ${costs['capex']['total']:,.2f} USD
• Costo operativo anual: ${costs['opex']['total_anual']:,.2f} USD/año
• Costo operativo mensual: ${costs['opex']['total_mensual']:,.2f} USD/mes

**RETORNO DE INVERSIÓN**
• Ahorro anual estimado: ${roi['ahorro_anual']:,.2f} USD/año
• Periodo de recuperación: {roi['periodo_recuperacion']:.1f} años
• ROI a 5 años: {roi['roi_5_anos']:.1f}%

**BENEFICIOS AMBIENTALES**
• Reducción de la huella hídrica de tu operación
• Disminución de la descarga de contaminantes al medio ambiente
• Cumplimiento con normativas ambientales vigentes
• Contribución a la sostenibilidad del recurso hídrico

**PRÓXIMOS PASOS**
¿Te gustaría recibir una propuesta detallada por correo electrónico? ¿O prefieres programar una reunión con nuestros especialistas para revisar en detalle esta recomendación y resolver cualquier duda específica?

También puedo responder cualquier pregunta adicional que tengas sobre la solución propuesta.
"""
        return summary


# Instancia global del servicio
questionnaire_service = QuestionnaireService()
