from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse, JSONResponse
import logging
import os

from app.services.enhanced_pdf_service import enhanced_pdf_service

router = APIRouter()
logger = logging.getLogger("hydrous")


@router.get("/{conversation_id}/download")
async def download_pdf(conversation_id: str, response: Response):
    """Descarga directa de la propuesta en formato PDF"""
    try:
        # Configurar headers CORS y seguridad
        response.headers["X-Frame-Options"] = "ALLOWALL"
        response.headers["Access-Control-Expose-Headers"] = "Content-Disposition"

        # Obtener datos del PDF
        pdf_data, filename, content_type = await enhanced_pdf_service.get_pdf_data(
            conversation_id
        )

        if not pdf_data:
            raise HTTPException(status_code=404, detail="Documento no encontrado")

        # Crear archivo temporal si es necesario
        temp_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "uploads",
            "temp",
            f"{conversation_id}_download.pdf",
        )
        os.makedirs(os.path.dirname(temp_file), exist_ok=True)

        with open(temp_file, "wb") as f:
            f.write(pdf_data)

        return FileResponse(
            path=temp_file,
            filename=filename,
            media_type=content_type,
        )
    except Exception as e:
        logger.error(f"Error al descargar PDF: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al generar el PDF")


@router.get("/{conversation_id}/data-url")
async def get_pdf_data_url(conversation_id: str):
    """Obtiene una data URL del PDF para embeber en el widget"""
    try:
        result = await enhanced_pdf_service.get_pdf_data_url(conversation_id)

        if not result:
            raise HTTPException(status_code=404, detail="Documento no encontrado")

        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error al obtener data URL: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al generar data URL")
