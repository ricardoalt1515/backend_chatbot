# app/routes/chat.py
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import logging
import os
from datetime import datetime  # Asegurarse que datetime está importado
from typing import Any

# Modelos
from app.models.conversation import ConversationResponse, Conversation
from app.models.message import Message, MessageCreate

# Servicios
from app.services.storage_service import storage_service
from app.services.ai_service import ai_service  # Usar la instancia LLM-Driven
from app.services.pdf_service import pdf_service

# Ya no necesitamos QuestionnaireService aquí directamente
# from app.services.questionnaire_service import questionnaire_service
from app.config import settings

router = APIRouter()
logger = logging.getLogger("hydrous")


@router.post("/start", response_model=ConversationResponse)
async def start_conversation():
    """Inicia una nueva conversación (solo crea el registro)."""
    try:
        # 1. Crear conversación vacía (metadata por defecto)
        conversation = await storage_service.create_conversation()
        logger.info(f"Nueva conversación LLM-Driven iniciada con ID: {conversation.id}")

        # 2. Devolver ID y metadata inicial. El primer mensaje real lo enviará la IA.
        return ConversationResponse(
            id=conversation.id,
            created_at=conversation.created_at,
            messages=[],  # Sin mensajes iniciales del backend
            metadata=conversation.metadata,
        )
    except Exception as e:
        logger.error(
            f"Error crítico al iniciar conversación LLM-Driven: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail="No se pudo iniciar la conversación."
        )


@router.post("/message")  # Quitar response_model
async def send_message(data: MessageCreate, background_tasks: BackgroundTasks):
    """Recibe mensaje del usuario, lo añade, obtiene respuesta del AI Service y devuelve."""
    conversation_id = data.conversation_id
    user_input = data.message

    try:
        # 1. Cargar Conversación
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            logger.error(f"Conversación no encontrada: {conversation_id}")
            return {
                "id": "error-conv-not-found",
                "message": "Error: Conversación no encontrada. Por favor, reinicia.",
                "conversation_id": conversation_id,
                "created_at": datetime.utcnow(),
            }
        if not isinstance(conversation.metadata, dict):
            logger.error(f"Metadata inválida para conversación: {conversation_id}")
            return {
                "id": "error-metadata",
                "message": "Error interno: Estado de conversación corrupto [MD01].",
                "conversation_id": conversation_id,
                "created_at": datetime.utcnow(),
            }

        # 2. Añadir mensaje del usuario a la conversación
        user_message_obj = Message.user(user_input)
        # conversation.add_message(user_message_obj) # NO añadir aún, pasamos el input a handle
        # Actualizar el historial en memoria, pero sin guardar permanentemente todavía
        conversation.messages.append(user_message_obj)

        # --- Lógica de Procesamiento ---
        # 3. Llamar al AI Service para obtener la siguiente respuesta
        #    Este servicio ahora maneja la lógica de prompt/LLM/estado
        logger.info(f"Llamando a ai_service.handle_conversation para {conversation_id}")
        ai_response_content = await ai_service.handle_conversation(conversation)
        # handle_conversation ya actualizó metadata necesaria (como current_question_asked_summary)

        # 4. Crear y añadir mensaje del asistente al historial en memoria
        assistant_message = Message.assistant(ai_response_content)
        conversation.messages.append(assistant_message)  # Añadir ahora sí

        # --- Actualizar metadata Sector/Subsector (MÁS FIABLE HACERLO AQUÍ) ---
        # Si la última pregunta fue INIT_1 o INIT_2, actualizar metadata basado en user_input
        last_q_summary = conversation.metadata.get("current_question_asked_summary", "")
        if "sector principal opera" in last_q_summary:  # Identifica pregunta INIT_1
            processed_answer = user_input.strip()
            q_details = questionnaire_service.get_question_details(
                "INIT_1"
            )  # Usar servicio simplificado
            options = q_details.get("options", []) if q_details else []
            sector = None
            if processed_answer.isdigit():
                try:
                    idx = int(processed_answer) - 1
                    if 0 <= idx < len(options):
                        sector = options[idx]
                except ValueError:
                    pass
            elif processed_answer in options:
                sector = processed_answer
            if sector:
                conversation.metadata["selected_sector"] = sector
                logger.info(
                    f"Metadata[selected_sector] actualizada a '{sector}' en chat.py"
                )
            else:
                logger.warning(
                    f"No se pudo determinar sector desde respuesta '{processed_answer}' a INIT_1"
                )

        elif "giro específico" in last_q_summary:  # Identifica pregunta INIT_2
            processed_answer = user_input.strip()
            sector = conversation.metadata.get("selected_sector")
            subsector = None
            if sector:
                q_details = questionnaire_service.get_question_details("INIT_2")
                conditions = q_details.get("conditions", {}) if q_details else {}
                options = conditions.get(sector, [])
                if processed_answer.isdigit():
                    try:
                        idx = int(processed_answer) - 1
                        if 0 <= idx < len(options):
                            subsector = options[idx]
                    except ValueError:
                        pass
                else:
                    for opt in options:
                        if processed_answer.lower() == opt.lower():
                            subsector = opt
                            break
            if subsector:
                conversation.metadata["selected_subsector"] = subsector
                logger.info(
                    f"Metadata[selected_subsector] actualizada a '{subsector}' en chat.py"
                )
            else:
                logger.warning(
                    f"No se pudo determinar subsector desde respuesta '{processed_answer}' a INIT_2 para sector '{sector}'"
                )
        # -------------------------------------------------------------

        # 5. Guardar conversación completa (con nuevos mensajes y metadata actualizada)
        await storage_service.save_conversation(conversation)

        # 6. Limpieza en segundo plano
        background_tasks.add_task(storage_service.cleanup_old_conversations)

        # 7. Devolver respuesta en formato esperado por frontend
        return {
            "id": assistant_message.id,
            "message": assistant_message.content,
            "conversation_id": conversation_id,
            "created_at": assistant_message.created_at,
        }

    # --- Manejo de Errores (Igual que en versión híbrida) ---
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(
            f"Error fatal no controlado en send_message (LLM-Driven) para {conversation_id}: {str(e)}",
            exc_info=True,
        )
        error_response = {
            "id": "error-fatal",
            "message": "Lo siento, ha ocurrido un error inesperado al procesar tu mensaje.",
            "conversation_id": (
                conversation_id if "conversation_id" in locals() else "unknown"
            ),
            "created_at": datetime.utcnow(),  # Usar datetime importado
        }
        try:
            if "conversation" in locals() and conversation:
                conversation.metadata["last_error"] = f"Fatal: {str(e)}"
                await storage_service.save_conversation(conversation)
        except Exception as save_err:
            logger.error(
                f"Error adicional al guardar error fatal en metadata: {save_err}"
            )
        return error_response


# --- Endpoints /download-pdf y _is_pdf_request (SIN CAMBIOS respecto a la versión híbrida) ---
# Siguen dependiendo de que metadata['has_proposal'] y metadata['proposal_text'] sean correctos.


def _is_pdf_request(message: str) -> bool:
    # ... (igual que antes) ...
    if not message:
        return False
    message = message.lower().strip()
    pdf_keywords = [
        "pdf",
        "descargar propuesta",
        "descargar pdf",
        "generar pdf",
        "obtener documento",
        "propuesta final",
    ]
    return message in pdf_keywords or any(
        keyword in message for keyword in pdf_keywords
    )


@router.get("/{conversation_id}/download-pdf")
async def download_pdf(conversation_id: str):
    # ... (pegar aquí la función download_pdf completa de la versión híbrida, no necesita cambios) ...
    try:
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")
        if not conversation.metadata.get("has_proposal", False):
            logger.warning(
                f"Intento de descarga PDF para {conversation_id} sin propuesta generada."
            )
            raise HTTPException(
                status_code=400,
                detail="La propuesta para esta conversación aún no está lista.",
            )
        proposal_text = conversation.metadata.get("proposal_text")
        if not proposal_text:
            logger.error(
                f"Propuesta marcada como lista pero sin texto en metadata para {conversation_id}."
            )
            raise HTTPException(
                status_code=500,
                detail="Error interno: Falta contenido de la propuesta [PDFL01]",
            )
        pdf_path = conversation.metadata.get("pdf_path")
        if pdf_path and os.path.exists(pdf_path):
            logger.info(f"PDF encontrado en caché para {conversation_id}: {pdf_path}")
        else:
            logger.info(
                f"Generando PDF bajo demanda (LLM-Driven) para {conversation_id}..."
            )
            try:
                pdf_path = await pdf_service.generate_pdf_from_text(
                    conversation_id, proposal_text
                )
                if not pdf_path or not os.path.exists(pdf_path):
                    raise ValueError(
                        "La generación de PDF falló o no devolvió una ruta válida."
                    )
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
                    detail="No se pudo generar el archivo PDF de la propuesta [PDFL02]",
                )
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
            detail="Error interno al procesar la descarga del archivo [PDFL03]",
        )
