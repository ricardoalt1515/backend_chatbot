# app/models/conversation.py
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from datetime import datetime
import uuid

from app.models.message import Message
from app.models.questionnaire_state import QuestionnaireState


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    messages: List[Message] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    questionnaire_state: QuestionnaireState = Field(default_factory=QuestionnaireState)

    def add_message(self, message: Message) -> None:
        """Añade un mensaje a la conversación"""
        self.messages.append(message)
        self.updated_at = datetime.now()

    def get_current_question(
        self, questionnaire_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Obtiene la pregunta actual basada en el estado del cuestionario de manera más robusta"""
        # Si no hay sector definido, primero preguntar por el sector
        if not self.questionnaire_state.sector:
            sectors = questionnaire_data.get("sectors", [])
            options_text = "\n".join(
                [f"{i+1}. {sector}" for i, sector in enumerate(sectors)]
            )

            return {
                "id": "sector_selection",
                "text": f"¿En qué sector se encuentra tu empresa?\n\n{options_text}",
                "explanation": "Este dato nos ayuda a entender el tipo de agua que necesitarás tratar y las tecnologías más adecuadas para tu industria.",
            }

        # Si no hay subsector definido, preguntar por el subsector dentro del sector elegido
        if not self.questionnaire_state.subsector:
            subsectors = questionnaire_data.get("subsectors", {}).get(
                self.questionnaire_state.sector, []
            )
            if subsectors:
                options_text = "\n".join(
                    [f"{i+1}. {sub}" for i, sub in enumerate(subsectors)]
                )
                return {
                    "id": "subsector_selection",
                    "text": f"¿Qué tipo específico de {self.questionnaire_state.sector} es?\n\n{options_text}",
                    "explanation": "Esto nos permite personalizar aún más la solución para tu tipo específico de operación.",
                }
            else:
                # Si no hay subsectores disponibles, pasar a las preguntas generales
                self.questionnaire_state.subsector = "General"

        # Obtener las preguntas para el sector/subsector específico
        question_key = (
            f"{self.questionnaire_state.sector}_{self.questionnaire_state.subsector}"
        )
        questions = questionnaire_data.get("questions", {}).get(question_key, [])

        # Si no hay preguntas específicas, intentar con preguntas genéricas del sector
        if not questions:
            question_key = f"{self.questionnaire_state.sector}_General"
            questions = questionnaire_data.get("questions", {}).get(question_key, [])

        # Si aún no hay preguntas, usar preguntas genéricas
        if not questions or self.questionnaire_state.current_question_index >= len(
            questions
        ):
            return None

        return questions[self.questionnaire_state.current_question_index]

    def update_questionnaire_state(
        self, user_message: str, questionnaire_data: Dict[str, Any]
    ) -> None:
        """Actualiza el estado del cuestionario de manera más robusta"""
        # Si aún no se ha definido sector/subsector, procesarlos primero
        if not self.questionnaire_state.sector:
            sectors = questionnaire_data.get("sectors", [])
            # Intentar identificar sector desde el mensaje
            for sector in questionnaire_data.get("sectors", []):
                if sector.lower() in user_message.lower():
                    self.questionnaire_state.sector = sector
                    return

            # Si no se identifica claramente, usar un valor predeterminado o pedir clarificación
            if not self.questionnaire_state.sector and user_message:
                # Podríamos implementar una lógica más sofisticada aquí para determinar el sector
                # Por ahora, simplemente usamos el primer sector si no hay una coincidencia clara
                self.questionnaire_state.sector = questionnaire_data.get(
                    "sectors", ["Industrial"]
                )[0]

            return

        if not self.questionnaire_state.subsector:
            # Intentar identificar subsector desde el mensaje
            subsectors = questionnaire_data.get("subsectors", {}).get(
                self.questionnaire_state.sector, []
            )
            for i, subsector in enumerate(subsectors):
                # Comprobar tanto el nombre como el número de la opción
                if (
                    subsector.lower() in user_message.lower()
                    or user_message.strip() == str(i + 1)
                ):
                    self.questionnaire_state.subsector = subsector
                    break

            # Si no se identifica claramente, usar un valor predeterminado
            if not self.questionnaire_state.subsector and user_message:
                if subsectors:
                    # Si el usuario ingresó un número, intentar usarlo como índice
                    try:
                        index = int(user_message.strip()) - 1
                        if 0 <= index < len(subsectors):
                            self.questionnaire_state.subsector = subsectors[index]
                    except ValueError:
                        # Si no es un número válido, usar el primer subsector
                        self.questionnaire_state.subsector = subsectors[0]
                else:
                    self.questionnaire_state.subsector = "General"

            return

        # Procesar la respuesta a la pregunta actual
        current_question = self.get_current_question(questionnaire_data)
        if current_question:
            # Actualizar la respuesta en el estado
            self.questionnaire_state.update_answer(current_question["id"], user_message)
            self.questionnaire_state.presented_questions.append(current_question["id"])

            # Avanzar a la siguiente pregunta
            self.questionnaire_state.current_question_index += 1


class ConversationResponse(BaseModel):
    id: str
    created_at: datetime
    messages: List[Message]
