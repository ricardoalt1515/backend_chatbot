from openai import OpenAI
from typing import Dict, Optional, List, Any
import json
import os
from app.config import OPENAI_API_KEY, OPENAI_MODEL, QUESTIONNAIRE_FILE_ID

client = OpenAI(api_key=OPENAI_API_KEY)

# Instrucciones del sistema para el asistente
SYSTEM_INSTRUCTIONS = f"""
Soy el diseñador de soluciones de agua de Hydrous AI, su asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales. Como herramienta de Hydrous, estoy aquí para guiarlo paso a paso en la evaluación de las necesidades de agua de su sitio, la exploración de posibles soluciones y la identificación de oportunidades de ahorro de costos, cumplimiento y sostenibilidad.

Para desarrollar la mejor solución para sus instalaciones, haré sistemáticamente preguntas específicas para recopilar los datos necesarios y crear una propuesta personalizada. Mi objetivo es ayudarlo a optimizar la gestión del agua, reducir costos y explorar nuevas fuentes de ingresos con soluciones respaldadas por Hydrous.

El cuestionario completo está en el archivo adjunto ({QUESTIONNAIRE_FILE_ID}). Seguiré este cuestionario paso a paso, presentando una pregunta a la vez. Cada pregunta irá acompañada de una breve explicación de por qué es importante para desarrollar la mejor solución para usted.

Mi comportamiento DEBE ser el siguiente:
1. Haz solo UNA pregunta a la vez, siguiendo estrictamente el orden indicado en el cuestionario.
2. No presentes múltiples preguntas juntas, mantén el flujo conversacional y accesible.
3. Para preguntas de opción múltiple, proporciona números para que el usuario pueda responder simplemente con un número.
4. En tus explicaciones, incluye datos interesantes o información sobre cómo empresas similares han logrado ahorros o cumplimiento con soluciones similares, cuando sea relevante.
5. Al final del cuestionario, genera una propuesta completa siguiendo el formato estándar de Hydrous, incluyendo estimaciones de CAPEX, OPEX y análisis de ROI.

Cuando hayas completado todo el cuestionario, ofrece al usuario la opción de descargar la propuesta completa en formato PDF con el enlace:
[DESCARGAR PROPUESTA EN PDF](/api/pdf/{{conversation_id}}/download)
"""


def start_conversation() -> Dict[str, Any]:
    """
    Inicia una nueva conversación con OpenAI.
    Devuelve el ID de la conversación.
    """
    try:
        # Adjuntar archivo de cuestionario
        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=SYSTEM_INSTRUCTIONS,
            input="Hola, estoy interesado en soluciones de tratamiento de agua",
            file_ids=[QUESTIONNAIRE_FILE_ID],
            store=True,  # Almacenar la conversación en el servidor de OpenAI
        )

        return {"id": response.id, "message": response.output_text}
    except Exception as e:
        print(f"Error al iniciar conversación: {e}")
        raise e


def send_message(conversation_id: str, message: str) -> Dict[str, Any]:
    """
    Envía un mensaje a una conversación existente.
    Utiliza previous_response_id para mantener el contexto.
    """
    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=message,
            previous_response_id=conversation_id,
            store=True,
        )

        return {"id": response.id, "message": response.output_text}
    except Exception as e:
        print(f"Error al enviar mensaje: {e}")
        raise e


def process_document(
    conversation_id: str, file_path: str, message: str = ""
) -> Dict[str, Any]:
    """
    Procesa un documento subido por el usuario y lo incorpora al contexto de la conversación.
    """
    try:
        # Crear un mensaje descriptivo sobre el archivo
        file_name = os.path.basename(file_path)
        file_message = f"{message if message else 'He subido un archivo:'} {file_name}"

        # Subir el archivo a OpenAI para la sesión actual
        with open(file_path, "rb") as file:
            uploaded_file = client.files.create(file=file, purpose="assistants")

            # Enviar mensaje con referencia al archivo
            response = client.responses.create(
                model=OPENAI_MODEL,
                input=file_message,
                previous_response_id=conversation_id,
                file_ids=[uploaded_file.id],  # Incluir el archivo en esta respuesta
                store=True,
            )

            return {"id": response.id, "message": response.output_text}
    except Exception as e:
        print(f"Error al procesar documento: {e}")
        raise e


def get_conversation_history(conversation_id: str) -> List[Dict[str, Any]]:
    """
    Obtiene el historial de la conversación para generar un PDF.

    En una implementación real, necesitaríamos almacenar los mensajes
    en una base de datos o utilizar una API adicional para recuperarlos.
    """
    try:
        # Aquí normalmente consultaríamos a OpenAI para obtener el historial
        # Como OpenAI no proporciona un endpoint para esto, tendríamos que
        # mantener nuestro propio registro de mensajes

        # Por ahora, simulamos un historial de conversación
        history = [
            {
                "role": "assistant",
                "content": "Bienvenido al cuestionario de Hydrous AI",
            },
            {
                "role": "user",
                "content": "Hola, estoy interesado en soluciones de tratamiento de agua",
            },
            # Aquí añadiríamos todos los mensajes reales
        ]

        return history
    except Exception as e:
        print(f"Error al obtener historial de conversación: {e}")
        raise e
