# app/services/storage_service.py
# ... (importaciones y logger) ...
# --- USAR METADATA ---
conversations_db: Dict[str, Conversation] = {}
# --------------------


class StorageService:

    async def create_conversation(self) -> Conversation:  # Quitar initial_state
        """Crea y almacena una nueva conversación con metadata inicial."""
        # Crear metadata inicial directamente aquí
        initial_metadata = {
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
        # Asegurarse que Conversation usa el default_factory para metadata si no se pasa
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
            # Asegurarse que metadata existe y tiene claves esperadas (opcionalmente merge con defaults)
            if not isinstance(conversation.metadata, dict):
                logger.warning(
                    f"Metadata inválida para {conversation_id}, reiniciando a default."
                )
                conversation.metadata = {  # Reset a default
                    "current_question_id": None,
                    "collected_data": {},
                    "selected_sector": None,  # ... etc
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
        conversation = await self.get_conversation(
            conversation_id
        )  # Log ya está en get
        if conversation:
            conversation.messages.append(message)
            logger.debug(
                f"DBG_SS: Mensaje '{message.role}' añadido a {conversation_id}."
            )
            # Limitar historial si se implementó en Conversation.add_message
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
        if not isinstance(
            conversation.metadata, dict
        ):  # Verificar que metadata sea dict
            logger.error(
                f"DBG_SS: Intento de guardar metadata inválida para {conversation.id}: {type(conversation.metadata)}"
            )
            return False

        logger.info(
            f"DBG_SS: GUARDANDO conversación {conversation.id}. Metadata a guardar: {conversation.metadata}"
        )

        # En memoria, simplemente reemplazamos
        conversations_db[conversation.id] = conversation
        logger.info(f"DBG_SS: Conversación {conversation.id} actualizada en memoria.")
        return True

    # ... (cleanup sin cambios) ...


storage_service = StorageService()
