# app/routes/chat.py
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import logging
import os
import uuid
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
    """
    Recibe mensaje del usuario. Si es petición de PDF (y está listo),
    devuelve trigger de descarga. Si no, añade mensaje, obtiene respuesta
    de la IA, actualiza estado y devuelve respuesta de IA.
    """
    conversation_id = data.conversation_id
    user_input = data.message.strip()  # Limpiar input

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

        # --- Comprobar si es petición de PDF ---
        is_pdf_req = _is_pdf_request(user_input)
        proposal_ready = conversation.metadata.get("has_proposal", False)

        # --- Manejo Especial para Petición de PDF ---
        if is_pdf_req and proposal_ready:
            logger.info(
                f"Petición de PDF detectada para {conversation_id} (propuesta lista). Devolviendo trigger."
            )

            # NO añadir mensaje "descargar pdf" al historial
            # NO llamar a AI Service

            # Devolver respuesta especial para disparar descarga en frontend
            download_url = f"{settings.API_V1_STR}/chat/{conversation.id}/download-pdf"
            trigger_response = {
                "id": "pdf-trigger-" + str(uuid.uuid4())[:8],
                "message": None,  # Indicar al frontend que no muestre mensaje
                "conversation_id": conversation_id,
                "created_at": datetime.utcnow(),
                "action": "trigger_download",  # Flag para el frontend
                "download_url": download_url,  # URL directa
            }
            # Opcional: Guardar conversación por si acaso (aunque no cambió mucho)
            # await storage_service.save_conversation(conversation)
            return trigger_response  # Devolver el JSON especial

        # --- Flujo Normal: No es petición de PDF (o la propuesta no está lista) ---
        else:
            # Añadir mensaje del usuario al historial en memoria primero
            user_message_obj = Message.user(user_input)
            conversation.messages.append(user_message_obj)

            # Llamar al AI Service para obtener la siguiente respuesta del bot
            logger.info(
                f"Llamando a ai_service.handle_conversation para {conversation_id}"
            )
            # handle_conversation internamente actualizará metadata como 'current_question_asked_summary'
            ai_response_content = await ai_service.handle_conversation(conversation)

            # Crear y añadir mensaje del asistente al historial en memoria
            assistant_message = Message.assistant(ai_response_content)
            conversation.messages.append(assistant_message)

            # --- Actualizar metadata Sector/Subsector (basado en input del usuario) ---
            # (Esta lógica es crucial para que el prompt tenga el estado correcto en la siguiente llamada)
            last_q_summary = conversation.metadata.get(
                "current_question_asked_summary", ""
            )
            logger.debug(
                f"Última pregunta resumida: '{last_q_summary}'"
            )  # Log para ver qué pregunta se hizo

            # Chequeo si la última pregunta FUE la de pedir el sector
            if last_q_summary and "sector principal opera" in last_q_summary:
                logger.debug(f"Procesando respuesta '{user_input}' para SECTOR")
                sector = None
                q_details = questionnaire_service.get_question_details(
                    "INIT_1"
                )  # Usar servicio simplificado
                options = q_details.get("options", []) if q_details else []
                if user_input.isdigit():
                    try:
                        idx = int(user_input) - 1
                        if 0 <= idx < len(options):
                            sector = options[idx]
                    except (ValueError, IndexError):
                        pass
                elif (
                    user_input in options
                ):  # Chequeo simple por texto exacto (sensible a mayúsculas aquí)
                    sector = user_input
                # Podríamos añadir chequeo case-insensitive si quisiéramos más robustez
                # else:
                #      for opt in options:
                #          if user_input.lower() == opt.lower():
                #              sector = opt
                #              break

                if sector:
                    conversation.metadata["selected_sector"] = sector
                    logger.info(
                        f"Metadata[selected_sector] actualizada a '{sector}' en chat.py"
                    )
                else:
                    conversation.metadata["selected_sector"] = (
                        None  # Resetear si no es válido
                    )
                    logger.warning(
                        f"No se pudo determinar sector desde respuesta '{user_input}' a INIT_1"
                    )

            # Chequeo si la última pregunta FUE la de pedir el giro específico
            elif last_q_summary and "giro específico" in last_q_summary:
                logger.debug(f"Procesando respuesta '{user_input}' para SUBSECTOR")
                subsector = None
                sector = conversation.metadata.get(
                    "selected_sector"
                )  # Necesitamos el sector ya guardado
                if sector:
                    q_details = questionnaire_service.get_question_details("INIT_2")
                    conditions = q_details.get("conditions", {}) if q_details else {}
                    options = conditions.get(
                        sector, []
                    )  # Obtener opciones para ese sector
                    if user_input.isdigit():
                        try:
                            idx = int(user_input) - 1
                            if 0 <= idx < len(options):
                                subsector = options[idx]
                        except (ValueError, IndexError):
                            pass
                    else:  # Chequeo por texto (case-insensitive)
                        for opt in options:
                            if user_input.lower() == opt.lower():
                                subsector = opt
                                break
                if subsector:
                    conversation.metadata["selected_subsector"] = subsector
                    logger.info(
                        f"Metadata[selected_subsector] actualizada a '{subsector}' en chat.py"
                    )
                else:
                    conversation.metadata["selected_subsector"] = (
                        None  # Resetear si no es válido
                    )
                    logger.warning(
                        f"No se pudo determinar subsector desde respuesta '{user_input}' a INIT_2 para sector '{sector}'"
                    )
            # --------------------------------------------------------------------

            # Guardar conversación completa con mensajes y metadata actualizada
            await storage_service.save_conversation(conversation)

            # Limpieza
            background_tasks.add_task(storage_service.cleanup_old_conversations)

            # Devolver respuesta normal del asistente
            return {
                "id": assistant_message.id,
                "message": assistant_message.content,
                "conversation_id": conversation_id,
                "created_at": assistant_message.created_at,
            }

    # --- Manejo de Excepciones ---
    except HTTPException as http_exc:
        logger.warning(
            f"HTTPException en send_message ({'PDF Req' if is_pdf_req else 'Normal'}) para {conversation_id}: {http_exc.status_code} - {http_exc.detail}"
        )
        raise http_exc
    except Exception as e:
        logger.error(
            f"Error fatal no controlado en send_message ({'PDF Req' if 'is_pdf_req' in locals() and is_pdf_req else 'Normal'}) para {conversation_id}: {str(e)}",
            exc_info=True,
        )
        error_response = {
            "id": "error-fatal",
            "message": "Lo siento, ha ocurrido un error inesperado al procesar tu mensaje.",
            "conversation_id": (
                conversation_id if "conversation_id" in locals() else "unknown"
            ),
            "created_at": datetime.utcnow(),
        }
        try:
            if (
                "conversation" in locals()
                and conversation
                and isinstance(conversation.metadata, dict)
            ):  # Verificar tipo metadata
                conversation.metadata["last_error"] = f"Fatal: {str(e)}"
                await storage_service.save_conversation(conversation)
        except Exception as save_err:
            logger.error(
                f"Error adicional al intentar guardar error fatal en metadata: {save_err}"
            )
        return error_response


# --- HASTA AQUÍ REEMPLAZAR ---

# --- Las funciones _is_pdf_request y download_pdf permanecen igual que en la versión anterior ---


def _is_pdf_request(message: str) -> bool:
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
        "descargar",
    ]  # Añadir 'descargar'
    # Comprobar si es una de las palabras clave exactas o si contiene una
    return message in pdf_keywords or any(
        keyword in message for keyword in ["propuesta", "documento", "pdf"]
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
