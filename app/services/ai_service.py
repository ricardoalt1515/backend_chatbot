# app/services/ai_service.py
import logging
import httpx
import json
import os
from typing import List, Dict, Any, Optional

from app.config import settings
from app.models.conversation import Conversation
from app.prompts.main_prompt import get_master_prompt
from app.services.conversation_flow_service import ConversationFlowService
from app.services.proposal_generator import proposal_generator

logger = logging.getLogger("hydrous")


class AIService:
    """Servicio para interactuar con LLMs con manejo mejorado del flujo de conversación"""

    def __init__(self):
        """Inicialización del servicio AI"""
        # Cargar datos del cuestionario
        self.questionnaire_data = self._load_questionnaire_data_sync()

        # Cargar el prompt maestro
        self.master_prompt = get_master_prompt(self.questionnaire_data)

        # Inicializar servicio de flujo de conversación
        self.conversation_flow_service = ConversationFlowService(
            self.questionnaire_data
        )

        # Configuración de API
        self.api_key = settings.API_KEY
        self.model = settings.MODEL
        self.api_url = settings.API_URL

    def _load_questionnaire_data_sync(self) -> Dict[str, Any]:
        """Carga los datos del cuestionario de forma síncrona"""
        try:
            questionnaire_path = os.path.join(
                os.path.dirname(__file__), "../prompts/questionnaire_complete.json"
            )

            if os.path.exists(questionnaire_path):
                with open(questionnaire_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                logger.warning(
                    f"No se encontró el archivo de cuestionario en {questionnaire_path}"
                )
                # Devolver una estructura mínima para evitar errores
                return {
                    "sectors": ["Industrial", "Comercial"],
                    "subsectors": {
                        "Industrial": ["Textil", "Alimentos y Bebidas"],
                        "Comercial": ["Hotel", "Restaurante"],
                    },
                    "questions": {},
                }
        except Exception as e:
            logger.error(f"Error al cargar datos del cuestionario: {str(e)}")
            return {"sectors": [], "subsectors": {}, "questions": {}}

    async def handle_conversation(
        self, conversation: Conversation, user_message: str = None
    ) -> str:
        """
        Maneja una conversación y genera una respuesta con mejor control de flujo
        """
        try:
            # Actualizar estado del cuestionario si hay un nuevo mensaje
            if user_message:
                conversation.update_questionnaire_state(
                    user_message, self.questionnaire_data
                )

            # Verificar si el cuestionario está completo
            is_complete = self.conversation_flow_service.is_questionnaire_complete(
                conversation
            )

            # Si está completo, actualizar metadata
            if is_complete and not conversation.questionnaire_state.is_complete:
                conversation.questionnaire_state.is_complete = True
                conversation.metadata["questionnaire_complete"] = True
                logger.info(
                    f"Cuestionario completo para conversación {conversation.id}"
                )

            # Obtener próxima pregunta si no está completo
            next_question = (
                None
                if is_complete
                else conversation.get_current_question(self.questionnaire_data)
            )

            # Preparar los mensajes para la API con contexto mejorado
            messages = self._prepare_messages_enhanced(
                conversation, user_message, next_question, is_complete
            )

            # Llamar a la API del LLM
            response = await self._call_llm_api(messages)

            # Detectar si el mensaje contiene una propuesta completa
            if "[PROPOSAL_COMPLETE:" in response or self._contains_proposal_markers(
                response
            ):
                conversation.metadata["has_proposal"] = True

                # Usar URL completa en lugar de relativa
                backend_url = (
                    settings.BACKEND_URL or "https://backend-chatbot-owzs.onrender.com"
                )

                # Añadir instrucciones para descargar PDF
                download_instructions = f"""

## 📥 Descargar Propuesta en PDF

Para descargar esta propuesta en formato PDF, por favor haz clic en el siguiente enlace:

**👉 [DESCARGAR PROPUESTA EN PDF]({backend_url}/api/chat/{conversation.id}/download-pdf)**
    
Este documento incluye todos los detalles discutidos y puede ser compartido con tu equipo.
"""
                # Solo añadir las instrucciones si aún no están presentes
                if "DESCARGAR PROPUESTA EN PDF" not in response:
                    response += download_instructions

            # Si ya hay una propuesta pero no se añadieron las instrucciones de descarga
            elif (
                conversation.metadata.get("has_proposal", False)
                and "DESCARGAR PROPUESTA" not in response
            ):
                # Verificar si el usuario está solicitando la propuesta
                download_keywords = [
                    "pdf",
                    "descargar",
                    "documento",
                    "propuesta",
                    "guardar",
                    "enviar",
                ]
                if user_message and any(
                    keyword in user_message.lower() for keyword in download_keywords
                ):
                    download_instructions = f"""

## 📥 Descargar Propuesta en PDF

Puedes descargar la propuesta completa en formato PDF haciendo clic en el siguiente enlace:

**👉 [DESCARGAR PROPUESTA EN PDF]({settings.BACKEND_URL}/api/chat/{conversation.id}/download-pdf)**

Este documento incluye todos los detalles discutidos y puede ser compartido con tu equipo.
"""
                    response += download_instructions

            # Actualizar metadata de la conversación si necesitamos generar un PDF
            if conversation.metadata.get(
                "has_proposal", False
            ) and not conversation.metadata.get("pdf_requested"):
                conversation.metadata["pdf_requested"] = True

                # Generar PDF en segundo plano si no se ha generado aún
                if not conversation.metadata.get("pdf_path"):
                    # Marcar como pendiente para generar PDF
                    conversation.metadata["pdf_pending"] = True

            return response

        except Exception as e:
            logger.error(f"Error en handle_conversation: {str(e)}")
            return "Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, inténtalo de nuevo."

    def _prepare_messages_enhanced(
        self,
        conversation: Conversation,
        user_message: str = None,
        next_question: Optional[Dict] = None,
        is_complete: bool = False,
    ) -> List[Dict[str, str]]:
        """Prepara los mensajes para la API con mejor contexto y control de flujo"""
        # Mensaje inicial del sistema con el prompt maestro
        messages = [{"role": "system", "content": self.master_prompt}]

        # Añadir contexto actual como mensaje del sistema
        context_summary = conversation.questionnaire_state.get_context_summary()
        if context_summary:
            context_message = {
                "role": "system",
                "content": f"CONTEXTO ACTUAL:\n{context_summary}\n\nUtiliza esta información para personalizar tus respuestas.",
            }
            messages.append(context_message)

        # Obtener hechos relevantes para el sector/industria
        relevant_facts = self.conversation_flow_service.get_relevant_facts(conversation)
        if relevant_facts:
            facts_message = {
                "role": "system",
                "content": f"HECHOS EDUCATIVOS PARA USAR:\n- {relevant_facts[0]}\n- {relevant_facts[1] if len(relevant_facts) > 1 else 'Las soluciones personalizadas pueden reducir significativamente los costos operativos.'}",
            }
            messages.append(facts_message)

        # Información específica de la próxima pregunta
        if next_question:
            question_info = {
                "role": "system",
                "content": f"SIGUIENTE PREGUNTA:\n{next_question['text']}\n\nAsegúrate de hacer SOLO esta pregunta en tu próxima respuesta.",
            }
            messages.append(question_info)

        # Indicar si es momento de generar la propuesta
        if is_complete:
            # Generar instrucciones específicas para la propuesta
            proposal_instructions = proposal_generator.generate_proposal_instructions(
                conversation
            )

            completion_message = {
                "role": "system",
                "content": f"El cuestionario está COMPLETO. {proposal_instructions}",
            }
            messages.append(completion_message)

        # Añadir mensajes anteriores de la conversación (limitar para evitar exceder tokens)
        hist_limit = 8  # Ajustar según necesidad
        for msg in conversation.messages[-hist_limit:]:
            if msg.role != "system":  # No duplicar mensajes del sistema
                messages.append({"role": msg.role, "content": msg.content})

        # Si hay un nuevo mensaje, añadirlo
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
            # Verificar si hay API key configurada
            if not self.api_key:
                logger.error("API Key no configurada. Revisa tus variables de entorno.")
                return "Error de configuración: API Key no disponible. Contacta al administrador."

            # Mostrar qué proveedor y modelo estamos usando (para debugging)
            logger.info(
                f"Usando proveedor: {settings.API_PROVIDER} con modelo: {self.model}"
            )

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
                    "max_tokens": 2000,  # Aumentando para propuestas completas
                }

                # Añadir timeout más largo para evitar problemas con respuestas lentas
                response = await client.post(
                    self.api_url, json=payload, headers=headers, timeout=90.0
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    return content
                elif response.status_code == 401:
                    logger.error(
                        f"Error de autenticación: API Key inválida para {settings.API_PROVIDER}"
                    )
                    return "Lo siento, hay un problema de autenticación con el servicio. Por favor, contacta al administrador del sistema."
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
            "Información del Cliente",
            "Objetivos del Proyecto",
            "Parámetros de Diseño",
            "Diseño del Proceso",
            "Equipamiento Sugerido",
            "CAPEX",
            "OPEX",
            "ROI",
            "Análisis de Retorno de Inversión",
            "Hydrous Management Group",
        ]

        # Contar cuántas secciones están presentes
        section_count = sum(1 for section in key_sections if section in text)

        # Si tiene la mayoría de las secciones, consideramos que es una propuesta completa
        return section_count >= 5


# Instancia global
ai_service = AIService()
