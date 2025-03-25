# app/models/feedback.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class Feedback(BaseModel):
    """Modelo para almacenar retroalimentación sobre las respuestas"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    message_id: str
    rating: int  # 1-5 donde 5 es excelente
    comment: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
