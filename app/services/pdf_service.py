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

    async def generate_pdf_from_conversation(
        self, conversation: Conversation
    ) -> Optional[str]:
        """Genera un PDF basado en la propuesta encontrada en la conversación"""
        try:
            # Extraer propuesta de la conversación
            proposal_text = self._extract_proposal(conversation)
            if not proposal_text:
                logger.warning(
                    f"No se encontró propuesta en la conversación {conversation.id}"
                )
                # Crear un HTML básico en caso de no encontrar propuesta
                return self._create_basic_html(conversation)

            # Extraer información del cliente
            client_info = self._extract_client_info(conversation)

            # Crear nombre de archivo
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{conversation.id}_{timestamp}"
            html_path = os.path.join(self.pdf_dir, f"{filename}.html")

            # Convertir a HTML
            html_content = self._markdown_to_html(proposal_text, client_info)

            # Guardar HTML
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            # Intentar generar PDF
            try:
                # Intentar con weasyprint primero
                try:
                    from weasyprint import HTML

                    pdf_path = os.path.join(self.pdf_dir, f"{filename}.pdf")
                    HTML(string=html_content).write_pdf(pdf_path)
                    logger.info(f"PDF generado con weasyprint: {pdf_path}")
                    return pdf_path
                except ImportError:
                    logger.warning("weasyprint no disponible, probando con pdfkit")

                # Si no está weasyprint, intentar con pdfkit
                try:
                    import pdfkit

                    pdf_path = os.path.join(self.pdf_dir, f"{filename}.pdf")
                    pdfkit.from_string(html_content, pdf_path)
                    logger.info(f"PDF generado con pdfkit: {pdf_path}")
                    return pdf_path
                except ImportError:
                    logger.warning("pdfkit no disponible, devolviendo HTML")

                return html_path
            except Exception as e:
                logger.error(f"Error al generar PDF: {str(e)}", exc_info=True)
                return html_path

        except Exception as e:
            logger.error(f"Error general en generación de PDF: {str(e)}", exc_info=True)
            return self._create_basic_html(conversation)

    def _extract_proposal(self, conversation: Conversation) -> Optional[str]:
        """Extrae la propuesta de la conversación"""
        # Buscar mensaje del asistente que contenga la propuesta
        for msg in reversed(conversation.messages):
            if msg.role == "assistant" and "HYDROUS MANAGEMENT GROUP" in msg.content:
                return msg.content

        # Si no encontramos una propuesta formal, buscar un mensaje largo del asistente
        for msg in reversed(conversation.messages):
            if msg.role == "assistant" and len(msg.content) > 500:
                return msg.content

        return None

    def _extract_client_info(self, conversation: Conversation) -> Dict[str, str]:
        """Extrae información del cliente de la conversación"""
        client_info = {
            "name": "Cliente",
            "company": "Empresa",
            "sector": "Industrial",
            "location": "No especificado",
        }

        # Buscar mensajes del usuario para extraer información
        for msg in conversation.messages:
            if msg.role == "user":
                content = msg.content.lower()

                # Buscar posible nombre/empresa en la primera respuesta
                if len(client_info["name"]) < 10 and len(msg.content) < 100:
                    parts = msg.content.split()
                    if len(parts) > 0:
                        client_info["name"] = parts[0]
                    if len(parts) > 1:
                        client_info["company"] = " ".join(parts[1:])

                # Buscar ubicación
                if (
                    "ubicación" in content
                    or "ubicacion" in content
                    or "dirección" in content
                ):
                    client_info["location"] = msg.content

                # Buscar sector
                if "sector" in content or "industria" in content:
                    for sector in [
                        "textil",
                        "alimentos",
                        "bebidas",
                        "farmacéutica",
                        "municipal",
                    ]:
                        if sector in content:
                            client_info["sector"] = sector.capitalize()
                            break

        return client_info

    def _create_basic_html(self, conversation: Conversation) -> str:
        """Crea un HTML básico con la conversación para casos de error"""
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Propuesta Hydrous</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; margin: 20px; }
                h1 { color: #2c3e50; }
                .header { background-color: #2c3e50; color: white; padding: 20px; text-align: center; }
                .message { margin: 10px 0; padding: 10px; border-radius: 5px; }
                .user { background-color: #f1f1f1; }
                .assistant { background-color: #e3f2fd; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>HYDROUS - Propuesta de Solución</h1>
            </div>
            <h2>Resumen de Conversación</h2>
        """

        # Añadir mensajes de la conversación
        for msg in conversation.messages:
            if msg.role in ["user", "assistant"]:
                role_name = "Usuario" if msg.role == "user" else "Asistente"
                html_content += f'<div class="message {msg.role}"><strong>{role_name}:</strong><br>{msg.content}</div>'

        html_content += """
            <div class="footer">
                <p>Documento generado automáticamente por Hydrous Management Group</p>
            </div>
        </body>
        </html>
        """

        # Guardar HTML
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_path = os.path.join(
            self.pdf_dir, f"basico_{conversation.id}_{timestamp}.html"
        )
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return html_path

    def _markdown_to_html(self, markdown_text: str, client_info: Dict[str, str]) -> str:
        """Convierte Markdown a HTML estilizado para PDF"""
        try:
            # Intentar usar markdown2 si está disponible
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
            # Convertir párrafos
            body_html = re.sub(r"\n\n", r"</p><p>", body_html)
            body_html = "<p>" + body_html + "</p>"

        # HTML completo con estilo
        complete_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Propuesta Hydrous - {client_info['company']}</title>
            <style>
                body {{ 
                    font-family: Arial, sans-serif; 
                    line-height: 1.6; 
                    color: #333; 
                    margin: 0;
                    padding: 0;
                }}
                
                .container {{
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                
                h1 {{ color: #2c3e50; margin-top: 20px; }}
                h2 {{ color: #3498db; margin-top: 15px; }}
                
                .header {{ 
                    background-color: #2c3e50; 
                    color: white; 
                    padding: 20px; 
                    text-align: center; 
                }}
                
                .content {{
                    padding: 20px;
                }}
                
                table {{ 
                    border-collapse: collapse; 
                    width: 100%;
                    margin: 15px 0; 
                }}
                
                th, td {{ 
                    border: 1px solid #ddd; 
                    padding: 8px; 
                    text-align: left; 
                }}
                
                th {{ background-color: #f2f2f2; }}
                
                .footer {{ 
                    text-align: center; 
                    margin-top: 30px;
                    padding: 20px;
                    background-color: #f8f9fa;
                    color: #6c757d;
                }}
                
                .client-info {{
                    background-color: #e3f2fd;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 5px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>HYDROUS MANAGEMENT GROUP</h1>
                <p>Soluciones Personalizadas de Tratamiento de Aguas Residuales</p>
            </div>
            
            <div class="container">
                <div class="client-info">
                    <h2>Propuesta para: {client_info['company']}</h2>
                    <p><strong>Cliente:</strong> {client_info['name']}</p>
                    <p><strong>Ubicación:</strong> {client_info['location']}</p>
                    <p><strong>Sector:</strong> {client_info['sector']}</p>
                    <p><strong>Fecha:</strong> {datetime.now().strftime('%d/%m/%Y')}</p>
                </div>
                
                <div class="content">
                    {body_html}
                </div>
                
                <div class="footer">
                    <p>© {datetime.now().year} Hydrous Management Group</p>
                    <p>Este documento es una propuesta preliminar basada en la información proporcionada.</p>
                    <p>Los detalles finales pueden requerir un análisis técnico adicional.</p>
                </div>
            </div>
        </body>
        </html>
        """

        return complete_html


# Instancia global
pdf_service = PDFService()
