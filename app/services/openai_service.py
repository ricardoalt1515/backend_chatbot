# app/services/openai_service.py
from openai import OpenAI
from app.config import settings
import logging
import json
import os
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("hydrous")


class OpenAIService:
    def __init__(self):
        """Inicializa el servicio de OpenAI usando la API Responses"""
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._load_instructions()

    async def initliaze(self):
        """Inicializa el servicio (debe llamarse despues de crear la Instancia)"""
        await self._initialize_vector_store()
        return self

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

    async def _initialize_vector_store(self):
        """Inicializa el vector store si está habilitado"""
        if not settings.ENABLE_FILE_SEARCH:
            return

        try:
            # Verificar si ya tenemos un vector store ID
            if settings.VECTOR_STORE_ID:
                # Verificar si el vector store existe
                try:
                    # Nota: Esto dependerá de la implementación específica de la API
                    # Ya que la documentación no es totalmente clara sobre cómo obtener un vector store por ID
                    vector_stores = self.client.vector_stores.list()
                    for store in vector_stores.data:
                        if store.id == settings.VECTOR_STORE_ID:
                            logger.info(
                                f"Vector store encontrado: {settings.VECTOR_STORE_ID}"
                            )
                            return
                except Exception as e:
                    logger.warning(f"No se pudo verificar el vector store: {e}")

            # Crear un nuevo vector store
            vector_store = self.client.vector_stores.create(
                name="hydrous_knowledge_base"
            )
            logger.info(f"Nuevo vector store creado: {vector_store.id}")

            # Subir cuestionario si existe
            if os.path.exists(settings.QUESTIONNAIRE_FILE):
                await self.upload_and_index_file(
                    settings.QUESTIONNAIRE_FILE, "questionnaire"
                )

            # Subir formato de propuesta si existe
            if os.path.exists(settings.PROPOSAL_FORMAT_FILE):
                await self.upload_and_index_file(
                    settings.PROPOSAL_FORMAT_FILE, "proposal_format"
                )

        except Exception as e:
            logger.error(f"Error al inicializar vector store: {e}")

    async def start_conversation(self) -> Dict[str, Any]:
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

🌍 *Esta información es importante para evaluar la normativa local, la disponibilidad de agua, y posibles incentivos para reciclaje de agua en tu zona.*
"""
            # Configurar herramientas
            tools = self._configure_tools()

            # Crear respuesta inicial
            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                instructions=self.instructions,
                input=welcome_message,
                tools=tools,
            )

            return {
                "id": response.id,
                "content": response.output_text,
                "created_at": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Error al iniciar conversación: {e}")
            raise

    async def send_message(
        self, response_id: str, message: str, files: List[str] = None
    ) -> Dict[str, Any]:
        """Envía un mensaje y obtiene respuesta"""
        try:
            # Configurar herramientas
            tools = self._configure_tools()

            # Crear respuesta (sin file_ids como parámetro directo)
            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                previous_response_id=response_id,
                input=message,
                tools=tools,
                # Removemos el parámetro file_ids que causaba el error
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
            logger.error(f"Error al procesar mensaje: {e}")
            raise

    async def generate_structured_proposal(self, response_id: str) -> Dict[str, Any]:
        """Genera una propuesta estructurada basada en la conversación"""
        try:
            # Esquema para la propuesta
            proposal_schema = {
                "type": "object",
                "properties": {
                    "client_info": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "location": {"type": "string"},
                            "sector": {"type": "string"},
                            "subsector": {"type": "string"},
                        },
                    },
                    "project_background": {"type": "string"},
                    "project_objective": {"type": "string"},
                    "key_parameters": {
                        "type": "object",
                        "properties": {
                            "water_consumption": {"type": "string"},
                            "wastewater_generation": {"type": "string"},
                            "key_contaminants": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                    "treatment_process": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "stage": {"type": "string"},
                                "technology": {"type": "string"},
                                "purpose": {"type": "string"},
                            },
                        },
                    },
                    "financial_analysis": {
                        "type": "object",
                        "properties": {
                            "estimated_capex": {"type": "string"},
                            "estimated_opex": {"type": "string"},
                            "roi_estimate": {"type": "string"},
                        },
                    },
                    "next_steps": {"type": "array", "items": {"type": "string"}},
                },
            }

            # Solicitar generación de propuesta estructurada
            prompt = "Por favor, genera una propuesta estructurada basada en toda nuestra conversación y la información recopilada hasta ahora."

            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                previous_response_id=response_id,
                input=prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "water_treatment_proposal",
                        "schema": proposal_schema,
                        "strict": True,
                    }
                },
            )

            # Parsear la propuesta
            proposal_data = json.loads(response.output_text)

            return {
                "id": response.id,
                "proposal": proposal_data,
                "created_at": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Error al generar propuesta estructurada: {e}")
            raise

    async def upload_and_index_file(
        self, file_path: str, file_purpose: str = None
    ) -> str:
        """Sube y vectoriza un archivo para búsqueda"""
        try:
            # Verificar que el archivo existe
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

            # 1. Crear un archivo
            logger.info(f"Subiendo archivo: {file_path}")
            with open(file_path, "rb") as file:
                file_obj = self.client.files.create(file=file, purpose="vector_store")

            logger.info(f"Archivo subido con ID: {file_obj.id}")

            # 2. Verificar o crear vector store
            if not settings.VECTOR_STORE_ID:
                # Crear vector store
                vector_store = self.client.vector_stores.create(
                    name=f"hydrous_knowledge_{file_purpose or 'general'}"
                )
                logger.info(f"Vector store creado: {vector_store.id}")
            else:
                # Usar vector store existente
                vector_store_id = settings.VECTOR_STORE_ID
                logger.info(f"Usando vector store existente: {vector_store_id}")

            # 3. Añadir archivo al vector store
            logger.info(f"Añadiendo archivo al vector store")
            file_entry = self.client.vector_stores.files.create(
                vector_store_id=vector_store.id, file_id=file_obj.id
            )

            logger.info(f"Archivo añadido al vector store: {file_entry.id}")

            return file_obj.id
        except Exception as e:
            logger.error(f"Error al procesar archivo: {e}")
            raise

    def _configure_tools(
        self, query_context: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Configura todas las herramientas disponibles según el contexto"""
        tools = []

        # Añadir búsqueda en archivos si está habilitada
        if settings.ENABLE_FILE_SEARCH and settings.VECTOR_STORE_ID:
            file_search_tool = {
                "type": "file_search",
                "vector_store_ids": [settings.VECTOR_STORE_ID],
            }

            # Configuraciones adicionales si hay contexto
            if query_context and "max_results" in query_context:
                file_search_tool["max_num_results"] = query_context["max_results"]

            tools.append(file_search_tool)

        # Añadir búsqueda web si está habilitada
        if settings.ENABLE_WEB_SEARCH:
            tools.append({"type": "web_search"})

        return tools


# Instancia global
openai_service = OpenAIService()

# Variable para almacenar la instancia inicializada
_openai_service_instance = None


async def get_openai_service():
    """Obtiene una instancia inicializada de OpenAIService"""
    global _openai_service_instance
    if _openai_service_instance is None:
        service = OpenAIService()
        _openai_service_instance = await service.initialize()
    return _openai_service_instance
