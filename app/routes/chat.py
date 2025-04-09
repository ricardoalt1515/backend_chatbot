# app/routes/chat.py
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import logging
import os
import uuid  # Importar uuid
import re
from datetime import datetime  # Importar datetime
from typing import Any, Optional, Dict, List  # Añadir Optional y Dict

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


def _is_pdf_request(message: str) -> bool:
    """Determina si el mensaje es una solicitud de PDF de forma más robusta."""
    if not message:
        return False
    message = message.lower().strip()
    # Palabras clave específicas
    pdf_keywords = [
        "pdf",
        "descargar propuesta",
        "descargar pdf",
        "generar pdf",
        "obtener documento",
        "propuesta final",
        "descargar",
    ]  # Añadir descargar
    # Podría ser una coincidencia exacta o contener una de las frases clave
    is_request = message in pdf_keywords or any(
        keyword in message for keyword in pdf_keywords
    )
    logger.debug(
        f"_is_pdf_request: Input='{message}', Keywords={pdf_keywords}, Result={is_request}"
    )
    return is_request


# --- Endpoints ---


@router.post("/start", response_model=ConversationResponse)
async def start_conversation():
    """Inicia conversación, devuelve saludo/pregunta inicial de la IA."""
    try:
        conversation = await storage_service.create_conversation()
        logger.info(f"Nueva conversación iniciada (Usuario inicia): {conversation.id}")

        # 2. NO llamar a IA aquí. Guardar estado vacío.
        await storage_service.save_conversation(conversation)
        # 3. Devolver solo ID y metadata vacía
        return ConversationResponse(
            id=conversation.id,
            created_at=conversation.created_at,
            messages=[],  # Sin mensajes iniciales
            metadata=conversation.metadata,
        )
    except Exception as e:
        logger.error(f"Error crítico al iniciar conversación: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="No se pudo iniciar la conversación."
        )


@router.post("/message")
async def send_message(data: MessageCreate, background_tasks: BackgroundTasks):
    """
    Procesa mensaje usuario. Llama a IA para obtener siguiente paso (pregunta o
    mensaje de propuesta lista). Maneja petición explícita de descarga PDF.
    """
    conversation_id = data.conversation_id
    user_input = data.message
    assistant_response_data = None  # Para guardar la respuesta a enviar al frontend

    try:
        # 1. Cargar Conversación
        logger.debug(f"Recibida petición /message para conv: {conversation_id}")
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation or not isinstance(conversation.metadata, dict):
            return {
                "id": "error-conv-not-found",
                "message": "Error: Conversación no encontrada. Por favor, reinicia.",
                "conversation_id": conversation_id,
                "created_at": datetime.utcnow(),
            }

        # 2. Crear objeto mensaje usuario
        user_message_obj = Message.user(user_input)

        # --- 3. Lógica Flujo ---
        is_pdf_req = _is_pdf_request(user_input)
        proposal_ready = conversation.metadata.get("has_proposal", False)

        logger.info(
            f"DBG_PDF_CHECK: ConvID={conversation_id}, Input='{user_input}', is_pdf_req={is_pdf_req}, proposal_ready={proposal_ready}"
        )

        if is_pdf_req and proposal_ready:
            # --- Flujo Descarga PDF Explícita (SIN CAMBIOS) ---
            logger.info(
                f"DBG_PDF_CHECK: Entrando en flujo de descarga PDF explícita para {conversation_id}."
            )
            download_url = f"{settings.BACKEND_URL}{settings.API_V1_STR}/chat/{conversation.id}/download-pdf"
            assistant_response_data = {
                "id": "pdf-trigger-" + str(uuid.uuid4())[:8],
                "message": None,
                "conversation_id": conversation_id,
                "created_at": datetime.utcnow(),
                "action": "trigger_download",
                "download_url": download_url,
            }
            # No guardar aquí

        else:
            # --- Flujo Normal ---
            logger.info(
                f"DBG_PDF_CHECK: Entrando en flujo normal/final para {conversation_id}."
            )
            conversation.messages.append(user_message_obj)  # Añadir mensaje usuario

            # Actualizar metadata básica (sector/subsector) si aplica
            last_question_id = conversation.metadata.get("current_question_id")
            if last_question_id:
                conversation.metadata["collected_data"][
                    last_question_id
                ] = user_input.strip()
                # ... (lógica sector/subsector si last_question_id es INIT_1 o INIT_2) ...
                pass

            # Verificar si fue la última respuesta
            is_final_answer = _is_last_question(last_question_id, conversation.metadata)
            logger.debug(
                f"DBG_PDF_CHECK: last_q_id='{last_question_id}', is_final_answer={is_final_answer}"
            )

            if is_final_answer:
                # --- Cuestionario Terminado: Generar Texto y PDF (Backend) ---
                logger.info(
                    f"Última respuesta recibida. Generando Propuesta+PDF (Backend) para {conversation_id}."
                )
                conversation.metadata["is_complete"] = True
                conversation.metadata["current_question_id"] = None
                conversation.metadata["current_question_asked_summary"] = (
                    "Cuestionario Completado"
                )

                proposal_text = None
                pdf_path = None
                error_occurred = False

                try:
                    # Generar texto de propuesta
                    logger.info(
                        f"Generando texto de propuesta para {conversation_id}..."
                    )
                    proposal_text = await ai_service.generate_proposal_text_only(
                        conversation
                    )

                    if proposal_text.startswith("Error"):
                        raise ValueError(
                            f"AI Service falló al generar texto: {proposal_text}"
                        )

                    conversation.metadata["proposal_text"] = proposal_text
                    conversation.metadata["has_proposal"] = True
                    client_name = conversation.metadata.get("collected_data", {}).get(
                        "INIT_0", "Cliente"
                    )
                    conversation.metadata["client_name"] = client_name

                    # Generar PDF
                    logger.info(f"Generando PDF para {conversation_id}...")
                    pdf_path = await pdf_service.generate_pdf_from_text(
                        conversation_id, proposal_text
                    )

                    if not pdf_path or not os.path.exists(pdf_path):
                        raise ValueError("PDF no generado correctamente.")

                    conversation.metadata["pdf_path"] = pdf_path

                    # Preparar respuesta con descarga automática
                    download_url = f"{settings.BACKEND_URL}{settings.API_V1_STR}/chat/{conversation.id}/download-pdf"

                    # Respuesta con acción de descarga
                    assistant_response_data = {
                        "id": "proposal-ready-" + str(uuid.uuid4())[:8],
                        "message": "¡Propuesta lista! Se está descargando el PDF con tu propuesta personalizada.",
                        "conversation_id": conversation_id,
                        "created_at": datetime.utcnow(),
                        "action": "trigger_download",  # Acción para frontend que inicia descarga
                        "download_url": download_url,
                    }

                    # Añadir mensaje al historial
                    msg_to_add = Message.assistant(assistant_response_data["message"])
                    await storage_service.add_message_to_conversation(
                        conversation.id, msg_to_add
                    )

                except Exception as e:
                    error_occurred = True
                    logger.error(f"Error generando propuesta/PDF: {e}", exc_info=True)
                    conversation.metadata["last_error"] = (
                        f"Error propuesta: {str(e)[:200]}"
                    )
                    error_msg = "Lo siento, ha ocurrido un error al generar tu propuesta. Por favor intenta nuevamente."
                    error_msg_obj = Message.assistant(error_msg)
                    await storage_service.add_message_to_conversation(
                        conversation.id, error_msg_obj
                    )
                    assistant_response_data = {
                        "id": error_msg_obj.id,
                        "message": error_msg_obj.content,
                        "conversation_id": conversation_id,
                        "created_at": error_msg_obj.created_at,
                    }

            else:
                # --- Aún hay preguntas: Llamar a IA para siguiente paso ---
                logger.info(
                    f"DBG_PDF_CHECK: Llamando a AI Service para obtener siguiente pregunta."
                )
                # Guardar antes de llamar
                await storage_service.save_conversation(conversation)
                ai_response_content = await ai_service.handle_conversation(conversation)
                assistant_message = Message.assistant(ai_response_content)
                await storage_service.add_message_to_conversation(
                    conversation.id, assistant_message
                )
                assistant_response_data = {
                    "id": assistant_message.id,
                    "message": assistant_message.content,
                    "conversation_id": conversation_id,
                    "created_at": assistant_message.created_at,
                }

        # --- Guardar y Devolver ---
        await storage_service.save_conversation(conversation)
        background_tasks.add_task(storage_service.cleanup_old_conversations)

        if not assistant_response_data:
            # ... (fallback error) ...
            pass

        logger.info(
            f"Devolviendo respuesta para {conversation_id}: action={assistant_response_data.get('action', 'N/A')}, msg_len={len(assistant_response_data.get('message', '') or '')}"
        )
        return assistant_response_data

    # --- Manejo de Excepciones ---
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(
            f"Error fatal no controlado en send_message para {conversation_id}: {str(e)}",
            exc_info=True,
        )
        error_response = {
            "id": "error-fatal-" + str(uuid.uuid4())[:8],
            "message": "Lo siento, ha ocurrido un error inesperado en el servidor.",
            "conversation_id": (
                conversation_id if "conversation_id" in locals() else "unknown"
            ),
            "created_at": datetime.utcnow(),
        }
        try:
            if (
                "conversation" in locals()
                and isinstance(conversation, Conversation)
                and isinstance(conversation.metadata, dict)
            ):
                conversation.metadata["last_error"] = f"Fatal: {str(e)[:200]}"
                await storage_service.save_conversation(conversation)
        except Exception as save_err:
            logger.error(f"Error adicional guardando error fatal: {save_err}")
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
