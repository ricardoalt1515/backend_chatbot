# app/services/proposal_service.py
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import re

from app.models.conversation import Conversation
from app.config import settings

logger = logging.getLogger("hydrous")


class ProposalService:
    """Servicio para generar propuestas estructuradas basadas en la plantilla Hydrous"""

    def __init__(self):
        """Inicialización del servicio"""
        # Crear directorio para propuestas
        self.proposals_dir = os.path.join(settings.UPLOAD_DIR, "proposals")
        os.makedirs(self.proposals_dir, exist_ok=True)

    def generate_proposal(self, conversation: Conversation) -> Dict[str, Any]:
        """
        Genera una propuesta estructurada basada en la información recopilada

        Args:
            conversation: Conversación con la información recopilada

        Returns:
            Dict: Estructura de la propuesta
        """
        # Extraer información clave de la conversación
        client_info = self._extract_client_info(conversation)
        water_info = self._extract_water_info(conversation)
        treatment_info = self._extract_treatment_info(conversation)

        # Crear estructura de propuesta basada en la plantilla
        proposal = {
            "client_info": client_info,
            "water_info": water_info,
            "treatment_info": treatment_info,
            "timestamp": datetime.now().isoformat(),
            "proposal_id": f"HYD-{datetime.now().strftime('%Y%m%d')}-{conversation.id[:8]}",
        }

        return proposal

    def generate_proposal_html(self, proposal: Dict[str, Any]) -> str:
        """
        Genera HTML formateado para la propuesta

        Args:
            proposal: Estructura de la propuesta

        Returns:
            str: HTML formateado
        """
        # Obtener información de la propuesta
        client_info = proposal.get("client_info", {})
        water_info = proposal.get("water_info", {})
        treatment_info = proposal.get("treatment_info", {})

        # Crear HTML con la estructura exacta de la plantilla
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
                }}
                .container {{
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{ 
                    background-color: #1a5276; 
                    color: white; 
                    padding: 20px; 
                    text-align: center; 
                    margin-bottom: 20px;
                }}
                h1, h2, h3 {{ color: #1a5276; }}
                table {{ 
                    width: 100%;
                    border-collapse: collapse; 
                    margin: 15px 0; 
                }}
                th, td {{ 
                    border: 1px solid #ddd; 
                    padding: 8px; 
                    text-align: left; 
                }}
                th {{ background-color: #f2f2f2; }}
                .disclaimer {{
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-left: 4px solid #1a5276;
                    margin-bottom: 20px;
                }}
                .footer {{ 
                    text-align: center; 
                    margin-top: 30px; 
                    font-size: 0.9em; 
                    color: #777;
                }}
                .check-item {{
                    background-color: #f1f8ff;
                    padding: 10px;
                    margin: 5px 0;
                    border-left: 3px solid #4CAF50;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>HYDROUS MANAGEMENT GROUP</h1>
                    <p>Soluciones de Tratamiento de Agua</p>
                </div>
                
                <div class="disclaimer">
                    <p><strong>📌 Aviso Importante</strong></p>
                    <p>Esta propuesta fue <strong>generada usando IA</strong> basada en la información proporcionada por el usuario final y <strong>estándares de la industria</strong>. Se recomienda que todos los detalles sean <strong>validados por Hydrous Management Group</strong> antes de la implementación.</p>
                </div>
                
                <h2>1. Introducción a Hydrous Management Group</h2>
                <p>Hydrous Management Group se especializa en <strong>soluciones personalizadas de tratamiento de aguas residuales</strong> adaptadas para clientes industriales y comerciales. Nuestra <strong>experiencia en gestión del agua</strong> ayuda a las empresas a lograr <strong>cumplimiento normativo, reducción de costos y reutilización sostenible del agua</strong>.</p>
                
                <h2>2. Antecedentes del Proyecto</h2>
                <table>
                    <tr>
                        <th>Información del Cliente</th>
                        <th>Detalles</th>
                    </tr>
                    <tr>
                        <td><strong>Nombre del Cliente</strong></td>
                        <td>{client_info.get('name', 'No especificado')}</td>
                    </tr>
                    <tr>
                        <td><strong>Ubicación</strong></td>
                        <td>{client_info.get('location', 'No especificada')}</td>
                    </tr>
                    <tr>
                        <td><strong>Industria</strong></td>
                        <td>{client_info.get('sector', 'No especificada')}</td>
                    </tr>
                    <tr>
                        <td><strong>Fuente de Agua</strong></td>
                        <td>{water_info.get('source', 'No especificada')}</td>
                    </tr>
                    <tr>
                        <td><strong>Consumo Actual de Agua</strong></td>
                        <td>{water_info.get('consumption', 'No especificado')}</td>
                    </tr>
                    <tr>
                        <td><strong>Generación Actual de Aguas Residuales</strong></td>
                        <td>{water_info.get('wastewater', 'No especificado')}</td>
                    </tr>
                    <tr>
                        <td><strong>Sistema de Tratamiento Existente</strong></td>
                        <td>{water_info.get('existing_system', 'No existe tratamiento')}</td>
                    </tr>
                </table>
                
                <h2>3. Objetivo del Proyecto</h2>
                <div class="check-item">✅ <strong>Cumplimiento Normativo</strong> — Asegurar que las aguas residuales tratadas cumplan con las regulaciones de descarga.</div>
                <div class="check-item">✅ <strong>Optimización de Costos</strong> — Reducir los costos de compra y descarga de agua.</div>
                <div class="check-item">✅ <strong>Reutilización de Agua</strong> — Tratar las aguas residuales para su uso en procesos industriales.</div>
                <div class="check-item">✅ <strong>Sostenibilidad</strong> — Mejorar la huella ambiental mediante una gestión eficiente de los recursos.</div>
                
                <!-- El resto de secciones seguiría la misma estructura -->
                
                <h2>4. Supuestos Clave de Diseño y Comparación con Estándares de la Industria</h2>
                <!-- Tabla de parámetros -->
                
                <h2>5. Diseño del Proceso y Alternativas de Tratamiento</h2>
                <!-- Tabla de etapas de tratamiento -->
                
                <h2>6. Equipamiento Sugerido y Dimensionamiento</h2>
                <!-- Tabla de equipos -->
                
                <h2>7. CAPEX y OPEX Estimados</h2>
                <!-- Tablas de costos -->
                
                <h2>8. Análisis de Retorno de Inversión (ROI)</h2>
                <!-- Tabla de ROI -->
                
                <h2>9. Anexo de Preguntas y Respuestas</h2>
                <p>Se incluyen todas las <strong>preguntas y respuestas clave</strong> recopiladas durante la consulta como referencia.</p>
                
                <div class="footer">
                    <p>📩 <strong>Para consultas o validación de esta propuesta, contacte a Hydrous Management Group en:</strong> info@hydrous.com</p>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def _extract_client_info(self, conversation: Conversation) -> Dict[str, Any]:
        """Extrae información del cliente de la conversación"""
        info = {
            "name": "Cliente",
            "location": "No especificada",
            "sector": "No especificado",
        }

        # Intentar extraer desde el estado del cuestionario
        if hasattr(conversation, "questionnaire_state"):
            key_entities = getattr(conversation.questionnaire_state, "key_entities", {})
            answers = getattr(conversation.questionnaire_state, "answers", {})

            if key_entities.get("company_name"):
                info["name"] = key_entities["company_name"]
            if key_entities.get("location"):
                info["location"] = key_entities["location"]
            if getattr(conversation.questionnaire_state, "sector", None):
                info["sector"] = conversation.questionnaire_state.sector

        # Buscar en los mensajes si aún no tenemos información
        if info["name"] == "Cliente" or info["location"] == "No especificada":
            for msg in conversation.messages:
                if msg.role == "user":
                    # Buscar nombre de empresa
                    if info["name"] == "Cliente":
                        company_match = re.search(
                            r"(?:empresa|compañía|proyecto)[\s:]+([a-zA-Z0-9\s]+)",
                            msg.content,
                            re.IGNORECASE,
                        )
                        if company_match:
                            info["name"] = company_match.group(1).strip()

                    # Buscar ubicación
                    if info["location"] == "No especificada":
                        location_match = re.search(
                            r"(?:ubicación|ubicacion|localización|ciudad)[\s:]+([a-zA-Z0-9\s,]+)",
                            msg.content,
                            re.IGNORECASE,
                        )
                        if location_match:
                            info["location"] = location_match.group(1).strip()

        return info

    def _extract_water_info(self, conversation: Conversation) -> Dict[str, Any]:
        """Extrae información sobre agua de la conversación"""
        info = {
            "source": "No especificada",
            "consumption": "No especificado",
            "wastewater": "No especificado",
            "existing_system": "Ninguno",
        }

        # Extraer desde el estado del cuestionario
        if hasattr(conversation, "questionnaire_state"):
            answers = getattr(conversation.questionnaire_state, "answers", {})
            key_entities = getattr(conversation.questionnaire_state, "key_entities", {})

            if key_entities.get("water_volume"):
                info["consumption"] = key_entities["water_volume"]
            if answers.get("cantidad_agua_residual"):
                info["wastewater"] = answers["cantidad_agua_residual"]
            if answers.get("fuente_agua"):
                info["source"] = answers["fuente_agua"]
            if answers.get("sistema_existente"):
                info["existing_system"] = answers["sistema_existente"]

        return info

    def _extract_treatment_info(self, conversation: Conversation) -> Dict[str, Any]:
        """Extrae información sobre tratamiento propuesto de la conversación"""
        # Buscar la propuesta de tratamiento en los mensajes del asistente
        info = {}
        treatment_text = ""

        for msg in reversed(conversation.messages):
            if msg.role == "assistant" and (
                "Propuesta" in msg.content or "Tratamiento" in msg.content
            ):
                treatment_text = msg.content
                break

        # Extraer información de tecnologías recomendadas
        if "MBBR" in treatment_text:
            info["technology"] = "MBBR (Reactor de Lecho Móvil)"
        elif "MBR" in treatment_text:
            info["technology"] = "MBR (Biorreactor de Membrana)"
        elif "DAF" in treatment_text:
            info["technology"] = "DAF (Flotación por Aire Disuelto)"
        else:
            info["technology"] = "Sistema de tratamiento personalizado"

        return info


# Instancia global
proposal_service = ProposalService()
