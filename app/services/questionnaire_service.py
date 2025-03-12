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

        # Generar recomendación de tratamiento basada en el sector/subsector
        treatment_recommendation = self._recommend_treatment(
            sector, subsector, wastewater_params
        )

        # Estimar costos basados en el flujo y tratamiento recomendado
        cost_estimation = self._estimate_costs(flow_rate, treatment_recommendation)

        # Calcular retorno de inversión
        roi = self._calculate_roi(cost_estimation, answers)

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

    def _recommend_treatment(
        self, sector: str, subsector: str, wastewater_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Recomienda un tratamiento basado en el sector/subsector y parámetros del agua residual"""
        # Esta es una versión simplificada. En producción, se implementaría
        # un algoritmo más complejo basado en las características del agua residual

        treatment = {
            "pretratamiento": {
                "descripcion": "Eliminación de sólidos gruesos y materiales flotantes",
                "tecnologias": ["Rejillas", "Tamices", "Desarenadores"],
                "eficiencia_esperada": "Eliminación del 90-95% de sólidos gruesos",
                "justificacion": "Necesario para proteger el equipo posterior y mejorar la eficiencia del tratamiento",
            },
            "primario": {},
            "secundario": {},
            "terciario": {},
        }

        # Tratamiento primario basado en sector/subsector
        if sector == "Industrial" and subsector == "Textil":
            treatment["primario"] = {
                "descripcion": "Remoción de sólidos suspendidos y parte de la materia orgánica",
                "tecnologias": [
                    "Flotación por aire disuelto (DAF)",
                    "Coagulación/Floculación",
                ],
                "eficiencia_esperada": "Reducción de 60-70% de SST, 30-40% de DQO",
                "justificacion": "Las aguas residuales textiles contienen altas concentraciones de sólidos suspendidos y colorantes que se pueden eliminar eficientemente mediante procesos físico-químicos",
            }

            # Tratamiento secundario
            dqo_valor = self._parse_numeric_value(wastewater_params.get("dqo", "1000"))
            if dqo_valor > 1000:
                treatment["secundario"] = {
                    "descripcion": "Degradación biológica de materia orgánica",
                    "tecnologias": [
                        "Reactor biológico de membrana (MBR)",
                        "Reactor de biopelícula de lecho móvil (MBBR)",
                    ],
                    "eficiencia_esperada": "Reducción de 90-95% de DBO, 70-85% de DQO",
                    "justificacion": "Alta carga orgánica requiere tratamiento biológico avanzado con retención de biomasa eficiente",
                }
            else:
                treatment["secundario"] = {
                    "descripcion": "Degradación biológica de materia orgánica",
                    "tecnologias": [
                        "Lodos activados convencionales",
                        "Reactor secuencial por lotes (SBR)",
                    ],
                    "eficiencia_esperada": "Reducción de 85-90% de DBO, 60-75% de DQO",
                    "justificacion": "Carga orgánica moderada permite usar tecnologías convencionales con buena relación costo-beneficio",
                }

            # Tratamiento terciario
            color_mencionado = "color" in wastewater_params
            if color_mencionado:
                treatment["terciario"] = {
                    "descripcion": "Remoción de color y contaminantes residuales",
                    "tecnologias": [
                        "Oxidación avanzada",
                        "Carbón activado",
                        "Nanofiltración",
                    ],
                    "eficiencia_esperada": "Reducción de 95-99% del color, 80-90% de contaminantes traza",
                    "justificacion": "Los efluentes textiles con colorantes requieren remoción específica del color para cumplir normativas y permitir reúso",
                }
            else:
                treatment["terciario"] = {
                    "descripcion": "Pulido final del efluente",
                    "tecnologias": ["Filtración multimedia", "Desinfección UV"],
                    "eficiencia_esperada": "Reducción adicional de 90% de sólidos suspendidos, 99% de patógenos",
                    "justificacion": "Tratamiento final para asegurar cumplimiento normativo y posibilitar el reúso",
                }

        return treatment

    def _parse_numeric_value(self, value_str: str) -> float:
        """Convierte un valor de texto en número, maneja unidades comunes"""
        try:
            # Remover posibles unidades y convertir a float
            cleaned_value = (
                value_str.lower().replace("mg/l", "").replace("ppm", "").strip()
            )
            return float(cleaned_value)
        except (ValueError, TypeError):
            # Si no se puede convertir, devolver un valor por defecto
            return 0.0

    def _estimate_costs(
        self, flow_rate: str, treatment_recommendation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Estima los costos CAPEX y OPEX basados en el flujo y el tratamiento recomendado"""
        # Estimar el flujo como número para cálculos
        try:
            # Intentar extraer un valor numérico del flujo
            numeric_flow = "".join(
                filter(lambda x: x.isdigit() or x == ".", flow_rate.split()[0])
            )
            flow_value = float(numeric_flow)
            # Estimar unidades (m³/día como predeterminado)
            if "semana" in flow_rate.lower():
                flow_value = flow_value / 7  # convertir a diario
            elif "mes" in flow_rate.lower():
                flow_value = flow_value / 30  # convertir a diario
            elif "hora" in flow_rate.lower():
                flow_value = flow_value * 24  # convertir a diario
        except:
            # Si no podemos extraer un valor, usar un valor predeterminado
            flow_value = 100  # m³/día como valor predeterminado

        # Costos base por m³/día de capacidad
        base_costs = {
            "pretratamiento": 500,  # USD por m³/día
            "primario": 1000,  # USD por m³/día
            "secundario": 1500,  # USD por m³/día
            "terciario": 2000,  # USD por m³/día
        }

        # Ajuste por economía de escala
        scale_factor = 0.85 if flow_value > 200 else (0.9 if flow_value > 50 else 1.0)

        # Calcular CAPEX por etapa
        capex = {}
        total_capex = 0

        for stage, details in treatment_recommendation.items():
            if details:  # Si la etapa tiene detalles
                # Factor tecnológico basado en las tecnologías recomendadas
                tech_factor = 1.0
                if "tecnologias" in details:
                    technologies = details["tecnologias"]
                    if "MBR" in str(technologies):
                        tech_factor = 1.5
                    elif "Oxidación avanzada" in str(technologies):
                        tech_factor = 1.3
                    elif "Nanofiltración" in str(
                        technologies
                    ) or "Ósmosis inversa" in str(technologies):
                        tech_factor = 1.4

                # Costo de esta etapa
                stage_cost = (
                    base_costs.get(stage, 1000)
                    * flow_value
                    * scale_factor
                    * tech_factor
                )
                capex[stage] = stage_cost
                total_capex += stage_cost

        # Añadir costos adicionales
        engineering_cost = total_capex * 0.15
        installation_cost = total_capex * 0.3

        capex["ingenieria_y_diseno"] = engineering_cost
        capex["instalacion_y_puesta_en_marcha"] = installation_cost
        capex["total"] = total_capex + engineering_cost + installation_cost

        # Estimar OPEX
        # Base: 5-10% del CAPEX anual
        base_opex_annual = capex["total"] * 0.08

        opex = {
            "energia": base_opex_annual * 0.3,  # 30% del OPEX
            "quimicos": base_opex_annual * 0.25,  # 25% del OPEX
            "mantenimiento": base_opex_annual * 0.2,  # 20% del OPEX
            "mano_de_obra": base_opex_annual * 0.15,  # 15% del OPEX
            "disposicion_lodos": base_opex_annual * 0.1,  # 10% del OPEX
            "total_anual": base_opex_annual,
            "total_mensual": base_opex_annual / 12,
        }

        return {
            "capex": capex,
            "opex": opex,
            "flow_rate_estimated": flow_value,
            "flow_unit": "m³/día",
        }

    def _calculate_roi(
        self, cost_estimation: Dict[str, Any], answers: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calcula el retorno de inversión basado en los costos y ahorros potenciales"""
        # Extraer datos relevantes
        capex_total = cost_estimation["capex"]["total"]
        opex_annual = cost_estimation["opex"]["total_anual"]
        flow_rate = cost_estimation["flow_rate_estimated"]  # m³/día

        # Estimar costo actual del agua
        costo_agua_actual = 0
        if "costo_agua" in answers:
            try:
                # Intentar extraer valor numérico del costo del agua
                costo_str = answers["costo_agua"]
                numeric_cost = "".join(
                    filter(lambda x: x.isdigit() or x == ".", costo_str.split()[0])
                )
                costo_agua_actual = float(numeric_cost)
            except:
                # Valor predeterminado en caso de no poder extraerlo
                costo_agua_actual = 1.5  # USD/m³, costo típico
        else:
            costo_agua_actual = 1.5  # USD/m³, costo típico

        # Estimar ahorros basados en reúso
        reuse_percentage = 0.7  # Suponer que se puede reusar 70% del agua tratada
        if "objetivo_reuso" in answers:
            reuse_answer = answers["objetivo_reuso"]
            if isinstance(reuse_answer, list) and len(reuse_answer) > 0:
                reuse_percentage = 0.5 + (
                    len(reuse_answer) * 0.1
                )  # Más objetivos de reúso = mayor porcentaje
                if reuse_percentage > 0.9:
                    reuse_percentage = 0.9  # Máximo 90% de reúso

        # Calcular ahorro anual en agua
        ahorro_agua_anual = flow_rate * 365 * reuse_percentage * costo_agua_actual

        # Estimar ahorro en costos de descarga (aproximadamente 20-30% del costo del agua limpia)
        ahorro_descarga_anual = flow_rate * 365 * 0.25 * costo_agua_actual

        # Calcular ahorro total anual
        ahorro_total_anual = ahorro_agua_anual + ahorro_descarga_anual

        # Calcular beneficio neto anual (ahorro - OPEX)
        beneficio_neto_anual = ahorro_total_anual - opex_annual

        # Calcular periodo de recuperación de la inversión (años)
        if beneficio_neto_anual > 0:
            periodo_recuperacion = capex_total / beneficio_neto_anual
        else:
            periodo_recuperacion = float("inf")  # No se recupera la inversión

        # Calcular ROI a 5 años
        roi_5_anos = ((beneficio_neto_anual * 5) - capex_total) / capex_total * 100

        return {
            "ahorro_agua_anual": ahorro_agua_anual,
            "ahorro_descarga_anual": ahorro_descarga_anual,
            "ahorro_total_anual": ahorro_total_anual,
            "beneficio_neto_anual": beneficio_neto_anual,
            "periodo_recuperacion_anos": periodo_recuperacion,
            "roi_5_anos_porcentaje": roi_5_anos,
            "supuestos": {
                "porcentaje_reuso": reuse_percentage * 100,
                "costo_agua": costo_agua_actual,
                "dias_operacion_anual": 365,
            },
        }

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
¡Gracias por completar el cuestionario! Basándonos en tus respuestas, hemos preparado una propuesta preliminar para tu proyecto de tratamiento de aguas residuales.

**RESUMEN DE LA PROPUESTA**

**Cliente:** {client_info['name']}
**Ubicación:** {client_info['location']}
**Sector:** {client_info['sector']} - {client_info['subsector']}

**OBJETIVOS DEL PROYECTO**
{"- " + "- ".join(project_details['objectives']) if project_details['objectives'] else "No especificados"}

**OBJETIVOS DE REÚSO**
{"- " + "- ".join(project_details['reuse_objectives']) if project_details['reuse_objectives'] else "No especificados"}

**TRATAMIENTO RECOMENDADO**
- Pretratamiento: {", ".join(treatment['pretratamiento']['tecnologias']) if 'pretratamiento' in treatment and treatment['pretratamiento'] and 'tecnologias' in treatment['pretratamiento'] else "No requerido"}
- Tratamiento primario: {", ".join(treatment['primario']['tecnologias']) if 'primario' in treatment and treatment['primario'] and 'tecnologias' in treatment['primario'] else "No requerido"}
- Tratamiento secundario: {", ".join(treatment['secundario']['tecnologias']) if 'secundario' in treatment and treatment['secundario'] and 'tecnologias' in treatment['secundario'] else "No requerido"}
- Tratamiento terciario: {", ".join(treatment['terciario']['tecnologias']) if 'terciario' in treatment and treatment['terciario'] and 'tecnologias' in treatment['terciario'] else "No requerido"}

**ESTIMACIÓN DE COSTOS**
- CAPEX total estimado: ${costs['capex']['total']:,.2f} USD
- OPEX anual estimado: ${costs['opex']['total_anual']:,.2f} USD/año
- OPEX mensual estimado: ${costs['opex']['total_mensual']:,.2f} USD/mes

**ANÁLISIS DE RETORNO DE INVERSIÓN**
- Ahorro anual estimado: ${roi['ahorro_total_anual']:,.2f} USD/año
- Periodo de recuperación estimado: {roi['periodo_recuperacion_anos']:.1f} años
- ROI a 5 años: {roi['roi_5_anos_porcentaje']:.1f}%

**BENEFICIO AMBIENTAL**
- Agua recuperada estimada: {costs['flow_rate_estimated'] * roi['supuestos']['porcentaje_reuso'] / 100:,.1f} {costs['flow_unit']}
- Reducción de la huella hídrica: Alta

¿Te gustaría recibir una propuesta detallada por correo electrónico o tienes alguna pregunta específica sobre estas recomendaciones?
"""
        return summary


# Instancia global del servicio
questionnaire_service = QuestionnaireService()
