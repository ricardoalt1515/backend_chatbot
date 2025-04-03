# app/main.py
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging

from app.api import chat, documents, pdf
from app.services.responses_service import responses_service
from app.config import settings

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("hydrous")

# Inicializar aplicación
app = FastAPI(
    title="Hydrous AI Chatbot API",
    description="Backend para el chatbot de soluciones de agua Hydrous",
    version="1.0.0",
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


# Inicializar servicios al arrancar
@app.on_event("startup")
async def startup_event():
    """Evento de inicio de la aplicación"""
    try:
        logger.info("Inicializando servicios...")
        await responses_service.initialize()
        logger.info("Servicios inicializados correctamente")
    except Exception as e:
        logger.error(f"Error al inicializar servicios: {e}")


# Incluir rutas
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(documents.router, prefix="/api", tags=["documents"])
app.include_router(pdf.router, prefix="/api", tags=["pdf"])


# Ruta especial para PDF (para mantener compatibilidad con el frontend)
@app.get(f"{settings.API_V1_STR}/pdf/{{conversation_id}}/download")
async def download_pdf_redirect(conversation_id: str):
    """Redirige a la ruta correcta para descargas de PDF"""
    return await chat.download_pdf(conversation_id)


@app.get(f"{settings.API_V1_STR}/health")
async def health_check():
    """Endpoint para verificar que la API está funcionando"""
    status = {"status": "ok", "version": app.version, "vector_store": "not_initialized"}

    if responses_service.vector_store_id:
        status["vector_store"] = {
            "id": responses_service.vector_store_id,
            "status": "active",
        }

    return status


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
