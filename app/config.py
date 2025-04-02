# app/config.py
from pydantic_settings import BaseSettings
import os
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # Configuración general
    API_V1_STR: str = "/api"
    PROJECT_NAME: str = "hydrous-backend"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

    # URL del backend para enlaces absolutos
    BACKEND_URL: str = os.getenv(
        "BACKEND_URL", "https://backend-chatbot-owzs.onrender.com"
    )

    # CORS
    CORS_ORIGINS: List[str] = [
        "https://ricardoalt1515.github.io",
        "http://localhost:3000",  # Para desarrollo local
        "*" if os.getenv("DEBUG", "False").lower() in ("true", "1", "t") else "",
    ]

    # Configuración IA - OpenAI Responses API
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

    # Rutas de archivos de instrucciones y recursos
    INSTRUCTIONS_FILE: str = os.getenv(
        "INSTRUCTIONS_FILE", "app/prompts/hydrous_instructions.txt"
    )

    # Configuración de vectores y búsqueda
    ENABLE_FILE_SEARCH: bool = os.getenv("ENABLE_FILE_SEARCH", "True").lower() in (
        "true",
        "1",
        "t",
    )
    ENABLE_WEB_SEARCH: bool = os.getenv("ENABLE_WEB_SEARCH", "False").lower() in (
        "true",
        "1",
        "t",
    )
    VECTOR_STORE_ID: Optional[str] = os.getenv("VECTOR_STORE_ID", None)

    # Archivos de referencia
    QUESTIONNAIRE_FILE: str = os.getenv(
        "QUESTIONNAIRE_FILE", "app/data/cuestionario.pdf"
    )
    PROPOSAL_FORMAT_FILE: str = os.getenv(
        "PROPOSAL_FORMAT_FILE", "app/data/format_proposal.docx"
    )

    # Almacenamiento
    CONVERSATION_TIMEOUT: int = 60 * 60 * 24  # 24 horas
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")


# Crear instancia de configuración
settings = Settings()

# Asegurar que exista el directorio de uploads
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
