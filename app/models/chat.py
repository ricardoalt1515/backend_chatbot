# app/models/chat.py
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class MessageCreate(BaseModel):
    response_id: Optional[str] = None
    message: str


class MessageResponse(BaseModel):
    id: str
    content: str
    created_at: datetime = Field(default_factory=datetime.now)
