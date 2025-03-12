from fastapi import APIRouter, HTTPException, Depends, Body, BackgroundTasks
import logging
from typing import Dict, Any, List, Optional
import os
import time
from datetime import datetime

from app.models.conversation import (
    Conversation,
    ConversationCreate,
    ConversationResponse,
)
from app.models.message import Message, MessageCreate, MessageResponse
from app.services.storage_service import storage_service
from app.services.ai_service import ai_service
from app.services.questionnaire_service import questionnaire_service

logger = logging.getLogger("hydrous-backend")

router = APIRouter()


@router.post("/start", response_model=ConversationResponse)
async def start_conversation(
    data: ConversationCreate = Body(default=ConversationCreate()),
):
    """Inicia una nueva conversación"""
    try:
        # Crear nueva conversación - asegurarnos de que metadata existe y es un dict
        metadata = data.metadata if hasattr(data, "metadata") else {}
        conversation = await storage_service.create_conversation(metadata)

        # Añadir mensaje inicial del bot (bienvenida)
        welcome_message = Message.assistant(
            "¡Hola! Soy el asistente virtual de Hydrous especializado en soluciones de reciclaje de agua. "
            "¿En qué puedo ayudarte hoy? Puedes preguntarme sobre nuestros sistemas de filtración, "
            "tratamiento de aguas residuales, reutilización de agua y más. También puedo ayudarte "
            "a diseñar una solución personalizada para tu negocio completando un sencillo cuestionario."
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
async def send_message(data: MessageCreate, background_tasks: BackgroundTasks):
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

        # Usar el servicio actualizado para manejar el flujo de conversación
        # incluyendo el cuestionario si está activo
        ai_response = await ai_service.handle_conversation(conversation, data.message)

        # Crear y añadir mensaje del asistente
        assistant_message = Message.assistant(ai_response)
        await storage_service.add_message_to_conversation(
            data.conversation_id, assistant_message
        )

        # Programar limpieza de conversaciones antiguas como tarea en segundo plano
        background_tasks.add_task(storage_service.cleanup_old_conversations)

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


@router.get("/{conversation_id}/questionnaire/status")
async def get_questionnaire_status(conversation_id: str):
    """Obtiene el estado actual del cuestionario para una conversación"""
    try:
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        return {
            "active": conversation.is_questionnaire_active(),
            "completed": conversation.is_questionnaire_completed(),
            "sector": conversation.questionnaire_state.sector,
            "subsector": conversation.questionnaire_state.subsector,
            "current_question": conversation.questionnaire_state.current_question_id,
            "answers_count": len(conversation.questionnaire_state.answers),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener estado del cuestionario: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error al obtener estado del cuestionario"
        )


@router.post("/{conversation_id}/questionnaire/start")
async def start_questionnaire(conversation_id: str):
    """Inicia manualmente el proceso de cuestionario"""
    try:
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Verificar si ya está activo
        if conversation.is_questionnaire_active():
            return {"message": "El cuestionario ya está activo"}

        # Iniciar cuestionario
        conversation.start_questionnaire()

        # Obtener introducción y primera pregunta
        intro_text, explanation = questionnaire_service.get_introduction()
        next_question = questionnaire_service.get_next_question(
            conversation.questionnaire_state
        )

        # Crear mensaje con la introducción y primera pregunta
        message_text = f"{intro_text}\n\n{explanation}\n\n"
        if next_question:
            message_text += ai_service._format_question(next_question)
            conversation.questionnaire_state.current_question_id = next_question["id"]

        # Añadir mensaje del asistente
        assistant_message = Message.assistant(message_text)
        await storage_service.add_message_to_conversation(
            conversation_id, assistant_message
        )

        return {
            "message": "Cuestionario iniciado correctamente",
            "first_question": message_text,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al iniciar cuestionario: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al iniciar cuestionario")


@router.get("/{conversation_id}/proposal")
async def generate_proposal(conversation_id: str):
    """Genera una propuesta basada en las respuestas del cuestionario"""
    try:
        # Obtener la conversación
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Verificar si hay suficientes respuestas
        if len(conversation.questionnaire_state.answers) < 3:
            raise HTTPException(
                status_code=400,
                detail="No hay suficiente información para generar una propuesta",
            )

        # Generar propuesta
        proposal = questionnaire_service.generate_proposal(conversation)

        # Por ahora devolvemos los datos JSON, pero en el futuro podría generarse un PDF
        return proposal
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al generar propuesta: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al generar la propuesta")
