# app/routes/chat.py
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse, Response
import logging
import os
from typing import Any

# Modelos
from app.models.conversation import ConversationResponse, Conversation
from app.models.message import (
    Message,
    MessageCreate,
)  # Asegurarse que MessageCreate está aquí

# Servicios
from app.services.storage_service import storage_service
from app.services.ai_service_hybrid import ai_service_hybrid  # Cambiado a Híbrido
from app.services.pdf_service import pdf_service
from app.services.questionnaire_service import (
    questionnaire_service,
)  # Aún se usa para saludo/IDs
from app.config import settings

router = APIRouter()
logger = logging.getLogger("hydrous")


@router.post("/start", response_model=ConversationResponse)
async def start_conversation():
    """Inicia una nueva conversación y devuelve el saludo inicial."""
    try:
        # 1. Crear conversación (storage_service maneja metadata inicial)
        conversation = await storage_service.create_conversation()
        logger.info(f"Nueva conversación HÍBRIDA iniciada con ID: {conversation.id}")

        # 2. Obtener saludo inicial del QuestionnaireService
        initial_greeting = questionnaire_service.get_initial_greeting()

        # 3. Opcional: Añadir un mensaje inicial de sistema o asistente si quieres
        #    PERO el flujo real empieza con el primer mensaje del usuario.
        #    Podríamos devolver el saludo como parte de la respuesta para que el frontend lo muestre.
        # initial_message = Message.assistant(initial_greeting)
        # await storage_service.add_message_to_conversation(conversation.id, initial_message)
        # await storage_service.save_conversation(conversation) # Guardar si añadimos mensaje

        # 4. Devolver ID y metadata inicial (frontend mostrará UI vacía o saludo)
        return ConversationResponse(
            id=conversation.id,
            created_at=conversation.created_at,
            messages=[],  # Sin mensajes aún, el saludo es implícito o lo maneja el frontend
            metadata=conversation.metadata,
        )
    except Exception as e:
        logger.error(
            f"Error crítico al iniciar conversación híbrida: {str(e)}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail="No se pudo iniciar la conversación."
        )


@router.post("/message")  # Quitar response_model
async def send_message(data: MessageCreate, background_tasks: BackgroundTasks):
    """Recibe mensaje del usuario, obtiene la siguiente respuesta del AI Service Híbrido."""
    conversation_id = data.conversation_id
    user_input = data.message

    try:
        # 1. Cargar Conversación
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            logger.error(f"Conversación no encontrada: {conversation_id}")
            # Devolver un diccionario de error compatible con frontend
            return {
                "id": "error-conv-not-found",
                "message": "Error: Conversación no encontrada. Por favor, reinicia.",
                "conversation_id": conversation_id,
                "created_at": datetime.utcnow(),
            }
        # Verificar metadata básica
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
        conversation.add_message(user_message_obj)  # Añadir al historial
        # Nota: La actualización de metadata (datos recolectados, sector, etc.)
        # la hará AHORA el ai_service_hybrid ANTES de determinar la siguiente instrucción.

        # 3. Llamar al AI Service Híbrido para obtener la siguiente respuesta
        logger.info(
            f"Llamando a ai_service_hybrid.get_next_response para {conversation_id}"
        )
        ai_response_content = await ai_service_hybrid.get_next_response(conversation)

        # 4. Crear y añadir mensaje del asistente
        assistant_message = Message.assistant(ai_response_content)
        conversation.add_message(assistant_message)

        # 5. Guardar conversación completa (con nuevos mensajes y metadata actualizada por AI Service)
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

    # --- Manejo de Errores ---
    except HTTPException as http_exc:
        # Re-lanzar para que FastAPI maneje
        raise http_exc
    except Exception as e:
        logger.error(
            f"Error fatal no controlado en send_message (híbrido) para {conversation_id}: {str(e)}",
            exc_info=True,
        )
        # Devolver un error genérico compatible con frontend
        error_response = {
            "id": "error-fatal",
            "message": "Lo siento, ha ocurrido un error inesperado al procesar tu mensaje.",
            "conversation_id": (
                conversation_id if "conversation_id" in locals() else "unknown"
            ),
            "created_at": datetime.utcnow(),
        }
        # Intentar guardar el error en metadata si la conversación se cargó
        try:
            if "conversation" in locals() and conversation:
                conversation.metadata["last_error"] = f"Fatal: {str(e)}"
                await storage_service.save_conversation(conversation)
        except Exception as save_err:
            logger.error(
                f"Error adicional al guardar error fatal en metadata: {save_err}"
            )

        return error_response  # Devolver el diccionario de error


# --- Endpoints /download-pdf y _is_pdf_request ---
# La lógica de descarga de PDF puede permanecer similar,
# PERO el endpoint /message YA NO maneja la generación del mensaje de descarga.
# El LLM ahora genera la propuesta y el mensaje de "Escribe PDF...".
# El usuario escribe "PDF", eso llega a /message, y el flujo normal debería detectar
# que has_proposal es True y is_pdf_request es True, devolviendo el enlace.


# Modificar _is_pdf_request para ser más preciso
def _is_pdf_request(message: str) -> bool:
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
    ]
    # Podría ser una coincidencia exacta o contener una de las frases clave
    return message in pdf_keywords or any(
        keyword in message for keyword in pdf_keywords
    )


@router.get("/{conversation_id}/download-pdf")
async def download_pdf(conversation_id: str):
    """Genera (si es necesario) y devuelve la propuesta en formato PDF."""
    # --- Esta lógica debería funcionar casi igual ---
    # Verifica que has_proposal sea True y que proposal_text exista en metadata
    try:
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")

        # Verificar si la propuesta está lista en metadata
        if not conversation.metadata.get("has_proposal", False):
            logger.warning(
                f"Intento de descarga PDF para {conversation_id} sin propuesta generada."
            )
            raise HTTPException(
                status_code=400,
                detail="La propuesta para esta conversación aún no está lista.",
            )

        # Obtener texto de la propuesta de metadata
        proposal_text = conversation.metadata.get("proposal_text")
        if not proposal_text:
            logger.error(
                f"Propuesta marcada como lista pero sin texto en metadata para {conversation_id}."
            )
            raise HTTPException(
                status_code=500,
                detail="Error interno: Falta contenido de la propuesta [PDFH01]",
            )

        # Verificar si el PDF ya existe en caché (ruta en metadata)
        pdf_path = conversation.metadata.get("pdf_path")
        if pdf_path and os.path.exists(pdf_path):
            logger.info(f"PDF encontrado en caché para {conversation_id}: {pdf_path}")
        else:
            # Generar PDF si no existe
            logger.info(
                f"Generando PDF bajo demanda (híbrido) para {conversation_id}..."
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
                    detail="No se pudo generar el archivo PDF de la propuesta [PDFH02]",
                )

        # Preparar y devolver el archivo
        client_name = conversation.metadata.get("client_name", "Cliente")
        filename = f"Propuesta_Hydrous_{client_name}_{conversation_id[:8]}.pdf"

        return FileResponse(
            path=pdf_path,
            filename=filename,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ... (Manejo de excepciones de download_pdf igual que antes) ...
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(
            f"Error fatal al procesar descarga de PDF para {conversation_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Error interno al procesar la descarga del archivo [PDFH03]",
        )
