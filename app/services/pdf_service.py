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

        import re

        # Quitar marcador final
        html_content = proposal_text.replace(
            "[PROPOSAL_COMPLETE: Propuesta lista para PDF]", ""
        ).strip()

        # PASO 1: Procesar tablas antes que nada (muy importante)
        table_pattern = r"(\|\s*[\w\s\(\)/\-\[\]$%.,]+\s*\|\s*[\w\s\(\)/\-\[\]$%.,]+\s*\|[\s\|\w\(\)/\-\[\]$%.,]+\n)+"

        def convert_table(match):
            table_text = match.group(0)
            rows = table_text.strip().split("\n")
            html_table = '<table class="proposal-table" border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">\n'

            # Determinar si hay fila de encabezado (generalmente la primera)
            for i, row in enumerate(rows):
                cells = [
                    cell.strip() for cell in row.split("|")[1:-1]
                ]  # Quitar los | inicial y final
                if i == 0:  # Primera fila como encabezado
                    html_table += "  <thead>\n    <tr>\n"
                    for cell in cells:
                        html_table += f'      <th style="background-color: #f2f2f2; font-weight: bold;">{cell}</th>\n'
                    html_table += "    </tr>\n  </thead>\n  <tbody>\n"
                else:
                    html_table += "    <tr>\n"
                    for cell in cells:
                        html_table += f"      <td>{cell}</td>\n"
                    html_table += "    </tr>\n"

            if len(rows) > 1:  # Cerrar tbody si hay más de una fila
                html_table += "  </tbody>\n"
            html_table += "</table>"
            return html_table

        # Reemplazar tablas
        html_content = re.sub(table_pattern, convert_table, html_content)

        # PASO 2: Procesar encabezados
        html_content = re.sub(
            r"^# (.*?)$", r"<h1>\1</h1>", html_content, flags=re.MULTILINE
        )
        html_content = re.sub(
            r"^## (.*?)$", r"<h2>\1</h2>", html_content, flags=re.MULTILINE
        )
        html_content = re.sub(
            r"^### (.*?)$", r"<h3>\1</h3>", html_content, flags=re.MULTILINE
        )

        # PASO 3: Procesar formato básico
        html_content = re.sub(
            r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html_content
        )  # Negritas
        html_content = re.sub(r"\*(.*?)\*", r"<em>\1</em>", html_content)  # Itálicas
        html_content = re.sub(r"`(.*?)`", r"<code>\1</code>", html_content)  # Código

        # PASO 4: Procesar listas
        lines = html_content.split("\n")
        in_ul = False
        processed_lines = []

        for line in lines:
            stripped_line = line.strip()

            # Si ya procesamos como tabla o encabezado, añadir directamente
            if stripped_line.startswith("<table") or stripped_line.startswith("<h"):
                if in_ul:
                    processed_lines.append("</ul>")
                    in_ul = False
                processed_lines.append(line)
                continue

            # Detectar elementos de lista
            is_li = stripped_line.startswith("* ") or stripped_line.startswith("- ")

            if is_li and not in_ul:
                processed_lines.append("<ul>")
                in_ul = True
            elif not is_li and in_ul:
                processed_lines.append("</ul>")
                in_ul = False

            if is_li:
                item_content = re.sub(r"^[\*\-]\s+", "", stripped_line)
                processed_lines.append(f"<li>{item_content}</li>")
            elif stripped_line and not stripped_line.startswith("<"):
                processed_lines.append(f"<p>{line}</p>")
            elif stripped_line:
                processed_lines.append(line)

        if in_ul:
            processed_lines.append("</ul>")

        html_content = "\n".join(processed_lines)

        # PASO 5: Envolver en plantilla con estilos mejorados
        try:
            template = self.jinja_env.get_template("proposal_base.html")
            return template.render(content=html_content)
        except Exception as e:
            logger.error(f"Error renderizando plantilla HTML: {e}", exc_info=True)
            # Fallback a HTML básico si falla
            return f"""
            <html>
            <head>
                <title>Propuesta Hydrous</title>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                    table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
                    th, td {{ padding: 8px; border: 1px solid #ddd; }}
                    th {{ background-color: #f2f2f2; }}
                    h1, h2, h3 {{ color: #0056b3; }}
                    h1 {{ border-bottom: 2px solid #0056b3; padding-bottom: 5px; }}
                    .footer {{ text-align: center; font-size: 0.8em; color: #777; margin-top: 20px; }}
                </style>
            </head>
            <body>
                {html_content}
                <div class="footer">
                    Documento generado por Hydrous AI. Las estimaciones son preliminares.
                </div>
            </body>
            </html>
            """

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
