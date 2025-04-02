# app/routes/documents.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import logging
import os
import tempfile
from typing import Optional

from app.services.responses_service import responses_service
from app.config import settings

router = APIRouter()
logger = logging.getLogger("hydrous")


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    conversation_id: str = Form(...),
    message: Optional[str] = Form(None),
):
    """Sube un documento y lo procesa"""
    try:
        # Guardar archivo temporalmente
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        # Crear directorio para archivos si no existe
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

        # Mover a ubicación permanente
        upload_path = os.path.join(settings.UPLOAD_DIR, file.filename)
        with open(upload_path, "wb") as dest_file:
            with open(temp_path, "rb") as src_file:
                dest_file.write(src_file.read())

        # Procesar documento con OpenAI
        response = await responses_service.process_document(
            response_id=conversation_id, document_path=file.filename, message=message
        )

        # Limpiar archivo temporal
        try:
            os.unlink(temp_path)
        except:
            pass

        return response
    except Exception as e:
        logger.error(f"Error al subir documento: {str(e)}")
        # Limpiar archivo temporal en caso de error
        if "temp_path" in locals():
            try:
                os.unlink(temp_path)
            except:
                pass
        raise HTTPException(status_code=500, detail="Error al procesar el documento")
