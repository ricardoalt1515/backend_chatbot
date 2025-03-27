from pydantic_settings import BaseSettings
import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # Configuración general
    API_V1_STR: str = "/api"
    PROJECT_NAME: str = "hydrous-backend"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

    # CORS
    CORS_ORIGINS: List[str] = ["*"]

    # Configuración IA - Añadimos compatibilidad con los nombres antiguos y nuevos
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    API_KEY: str = os.getenv(
        "OPENAI_API_KEY", os.getenv("GROQ_API_KEY", "")
    )  # Para compatibilidad

    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "distil-whisper-large-v3-en")
    MODEL: str = os.getenv(
        "MODEL", os.getenv("OPENAI_MODEL", os.getenv("GROQ_MODEL", "gpt-3.5-turbo"))
    )

    # Determinar URL de API basado en lo que esté disponible
    API_PROVIDER: str = os.getenv("AI_PROVIDER", "groq")  # "openai" o "groq"

    @property
    def API_URL(self):
        if self.API_PROVIDER == "groq":
            return "https://api.groq.com/openai/v1/chat/completions"
        else:
            return "https://api.openai.com/v1/chat/completions"

    # Almacenamiento
    CONVERSATION_TIMEOUT: int = 60 * 60 * 24  # 24 horas
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")


# Crear instancia de configuración
settings = Settings()

# Asegurar que exista el directorio de uploads
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
