# app/models/questionnaire_state.py
from pydantic import BaseModel
from typing import Dict, Any, List, Optional


class QuestionnaireState(BaseModel):
    """Modelo para mantener el estado del cuestionario del usuario"""

    # Sector y subsector seleccionados
    sector: Optional[str] = None
    subsector: Optional[str] = None

    # Índice de la pregunta actual
    current_question_index: int = 0

    # Respuestas almacenadas
    answers: Dict[str, Any] = {}

    # Preguntas que se han presentado
    presented_questions: List[str] = []

    # Si el cuestionario está completo
    is_complete: bool = False
