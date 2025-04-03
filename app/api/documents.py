from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
import os
import uuid
from app.config import settings  # Actualizar import
from app.core.openai_service import process_document

router = APIRouter()


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    conversation_id: str = Form(...),
    message: Optional[str] = Form(""),
):
    """
    Sube un documento y lo procesa en el contexto de la conversación.
    """
    try:
        # Generar nombre único para el archivo
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(settings.UPLOAD_DIR, unique_filename)  # Usar settings

        # Guardar archivo
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        # Procesar documento
        result = process_document(conversation_id, file_path, message)

        return {
            "success": True,
            "filename": file.filename,
            "stored_path": file_path,
            "id": result["id"],
            "message": result["message"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
