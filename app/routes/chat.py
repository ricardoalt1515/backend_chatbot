# app/routes/chat.py
from fastapi import APIRouter, HTTPException
import logging

from app.models.chat import MessageCreate, MessageResponse
from app.services.openai_service import openai_service

router = APIRouter()
logger = logging.getLogger("hydrous")


@router.post("/start", response_model=MessageResponse)
async def start_conversation():
    """Inicia una nueva conversación"""
    try:
        # Crear nueva conversación
        response = await openai_service.start_conversation()

        return MessageResponse(
            id=response["id"],
            content=response["content"],
            created_at=response["created_at"],
        )
    except Exception as e:
        logger.error(f"Error al iniciar conversación: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error al iniciar la conversación: {str(e)}"
        )


@router.post("/message", response_model=MessageResponse)
async def send_message(data: MessageCreate):
    """Procesa un mensaje del usuario y genera una respuesta"""
    try:
        # Validar que tenemos un response_id
        if not data.response_id:
            raise HTTPException(
                status_code=400,
                detail="Se requiere response_id para continuar la conversación",
            )

        # Enviar mensaje y obtener respuesta
        response = await openai_service.send_message(
            response_id=data.response_id, message=data.message
        )

        # Verificar si contiene propuesta completa
        has_proposal = response.get("has_proposal", False)

        return MessageResponse(
            id=response["id"],
            content=response["content"],
            created_at=response["created_at"],
        )
    except Exception as e:
        logger.error(f"Error al procesar mensaje: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error al procesar el mensaje: {str(e)}"
        )
