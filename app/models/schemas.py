from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class ChatRequest(BaseModel):
    thread_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    thread_id: str
    response: str


class AssistantCreate(BaseModel):
    name: str = "Hydrous Water Solutions Assistant"
    instructions: str
    file_ids: Optional[List[str]] = None


class AssistantResponse(BaseModel):
    id: str
    name: str
    created_at: int


class FileUploadResponse(BaseModel):
    file_id: str
    filename: str


class ThreadCreate(BaseModel):
    metadata: Optional[Dict[str, Any]] = None


class ThreadResponse(BaseModel):
    id: str


class StatusResponse(BaseModel):
    status: str
    assistant_id: Optional[str] = None
    message: str
