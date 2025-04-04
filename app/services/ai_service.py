# app/services/ai_service.py
import logging
import httpx
import os
from typing import List, Dict, Any

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.main_prompt import get_master_prompt  # Importar prompt limpio

logger = logging.getLogger("hydrous")


class AIService:
    """Servicio para interactuar con LLMs para tareas específicas."""

    def __init__(self):
        """Inicialización del servicio AI."""
        self.master_prompt_template = (
            get_master_prompt()
        )  # Cargar plantilla base del prompt

        # Cargar formato de propuesta
        proposal_format_path = os.path.join(
            os.path.dirname(__file__), "../prompts/Format Proposal.txt"
        )
        self.proposal_format_content = ""
        try:
            if os.path.exists(proposal_format_path):
                with open(proposal_format_path, "r", encoding="utf-8") as f:
                    self.proposal_format_content = f.read()
            else:
                logger.error(
                    f"Archivo de formato de propuesta no encontrado en: {proposal_format_path}"
                )
                # Podrías definir un formato básico aquí como fallback si quieres
                self.proposal_format_content = "# Formato de Propuesta Básico\n..."
        except Exception as e:
            logger.error(f"Error al cargar formato de propuesta: {e}", exc_info=True)
            self.proposal_format_content = "Error al cargar formato."

        # Configuración de API
        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_URL
        if not self.api_key:
            logger.critical(
                "¡Clave API de IA no configurada (OPENAI_API_KEY o GROQ_API_KEY)! El servicio no funcionará."
            )
        if not self.api_url:
            logger.critical("¡URL de API de IA no configurada!")

    async def _call_llm_api(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1500,
        temperature: float = 0.5,
    ) -> str:
        """Llama a la API del LLM de forma genérica."""
        if not self.api_key or not self.api_url:
            error_msg = "Error de configuración: Clave API o URL no proporcionada."
            logger.error(error_msg)
            return error_msg

        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                }
                # Ajustar payload según proveedor si es necesario (OpenAI/Groq suelen ser compatibles)
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    # "stream": False, # Asegurarse que no está en modo stream para respuestas completas
                }

                logger.debug(
                    f"Llamando a API LLM: {self.api_url} con modelo {self.model}"
                )
                # logger.debug(f"Payload (primeros mensajes): {messages[:2]}") # Loggear parte del payload para debug

                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=90.0,  # Aumentar timeout
                )

                response.raise_for_status()  # Lanza excepción para errores HTTP 4xx/5xx

                data = response.json()
                content = (
                    data.get("choices", [{}])[0].get("message", {}).get("content", "")
                )
                logger.debug(
                    f"Respuesta LLM recibida (primeros 100 chars): {content[:100]}"
                )
                if not content:
                    logger.warning("Respuesta del LLM vacía.")
                    return "(El asistente no proporcionó una respuesta)"

                return content.strip()

        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            logger.error(
                f"Error HTTP en API LLM: {e.response.status_code} - {error_body}",
                exc_info=True,
            )
            return f"Error al contactar el servicio de IA ({e.response.status_code}). Detalles: {error_body[:500]}"  # Devolver más info
        except httpx.RequestError as e:
            logger.error(f"Error de red llamando a API LLM: {e}", exc_info=True)
            return f"Error de red al contactar el servicio de IA: {e}"
        except Exception as e:
            logger.error(f"Error inesperado en _call_llm_api: {str(e)}", exc_info=True)
            return "Lo siento, ha ocurrido un error inesperado al procesar la solicitud con la IA."

    async def generate_educational_insight(
        self, conversation: Conversation, last_user_answer: str
    ) -> str:
        """Genera un breve insight educativo basado en la última respuesta."""
        if not conversation.state or not conversation.state.current_question_id:
            return ""  # No hay contexto para generar insight

        # Construir prompt específico para el insight
        system_prompt = (
            self.master_prompt_template
            + "\n\n**TAREA ACTUAL:** Genera un breve insight educativo (1-2 frases) basado en la última respuesta del usuario. Sé conciso y relevante para su sector."
        )

        # Obtener detalles de la última pregunta hecha (la que acaba de responder)
        from app.services.questionnaire_service import (
            questionnaire_service,
        )  # Import local para evitar ciclo

        last_question_details = questionnaire_service.get_question(
            conversation.state.current_question_id
        )
        last_question_text = (
            last_question_details.get("text", "la pregunta anterior")
            if last_question_details
            else "la pregunta anterior"
        )

        user_context = f"Contexto: El usuario opera en el sector '{conversation.state.selected_sector or 'No especificado'}' / subsector '{conversation.state.selected_subsector or 'No especificado'}'. Acaba de responder a la pregunta '{last_question_text}' con: '{last_user_answer}'."

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": user_context
                + "\n\nPor favor, proporciona solo el insight educativo solicitado, sin saludos ni comentarios adicionales.",
            },
            # Podríamos añadir algunos mensajes previos del chat para más contexto si fuera necesario
            # *pero puede hacer la respuesta menos enfocada*
        ]

        # Llamar al LLM con pocos tokens, ya que la respuesta debe ser corta
        insight = await self._call_llm_api(messages, max_tokens=150, temperature=0.6)

        # Limpieza simple por si añade frases extra
        if insight and not insight.startswith("Error"):
            # Formatear consistentemente
            return f"📊 *Insight:* {insight}"
        else:
            logger.warning(f"No se pudo generar insight o hubo error: {insight}")
            return ""  # Devolver vacío si falla

    async def generate_proposal_text(self, conversation: Conversation) -> str:
        """Genera el texto completo de la propuesta usando el LLM."""
        if not conversation.state or not conversation.state.collected_data:
            return "Error: No hay datos recopilados para generar la propuesta."
        if not self.proposal_format_content or "Error" in self.proposal_format_content:
            return "Error: No se pudo cargar la plantilla de la propuesta."

        logger.info(
            f"Iniciando generación de propuesta para conversación {conversation.id}"
        )

        # Preparar los datos recolectados en un formato legible para el LLM
        collected_data_summary = "\n## Datos Recopilados del Usuario:\n"
        for q_id, answer in conversation.state.collected_data.items():
            # Obtener el texto de la pregunta para dar contexto
            from app.services.questionnaire_service import questionnaire_service

            question_details = questionnaire_service.get_question(q_id)
            q_text = question_details.get("text", q_id) if question_details else q_id
            collected_data_summary += f"- **{q_text}:** {answer}\n"

        # Construir el prompt para la generación de la propuesta
        system_prompt = (
            self.master_prompt_template
            + "\n\n**TAREA ACTUAL:** Generar una propuesta técnica y económica preliminar COMPLETA."
            + "\nUtiliza los 'Datos Recopilados del Usuario' proporcionados y sigue ESTRICTAMENTE la 'Plantilla de Propuesta' adjunta."
            + "\nAplica tus conocimientos técnicos en tratamiento de agua para proponer soluciones lógicas, estimar tamaños/costos (con descargos de responsabilidad) y calcular ROI."
            + "\nRecuerda manejar la incertidumbre si faltan datos y añadir TODOS los descargos de responsabilidad necesarios."
            + "\n**IMPRESCINDIBLE:** Finaliza TODA la respuesta con la etiqueta `[PROPOSAL_COMPLETE: Propuesta lista para PDF]` y NADA MÁS después de ella."
        )

        # Añadir la plantilla al prompt del sistema o como mensaje separado
        system_prompt += (
            "\n\n<plantilla_propuesta>\n"
            + self.proposal_format_content
            + "\n</plantilla_propuesta>"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            # Proporcionar los datos como mensaje de usuario parece funcionar bien
            {
                "role": "user",
                "content": collected_data_summary
                + "\n\nPor favor, genera la propuesta completa siguiendo la plantilla y las instrucciones.",
            },
            # Incluir historial de chat es probablemente DEMASIADO contexto aquí y puede distraer al LLM.
            # Nos enfocamos en los datos recolectados y la plantilla.
        ]

        # Llamar al LLM con más tokens permitidos para la propuesta
        proposal_text = await self._call_llm_api(
            messages, max_tokens=3500, temperature=0.5
        )  # Más tokens, menos creatividad

        # Verificar y/o añadir el marcador final si el LLM lo olvidó
        if "[PROPOSAL_COMPLETE:" not in proposal_text:
            logger.warning(
                f"El LLM no incluyó el marcador final. Añadiéndolo manualmente. ID: {conversation.id}"
            )
            proposal_text += "\n\n[PROPOSAL_COMPLETE: Propuesta lista para PDF]"

        logger.info(
            f"Texto de propuesta generado para {conversation.id} (longitud: {len(proposal_text)})"
        )
        return proposal_text


# Instancia global
ai_service = AIService()
