# app/services/ai_service.py
import logging
import httpx
from typing import List, Dict, Any

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.main_prompt import get_master_prompt

logger = logging.getLogger("hydrous")


class AIService:
    """Servicio simplificado para interactuar con LLMs"""

    def __init__(self):
        """Inicialización del servicio AI"""
        # Cargar el prompt maestro
        self.master_prompt = get_master_prompt()

        # Configuración de API
        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_URL

    async def handle_conversation(
        self, conversation: Conversation, user_message: str = None
    ) -> str:
        """
        Maneja una conversación y genera una respuesta
        """
        try:
            # Preparar los mensajes para la API
            messages = self._prepare_messages(conversation, user_message)

            # Llamar a la API del LLM
            response = await self._call_llm_api(messages)

            # Detectar si el mensaje contiene una propuesta completa
            if self._contains_proposal_markers(response):
                conversation.metadata["has_proposal"] = True

            return response

        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, inténtalo de nuevo."

    def _prepare_messages(self, conversation: Conversation, user_message: str = None):
        # Mensaje sistema base con el prompt maestro optimizado
        messages = [{"role": "system", "content": self.master_prompt}]

        # Detectar fase actual e información clave
        message_count = sum(1 for m in conversation.messages if m.role == "user")
        need_summary = message_count > 0 and message_count % 5 == 0

        # Si es momento de hacer resumen, añadir instrucción específica
        if need_summary:
            summary_instruction = {
                "role": "system",
                "content": "Antes de hacer la siguiente pregunta, proporciona un BREVE RESUMEN de la información clave recopilada hasta ahora. Luego continúa con la siguiente pregunta del cuestionario.",
            }
            messages.append(summary_instruction)

        # Si hemos detectado un posible sector, ajustar instrucciones
        if "sector" in conversation.metadata:
            sector = conversation.metadata["sector"]
            sector_instruction = {
                "role": "system",
                "content": f"El usuario pertenece al sector {sector}. Utiliza los datos educativos específicos para este sector.",
            }
            messages.append(sector_instruction)

        # Añadir mensaje final de recordatorio de estructura
        structure_reminder = {
            "role": "system",
            "content": "RECUERDA: Tu próxima respuesta DEBE seguir la estructura exacta: 1) Validación positiva, 2) Comentario específico, 3) Dato educativo con emoji 💡, 4) Explicación breve, 5) UNA SOLA pregunta en negrita.",
        }
        messages.append(structure_reminder)

        # Añadir historial de conversación (limitado)
        for msg in conversation.messages[-12:]:
            if msg.role != "system":
                messages.append({"role": msg.role, "content": msg.content})

        # Añadir nuevo mensaje si existe
        if user_message:
            messages.append({"role": "user", "content": user_message})

        return messages

    def _get_phase_instructions(self, phase, conversation):
        """Genera instrucciones especificas, segun la fase"""
        if phase == "initial_questions":
            return "Estas en la fase inicial de recopilacion de información. Concentrate en preguntas basicas sobre la empresa, ubicacion y conusmo de agua"

        elif phase == "detailed_questions":
            # Es momento de hacer un resumen si hay suficiente información
            questions_answered = sum(
                1 for msg in conversation.messages if msg.role == "user"
            )
            if questions_answered % 5 == 0 and questions_answered > 0:
                return """
                Haz un breve resumen de la información recopilada hasta ahora antes de hacer la siguiente pregunta.
                El resumen debe ser conciso y destacar los puntos clave que has aprendido sobre el proyecto.
                """
            return "Continúa con las preguntas detalladas sobre procesos específicos de agua."

        elif phase == "final_questions":
            return "Estás en las preguntas finales. Prioriza preguntas sobre restricciones, objetivos principales y plazos."

        elif phase == "proposal_generation":
            return """
            Has recopilado suficiente información. Genera una propuesta completa siguiendo el formato establecido:
            1. Título con nombre del cliente
            2. Antecedentes del proyecto
            3. Objetivos
            4. Parámetros de diseño
            5. Proceso de tratamiento propuesto
            6. Capacidades estimadas
            7. Costos estimados
            8. Análisis ROI
            9. Siguientes pasos
            """

        else:  # proposal_complete
            return "El usuario ya tiene una propuesta completa. Responde a sus preguntas adicionales o aclaraciones."

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
            "Propuesta",
            "Antecedentes del Proyecto",
            "Objetivo del Proyecto",
            "Parámetros de Diseño",
            "Proceso de Tratamiento",
        ]

        marker_count = sum(1 for marker in markers if marker in text)
        return marker_count >= 3


# Instancia global
ai_service = AIService()
