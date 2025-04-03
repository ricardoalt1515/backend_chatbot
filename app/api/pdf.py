from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import FileResponse, JSONResponse
import os
import uuid
import base64
from app.core.openai_service import get_conversation_history
from app.utils.pdf_generator import generate_proposal_pdf

router = APIRouter()

PDF_DIR = "pdfs"
os.makedirs(PDF_DIR, exist_ok=True)


@router.get("/pdf/{conversation_id}/download")
async def download_pdf(conversation_id: str = Path(...)):
    """
    Genera y descarga un PDF basado en la conversación.
    """
    try:
        # Obtener historial de conversación
        conversation_history = get_conversation_history(conversation_id)

        # Generar nombre de archivo
        filename = f"propuesta-hydrous-{conversation_id[:8]}.pdf"
        file_path = os.path.join(PDF_DIR, filename)

        # Generar PDF
        generate_proposal_pdf(conversation_history, file_path)

        # Devolver archivo
        return FileResponse(
            path=file_path, filename=filename, media_type="application/pdf"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pdf/{conversation_id}/data-url")
async def get_pdf_data_url(conversation_id: str = Path(...)):
    """
    Genera un PDF y lo devuelve como Data URL para navegadores que bloquean descargas.
    """
    try:
        # Obtener historial de conversación
        conversation_history = get_conversation_history(conversation_id)

        # Generar nombre de archivo
        filename = f"propuesta-hydrous-{conversation_id[:8]}.pdf"
        file_path = os.path.join(PDF_DIR, filename)

        # Generar PDF
        generate_proposal_pdf(conversation_history, file_path)

        # Convertir a Data URL
        with open(file_path, "rb") as pdf_file:
            pdf_bytes = pdf_file.read()
            pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
            data_url = f"data:application/pdf;base64,{pdf_base64}"

        return JSONResponse({"data_url": data_url, "filename": filename})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
