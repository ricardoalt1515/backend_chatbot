from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.core.openai_service import (
    start_conversation,
    send_message,
    get_conversation_history,
)

router = APIRouter()


class MessageRequest(BaseModel):
    conversation_id: str
    message: str


class ConversationResponse(BaseModel):
    id: str
    message: str


@router.post("/chat/start", response_model=ConversationResponse)
async def start_chat():
    """
    Inicia una nueva conversación y devuelve el primer mensaje del asistente.
    """
    try:
        result = start_conversation()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/message", response_model=ConversationResponse)
async def chat_message(request: MessageRequest):
    """
    Envía un mensaje a una conversación existente.
    """
    try:
        result = send_message(request.conversation_id, request.message)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat/{conversation_id}")
async def get_conversation(conversation_id: str):
    """
    Verifica si una conversación existe y devuelve su estado.
    """
    try:
        # Aquí se podría implementar una verificación real con la API de OpenAI
        # Por simplicidad, asumimos que la conversación existe si no hay error
        return {"status": "active", "id": conversation_id}
    except Exception as e:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
