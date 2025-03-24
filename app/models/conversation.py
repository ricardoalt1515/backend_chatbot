from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
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
        """Añade un mensaje a la conversación y actualiza la fecha"""
        self.messages.append(message)
        self.updated_at = datetime.now()

    def get_messages_for_llm(self) -> List[Dict[str, Any]]:
        """Obtiene los mensajes en formato para API LLM"""
        return [{"role": msg.role, "content": msg.content} for msg in self.messages]


class ConversationResponse(BaseModel):
    id: str
    created_at: datetime
    messages: List[Message]
