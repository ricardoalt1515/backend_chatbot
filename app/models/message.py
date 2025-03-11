from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str  # "system", "user", "assistant"
    content: str
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = {}

    @classmethod
    def system(cls, content: str) -> "Message":
        """Crea un mensaje de sistema"""
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str, metadata: Dict[str, Any] = None) -> "Message":
        """Crea un mensaje de usuario"""
        return cls(role="user", content=content, metadata=metadata or {})

    @classmethod
    def assistant(cls, content: str, metadata: Dict[str, Any] = None) -> "Message":
        """Crea un mensaje del asistente"""
        return cls(role="assistant", content=content, metadata=metadata or {})


class MessageCreate(BaseModel):
    conversation_id: str
    message: str
    metadata: Optional[Dict[str, Any]] = {}


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    message: str
    created_at: datetime
