import groq
import openai
import logging
from typing import List, Dict, Any, Optional

from app.config import settings

logger = logging.getLogger("hydrous-backend")


class AIService:
    """Servicio para interactuar con modelos de IA"""

    def __init__(self):
        self.provider = settings.AI_PROVIDER

        # Inicializar cliente de Groq
        if self.provider == "groq":
            if not settings.GROQ_API_KEY:
                logger.warning(
                    "GROQ_API_KEY no configurada. Las llamadas a la API fallarán."
                )
            self.groq_client = groq.Client(api_key=settings.GROQ_API_KEY)
            self.groq_model = settings.GROQ_MODEL

        # Inicializar cliente de OpenAI
        elif self.provider == "openai":
            if not settings.OPENAI_API_KEY:
                logger.warning(
                    "OPENAI_API_KEY no configurada. Las llamadas a la API fallarán."
                )
            self.openai_client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            self.openai_model = settings.OPENAI_MODEL

        else:
            raise ValueError(f"Proveedor de IA no soportado: {self.provider}")

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Genera una respuesta utilizando el proveedor de IA configurado

        Args:
            messages: Lista de mensajes para la conversación
            temperature: Temperatura para la generación (0.0-1.0)
            max_tokens: Número máximo de tokens para la respuesta

        Returns:
            str: Texto de la respuesta generada
        """
        try:
            if self.provider == "groq":
                return await self._generate_with_groq(messages, temperature, max_tokens)
            elif self.provider == "openai":
                return await self._generate_with_openai(
                    messages, temperature, max_tokens
                )
            else:
                raise ValueError(f"Proveedor no soportado: {self.provider}")
        except Exception as e:
            logger.error(f"Error al generar respuesta con {self.provider}: {str(e)}")
            # Respuesta de fallback en caso de error
            return "Lo siento, estoy teniendo problemas para procesar tu solicitud en este momento. Por favor, intenta de nuevo más tarde."

    async def _generate_with_groq(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Genera respuesta utilizando Groq"""
        response = self.groq_client.chat.completions.create(
            model=self.groq_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens or 1024,
        )
        return response.choices[0].message.content

    async def _generate_with_openai(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Genera respuesta utilizando OpenAI"""
        response = self.openai_client.chat.completions.create(
            model=self.openai_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens or 1024,
        )
        return response.choices[0].message.content


# Instancia global del servicio
ai_service = AIService()
