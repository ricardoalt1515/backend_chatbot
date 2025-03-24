import os
import logging
from typing import Optional
from datetime import datetime
import uuid

from app.models.conversation import Conversation
from app.config import settings

logger = logging.getLogger("hydrous")


class PDFService:
    """Servicio simplificado para generar PDF de propuestas"""

    def __init__(self):
        """Inicialización del servicio"""
        self.pdf_dir = os.path.join(settings.UPLOAD_DIR, "pdf")
        os.makedirs(self.pdf_dir, exist_ok=True)

    def get_pdf_path(self, conversation_id: str) -> Optional[str]:
        """Obtiene la ruta al PDF de una conversación si existe"""
        # Buscar PDF existente
        pdf_pattern = f"{conversation_id}*.pdf"
        for filename in os.listdir(self.pdf_dir):
            if filename.startswith(conversation_id):
                return os.path.join(self.pdf_dir, filename)
        return None

    async def generate_pdf_from_conversation(
        self, conversation: Conversation
    ) -> Optional[str]:
        """
        Genera un PDF basado en la propuesta encontrada en la conversación

        Args:
            conversation: Conversación que contiene la propuesta

        Returns:
            str: Ruta al archivo PDF generado, o None si hubo un error
        """
        try:
            # Extraer propuesta de la conversación
            proposal_text = self._extract_proposal(conversation)
            if not proposal_text:
                logger.warning(
                    f"No se encontró propuesta en la conversación {conversation.id}"
                )
                return None

            # Extraer información del cliente para nombre de archivo
            client_name = "Cliente"
            for msg in conversation.messages:
                if msg.role == "user" and len(msg.content) < 100:
                    client_name = msg.content.split()[0]
                    break

            # Crear nombre de archivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{conversation.id}_{timestamp}.pdf"
            pdf_path = os.path.join(self.pdf_dir, filename)

            # Convertir a HTML
            html_content = self._markdown_to_html(proposal_text, client_name)

            # Generar PDF
            html_path = os.path.join(
                self.pdf_dir, f"{conversation.id}_{timestamp}.html"
            )
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            # Intentar generar PDF con weasyprint o pdfkit si están disponibles
            try:
                import importlib

                # Intentar con weasyprint primero
                if importlib.util.find_spec("weasyprint"):
                    from weasyprint import HTML

                    HTML(string=html_content).write_pdf(pdf_path)
                    return pdf_path

                # Luego intentar con pdfkit
                if importlib.util.find_spec("pdfkit"):
                    import pdfkit

                    pdfkit.from_string(html_content, pdf_path)
                    return pdf_path

                # Si no hay generadores de PDF, devolver la ruta HTML
                logger.warning("No se encontraron generadores de PDF, devolviendo HTML")
                return html_path

            except Exception as e:
                logger.error(f"Error al generar PDF: {str(e)}")
                return html_path

        except Exception as e:
            logger.error(f"Error al generar PDF: {str(e)}")
            return None

    def _extract_proposal(self, conversation: Conversation) -> Optional[str]:
        """Extrae la propuesta de la conversación"""
        # Buscar mensaje del asistente con la propuesta
        for msg in reversed(conversation.messages):
            if msg.role == "assistant" and "Propuesta" in msg.content:
                return msg.content
        return None

    def _markdown_to_html(self, markdown_text: str, client_name: str) -> str:
        """Convierte Markdown a HTML estilizado para PDF"""
        # Intentar usar markdown2 si está disponible
        try:
            import markdown2

            body_html = markdown2.markdown(
                markdown_text, extras=["tables", "fenced-code-blocks"]
            )
        except ImportError:
            # Conversión básica si markdown2 no está disponible
            import re

            body_html = markdown_text
            # Convertir encabezados
            body_html = re.sub(
                r"^# (.*?)$", r"<h1>\1</h1>", body_html, flags=re.MULTILINE
            )
            body_html = re.sub(
                r"^## (.*?)$", r"<h2>\1</h2>", body_html, flags=re.MULTILINE
            )
            # Convertir negrita y cursiva
            body_html = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", body_html)
            body_html = re.sub(r"\*(.*?)\*", r"<em>\1</em>", body_html)
            # Convertir listas
            body_html = re.sub(
                r"^- (.*?)$", r"<li>\1</li>", body_html, flags=re.MULTILINE
            )

        # HTML completo con estilo
        complete_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Propuesta Hydrous - {client_name}</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                h1 {{ color: #2c3e50; }}
                h2 {{ color: #3498db; }}
                .header {{ 
                    background-color: #2c3e50; 
                    color: white; 
                    padding: 20px; 
                    text-align: center; 
                }}
                .footer {{ text-align: center; margin-top: 30px; color: #7f8c8d; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>HYDROUS</h1>
                <p>Soluciones de Tratamiento de Agua</p>
            </div>
            
            {body_html}
            
            <div class="footer">
                <p>Hydrous Management Group &copy; {datetime.now().year}</p>
                <p>Documento generado el {datetime.now().strftime('%d/%m/%Y')}</p>
            </div>
        </body>
        </html>
        """

        return complete_html


# Instancia global
pdf_service = PDFService()
