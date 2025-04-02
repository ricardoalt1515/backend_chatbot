# app/models/chat.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class MessageCreate(BaseModel):
    # Admitir múltiples formatos para compatibilidad con frontend existente
    response_id: Optional[str] = None
    conversation_id: Optional[str] = None  # Para compatibilidad con frontend
    thread_id: Optional[str] = None  # Para compatibilidad con frontend
    message: str


class MessageResponse(BaseModel):
    id: str
    content: str
    created_at: datetime = Field(default_factory=datetime.now)
