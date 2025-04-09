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
                "message": "Error interno [MD01].",
                "conversation_id": conversation_id,
                "created_at": datetime.utcnow(),
            }

        # 2. Crear objeto mensaje usuario (se añade al historial si no es petición PDF)
        user_message_obj = Message.user(user_input)

        # --- 3. Lógica Flujo: ¿Petición PDF Explícita? ---
        is_pdf_req = _is_pdf_request(user_input)
        proposal_ready = conversation.metadata.get("has_proposal", False)

        logger.info(
            f"DBG_PDF_CHECK: ConvID={conversation_id}, Input='{user_input}', is_pdf_req={is_pdf_req}, proposal_ready={proposal_ready}"
        )

        if is_pdf_req and proposal_ready:
            # --- Flujo de Descarga PDF Explícita ---
            logger.info(
                f"DBG_PDF_CHECK: Entrando en flujo de descarga PDF explícita para {conversation_id}."
            )
            download_url = f"{settings.BACKEND_URL}{settings.API_V1_STR}/chat/{conversation.id}/download-pdf"
            assistant_response_data = {
                "id": "pdf-trigger-" + str(uuid.uuid4())[:8],
                "message": None,  # No hay mensaje de chat
                "conversation_id": conversation_id,
                "created_at": datetime.utcnow(),
                "action": "trigger_download",  # Flag para frontend
                "download_url": download_url,
            }
            logger.info(
                f"DBG_PDF_CHECK: Preparada respuesta trigger_download para {conversation_id}."
            )
            # No añadir mensaje "descargar pdf", no llamar a IA, no guardar conversación aquí

        else:
            # --- Flujo Normal: Procesar input, llamar a IA ---
            logger.info(
                f"DBG_PDF_CHECK: Entrando en flujo normal para {conversation_id}."
            )

            # Añadir mensaje del usuario al historial ANTES de procesarlo/llamar a IA
            conversation.messages.append(user_message_obj)

            # Actualizar metadata Sector/Subsector (si aplica, basado en user_input a PREGUNTA ANTERIOR)
            try:
                # Usar metadata ANTES de la llamada a IA para saber cuál fue la última pregunta
                last_q_summary = conversation.metadata.get(
                    "current_question_asked_summary", ""
                )
                last_question_id = conversation.metadata.get(
                    "current_question_id"
                )  # Necesitamos el ID anterior
                logger.debug(
                    f"Actualizando sector/subsector basado en user_input='{user_input}' para last_q_id='{last_question_id}'"
                )

                if last_question_id == "INIT_1":  # Pregunta del Sector
                    processed_answer = user_input.strip()
                    q_details = questionnaire_service.get_question_details("INIT_1")
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
                    # Verificar si el texto coincide case-insensitive
                    else:
                        for opt in options:
                            if processed_answer.lower() == opt.lower():
                                sector = opt
                                break
                    if sector:
                        conversation.metadata["selected_sector"] = sector
                        logger.info(
                            f"Metadata[selected_sector] actualizada a '{sector}'"
                        )
                    else:
                        logger.warning(
                            f"No se pudo determinar sector desde '{processed_answer}' para INIT_1"
                        )

                elif last_question_id == "INIT_2":  # Pregunta del Subsector
                    processed_answer = user_input.strip()
                    sector = conversation.metadata.get("selected_sector")
                    subsector = None
                    if sector:
                        q_details = questionnaire_service.get_question_details("INIT_2")
                        conditions = (
                            q_details.get("conditions", {}) if q_details else {}
                        )
                        options = conditions.get(sector, [])
                        if processed_answer.isdigit():
                            try:
                                idx = int(processed_answer) - 1
                                if options and 0 <= idx < len(options):
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
                            f"Metadata[selected_subsector] actualizada a '{subsector}'"
                        )
                        # IMPORTANTE: Construir la ruta AHORA que tenemos sector y subsector
                        full_path = _get_full_questionnaire_path(conversation.metadata)
                        conversation.metadata["questionnaire_path"] = full_path
                        logger.info(f"Ruta completa guardada en metadata: {full_path}")
                    else:
                        logger.warning(
                            f"No se pudo determinar subsector desde '{processed_answer}' para INIT_2 / sector '{sector}'"
                        )

                # Guardar conversación con metadata actualizada ANTES de llamar a IA
                # Esto asegura que la IA tenga el sector/subsector correcto para su lógica
                await storage_service.save_conversation(conversation)

            except Exception as e:
                logger.error(
                    f"Error actualizando metadata antes de llamar a IA: {e}",
                    exc_info=True,
                )
                # Considerar continuar o devolver error

            # Llamar a AI Service para obtener la siguiente respuesta
            # ai_service.handle_conversation actualizará internamente metadata como
            # 'current_question_asked_summary', 'proposal_text', 'has_proposal', 'is_complete'
            logger.info(
                f"Llamando a ai_service.handle_conversation para {conversation_id}"
            )
            ai_response_content = await ai_service.handle_conversation(conversation)

            # Crear y añadir mensaje del asistente al historial
            assistant_message = Message.assistant(ai_response_content)
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

        # --- Guardar y Devolver ---
        # Guardar estado final de la conversación (incluye mensajes y metadata actualizada por IA)
        # Guardar incluso si la respuesta fue solo el trigger_download (para persistir el historial si es necesario)
        if not (
            is_pdf_req and proposal_ready
        ):  # No guardar si solo se devolvió trigger_download
            await storage_service.save_conversation(conversation)

        background_tasks.add_task(storage_service.cleanup_old_conversations)  # Limpieza

        if not assistant_response_data:
            logger.error(
                f"Fallo crítico: No se preparó assistant_response_data para {conversation_id}"
            )
            assistant_response_data = {
                "id": "error-no-resp-prep",
                "message": "Error interno [NR03]",
                "conversation_id": conversation_id,
                "created_at": datetime.utcnow(),
            }

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
