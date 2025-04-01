# app/services/ai_service.py

from openai import OpenAI
import os
import logging
from typing import Dict, Any, List, Optional

from app.config import settings
from app.models.conversation import Conversation

logger = logging.getLogger("hydrous")


class AIService:
    """Servicio que utiliza la API Responses para mantener el contexto de conversación"""

    def __init__(self):
        """Inicialización del servicio"""
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

        # Cargar instrucciones desde archivos
        self.instruction_content = self._load_instructions()

    def _load_instructions(self) -> str:
        """Carga las instrucciones desde los archivos de prompt"""
        instructions = ""

        # Cargar el prompt principal
        prompt_path = os.path.join(
            os.path.dirname(__file__), "../prompts/main_prompt.py"
        )
        if os.path.exists(prompt_path):
            # Extraer contenido del prompt desde el archivo Python
            with open(prompt_path, "r", encoding="utf-8") as f:
                content = f.read()
                # Extraer el texto entre comillas triples dentro de base_prompt
                import re

                base_prompt_match = re.search(
                    r'base_prompt\s*=\s*"""(.*?)"""', content, re.DOTALL
                )
                if base_prompt_match:
                    instructions += base_prompt_match.group(1).strip()

        # Cargar cuestionario
        questionnaire_path = os.path.join(
            os.path.dirname(__file__), "../prompts/cuestionario.txt"
        )
        if os.path.exists(questionnaire_path):
            with open(questionnaire_path, "r", encoding="utf-8") as f:
                questionnaire_content = f.read()
                instructions += f"\n\n# CUESTIONARIO:\n{questionnaire_content}"

        # Cargar formato de propuesta
        proposal_path = os.path.join(
            os.path.dirname(__file__), "../prompts/Format Proposal.txt"
        )
        if os.path.exists(proposal_path):
            with open(proposal_path, "r", encoding="utf-8") as f:
                proposal_content = f.read()
                instructions += f"\n\n# FORMATO DE PROPUESTA:\n{proposal_content}"

        return instructions

    async def initialize_conversation(self) -> Dict[str, Any]:
        """Inicializa una conversación con la API Responses"""
        try:
            # Crear una nueva conversación usando la API Responses
            response = self.client.responses.create(
                model=settings.MODEL,
                instructions=self.instruction_content,
                input="Inicializar asistente de agua Hydrous. Saluda al usuario y pregunta por su sector.",
            )

            # Devolver información de la conversación iniciada
            return {"response_id": response.id, "output_text": response.output_text}
        except Exception as e:
            logger.error(f"Error al inicializar conversación: {str(e)}")
            raise

    async def continue_conversation(
        self, previous_response_id: str, user_message: str
    ) -> Dict[str, Any]:
        """Continúa una conversación existente usando previous_response_id"""
        try:
            # Continuar conversación con la API Responses
            response = self.client.responses.create(
                model=settings.MODEL,
                previous_response_id=previous_response_id,
                input=user_message,
            )

            # Devolver información de la respuesta
            return {"response_id": response.id, "output_text": response.output_text}
        except Exception as e:
            logger.error(f"Error al continuar conversación: {str(e)}")
            raise

    async def handle_conversation(
        self, conversation: Conversation, user_message: str = None
    ) -> str:
        """Maneja una conversación usando la API Responses"""
        try:
            # Verificar si ya hay un ID de respuesta en los metadatos
            previous_response_id = conversation.metadata.get("openai_response_id")

            if not previous_response_id:
                # Primera interacción - inicializar conversación
                result = await self.initialize_conversation()

                # Guardar ID de respuesta en los metadatos
                conversation.metadata["openai_response_id"] = result["response_id"]

                return result["output_text"]
            else:
                # Continuación de conversación existente
                result = await self.continue_conversation(
                    previous_response_id, user_message
                )

                # Actualizar ID de respuesta en los metadatos
                conversation.metadata["openai_response_id"] = result["response_id"]

                # Detectar si la respuesta contiene una propuesta completa
                if self._contains_proposal_markers(result["output_text"]):
                    conversation.metadata["has_proposal"] = True

                return result["output_text"]
        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, inténtalo de nuevo."

    def _contains_proposal_markers(self, text: str) -> bool:
        """Detecta si el texto contiene marcadores de una propuesta completa"""
        key_terms = [
            "CAPEX",
            "OPEX",
            "Return on Investment",
            "ROI",
            "Estimated Cost",
            "Process Design",
            "Treatment Alternatives",
            "Equipment & Sizing",
            "PROPUESTA COMPLETA",
            "HYDROUS MANAGEMENT GROUP",
        ]

        # Contar cuántos términos clave están presentes
        term_count = sum(1 for term in key_terms if term in text)

        # Si hay varios términos clave, considerar que es una propuesta
        return term_count >= 3 or "PROPUESTA" in text.upper()


# Instancia global
ai_service = AIService()
