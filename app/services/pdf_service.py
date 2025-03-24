# app/services/pdf_service.py
import os
import logging
from typing import Optional
from datetime import datetime
import re

from app.models.conversation import Conversation
from app.config import settings

logger = logging.getLogger("hydrous")


class PDFService:
    """Servicio para generar PDFs de propuestas"""

    def __init__(self):
        """Inicialización del servicio"""
        # Crear directorio para PDFs
        self.pdf_dir = os.path.join(settings.UPLOAD_DIR, "pdf")
        os.makedirs(self.pdf_dir, exist_ok=True)

    async def generate_pdf(self, conversation: Conversation) -> Optional[str]:
        """Genera un PDF a partir de una propuesta en la conversación"""
        try:
            # Extraer propuesta
            proposal_text = self._extract_proposal_text(conversation)
            if not proposal_text:
                logger.warning(
                    f"No se encontró propuesta en la conversación {conversation.id}"
                )
                return None

            # Convertir a HTML
            html_content = self._markdown_to_html(proposal_text)

            # Generar nombre de archivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_path = os.path.join(
                self.pdf_dir, f"{conversation.id}_{timestamp}.html"
            )

            # Guardar HTML
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            # Intentar generar PDF si alguna biblioteca está disponible
            try:
                pdf_path = os.path.join(
                    self.pdf_dir, f"{conversation.id}_{timestamp}.pdf"
                )

                # Intentar con weasyprint
                try:
                    from weasyprint import HTML

                    HTML(string=html_content).write_pdf(pdf_path)
                    return pdf_path
                except ImportError:
                    pass

                # Intentar con pdfkit
                try:
                    import pdfkit

                    pdfkit.from_string(html_content, pdf_path)
                    return pdf_path
                except ImportError:
                    pass

                # Si no hay generadores de PDF, devolver HTML
                return html_path

            except Exception as e:
                logger.error(f"Error al generar PDF: {str(e)}")
                return html_path

        except Exception as e:
            logger.error(f"Error en generate_pdf: {str(e)}")
            return None

    def _extract_proposal_text(self, conversation: Conversation) -> Optional[str]:
        """Extrae el texto de la propuesta de una conversación"""
        # Buscar un mensaje del asistente que contenga la propuesta
        for msg in reversed(conversation.messages):
            if msg.role == "assistant" and "Propuesta" in msg.content:
                return msg.content

        return None

    def _markdown_to_html(self, markdown_text: str) -> str:
        """Convierte texto markdown a HTML"""
        try:
            # Intentar usar markdown2 si está disponible
            try:
                import markdown2

                html_body = markdown2.markdown(
                    markdown_text, extras=["tables", "fenced-code-blocks"]
                )
            except ImportError:
                # Conversión básica si markdown2 no está disponible
                html_body = markdown_text
                # Encabezados
                html_body = re.sub(
                    r"^# (.*?)$", r"<h1>\1</h1>", html_body, flags=re.MULTILINE
                )
                html_body = re.sub(
                    r"^## (.*?)$", r"<h2>\1</h2>", html_body, flags=re.MULTILINE
                )
                # Negrita y cursiva
                html_body = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html_body)
                html_body = re.sub(r"\*(.*?)\*", r"<em>\1</em>", html_body)
                # Listas
                html_body = re.sub(
                    r"^- (.*?)$", r"<li>\1</li>", html_body, flags=re.MULTILINE
                )

            # Plantilla HTML completa con estilos
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Propuesta Hydrous</title>
                <style>
                    body {{ 
                        font-family: Arial, sans-serif; 
                        line-height: 1.6; 
                        color: #333; 
                        margin: 0; 
                        padding: 20px; 
                    }}
                    h1 {{ color: #2c3e50; }}
                    h2 {{ color: #3498db; }}
                    table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                    th {{ background-color: #f2f2f2; }}
                    .header {{ 
                        background-color: #2c3e50; 
                        color: white; 
                        padding: 20px; 
                        text-align: center; 
                        margin-bottom: 20px;
                    }}
                    .footer {{ 
                        margin-top: 30px; 
                        text-align: center; 
                        font-size: 0.8em; 
                        color: #7f8c8d; 
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>HYDROUS</h1>
                    <p>Soluciones de Tratamiento de Agua</p>
                </div>
                
                {html_body}
                
                <div class="footer">
                    <p>Hydrous Management Group &copy; {datetime.now().year}</p>
                    <p>Documento generado el {datetime.now().strftime('%d/%m/%Y')}</p>
                </div>
            </body>
            </html>
            """

            return html

        except Exception as e:
            logger.error(f"Error al convertir Markdown a HTML: {str(e)}")
            return f"<pre>{markdown_text}</pre>"


# Instancia global
pdf_service = PDFService()
