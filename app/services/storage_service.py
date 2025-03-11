import logging
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
import time

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.analytics import AnalyticsEvent
from app.config import settings

logger = logging.getLogger("hydrous-backend")


class MemoryStorage:
    """
    Almacenamiento en memoria para el MVP
    En el futuro, esto se reemplazará por MongoDB
    """

    def __init__(self):
        # Diccionarios para almacenar datos en memoria
        self.conversations: Dict[str, Conversation] = {}
        self.analytics_events: List[AnalyticsEvent] = []
        # Control del tiempo de expiración de las conversaciones
        self.conversation_last_access: Dict[str, float] = {}

    async def cleanup_old_conversations(self):
        """Elimina conversaciones antiguas basadas en el tiempo de acceso"""
        current_time = time.time()
        expired_ids = []

        for conv_id, last_access in self.conversation_last_access.items():
            if current_time - last_access > settings.CONVERSATION_TIMEOUT:
                expired_ids.append(conv_id)

        for conv_id in expired_ids:
            if conv_id in self.conversations:
                del self.conversations[conv_id]
            del self.conversation_last_access[conv_id]

        if expired_ids:
            logger.info(f"Limpiadas {len(expired_ids)} conversaciones expiradas")

    # Métodos para gestión de conversaciones
    async def create_conversation(
        self, metadata: Dict[str, Any] = None
    ) -> Conversation:
        """Crea una nueva conversación"""
        conversation = Conversation(metadata=metadata or {})

        # Añadir mensaje del sistema para guiar al modelo
        system_message = Message.system(settings.SYSTEM_PROMPT)
        conversation.add_message(system_message)

        # Guardar conversación
        self.conversations[conversation.id] = conversation
        self.conversation_last_access[conversation.id] = time.time()

        return conversation

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Obtiene una conversación por su ID"""
        # Actualizar tiempo de acceso
        if conversation_id in self.conversations:
            self.conversation_last_access[conversation_id] = time.time()

        return self.conversations.get(conversation_id)

    async def add_message_to_conversation(
        self, conversation_id: str, message: Message
    ) -> Optional[Conversation]:
        """Añade un mensaje a una conversación existente"""
        conversation = await self.get_conversation(conversation_id)
        if not conversation:
            return None

        conversation.add_message(message)
        return conversation

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Elimina una conversación"""
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
            if conversation_id in self.conversation_last_access:
                del self.conversation_last_access[conversation_id]
            return True
        return False

    # Métodos para gestión de eventos de analítica
    async def store_analytics_event(self, event: AnalyticsEvent) -> AnalyticsEvent:
        """Almacena un evento de analítica"""
        self.analytics_events.append(event)
        # En el MVP solo guardamos un número limitado de eventos
        if len(self.analytics_events) > 1000:
            self.analytics_events = self.analytics_events[-1000:]
        return event

    async def get_recent_analytics(self, limit: int = 100) -> List[AnalyticsEvent]:
        """Obtiene los eventos de analítica más recientes"""
        return self.analytics_events[-limit:]


# Instancia global del servicio de almacenamiento
storage_service = MemoryStorage()
