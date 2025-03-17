from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from app.models.message import Message


class QuestionnaireState(BaseModel):
    """Estado del cuestionario dentro de una conversación"""

    def __init__(self):
        self.active: bool = False
        self.completed: bool = False
        self.sector: Optional[str] = None
        self.subsector: Optional[str] = None
        self.current_question_id: Optional[str] = None
        self.answers: Dict[str, Any] = {}
        self.section_intros_shown: Dict[str, bool] = {}


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    messages: List[Message] = []
    metadata: Dict[str, Any] = Field(default_factory=dict)
    questionnaire_state: QuestionnaireState = Field(default_factory=QuestionnaireState)

    def add_message(self, message: Message) -> None:
        """Añade un mensaje a la conversación y actualiza la fecha de actualización"""
        self.messages.append(message)
        self.updated_at = datetime.now()

    def get_history_as_list(self) -> List[Dict[str, Any]]:
        """Devuelve el historial de mensajes en formato lista para las APIs de IA"""
        return [msg.model_dump() for msg in self.messages]

    def get_history_as_string(self) -> str:
        """Devuelve el historial de mensajes en formato texto para contexto"""
        history = ""
        for msg in self.messages:
            if msg.role in ["user", "assistant"]:
                history += f"{msg.role.capitalize()}: {msg.content}\n\n"
        return history.strip()

    def start_questionnaire(self, sector: Optional[str] = None) -> None:
        """Inicia el proceso de cuestionario"""
        self.questionnaire_state.active = True
        if sector:
            self.questionnaire_state.sector = sector
        self.updated_at = datetime.now()

    def set_sector(self, sector: str) -> None:
        """Establece el sector para el cuestionario"""
        self.questionnaire_state.sector = sector
        self.updated_at = datetime.now()

    def set_subsector(self, subsector: str) -> None:
        """Establece el subsector para el cuestionario"""
        self.questionnaire_state.subsector = subsector
        self.updated_at = datetime.now()

    def add_answer(self, question_id: str, answer: Any) -> None:
        """Añade una respuesta al cuestionario"""
        self.questionnaire_state.answers[question_id] = answer
        self.updated_at = datetime.now()

    def complete_questionnaire(self) -> None:
        """Marca el cuestionario como completado"""
        self.questionnaire_state.completed = True
        self.questionnaire_state.active = False
        self.updated_at = datetime.now()

    def is_questionnaire_active(self) -> bool:
        """Verifica si el cuestionario está activo"""
        return self.questionnaire_state.active

    def is_questionnaire_completed(self) -> bool:
        """Verifica si el cuestionario está completado"""
        return self.questionnaire_state.completed


class ConversationCreate(BaseModel):
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ConversationResponse(BaseModel):
    id: str
    created_at: datetime
    messages: List[Message]
