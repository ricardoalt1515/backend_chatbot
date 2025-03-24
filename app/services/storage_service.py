import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import time

from app.models.conversation import Conversation
from app.models.message import Message
from app.config import settings

logger = logging.getLogger("hydrous")


class SimpleStorageService:
    """Almacenamiento básico en memoria para conversaciones y documentos"""

    def __init__(self):
        # Almacenamiento en memoria
        self.conversations: Dict[str, Conversation] = {}
        self.documents: Dict[str, Dict] = {}
        self.last_access: Dict[str, float] = {}

    async def create_conversation(self, metadata: Dict = None) -> Conversation:
        """Crea una nueva conversación"""
        # Crear conversación
        conversation = Conversation(metadata=metadata or {})

        # Añadir mensaje del sistema con el prompt maestro
        system_message = Message.system(settings.SYSTEM_PROMPT)
        conversation.add_message(system_message)

        # Guardar
        self.conversations[conversation.id] = conversation
        self.last_access[conversation.id] = time.time()

        return conversation

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Obtiene una conversación por su ID"""
        # Actualizar tiempo de acceso
        if conversation_id in self.conversations:
            self.last_access[conversation_id] = time.time()

        return self.conversations.get(conversation_id)

    async def add_message_to_conversation(
        self, conversation_id: str, message: Message
    ) -> Optional[Conversation]:
        """Añade un mensaje a una conversación"""
        conversation = await self.get_conversation(conversation_id)
        if not conversation:
            return None

        conversation.add_message(message)
        self.conversations[conversation_id] = conversation

        return conversation

    async def save_document(
        self, file_data: bytes, filename: str, conversation_id: str
    ) -> Dict:
        """Guarda un documento y lo asocia a una conversación"""
        import uuid
        import os

        # Crear ID y dirección para el documento
        doc_id = str(uuid.uuid4())
        file_ext = os.path.splitext(filename)[1]
        save_path = f"{settings.UPLOAD_DIR}/{doc_id}{file_ext}"

        # Guardar físicamente
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(file_data)

        # Registrar documento
        doc_info = {
            "id": doc_id,
            "filename": filename,
            "path": save_path,
            "conversation_id": conversation_id,
            "uploaded_at": datetime.now().isoformat(),
        }

        self.documents[doc_id] = doc_info
        return doc_info

    async def cleanup_old_conversations(self):
        """Elimina conversaciones antiguas"""
        current_time = time.time()
        timeout = settings.CONVERSATION_TIMEOUT

        to_delete = [
            conv_id
            for conv_id, last_time in self.last_access.items()
            if current_time - last_time > timeout
        ]

        for conv_id in to_delete:
            if conv_id in self.conversations:
                del self.conversations[conv_id]
            if conv_id in self.last_access:
                del self.last_access[conv_id]


# Instancia global
storage_service = SimpleStorageService()
