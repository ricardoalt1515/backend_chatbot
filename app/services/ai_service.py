# app/services/ai_service.py
import logging
import httpx
import os
from typing import List, Dict, Any

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.main_prompt import get_master_prompt
from app.services import questionnaire_service

logger = logging.getLogger("hydrous")


class AIService:
    """Servicio simplificado para interactuar con LLMs"""

    def __init__(self):
        """Inicialización del servicio AI"""
        # Cargar el prompt maestro
        self.master_prompt = get_master_prompt()

        # Cargar archivos de cuestionario y formato de propuesta
        proposal_format_path = os.path.join(
            os.path.dirname(__file__), "../prompts/Format Proposal.txt"
        )

        # Leer estos archivos si existen (asegúrate de tener versiones .txt de ellos)
        self.questionnaire_content = ""
        self.proposal_format_content = ""

        if os.path.exists(questionnaire_path):
            with open(questionnaire_path, "r", encoding="utf-8") as f:
                self.questionnaire_content = f.read()

        if os.path.exists(proposal_format_path):
            with open(proposal_format_path, "r", encoding="utf-8") as f:
                self.proposal_format_content = f.read()

        # Configuración de API
        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_URL

    async def handle_conversation(
        self, conversation: Conversation, user_message: str = None
    ) -> str:
        """Maneja una conversación y genera una respuesta simplificada"""
        try:
            # Preparar los mensajes para la API de forma mucho más simple
            messages = self._prepare_messages(conversation, user_message)

            # Llamar a la API del LLM
            response = await self._call_llm_api(messages)

            # Detectar si contiene una propuesta completa para PDF
            if "[PROPOSAL_COMPLETE:" in response:
                conversation.metadata["has_proposal"] = True
                # Añadir instrucciones para descargar PDF si es necesario
                # ...

            return response
        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, inténtalo de nuevo."

    def _prepare_messages(
        self, conversation: Conversation, user_message: str = None
    ) -> List[Dict[str, str]]:
        """Prepara los mensajes para la API del LLM de forma simplificada"""
        # Mensaje inicial del sistema con el prompt maestro
        system_prompt = self.master_prompt

        # Añadir contenido del cuestionario como un bloque específico con formato preservado

        if self.questionnaire_content:
            system_prompt += (
                "\n\n<cuestionario>\n"
                + self.questionnaire_content
                + "\n</cuestionario>"
            )

        if self.proposal_format_content:
            system_prompt += (
                "\n\n<formato_propuesta>\n"
                + self.proposal_format_content
                + "\n</formato_propuesta>"
            )

        # Añadir instrucciones específicas para el manejo de opciones múltiples
        system_prompt += """
        \n\nIMPORTANTE: Cuando encuentres una lista de opciones marcada con asteriscos (*) o números, DEBES presentarla como opciones numeradas para que el usuario pueda elegir por número. Ejemplo:
        1. Opción A
        2. Opción B
        3. Opción C

        Al procesar la respuesta del usuario, acepta tanto el número como el texto de la opción.
        """

        messages = [{"role": "system", "content": system_prompt}]

        # Añadir mensajes anteriores de la conversación
        for msg in conversation.messages:
            if msg.role != "system":  # No duplicar mensajes del sistema
                messages.append({"role": msg.role, "content": msg.content})

        # Si hay un nuevo mensaje del usuario, añadirlo
        if user_message:
            messages.append({"role": "user", "content": user_message})

        return messages

    async def _call_llm_api(self, messages: List[Dict[str, str]]) -> str:
        """Llama a la API del LLM"""
        try:

            # Llamar a la API usando httpx
            async with httpx.AsyncClient() as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }

                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 3000,
                }

                response = await client.post(
                    self.api_url, json=payload, headers=headers, timeout=60.0
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    return content
                else:
                    logger.error(
                        f"Error en API LLM: {response.status_code} - {response.text}"
                    )
                    return "Lo siento, ha habido un problema con el servicio. Por favor, inténtalo de nuevo más tarde."

        except Exception as e:
            logger.error(f"Error en _call_llm_api: {str(e)}")
            return "Lo siento, ha ocurrido un error al comunicarse con el servicio. Por favor, inténtalo de nuevo."

    def _contains_proposal_markers(self, text: str) -> bool:
        """Detecta si el texto contiene marcadores de una propuesta completa"""
        # Verificar si contiene las secciones principales de la Propuesta
        key_sections = [
            "Important Disclaimer",
            "Introduction to Hydrous Management Group",
            "Project Background",
            "Objective of the Project",
            "Key Design Assumptions",
            "Process Design & Treatment Alternatives",
            "Suggested Equipment & Sizing",
            "Estimated CAPEX & OPEX",
            "Return on Investment",
        ]

        # Contar cuatnas secciones estan presentes
        section_count = sum(1 for section in key_sections if section in text)

        # Si tiene la mayorua de las secciones, consideramos que es una propuesta completa
        return section_count >= 6


# Instancia global
ai_service = AIService()
