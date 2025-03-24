from fastapi import APIRouter, HTTPException, Depends, Body, BackgroundTasks, Response
from fastapi.responses import FileResponse
import logging
from typing import Dict, Any, List, Optional
import os
import time
from datetime import datetime

from app.models.conversation import (
    Conversation,
    ConversationCreate,
    ConversationResponse,
)
from app.models.message import Message, MessageCreate, MessageResponse
from app.services.storage_service import storage_service
from app.services.ai_service import ai_service
from app.services.questionnaire_service import questionnaire_service
from app.services.analytics_improved import chatbot_analytics

from app.config import settings

logger = logging.getLogger("hydrous-backend")

router = APIRouter()


@router.post("/start", response_model=ConversationResponse)
async def start_conversation(
    data: ConversationCreate = Body(default=ConversationCreate()),
):
    """Inicia una nueva conversación"""
    try:
        # Crear nueva conversación
        metadata = data.metadata if hasattr(data, "metadata") else {}
        conversation = await storage_service.create_conversation(metadata)

        # Registrar inicio de conversación en analíticas
        chatbot_analytics.log_conversation_start()

        # Añadir mensaje inicial del bot con el estilo mejorado
        welcome_message = Message.assistant(
            """
# 👋 ¡Bienvenido a Hydrous AI!

Soy el diseñador de soluciones de agua de Hydrous AI, su asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales. Como herramienta de Hydrous, estoy aquí para guiarlo paso a paso en la evaluación de las necesidades de agua de su sitio, la exploración de posibles soluciones y la identificación de oportunidades de ahorro de costos, cumplimiento y sostenibilidad.

Para desarrollar la mejor solución para sus instalaciones, haré sistemáticamente preguntas específicas para recopilar los datos necesarios y crear una propuesta personalizada. Mi objetivo es ayudarlo a optimizar la gestión del agua, reducir costos y explorar nuevas fuentes de ingresos con soluciones respaldadas por Hydrous.

💡 *Las soluciones de reciclaje de agua pueden reducir el consumo de agua fresca hasta en un 70% en instalaciones industriales similares.*

**PREGUNTA: ¿Cuál es el nombre de tu empresa o proyecto y dónde se ubica?**

Por favor incluye:
- Nombre de tu empresa o proyecto
- Ubicación (ciudad, estado, país)

🌍 *Esta información es importante para evaluar la normativa local, la disponibilidad de agua, y posibles incentivos para reciclaje de agua en tu zona.*
"""
        )
        conversation.add_message(welcome_message)

        # Iniciar el cuestionario
        conversation.start_questionnaire()

        return ConversationResponse(
            id=conversation.id,
            created_at=conversation.created_at,
            messages=[welcome_message],
        )
    except Exception as e:
        logger.error(f"Error al iniciar conversación: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al iniciar la conversación")


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str):
    """Obtiene una conversación existente por su ID"""
    conversation = await storage_service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    # Filtrar mensajes del sistema para la respuesta
    visible_messages = [msg for msg in conversation.messages if msg.role != "system"]

    return ConversationResponse(
        id=conversation.id,
        created_at=conversation.created_at,
        messages=visible_messages,
    )


@router.post("/message", response_model=MessageResponse)
async def send_message(data: MessageCreate, background_tasks: BackgroundTasks):
    """Procesa un mensaje del usuario y genera una respuesta"""
    try:
        # Validar que la conversación existe
        conversation = await storage_service.get_conversation(data.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Crear y añadir mensaje del usuario
        user_message = Message.user(data.message, data.metadata)
        await storage_service.add_message_to_conversation(
            data.conversation_id, user_message
        )

        # Detectar si es una solicitud para generar PDF
        if conversation.is_questionnaire_completed() and _is_pdf_request(data.message):
            # Generar y verificar propuesta
            proposal = questionnaire_service.generate_proposal(conversation)

            # Informar al usuario que puede descargar el PDF
            download_url = f"/api/chat/{conversation.id}/download-proposal-pdf"
            pdf_message = f"""
# 📄 Propuesta Lista para Descargar

He preparado tu propuesta personalizada basada en la información proporcionada. Puedes descargarla como PDF usando el siguiente enlace:

## [👉 DESCARGAR PROPUESTA EN PDF]({download_url})

Este documento incluye:
- Análisis de tus necesidades específicas
- Solución tecnológica recomendada
- Estimación de costos y retorno de inversión
- Pasos siguientes recomendados

¿Necesitas alguna aclaración sobre la propuesta o tienes alguna otra pregunta?
"""
            # añadir mensaje del asistente
            assistant_message = Message.assistant(pdf_message)
            await storage_service.add_message_to_conversation(
                data.conversation_id, assistant_message
            )

            # Generar el PDF en segundo plano
            background_tasks.add_task(
                questionnaire_service.generate_proposal_pdf, proposal
            )

            return MessageResponse(
                id=assistant_message.id,
                conversation_id=data.conversation_id,
                message=pdf_message,
                created_at=assistant_message.created_at,
            )

        # Usar el enfoque simplificado para generar la respuesta
        ai_response = await ai_service.handle_conversation(conversation, data.message)

        # Crear y añadir mensaje del asistente
        assistant_message = Message.assistant(ai_response)
        await storage_service.add_message_to_conversation(
            data.conversation_id, assistant_message
        )

        # Programar limpieza de conversaciones antiguas
        background_tasks.add_task(storage_service.cleanup_old_conversations)

        return MessageResponse(
            id=assistant_message.id,
            conversation_id=data.conversation_id,
            message=ai_response,
            created_at=assistant_message.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al procesar mensaje: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al procesar el mensaje")


@router.get("/{conversation_id}/download-proposal-pdf")
async def download_proposal_pdf(conversation_id: str, response: Response):
    """Descarga la propuesta en formato PDF"""
    try:
        # Obtener la conversación
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Verificar que el cuestionario está completo
        if not conversation.is_questionnaire_completed():
            raise HTTPException(
                status_code=400,
                detail="El cuestionario no está completo, no se puede generar la propuesta",
            )

        # Generar la propuesta y el PDF
        proposal = questionnaire_service.generate_proposal(conversation)
        file_path = questionnaire_service.generate_proposal_pdf(proposal)

        # Registrar descarga en analíticas
        chatbot_analytics.log_pdf_download(conversation_id)

        if not file_path or not os.path.exists(file_path):
            # Generar respuesta HTML simple en caso de error
            html_content = f"""
            <html>
                <head><title>Error al generar PDF</title></head>
                <body>
                    <h1>Error al generar documento</h1>
                    <p>No se pudo generar el documento de propuesta. Esto puede deberse a una de las siguientes razones:</p>
                    <ul>
                        <li>La información proporcionada está incompleta</li>
                        <li>Ocurrió un problema técnico durante la generación</li>
                        <li>El servicio de generación de PDF no está disponible actualmente</li>
                    </ul>
                    <p>Por favor intente nuevamente o contacte con soporte proporcionando el siguiente código:</p>
                    <p><strong>Referencia: {datetime.now().strftime('%Y%m%d%H%M%S')}</strong></p>
                    <a href="/chat/{conversation_id}">Volver a la conversación</a>
                </body>
            </html>
            """
            response.headers["Content-Type"] = "text/html"
            return Response(content=html_content, media_type="text/html")

        # Obtener el nombre del cliente para el nombre del archivo
        client_name = proposal["client_info"]["name"].replace(" ", "_")

        # Determinar tipo de archivo basado en la extensión
        is_pdf = file_path.lower().endswith(".pdf")
        if is_pdf:
            filename = f"Propuesta_Hydrous_{client_name}.pdf"
            media_type = "application/pdf"
        else:
            filename = f"Propuesta_Hydrous_{client_name}.html"
            media_type = "text/html"

        # Configurar headers para la descarga
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Devolver el archivo
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type=media_type,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al descargar propuesta: {str(e)}")

        # Página de error con instrucciones claras
        error_html = f"""
        <html>
            <head>
                <title>Error de Descarga - Hydrous</title>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; padding: 0; margin: 0; background: #f5f5f5; }}
                    .container {{ max-width: 800px; margin: 40px auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 15px rgba(0,0,0,0.1); }}
                    h1 {{ color: #2c3e50; margin-top: 0; }}
                    .error-code {{ background: #f8d7da; padding: 15px; border-radius: 5px; margin: 20px 0; color: #721c24; }}
                    .actions {{ margin-top: 30px; }}
                    .btn {{ display: inline-block; background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Error al generar el documento</h1>
                    <p>Ha ocurrido un problema técnico al procesar la propuesta. Disculpe las molestias.</p>
                    
                    <div class="error-code">
                        <p><strong>Código de referencia:</strong> {datetime.now().strftime('%Y%m%d%H%M%S')}</p>
                        <p><strong>Detalle técnico:</strong> {str(e)[:100]}...</p>
                    </div>
                    
                    <p>Este error ha sido registrado automáticamente. Por favor, intente las siguientes opciones:</p>
                    
                    <ul>
                        <li>Vuelva a la conversación y solicite nuevamente la descarga</li>
                        <li>Asegúrese de completar todas las preguntas del cuestionario</li>
                        <li>Contacte a nuestro equipo de soporte si el problema persiste</li>
                    </ul>
                    
                    <div class="actions">
                        <a href="/chat/{conversation_id}" class="btn">Volver a la conversación</a>
                    </div>
                </div>
            </body>
        </html>
        """
        return Response(content=error_html, media_type="text/html", status_code=500)


def _is_pdf_request(message: str) -> bool:
    """
    Determina si el mensaje del usuario es una solicitud de PDF
    """
    message = message.lower()
    pdf_keywords = [
        "pdf",
        "descargar",
        "propuesta",
        "documento",
        "guardar",
        "archivo",
        "exportar",
        "bajar",
        "obtener",
        "enviar",
        "quiero el pdf",
        "dame la propuesta",
        "ver el documento",
    ]

    return any(keyword in message for keyword in pdf_keywords)
