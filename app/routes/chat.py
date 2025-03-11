from fastapi import APIRouter, HTTPException, Depends, Body
import logging
from typing import Dict, Any, List

from app.models.conversation import (
    Conversation,
    ConversationCreate,
    ConversationResponse,
)
from app.models.message import Message, MessageCreate, MessageResponse
from app.services.storage_service import storage_service
from app.services.ai_service import ai_service

logger = logging.getLogger("hydrous-backend")

router = APIRouter()


@router.post("/start", response_model=ConversationResponse)
async def start_conversation(data: ConversationCreate = Body(default={})):
    """Inicia una nueva conversación"""
    try:
        # Crear nueva conversación
        conversation = await storage_service.create_conversation(data.metadata)

        # Añadir mensaje inicial del bot (bienvenida)
        welcome_message = Message.assistant(
            "¡Hola! Soy el asistente virtual de Hydrous especializado en soluciones de reciclaje de agua. "
            "¿En qué puedo ayudarte hoy? Puedes preguntarme sobre nuestros sistemas de filtración, "
            "tratamiento de aguas grises, captación de agua de lluvia u otros servicios."
        )
        conversation.add_message(welcome_message)

        return ConversationResponse(
            id=conversation.id,
            created_at=conversation.created_at,
            messages=[
                welcome_message
            ],  # Solo devolvemos mensajes visibles, no el prompt del sistema
        )
    except Exception as e:
        logger.error(f"Error al iniciar conversación: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al iniciar la conversación")


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str):
    """Obtiene una conversación existente por su ID"""
    conversation = await storage_service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    # Filtrar mensajes del sistema para la respuesta
    visible_messages = [msg for msg in conversation.messages if msg.role != "system"]

    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=visible_messages,
    )


@router.post("/message", response_model=MessageResponse)
async def send_message(data: MessageCreate):
    """Procesa un mensaje del usuario y genera una respuesta"""
    try:
        # Validar que la conversación existe
        conversation = await storage_service.get_conversation(data.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Crear y añadir mensaje del usuario
        user_message = Message.user(data.message, data.metadata)
        await storage_service.add_message_to_conversation(
            data.conversation_id, user_message
        )

        # Preparar historial para el modelo de IA (incluyendo prompt del sistema)
        messages_for_ai = [
            {"role": msg.role, "content": msg.content} for msg in conversation.messages
        ]

        # Añadir el nuevo mensaje del usuario
        messages_for_ai.append({"role": "user", "content": data.message})

        # Generar respuesta con el modelo de IA
        ai_response = await ai_service.generate_response(messages_for_ai)

        # Crear y añadir mensaje del asistente
        assistant_message = Message.assistant(ai_response)
        await storage_service.add_message_to_conversation(
            data.conversation_id, assistant_message
        )

        return MessageResponse(
            id=assistant_message.id,
            conversation_id=data.conversation_id,
            message=ai_response,
            created_at=assistant_message.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al procesar mensaje: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al procesar el mensaje")
