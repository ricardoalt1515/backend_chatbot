# app/services/responses_service.py
from openai import OpenAI
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger("hydrous")


class ResponsesService:
    """Servicio simplificado para la API Responses de OpenAI"""

    def __init__(self):
        """Inicializa el servicio con la API key"""
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._load_instructions()

    def _load_instructions(self):
        """Carga las instrucciones desde archivo"""
        try:
            instructions_file = settings.INSTRUCTIONS_FILE
            with open(instructions_file, "r", encoding="utf-8") as f:
                self.instructions = f.read()
            logger.info("Instrucciones cargadas correctamente")
        except Exception as e:
            logger.error(f"Error al cargar instrucciones: {e}")
            self.instructions = "Soy el asistente de soluciones de agua de Hydrous AI."

    async def start_conversation(self) -> Dict[str, Any]:
        """Inicia una nueva conversación con un mensaje de bienvenida"""
        try:
            # Mensaje inicial
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
                "message": response.output_text,
                "created_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error al iniciar conversación: {e}")
            raise

    async def process_message(self, response_id: str, message: str) -> Dict[str, Any]:
        """Procesa un mensaje y obtiene respuesta"""
        try:
            # Crear respuesta usando previous_response_id
            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                previous_response_id=response_id,
                input=message,
            )

            # Verificar si contiene una propuesta completa
            has_proposal = "[PROPOSAL_COMPLETE:" in response.output_text

            return {
                "id": response.id,
                "message": response.output_text,
                "has_proposal": has_proposal,
                "created_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error al procesar mensaje: {e}")
            raise

    async def process_document(
        self, response_id: str, document_path: str, message: str = None
    ) -> Dict[str, Any]:
        """Procesa un documento junto con un mensaje opcional"""
        try:
            # Mensaje para enviar con el documento
            doc_message = message or f"He subido un documento: {document_path}"

            # Analizar documento (no hay soporte directo para adjuntar archivos en API Responses)
            # En su lugar, mencionamos el documento en el mensaje
            doc_context = f"[DOCUMENTO: {document_path}] {doc_message}"

            # Crear respuesta
            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                previous_response_id=response_id,
                input=doc_context,
            )

            return {
                "id": response.id,
                "message": response.output_text,
                "created_at": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error(f"Error al procesar documento: {e}")
            raise


# Instancia global
responses_service = ResponsesService()
