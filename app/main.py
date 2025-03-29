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

    # 1. Inicializar servicios en el orden correcto
    try:
        # Ya tenemos los servicios básicos cargados por las importaciones:
        # - storage_service
        # - ai_service
        # - pdf_service

        # Ahora creamos e inicializamos el servicio de flujo de conversación
        from app.services.ai_service import ai_service
        from app.services.conversation_flow_service import ConversationFlowService

        # Crear una instancia del servicio de flujo con los datos del cuestionario
        conversation_flow_service = ConversationFlowService(
            ai_service.questionnaire_data
        )

        # Conectar el servicio de flujo con el servicio de IA
        ai_service.set_conversation_flow_service(conversation_flow_service)

        # Almacenar la referencia en el estado de la aplicación para uso global
        app.state.conversation_flow_service = conversation_flow_service

        logger.info("Servicios principales inicializados correctamente")
    except Exception as e:
        logger.error(f"Error al inicializar servicios principales: {e}")

    # 2. Cargar datos adicionales (hechos, estadísticas, etc.)
    try:
        facts_path = os.path.join(os.path.dirname(__file__), "data/facts.json")
        if os.path.exists(facts_path):
            with open(facts_path, "r", encoding="utf-8") as f:
                app.state.facts_data = json.load(f)
                logger.info("Datos de hechos cargados")
        else:
            logger.info(f"Archivo de hechos no encontrado en: {facts_path}")
    except Exception as e:
        logger.error(f"Error al cargar datos de hechos: {e}")
        app.state.facts_data = {}

    logger.info("Inicialización de servicios completada")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
