# app/models/conversation.py
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from datetime import datetime
import uuid

from app.models.message import Message
from app.models.questionnaire_state import QuestionnaireState


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    messages: List[Message] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    questionnaire_state: QuestionnaireState = Field(
        default_factory=QuestionnaireState
    )  # Nuevo campo

    def add_message(self, message: Message) -> None:
        """Añade un mensaje a la conversación"""
        self.messages.append(message)
        self.updated_at = datetime.now()

    def get_current_question(
        self, questionnaire_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Obtiene la pregunta actual basada en el estado del cuestionario"""
        if not self.questionnaire_state.sector:
            return {
                "id": "sector_selection",
                "text": "¿En qué sector se encuentra tu empresa?",
            }

        if not self.questionnaire_state.subsector:
            return {
                "id": "subsector_selection",
                "text": f"¿Qué tipo de {self.questionnaire_state.sector} es?",
            }

        # Obtener las preguntas para el sector/subsector específico
        question_key = (
            f"{self.questionnaire_state.sector}_{self.questionnaire_state.subsector}"
        )
        questions = questionnaire_data.get("questions", {}).get(question_key, [])

        if not questions or self.questionnaire_state.current_question_index >= len(
            questions
        ):
            return None  # No hay más preguntas

        return questions[self.questionnaire_state.current_question_index]

    def update_questionnaire_state(
        self, user_message: str, questionnaire_data: Dict[str, Any]
    ) -> None:
        """Actualiza el estado del cuestionario basado en el mensaje del usuario"""
        current_question = self.get_current_question(questionnaire_data)

        if not current_question:
            return

        # Actualizar la respuesta en el estado
        self.questionnaire_state.update_answer(current_question["id"], user_message)
        self.questionnaire_state.mark_question_presented(current_question["id"])

        # Avanzar a la siguiente pregunta
        self.questionnaire_state.set_next_question()


class ConversationResponse(BaseModel):
    id: str
    created_at: datetime
    messages: List[Message]
