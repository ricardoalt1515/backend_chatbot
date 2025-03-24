# app/services/storage_service.py
import logging
from typing import Dict, Optional
from datetime import datetime
import time

from app.models.conversation import Conversation
from app.models.message import Message
from app.config import settings

logger = logging.getLogger("hydrous")


class StorageService:
    """Servicio para almacenar conversaciones"""

    def __init__(self):
        """Inicialización del servicio"""
        # Almacenamiento en memoria para conversaciones
        self.conversations: Dict[str, Conversation] = {}

        # Registro de último acceso para expiración
        self.last_access: Dict[str, float] = {}

    async def create_conversation(self) -> Conversation:
        """Crea una nueva conversación"""
        # Crear conversación con metadatos vacíos
        conversation = Conversation()

        # Guardar en el almacenamiento
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

        # Añadir mensaje
        conversation.add_message(message)

        # Actualizar en el almacenamiento
        self.conversations[conversation_id] = conversation
        self.last_access[conversation_id] = time.time()

        return conversation

    async def cleanup_old_conversations(self):
        """Elimina conversaciones antiguas basado en el tiempo de acceso"""
        current_time = time.time()
        timeout = settings.CONVERSATION_TIMEOUT

        # Buscar conversaciones expiradas
        expired_ids = [
            conv_id
            for conv_id, last_time in self.last_access.items()
            if current_time - last_time > timeout
        ]

        # Eliminar conversaciones expiradas
        for conv_id in expired_ids:
            if conv_id in self.conversations:
                del self.conversations[conv_id]
            if conv_id in self.last_access:
                del self.last_access[conv_id]

        if expired_ids:
            logger.info(f"Eliminadas {len(expired_ids)} conversaciones expiradas")


# Instancia global
storage_service = StorageService()
