# app/services/pdf_service.py (actualizado)
import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import re

from app.models.conversation import Conversation
from app.config import settings

logger = logging.getLogger("hydrous")


class EnhancedPDFService:
    """Servicio mejorado para generar PDFs de propuestas"""

    def __init__(self):
        """Inicialización del servicio"""
        # Crear directorio para PDFs
        self.pdf_dir = os.path.join(settings.UPLOAD_DIR, "pdf")
        os.makedirs(self.pdf_dir, exist_ok=True)

        # Crear directorio para recursos (imágenes, CSS, etc.)
        self.resources_dir = os.path.join(settings.UPLOAD_DIR, "resources")
        os.makedirs(self.resources_dir, exist_ok=True)

    async def generate_pdf(self, conversation: Conversation) -> Optional[str]:
        """Genera un PDF a partir de una propuesta en la conversación"""
        try:
            # Extraer información del cliente
            client_info = self._extract_client_info(conversation)

            # Extraer propuesta
            proposal_text = self._extract_proposal_text(conversation)
            if not proposal_text:
                logger.warning(
                    f"No se encontró propuesta en la conversación {conversation.id}"
                )
                return None

            # Generar identificador único para la propuesta
            proposal_id = (
                f"HYD-{datetime.now().strftime('%Y%m%d')}-{conversation.id[:8]}"
            )

            # Convertir a HTML con diseño mejorado
            html_content = self._markdown_to_html_enhanced(
                proposal_text, client_info, proposal_id
            )

            # Generar nombre de archivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            client_name = client_info.get("name", "Cliente").replace(" ", "_")
            html_path = os.path.join(
                self.pdf_dir, f"Propuesta_Hydrous_{client_name}_{timestamp}.html"
            )

            # Guardar HTML
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            # Intentar generar PDF
            pdf_path = self._generate_pdf_from_html(html_path, client_name, timestamp)

            # Almacenar ruta del PDF en los metadatos de la conversación
            if pdf_path:
                conversation.metadata["pdf_path"] = pdf_path
                conversation.metadata["pdf_generated_at"] = datetime.now().isoformat()
                return pdf_path
            return html_path

        except Exception as e:
            logger.error(f"Error en generate_pdf: {str(e)}")
            return None

    async def get_pdf_data(
        self, conversation_id: str
    ) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
        """
        Obtiene los datos binarios del PDF para engrega diracta o como data URL

        Returns:
            Tuple: (pdf_data, filename, content_type)
        """
        from app.services.storage_service import storage_service

        try:
            # Obtener conversación
            conversation = await storage_service.get_conversation(conversation_id)
            if not conversation:
                logger.error(f"Conversación no encontrada: {conversation_id}")
                return None, None, None

            # Verificar si ya hay un PDF generado
            pdf_path = conversation.metadata.get("pdf_path")
            if not pdf_path or not os.path.exists(pdf_path):
                # Generar PDF si no existe
                pdf_path = await self.generate_pdf(conversation)

            if not pdf_path:
                logger.error(f"No se pudo generar PDF para {conversation_id}")
                return None, None, None

            # Determinar tipo de contenido
            is_pdf = pdf_path.endswith(".pdf")
            content_type = "application/pdf" if is_pdf else "text/html"

            # Prepara nombre del archivo
            client_name = "Cliente"
            if conversation.questionnaire_state.key_entities.get("company_name"):
                client_name = conversation.questionnaire_state.key_entities[
                    "company_name"
                ]
            filename = f"Propuesta_Hydrous_{client_name}.{'pdf' if is_pdf else 'html'}"

            # Leer el archivo
            with open(pdf_path, "rb") as f:
                file_data = f.read()

            return file_data, filename, content_type

        except Exception as e:
            logger.error(f"Error al obtener datos del PDF: {str(e)}")

    async def get_pdf_data_url(self, conversation_id: str) -> Optional[Dict[str, str]]:
        """
        Genera una data URL para el PDF o HTML

        Returns:
            Dict con data_url, filename y content_type
        """
        pdf_data, filename, content_type = await self.get_pdf_data(conversation_id)

        if not pdf_data:
            return None

        # Convertir a Base64
        b64_data = base64.b64encode(pdf_data).decode("utf-8")
        data_url = f"data:{content_type};base64,{b64_data}"

        return {
            "data_url": data_url,
            "filename": filename,
            "content_type": content_type,
        }

    def _extract_client_info(self, conversation: Conversation) -> Dict[str, Any]:
        """Extrae información del cliente de la conversación"""
        client_info = {
            "name": "Cliente",
            "location": "No especificada",
            "sector": "No especificado",
            "contact": "",
        }

        # Intentar extraer desde el estado del cuestionario
        if hasattr(conversation, "questionnaire_state"):
            key_entities = getattr(conversation.questionnaire_state, "key_entities", {})
            answers = getattr(conversation.questionnaire_state, "answers", {})

            if key_entities.get("company_name"):
                client_info["name"] = key_entities["company_name"]
            if key_entities.get("location"):
                client_info["location"] = key_entities["location"]
            if getattr(conversation.questionnaire_state, "sector", None):
                client_info["sector"] = conversation.questionnaire_state.sector

        # Analizar los mensajes en busca de información si no la tenemos aún
        if (
            client_info["name"] == "Cliente"
            or client_info["location"] == "No especificada"
        ):
            for msg in conversation.messages:
                if msg.role == "user":
                    # Buscar nombre de empresa
                    if client_info["name"] == "Cliente":
                        company_match = re.search(
                            r"(?:empresa|compañía|proyecto)[\s:]+([a-zA-Z0-9\s]+)",
                            msg.content,
                            re.IGNORECASE,
                        )
                        if company_match:
                            client_info["name"] = company_match.group(1).strip()

                    # Buscar ubicación
                    if client_info["location"] == "No especificada":
                        location_match = re.search(
                            r"(?:ubicación|ubicacion|localización|ciudad)[\s:]+([a-zA-Z0-9\s,]+)",
                            msg.content,
                            re.IGNORECASE,
                        )
                        if location_match:
                            client_info["location"] = location_match.group(1).strip()

        return client_info

    def _extract_proposal_text(self, conversation: Conversation) -> Optional[str]:
        """Extrae el texto de la propuesta de una conversación"""
        # Buscar un mensaje del asistente que contenga la propuesta
        for msg in reversed(conversation.messages):
            if msg.role == "assistant" and "Propuesta" in msg.content:
                # Verificar si la propuesta parece completa (tiene secciones clave)
                if all(
                    section in msg.content
                    for section in ["Introducción", "Objetivo", "CAPEX", "ROI"]
                ):
                    return msg.content
                # Si encontramos una propuesta parcial, seguir buscando una más completa

        # Si no encontramos una propuesta completa, buscar una parcial
        for msg in reversed(conversation.messages):
            if msg.role == "assistant" and "Propuesta" in msg.content:
                return msg.content

        return None

    def _markdown_to_html_enhanced(
        self, markdown_text: str, client_info: Dict[str, Any], proposal_id: str
    ) -> str:
        """Convierte texto markdown a HTML con diseño profesional mejorado"""
        try:
            # Intentar usar markdown2 si está disponible
            try:
                import markdown2

                html_body = markdown2.markdown(
                    markdown_text, extras=["tables", "fenced-code-blocks"]
                )
            except ImportError:
                # Conversión básica si markdown2 no está disponible
                html_body = self._basic_markdown_to_html(markdown_text)

            # Plantilla HTML completa con estilos profesionales
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Propuesta Hydrous - {client_info["name"]}</title>
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
                    
                    body {{ 
                        font-family: 'Roboto', Arial, sans-serif; 
                        line-height: 1.6; 
                        color: #333; 
                        margin: 0;
                        padding: 0;
                        background-color: #f9fafb;
                    }}
                    
                    .container {{
                        max-width: 800px;
                        margin: 0 auto;
                        padding: 20px 40px;
                        background-color: white;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }}
                    
                    .header {{ 
                        position: relative;
                        background-color: #1a5276; 
                        color: white; 
                        padding: 30px 40px; 
                        margin: 0 0 30px 0;
                    }}
                    
                    .header .logo {{
                        height: 60px;
                        margin-bottom: 10px;
                    }}
                    
                    .header h1 {{
                        margin: 5px 0;
                        font-size: 28px;
                        font-weight: 500;
                    }}
                    
                    .header p {{
                        margin: 5px 0;
                        font-size: 16px;
                        opacity: 0.9;
                    }}
                    
                    .proposal-id {{
                        position: absolute;
                        top: 20px;
                        right: 40px;
                        font-size: 14px;
                        opacity: 0.9;
                    }}
                    
                    .client-info {{
                        margin-bottom: 30px;
                        padding: 20px;
                        background-color: #f1f8ff;
                        border-left: 4px solid #1a5276;
                    }}
                    
                    .client-info p {{
                        margin: 5px 0;
                    }}
                    
                    h1, h2, h3, h4 {{ 
                        color: #1a5276;
                        margin-top: 30px;
                    }}
                    
                    h1 {{ font-size: 24px; }}
                    h2 {{ font-size: 20px; }}
                    h3 {{ font-size: 18px; }}
                    
                    table {{ 
                        width: 100%;
                        border-collapse: collapse; 
                        margin: 20px 0;
                    }}
                    
                    th, td {{ 
                        padding: 12px 15px;
                        border: 1px solid #ddd;
                    }}
                    
                    th {{
                        background-color: #1a5276;
                        color: white;
                        font-weight: 500;
                    }}
                    
                    tr:nth-child(even) {{
                        background-color: #f9f9f9;
                    }}
                    
                    .highlight {{
                        background-color: #ebf5ff;
                        padding: 15px;
                        border-radius: 5px;
                        margin: 20px 0;
                    }}
                    
                    .footer {{ 
                        text-align: center;
                        margin-top: 40px;
                        padding-top: 20px;
                        border-top: 1px solid #ddd;
                        color: #777;
                        font-size: 14px;
                    }}
                    
                    .watermark {{
                        position: fixed;
                        bottom: 5cm;
                        right: 5cm;
                        opacity: 0.03;
                        transform: rotate(-45deg);
                        font-size: 120px;
                        color: #1a5276;
                        z-index: -1;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <div class="proposal-id">{proposal_id}</div>
                        <!-- <img src="hydrous_logo.png" alt="Hydrous Logo" class="logo"> -->
                        <h1>HYDROUS MANAGEMENT GROUP</h1>
                        <p>Soluciones de Tratamiento de Agua</p>
                    </div>
                    
                    <div class="client-info">
                        <p><strong>Cliente:</strong> {client_info["name"]}</p>
                        <p><strong>Ubicación:</strong> {client_info["location"]}</p>
                        <p><strong>Sector:</strong> {client_info["sector"]}</p>
                        <p><strong>Fecha:</strong> {datetime.now().strftime('%d/%m/%Y')}</p>
                    </div>
                    
                    {html_body}
                    
                    <div class="footer">
                        <p>© {datetime.now().year} Hydrous Management Group. Todos los derechos reservados.</p>
                        <p>Esta propuesta es confidencial y está destinada únicamente para el uso del destinatario.</p>
                        <p>Los costos y especificaciones finales pueden variar tras un estudio detallado.</p>
                    </div>
                </div>
                
                <div class="watermark">HYDROUS</div>
            </body>
            </html>
            """

            return html

        except Exception as e:
            logger.error(f"Error al convertir Markdown a HTML: {str(e)}")
            return f"<pre>{markdown_text}</pre>"

    def _basic_markdown_to_html(self, markdown_text: str) -> str:
        """Conversión básica de Markdown a HTML sin dependencias externas"""
        html = markdown_text

        # Encabezados
        html = re.sub(r"^# (.*?)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
        html = re.sub(r"^## (.*?)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
        html = re.sub(r"^### (.*?)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)

        # Negrita y cursiva
        html = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html)
        html = re.sub(r"\*(.*?)\*", r"<em>\1</em>", html)

        # Listas
        html = re.sub(r"^- (.*?)$", r"<li>\1</li>", html, flags=re.MULTILINE)
        # Agrupar elementos li en ul
        li_pattern = r"(<li>.*?</li>)+"
        html = re.sub(li_pattern, r"<ul>\g<0></ul>", html)

        # Tablas simples - esto es una aproximación básica
        table_pattern = r"^\|(.*?)\|[\r\n]?\|[-:| ]+\|[\r\n]((?:\|.*?\|[\r\n]?)+)"

        def replace_table(match):
            header = match.group(1)
            rows = match.group(2).strip().split("\n")

            header_cells = [cell.strip() for cell in header.split("|") if cell.strip()]
            header_html = (
                "<tr>"
                + "".join([f"<th>{cell}</th>" for cell in header_cells])
                + "</tr>"
            )

            rows_html = ""
            for row in rows:
                cells = [cell.strip() for cell in row.split("|") if cell.strip()]
                rows_html += (
                    "<tr>" + "".join([f"<td>{cell}</td>" for cell in cells]) + "</tr>"
                )

            return f"<table>{header_html}{rows_html}</table>"

        html = re.sub(
            table_pattern, replace_table, html, flags=re.MULTILINE | re.DOTALL
        )

        # Párrafos
        paragraphs = html.split("\n\n")
        for i, paragraph in enumerate(paragraphs):
            if not paragraph.startswith("<") and paragraph.strip():
                paragraphs[i] = f"<p>{paragraph}</p>"

        html = "\n\n".join(paragraphs)

        return html

    def _generate_pdf_from_html(
        self, html_path: str, client_name: str, timestamp: str
    ) -> Optional[str]:
        """Genera un archivo PDF a partir del HTML usando la biblioteca disponible"""
        pdf_path = os.path.join(
            self.pdf_dir, f"Propuesta_Hydrous_{client_name}_{timestamp}.pdf"
        )

        try:
            # Intentar con WeasyPrint
            try:
                from weasyprint import HTML

                HTML(filename=html_path).write_pdf(pdf_path)
                logger.info(f"PDF generado con WeasyPrint: {pdf_path}")
                return pdf_path
            except ImportError:
                logger.warning(
                    "WeasyPrint no está disponible, intentando con pdfkit..."
                )

            # Intentar con pdfkit
            try:
                import pdfkit

                pdfkit.from_file(html_path, pdf_path)
                logger.info(f"PDF generado con pdfkit: {pdf_path}")
                return pdf_path
            except ImportError:
                logger.warning(
                    "pdfkit no está disponible, intentando con otros métodos..."
                )

            # Aquí se podrían añadir más métodos alternativos

            logger.warning("No se pudo generar PDF. Se usará HTML como alternativa.")
            return None

        except Exception as e:
            logger.error(f"Error al generar PDF: {str(e)}")
            return None


# Instancia global
pdf_service = PDFService()
