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

        # Verificar si es el inicio de la conversación o se detecta intención de cuestionario
        if (
            not conversation.is_questionnaire_active()
            and not conversation.is_questionnaire_completed()
        ):

            # Detectar si el usuario quiere iniciar el cuestionario o es el primer mensaje
            should_start = ai_service._detect_questionnaire_intent(data.message)
            is_initial_message = (
                len([m for m in conversation.messages if m.role == "user"]) <= 1
            )

            if should_start or is_initial_message:
                # Iniciar cuestionario
                conversation.start_questionnaire()

                # Mostrar saludo inicial según estructura específica
                initial_greeting = """
Soy el diseñador de soluciones de agua de Hydrous AI, su asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales. Como herramienta de Hydrous, estoy aquí para guiarlo paso a paso en la evaluación de las necesidades de agua de su sitio, la exploración de posibles soluciones y la identificación de oportunidades de ahorro de costos, cumplimiento y sostenibilidad.

Para desarrollar la mejor solución para sus instalaciones, haré sistemáticamente preguntas específicas para recopilar los datos necesarios y crear una propuesta personalizada. Mi objetivo es ayudarlo a optimizar la gestión del agua, reducir costos y explorar nuevas fuentes de ingresos con soluciones respaldadas por Hydrous.

*Las soluciones de reciclaje de agua pueden reducir el consumo de agua fresca hasta en un 70% en instalaciones industriales similares.*

El tratamiento adecuado del agua no solo es beneficioso para el medio ambiente, sino que puede representar un ahorro significativo en costos operativos a mediano y largo plazo.

**PREGUNTA: ¿En qué sector opera su empresa?**
1. Industrial
2. Comercial
3. Municipal
4. Residencial
"""

                # Añadir mensaje del asistente
                assistant_message = Message.assistant(initial_greeting)
                await storage_service.add_message_to_conversation(
                    data.conversation_id, assistant_message
                )

                # Configurar estado del cuestionario para sector
                conversation.questionnaire_state.current_question_id = (
                    "sector_selection"
                )

                return MessageResponse(
                    id=assistant_message.id,
                    conversation_id=data.conversation_id,
                    message=initial_greeting,
                    created_at=assistant_message.created_at,
                )

        # Si el cuestionario está activo, procesamos según el flujo estructurado
        if conversation.is_questionnaire_active():
            # CASO 1: Procesar respuesta al sector si es la pregunta actual
            if (
                conversation.questionnaire_state.current_question_id
                == "sector_selection"
            ):
                # Intentar extraer sector de la respuesta
                sector = None
                message_lower = data.message.lower().strip()

                # Verificar si es respuesta numérica (1-4)
                if message_lower in ["1", "2", "3", "4"]:
                    sectors = ["Industrial", "Comercial", "Municipal", "Residencial"]
                    sector = sectors[int(message_lower) - 1]
                # O buscar mención textual del sector
                else:
                    for possible_sector in [
                        "industrial",
                        "comercial",
                        "municipal",
                        "residencial",
                    ]:
                        if possible_sector in message_lower:
                            sector = possible_sector.capitalize()
                            break

                if sector:
                    # Actualizar estado con sector seleccionado
                    conversation.questionnaire_state.sector = sector
                    conversation.questionnaire_state.answers["sector_selection"] = (
                        sector
                    )

                    # Preparar pregunta de subsector
                    subsector_options = questionnaire_service.get_subsectors(sector)
                    interesting_fact = questionnaire_service.get_random_fact(
                        sector
                    ) or (
                        "Las soluciones de reciclaje pueden reducir costos operativos significativamente."
                    )

                    subsector_response = f"""
Gracias por indicar su sector. Esta información es fundamental para adaptar nuestra solución a sus necesidades específicas.

*{interesting_fact}*

Cada subsector tiene características y necesidades específicas para el tratamiento de agua.

**PREGUNTA: ¿Cuál es el subsector específico dentro de {sector}?**
{chr(10).join([f"{i+1}. {option}" for i, option in enumerate(subsector_options)])}
"""
                    # Actualizar la pregunta actual
                    conversation.questionnaire_state.current_question_id = (
                        "subsector_selection"
                    )

                    # Crear y añadir mensaje del asistente
                    assistant_message = Message.assistant(subsector_response)
                    await storage_service.add_message_to_conversation(
                        data.conversation_id, assistant_message
                    )

                    return MessageResponse(
                        id=assistant_message.id,
                        conversation_id=data.conversation_id,
                        message=subsector_response,
                        created_at=assistant_message.created_at,
                    )

            # CASO 2: Procesar respuesta al subsector si es la pregunta actual
            elif (
                conversation.questionnaire_state.current_question_id
                == "subsector_selection"
            ):
                # Extraer subsector de la respuesta
                subsector = None
                message_lower = data.message.lower().strip()
                sector = conversation.questionnaire_state.sector
                subsector_options = questionnaire_service.get_subsectors(sector)

                # Verificar si es respuesta numérica
                if message_lower.isdigit():
                    index = int(message_lower) - 1
                    if 0 <= index < len(subsector_options):
                        subsector = subsector_options[index]
                # O buscar mención textual del subsector
                else:
                    for option in subsector_options:
                        if option.lower() in message_lower:
                            subsector = option
                            break

                if subsector:
                    # Actualizar estado con subsector seleccionado
                    conversation.questionnaire_state.subsector = subsector
                    conversation.questionnaire_state.answers["subsector_selection"] = (
                        subsector
                    )

                    # Obtener la primera pregunta del cuestionario específico
                    next_question = questionnaire_service.get_next_question(
                        conversation.questionnaire_state
                    )

                    if next_question:
                        # Preparar respuesta con estructura correcta
                        interesting_fact = questionnaire_service.get_random_fact(
                            sector, subsector
                        )
                        previous_comment = f"Excelente. El subsector {subsector} dentro del sector {sector} presenta desafíos y oportunidades particulares en el tratamiento de agua."

                        question_response = f"""
{previous_comment}

*{interesting_fact}*

{next_question.get('explanation', 'Esta información nos ayudará a personalizar nuestra solución.')}

**PREGUNTA: {next_question.get('text', '')}**
"""
                        # Añadir opciones numeradas si es una pregunta de selección múltiple
                        if (
                            next_question.get("type")
                            in ["multiple_choice", "multiple_select"]
                            and "options" in next_question
                        ):
                            for i, option in enumerate(next_question["options"], 1):
                                question_response += f"{i}. {option}\n"

                        # Actualizar la pregunta actual
                        conversation.questionnaire_state.current_question_id = (
                            next_question.get("id", "")
                        )

                        # Verificar si debemos sugerir subir documentos para esta pregunta
                        if ai_service.should_suggest_document(
                            next_question.get("id", "")
                        ):
                            document_suggestion = (
                                questionnaire_service.suggest_document_upload(
                                    next_question.get("id", "")
                                )
                            )
                            question_response += f"\n\n{document_suggestion}"

                        # Crear y añadir mensaje del asistente
                        assistant_message = Message.assistant(question_response)
                        await storage_service.add_message_to_conversation(
                            data.conversation_id, assistant_message
                        )

                        return MessageResponse(
                            id=assistant_message.id,
                            conversation_id=data.conversation_id,
                            message=question_response,
                            created_at=assistant_message.created_at,
                        )

            # CASO 3: Procesamiento de preguntas del cuestionario específico
            elif conversation.questionnaire_state.current_question_id:
                # Guardar respuesta a pregunta actual
                current_question_id = (
                    conversation.questionnaire_state.current_question_id
                )
                conversation.questionnaire_state.answers[current_question_id] = (
                    data.message
                )

                # Incrementar contador de preguntas respondidas
                if hasattr(conversation.questionnaire_state, "questions_answered"):
                    conversation.questionnaire_state.questions_answered += 1

                # Verificar si es momento de mostrar un resumen intermedio
                show_summary = False
                questions_answered = len(conversation.questionnaire_state.answers)
                if questions_answered > 0 and questions_answered % 5 == 0:
                    # Verificar que no hayamos mostrado resumen para esta cantidad de respuestas
                    if (
                        not hasattr(conversation.questionnaire_state, "last_summary_at")
                        or conversation.questionnaire_state.last_summary_at
                        != questions_answered
                    ):
                        show_summary = True
                        # Actualizar cuando mostramos el último resumen
                        if not hasattr(
                            conversation.questionnaire_state, "last_summary_at"
                        ):
                            conversation.questionnaire_state.last_summary_at = 0
                        conversation.questionnaire_state.last_summary_at = (
                            questions_answered
                        )

                if show_summary:
                    # Generar resumen intermedio
                    summary = questionnaire_service.generate_interim_summary(
                        conversation
                    )

                    # Crear y añadir mensaje del asistente con el resumen
                    assistant_message = Message.assistant(summary)
                    await storage_service.add_message_to_conversation(
                        data.conversation_id, assistant_message
                    )

                    return MessageResponse(
                        id=assistant_message.id,
                        conversation_id=data.conversation_id,
                        message=summary,
                        created_at=assistant_message.created_at,
                    )

                # Obtener la siguiente pregunta
                next_question = questionnaire_service.get_next_question(
                    conversation.questionnaire_state
                )

                # Si no hay más preguntas, completar cuestionario
                if not next_question:
                    # Marcar cuestionario como completado
                    conversation.complete_questionnaire()

                    # Generar diagnóstico preliminar
                    diagnosis = questionnaire_service.generate_preliminary_diagnosis(
                        conversation
                    )

                    # Crear y añadir mensaje del asistente con el diagnóstico
                    assistant_message = Message.assistant(diagnosis)
                    await storage_service.add_message_to_conversation(
                        data.conversation_id, assistant_message
                    )

                    return MessageResponse(
                        id=assistant_message.id,
                        conversation_id=data.conversation_id,
                        message=diagnosis,
                        created_at=assistant_message.created_at,
                    )

                # Preparar siguiente pregunta con estructura correcta
                previous_comment = ai_service._generate_previous_answer_comment(
                    conversation, data.message
                )
                interesting_fact = questionnaire_service.get_random_fact(
                    conversation.questionnaire_state.sector,
                    conversation.questionnaire_state.subsector,
                )

                question_response = f"""
{previous_comment}

*{interesting_fact}*

{next_question.get('explanation', 'Esta información nos ayudará a personalizar nuestra solución.')}

**PREGUNTA: {next_question.get('text', '')}**
"""
                # Añadir opciones numeradas si es pregunta de selección múltiple
                if (
                    next_question.get("type") in ["multiple_choice", "multiple_select"]
                    and "options" in next_question
                ):
                    for i, option in enumerate(next_question["options"], 1):
                        question_response += f"{i}. {option}\n"

                # Actualizar la pregunta actual
                conversation.questionnaire_state.current_question_id = (
                    next_question.get("id", "")
                )

                # Verificar si debemos sugerir subir documentos para esta pregunta
                if ai_service.should_suggest_document(next_question.get("id", "")):
                    document_suggestion = questionnaire_service.suggest_document_upload(
                        next_question.get("id", "")
                    )
                    question_response += f"\n\n{document_suggestion}"

                # Crear y añadir mensaje del asistente
                assistant_message = Message.assistant(question_response)
                await storage_service.add_message_to_conversation(
                    data.conversation_id, assistant_message
                )

                return MessageResponse(
                    id=assistant_message.id,
                    conversation_id=data.conversation_id,
                    message=question_response,
                    created_at=assistant_message.created_at,
                )

        # Si el cuestionario ya está completo y el usuario no está solicitando el PDF,
        # responder a preguntas sobre la propuesta
        if conversation.is_questionnaire_completed():
            # Usar el servicio de IA para generar una respuesta contextual
            ai_response = await ai_service.handle_conversation(
                conversation, data.message
            )

            # Verificar si la respuesta contiene una solicitud implícita de PDF
            if _is_pdf_request(ai_response):
                # Generar enlace para descargar PDF y mensaje informativo
                download_url = f"/api/chat/{conversation.id}/download-proposal-pdf"
                ai_response = f"""
# 📄 Propuesta Lista para Descargar

He preparado su propuesta personalizada basada en la información proporcionada. Puede descargarla como PDF usando el siguiente enlace:

## [👉 DESCARGAR PROPUESTA EN PDF]({download_url})

Este documento incluye:
- Análisis de sus necesidades específicas
- Solución tecnológica recomendada
- Estimación de costos y retorno de inversión
- Pasos siguientes recomendados

¿Necesita alguna aclaración sobre la propuesta o tiene alguna otra pregunta?
"""
                # Generar el PDF en segundo plano
                proposal = questionnaire_service.generate_proposal(conversation)
                background_tasks.add_task(
                    questionnaire_service.generate_proposal_pdf, proposal
                )

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

        # Si llegamos aquí, usamos el servicio de IA para manejar la conversación
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
