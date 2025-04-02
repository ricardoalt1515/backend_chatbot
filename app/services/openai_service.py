# app/services/openai_service.py
from openai import OpenAI
from app.config import settings
import logging
from datetime import datetime

logger = logging.getLogger("hydrous")


class OpenAIService:
    def __init__(self):
        """Inicializa el servicio de OpenAI usando la API Responses"""
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    async def start_conversation(self) -> dict:
        """Inicia una nueva conversación con mensaje de bienvenida"""
        try:
            # Mensaje de bienvenida
            welcome_message = """
# 👋 ¡Bienvenido a Hydrous AI!

Soy el diseñador de soluciones de agua de Hydrous AI, tu asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales.

**PREGUNTA: ¿Cuál es el nombre de tu empresa o proyecto y dónde se ubica?**
"""
            # Crear respuesta
            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                instructions=self._get_instructions(),
                input=welcome_message,
            )

            return {
                "id": response.id,
                "content": response.output_text,
                "created_at": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Error al iniciar conversación: {e}")
            raise

    async def send_message(self, response_id: str, message: str) -> dict:
        """Envía un mensaje y obtiene respuesta"""
        try:
            # Crear respuesta
            response = self.client.responses.create(
                model=settings.OPENAI_MODEL,
                previous_response_id=response_id,
                input=message,
            )

            # Verificar si contiene indicador de propuesta completa
            content = response.output_text
            has_proposal = "[PROPOSAL_COMPLETE:" in content

            return {
                "id": response.id,
                "content": content,
                "has_proposal": has_proposal,
                "created_at": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Error al procesar mensaje: {e}")
            raise

    def _get_instructions(self) -> str:
        """Instrucciones base para el asistente con cuestionario y formato de propuesta"""
        return """
Eres el diseñador de soluciones de agua de Hydrous AI, un asistente experto diseñado para ayudar a los usuarios a desarrollar soluciones personalizadas de tratamiento de agua y aguas residuales.

PROCESO DE RECOPILACIÓN DE INFORMACIÓN:
- El proceso debe dividirse en pasos pequeños y sencillos.
- SOLO DEBES REALIZAR UNA PREGUNTA A LA VEZ.
- Primero, identificar el sector: Industrial, Comercial, Municipal o Residencial.
- Luego, identificar el subsector específico dentro del sector seleccionado.
- Seguir el cuestionario específico para ese sector/subsector.
- Cada pregunta debe ir acompañada de una breve explicación de por qué es importante.
- Para preguntas de opción múltiple, numerar las opciones para que el usuario responda con un número.

COMUNICACIÓN:
- Usa emojis estratégicos (💧, 📊, 🌊, ♻️, 💰)
- Después de cada respuesta del usuario, proporciona un dato educativo relevante.
- Realiza resúmenes periódicos (cada 3-4 preguntas) de la información recopilada.

PROPUESTA FINAL:
Al finalizar el cuestionario, presenta una propuesta siguiendo este formato:
1. Introducción a Hydrous Management Group
2. Antecedentes del proyecto
3. Objetivo del Proyecto
4. Supuestos clave de diseño y comparación con los estándares de la industria
5. Diseño de Procesos y Alternativas de Tratamiento
6. Equipo y tamaño sugeridos
7. Estimación de CAPEX y OPEX
8. Análisis del retorno de la inversión (ROI)

Finaliza la propuesta con: "[PROPOSAL_COMPLETE: Esta propuesta está lista para descargarse como PDF]"
"""


# Instancia global
openai_service = OpenAIService()
