# app/models/conversation.py (simplificado)
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from datetime import datetime
import uuid

from app.models.message import Message


class QuestionnaireState(BaseModel):
    """Estado simplificado del cuestionario"""

    sector: str = None
    subsector: str = None
    answers: Dict[str, Any] = Field(default_factory=dict)


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    messages: List[Message] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    questionnaire_state: QuestionnaireState = Field(default_factory=QuestionnaireState)

    def add_message(self, message: Message) -> None:
        """Añade un mensaje a la conversación"""
        self.messages.append(message)
        self.updated_at = datetime.now()


class ConversationResponse(BaseModel):
    id: str
    created_at: datetime
    messages: List[Message]
