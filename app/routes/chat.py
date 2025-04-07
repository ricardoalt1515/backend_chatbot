# app/routes/chat.py
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import logging
import os
import uuid  # Importar uuid
from datetime import datetime  # Importar datetime
from typing import Any, Optional, Dict  # Añadir Optional y Dict

# Modelos
from app.models.conversation import ConversationResponse, Conversation
from app.models.message import Message, MessageCreate

# Servicios
from app.services.storage_service import storage_service
from app.services.ai_service import ai_service  # IA para conversación
from app.services.pdf_service import pdf_service  # Para generar PDF
from app.services.proposal_service import (
    proposal_service,
)  # NUEVO: Para generar texto propuesta
from app.services.questionnaire_service import (
    questionnaire_service,
)  # Para obtener IDs/detalles preguntas
from app.config import settings

router = APIRouter()
logger = logging.getLogger("hydrous")

# --- Funciones Auxiliares (Movidas aquí o importadas si son complejas) ---


def _get_full_questionnaire_path(metadata: Dict[str, Any]) -> List[str]:
    """Intenta construir la ruta completa del cuestionario."""
    # Reutilizar lógica de construcción de ruta (simplificada de proposal_service o questionnaire_service original)
    path = [
        q["id"]
        for q in questionnaire_service.structure.get("initial_questions", [])
        if "id" in q
    ]
    sector = metadata.get("selected_sector")
    subsector = metadata.get("selected_subsector")
    if sector and subsector:
        try:
            sector_data = questionnaire_service.structure.get(
                "sector_questionnaires", {}
            ).get(sector, {})
            subsector_questions = sector_data.get(subsector, [])
            if not isinstance(subsector_questions, list):
                subsector_questions = sector_data.get("Otro", [])
            path.extend([q["id"] for q in subsector_questions if "id" in q])
        except Exception as e:
            logger.error(f"Error construyendo ruta en _get_full_path: {e}")
            # Fallback a solo iniciales si falla
            path = [
                q["id"]
                for q in questionnaire_service.structure.get("initial_questions", [])
                if "id" in q
            ]
    return path


def _is_last_question(
    current_question_id: Optional[str], metadata: Dict[str, Any]
) -> bool:
    """Verifica si la pregunta actual es la última de la ruta completa."""
    if not current_question_id:
        return False

    # Intentar obtener/construir la ruta completa
    path = metadata.get("questionnaire_path", [])
    if not path:  # Si no está en metadata, intentar construirla ahora
        path = _get_full_questionnaire_path(metadata)
        metadata["questionnaire_path"] = path  # Guardar por si acaso
        logger.debug(f"Ruta construida on-the-fly en _is_last_question: {path}")

    if not path:
        return False  # Si no se pudo construir, no podemos saber si es la última

    try:
        # Es la última si su índice es el último de la lista
        is_last = path.index(current_question_id) == len(path) - 1
        if is_last:
            logger.info(
                f"Detectada respuesta a la última pregunta ({current_question_id}) de la ruta."
            )
        return is_last
    except ValueError:
        logger.warning(
            f"_is_last_question: ID '{current_question_id}' no encontrado en ruta {path}"
        )
        return False  # No estaba en la ruta


# --- Endpoints ---


@router.post("/start", response_model=ConversationResponse)
async def start_conversation():
    """Inicia conversación, devuelve saludo/pregunta inicial de la IA."""
    try:
        conversation = await storage_service.create_conversation()
        logger.info(
            f"Nueva conversación (Flujo PDF Automático) iniciada: {conversation.id}"
        )

        # Llamar a la IA para obtener el primer mensaje (saludo + primera pregunta)
        # Pasamos una conversación "vacía" (solo con ID y metadata) para que sepa que es el inicio
        initial_ai_response = await ai_service.handle_conversation(conversation)
        assistant_message = Message.assistant(initial_ai_response)

        # Añadir este primer mensaje al historial de la conversación
        conversation.messages.append(assistant_message)
        # Actualizar metadata con la primera pregunta hecha (extraída por ai_service)
        # ai_service.handle_conversation debería haber actualizado metadata['current_question_asked_summary']

        # Guardar estado inicial con el primer mensaje
        await storage_service.save_conversation(conversation)

        return ConversationResponse(
            id=conversation.id,
            created_at=conversation.created_at,
            messages=[assistant_message],  # Devolver solo el primer mensaje
            metadata=conversation.metadata,
        )
    except Exception as e:
        logger.error(
            f"Error crítico al iniciar conversación (PDF Automático): {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail="No se pudo iniciar la conversación."
        )


@router.post("/message")
async def send_message(data: MessageCreate, background_tasks: BackgroundTasks):
    """
    Procesa mensaje usuario. Si es el último, genera propuesta y PDF automáticamente.
    Si no, obtiene siguiente pregunta de la IA.
    """
    conversation_id = data.conversation_id
    user_input = data.message
    assistant_response_data = None  # Para guardar la respuesta a enviar al frontend

    try:
        # 1. Cargar Conversación
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            logger.error(f"Conversación no encontrada: {conversation_id}")
            # Usar un return aquí para evitar anidamiento excesivo
            return {
                "id": "error-conv-not-found",
                "message": "Error: Conversación no encontrada.",
                "conversation_id": conversation_id,
                "created_at": datetime.utcnow(),
            }
        if not isinstance(conversation.metadata, dict):
            logger.error(f"Metadata inválida para conversación: {conversation_id}")
            return {
                "id": "error-metadata",
                "message": "Error interno [MD01].",
                "conversation_id": conversation_id,
                "created_at": datetime.utcnow(),
            }

        # 2. Añadir mensaje del usuario al historial en memoria
        user_message_obj = Message.user(user_input)
        conversation.messages.append(user_message_obj)

        # 3. Determinar si fue la última respuesta
        last_question_id = conversation.metadata.get("current_question_id")
        is_final_answer = _is_last_question(last_question_id, conversation.metadata)

        if is_final_answer:
            # --- Cuestionario Terminado ---
            logger.info(
                f"Última respuesta ({last_question_id}) recibida para {conversation_id}. Iniciando generación Propuesta+PDF."
            )

            # a. Actualizar metadata con la última respuesta
            conversation.metadata["collected_data"][
                last_question_id
            ] = user_input.strip()
            conversation.metadata["is_complete"] = True
            conversation.metadata["current_question_id"] = None
            conversation.metadata["current_question_asked_summary"] = (
                "Cuestionario Completado"
            )

            # b. Generar Texto Propuesta (Backend)
            proposal_text = None
            try:
                proposal_text = await proposal_service.generate_proposal_text(
                    conversation
                )
                conversation.metadata["proposal_text"] = proposal_text
                conversation.metadata["has_proposal"] = True
                client_name = conversation.metadata.get("collected_data", {}).get(
                    "INIT_0", "Cliente"
                )
                conversation.metadata["client_name"] = client_name
                logger.info(
                    f"Texto de propuesta generado (Backend) para {conversation_id}"
                )
            except Exception as e:
                logger.error(
                    f"Error generando texto de propuesta para {conversation_id}: {e}",
                    exc_info=True,
                )
                # Crear mensaje de error para enviar al frontend
                error_msg = Message.assistant(
                    "Lo siento, hubo un problema al generar el contenido de tu propuesta."
                )
                await storage_service.add_message_to_conversation(
                    conversation.id, error_msg
                )
                await storage_service.save_conversation(conversation)
                return {
                    "id": error_msg.id,
                    "message": error_msg.content,
                    "conversation_id": conversation_id,
                    "created_at": error_msg.created_at,
                }

            # c. Generar PDF (Backend)
            pdf_path = None
            if proposal_text:  # Solo si el texto se generó
                try:
                    pdf_path = await pdf_service.generate_pdf_from_text(
                        conversation_id, proposal_text
                    )
                    if pdf_path:
                        conversation.metadata["pdf_path"] = pdf_path
                        logger.info(
                            f"PDF generado (Backend) para {conversation_id} en: {pdf_path}"
                        )
                    else:
                        raise ValueError("pdf_service no devolvió ruta válida.")
                except Exception as e:
                    logger.error(
                        f"Error generando PDF para {conversation_id}: {e}",
                        exc_info=True,
                    )
                    # Enviar mensaje indicando error PDF pero propuesta lista? O error general?
                    # Optamos por mensaje de error específico de PDF
                    error_msg = Message.assistant(
                        "¡Propuesta generada! Pero hubo un problema al crear el archivo PDF. Contacta a soporte."
                    )
                    await storage_service.add_message_to_conversation(
                        conversation.id, error_msg
                    )
                    await storage_service.save_conversation(conversation)
                    return {
                        "id": error_msg.id,
                        "message": error_msg.content,
                        "conversation_id": conversation_id,
                        "created_at": error_msg.created_at,
                    }

            # d. Si TODO OK (Texto y PDF generados): Preparar respuesta especial
            if pdf_path:
                download_url = (
                    f"{settings.API_V1_STR}/chat/{conversation.id}/download-pdf"
                )
                assistant_response_data = {
                    "id": "proposal-ready-" + str(uuid.uuid4())[:8],
                    "message": "¡Hemos completado tu propuesta! Puedes descargarla ahora.",  # Mensaje a mostrar
                    "conversation_id": conversation_id,
                    "created_at": datetime.utcnow(),
                    "action": "download_proposal_pdf",  # Acción para frontend
                    "download_url": download_url,
                }
                # Añadir el mensaje "Hemos completado..." al historial también
                msg_to_add = Message.assistant(assistant_response_data["message"])
                await storage_service.add_message_to_conversation(
                    conversation.id, msg_to_add
                )

        else:
            # --- Flujo Normal: Pedir siguiente pregunta a IA ---
            logger.info(
                f"Llamando a ai_service.handle_conversation para {conversation_id}"
            )
            ai_response_content = await ai_service.handle_conversation(conversation)
            assistant_message = Message.assistant(ai_response_content)
            # Añadir respuesta de IA al historial
            await storage_service.add_message_to_conversation(
                conversation.id, assistant_message
            )
            # Preparar respuesta normal para frontend
            assistant_response_data = {
                "id": assistant_message.id,
                "message": assistant_message.content,
                "conversation_id": conversation_id,
                "created_at": assistant_message.created_at,
            }

            # --- Actualizar metadata Sector/Subsector (si aplica, basado en user_input) ---
            last_q_summary = conversation.metadata.get(
                "current_question_asked_summary", ""
            )
            # (La lógica para actualizar sector/subsector aquí se mantiene igual que antes)
            if "sector principal opera" in last_q_summary:
                # ... lógica sector ...
                pass
            elif "giro específico" in last_q_summary:
                # ... lógica subsector ...
                pass

        # --- Guardar y Devolver ---
        # Guardar conversación ANTES de devolver respuesta
        await storage_service.save_conversation(conversation)
        # Limpieza
        background_tasks.add_task(storage_service.cleanup_old_conversations)

        if assistant_response_data:
            return assistant_response_data
        else:
            # Fallback si algo salió mal y no se preparó respuesta
            logger.error(f"Fallo al determinar respuesta para {conversation_id}")
            return {
                "id": "error-no-response",
                "message": "Error interno [NR02]",
                "conversation_id": conversation_id,
                "created_at": datetime.utcnow(),
            }

    # --- Manejo de Excepciones ---
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(
            f"Error fatal en send_message (PDF Automático) para {conversation_id}: {str(e)}",
            exc_info=True,
        )
        error_response = {
            "id": "error-fatal",
            "message": "Lo siento, ha ocurrido un error inesperado.",
            "conversation_id": (
                conversation_id if "conversation_id" in locals() else "unknown"
            ),
            "created_at": datetime.utcnow(),
        }
        try:  # Intentar guardar error
            if (
                "conversation" in locals()
                and conversation
                and isinstance(conversation.metadata, dict)
            ):
                conversation.metadata["last_error"] = (
                    f"Fatal: {str(e)[:200]}"  # Limitar longitud error
                )
                await storage_service.save_conversation(conversation)
        except Exception as save_err:
            logger.error(f"Error guardando error fatal: {save_err}")
        return error_response


# Endpoint /download-pdf (SIN CAMBIOS)
@router.get("/{conversation_id}/download-pdf")
async def download_pdf(conversation_id: str):
    # ... (La lógica de descarga que ya tenías y funcionaba) ...
    try:
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")
        if not conversation.metadata.get("has_proposal", False):
            raise HTTPException(status_code=400, detail="Propuesta no lista.")
        proposal_text = conversation.metadata.get("proposal_text")
        if not proposal_text:
            raise HTTPException(
                status_code=500, detail="Error interno: Falta contenido [PDFDL01]"
            )

        pdf_path = conversation.metadata.get("pdf_path")
        # Generar si no existe o el archivo se borró
        if not pdf_path or not os.path.exists(pdf_path):
            logger.info(
                f"Generando PDF bajo demanda (descarga) para {conversation_id}..."
            )
            try:
                pdf_path = await pdf_service.generate_pdf_from_text(
                    conversation_id, proposal_text
                )
                if not pdf_path or not os.path.exists(pdf_path):
                    raise ValueError("Generación PDF falló.")
                conversation.metadata["pdf_path"] = pdf_path
                await storage_service.save_conversation(conversation)
            except Exception as e:
                logger.error(
                    f"Error crítico generando PDF para descarga {conversation_id}: {e}",
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=500,
                    detail="No se pudo generar el archivo PDF [PDFDL02]",
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
            f"Error fatal procesando descarga PDF para {conversation_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Error interno descarga [PDFDL03]")
