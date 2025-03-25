# app/services/ai_service.py
import logging
import httpx
import json
import os
from typing import List, Dict, Any

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.main_prompt import get_master_prompt

logger = logging.getLogger("hydrous")


class AIService:
    """Servicio simplificado para interactuar con LLMs"""

    def __init__(self):
        """Inicialización del servicio AI"""
        # Cargar datos del cuestionario y hechos
        self.questionnaire_data = self._load_questionnaire_data()
        self.facts_data = self._load_facts_data()

        # Cargar el prompt maestro
        self.master_prompt = get_master_prompt(
            questionnaire_data=self.questionnaire_data, facts_data=self.facts_data
        )

        # Configuración de API
        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_URL

    def _load_questionnaire_data(self) -> Dict[str, Any]:
        """Carga los datos del cuestionario"""
        try:
            # Intentar cargar desde archivo
            questionnaire_path = os.path.join(
                os.path.dirname(__file__), "../prompts/questionnaire_complete.json"
            )
            if os.path.exists(questionnaire_path):
                with open(questionnaire_path, "r", encoding="utf-8") as f:
                    return json.load(f)

            logger.warning("Archivo de cuestionario no encontrado.")
            return {}
        except Exception as e:
            logger.error(f"Error al cargar datos del cuestionario: {str(e)}")
            return {}

    def _load_facts_data(self) -> Dict[str, List[str]]:
        """Carga los hechos/datos para diferentes sectores"""
        try:
            # Intentar extraer hechos del cuestionario
            questionnaire_data = self._load_questionnaire_data()
            return questionnaire_data.get("facts", {})
        except Exception as e:
            logger.error(f"Error al cargar datos de hechos: {str(e)}")
            return {}

    async def handle_conversation(
        self, conversation: Conversation, user_message: str = None
    ) -> str:
        """
        Maneja una conversación y genera una respuesta
        """
        try:
            # Si es un nuevo mensaje, procesar para actualizar el estado del cuestionario
            if user_message:
                self._update_questionnaire_state(conversation, user_message)

            # Preparar los mensajes para la API
            messages = self._prepare_messages(conversation, user_message)

            # Llamar a la API del LLM
            response = await self._call_llm_api(messages)

            # Detectar si el mensaje contiene una propuesta completa
            if self._contains_proposal_markers(response):
                conversation.metadata["has_proposal"] = True
                conversation.questionnaire_state.is_complete = True

            return response

        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, inténtalo de nuevo."

    def _update_questionnaire_state(
        self, conversation: Conversation, user_message: str
    ) -> None:
        """Actualiza el estado del cuestionario basado en el mensaje del usuario"""
        state = conversation.questionnaire_state

        # Si no hay sector seleccionado, intentar identificarlo
        if not state.sector:
            for sector in self.questionnaire_data.get("sectors", []):
                if sector.lower() in user_message.lower():
                    state.sector = sector
                    return

        # Si hay sector pero no subsector, intentar identificarlo
        elif not state.subsector and state.sector:
            subsectors = self.questionnaire_data.get("subsectors", {}).get(
                state.sector, []
            )
            for subsector in subsectors:
                if subsector.lower() in user_message.lower():
                    state.subsector = subsector
                    return

        # Si ya tenemos sector y subsector, guardar la respuesta a la pregunta actual
        elif state.sector and state.subsector:
            question_key = f"{state.sector}_{state.subsector}"
            questions = self.questionnaire_data.get("questions", {}).get(
                question_key, []
            )

            if state.current_question_index < len(questions):
                current_question = questions[state.current_question_index]
                state.update_answer(current_question["id"], user_message)
                state.mark_question_presented(current_question["id"])
                state.set_next_question()  # Avanzar a la siguiente pregunta

    def _prepare_messages(
        self, conversation: Conversation, user_message: str = None
    ) -> List[Dict[str, str]]:
        """Prepara los mensajes para la API del LLM"""
        # Mensaje inicial del sistema con el prompt maestro
        messages = [{"role": "system", "content": self.master_prompt}]

        # Añadir contexto sobre el estado del cuestionario
        state = conversation.questionnaire_state
        if state.sector:
            sector_context = f"El usuario está en el sector: {state.sector}"
            if state.subsector:
                sector_context += f", subsector: {state.subsector}"

            # Añadir información sobre la pregunta actual
            if state.sector and state.subsector:
                question_key = f"{state.sector}_{state.subsector}"
                questions = self.questionnaire_data.get("questions", {}).get(
                    question_key, []
                )

                if state.current_question_index < len(questions):
                    current_question = questions[state.current_question_index]
                    sector_context += (
                        f"\nLa siguiente pregunta es: {current_question['text']}"
                    )
                    if (
                        current_question.get("type") == "multiple_choice"
                        or current_question.get("type") == "multiple_select"
                    ):
                        options = current_question.get("options", [])
                        options_text = "\n".join(
                            [f"{i+1}. {option}" for i, option in enumerate(options)]
                        )
                        sector_context += f"\nOpciones:\n{options_text}"

            messages.append({"role": "system", "content": sector_context})

        # Añadir resumen de respuestas previas
        if state.answers:
            answers_summary = "Respuestas proporcionadas hasta ahora:\n"
            for q_id, answer in state.answers.items():
                answers_summary += f"- {q_id}: {answer}\n"
            messages.append({"role": "system", "content": answers_summary})

        # Añadir mensajes anteriores de la conversación (limitar para evitar exceder tokens)
        for msg in conversation.messages[-15:]:
            if msg.role != "system":  # No duplicar mensajes del sistema
                messages.append({"role": msg.role, "content": msg.content})

        # Si hay un nuevo mensaje y no es igual al último, añadirlo
        if user_message and (
            not messages
            or messages[-1]["role"] != "user"
            or messages[-1]["content"] != user_message
        ):
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
                    "max_tokens": 1500,
                }

                response = await client.post(
                    self.api_url, json=payload, headers=headers, timeout=30.0
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
        markers = [
            "Hydrous Management Group",
            "Antecedentes del Proyecto",
            "Objetivo del Proyecto",
            "Proceso de Diseño",
            "CAPEX & OPEX",
        ]

        marker_count = sum(1 for marker in markers if marker in text)
        return marker_count >= 3


# Instancia global
ai_service = AIService()
