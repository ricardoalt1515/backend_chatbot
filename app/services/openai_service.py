# app/services/openai_service.py
from openai import OpenAI
from app.config import settings
import logging
from datetime import datetime

logger = logging.getLogger("hydrous")


class OpenAIService:
    def __init__(self):
        """Inicializa el servicio de OpenAI usando la API Responses"""
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._load_instructions()

    def _load_instructions(self):
        """Carga las instrucciones desde el archivo"""
        try:
            if hasattr(settings, "INSTRUCTIONS_FILE") and settings.INSTRUCTIONS_FILE:
                with open(settings.INSTRUCTIONS_FILE, "r", encoding="utf-8") as f:
                    self.instructions = f.read()
                logger.info("Instrucciones cargadas correctamente")
            else:
                logger.warning("Ruta de instrucciones no configurada")
                self.instructions = (
                    "Soy el asistente de soluciones de agua de Hydrous AI."
                )
        except Exception as e:
            logger.error(f"Error al cargar instrucciones: {e}")
            self.instructions = "Soy el asistente de soluciones de agua de Hydrous AI."

    async def start_conversation(self) -> dict:
        """Inicia una nueva conversación con mensaje de bienvenida"""
        try:
            # Mensaje de bienvenida
            welcome_message = """
# 👋 ¡Bienvenido a Hydrous AI!

Soy el diseñador de soluciones de agua de Hydrous AI, tu asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales.

**PREGUNTA: ¿Cuál es el nombre de tu empresa o proyecto y dónde se ubica?**

Por favor incluye:
- Nombre de tu empresa o proyecto
- Ubicación (ciudad, estado, país)
"""
            # Crear respuesta inicial
            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                instructions=self.instructions,
                input=welcome_message,
            )

            return {
                "id": response.id,
                "content": response.output_text,
                "created_at": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Error al iniciar conversación: {e}")
            raise

    async def send_message(self, previous_response_id: str, message: str) -> dict:
        """Envía un mensaje y obtiene respuesta"""
        try:
            # Usar previous_response_id para continuidad de la conversación
            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                previous_response_id=previous_response_id,
                input=message,
            )

            return {
                "id": response.id,
                "content": response.output_text,
                "created_at": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Error al procesar mensaje: {e}")
            raise


# Instancia global
openai_service = OpenAIService()
