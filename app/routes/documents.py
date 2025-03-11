from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
import logging
from typing import Optional, List

from app.services.document_service import document_service
from app.services.storage_service import storage_service
from app.services.ai_service import ai_service
from app.models.message import Message, MessageResponse
from app.config import settings

logger = logging.getLogger("hydrous-backend")

router = APIRouter()


@router.post("/upload", response_model=MessageResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    conversation_id: str = Form(...),
    message: Optional[str] = Form(None),
):
    """
    Sube un documento y lo asocia a una conversación.
    Opcionalmente procesa un mensaje relacionado con el documento.
    """
    try:
        # Verificar que la conversación existe
        conversation = await storage_service.get_conversation(conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")

        # Verificar tamaño máximo del archivo
        if file.size > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"El archivo excede el tamaño máximo permitido ({settings.MAX_UPLOAD_SIZE/1024/1024} MB)",
            )

        # Guardar documento
        doc_info = await document_service.save_document(file, conversation_id)

        # Si hay un mensaje del usuario, añadirlo a la conversación
        user_message_content = f"[Documento adjunto: {file.filename}]"
        if message:
            user_message_content = f"{message}\n{user_message_content}"

        user_message = Message.user(
            user_message_content, {"document_id": doc_info["id"]}
        )
        await storage_service.add_message_to_conversation(conversation_id, user_message)

        # Respuesta inicial
        initial_response = f"He recibido tu documento '{file.filename}'. "

        # En el MVP usamos una respuesta simple para documentos
        # En el futuro se implementará procesamiento y análisis de documentos
        if file.content_type.startswith("image/"):
            response_text = (
                initial_response
                + "Veo que has compartido una imagen. ¿Hay algo específico que quieras saber sobre ella en relación con nuestras soluciones de reciclaje de agua?"
            )
        elif file.content_type == "application/pdf":
            response_text = (
                initial_response
                + "Revisaré el PDF que has compartido. ¿Hay alguna sección o información específica que te interese discutir sobre nuestros sistemas de reciclaje de agua?"
            )
        elif "spreadsheet" in file.content_type or file.filename.endswith(
            (".xlsx", ".xls", ".csv")
        ):
            response_text = (
                initial_response
                + "Has compartido una hoja de cálculo. ¿Estás analizando datos sobre consumo o tratamiento de agua? Puedo ayudarte a interpretar esa información."
            )
        else:
            response_text = (
                initial_response
                + "¿Hay algo específico sobre este documento con lo que pueda ayudarte en relación a nuestras soluciones de reciclaje de agua?"
            )

        # Crear y añadir mensaje del asistente
        assistant_message = Message.assistant(response_text)
        await storage_service.add_message_to_conversation(
            conversation_id, assistant_message
        )

        # Programar limpieza de conversaciones antiguas (tarea en segundo plano)
        background_tasks.add_task(storage_service.cleanup_old_conversations)

        return MessageResponse(
            id=assistant_message.id,
            conversation_id=conversation_id,
            message=response_text,
            created_at=assistant_message.created_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al procesar documento: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al procesar el documento")


@router.get("/{document_id}")
async def get_document_info(document_id: str):
    """Obtiene información de un documento por su ID"""
    doc = await document_service.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    # Excluir la ruta del sistema de archivos por seguridad
    doc_info = {k: v for k, v in doc.items() if k != "path"}
    return doc_info


@router.get("/conversation/{conversation_id}")
async def get_conversation_documents(conversation_id: str):
    """Obtiene todos los documentos asociados a una conversación"""
    # Verificar que la conversación existe
    conversation = await storage_service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    docs = await document_service.get_conversation_documents(conversation_id)
    # Excluir las rutas del sistema de archivos por seguridad
    return [{k: v for k, v in doc.items() if k != "path"} for doc in docs]
