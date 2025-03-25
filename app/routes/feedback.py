# app/routes/feedback.py
from fastapi import APIRouter, HTTPException
import logging

from app.models.feedback import Feedback
from app.services.feedback_service import feedback_service
from app.services.storage_service import storage_service

router = APIRouter()
logger = logging.getLogger("hydrous")


@router.post("/submit")
async def submit_feedback(feedback: Feedback):
    """Envía retroalimentación sobre una respuesta específica"""
    try:
        # Verificar que la conversación existe
        conversation = await storage_service.get_conversation(feedback.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Verificar que el mensaje existe
        message_exists = any(
            msg.id == feedback.message_id for msg in conversation.messages
        )
        if not message_exists:
            raise HTTPException(status_code=404, detail="Mensaje no encontrado")

        # Guardar retroalimentación
        success = await feedback_service.save_feedback(feedback)
        if not success:
            raise HTTPException(
                status_code=500, detail="Error al guardar la retroalimentación"
            )

        return {
            "status": "success",
            "message": "Retroalimentación recibida correctamente",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al procesar retroalimentación: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error al procesar la retroalimentación"
        )


@router.get("/stats")
async def get_feedback_stats():
    """Obtiene estadísticas de retroalimentación"""
    try:
        average_rating = await feedback_service.get_average_rating()
        return {
            "average_rating": average_rating,
            "count": int(average_rating > 0),  # Si hay al menos una calificación
        }
    except Exception as e:
        logger.error(f"Error al obtener estadísticas de retroalimentación: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al obtener estadísticas")
