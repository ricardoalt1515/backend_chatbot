from fastapi import APIRouter, HTTPException, Depends, Body, BackgroundTasks, Response
from fastapi.responses import FileResponse
import logging
from typing import Dict, Any, List, Optional
import os
import time
import re
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
from app.config import settings

logger = logging.getLogger("hydrous-backend")

router = APIRouter()


def _is_pdf_request(message: str) -> bool:
    """
    Determina si el mensaje del usuario es una solicitud de PDF

    Args:
        message: Mensaje del usuario

    Returns:
        bool: True si es una solicitud de PDF
    """
    message = message.lower()

    # Palabras clave relacionadas con PDF
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
    ]

    # Frases comunes de solicitud
    pdf_phrases = [
        "quiero el pdf",
        "dame la propuesta",
        "ver el documento",
        "obtener el archivo",
        "descargar la propuesta",
        "enviame el pdf",
        "generar documento",
        "necesito la propuesta",
        "el enlace no funciona",
    ]

    # Verificar palabras clave simples
    if any(keyword in message for keyword in pdf_keywords):
        return True

    # Verificar frases comunes
    if any(phrase in message for phrase in pdf_phrases):
        return True

    return False


@router.post("/start", response_model=ConversationResponse)
async def start_conversation(
    data: ConversationCreate = Body(default=ConversationCreate()),
):
    """Inicia una nueva conversación"""
    try:
        # Crear nueva conversación - asegurarnos de que metadata existe y es un dict
        metadata = data.metadata if hasattr(data, "metadata") else {}
        conversation = await storage_service.create_conversation(metadata)

        # Añadir mensaje inicial del bot (bienvenida)
        welcome_message = Message.assistant(
            "¡Hola! Soy el asistente virtual de Hydrous especializado en soluciones de reciclaje de agua. "
            "¿En qué puedo ayudarte hoy? Puedes preguntarme sobre nuestros sistemas de filtración, "
            "tratamiento de aguas residuales, reutilización de agua y más. También puedo ayudarte "
            "a diseñar una solución personalizada para tu negocio completando un sencillo cuestionario."
        )
        conversation.add_message(welcome_message)

        return ConversationResponse(
            id=conversation.id,
            created_at=conversation.created_at,
            messages=[
                welcome_message
            ],  # Solo devolvemos mensajes visibles, no el prompt del sistema
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
        pdf_requested = _is_pdf_request(data.message)

        # Si se solicita PDF y el cuestionario está completo, generar PDF
        if pdf_requested and conversation.is_questionnaire_completed():
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

            # Generar el PDF en segundo plano para tenerlo listo cuando se solicite
            background_tasks.add_task(
                questionnaire_service.generate_proposal_pdf, proposal
            )

            return MessageResponse(
                id=assistant_message.id,
                conversation_id=data.conversation_id,
                message=pdf_message,
                created_at=assistant_message.created_at,
            )

        # Usar el servicio actualizado para manejar el flujo de conversación
        # incluyendo el cuestionario si está activo
        ai_response = await ai_service.handle_conversation(conversation, data.message)

        # Crear y añadir mensaje del asistente
        assistant_message = Message.assistant(ai_response)
        await storage_service.add_message_to_conversation(
            data.conversation_id, assistant_message
        )

        # Verificar nuevamente si es una solicitud para generar PDF después de la respuesta del modelo
        # Esto es útil por si el modelo detectó una intención implícita que nuestra función simple no captó
        if (
            (not pdf_requested)
            and _is_pdf_request(ai_response)
            and conversation.is_questionnaire_completed()
        ):
            # Generar y verificar la propuesta
            proposal = questionnaire_service.generate_proposal(conversation)

            # Generar PDF en segundo plano para tenerlo listo cuando se solicite
            background_tasks.add_task(
                questionnaire_service.generate_proposal_pdf, proposal
            )

        # Programar limpieza de conversaciones antiguas como tarea en segundo plano
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
    """Descarga la propuesta en formato PDF o HTML según disponibilidad"""
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

        # Generar la propuesta y el PDF/HTML
        proposal = questionnaire_service.generate_proposal(conversation)

        # intentar generar el PDF - aqui es donde fallaria si hay problema
        file_path = questionnaire_service.generate_proposal_pdf(proposal)

        if not file_path or not os.path.exists(file_path):
            # Si falla la generacion, generar una respuesta HTML simple
            html_content = f"""
            <html>
                <head>
                    <title>Propuesta Hydrous</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; padding: 30px; line-height: 1.6; }}
                        h1 {{ color: #2c3e50; }}
                        .container {{ max-width: 800px; margin: 0 auto; background: #f9f9f9; padding: 30px; border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                        .error {{ color: #e74c3c; }}
                        .btn {{ display: inline-block; background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>Error al generar documento</h1>
                        <p>No se pudo generar el documento de propuesta. Esto puede deberse a una de las siguientes razones:</p>
                        <ul>
                            <li>La información proporcionada está incompleta</li>
                            <li>Ocurrió un problema técnico durante la generación</li>
                            <li>El servicio de generación de PDF no está disponible actualmente</li>
                        </ul>
                        <p>Por favor intente nuevamente o contacte con soporte proporcionando el siguiente código:</p>
                        <p class="error"><strong>Referencia: {datetime.datetime.now().strftime('%Y%m%d%H%M%S')}</strong></p>
                        <a href="/chat/{conversation_id}" class="btn">Volver a la conversación</a>
                    </div>
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

        # Mejorar manejo de la descarga
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Registrar éxito
        logger.info(f"Descarga exitosa: {filename} para conversación {conversation_id}")

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

        # Pagina de error con instrucciones claras
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
                        <p><strong>Código de referencia:</strong> {datetime.datetime.now().strftime('%Y%m%d%H%M%S')}</p>
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


@router.get("/{conversation_id}/questionnaire/status")
async def get_questionnaire_status(conversation_id: str):
    """Obtiene el estado actual del cuestionario para una conversación"""
    try:
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        return {
            "active": conversation.is_questionnaire_active(),
            "completed": conversation.is_questionnaire_completed(),
            "sector": conversation.questionnaire_state.sector,
            "subsector": conversation.questionnaire_state.subsector,
            "current_question": conversation.questionnaire_state.current_question_id,
            "answers_count": len(conversation.questionnaire_state.answers),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener estado del cuestionario: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error al obtener estado del cuestionario"
        )


@router.post("/{conversation_id}/questionnaire/start")
async def start_questionnaire(conversation_id: str):
    """Inicia manualmente el proceso de cuestionario"""
    try:
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Verificar si ya está activo
        if conversation.is_questionnaire_active():
            return {"message": "El cuestionario ya está activo"}

        # Iniciar cuestionario
        conversation.start_questionnaire()

        # Obtener introducción y primera pregunta
        intro_text, explanation = questionnaire_service.get_introduction()
        next_question = questionnaire_service.get_next_question(
            conversation.questionnaire_state
        )

        # Crear mensaje con la introducción y primera pregunta
        message_text = f"{intro_text}\n\n{explanation}\n\n"
        if next_question:
            message_text += ai_service._format_question(next_question)
            conversation.questionnaire_state.current_question_id = next_question["id"]

        # Añadir mensaje del asistente
        assistant_message = Message.assistant(message_text)
        await storage_service.add_message_to_conversation(
            conversation_id, assistant_message
        )

        return {
            "message": "Cuestionario iniciado correctamente",
            "first_question": message_text,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al iniciar cuestionario: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al iniciar cuestionario")


@router.post("/{conversation_id}/questionnaire/answer")
async def answer_questionnaire(conversation_id: str, data: Dict[str, Any] = Body(...)):
    """Procesa una respuesta del cuestionario y devuelve la siguiente pregunta"""
    try:
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Verificar si el cuestionario está activo
        if not conversation.is_questionnaire_active():
            raise HTTPException(
                status_code=400, detail="El cuestionario no está activo"
            )

        # Verificar que se recibió una respuesta
        if "answer" not in data:
            raise HTTPException(
                status_code=400, detail="No se ha proporcionado una respuesta"
            )

        # Verificar que hay una pregunta actual
        if not conversation.questionnaire_state.current_question_id:
            raise HTTPException(status_code=400, detail="No hay una pregunta actual")

        # Procesar la respuesta
        question_id = conversation.questionnaire_state.current_question_id
        answer = data["answer"]
        questionnaire_service.process_answer(conversation, question_id, answer)

        # Obtener siguiente pregunta
        next_question = questionnaire_service.get_next_question(
            conversation.questionnaire_state
        )

        if not next_question:
            # Si no hay siguiente pregunta, generar propuesta
            if not conversation.is_questionnaire_completed():
                conversation.complete_questionnaire()

            # Generar y formatear propuesta
            proposal = questionnaire_service.generate_proposal(conversation)
            summary = questionnaire_service.format_proposal_summary(
                proposal, conversation.id
            )

            # Añadir mensaje con la propuesta
            assistant_message = Message.assistant(summary)
            await storage_service.add_message_to_conversation(
                conversation_id, assistant_message
            )

            return {"completed": True, "message": summary}

        # Actualizar la pregunta actual
        conversation.questionnaire_state.current_question_id = next_question["id"]

        # Formatear la siguiente pregunta
        next_question_formatted = ai_service._format_question(next_question)

        # Añadir mensaje con la siguiente pregunta
        assistant_message = Message.assistant(next_question_formatted)
        await storage_service.add_message_to_conversation(
            conversation_id, assistant_message
        )

        return {
            "completed": False,
            "next_question": next_question,
            "message": next_question_formatted,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al procesar respuesta del cuestionario: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error al procesar respuesta del cuestionario"
        )


@router.get("/{conversation_id}/proposal")
async def generate_proposal(conversation_id: str):
    """Genera una propuesta basada en las respuestas del cuestionario"""
    try:
        # Obtener la conversación
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Verificar si hay suficientes respuestas
        if len(conversation.questionnaire_state.answers) < 3:
            raise HTTPException(
                status_code=400,
                detail="No hay suficiente información para generar una propuesta",
            )

        # Generar propuesta
        proposal = questionnaire_service.generate_proposal(conversation)

        # Por ahora devolvemos los datos JSON, pero en el futuro podría generarse un PDF
        return proposal
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al generar propuesta: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al generar la propuesta")
