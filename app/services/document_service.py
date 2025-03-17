# Mejoras para app/services/document_service.py

import os
import logging
import uuid
from typing import Optional, Dict, Any, List
from fastapi import UploadFile
import shutil
import re
import json

from app.config import settings

logger = logging.getLogger("hydrous-backend")


class DocumentService:
    """Servicio para gestionar y procesar documentos subidos por los usuarios"""

    def __init__(self):
        # Asegurarse de que exista el directorio de uploads
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        # Mapeo de documentos - para el MVP en memoria
        self.documents: Dict[str, Dict[str, Any]] = {}
        # Registro de documentos procesados por conversación
        self.conversation_document_insights: Dict[str, List[Dict[str, Any]]] = {}

    async def save_document(
        self, file: UploadFile, conversation_id: str
    ) -> Dict[str, Any]:
        """
        Guarda un documento subido por el usuario y extrae información preliminar

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
                "processed": False,
                "insights": {},
            }

            # Guardar en el registro de documentos
            self.documents[doc_id] = doc_info

            # Agregar el documento a la lista de la conversación para seguimiento
            if conversation_id not in self.conversation_document_insights:
                self.conversation_document_insights[conversation_id] = []

            # Extraer información preliminar según el tipo de archivo
            insights = await self._extract_preliminary_insights(
                file_path, file.content_type, file.filename
            )
            doc_info["insights"] = insights
            doc_info["processed"] = True

            # Guardar los insights para referencia futura
            self.conversation_document_insights[conversation_id].append(
                {
                    "doc_id": doc_id,
                    "filename": file.filename,
                    "content_type": file.content_type,
                    "insights": insights,
                }
            )

            return doc_info

        except Exception as e:
            logger.error(f"Error al guardar documento: {str(e)}")
            raise

    async def _extract_preliminary_insights(
        self, file_path: str, content_type: str, filename: str
    ) -> Dict[str, Any]:
        """
        Extrae información preliminar de un archivo según su tipo

        Args:
            file_path: Ruta al archivo guardado
            content_type: Tipo MIME del archivo
            filename: Nombre original del archivo

        Returns:
            Dict con información extraída del archivo
        """
        insights = {
            "summary": "",
            "document_type": "unknown",
            "extracted_text": "",
            "key_points": [],
            "relevance_to_water_treatment": "unknown",
        }

        try:
            # Detectar tipo de documento
            if content_type.startswith("image/"):
                insights["document_type"] = "image"
                insights["summary"] = (
                    f"Imagen que podría mostrar instalaciones, problemas de agua o equipos de tratamiento."
                )
                insights["relevance_to_water_treatment"] = "potential_visual_evidence"

            elif content_type == "application/pdf":
                # Extraer texto de PDF - aquí podrías usar PyPDF2 o similares
                # Para el MVP, solo indicamos que es un PDF
                insights["document_type"] = "pdf"
                insights["summary"] = (
                    f"Documento PDF que podría contener especificaciones técnicas, informes o datos de la empresa."
                )
                insights["relevance_to_water_treatment"] = "likely_technical_document"

            elif "spreadsheet" in content_type or filename.endswith(
                (".xlsx", ".xls", ".csv")
            ):
                insights["document_type"] = "spreadsheet"
                insights["summary"] = (
                    f"Hoja de cálculo que podría contener datos de consumo de agua, parámetros de calidad o costos."
                )
                insights["relevance_to_water_treatment"] = "likely_data_source"

            elif (
                content_type == "application/msword"
                or content_type
                == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ):
                insights["document_type"] = "text_document"
                insights["summary"] = (
                    f"Documento de texto que podría contener información sobre la empresa, procesos o especificaciones."
                )
                insights["relevance_to_water_treatment"] = "likely_descriptive_content"

            else:
                # Intentar leer como texto si es pequeño (menos de 1MB)
                file_size = os.path.getsize(file_path)
                if file_size < 1024 * 1024 and content_type.startswith("text/"):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            text_content = f.read(
                                10000
                            )  # Leer solo los primeros 10000 caracteres

                        insights["document_type"] = "text"
                        insights["extracted_text"] = (
                            text_content[:500] + "..."
                            if len(text_content) > 500
                            else text_content
                        )
                        insights["summary"] = (
                            f"Documento de texto con información que podría ser relevante para el proyecto."
                        )
                        insights["relevance_to_water_treatment"] = (
                            "potential_information"
                        )
                    except Exception as e:
                        logger.warning(
                            f"No se pudo leer el archivo como texto: {str(e)}"
                        )

            # Detectar palabras clave relacionadas con tratamiento de agua
            water_keywords = [
                "agua",
                "residual",
                "tratamiento",
                "filtración",
                "pH",
                "DBO",
                "DQO",
                "sólidos",
                "efluente",
                "contaminantes",
                "reutilización",
                "reciclaje",
                "consumo",
                "descarga",
                "osmosis",
                "membrana",
                "biológico",
            ]

            if insights["extracted_text"]:
                # Contar palabras clave en el texto extraído
                keyword_count = sum(
                    1
                    for keyword in water_keywords
                    if keyword.lower() in insights["extracted_text"].lower()
                )

                if keyword_count > 3:
                    insights["relevance_to_water_treatment"] = "highly_relevant"
                    insights["key_points"] = self._extract_key_points(
                        insights["extracted_text"], water_keywords
                    )

            return insights

        except Exception as e:
            logger.error(f"Error al extraer información del archivo: {str(e)}")
            return {
                "summary": f"Archivo recibido pero no se pudo procesar: {str(e)}",
                "document_type": "unknown",
                "relevance_to_water_treatment": "unknown",
            }

    def _extract_key_points(self, text: str, keywords: List[str]) -> List[str]:
        """
        Extrae frases clave que contienen palabras relacionadas con tratamiento de agua

        Args:
            text: Texto del documento
            keywords: Lista de palabras clave a buscar

        Returns:
            Lista de frases clave encontradas
        """
        key_points = []

        # Dividir en oraciones
        sentences = re.split(r"[.!?]+", text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Verificar si la oración contiene alguna palabra clave
            if any(keyword.lower() in sentence.lower() for keyword in keywords):
                # Limitar longitud de la oración
                if len(sentence) > 100:
                    sentence = sentence[:100] + "..."
                key_points.append(sentence)

                # Limitar a 5 puntos clave
                if len(key_points) >= 5:
                    break

        return key_points

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

    async def get_document_insights_for_conversation(
        self, conversation_id: str
    ) -> List[Dict[str, Any]]:
        """
        Obtiene los insights extraídos de todos los documentos de una conversación

        Args:
            conversation_id: ID de la conversación

        Returns:
            Lista de insights de documentos para esta conversación
        """
        return self.conversation_document_insights.get(conversation_id, [])

    async def get_document_insights_summary(self, conversation_id: str) -> str:
        """
        Genera un resumen de los insights de documentos para una conversación,
        formateado para su uso en el prompt del modelo de IA

        Args:
            conversation_id: ID de la conversación

        Returns:
            Texto de resumen formateado
        """
        insights = self.conversation_document_insights.get(conversation_id, [])

        if not insights:
            return ""

        summary = "INFORMACIÓN DE DOCUMENTOS PROPORCIONADOS POR EL USUARIO:\n\n"

        for i, doc in enumerate(insights, 1):
            summary += f"Documento {i}: {doc['filename']}\n"
            summary += f"Tipo: {doc['insights'].get('document_type', 'desconocido')}\n"
            summary += f"Resumen: {doc['insights'].get('summary', '')}\n"

            # Incluir puntos clave si existen
            key_points = doc["insights"].get("key_points", [])
            if key_points:
                summary += "Puntos clave identificados:\n"
                for point in key_points:
                    summary += f"- {point}\n"

            # Incluir parte del texto extraído si existe
            extracted_text = doc["insights"].get("extracted_text", "")
            if extracted_text:
                summary += "Extracto del texto:\n"
                summary += f'"{extracted_text[:200]}..."\n'

            summary += "\n"

        return summary

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

            # Eliminar insights si existen
            conversation_id = doc["conversation_id"]
            if conversation_id in self.conversation_document_insights:
                self.conversation_document_insights[conversation_id] = [
                    insight
                    for insight in self.conversation_document_insights[conversation_id]
                    if insight["doc_id"] != doc_id
                ]

            return True
        except Exception as e:
            logger.error(f"Error al eliminar documento {doc_id}: {str(e)}")
            return False


# Instancia global del servicio
document_service = DocumentService()
