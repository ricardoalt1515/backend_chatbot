from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from app.models.message import Message


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    messages: List[Message] = []
    metadata: Dict[str, Any] = Field(default_factory=dict)

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


class ConversationCreate(BaseModel):
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ConversationResponse(BaseModel):
    id: str
    created_at: datetime
    messages: List[Message]
