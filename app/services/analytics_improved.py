# Crear archivo app/services/analytics_improved.py

from datetime import datetime
from typing import Dict, List, Any, Optional
import json
import os
import logging

logger = logging.getLogger("hydrous-analytics")


class ChatbotAnalytics:
    """Servicio mejorado para análisis y mejora continua del chatbot"""

    def __init__(self, analytics_dir: str = "analytics"):
        """
        Inicializa el servicio de análisis

        Args:
            analytics_dir: Directorio para almacenar datos de análisis
        """
        self.analytics_dir = analytics_dir
        os.makedirs(analytics_dir, exist_ok=True)

        # Archivo para conversiones
        self.conversion_file = os.path.join(analytics_dir, "conversions.json")
        if not os.path.exists(self.conversion_file):
            with open(self.conversion_file, "w") as f:
                json.dump([], f)

        # Archivo para errores y problemas
        self.issues_file = os.path.join(analytics_dir, "issues.json")
        if not os.path.exists(self.issues_file):
            with open(self.issues_file, "w") as f:
                json.dump([], f)

        # Métricas de uso
        self.usage_file = os.path.join(analytics_dir, "usage.json")
        if not os.path.exists(self.usage_file):
            with open(self.usage_file, "w") as f:
                json.dump(
                    {
                        "total_conversations": 0,
                        "completed_questionnaires": 0,
                        "pdf_downloads": 0,
                    },
                    f,
                )

    def log_conversation_completed(
        self, conversation_id: str, details: Dict[str, Any]
    ) -> None:
        """
        Registra una conversación completada con propuesta generada

        Args:
            conversation_id: ID de la conversación
            details: Detalles sobre la conversación y propuesta
        """
        try:
            # Cargar conversiones existentes
            with open(self.conversion_file, "r") as f:
                conversions = json.load(f)

            # Añadir nueva conversión
            conversions.append(
                {
                    "conversation_id": conversation_id,
                    "timestamp": datetime.now().isoformat(),
                    "details": details,
                }
            )

            # Guardar conversiones actualizadas
            with open(self.conversion_file, "w") as f:
                json.dump(conversions, f, indent=2)

            # Actualizar métricas de uso
            self._update_usage_metrics("completed_questionnaires")

            logger.info(f"Conversación completada registrada: {conversation_id}")
        except Exception as e:
            logger.error(f"Error al registrar conversación completada: {e}")

    def log_issue(
        self,
        conversation_id: str,
        issue_type: str,
        description: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Registra un problema o error en el chatbot

        Args:
            conversation_id: ID de la conversación
            issue_type: Tipo de problema (error, inconsistencia, etc.)
            description: Descripción del problema
            details: Detalles adicionales
        """
        try:
            # Cargar problemas existentes
            with open(self.issues_file, "r") as f:
                issues = json.load(f)

            # Añadir nuevo problema
            issues.append(
                {
                    "conversation_id": conversation_id,
                    "timestamp": datetime.now().isoformat(),
                    "issue_type": issue_type,
                    "description": description,
                    "details": details or {},
                }
            )

            # Guardar problemas actualizados
            with open(self.issues_file, "w") as f:
                json.dump(issues, f, indent=2)

            logger.warning(f"Problema registrado: {issue_type} en {conversation_id}")
        except Exception as e:
            logger.error(f"Error al registrar problema: {e}")

    def log_pdf_download(self, conversation_id: str) -> None:
        """
        Registra una descarga de PDF

        Args:
            conversation_id: ID de la conversación
        """
        try:
            self._update_usage_metrics("pdf_downloads")
            logger.info(f"Descarga de PDF registrada: {conversation_id}")
        except Exception as e:
            logger.error(f"Error al registrar descarga de PDF: {e}")

    def log_conversation_start(self) -> None:
        """Registra el inicio de una nueva conversación"""
        try:
            self._update_usage_metrics("total_conversations")
            logger.info("Nueva conversación registrada")
        except Exception as e:
            logger.error(f"Error al registrar inicio de conversación: {e}")

    def _update_usage_metrics(self, metric: str) -> None:
        """
        Actualiza una métrica de uso

        Args:
            metric: Nombre de la métrica a actualizar
        """
        try:
            # Cargar métricas existentes
            with open(self.usage_file, "r") as f:
                usage = json.load(f)

            # Actualizar métrica
            usage[metric] = usage.get(metric, 0) + 1

            # Guardar métricas actualizadas
            with open(self.usage_file, "w") as f:
                json.dump(usage, f, indent=2)
        except Exception as e:
            logger.error(f"Error al actualizar métrica {metric}: {e}")

    def get_usage_statistics(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas de uso del chatbot

        Returns:
            Dict: Estadísticas de uso
        """
        try:
            # Cargar métricas
            with open(self.usage_file, "r") as f:
                usage = json.load(f)

            # Calcular estadísticas adicionales
            if usage.get("total_conversations", 0) > 0:
                usage["completion_rate"] = (
                    usage.get("completed_questionnaires", 0)
                    / usage.get("total_conversations", 1)
                ) * 100
                usage["download_rate"] = (
                    usage.get("pdf_downloads", 0)
                    / usage.get("completed_questionnaires", 1)
                ) * 100

            return usage
        except Exception as e:
            logger.error(f"Error al obtener estadísticas de uso: {e}")
            return {}


# Instancia global del servicio
chatbot_analytics = ChatbotAnalytics()
