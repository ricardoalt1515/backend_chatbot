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
    """Inicia una nueva conversación"""
    try:
        # Crear nueva conversación
        conversation = await storage_service.create_conversation()

        # Añadir mensaje de bienvenida
        welcome_message = Message.assistant(
            """
# 👋 ¡Bienvenido a Hydrous AI!

Soy el diseñador de soluciones de agua de Hydrous AI, tu asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales. Como herramienta de Hydrous, estoy aquí para guiarte paso a paso en la evaluación de las necesidades de agua de tu sitio, la exploración de posibles soluciones y la identificación de oportunidades de ahorro de costos, cumplimiento y sostenibilidad.

💡 *Las soluciones de reciclaje de agua pueden reducir el consumo de agua fresca hasta en un 70% en instalaciones industriales similares.*

**PREGUNTA: ¿Cuál es el nombre de tu empresa o proyecto y dónde se ubica?**

Por favor incluye:
- Nombre de tu empresa o proyecto
- Ubicación (ciudad, estado, país)

🌍 *Esta información es importante para evaluar la normativa local, la disponibilidad de agua, y posibles incentivos para reciclaje de agua en tu zona.*
"""
        )
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
            # Lógica de generación de PDF...
            pass

        # Generar respuesta usando el servicio simplificado de IA
        ai_response = await ai_service.handle_conversation(conversation, data.message)

        # Crear mensaje del asistente
        assistant_message = Message.assistant(ai_response)
        await storage_service.add_message_to_conversation(
            conversation_id, assistant_message
        )

        # Limpieza en segundo plano
        background_tasks.add_task(storage_service.cleanup_old_conversations)

        return {
            "id": assistant_message.id,
            "conversation_id": conversation_id,
            "message": ai_response,
            "created_at": assistant_message.created_at,
        }
    except Exception as e:
        logging.error(f"Error al procesar mensaje: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al procesar el mensaje")


# En app/routes/chat.py


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
