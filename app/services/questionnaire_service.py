import os
import logging
import json
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

# Verificar dependencias disponibles para generación de PDF
PDF_GENERATORS = []
try:
    import markdown2
except ImportError:
    markdown2 = None
    logging.warning("markdown2 no está instalado. Necesario para formatear propuestas.")

try:
    import pdfkit

    PDF_GENERATORS.append("pdfkit")
except ImportError:
    logging.warning("pdfkit no está instalado. No se podrá usar para generar PDFs.")

try:
    from weasyprint import HTML

    PDF_GENERATORS.append("weasyprint")
except ImportError:
    logging.warning("weasyprint no está instalado. No se podrá usar para generar PDFs.")

if not PDF_GENERATORS:
    logging.warning(
        "¡ADVERTENCIA! No hay generadores de PDF disponibles. Las propuestas solo se generarán en HTML."
    )
else:
    logging.info(f"Generadores de PDF disponibles: {', '.join(PDF_GENERATORS)}")

from app.models.conversation import Conversation
from app.config import settings

logger = logging.getLogger("hydrous-backend")


class QuestionnaireService:
    """Servicio simplificado para manejar el cuestionario y generar propuestas"""

    def __init__(self):
        self.questionnaire_data = self._load_questionnaire_data()

    def _load_questionnaire_data(self) -> Dict[str, Any]:
        """Carga los datos del cuestionario desde un archivo JSON"""
        try:
            # Intentar cargar desde archivo
            questionnaire_path = os.path.join(
                os.path.dirname(__file__), "../data/questionnaire.json"
            )
            if os.path.exists(questionnaire_path):
                with open(questionnaire_path, "r", encoding="utf-8") as f:
                    return json.load(f)

            # Intentar con questionnaire_complete.json como alternativa
            questionnaire_complete_path = os.path.join(
                os.path.dirname(__file__), "../data/questionnaire_complete.json"
            )
            if os.path.exists(questionnaire_complete_path):
                with open(questionnaire_complete_path, "r", encoding="utf-8") as f:
                    return json.load(f)

            logger.warning(
                "Archivo de cuestionario no encontrado. Usando estructura predeterminada."
            )
            return self._build_default_questionnaire()
        except Exception as e:
            logger.error(f"Error al cargar datos del cuestionario: {str(e)}")
            return self._build_default_questionnaire()

    def _build_default_questionnaire(self) -> Dict[str, Any]:
        """Construye una versión predeterminada del cuestionario para emergencias"""
        # Estructura mínima para que el sistema funcione en caso de error
        return {
            "sectors": ["Industrial", "Comercial", "Municipal", "Residencial"],
            "subsectors": {
                "Industrial": ["Textil", "Alimentos y Bebidas", "Petroquímica"],
                "Comercial": ["Hotel", "Edificio de oficinas"],
                "Municipal": ["Gobierno de la ciudad"],
                "Residencial": ["Vivienda unifamiliar", "Edificio multifamiliar"],
            },
            "facts": {
                "Industrial_Textil": [
                    "Las industrias textiles que implementan sistemas de reciclaje eficientes logran reducir su consumo de agua hasta en un 40%.",
                    "El sector textil es uno de los mayores consumidores de agua dulce a nivel mundial.",
                    "Las plantas textiles modernas pueden reciclar hasta el 70% del agua utilizada.",
                ],
                "Industrial_Alimentos y Bebidas": [
                    "Las empresas de alimentos pueden reducir su consumo hasta en un 50%.",
                    "El tratamiento adecuado puede generar biogás como fuente de energía.",
                    "Los sistemas de tratamiento anaerobios pueden reducir hasta un 90% la carga orgánica.",
                ],
            },
        }

    def generate_proposal(self, conversation: Conversation) -> Dict[str, Any]:
        """
        Genera una propuesta basada en las respuestas recopiladas

        Args:
            conversation: Conversación con la información recopilada

        Returns:
            Dict: Propuesta generada
        """
        # Extraer información de la conversación
        info = self._extract_conversation_info(conversation)

        # Datos del cliente
        client_info = {
            "name": info.get("nombre_empresa", "Cliente"),
            "location": info.get("ubicacion", "No especificada"),
            "sector": info.get("sector", "Industrial"),
            "subsector": info.get("subsector", ""),
        }

        # Datos técnicos
        technical_info = {
            "water_consumption": info.get("cantidad_agua_consumida", "No especificado"),
            "wastewater_generation": info.get(
                "cantidad_agua_residual", "No especificado"
            ),
            "water_cost": info.get("costo_agua", "No especificado"),
            "objectives": info.get(
                "objetivo_principal", "Optimización de recursos hídricos"
            ),
            "reuse_objectives": info.get("objetivo_reuso", ["Reutilización de agua"]),
        }

        # Obtener propuesta del último mensaje del asistente
        proposal_text = ""
        for msg in reversed(conversation.messages):
            if msg.role == "assistant" and "Propuesta" in msg.content:
                proposal_text = msg.content
                break

        # Si no se encontró propuesta, usar uno genérico
        if not proposal_text:
            proposal_text = f"""
# 🧾 Propuesta Preliminar de Tratamiento y Reúso de Agua

**Cliente:** {client_info.get('name', 'Cliente')}
**Ubicación:** {client_info.get('location', 'No especificada')}
**Sector:** {client_info.get('sector', 'Industrial')} - {client_info.get('subsector', '')}

## 1. Antecedentes del Proyecto
{client_info.get('name', 'Cliente')} requiere una solución para tratamiento y reciclaje de aguas residuales.

## 2. Objetivo del Proyecto
- Optimización del uso de recursos hídricos
- Reducción de costos operativos
- Cumplimiento normativo

## 3. Solución propuesta
Se recomienda un sistema de tratamiento que incluye:
- Pretratamiento
- Tratamiento primario
- Tratamiento secundario
- Tratamiento terciario si es necesario

## 4. Costos estimados
- CAPEX: Por determinar según requisitos específicos
- OPEX: Por determinar según requisitos específicos

## 5. Siguientes pasos
- Validación de parámetros técnicos
- Visita técnica al sitio
- Desarrollo de propuesta detallada
"""

        # Construir propuesta final
        proposal = {
            "client_info": client_info,
            "technical_info": technical_info,
            "proposal_text": proposal_text,
            "timestamp": datetime.now().isoformat(),
            "proposal_id": f"HYD-{datetime.now().strftime('%Y%m%d')}-{conversation.id[:8]}",
        }

        return proposal

    def _extract_conversation_info(self, conversation: Conversation) -> Dict[str, Any]:
        """
        Extrae información de la conversación para la propuesta

        Args:
            conversation: Conversación actual

        Returns:
            Dict: Información extraída
        """
        info = {}

        # Extraer sector/subsector
        info["sector"] = conversation.questionnaire_state.sector
        info["subsector"] = conversation.questionnaire_state.subsector

        # Extraer respuestas del cuestionario
        answers = conversation.questionnaire_state.answers
        for key, value in answers.items():
            info[key] = value

        # Extraer información de los mensajes
        all_text = ""
        for msg in conversation.messages:
            if msg.role == "user":
                all_text += msg.content + " "

        # Buscar patrones relevantes si faltan datos clave
        if "nombre_empresa" not in info:
            name_match = re.search(
                r"(?:empresa|compañía|proyecto)[\s:]+([a-zA-Z0-9\s]+)",
                all_text,
                re.IGNORECASE,
            )
            if name_match:
                info["nombre_empresa"] = name_match.group(1).strip()

        if "ubicacion" not in info:
            location_match = re.search(
                r"(?:ubicación|ubicacion|localización|ciudad)[\s:]+([a-zA-Z0-9\s,]+)",
                all_text,
                re.IGNORECASE,
            )
            if location_match:
                info["ubicacion"] = location_match.group(1).strip()

        if "costo_agua" not in info:
            cost_match = re.search(
                r"(?:costo|precio)[\s:]+(\$?\d+(?:\.\d+)?(?:\s*[\$/]m3)?)",
                all_text,
                re.IGNORECASE,
            )
            if cost_match:
                info["costo_agua"] = cost_match.group(1).strip()

        return info

    def generate_proposal_pdf(self, proposal: Dict[str, Any]) -> str:
        """
        Genera un PDF basado en la propuesta

        Args:
            proposal: Propuesta generada

        Returns:
            str: Ruta al archivo PDF generado
        """
        try:
            # Extraer información básica
            client_info = proposal.get("client_info", {})
            client_name = client_info.get("name", "Cliente").replace(" ", "_")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Obtener el contenido de la propuesta
            proposal_text = proposal.get("proposal_text", "")

            # Convertir Markdown a HTML
            html_content = self._markdown_to_html(proposal_text)

            # Añadir encabezado y pie de página HTML
            html_content = f"""
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
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <div class="logo-text">HYDROUS</div>
                        <div>Soluciones de Tratamiento de Agua</div>
                    </div>
                    
                    {html_content}
                    
                    <div class="footer">
                        <p>Hydrous Management Group © {datetime.now().year}</p>
                        <p>Propuesta generada el {datetime.now().strftime('%d/%m/%Y')}</p>
                        <p>Documento confidencial para uso exclusivo del cliente</p>
                    </div>
                </div>
            </body>
            </html>
            """

            # Guardar como HTML
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
            html_path = os.path.join(
                settings.UPLOAD_DIR, f"{client_name}_propuesta_{timestamp}.html"
            )
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            # Intentar generar PDF si hay bibliotecas disponibles
            if PDF_GENERATORS:
                pdf_path = os.path.join(
                    settings.UPLOAD_DIR, f"{client_name}_propuesta_{timestamp}.pdf"
                )

                # Intentar con WeasyPrint primero
                if "weasyprint" in PDF_GENERATORS:
                    try:
                        from weasyprint import HTML

                        HTML(string=html_content).write_pdf(pdf_path)
                        return pdf_path
                    except Exception as e:
                        logger.warning(f"Error al generar PDF con WeasyPrint: {e}")

                # Si falla, intentar con pdfkit
                if "pdfkit" in PDF_GENERATORS:
                    try:
                        import pdfkit

                        pdfkit.from_string(html_content, pdf_path)
                        return pdf_path
                    except Exception as e:
                        logger.warning(f"Error al generar PDF con pdfkit: {e}")

            # Si no se pudo generar PDF, devolver HTML
            return html_path

        except Exception as e:
            logger.error(f"Error al generar propuesta: {str(e)}")
            return ""

    def _markdown_to_html(self, markdown_text: str) -> str:
        """
        Convierte Markdown a HTML

        Args:
            markdown_text: Texto en formato Markdown

        Returns:
            str: HTML resultante
        """
        try:
            if markdown2:
                return markdown2.markdown(
                    markdown_text, extras=["tables", "fenced-code-blocks"]
                )
            else:
                # Conversión básica si no está disponible markdown2
                html = markdown_text
                # Encabezados
                html = re.sub(r"^# (.*?)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
                html = re.sub(r"^## (.*?)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
                html = re.sub(r"^### (.*?)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
                # Negrita
                html = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html)
                # Cursiva
                html = re.sub(r"\*(.*?)\*", r"<em>\1</em>", html)
                # Listas
                html = re.sub(r"^- (.*?)$", r"<li>\1</li>", html, flags=re.MULTILINE)
                html = re.sub(r"(<li>.*?</li>)", r"<ul>\1</ul>", html, flags=re.DOTALL)
                # Párrafos
                html = re.sub(r"([^\n])\n([^\n])", r"\1<br>\2", html)
                html = re.sub(r"\n\n", r"</p><p>", html)
                html = "<p>" + html + "</p>"
                return html
        except Exception as e:
            logger.warning(f"Error al convertir Markdown a HTML: {e}")
            return f"<pre>{markdown_text}</pre>"


# Instancia global del servicio
questionnaire_service = QuestionnaireService()
