from fastapi import APIRouter, HTTPException, Depends, Body, BackgroundTasks, Response
from fastapi.responses import FileResponse
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
from app.config import settings

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

        # Detectar si es una solicitud para generar PDF
        pdf_keywords = [
            "pdf",
            "descargar",
            "propuesta",
            "documento",
            "guardar",
            "archivo",
        ]
        pdf_requested = any(keyword in data.message.lower() for keyword in pdf_keywords)

        # Si se solicita PDF y el cuestionario está completo, generar PDF
        if pdf_requested and conversation.is_questionnaire_completed():
            # Generar y verificar propuesta
            proposal = questionnaire_service.generate_proposal(conversation)

            # Informar al usuario que puede descargar el PDF
            download_url = f"/api/chat/{conversation.id}/download-proposal-pdf"
            pdf_message = (
                "He preparado tu propuesta personalizada. Puedes descargarla usando el siguiente enlace:\n\n"
                f"[DESCARGAR PROPUESTA EN PDF] ({download_url})\n\n"
                "Este enlace te permitira guardar la propuesta en tu dispositivo para que puedas revisarla"
                "cuando lo necesites o compartirla con tu equipo. ¿Necesitas algo más?"
            )

            # añadir mensaje del asistente
            assistant_message = Message.assistant(pdf_message)
            await storage_service.add_message_to_conversation(
                data.conversation_id, assistant_message
            )

            # Generar el PDF en segundo plano para tenerlo listo cuadno se solicite
            background_tasks.add_task(
                questionnaire_service.generate_proposal_pdf, proposal
            )

            return MessageResponse(
                id=assistant_message.id,
                conversation_id=data.conversation_id,
                message=pdf_message,
                created_at=assistant_message.created_at,
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


@router.get("/{conversation_id}/download-proposal-pdf")
async def download_proposal_pdf(conversation_id: str):
    """Descarga la propuesta en formato PDF o HTML segun disponibilidad"""
    try:
        # Obtener la conversación
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Verificar que el cuestionario está completo
        if not conversation.is_questionnaire_completed():
            raise HTTPException(
                status_code=400,
                detail="El cuestionario no está completo, no se puede generar la propuesta",
            )

        # Generar la propuesta y el PDF/HTML
        proposal = questionnaire_service.generate_proposal(conversation)
        file_path = questionnaire_service.generate_proposal_pdf(proposal)

        if not file_path or not os.path.exists(file_path):
            # Si falla la generacion, generar una respuesta HTML simple
            html_content = f"""
            <html>
                <head>
                    <title>Propuesta Hydrous</title>
                </head>
                <body>
                    <h1>Error al generar documento</h1>
                    <p>No se pudo generar el documento de propuesta. Por favor intente nuevamente o contacte con soporte.</p>
                </body>
            </html>
            """
            response.headers["Content-Type"] = "text/html"
            return html_content

        # Obtener el nombre del clietne para el nombre del archivo
        client_name = proposal["client_info"]["name"].replace(" ", "_")

        # Determinar tipo de archivo basado en la extension
        is_pdf = file_path.lower().endswith(".pdf")
        if is_pdf:
            filename = f"Propuesta_Hydrous_{client_name}.pdf"
            media_type = "application/pdf"
        else:
            filename = f"Propuesta_Hydrous_{client_name}.html"
            media_type = "text/html"

        # Devolver el archivo
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=media_type,
            background=BackgroundTasks(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al descargar propuesta: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error al generar el documento {str(e)}"
        )


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


@router.post("/{conversation_id}/questionnaire/answer")
async def answer_questionnaire(conversation_id: str, data: Dict[str, Any] = Body(...)):
    """Procesa una respuesta del cuestionario y devuelve la siguiente pregunta"""
    try:
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Verificar si el cuestionario está activo
        if not conversation.is_questionnaire_active():
            raise HTTPException(
                status_code=400, detail="El cuestionario no está activo"
            )

        # Verificar que se recibió una respuesta
        if "answer" not in data:
            raise HTTPException(
                status_code=400, detail="No se ha proporcionado una respuesta"
            )

        # Verificar que hay una pregunta actual
        if not conversation.questionnaire_state.current_question_id:
            raise HTTPException(status_code=400, detail="No hay una pregunta actual")

        # Procesar la respuesta
        question_id = conversation.questionnaire_state.current_question_id
        answer = data["answer"]
        questionnaire_service.process_answer(conversation, question_id, answer)

        # Obtener siguiente pregunta
        next_question = questionnaire_service.get_next_question(
            conversation.questionnaire_state
        )

        if not next_question:
            # Si no hay siguiente pregunta, generar propuesta
            if not conversation.is_questionnaire_completed():
                conversation.complete_questionnaire()

            # Generar y formatear propuesta
            proposal = questionnaire_service.generate_proposal(conversation)
            summary = questionnaire_service.format_proposal_summary(proposal)

            # Añadir mensaje con la propuesta
            assistant_message = Message.assistant(summary)
            await storage_service.add_message_to_conversation(
                conversation_id, assistant_message
            )

            return {"completed": True, "message": summary}

        # Actualizar la pregunta actual
        conversation.questionnaire_state.current_question_id = next_question["id"]

        # Formatear la siguiente pregunta
        next_question_formatted = ai_service._format_question(next_question)

        # Añadir mensaje con la siguiente pregunta
        assistant_message = Message.assistant(next_question_formatted)
        await storage_service.add_message_to_conversation(
            conversation_id, assistant_message
        )

        return {
            "completed": False,
            "next_question": next_question,
            "message": next_question_formatted,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al procesar respuesta del cuestionario: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error al procesar respuesta del cuestionario"
        )


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
