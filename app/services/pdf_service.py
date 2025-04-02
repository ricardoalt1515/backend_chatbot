# app/services/pdf_service.py
import os
import logging
from typing import Dict, Any, Optional
import json
from datetime import datetime

from app.config import settings

logger = logging.getLogger("hydrous")


class PDFService:
    """Servicio para generar PDFs a partir de propuestas"""

    async def generate_proposal_pdf(
        self, proposal_data: Dict[str, Any], response_id: str
    ) -> Optional[str]:
        """
        Genera un PDF a partir de datos de propuesta estructurada

        Args:
            proposal_data: Datos estructurados de la propuesta
            response_id: ID de la respuesta asociada

        Returns:
            str: Ruta al archivo PDF generado o None si falla
        """
        try:
            # Extraer información básica para el nombre del archivo
            client_info = proposal_data.get("client_info", {})
            client_name = client_info.get("name", "Cliente").replace(" ", "_")

            # Generar HTML primero
            html_content = self._generate_proposal_html(proposal_data)

            # Guardar HTML
            html_path = os.path.join(
                settings.UPLOAD_DIR, f"proposal_{response_id}.html"
            )
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            # Intentar generar PDF - Aquí necesitamos una implementación específica
            # Podrías usar weasyprint, pdfkit, reportlab, etc.
            # Por ahora, vamos a hacer un stub simple

            # NOTA: Esta parte depende de la biblioteca específica que quieras usar
            pdf_path = os.path.join(settings.UPLOAD_DIR, f"proposal_{response_id}.pdf")

            try:
                # Intentar con WeasyPrint si está disponible
                from weasyprint import HTML

                HTML(string=html_content).write_pdf(pdf_path)
                logger.info(f"PDF generado con WeasyPrint: {pdf_path}")
                return pdf_path
            except ImportError:
                try:
                    # Intentar con pdfkit si está disponible
                    import pdfkit

                    pdfkit.from_string(html_content, pdf_path)
                    logger.info(f"PDF generado con pdfkit: {pdf_path}")
                    return pdf_path
                except ImportError:
                    # Si no hay generadores de PDF disponibles, devolver la ruta del HTML
                    logger.warning(
                        "No hay generadores de PDF disponibles, devolviendo HTML"
                    )
                    return html_path

        except Exception as e:
            logger.error(f"Error al generar PDF: {e}")
            return None

    def _generate_proposal_html(self, proposal_data: Dict[str, Any]) -> str:
        """
        Genera HTML formateado a partir de datos de propuesta

        Args:
            proposal_data: Datos estructurados de la propuesta

        Returns:
            str: Contenido HTML
        """
        # Extraer datos de la propuesta
        client_info = proposal_data.get("client_info", {})
        project_background = proposal_data.get("project_background", "")
        project_objective = proposal_data.get("project_objective", "")
        key_parameters = proposal_data.get("key_parameters", {})
        treatment_process = proposal_data.get("treatment_process", [])
        financial_analysis = proposal_data.get("financial_analysis", {})
        next_steps = proposal_data.get("next_steps", [])

        # Construir el HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Propuesta Hydrous - {client_info.get('name', 'Cliente')}</title>
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
                    margin: 20px auto;
                    padding: 20px;
                    background-color: white;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    border-radius: 8px;
                }}
                
                h1 {{ color: #1a5276; font-size: 24px; margin-top: 20px; }}
                h2 {{ color: #2874a6; font-size: 20px; margin-top: 15px; }}
                
                .header {{ 
                    background-color: #2c3e50; 
                    color: white; 
                    padding: 20px; 
                    text-align: center; 
                    margin-bottom: 20px;
                    border-radius: 8px 8px 0 0;
                }}
                
                .logo-text {{
                    font-size: 28px;
                    font-weight: bold;
                    color: white;
                    margin-bottom: 5px;
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
                    font-size: 0.9em; 
                    color: #777;
                }}
                
                .disclaimer {{
                    background-color: #f8f9fa;
                    border-left: 4px solid #4682B4;
                    padding: 15px;
                    margin: 20px 0;
                    font-size: 0.9em;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo-text">HYDROUS</div>
                    <div>Soluciones de Tratamiento de Agua</div>
                </div>
                
                <div class="disclaimer">
                    <strong>Aviso importante:</strong> Esta propuesta fue generada usando IA basada en la información 
                    proporcionada y estándares de la industria. Todas las estimaciones y recomendaciones deben ser 
                    validadas por Hydrous Management Group antes de su implementación.
                </div>
                
                <h1>Propuesta de Tratamiento de Agua para {client_info.get('name', 'Cliente')}</h1>
                
                <h2>1. Información del Cliente</h2>
                <table>
                    <tr>
                        <th>Cliente</th>
                        <td>{client_info.get('name', 'N/A')}</td>
                    </tr>
                    <tr>
                        <th>Ubicación</th>
                        <td>{client_info.get('location', 'N/A')}</td>
                    </tr>
                    <tr>
                        <th>Sector</th>
                        <td>{client_info.get('sector', 'N/A')}</td>
                    </tr>
                    <tr>
                        <th>Subsector</th>
                        <td>{client_info.get('subsector', 'N/A')}</td>
                    </tr>
                </table>
                
                <h2>2. Antecedentes del Proyecto</h2>
                <p>{project_background}</p>
                
                <h2>3. Objetivo del Proyecto</h2>
                <p>{project_objective}</p>
                
                <h2>4. Parámetros Clave</h2>
                <table>
                    <tr>
                        <th>Consumo de Agua</th>
                        <td>{key_parameters.get('water_consumption', 'N/A')}</td>
                    </tr>
                    <tr>
                        <th>Generación de Aguas Residuales</th>
                        <td>{key_parameters.get('wastewater_generation', 'N/A')}</td>
                    </tr>
                </table>
                
                <h3>Contaminantes Clave</h3>
                <ul>
        """

        # Añadir contaminantes
        for contaminant in key_parameters.get("key_contaminants", []):
            html += f"<li>{contaminant}</li>"

        html += """
                </ul>
                
                <h2>5. Proceso de Tratamiento Recomendado</h2>
                <table>
                    <tr>
                        <th>Etapa</th>
                        <th>Tecnología</th>
                        <th>Propósito</th>
                    </tr>
        """

        # Añadir etapas de tratamiento
        for stage in treatment_process:
            html += f"""
                    <tr>
                        <td>{stage.get('stage', 'N/A')}</td>
                        <td>{stage.get('technology', 'N/A')}</td>
                        <td>{stage.get('purpose', 'N/A')}</td>
                    </tr>
            """

        html += """
                </table>
                
                <h2>6. Análisis Financiero</h2>
                <table>
                    <tr>
                        <th>CAPEX Estimado</th>
                        <td>{}</td>
                    </tr>
                    <tr>
                        <th>OPEX Estimado</th>
                        <td>{}</td>
                    </tr>
                    <tr>
                        <th>ROI Estimado</th>
                        <td>{}</td>
                    </tr>
                </table>
        """.format(
            financial_analysis.get("estimated_capex", "N/A"),
            financial_analysis.get("estimated_opex", "N/A"),
            financial_analysis.get("roi_estimate", "N/A"),
        )

        html += """
                <h2>7. Próximos Pasos</h2>
                <ol>
        """

        # Añadir próximos pasos
        for step in next_steps:
            html += f"<li>{step}</li>"

        html += """
                </ol>
                
                <div class="footer">
                    <p>Hydrous Management Group © {}</p>
                    <p>Propuesta generada el {}</p>
                    <p>Documento confidencial para uso exclusivo del cliente</p>
                </div>
            </div>
        </body>
        </html>
        """.format(
            datetime.now().year, datetime.now().strftime("%d/%m/%Y")
        )

        return html


# Instancia global
pdf_service = PDFService()
