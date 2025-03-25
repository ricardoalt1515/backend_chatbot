# app/services/feedback_service.py
import os
import json
import logging
from typing import Dict, List, Any
from datetime import datetime

from app.models.feedback import Feedback
from app.config import settings

logger = logging.getLogger("hydrous")


class FeedbackService:
    """Servicio para gestionar la retroalimentación del usuario"""

    def __init__(self):
        """Inicialización del servicio"""
        # Crear directorio para retroalimentación
        self.feedback_dir = os.path.join(settings.UPLOAD_DIR, "feedback")
        os.makedirs(self.feedback_dir, exist_ok=True)

        # Archivo para almacenar retroalimentación
        self.feedback_file = os.path.join(self.feedback_dir, "feedback.json")

        # Inicializar archivo si no existe
        if not os.path.exists(self.feedback_file):
            with open(self.feedback_file, "w", encoding="utf-8") as f:
                json.dump([], f)

    async def save_feedback(self, feedback: Feedback) -> bool:
        """Guarda la retroalimentación del usuario"""
        try:
            # Cargar retroalimentación existente
            feedback_list = []
            try:
                with open(self.feedback_file, "r", encoding="utf-8") as f:
                    feedback_list = json.load(f)
            except json.JSONDecodeError:
                logger.warning(
                    "Error al decodificar el archivo de retroalimentación. Creando nuevo archivo."
                )

            # Añadir nueva retroalimentación
            feedback_list.append(feedback.dict())

            # Guardar retroalimentación
            with open(self.feedback_file, "w", encoding="utf-8") as f:
                json.dump(feedback_list, f, default=self._json_serializer)

            logger.info(
                f"Retroalimentación guardada para mensaje {feedback.message_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Error al guardar retroalimentación: {str(e)}")
            return False

    async def get_feedback_for_conversation(
        self, conversation_id: str
    ) -> List[Dict[str, Any]]:
        """Obtiene toda la retroalimentación para una conversación específica"""
        try:
            with open(self.feedback_file, "r", encoding="utf-8") as f:
                all_feedback = json.load(f)

            return [
                item
                for item in all_feedback
                if item.get("conversation_id") == conversation_id
            ]

        except Exception as e:
            logger.error(f"Error al obtener retroalimentación: {str(e)}")
            return []

    async def get_average_rating(self) -> float:
        """Obtiene la calificación promedio de todas las retroalimentaciones"""
        try:
            with open(self.feedback_file, "r", encoding="utf-8") as f:
                all_feedback = json.load(f)

            if not all_feedback:
                return 0.0

            total_rating = sum(item.get("rating", 0) for item in all_feedback)
            return total_rating / len(all_feedback)

        except Exception as e:
            logger.error(f"Error al calcular calificación promedio: {str(e)}")
            return 0.0

    def _json_serializer(self, obj):
        """Serializador para objetos datetime"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")


# Instancia global
feedback_service = FeedbackService()
