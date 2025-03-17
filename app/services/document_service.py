import os
import logging
import uuid
import re
from typing import Optional, Dict, Any, List
from fastapi import UploadFile
import shutil
import json

from app.config import settings

logger = logging.getLogger("hydrous-backend")


class DocumentService:
    """Servicio mejorado para gestionar y analizar documentos subidos por los usuarios"""

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
        Guarda un documento subido por el usuario y extrae información detallada

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

            # Extraer información detallada del documento
            insights = await self.extract_document_insights(
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

    async def extract_document_insights(
        self, file_path: str, content_type: str, filename: str
    ) -> Dict[str, Any]:
        """
        Extrae información detallada de documentos con análisis mejorado

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
            "parameters": {},
            "relevance": "unknown",
        }

        try:
            # Determinar tipo de documento y procesar según su tipo
            if content_type.startswith("image/"):
                insights["document_type"] = "image"
                insights["summary"] = (
                    "Imagen que podría mostrar instalaciones, problemas de agua o equipos de tratamiento."
                )
                insights["relevance"] = "potential_visual"

            elif content_type == "application/pdf":
                insights["document_type"] = "pdf"
                # Intentar extraer texto del PDF si está disponible PyPDF2
                try:
                    import PyPDF2

                    with open(file_path, "rb") as pdf_file:
                        pdf_reader = PyPDF2.PdfReader(pdf_file)
                        text = ""
                        for page_num in range(
                            min(5, len(pdf_reader.pages))
                        ):  # Primeras 5 páginas
                            text += pdf_reader.pages[page_num].extract_text() + "\n"

                        if text.strip():
                            insights["extracted_text"] = text[
                                :5000
                            ]  # Limitar a 5000 caracteres
                            insights["key_points"] = self._extract_key_points(text)
                            insights["parameters"] = self._extract_water_parameters(
                                text
                            )

                            if insights["parameters"]:
                                insights["relevance"] = "highly_relevant"
                                insights["summary"] = (
                                    f"Documento técnico con información sobre calidad del agua. Se encontraron {len(insights['parameters'])} parámetros relevantes."
                                )
                            else:
                                insights["relevance"] = "potentially_relevant"
                                insights["summary"] = (
                                    "Documento PDF que podría contener especificaciones técnicas o información sobre sistemas de agua."
                                )
                except ImportError:
                    insights["summary"] = (
                        "Documento PDF que podría contener especificaciones técnicas o información sobre sistemas de agua."
                    )
                    insights["relevance"] = "likely_technical"
                except Exception as e:
                    logger.warning(f"Error al procesar PDF: {str(e)}")
                    insights["summary"] = (
                        "Documento PDF recibido pero no se pudo procesar completamente."
                    )
                    insights["relevance"] = "likely_technical"

            elif "spreadsheet" in content_type or filename.endswith(
                (".xlsx", ".xls", ".csv")
            ):
                insights["document_type"] = "spreadsheet"

                # Procesar CSV si es posible
                if filename.endswith(".csv"):
                    try:
                        import csv

                        with open(file_path, "r", encoding="utf-8") as csv_file:
                            reader = csv.reader(csv_file)
                            rows = list(reader)

                            # Extraer encabezados y primeras filas para análisis
                            if rows:
                                headers = rows[0]
                                data_sample = rows[1 : min(6, len(rows))]

                                # Verificar si contiene datos de agua
                                water_related_headers = [
                                    h
                                    for h in headers
                                    if any(
                                        kw in h.lower()
                                        for kw in [
                                            "agua",
                                            "ph",
                                            "conductividad",
                                            "dbo",
                                            "dqo",
                                            "sst",
                                            "sólidos",
                                            "solidos",
                                            "consumo",
                                            "caudal",
                                            "flow",
                                            "water",
                                        ]
                                    )
                                ]

                                if water_related_headers:
                                    insights["relevance"] = "highly_relevant"
                                    insights["summary"] = (
                                        f"Hoja de cálculo con datos relacionados con agua. Columnas relevantes: {', '.join(water_related_headers[:3])}"
                                    )

                                    # Extraer algunos valores de ejemplo
                                    parameters = {}
                                    for header in water_related_headers[
                                        :5
                                    ]:  # Limitar a 5 columnas
                                        header_index = headers.index(header)
                                        sample_values = [
                                            row[header_index]
                                            for row in data_sample
                                            if len(row) > header_index
                                        ]
                                        if sample_values:
                                            # Guardar solo valores numéricos
                                            numeric_values = []
                                            for val in sample_values:
                                                try:
                                                    numeric_values.append(
                                                        float(val.replace(",", "."))
                                                    )
                                                except:
                                                    pass

                                            if numeric_values:
                                                avg_value = sum(numeric_values) / len(
                                                    numeric_values
                                                )
                                                parameters[header.lower()] = (
                                                    f"{avg_value:.2f}"
                                                )

                                    insights["parameters"] = parameters
                                else:
                                    insights["relevance"] = "potentially_relevant"
                                    insights["summary"] = (
                                        "Hoja de cálculo que podría contener datos relacionados con consumo de agua o parámetros de calidad."
                                    )
                    except Exception as e:
                        logger.warning(f"Error al procesar CSV: {str(e)}")
                        insights["summary"] = (
                            "Hoja de cálculo que podría contener datos de consumo de agua o parámetros de calidad."
                        )
                        insights["relevance"] = "likely_data"
                else:
                    insights["summary"] = (
                        "Hoja de cálculo que podría contener datos de consumo de agua o parámetros de calidad."
                    )
                    insights["relevance"] = "likely_data"

            elif content_type.startswith("text/") or filename.endswith(
                (".txt", ".md", ".log")
            ):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        text_content = f.read(10000)  # Limitar a 10000 caracteres

                    insights["document_type"] = "text"
                    insights["extracted_text"] = text_content[:2000] + (
                        "..." if len(text_content) > 2000 else ""
                    )

                    # Extraer parámetros clave del texto
                    insights["parameters"] = self._extract_water_parameters(
                        text_content
                    )
                    insights["key_points"] = self._extract_key_points(text_content)

                    # Determinar relevancia basada en parámetros encontrados
                    if insights["parameters"]:
                        insights["relevance"] = "highly_relevant"
                        insights["summary"] = (
                            f"Documento con información técnica sobre calidad del agua. Encontrados {len(insights['parameters'])} parámetros relevantes."
                        )
                    else:
                        water_keywords = [
                            "agua",
                            "tratamiento",
                            "residual",
                            "reciclaje",
                            "filtración",
                            "consumo",
                        ]
                        keyword_count = sum(
                            1 for kw in water_keywords if kw in text_content.lower()
                        )

                        if keyword_count >= 3:
                            insights["relevance"] = "potentially_relevant"
                            insights["summary"] = (
                                "Documento de texto con posible información sobre tratamiento de agua."
                            )
                        else:
                            insights["relevance"] = "unknown"
                            insights["summary"] = "Documento de texto recibido."
                except Exception as e:
                    logger.warning(f"Error al leer texto: {str(e)}")
                    insights["summary"] = (
                        "Documento de texto que no se pudo procesar completamente."
                    )
                    insights["relevance"] = "unknown"

            else:
                # Para otros tipos de archivo, información básica
                insights["summary"] = (
                    f"Archivo {content_type} que podría contener información relevante para el proyecto de agua."
                )
                insights["relevance"] = "unknown"

            return insights

        except Exception as e:
            logger.error(f"Error al procesar documento: {str(e)}")
            insights["summary"] = f"Archivo recibido pero no se pudo procesar: {str(e)}"
            return insights

    def _extract_water_parameters(self, text: str) -> Dict[str, str]:
        """
        Extrae parámetros de calidad del agua de un texto con patrones mejorados

        Args:
            text: Texto del documento

        Returns:
            Dict con parámetros de agua y sus valores
        """
        parameters = {}

        # Patrones mejorados para parámetros comunes de agua
        patterns = {
            "ph": r"pH\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "dbo": r"(?:DBO|BOD)[5]?\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "dqo": r"(?:DQO|COD)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "sst": r"(?:SST|TSS)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "sdt": r"(?:SDT|TDS)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "conductividad": r"(?:[Cc]onductividad|[Cc]onductivity)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "turbidez": r"(?:[Tt]urbidez|[Tt]urbidity)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "color": r"[Cc]olor\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "grasas_aceites": r"(?:[Gg]rasas y aceites|[Oo]il and [Gg]rease)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "nitrogeno": r"(?:[Nn]itrógeno|[Nn]itrogen)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "fosforo": r"(?:[Ff]ósforo|[Pp]hosphorus)\s*[:=]?\s*(\d+(?:\.\d+)?)",
            "cloro": r"(?:[Cc]loro|[Cc]hlorine)\s*[:=]?\s*(\d+(?:\.\d+)?)",
        }

        # Extraer unidades junto con valores cuando sea posible
        unit_pattern = r"(\d+(?:\.\d+)?)\s*(mg/[lL]|µS/cm|NTU|Pt-Co)"
        unit_matches = re.findall(unit_pattern, text)
        for value, unit in unit_matches:
            # Determinar el parámetro basado en la unidad
            if unit == "NTU":
                parameters["turbidez"] = f"{value} {unit}"
            elif unit == "Pt-Co":
                parameters["color"] = f"{value} {unit}"
            elif unit == "µS/cm":
                parameters["conductividad"] = f"{value} {unit}"

        # Buscar patrones específicos
        for param, pattern in patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                # Si ya tenemos este parámetro con unidad, no lo sobreescribimos
                if param not in parameters:
                    parameters[param] = matches[0]

        # Buscar patrones de consumo de agua
        flow_pattern = r"(?:caudal|consumo|flujo|flow|consumption).{0,30}?(\d+(?:[\.,]\d+)?)\s*(m3/d|m³/día|m3/día|litros/día|l/d)"
        flow_matches = re.findall(flow_pattern, text, re.IGNORECASE)
        if flow_matches:
            value, unit = flow_matches[0]
            parameters["caudal"] = f"{value.replace(',', '.')} {unit}"

        return parameters

    def _extract_key_points(self, text: str) -> List[str]:
        """
        Extrae frases clave relevantes para tratamiento de agua

        Args:
            text: Texto del documento

        Returns:
            Lista de frases clave encontradas
        """
        key_points = []

        # Palabras clave relacionadas con tratamiento de agua
        water_keywords = [
            "agua",
            "residual",
            "tratamiento",
            "filtración",
            "ph",
            "dbo",
            "dqo",
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
            "clarificación",
            "sistema",
            "planta",
            "proceso",
            "caudal",
            "flujo",
            "normativa",
            "regulación",
        ]

        # Dividir en oraciones
        sentences = re.split(r"[.!?]+", text)

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Verificar si la oración contiene alguna palabra clave
            keyword_count = sum(
                1 for keyword in water_keywords if keyword in sentence.lower()
            )

            if keyword_count >= 2:  # Debe contener al menos 2 palabras clave
                # Limitar longitud de la oración
                if len(sentence) > 150:
                    sentence = sentence[:150] + "..."

                key_points.append(sentence)

                # Limitar a 8 puntos clave
                if len(key_points) >= 8:
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

    def get_insights_for_conversation_sync(
        self, conversation_id: str
    ) -> List[Dict[str, Any]]:
        """
        Versión sincrónica de get_document_insights_for_conversation para uso interno

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
            doc_insights = doc["insights"]
            summary += f"Documento {i}: {doc['filename']}\n"
            summary += f"Tipo: {doc_insights.get('document_type', 'desconocido')}\n"

            # Añadir parámetros encontrados
            parameters = doc_insights.get("parameters", {})
            if parameters:
                summary += "Parámetros detectados:\n"
                for param, value in parameters.items():
                    summary += f"- {param}: {value}\n"

            # Incluir puntos clave si existen
            key_points = doc_insights.get("key_points", [])
            if key_points:
                summary += "Información relevante identificada:\n"
                for point in key_points[:3]:  # Limitar a 3 puntos por documento
                    summary += f"- {point}\n"

            # Incluir parte del texto extraído si existe
            extracted_text = doc_insights.get("extracted_text", "")
            if extracted_text and len(extracted_text) > 100:
                summary += "Extracto del texto:\n"
                summary += f'"{extracted_text[:150]}..."\n'

            summary += "\n"

        # Añadir resumen de datos clave para todos los documentos
        all_parameters = {}
        for doc in insights:
            all_parameters.update(doc["insights"].get("parameters", {}))

        if all_parameters:
            summary += (
                "RESUMEN DE PARÁMETROS CLAVE ENCONTRADOS EN TODOS LOS DOCUMENTOS:\n"
            )
            for param, value in all_parameters.items():
                summary += f"- {param}: {value}\n"

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
