# app/routes/chat.py
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
import logging
import os
import json
from datetime import datetime

from app.services.responses_service import responses_service
from app.config import settings

router = APIRouter()
logger = logging.getLogger("hydrous")


async def initialize_service():
    """Middleware para asegurar que el servicio esté inicializado"""
    if responses_service.vector_store_id is None:
        await responses_service.initialize()
    return responses_service


@router.post("/start")
async def start_conversation(service: ResponsesService = Depends(initialize_service)):
    """Inicia una nueva conversación"""
    try:
        # Iniciar conversación con el servicio
        response = await service.start_conversation()

        return response
    except Exception as e:
        logger.error(f"Error al iniciar conversación: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al iniciar la conversación")


@router.post("/message")
async def send_message(
    data: dict,
    background_tasks: BackgroundTasks = None,
    service: ResponsesService = Depends(initialize_service),
):
    """Procesa un mensaje del usuario y genera una respuesta"""
    try:
        # Validar datos
        if "conversation_id" not in data or "message" not in data:
            raise HTTPException(status_code=400, detail="Datos incompletos")

        # Procesar mensaje
        response = await service.process_message(
            response_id=data["conversation_id"], message=data["message"]
        )

        return response
    except Exception as e:
        logger.error(f"Error al procesar mensaje: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al procesar el mensaje")


@router.get("/{conversation_id}/download-pdf")
async def download_pdf(conversation_id: str):
    """Descarga la propuesta en formato PDF"""
    # Este endpoint corresponde a `/api/pdf/{conversationId}/download`
    # que espera el frontend, pero lo implementamos aquí para simplicidad
    try:
        # Verificar si existe un archivo PDF para esta conversación
        pdf_path = os.path.join(settings.UPLOAD_DIR, f"proposal_{conversation_id}.pdf")

        # Si no existe, generar un PDF simple
        if not os.path.exists(pdf_path):
            # Aquí iría la lógica de generación de PDF
            # Para simplificar, solo regresamos un error
            raise HTTPException(status_code=404, detail="Propuesta no encontrada")

        # Retornar archivo
        return FileResponse(
            path=pdf_path,
            filename=f"Propuesta_Hydrous_{conversation_id}.pdf",
            media_type="application/pdf",
        )
    except Exception as e:
        logger.error(f"Error al descargar propuesta: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al generar la propuesta")
