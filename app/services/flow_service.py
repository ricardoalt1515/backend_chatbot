# app/services/conversation_flow_service.py
from typing import Dict, Any, Optional, List
import logging
from app.models.conversation import Conversation

logger = logging.getLogger("hydrous")


class ConversationFlowService:
    """Servicio para manejar el flujo de la conversación según el cuestionario estructurado"""

    def __init__(self, questionnaire_data: Dict[str, Any]):
        """Inicializa el servicio con los datos del cuestionario"""
        self.questionnaire_data = questionnaire_data

    def get_next_question(self, conversation: Conversation) -> Optional[Dict[str, Any]]:
        """Determina la siguiente pregunta basada en el estado actual"""
        return conversation.get_current_question(self.questionnaire_data)

    def is_questionnaire_complete(self, conversation: Conversation) -> bool:
        """Determina si se ha completado el cuestionario basado en preguntas obligatorias"""
        # Verificar si se ha definido sector/subsector
        if (
            not conversation.questionnaire_state.sector
            or not conversation.questionnaire_state.subsector
        ):
            return False

        # Obtener lista de preguntas para este sector/subsector
        question_key = f"{conversation.questionnaire_state.sector}_{conversation.questionnaire_state.subsector}"
        questions = self.questionnaire_data.get("questions", {}).get(question_key, [])

        # Filtrar preguntas obligatorias
        required_questions = [q["id"] for q in questions if q.get("required", True)]

        # Verificar si todas las preguntas obligatorias tienen respuesta
        for q_id in required_questions:
            if q_id not in conversation.questionnaire_state.answers:
                return False

        # Verificar si tenemos la información crítica mínima
        critical_entities = [
            "company_name",
            "location",
            "water_consumption",
            "water_cost",
        ]
        for entity in critical_entities:
            if entity not in conversation.questionnaire_state.key_entities:
                # Buscar alternativas en las respuestas para estas entidades críticas
                if not self._find_alternative_entity(conversation, entity):
                    return False

        return True

    def _find_alternative_entity(self, conversation: Conversation, entity: str) -> bool:
        """Busca alternativas para entidades críticas en las respuestas"""
        # Mapeo de entidades a posibles preguntas que contienen esa información
        entity_question_map = {
            "company_name": ["nombre_empresa"],
            "location": ["ubicacion"],
            "water_consumption": ["cantidad_agua_consumida"],
            "water_cost": ["costo_agua"],
        }

        if entity in entity_question_map:
            for question_id in entity_question_map[entity]:
                if question_id in conversation.questionnaire_state.answers:
                    return True

        return False

    def get_context_summary(self, conversation: Conversation) -> str:
        """Genera un resumen del contexto actual para el prompt"""
        return conversation.questionnaire_state.get_context_summary()

    def _find_question_text(self, question_id: str) -> Optional[str]:
        """Busca el texto de una pregunta dado su ID"""
        # Buscar en todas las secciones de preguntas
        for sector in self.questionnaire_data.get("sectors", []):
            for subsector in self.questionnaire_data.get("subsectors", {}).get(
                sector, []
            ):
                question_key = f"{sector}_{subsector}"
                questions = self.questionnaire_data.get("questions", {}).get(
                    question_key, []
                )

                for question in questions:
                    if question.get("id") == question_id:
                        return question.get("text")

        return None

    def get_relevant_facts(self, conversation: Conversation) -> List[str]:
        """Obtiene datos educativos relevantes para el sector y subsector del usuario"""
        facts = []

        # Si no hay sector definido, devolver facts generales
        if not conversation.questionnaire_state.sector:
            return [
                "El tratamiento de aguas residuales puede reducir significativamente los costos operativos.",
                "Las empresas que implementan soluciones de tratamiento de agua pueden reducir su huella hídrica hasta en un 70%.",
            ]

        # Buscar facts específicos para el sector/subsector
        sector = conversation.questionnaire_state.sector
        subsector = conversation.questionnaire_state.subsector or "General"

        # Formar la clave de búsqueda
        fact_key = f"{sector}_{subsector}"

        # Buscar en el diccionario de facts
        if "facts" in self.questionnaire_data:
            if fact_key in self.questionnaire_data["facts"]:
                facts = self.questionnaire_data["facts"][fact_key]
            elif sector in self.questionnaire_data["facts"]:
                facts = self.questionnaire_data["facts"][sector]

        # Si no se encuentran hechos específicos, devolver algunos genéricos
        if not facts:
            if sector == "Industrial":
                facts = [
                    "Las industrias pueden reducir su consumo de agua hasta en un 60% con sistemas de reutilización adecuados.",
                    "El tratamiento adecuado de aguas residuales industriales puede generar ahorros significativos en tarifas de descarga.",
                ]
            elif sector == "Comercial":
                facts = [
                    "Los edificios comerciales pueden reducir su consumo de agua hasta en un 40% implementando soluciones de reutilización.",
                    "Invertir en sistemas de tratamiento de agua puede mejorar la imagen de sostenibilidad de su empresa.",
                ]
            else:
                facts = [
                    "Los sistemas de tratamiento de agua modernos pueden recuperar hasta el 80% del agua utilizada para su reutilización.",
                    "La implementación de tecnologías de tratamiento de agua tiene períodos típicos de retorno de inversión de 2-4 años.",
                ]

        return facts[:2]  # Devolver solo los 2 primeros para no sobrecargar el contexto
