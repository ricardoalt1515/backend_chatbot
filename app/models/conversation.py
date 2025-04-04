# app/models/conversation.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Any, Optional
import uuid

from app.models.message import Message
from app.models.conversation_state import ConversationState  # Importar nuevo modelo


class Conversation(BaseModel):
    """Representa una conversación completa con su estado."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    messages: List[Message] = Field(default_factory=list)
    # Incluir el estado de la conversación
    state: ConversationState = Field(default_factory=ConversationState)
    # Metadatos para información adicional (ej: si la propuesta está lista, rutas de archivos)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def add_message(self, message: Message):
        """Añade un mensaje a la conversación."""
        self.messages.append(message)

    class Config:
        allow_mutation = True  # Necesario si modificas el objeto después de crearlo


# Modelo para la respuesta al iniciar o cargar una conversación
class ConversationResponse(BaseModel):
    id: str
    created_at: datetime
    messages: List[Message]
    state: Optional[ConversationState] = None  # Incluir estado en la respuesta
    metadata: Optional[Dict[str, Any]] = None  # Incluir metadatos
