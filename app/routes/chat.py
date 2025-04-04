# app/routes/chat.py
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse, Response  # Añadir Response
import logging
import os
from typing import Any

from app.models.conversation import (
    ConversationResponse,
    Conversation,
    Message,
    MessageCreate,
)
from app.models.conversation_state import ConversationState
from app.services.storage_service import storage_service
from app.services.ai_service import ai_service  # Usará nuevos métodos
from app.services.pdf_service import pdf_service  # Necesitará ajustes
from app.services.questionnaire_service import (
    questionnaire_service,
)  # Servicio principal de flujo
from app.config import settings

router = APIRouter()
logger = logging.getLogger("hydrous")


@router.post("/start", response_model=ConversationResponse)
async def start_conversation():
    """Inicia una nueva conversación y hace la primera pregunta."""
    try:
        # 1. Crear conversación con estado inicial
        initial_state = ConversationState()
        conversation = await storage_service.create_conversation(
            initial_state=initial_state
        )
        logger.info(f"Nueva conversación iniciada con ID: {conversation.id}")

        # 2. Obtener la primera pregunta
        first_question_id = questionnaire_service.get_initial_question_id()
        if not first_question_id:
            logger.error(
                "Configuración inválida: No se pudo obtener la primera pregunta."
            )
            raise HTTPException(
                status_code=500, detail="Error interno del servidor [QS01]"
            )

        question_details = questionnaire_service.get_question(first_question_id)
        if not question_details:
            logger.error(
                f"Configuración inválida: Detalles no encontrados para la primera pregunta ID: {first_question_id}"
            )
            raise HTTPException(
                status_code=500, detail="Error interno del servidor [QS02]"
            )

        # 3. Actualizar estado con la primera pregunta
        conversation.state.current_question_id = first_question_id
        # No es necesario guardar aquí si `create_conversation` ya lo hizo.
        # Si `create` no guarda, descomentar: await storage_service.save_conversation(conversation)

        # 4. Formatear mensaje de bienvenida + primera pregunta
        welcome_text = questionnaire_service.get_initial_greeting()
        formatted_question = questionnaire_service.format_question_for_display(
            question_details
        )
        initial_message_content = f"{welcome_text}\n\n{formatted_question}"
        initial_message = Message.assistant(initial_message_content)

        # 5. Añadir mensaje a la conversación y GUARDAR (importante si no se hizo antes)
        await storage_service.add_message_to_conversation(
            conversation.id, initial_message
        )
        await storage_service.save_conversation(
            conversation
        )  # Asegurar que el estado inicializado se guarde

        # 6. Devolver respuesta
        return ConversationResponse(
            id=conversation.id,
            created_at=conversation.created_at,
            messages=[initial_message],  # Devolver solo el mensaje de bienvenida/inicio
            state=conversation.state,
            metadata=conversation.metadata,
        )
    except Exception as e:
        logger.error(f"Error crítico al iniciar conversación: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="No se pudo iniciar la conversación."
        )


@router.post("/message", response_model=Message)  # Devolver el objeto Message Pydantic
async def send_message(data: MessageCreate, background_tasks: BackgroundTasks):
    """Procesa un mensaje del usuario, avanza en el cuestionario y genera una respuesta."""
    conversation_id = data.conversation_id
    user_input = data.message

    try:
        # 1. Cargar Conversación y Estado
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            logger.error(f"Conversación no encontrada: {conversation_id}")
            raise HTTPException(
                status_code=404,
                detail="Conversación no encontrada. Por favor, inicia una nueva.",
            )
        if not conversation.state or not isinstance(
            conversation.state, ConversationState
        ):
            logger.error(
                f"Estado inválido o faltante para conversación: {conversation_id}"
            )
            # Podríamos intentar reiniciar, pero es mejor lanzar error claro.
            raise HTTPException(
                status_code=500,
                detail="Error interno: Estado de la conversación corrupto [CS01]",
            )

        # 2. Añadir mensaje del usuario (solo si no es petición de PDF después de completar)
        # Si la propuesta ya está lista Y es petición de PDF, no añadimos la petición como mensaje
        is_pdf_req = _is_pdf_request(user_input)
        proposal_ready = conversation.metadata.get("has_proposal", False)

        if not (is_pdf_req and proposal_ready):
            user_message_obj = Message.user(user_input)
            await storage_service.add_message_to_conversation(
                conversation.id, user_message_obj
            )
        else:
            logger.info(
                f"Petición de PDF detectada para {conversation_id} con propuesta lista. No se añade mensaje 'PDF'."
            )

        # 3. Manejar Solicitud de PDF (si aplica Y la propuesta está lista)
        if is_pdf_req and proposal_ready:
            logger.info(
                f"Procesando solicitud de PDF para conversación {conversation_id}"
            )

            # Generar mensaje indicando cómo descargar (no genera el PDF aquí)
            pdf_info_message_content = f"""
📄 Tu propuesta personalizada está lista.

Puedes descargarla usando el siguiente enlace:
[👉 DESCARGAR PROPUESTA EN PDF]({settings.API_V1_STR}/chat/{conversation.id}/download-pdf)

Si tienes algún problema con la descarga o alguna pregunta sobre la propuesta, házmelo saber.
"""
            pdf_info_message = Message.assistant(pdf_info_message_content)
            await storage_service.add_message_to_conversation(
                conversation.id, pdf_info_message
            )
            # No es necesario guardar la conversación aquí, solo se añadió un mensaje informativo
            return pdf_info_message  # Devolver este mensaje informativo

        # --- Lógica Principal del Cuestionario (si no fue petición de PDF) ---

        # 4. Procesar Respuesta Anterior (si había una pregunta pendiente)
        last_question_id = conversation.state.current_question_id
        educational_insight = ""
        if last_question_id and not conversation.state.is_complete:
            processed_answer = questionnaire_service.process_answer(
                last_question_id, user_input
            )
            conversation.state.update_collected_data(last_question_id, processed_answer)
            logger.info(
                f"Respuesta a {last_question_id} procesada: '{processed_answer}' para conv {conversation_id}"
            )

            # Generar insight educativo sobre la respuesta dada
            try:
                insight = await ai_service.generate_educational_insight(
                    conversation, user_input
                )
                if insight:
                    educational_insight = insight + "\n\n---\n\n"  # Añadir separador
            except Exception as e:
                logger.warning(
                    f"No se pudo generar insight educativo para {conversation_id}: {e}"
                )

        # 5. Determinar Siguiente Pregunta o Finalización
        next_question_id = questionnaire_service.get_next_question_id(
            conversation.state
        )

        if next_question_id:
            # 5.a. Hay más preguntas
            conversation.state.current_question_id = next_question_id
            next_question_details = questionnaire_service.get_question(next_question_id)
            if not next_question_details:
                logger.error(
                    f"Configuración inválida: No se encontraron detalles para la siguiente pregunta ID: {next_question_id}"
                )
                raise HTTPException(
                    status_code=500, detail="Error interno del servidor [QS03]"
                )

            # Formatear siguiente pregunta
            next_question_text = questionnaire_service.format_question_for_display(
                next_question_details
            )
            response_content = f"{educational_insight}{next_question_text}"
            assistant_message = Message.assistant(response_content)
            logger.debug(
                f"Siguiente pregunta para {conversation_id}: {next_question_id}"
            )

        else:
            # 5.b. Cuestionario Completo -> Generar Propuesta (si no se ha generado ya)
            if not proposal_ready:
                logger.info(
                    f"Cuestionario completado para {conversation_id}. Generando texto de propuesta."
                )
                conversation.metadata["has_proposal"] = True
                conversation.state.current_question_id = (
                    None  # Ya no hay pregunta activa
                )
                conversation.state.is_complete = True  # Marcar como completo

                try:
                    # Generar el texto y guardarlo en metadatos
                    proposal_text = await ai_service.generate_proposal_text(
                        conversation
                    )
                    conversation.metadata["proposal_text"] = proposal_text
                    # Extraer nombre cliente del estado si existe, para el nombre del archivo PDF
                    client_name = conversation.state.key_entities.get(
                        "company_name", "Cliente"
                    )
                    conversation.metadata["client_name"] = client_name

                    logger.info(
                        f"Texto de propuesta generado y guardado en metadata para {conversation_id}"
                    )

                    response_content = f"{educational_insight}✅ ¡Excelente! Hemos recopilado toda la información necesaria.\n\nHe generado una propuesta preliminar basada en tus respuestas.\n\n**Escribe 'descargar propuesta' o 'PDF' para obtener el documento.**"
                    assistant_message = Message.assistant(response_content)

                except Exception as e:
                    logger.error(
                        f"Error crítico generando texto de propuesta para {conversation_id}: {e}",
                        exc_info=True,
                    )
                    conversation.metadata["has_proposal"] = False  # Marcar que falló
                    conversation.metadata["proposal_error"] = str(e)
                    assistant_message = Message.assistant(
                        f"{educational_insight}Lo siento, tuve un problema al generar el resumen final de la propuesta. Por favor, contacta a soporte o intenta responder la última pregunta de nuevo."
                    )

            else:
                # El cuestionario ya estaba completo y la propuesta lista (usuario envió otro mensaje?)
                logger.info(
                    f"Conversación {conversation_id} ya completada. Recordando cómo descargar PDF."
                )
                assistant_message = Message.assistant(
                    f"{educational_insight}Ya hemos completado la recopilación de datos. Puedes escribir 'descargar propuesta' o 'PDF' para obtener tu documento."
                )

        # 6. Guardar Estado y Mensaje del Asistente
        # Guardar siempre la conversación al final para persistir cambios en estado y metadata
        await storage_service.save_conversation(conversation)
        await storage_service.add_message_to_conversation(
            conversation.id, assistant_message
        )

        # 7. Limpieza en segundo plano
        background_tasks.add_task(storage_service.cleanup_old_conversations)

        # 8. Devolver respuesta (el objeto Pydantic Message)
        return assistant_message

    except HTTPException as http_exc:
        logger.warning(
            f"HTTPException en send_message para {conversation_id}: {http_exc.status_code} - {http_exc.detail}"
        )
        raise http_exc  # Re-lanzar para que FastAPI la maneje
    except Exception as e:
        logger.error(
            f"Error fatal no controlado en send_message para {conversation_id}: {str(e)}",
            exc_info=True,
        )
        # Devolver un error genérico como mensaje del asistente
        error_msg = Message.assistant(
            "Lo siento, ha ocurrido un error inesperado. Por favor, intenta de nuevo en unos momentos."
        )
        # Intentar guardar el mensaje de error en la conversación si existe
        try:
            if "conversation" in locals() and conversation:
                await storage_service.add_message_to_conversation(
                    conversation.id, error_msg
                )
                # Podríamos guardar un flag de error en metadata también
                conversation.metadata["last_error"] = str(e)
                await storage_service.save_conversation(conversation)
        except Exception as save_err:
            logger.error(
                f"Error adicional al intentar guardar mensaje de error para {conversation_id}: {save_err}"
            )

        # Devolver el mensaje de error al usuario (status 200 pero con contenido de error)
        # Para indicar un error real al frontend, sería mejor devolver un status 500 aquí
        # raise HTTPException(status_code=500, detail="Error interno del servidor [MSG01]")
        # Pero devolver el mensaje permite que el chat no se rompa visualmente
        return error_msg


@router.get("/{conversation_id}/download-pdf")
async def download_pdf(conversation_id: str):
    """Genera (si es necesario) y devuelve la propuesta en formato PDF."""
    try:
        # 1. Cargar conversación
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")
        if not conversation.metadata.get("has_proposal", False):
            raise HTTPException(
                status_code=400,
                detail="La propuesta para esta conversación aún no está lista.",
            )

        # 2. Verificar si el PDF ya existe
        pdf_path = conversation.metadata.get("pdf_path")
        if pdf_path and os.path.exists(pdf_path):
            logger.info(f"PDF encontrado en caché para {conversation_id}: {pdf_path}")
        else:
            # 3. Generar PDF si no existe
            logger.info(f"Generando PDF bajo demanda para {conversation_id}...")
            proposal_text = conversation.metadata.get("proposal_text")
            if not proposal_text:
                logger.error(
                    f"No se encontró texto de propuesta en metadata para generar PDF. ID: {conversation_id}"
                )
                raise HTTPException(
                    status_code=500,
                    detail="Error interno: Falta contenido de la propuesta [PDF01]",
                )

            try:
                # Llamar a pdf_service para generar desde el texto
                pdf_path = await pdf_service.generate_pdf_from_text(
                    conversation_id, proposal_text
                )
                if not pdf_path or not os.path.exists(pdf_path):
                    raise ValueError(
                        "La generación de PDF falló o no devolvió una ruta válida."
                    )

                # Guardar la ruta en metadatos para futuras descargas
                conversation.metadata["pdf_path"] = pdf_path
                await storage_service.save_conversation(conversation)
                logger.info(
                    f"PDF generado y guardado en {pdf_path} para {conversation_id}"
                )

            except Exception as e:
                logger.error(
                    f"Error crítico generando PDF para {conversation_id}: {e}",
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=500,
                    detail="No se pudo generar el archivo PDF de la propuesta [PDF02]",
                )

        # 4. Preparar y devolver el archivo
        client_name = conversation.metadata.get("client_name", "Cliente")
        filename = f"Propuesta_Hydrous_{client_name}_{conversation_id[:8]}.pdf"

        return FileResponse(
            path=pdf_path,
            filename=filename,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(
            f"Error fatal al procesar descarga de PDF para {conversation_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Error interno al procesar la descarga del archivo [PDF03]",
        )


def _is_pdf_request(message: str) -> bool:
    """Determina si el mensaje es una solicitud de PDF de forma más robusta."""
    if not message:
        return False
    message = message.lower().strip()
    # Palabras clave fuertes que indican intención de descarga
    strong_keywords = [
        "pdf",
        "descargar",
        "propuesta",
        "documento",
        "bajar",
        "archivo final",
    ]
    # Evitar falsos positivos comunes
    negative_keywords = ["no quiero", "todavía no", "pregunta", "duda"]

    has_strong_keyword = any(keyword in message for keyword in strong_keywords)
    has_negative_keyword = any(keyword in message for keyword in negative_keywords)

    # Requiere una palabra clave fuerte y ninguna negativa
    return has_strong_keyword and not has_negative_keyword
