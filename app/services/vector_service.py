# app/services/vector_service.py
from openai import OpenAI
import logging
import os
from typing import Dict, Any, Optional, List
from app.config import settings

logger = logging.getLogger("hydrous")


class VectorService:
    """Servicio para gestionar la subida y vectorización de documentos"""

    def __init__(self):
        """Inicializa el servicio con la API key"""
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    async def initialize_vector_store(self) -> Optional[str]:
        """Inicializa o recupera el vector store para el cuestionario"""
        try:
            # Buscar si ya existe un vector store
            vector_stores = self.client.vector_stores.list()
            for store in vector_stores.data:
                if store.name == "hydrous_questionnaire":
                    logger.info(f"Vector store encontrado: {store.id}")
                    return store.id

            # Si no existe, crear uno nuevo
            logger.info("Creando nuevo vector store para el cuestionario")
            vector_store = self.client.vector_stores.create(
                name="hydrous_questionnaire"
            )

            # Subir y añadir el archivo al vector store
            questionnaire_path = settings.QUESTIONNAIRE_FILE
            if not os.path.exists(questionnaire_path):
                logger.error(
                    f"Archivo de cuestionario no encontrado: {questionnaire_path}"
                )
                return None

            file_id = await self.upload_file(questionnaire_path)
            if not file_id:
                return None

            # Añadir el archivo al vector store
            file_entry = self.client.vector_stores.files.create(
                vector_store_id=vector_store.id, file_id=file_id
            )

            logger.info(f"Vector store inicializado: {vector_store.id}")
            return vector_store.id

        except Exception as e:
            logger.error(f"Error al inicializar vector store: {e}")
            return None

    async def upload_file(self, file_path: str) -> Optional[str]:
        """Sube un archivo a OpenAI para vectorización"""
        try:
            logger.info(f"Subiendo archivo: {file_path}")
            with open(file_path, "rb") as file:
                response = self.client.files.create(file=file, purpose="vector_store")

            logger.info(f"Archivo subido correctamente: {response.id}")
            return response.id
        except Exception as e:
            logger.error(f"Error al subir archivo: {e}")
            return None

    async def get_vector_store_status(self, vector_store_id: str) -> Dict[str, Any]:
        """Obtiene el estado del vector store"""
        try:
            files = self.client.vector_stores.files.list(
                vector_store_id=vector_store_id
            )

            return {
                "id": vector_store_id,
                "status": "active" if files.data else "empty",
                "file_count": len(files.data),
            }
        except Exception as e:
            logger.error(f"Error al obtener estado del vector store: {e}")
            return {"id": vector_store_id, "status": "error", "message": str(e)}

    async def test_vector_search(
        self, vector_store_id: str, query: str = "cuestionario industrial"
    ) -> Dict[str, Any]:
        """Prueba la búsqueda en el vector store para verificar su funcionamiento"""
        try:
            # Realizar búsqueda directa
            results = self.client.vector_stores.search(
                vector_store_id=vector_store_id, query=query, max_results=5
            )

            search_info = {
                "query": query,
                "results_count": len(results.data),
                "results": [],
            }

            # Registrar resultados
            for result in results.data:
                search_info["results"].append(
                    {
                        "score": result.score,
                        "file_id": result.file_id,
                        "text": (
                            result.text[:100] + "..."
                            if len(result.text) > 100
                            else result.text
                        ),
                    }
                )

            return search_info
        except Exception as e:
            logger.error(f"Error en prueba de búsqueda: {e}")
            return {"error": str(e)}


# Instancia global
vector_service = VectorService()
