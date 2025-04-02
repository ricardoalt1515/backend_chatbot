# app/routes/chat.py
from fastapi import APIRouter, HTTPException
import logging

from app.models.chat import MessageCreate, MessageResponse
from app.services.openai_service import openai_service

router = APIRouter()
logger = logging.getLogger("hydrous")


@router.post("/start")  # Elimina response_model para personalizar respuesta
async def start_conversation():
    """Inicia una nueva conversación"""
    try:
        # Crear nueva conversación
        response = await openai_service.start_conversation()

        # Formato compatible con frontend existente
        return {
            "id": response["id"],
            "conversation_id": response["id"],  # Para compatibilidad
            "thread_id": response["id"],  # Para compatibilidad
            "content": response["content"],
            "message": response["content"],  # Para compatibilidad
            "created_at": response["created_at"],
        }
    except Exception as e:
        logger.error(f"Error al iniciar conversación: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error al iniciar conversación: {str(e)}"
        )


@router.post("/message", response_model=MessageResponse)
async def send_message(data: MessageCreate):
    """Procesa un mensaje del usuario y genera una respuesta"""
    try:
        # Obtener el ID de respuesta, permitiendo múltiples formatos
        response_id = data.response_id or data.conversation_id or data.thread_id

        if not response_id:
            raise HTTPException(
                status_code=400,
                detail="Se requiere un ID (response_id, conversation_id o thread_id)",
            )

        # Enviar mensaje y obtener respuesta
        response = await openai_service.send_message(
            response_id=response_id, message=data.message
        )

        return MessageResponse(
            id=response["id"],
            content=response["content"],
            created_at=response["created_at"],
        )
    except Exception as e:
        logger.error(f"Error al procesar mensaje: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error al procesar mensaje: {str(e)}"
        )
