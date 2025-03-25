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

    # Documentos subidos y su relación con las preguntas
    documents: Dict[str, List[str]] = {}

    # Si el cuestionario está completo
    is_complete: bool = False

    def update_answer(self, question_id: str, answer: Any) -> None:
        """Actualiza la respuesta a una pregunta específica"""
        self.answers[question_id] = answer

    def set_next_question(self, question_index: int = None) -> None:
        """Establece la siguiente pregunta a presentar"""
        if question_index is not None:
            self.current_question_index = question_index
        else:
            self.current_question_index += 1

    def mark_question_presented(self, question_id: str) -> None:
        """Marca una pregunta como presentada al usuario"""
        if question_id not in self.presented_questions:
            self.presented_questions.append(question_id)

    def add_document_reference(self, question_id: str, document_id: str) -> None:
        """Asocia un documento subido con una pregunta específica"""
        if question_id not in self.documents:
            self.documents[question_id] = []

        if document_id not in self.documents[question_id]:
            self.documents[question_id].append(document_id)

    def complete_questionnaire(self) -> None:
        """Marca el cuestionario como completado"""
        self.is_complete = True
