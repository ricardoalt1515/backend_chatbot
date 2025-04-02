# app/routes/chat.py
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import logging
import os
import json

from app.models.chat import (
    MessageCreate,
    MessageResponse,
    ProposalRequest,
    ProposalResponse,
)
from app.services.openai_service import openai_service
from app.services.pdf_service import pdf_service
from app.config import settings

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
        raise HTTPException(status_code=500, detail="Error al iniciar la conversación")


@router.post("/message")
async def send_message(data: MessageCreate, background_tasks: BackgroundTasks):
    """Procesa un mensaje del usuario y genera una respuesta"""
    try:
        # Enviar mensaje y obtener respuesta
        response = await openai_service.send_message(
            response_id=data.response_id, message=data.message, files=data.files
        )

        # Verificar si contiene propuesta completa
        has_proposal = response.get("has_proposal", False)

        # Si hay propuesta, generar version estructurada en segundo plano
        if has_proposal:
            # Almacenar el response_id para la propuesta en algún lugar
            # (Podría ser un archivo temporal, base de datos, etc.)
            proposal_file = os.path.join(
                settings.UPLOAD_DIR, f"proposal_{response['id']}.json"
            )
            with open(proposal_file, "w", encoding="utf-8") as f:
                json.dump({"response_id": response["id"]}, f)

            # Indicar al usuario que puede descargar la propuesta
            download_message = """
# 📄 Propuesta Lista para Descargar

He preparado tu propuesta personalizada basada en la información proporcionada. Puedes descargarla usando el siguiente enlace:

## [👉 DESCARGAR PROPUESTA EN PDF](/api/chat/download-proposal?response_id={})

Este documento incluye:
- Análisis de tus necesidades específicas
- Solución tecnológica recomendada
- Estimación de costos y retorno de inversión
- Pasos siguientes recomendados

¿Necesitas alguna aclaración sobre la propuesta o tienes alguna otra pregunta?
""".format(
                response["id"]
            )

            # Enviar mensaje de descarga
            download_response = await openai_service.send_message(
                response_id=response["id"], message=download_message
            )

            # Generar propuesta estructurada en segundo plano
            background_tasks.add_task(
                openai_service.generate_structured_proposal, response["id"]
            )

            # Devolver el mensaje de descarga
            return {
                "id": download_response["id"],
                "content": download_response["content"],
                "created_at": download_response["created_at"],
                "has_proposal": True,
            }

        return {
            "id": response["id"],
            "content": response["content"],
            "created_at": response["created_at"],
        }
    except Exception as e:
        logger.error(f"Error al procesar mensaje: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al procesar el mensaje")


@router.get("/download-proposal")
async def download_proposal(response_id: str):
    """Descarga la propuesta en formato PDF"""
    try:
        # Verificar si existe un archivo de propuesta estructurada
        proposal_file = os.path.join(
            settings.UPLOAD_DIR, f"proposal_{response_id}.json"
        )

        if not os.path.exists(proposal_file):
            # Si no existe, intentar generar la propuesta estructurada
            proposal_data = await openai_service.generate_structured_proposal(
                response_id
            )

            # Guardar la propuesta estructurada
            with open(proposal_file, "w", encoding="utf-8") as f:
                json.dump(proposal_data, f)
        else:
            # Cargar la propuesta existente
            with open(proposal_file, "r", encoding="utf-8") as f:
                proposal_info = json.load(f)

            # Si solo tenemos el ID de respuesta, generar la propuesta
            if "proposal" not in proposal_info:
                proposal_data = await openai_service.generate_structured_proposal(
                    response_id
                )

                # Actualizar el archivo
                with open(proposal_file, "w", encoding="utf-8") as f:
                    json.dump(proposal_data, f)
            else:
                proposal_data = proposal_info

        # Generar PDF a partir de la propuesta estructurada
        pdf_path = await pdf_service.generate_proposal_pdf(
            proposal_data["proposal"], response_id
        )

        if not pdf_path:
            raise HTTPException(status_code=500, detail="Error al generar el PDF")

        # Obtener nombre del cliente de la propuesta
        client_name = (
            proposal_data["proposal"].get("client_info", {}).get("name", "Cliente")
        )
        client_name = client_name.replace(" ", "_")

        # Preparar nombre para el archivo
        filename = f"Propuesta_Hydrous_{client_name}.pdf"

        return FileResponse(
            path=pdf_path, filename=filename, media_type="application/pdf"
        )
    except Exception as e:
        logger.error(f"Error al descargar propuesta: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al generar la propuesta")
