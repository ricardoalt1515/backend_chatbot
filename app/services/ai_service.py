# app/services/ai_service.py
import logging
import httpx
import os
from typing import List, Dict, Any
import re

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.main_prompt import get_master_prompt
from app.services import questionnaire_service

logger = logging.getLogger("hydrous")


class AIService:
    """Servicio simplificado para interactuar con LLMs"""

    def __init__(self):
        """Inicialización del servicio AI"""
        selfMASTER_PROMPT = get_master_prompt()
        # Cargar el prompt maestro
        self.master_prompt = get_master_prompt()

        # Cargar archivos de cuestionario y formato de propuesta
        questionnaire_path = os.path.join(
            os.path.dirname(__file__), "../prompts/cuestionario.txt"
        )
        proposal_format_path = os.path.join(
            os.path.dirname(__file__), "../prompts/Format Proposal.txt"
        )

        # Leer estos archivos si existen
        self.questionnaire_content = ""
        self.proposal_format_content = ""

        if os.path.exists(questionnaire_path):
            with open(questionnaire_path, "r", encoding="utf-8") as f:
                self.questionnaire_content = f.read()

        if os.path.exists(proposal_format_path):
            with open(proposal_format_path, "r", encoding="utf-8") as f:
                self.proposal_format_content = f.read()

        # Extraer preguntas del cuestionario
        self.questions = self._parse_questionnaire(self.questionnaire_content)

        # Configuración de API
        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_URL
        self.last_response_id = None  # Para Responses API

    def _parse_questionnaire(self, content: str) -> List[Dict[str, Any]]:
        """Extrae preguntas y opciones del cuestionario"""
        questions = []
        lines = content.split("\n")
        current_question = None

        for line in lines:
            line = line.strip()
            if line.startswith("Pregunta ") or re.match(r"^\d+\.", line):
                if current_question:
                    questions.append(current_question)
                question_text = re.sub(r"^(Pregunta \d+|\d+\.)\s*", "", line)
                current_question = {
                    "text": question_text,
                    "options": [],
                    "id": len(questions) + 1,
                }
            elif line and current_question and re.match(r"^[A-Za-z]\.|^\*\s", line):
                option_text = re.sub(r"^[A-Za-z]\.|\*\s", "", line).strip()
                current_question["options"].append(option_text)

        if current_question:
            questions.append(current_question)

        return questions

    async def handle_conversation(
        self, conversation: Conversation, user_message: str = None
    ) -> str:
        """Maneja una conversación y genera una respuesta simplificada"""
        try:
            # Inicializar el estado si es la primera interacción
            if "current_question" not in conversation.metadata:
                conversation.metadata["current_question"] = 0
                conversation.metadata["responses"] = {}
                return self._format_question(
                    0
                )  # Mostrar la primera pregunta directamente

            current_question_idx = conversation.metadata["current_question"]

            if current_question_idx >= len(self.questions):
                # Fin del cuestionario, generar propuesta
                return await self._generate_proposal(conversation)

            # Procesar la respuesta del usuario
            if user_message:
                selected_option = self._extract_option(
                    user_message, current_question_idx
                )
                if selected_option:
                    conversation.metadata["responses"][
                        str(current_question_idx)
                    ] = selected_option
                    conversation.metadata["current_question"] += 1
                    if conversation.metadata["current_question"] < len(self.questions):
                        return self._format_question(
                            conversation.metadata["current_question"]
                        )
                    else:
                        return await self._generate_proposal(conversation)
                else:
                    return "Por favor, selecciona una opción válida usando el número o el texto de la opción."

            # Si no hay mensaje, mostrar la pregunta actual (esto no debería pasar después de la primera vez)
            return self._format_question(current_question_idx)

        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, inténtalo de nuevo."

    def _prepare_messages(
        self, conversation: Conversation, user_message: str = None
    ) -> List[Dict[str, str]]:
        """Prepara los mensajes para la API del LLM"""
        system_prompt = self.master_prompt

        system_prompt += f"""
        \n\nTu tarea es seguir este cuestionario estrictamente, una pregunta a la vez, en el orden dado. Aquí está el cuestionario completo:

        <cuestionario>
        {self.questionnaire_content}
        </cuestionario>

        Instrucciones:
        1. Haz la pregunta actual y muestra sus opciones numeradas (1, 2, 3, etc.).
        2. Espera la respuesta del usuario (puede ser un número o el texto de la opción).
        3. No pases a la siguiente pregunta hasta que el usuario responda.
        4. Una vez que todas las preguntas estén respondidas, genera una propuesta siguiendo este formato:

        <formato_propuesta>
        {self.proposal_format_content}
        </formato_propuesta>
        """

        messages = [{"role": "system", "content": system_prompt}]

        # Añadir mensajes anteriores
        for msg in conversation.messages:
            if msg.role != "system":
                messages.append({"role": msg.role, "content": msg.content})

        if user_message:
            messages.append({"role": "user", "content": user_message})

        return messages

    def _format_question(self, idx: int) -> str:
        """Formatea una pregunta con sus opciones numeradas"""
        if idx >= len(self.questions):
            return "Cuestionario completado."
        question = self.questions[idx]
        options_text = "\n".join(
            f"{i+1}. {opt}" for i, opt in enumerate(question["options"])
        )
        return f"{question['text']}\n{options_text}"

    def _extract_option(self, user_message: str, question_idx: int) -> str | None:
        """Extrae la opción seleccionada del mensaje del usuario"""
        question = self.questions[question_idx]
        try:
            option_idx = int(user_message.strip()) - 1
            if 0 <= option_idx < len(question["options"]):
                return question["options"][option_idx]
        except ValueError:
            for opt in question["options"]:
                if opt.lower() in user_message.lower():
                    return opt
        return None

    async def _generate_proposal(self, conversation: Conversation) -> str:
        """Genera la propuesta final basada en las respuestas"""
        responses = conversation.metadata["responses"]
        messages = self._prepare_messages(conversation)
        messages.append(
            {
                "role": "user",
                "content": f"Genera una propuesta con estas respuestas:\n{self._format_responses(responses)}",
            }
        )
        return await self._call_llm_api(messages)

    def _format_responses(self, responses: Dict[str, str]) -> str:
        """Formatea las respuestas para incluirlas en el prompt"""
        formatted = ""
        for idx, answer in responses.items():
            question = self.questions[int(idx)]
            formatted += f"{question['text']}: {answer}\n"
        return formatted

    async def _call_llm_api(self, messages: List[Dict[str, str]]) -> str:
        """Llama a la API del LLM (Responses API compatible)"""
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }
                payload = {
                    "model": self.model,
                    "input": (
                        messages[-1]["content"] if messages else ""
                    ),  # Para Responses API
                    "previous_response_id": (
                        self.last_response_id if self.last_response_id else None
                    ),
                }
                response = await client.post(
                    self.api_url, json=payload, headers=headers, timeout=60.0
                )
                if response.status_code == 200:
                    data = response.json()
                    self.last_response_id = data.get(
                        "id"
                    )  # Guardar ID para Responses API
                    # Ajustar según la estructura de la Responses API
                    return (
                        data["output"][0]["content"][0]["text"]
                        if "output" in data
                        else data["choices"][0]["message"]["content"]
                    )
                else:
                    logger.error(
                        f"Error en API: {response.status_code} - {response.text}"
                    )
                    return "Error en la API. Inténtalo de nuevo."
        except Exception as e:
            logger.error(f"Error en _call_llm_api: {str(e)}")
            return "Error al comunicarse con el servicio."

    def _contains_proposal_markers(self, text: str) -> bool:
        """Detecta si el texto contiene marcadores de una propuesta completa"""
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
        section_count = sum(1 for section in key_sections if section in text)
        return section_count >= 6


# Instancia global
ai_service = AIService()
