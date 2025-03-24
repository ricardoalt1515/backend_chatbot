from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime
import uuid


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # "system", "user", "assistant"
    content: str
    created_at: datetime = Field(default_factory=datetime.now)

    @classmethod
    def system(cls, content: str) -> "Message":
        """Crea un mensaje de sistema"""
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "Message":
        """Crea un mensaje de usuario"""
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str) -> "Message":
        """Crea un mensaje del asistente"""
        return cls(role="assistant", content=content)


class MessageCreate(BaseModel):
    conversation_id: str
    message: str
    metadata: Optional[Dict[str, Any]] = {}


# Añadimos esta clase que faltaba
class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    message: str
    created_at: datetime
