# app/services/pdf_service.py
import logging
import os
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
        @page { size: A4; margin: 1.5cm; } /* Estilo para PDF */
        body { font-family: sans-serif; line-height: 1.4; padding: 0; margin: 0; } /* Ajustar padding/margin para @page */
        h1, h2, h3 { color: #0056b3; margin-top: 1.2em; margin-bottom: 0.6em; }
        h1 { border-bottom: 2px solid #0056b3; padding-bottom: 5px; font-size: 1.8em;}
        h2 { border-bottom: 1px solid #ccc; padding-bottom: 3px; font-size: 1.5em;}
        h3 { font-size: 1.2em; }
        p { margin-top: 0.5em; margin-bottom: 0.5em; }
        pre { background-color: #f8f8f8; border: 1px solid #ddd; padding: 10px; white-space: pre-wrap; word-wrap: break-word; font-size: 0.9em; }
        ul { margin-top: 0.5em; margin-bottom: 0.5em; padding-left: 25px; }
        li { margin-bottom: 0.3em; }
        strong { font-weight: bold; }
        em { font-style: italic; }
        .footer { position: fixed; bottom: 1cm; left: 1.5cm; right: 1.5cm; text-align: center; font-size: 0.8em; color: #777; }
        /* Añade más estilos según necesites */
    </style>
</head>
<body>
    <!-- Contenido principal -->
    <div>
        {{ content | safe }} {# El contenido de la propuesta se inyectará aquí #}
    </div>

    <!-- Pie de página -->
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
        """Intenta convertir el texto markdown-like a HTML básico."""
        # Reemplazos simples (puedes usar una librería Markdown si prefieres: pip install markdown)
        # import markdown
        # html_content = markdown.markdown(proposal_text) # Esto sería más robusto

        # --- Conversión manual simple ---
        html_content = proposal_text

        # Quitar marcador final ANTES de procesar
        html_content = html_content.replace(
            "[PROPOSAL_COMPLETE: Propuesta lista para PDF]", ""
        )
        html_content = html_content.strip()

        # Encabezados
        import re

        html_content = re.sub(
            r"^### (.*?)$", r"<h3>\1</h3>", html_content, flags=re.MULTILINE
        )
        html_content = re.sub(
            r"^## (.*?)$", r"<h2>\1</h2>", html_content, flags=re.MULTILINE
        )
        html_content = re.sub(
            r"^# (.*?)$", r"<h1>\1</h1>", html_content, flags=re.MULTILINE
        )

        # Negritas
        html_content = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html_content)
        # Énfasis (itálicas)
        html_content = re.sub(r"\*(.*?)\*", r"<em>\1</em>", html_content)

        # Listas (manejo básico)
        lines = html_content.split("\n")
        in_ul = False
        processed_lines = []
        for line in lines:
            stripped_line = line.strip()
            # Detectar inicio/fin de lista
            is_li = stripped_line.startswith("* ") or stripped_line.startswith("- ")
            if is_li and not in_ul:
                processed_lines.append("<ul>")
                in_ul = True
            elif not is_li and in_ul:
                processed_lines.append("</ul>")
                in_ul = False

            # Procesar línea
            if is_li:
                # Quitar el '* ' o '- '
                item_content = re.sub(r"^[\*\-]\s+", "", stripped_line)
                processed_lines.append(f"<li>{item_content}</li>")
            else:
                # Añadir <p> si no es encabezado o lista y no está vacío
                if (
                    stripped_line
                    and not re.match(r"^<[hH][1-6]>.*", line)
                    and not re.match(r"^<[uU][lL]>.*", line)
                    and not re.match(r"^<[lL][iI]>.*", line)
                ):
                    processed_lines.append(
                        f"<p>{line}</p>"
                    )  # Usar line original para mantener indentación si hubiera
                elif stripped_line:  # Si es un encabezado ya procesado u otra etiqueta
                    processed_lines.append(line)

        # Cerrar lista si quedó abierta
        if in_ul:
            processed_lines.append("</ul>")

        html_content = "\n".join(processed_lines)
        # Reemplazar saltos de línea dobles con párrafos (más robusto que antes)
        # html_content = html_content.replace('\n\n', '</p><p>') # Esto puede ser problemático

        # --- Fin conversión manual ---

        # Envolver en plantilla Jinja
        try:
            template = self.jinja_env.get_template("proposal_base.html")
            # Usar el HTML generado como 'content'
            return template.render(content=html_content)
        except Exception as e:
            logger.error(f"Error al renderizar plantilla Jinja2: {e}", exc_info=True)
            # Fallback a HTML simple si falla la plantilla
            # Usar <pre> para mantener formato original si la conversión falló
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
