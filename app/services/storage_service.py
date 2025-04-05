# app/services/storage_service.py
import logging
from datetime import datetime, timedelta

# --- AÑADIR ESTAS IMPORTACIONES ---
from typing import (
    Dict,
    Optional,
    Any,
)  # Asegúrate de importar Optional y Any también si los usas

# -----------------------------------

from app.models.conversation import Conversation
from app.models.message import Message

# Quitar import de ConversationState si ya no se usa
# from app.models.conversation_state import ConversationState
from app.config import settings

logger = logging.getLogger("hydrous")

# Usar la importación correcta para la anotación de tipo
conversations_db: Dict[str, Conversation] = {}


class StorageService:

    async def create_conversation(self) -> Conversation:
        """Crea y almacena una nueva conversación con metadata inicial."""
        initial_metadata: Dict[str, Any] = {  # Usar Dict aquí también
            "current_question_id": None,
            "collected_data": {},
            "selected_sector": None,
            "selected_subsector": None,
            "questionnaire_path": [],
            "is_complete": False,
            "has_proposal": False,
            "proposal_text": None,
            "pdf_path": None,
            "client_name": "Cliente",
            "last_error": None,
        }
        new_conversation = Conversation(metadata=initial_metadata)
        conversations_db[new_conversation.id] = new_conversation
        logger.info(
            f"DBG_SS: Conversación {new_conversation.id} CREADA. Metadata inicial: {initial_metadata}"
        )
        return new_conversation

    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Obtiene una conversación por su ID (EN MEMORIA)."""
        conversation = conversations_db.get(conversation_id)
        if conversation:
            if not isinstance(conversation.metadata, dict):
                logger.warning(
                    f"Metadata inválida para {conversation_id}, reiniciando a default."
                )
                # Recrear metadata inicial si está corrupta
                conversation.metadata = {
                    "current_question_id": None,
                    "collected_data": {},
                    "selected_sector": None,
                    "selected_subsector": None,
                    "questionnaire_path": [],
                    "is_complete": False,
                    "has_proposal": False,
                    "proposal_text": None,
                    "pdf_path": None,
                    "client_name": "Cliente",
                    "last_error": None,
                }
            logger.info(
                f"DBG_SS: Conversación {conversation_id} RECUPERADA. Metadata actual: {conversation.metadata}"
            )
            return conversation
        else:
            logger.warning(f"DBG_SS: Conversación {conversation_id} NO encontrada.")
            return None

    async def add_message_to_conversation(
        self, conversation_id: str, message: Message
    ) -> bool:
        """Añade un mensaje (EN MEMORIA)."""
        conversation = await self.get_conversation(conversation_id)
        if conversation:
            # Asegurarse que messages es una lista
            if not isinstance(conversation.messages, list):
                logger.warning(
                    f"Lista de mensajes inválida para {conversation_id}, reiniciando."
                )
                conversation.messages = []
            conversation.messages.append(message)
            logger.debug(
                f"DBG_SS: Mensaje '{message.role}' añadido a {conversation_id}."
            )
            return True
        else:
            logger.error(
                f"DBG_SS: Error al añadir mensaje, conversación {conversation_id} no encontrada."
            )
            return False

    async def save_conversation(self, conversation: Conversation) -> bool:
        """Guarda/Actualiza la conversación completa (EN MEMORIA)."""
        if not isinstance(conversation, Conversation):
            logger.error(
                f"DBG_SS: Intento de guardar objeto inválido: {type(conversation)}"
            )
            return False
        # Verificar metadata y messages antes de guardar
        if not isinstance(conversation.metadata, dict):
            logger.error(
                f"DBG_SS: Intento de guardar metadata inválida para {conversation.id}: {type(conversation.metadata)}"
            )
            return False
        if not isinstance(conversation.messages, list):
            logger.error(
                f"DBG_SS: Intento de guardar lista de mensajes inválida para {conversation.id}: {type(conversation.messages)}"
            )
            return False

        logger.info(
            f"DBG_SS: GUARDANDO conversación {conversation.id}. Metadata: {conversation.metadata}"
        )
        conversations_db[conversation.id] = conversation
        logger.info(f"DBG_SS: Conversación {conversation.id} actualizada en memoria.")
        return True

    async def cleanup_old_conversations(self):
        """Elimina conversaciones más antiguas que el timeout (ejemplo en memoria)."""
        now = datetime.utcnow()
        timeout_delta = timedelta(seconds=settings.CONVERSATION_TIMEOUT)
        ids_to_remove = [
            conv_id
            for conv_id, conv in conversations_db.items()
            if isinstance(conv, Conversation)
            and (now - conv.created_at > timeout_delta)
        ]
        removed_count = 0
        for conv_id in ids_to_remove:
            try:
                if conv_id in conversations_db:
                    del conversations_db[conv_id]
                    logger.info(f"Conversación antigua eliminada: {conv_id}")
                    removed_count += 1
            except KeyError:
                pass
        if removed_count > 0:
            logger.info(
                f"Limpieza completada. {removed_count} conversaciones antiguas eliminadas."
            )


# Instancia global
storage_service = StorageService()
