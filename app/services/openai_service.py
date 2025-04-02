# app/services/openai_service.py
from openai import OpenAI
from app.config import settings
import logging
import os
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
            if os.path.exists(settings.INSTRUCTIONS_FILE):
                with open(settings.INSTRUCTIONS_FILE, "r", encoding="utf-8") as f:
                    self.instructions = f.read()
                logger.info("Instrucciones cargadas correctamente")
            else:
                logger.warning(
                    f"Archivo de instrucciones no encontrado: {settings.INSTRUCTIONS_FILE}"
                )
                self.instructions = (
                    "Soy el asistente de soluciones de agua de Hydrous AI."
                )
        except Exception as e:
            logger.error(f"Error al cargar instrucciones: {e}")
            self.instructions = "Soy el asistente de soluciones de agua de Hydrous AI."

    async def start_conversation(self):
        """Inicia una nueva conversación con mensaje de bienvenida"""
        try:
            welcome_message = """
# 👋 ¡Bienvenido a Hydrous AI!

Soy el diseñador de soluciones de agua de Hydrous AI, tu asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales. Como herramienta de Hydrous, estoy aquí para guiarte paso a paso en la evaluación de las necesidades de agua de tu sitio, la exploración de posibles soluciones y la identificación de oportunidades de ahorro de costos, cumplimiento y sostenibilidad.

💡 *Las soluciones de reciclaje de agua pueden reducir el consumo de agua fresca hasta en un 70% en instalaciones industriales similares.*

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
            logger.error(f"Error al iniciar conversación: {str(e)}")
            raise

    async def send_message(self, response_id, message):
        """Envía un mensaje y obtiene respuesta"""
        try:
            # Crear respuesta usando previous_response_id
            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                previous_response_id=response_id,
                input=message,
            )

            # Verificar si contiene indicador de propuesta completa
            content = response.output_text
            has_proposal = "[PROPOSAL_COMPLETE:" in content

            return {
                "id": response.id,
                "content": content,
                "has_proposal": has_proposal,
                "created_at": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Error al procesar mensaje: {str(e)}")
            raise


# Instancia global
openai_service = OpenAIService()
