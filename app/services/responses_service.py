# app/services/responses_service.py
from openai import OpenAI
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
import os

from app.config import settings
from app.services.vector_service import vector_service

logger = logging.getLogger("hydrous")


class ResponsesService:
    """Servicio para interactuar con la API Responses de OpenAI"""

    def __init__(self):
        """Inicializa el servicio con la API key"""
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._load_instructions()
        self.vector_store_id = None

    def _load_instructions(self):
        """Carga las instrucciones desde archivo"""
        try:
            instructions_file = settings.INSTRUCTIONS_FILE
            if os.path.exists(instructions_file):
                with open(instructions_file, "r", encoding="utf-8") as f:
                    self.instructions = f.read()
                logger.info("Instrucciones cargadas correctamente")
            else:
                logger.warning(
                    f"Archivo de instrucciones no encontrado: {instructions_file}"
                )
                self.instructions = (
                    "Soy el asistente de soluciones de agua de Hydrous AI."
                )
        except Exception as e:
            logger.error(f"Error al cargar instrucciones: {e}")
            self.instructions = "Soy el asistente de soluciones de agua de Hydrous AI."

    async def initialize(self):
        """Inicializa el servicio y los recursos necesarios"""
        self.vector_store_id = await vector_service.initialize_vector_store()
        if self.vector_store_id:
            logger.info(
                f"Servicio inicializado con vector store: {self.vector_store_id}"
            )
        else:
            logger.warning("No se pudo inicializar el vector store")

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
            # Configurar herramientas si el vector store está disponible
            tools = []
            if self.vector_store_id:
                tools.append(
                    {
                        "type": "file_search",
                        "vector_store_ids": [self.vector_store_id],
                        "max_num_results": 5,
                    }
                )

            # Crear respuesta inicial
            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                instructions=self.instructions,
                input=welcome_message,
                tools=tools,
                temperature=0.7,
                max_output_tokens=2048,
                store=True,
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
        """Procesa un mensaje y obtiene respuesta con búsqueda mejorada"""
        try:
            # Configurar herramientas para búsqueda en archivos
            tools = []
            if self.vector_store_id:
                tools.append(
                    {
                        "type": "file_search",
                        "vector_store_ids": [self.vector_store_id],
                        "max_num_results": 10,  # Aumentado para obtener más contexto
                        "filter": {"document_type": "pdf"},  # Filtrar solo PDFs
                    }
                )
                logger.info(
                    f"Configurada búsqueda en vector store: {self.vector_store_id}"
                )

            # Preparar mensaje de sistema para reforzar el uso del cuestionario
            system_message = """
    IMPORTANTE: Debes usar el cuestionario para guiar la conversación. 
    Busca la sección correspondiente al sector y subsector del usuario.
    Sigue EXACTAMENTE las preguntas del cuestionario en orden, una a la vez.
    """

            # Crear respuesta
            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                previous_response_id=response_id,
                input=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": message},
                ],
                tools=tools,
                temperature=0.5,  # Reducido para mayor precisión
                max_output_tokens=2048,
                store=True,
            )

            # Registrar si se usó la herramienta de búsqueda
            if hasattr(response, "tool_calls") and response.tool_calls:
                for tool_call in response.tool_calls:
                    if tool_call.type == "file_search":
                        logger.info(
                            f"Búsqueda realizada: {tool_call.file_search_call.query}"
                        )
                        logger.info(
                            f"Resultados obtenidos: {len(tool_call.file_search_call.search_results)}"
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

            # Analizar documento (usando file_search si está disponible)
            doc_context = f"[DOCUMENTO: {document_path}] {doc_message}"

            # Configurar herramientas
            tools = []
            if self.vector_store_id:
                tools.append(
                    {
                        "type": "file_search",
                        "vector_store_ids": [self.vector_store_id],
                        "max_num_results": 5,
                    }
                )

            # Crear respuesta
            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                previous_response_id=response_id,
                input=doc_context,
                tools=tools,
                temperature=0.7,
                max_output_tokens=2048,
                store=True,
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

# Asegurarse de que la clase sea exportada correctamente
__all__ = ["ResponsesService", "responses_service"]
