# app/routes/documents.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import logging
import os
import tempfile
from typing import Optional

from app.services.openai_service import openai_service
from app.config import settings

router = APIRouter()
logger = logging.getLogger("hydrous")


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    response_id: str = Form(...),
    message: Optional[str] = Form(None),
):
    """Sube un documento y lo procesa"""
    try:
        # Guardar el archivo temporalmente
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        # Directorio para archivos subidos
        upload_path = os.path.join(settings.UPLOAD_DIR, file.filename)

        # Crear directorio si no existe
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)

        # Copiar a ubicación permanente
        with open(upload_path, "wb") as dest_file:
            with open(temp_path, "rb") as src_file:
                dest_file.write(src_file.read())

        # Subir a OpenAI y vectorizar (si está habilitado)
        file_id = None
        if settings.ENABLE_FILE_SEARCH:
            file_id = await openai_service.upload_and_index_file(
                upload_path, file.filename
            )

        # Limpiar archivo temporal
        os.unlink(temp_path)

        # Mensaje para enviar con el archivo
        user_message = message or f"He subido un documento: {file.filename}"

        # Enviar mensaje con referencia al archivo
        response = await openai_service.send_message(
            response_id=response_id,
            message=user_message,
            files=[file_id] if file_id else None,
        )

        return {
            "id": response["id"],
            "content": response["content"],
            "created_at": response["created_at"],
            "file_path": upload_path,
            "file_id": file_id,
        }
    except Exception as e:
        logger.error(f"Error al subir documento: {str(e)}")
        # Limpiar archivo temporal si existe
        if "temp_path" in locals():
            try:
                os.unlink(temp_path)
            except:
                pass
        raise HTTPException(status_code=500, detail="Error al procesar el documento")
