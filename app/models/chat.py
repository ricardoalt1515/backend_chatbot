# app/models/chat.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


class MessageCreate(BaseModel):
    response_id: Optional[str] = None
    message: str
    files: Optional[List[str]] = None


class MessageResponse(BaseModel):
    id: str
    content: str
    created_at: datetime = Field(default_factory=datetime.now)


class ProposalRequest(BaseModel):
    response_id: str


class ProposalResponse(BaseModel):
    id: str
    content: str
    download_url: str
    created_at: datetime = Field(default_factory=datetime.now)
