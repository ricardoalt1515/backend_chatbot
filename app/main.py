# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import logging
import os
import json

from app.routes import chat, documents, feedback
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
    expose_headers=["Content-Disposition"],  # Importante para las descargas
)

# Incluir rutas
app.include_router(chat.router, prefix=f"{settings.API_V1_STR}/chat", tags=["chat"])
app.include_router(
    documents.router, prefix=f"{settings.API_V1_STR}/documents", tags=["documents"]
)
app.include_router(
    feedback.router, prefix=f"{settings.API_V1_STR}/feedback", tags=["feedback"]
)


@app.get(f"{settings.API_V1_STR}/health")
async def health_check():
    """Endpoint para verificar que la API está funcionando"""
    return {"status": "ok", "version": app.version}


@app.on_event("startup")
async def startup_event():
    """Inicialización de servicios al arrancar la aplicación"""
    logger.info("Iniciando servicios de la aplicación...")

    # Verificar que los directorios necesarios existen
    for dir_path in ["uploads", "uploads/pdf", "uploads/feedback", "uploads/analytics"]:
        os.makedirs(dir_path, exist_ok=True)
        logger.info(f"Directorio verificado: {dir_path}")

    # Inicializar servicios necesarios
    try:
        # Asegurar que el servicio de flujo de conversación está inicializado
        from app.services.ai_service import ai_service
        from app.services.conversation_flow_service import ConversationFlowService

        # Obtener datos del cuestionario ya cargados desde ai_service
        questionnaire_data = ai_service.questionnaire_data

        # Verificar si el servicio de flujo de conversación necesita ser inicializado explícitamente
        global conversation_flow_service
        if not hasattr(app.state, "conversation_flow_service"):
            app.state.conversation_flow_service = ConversationFlowService(
                questionnaire_data
            )
            logger.info("Servicio de flujo de conversación inicializado")
    except Exception as e:
        logger.error(f"Error al inicializar servicios: {e}")

    # Cargar datos de hechos y stats si existen
    try:
        facts_path = os.path.join(os.path.dirname(__file__), "data/facts.json")
        if os.path.exists(facts_path):
            with open(facts_path, "r", encoding="utf-8") as f:
                app.state.facts_data = json.load(f)
                logger.info("Datos de hechos cargados")
    except Exception as e:
        logger.error(f"Error al cargar datos de hechos: {e}")
        app.state.facts_data = {}

    logger.info("Inicialización de servicios completada")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
