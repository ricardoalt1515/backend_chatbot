# app/services/pdf_service.py
import logging
import os
import markdown
from xhtml2pdf import pisa  # type: ignore
from jinja2 import Environment, FileSystemLoader, select_autoescape

# --- AÑADIR ESTA IMPORTACIÓN ---
from typing import Optional

# -------------------------------

from app.config import settings

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
        @page { size: A4; margin: 1.5cm; }
        body { 
            font-family: Arial, sans-serif; 
            line-height: 1.5; 
            color: #333;
            margin: 0;
            padding: 0;
        }
        h1, h2, h3 { 
            color: #0056b3; 
            margin-top: 1.4em; 
            margin-bottom: 0.7em; 
        }
        h1 { 
            font-size: 1.8em;
            border-bottom: 2px solid #0056b3; 
            padding-bottom: 0.2em; 
        }
        h2 { 
            font-size: 1.5em;
            border-bottom: 1px solid #ccc; 
            padding-bottom: 0.1em; 
        }
        h3 { font-size: 1.2em; }
        p { margin: 0.7em 0; }
        
        /* Estilos para tablas */
        table.proposal-table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            page-break-inside: avoid;
        }
        table.proposal-table th {
            background-color: #f2f2f2;
            font-weight: bold;
            text-align: left;
            padding: 8px;
            border: 1px solid #ddd;
        }
        table.proposal-table td {
            padding: 8px;
            border: 1px solid #ddd;
            vertical-align: top;
        }
        
        /* Listas */
        ul { margin: 0.7em 0; padding-left: 2em; }
        li { margin-bottom: 0.3em; }
        
        /* Énfasis */
        strong { font-weight: bold; }
        em { font-style: italic; }
        
        /* Pie de página */
        .footer { 
            position: fixed; 
            bottom: 1cm; 
            left: 1.5cm; 
            right: 1.5cm; 
            text-align: center; 
            font-size: 0.8em; 
            color: #777; 
        }
        
        /* Encabezados de página y saltos */
        .page-break { page-break-after: always; }
        .no-break { page-break-inside: avoid; }
    </style>
</head>
<body>
    <div class="content">
        {{ content | safe }}
    </div>
    <div class="footer">
        Página <pdf:pagenumber> de <pdf:pagecount> |
        Documento generado por Hydrous AI. Las estimaciones son preliminares.
    </div>
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
            output_dir = os.path.dirname(output_path)
            os.makedirs(output_dir, exist_ok=True)

            with open(output_path, "wb") as pdf_file:
                pisa_status = pisa.CreatePDF(
                    html_content, dest=pdf_file, encoding="utf-8"
                )

            if pisa_status.err:
                logger.error(
                    f"Error durante la conversión HTML a PDF ({output_path}): {pisa_status.err}"
                )
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except Exception:
                        pass
                return False
            else:
                logger.info(f"PDF generado correctamente en: {output_path}")
                return True
        except Exception as e:
            logger.error(
                f"Excepción durante la conversión HTML a PDF ({output_path}): {e}",
                exc_info=True,
            )
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            return False

    def _format_proposal_text_to_html(self, proposal_text: str) -> str:
        """Mejora la conversión de texto/markdown a HTML, especialmente para tablas."""

        import markdown

        # Eliminar marcador final y cualquier texto previo a la propuesta real
        proposal_text = proposal_text.replace(
            "[PROPOSAL_COMPLETE: Propuesta lista para PDF]", ""
        ).strip()

        # Intentar identificar y eliminar cualquier texto conversacional previo
        if "Con esto, hemos completado todas las preguntas" in proposal_text:
            parts = proposal_text.split(
                "Con esto, hemos completado todas las preguntas"
            )
            if len(parts) > 1:
                # Tomar solo la parte después de ese texto
                proposal_text = parts[1]

        # Guardar para debug
        debug_dir = os.path.join(settings.UPLOAD_DIR, "debug")
        os.makedirs(debug_dir, exist_ok=True)
        with open(
            os.path.join(debug_dir, "proposal_pre_html.txt"), "w", encoding="utf-8"
        ) as f:
            f.write(proposal_text)

        # Conversión simple de markdown a HTML
        html_content = markdown.markdown(
            proposal_text, extensions=["tables", "fenced_code", "nl2br"]
        )

        # Guardar HTML para debug
        with open(
            os.path.join(debug_dir, "proposal_html.html"), "w", encoding="utf-8"
        ) as f:
            f.write(html_content)

        # Crear documento HTML completo con estilos
        complete_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Propuesta Hydrous</title>
            <style>
                @page {{ size: A4; margin: 2cm; }}
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                h1 {{ font-size: 20pt; color: #0056b3; border-bottom: 2px solid #0056b3; }}
                h2 {{ font-size: 16pt; color: #0056b3; border-bottom: 1px solid #ccc; }}
                h3 {{ font-size: 14pt; color: #0056b3; }}
                table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; }}
                th {{ background-color: #f2f2f2; }}
                .footer {{ position: fixed; bottom: 1cm; left: 2cm; right: 2cm; text-align: center; }}
            </style>
        </head>
        <body>
            {html_content}
            <div class="footer">
                Documento generado por Hydrous Management Group | Página <pdf:pagenumber> de <pdf:pagecount>
            </div>
        </body>
        </html>
        """

        return complete_html

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
        try:
            html_content = self._format_proposal_text_to_html(proposal_text)
        except Exception as fmt_err:
            logger.error(
                f"Error formateando propuesta a HTML para {conversation_id}: {fmt_err}",
                exc_info=True,
            )
            return None  # No se puede continuar si falla el formateo

        # Definir ruta de salida única para evitar colisiones si hay concurrencia
        # Podríamos usar uuid o timestamp
        import uuid

        unique_id = str(uuid.uuid4())[:8]
        pdf_filename = f"propuesta_{conversation_id}_{unique_id}.pdf"
        output_path = os.path.join(settings.UPLOAD_DIR, pdf_filename)

        # Convertir HTML a PDF
        success = self._html_to_pdf(html_content, output_path)

        if success:
            # Opcional: Limpiar PDFs antiguos para esta conversation_id?
            return output_path
        else:
            logger.error(f"Falló la generación de PDF para {conversation_id}")
            return None


# Instancia global
pdf_service = PDFService()
