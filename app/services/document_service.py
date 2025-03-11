import os
import logging
import uuid
from typing import Optional, Dict, Any, List
from fastapi import UploadFile
import shutil

from app.config import settings

logger = logging.getLogger("hydrous-backend")


class DocumentService:
    """Servicio para gestionar documentos subidos por los usuarios"""

    def __init__(self):
        # Asegurarse de que exista el directorio de uploads
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        # Mapeo de documentos - para el MVP en memoria
        self.documents: Dict[str, Dict[str, Any]] = {}

    async def save_document(
        self, file: UploadFile, conversation_id: str
    ) -> Dict[str, Any]:
        """
        Guarda un documento subido por el usuario

        Args:
            file: Archivo subido
            conversation_id: ID de la conversación asociada

        Returns:
            Dict con la información del documento guardado
        """
        try:
            # Generar ID único para el documento
            doc_id = str(uuid.uuid4())

            # Extraer extensión y crear nombre de archivo
            file_ext = os.path.splitext(file.filename)[1]
            filename = f"{doc_id}{file_ext}"
            file_path = os.path.join(settings.UPLOAD_DIR, filename)

            # Guardar archivo
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Registrar información del documento
            doc_info = {
                "id": doc_id,
                "filename": file.filename,
                "content_type": file.content_type,
                "size": os.path.getsize(file_path),
                "path": file_path,
                "conversation_id": conversation_id,
            }

            # Guardar en el registro de documentos
            self.documents[doc_id] = doc_info

            return doc_info

        except Exception as e:
            logger.error(f"Error al guardar documento: {str(e)}")
            raise

    async def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene información de un documento por su ID"""
        return self.documents.get(doc_id)

    async def get_conversation_documents(
        self, conversation_id: str
    ) -> List[Dict[str, Any]]:
        """Obtiene todos los documentos asociados a una conversación"""
        return [
            doc
            for doc in self.documents.values()
            if doc["conversation_id"] == conversation_id
        ]

    async def delete_document(self, doc_id: str) -> bool:
        """Elimina un documento"""
        doc = self.documents.get(doc_id)
        if not doc:
            return False

        try:
            # Eliminar archivo físico
            if os.path.exists(doc["path"]):
                os.remove(doc["path"])

            # Eliminar registro
            del self.documents[doc_id]
            return True
        except Exception as e:
            logger.error(f"Error al eliminar documento {doc_id}: {str(e)}")
            return False


# Instancia global del servicio
document_service = DocumentService()
