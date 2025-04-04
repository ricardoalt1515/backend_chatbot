# app/services/pdf_service.py
import logging
import os
from xhtml2pdf import pisa  # type: ignore # pip install xhtml2pdf
from jinja2 import (
    Environment,
    FileSystemLoader,
    select_autoescape,
)  # pip install Jinja2

from app.config import settings

# Quitar dependencia de 'Conversation' si solo necesitamos texto
# from app.models.conversation import Conversation

logger = logging.getLogger("hydrous")


class PDFService:

    def __init__(self):
        # Configurar Jinja2 para cargar plantillas HTML (opcional pero recomendado)
        template_dir = os.path.join(os.path.dirname(__file__), "../templates")
        if not os.path.exists(template_dir):
            os.makedirs(template_dir)
            # Crear un archivo base si no existe
            base_html_path = os.path.join(template_dir, "proposal_base.html")
            if not os.path.exists(base_html_path):
                with open(base_html_path, "w", encoding="utf-8") as f:
                    f.write(
                        """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Propuesta Hydrous</title>
    <style>
        body { font-family: sans-serif; line-height: 1.4; padding: 20px; }
        h1, h2, h3 { color: #0056b3; }
        h1 { border-bottom: 2px solid #0056b3; padding-bottom: 10px; }
        pre { background-color: #f8f8f8; border: 1px solid #ddd; padding: 10px; white-space: pre-wrap; word-wrap: break-word; }
        /* Añade más estilos según necesites */
    </style>
</head>
<body>
    <h1>Propuesta de Solución de Agua - Hydrous AI</h1>
    <div>
        {{ content | safe }} {# El contenido de la propuesta se inyectará aquí #}
    </div>
    <hr>
    <p><em>Documento generado por Hydrous AI. Las estimaciones son preliminares.</em></p>
</body>
</html>
                      """
                    )
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def _html_to_pdf(self, html_content: str, output_path: str) -> bool:
        """Convierte contenido HTML a un archivo PDF."""
        try:
            # Asegurarse que el directorio de salida existe
            output_dir = os.path.dirname(output_path)
            os.makedirs(output_dir, exist_ok=True)

            with open(output_path, "wb") as pdf_file:
                pisa_status = pisa.CreatePDF(
                    html_content, dest=pdf_file, encoding="utf-8"
                )

            if pisa_status.err:
                logger.error(
                    f"Error durante la conversión HTML a PDF: {pisa_status.err}"
                )
                # Intentar eliminar archivo parcial si falló
                if os.path.exists(output_path):
                    os.remove(output_path)
                return False
            else:
                logger.info(f"PDF generado correctamente en: {output_path}")
                return True
        except Exception as e:
            logger.error(
                f"Excepción durante la conversión HTML a PDF: {e}", exc_info=True
            )
            # Intentar eliminar archivo parcial si falló
            if os.path.exists(output_path):
                os.remove(output_path)
            return False

    def _format_proposal_text_to_html(self, proposal_text: str) -> str:
        """Intenta convertir el texto markdown-like a HTML básico."""
        # Reemplazos simples (puedes usar una librería Markdown si prefieres)
        html_content = proposal_text.replace("\n\n", "<br><p>")  # Párrafos aproximados
        html_content = html_content.replace("\n", "<br>")  # Saltos de línea

        # Encabezados (simplificado)
        import re

        html_content = re.sub(
            r"^# (.*?)$", r"<h1>\1</h1>", html_content, flags=re.MULTILINE
        )
        html_content = re.sub(
            r"^## (.*?)$", r"<h2>\1</h2>", html_content, flags=re.MULTILINE
        )
        html_content = re.sub(
            r"^### (.*?)$", r"<h3>\1</h3>", html_content, flags=re.MULTILINE
        )

        # Negritas
        html_content = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html_content)
        # Listas (muy básico)
        html_content = re.sub(
            r"^\* (.*?)$", r"<li>\1</li>", html_content, flags=re.MULTILINE
        )
        html_content = re.sub(
            r"(<li>.*?</li>)+", r"<ul>\g<0></ul>", html_content, flags=re.DOTALL
        )  # Envolver en <ul>

        # Quitar marcador final del HTML visible
        html_content = html_content.replace(
            "[PROPOSAL_COMPLETE: Propuesta lista para PDF]", ""
        )

        # Envolver en plantilla Jinja
        try:
            template = self.jinja_env.get_template("proposal_base.html")
            return template.render(content=html_content)
        except Exception as e:
            logger.error(f"Error al renderizar plantilla Jinja2: {e}")
            # Fallback a HTML simple si falla la plantilla
            return f"<html><head><title>Propuesta</title></head><body><pre>{proposal_text}</pre></body></html>"

    async def generate_pdf_from_text(
        self, conversation_id: str, proposal_text: str
    ) -> Optional[str]:
        """Genera un PDF a partir del texto de la propuesta ya generado."""
        if not proposal_text:
            logger.error(
                f"Intento de generar PDF sin texto de propuesta para {conversation_id}"
            )
            return None

        # Convertir el texto (posiblemente markdown) a HTML
        html_content = self._format_proposal_text_to_html(proposal_text)

        # Definir ruta de salida
        pdf_filename = f"propuesta_{conversation_id}.pdf"
        output_path = os.path.join(settings.UPLOAD_DIR, pdf_filename)

        # Convertir HTML a PDF
        success = self._html_to_pdf(html_content, output_path)

        if success:
            return output_path
        else:
            logger.error(f"Falló la generación de PDF para {conversation_id}")
            return None


# Instancia global
pdf_service = PDFService()
