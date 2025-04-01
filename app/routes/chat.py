# app/routes/chat.py
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import logging
import os

from app.models.conversation import ConversationResponse
from app.models.message import Message, MessageCreate
from app.services.storage_service import storage_service
from app.services.ai_service import ai_service
from app.services.pdf_service import pdf_service

router = APIRouter()


@router.post("/start", response_model=ConversationResponse)
async def start_conversation():
    """Inicia una nueva conversación usando la API Responses"""
    try:
        # Crear nueva conversación
        conversation = await storage_service.create_conversation()

        # Obtener mensaje de bienvenida inicial
        ai_response = await ai_service.handle_conversation(conversation)

        # Añadir mensaje de bienvenida
        welcome_message = Message.assistant(ai_response)
        conversation.add_message(welcome_message)

        return ConversationResponse(
            id=conversation.id,
            created_at=conversation.created_at,
            messages=[welcome_message],
        )
    except Exception as e:
        logging.error(f"Error al iniciar conversación: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al iniciar la conversación")


@router.post("/message")
async def send_message(data: MessageCreate, background_tasks: BackgroundTasks):
    """Procesa un mensaje del usuario y genera una respuesta"""
    try:
        # Obtener conversación
        conversation_id = data.conversation_id
        conversation = await storage_service.get_conversation(conversation_id)

        if not conversation:
            # Crear nueva conversación si no existe
            conversation = await storage_service.create_conversation()
            logging.info(f"Nueva conversación creada con ID: {conversation.id}")

            return {
                "error": "Conversación original no encontrada",
                "new_conversation_created": True,
                "conversation_id": conversation.id,
                "message": "Se creó una nueva conversación. Por favor, intenta de nuevo.",
            }

        # Añadir mensaje del usuario
        user_message = Message.user(data.message)
        await storage_service.add_message_to_conversation(conversation_id, user_message)

        # Verificar si es una solicitud de PDF
        if _is_pdf_request(data.message) and conversation.metadata.get(
            "has_proposal", False
        ):
            # Generar PDF...
            pass

        # Generar respuesta usando la API Responses
        ai_response = await ai_service.handle_conversation(conversation, data.message)

        # Crear mensaje del asistente
        assistant_message = Message.assistant(ai_response)
        await storage_service.add_message_to_conversation(
            conversation_id, assistant_message
        )

        # Verificar si hay propuesta
        has_proposal = (
            "has_proposal" in conversation.metadata
            and conversation.metadata["has_proposal"]
        )

        return {
            "id": assistant_message.id,
            "conversation_id": conversation_id,
            "message": ai_response,
            "created_at": assistant_message.created_at,
            "has_proposal": has_proposal,
        }
    except Exception as e:
        logging.error(f"Error al procesar mensaje: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al procesar el mensaje")


@router.get("/{conversation_id}/download-pdf")
async def download_pdf(conversation_id: str):
    """Descarga la propuesta en formato PDF"""
    try:
        # Verificar que la conversación existe
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Si ya tenemos un PDF generado, usamos esa ruta
        if conversation.metadata.get("pdf_path") and os.path.exists(
            conversation.metadata["pdf_path"]
        ):
            pdf_path = conversation.metadata["pdf_path"]
        else:
            # Generar PDF
            pdf_path = await pdf_service.generate_pdf(conversation)

        if not pdf_path:
            raise HTTPException(status_code=500, detail="Error al generar el PDF")

        # Preparar nombre para el archivo
        client_name = "Cliente"
        if conversation.questionnaire_state.key_entities.get("company_name"):
            client_name = conversation.questionnaire_state.key_entities["company_name"]

        # Determinar si es PDF o HTML
        is_pdf = pdf_path.endswith(".pdf")
        filename = f"Propuesta_Hydrous_{client_name}.{'pdf' if is_pdf else 'html'}"

        return FileResponse(
            path=pdf_path,
            filename=filename,
            media_type="application/pdf" if is_pdf else "text/html",
        )
    except Exception as e:
        logger.error(f"Error al descargar PDF: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al generar el PDF")


def _is_pdf_request(message: str) -> bool:
    """Determina si el mensaje es una solicitud de PDF"""
    message = message.lower()
    pdf_keywords = ["pdf", "descargar", "documento", "propuesta", "bajar", "archivo"]
    return any(keyword in message for keyword in pdf_keywords)
