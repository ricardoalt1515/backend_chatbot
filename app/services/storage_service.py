# app/services/storage_service.py
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from app.models.conversation import Conversation
from app.models.message import Message
from app.models.conversation_state import ConversationState  # Importar
from app.config import settings

logger = logging.getLogger("hydrous")

# --- ALMACENAMIENTO EN MEMORIA (SOLO PARA EJEMPLO) ---
# ¡¡¡ REEMPLAZAR CON TU BASE DE DATOS EN PRODUCCIÓN !!!
conversations_db: Dict[str, Conversation] = {}
# ----------------------------------------------------


class StorageService:

    async def create_conversation(
        self, initial_state: Optional[ConversationState] = None
    ) -> Conversation:
        """Crea y almacena una nueva conversación."""
        if initial_state is None:
            initial_state = (
                ConversationState()
            )  # Crear estado por defecto si no se pasa
        new_conversation = Conversation(state=initial_state)  # Pasar estado al crear
        conversations_db[new_conversation.id] = new_conversation
        logger.info(f"Conversación creada en memoria con ID: {new_conversation.id}")
        return new_conversation

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Obtiene una conversación por su ID."""
        conversation = conversations_db.get(conversation_id)
        if conversation:
            logger.debug(f"Conversación {conversation_id} encontrada en memoria.")
            # Asegurarse que el estado es un objeto ConversationState
            if isinstance(
                conversation.state, dict
            ):  # Si se guardó como dict, convertirlo
                conversation.state = ConversationState(**conversation.state)
            return conversation
        else:
            logger.warning(f"Conversación {conversation_id} NO encontrada en memoria.")
            return None

    async def add_message_to_conversation(
        self, conversation_id: str, message: Message
    ) -> bool:
        """Añade un mensaje a una conversación existente."""
        conversation = await self.get_conversation(conversation_id)
        if conversation:
            conversation.add_message(message)
            # No es necesario guardar explícitamente en memoria si modificamos el objeto
            logger.debug(f"Mensaje añadido a conversación {conversation_id}")
            return True
        else:
            logger.error(
                f"Intento de añadir mensaje a conversación inexistente: {conversation_id}"
            )
            return False

    async def save_conversation(self, conversation: Conversation) -> bool:
        """
        Guarda/Actualiza una conversación completa (incluyendo estado y metadatos).
        En este ejemplo en memoria, la modificación directa del objeto es suficiente,
        pero esta función es CRUCIAL para BDs reales.
        """
        if conversation.id in conversations_db:
            # Asegurarse que el estado se guarda correctamente
            if not isinstance(conversation.state, ConversationState):
                logger.error(
                    f"Intentando guardar estado inválido para {conversation.id}"
                )
                return False
            conversations_db[conversation.id] = (
                conversation  # Reemplazar con la versión actualizada
            )
            logger.info(
                f"Conversación {conversation.id} actualizada/guardada en memoria."
            )
            return True
        else:
            logger.error(
                f"Intento de guardar conversación inexistente: {conversation.id}"
            )
            return False

    async def cleanup_old_conversations(self):
        """Elimina conversaciones más antiguas que el timeout (ejemplo en memoria)."""
        now = datetime.utcnow()
        timeout_delta = timedelta(seconds=settings.CONVERSATION_TIMEOUT)
        ids_to_remove = [
            conv_id
            for conv_id, conv in conversations_db.items()
            if now - conv.created_at > timeout_delta
        ]
        for conv_id in ids_to_remove:
            try:
                del conversations_db[conv_id]
                logger.info(f"Conversación antigua eliminada: {conv_id}")
            except KeyError:
                pass  # Ya no existía


# Instancia global
storage_service = StorageService()
