from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import logging
import os
from datetime import datetime

from app.models.conversation import Conversation, ConversationResponse
from app.models.message import Message, MessageCreate
from app.services.storage_service import storage_service
from app.services.ai_service import ai_service
from app.services.pdf_service import pdf_service

logger = logging.getLogger("hydrous")

router = APIRouter()


@router.post("/start", response_model=ConversationResponse)
async def start_conversation():
    """Inicia una nueva conversación"""
    try:
        # Crear nueva conversación
        conversation = await storage_service.create_conversation()

        # Añadir mensaje inicial del asistente
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
        logger.error(f"Error al iniciar conversación: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al iniciar la conversación")


@router.post("/message")
async def send_message(data: MessageCreate, background_tasks: BackgroundTasks):
    """Procesa un mensaje del usuario y genera una respuesta"""
    try:
        # Obtener conversación
        conversation = await storage_service.get_conversation(data.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Añadir mensaje del usuario
        user_message = Message.user(data.message)
        await storage_service.add_message_to_conversation(
            data.conversation_id, user_message
        )

        # Detectar si es una solicitud para generar PDF
        if conversation.metadata.get("has_proposal", False) and _is_pdf_request(
            data.message
        ):
            # Generar enlace para descargar PDF
            download_url = f"/api/chat/{conversation.id}/download-pdf"
            pdf_message = f"""
# 📄 Propuesta Lista para Descargar

He preparado tu propuesta personalizada basada en la información proporcionada. Puedes descargarla usando el siguiente enlace:

## [👉 DESCARGAR PROPUESTA EN PDF]({download_url})

Este documento incluye:
- Análisis de tus necesidades específicas
- Solución tecnológica recomendada
- Estimación de costos y retorno de inversión
- Pasos siguientes recomendados

¿Necesitas alguna aclaración sobre la propuesta o tienes alguna otra pregunta?
"""
            # Añadir mensaje del asistente
            assistant_message = Message.assistant(pdf_message)
            await storage_service.add_message_to_conversation(
                data.conversation_id, assistant_message
            )

            # Generar PDF en segundo plano
            background_tasks.add_task(
                pdf_service.generate_pdf_from_conversation, conversation
            )

            return {
                "id": assistant_message.id,
                "conversation_id": data.conversation_id,
                "message": pdf_message,
                "created_at": assistant_message.created_at,
            }

        # Generar respuesta a través del servicio AI
        ai_response = await ai_service.handle_conversation(conversation, data.message)

        # Crear mensaje del asistente
        assistant_message = Message.assistant(ai_response)
        await storage_service.add_message_to_conversation(
            data.conversation_id, assistant_message
        )

        # Limpiar conversaciones antiguas en segundo plano
        background_tasks.add_task(storage_service.cleanup_old_conversations)

        return {
            "id": assistant_message.id,
            "conversation_id": data.conversation_id,
            "message": ai_response,
            "created_at": assistant_message.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al procesar mensaje: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al procesar el mensaje")


@router.get("/{conversation_id}/download-pdf")
async def download_pdf(conversation_id: str):
    """Descarga la propuesta en formato PDF"""
    try:
        # Verificar conversación
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        if not conversation.metadata.get("has_proposal", False):
            raise HTTPException(
                status_code=400,
                detail="No hay propuesta disponible para esta conversación",
            )

        # Generar el PDF si aún no existe
        pdf_path = pdf_service.get_pdf_path(conversation_id)
        if not pdf_path or not os.path.exists(pdf_path):
            pdf_path = await pdf_service.generate_pdf_from_conversation(conversation)

        if not pdf_path:
            raise HTTPException(status_code=500, detail="Error al generar el PDF")

        # Extraer nombre del cliente de la conversación para el nombre del archivo
        client_name = "Cliente"
        for msg in conversation.messages:
            if msg.role == "user" and len(msg.content) < 100:
                # Buscar un posible nombre de empresa en el primer mensaje corto
                client_name = msg.content.split()[0]
                break

        return FileResponse(
            path=pdf_path,
            filename=f"Propuesta_Hydrous_{client_name}.pdf",
            media_type="application/pdf",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al descargar PDF: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al generar el PDF")


def _is_pdf_request(message: str) -> bool:
    """Determina si el mensaje es una solicitud de PDF"""
    message = message.lower()
    keywords = ["pdf", "descargar", "documento", "propuesta", "archivo"]
    return any(kw in message for kw in keywords)
