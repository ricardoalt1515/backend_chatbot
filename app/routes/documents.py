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

        # Guardar documento y obtener insights preliminares
        doc_info = await document_service.save_document(file, conversation_id)

        # Si hay un mensaje del usuario, añadirlo a la conversación
        user_message_content = f"[Documento adjunto: {file.filename}]"
        if message:
            user_message_content = f"{message}\n{user_message_content}"

        user_message = Message.user(
            user_message_content, {"document_id": doc_info["id"]}
        )
        await storage_service.add_message_to_conversation(conversation_id, user_message)

        # Generar respuesta basada en los insights del documento
        insights = doc_info.get("insights", {})
        doc_type = insights.get("document_type", "unknown")
        relevance = insights.get("relevance_to_water_treatment", "unknown")

        # Personalizar respuestas segun el tipo de documento
        if doc_type == "image":
            response_text = (
                f"Gracias por compartir esta imagen. He recibido tu archivo '{file.filename}'. "
                f"Las imágenes son muy útiles para entender visualmente los problemas o instalaciones actuales. "
                f"¿Podrías describir brevemente qué muestra esta imagen y por qué es relevante para tu proyecto de tratamiento de agua?"
            )
        elif doc_type == "pdf":
            response_text = (
                f"He recibido tu documento PDF '{file.filename}'. "
                f"Los documentos técnicos son muy valiosos para entender mejor tus necesidades específicas. "
                f"¿Este documento contiene información sobre tus instalaciones actuales, especificaciones técnicas, o estudios previos relacionados con el agua?"
            )
        elif doc_type == "spreadsheet":
            response_text = (
                f"Gracias por compartir la hoja de cálculo '{file.filename}'. "
                f"Los datos numéricos son fundamentales para dimensionar correctamente una solución de tratamiento de agua. "
                f"¿Esta hoja de cálculo contiene datos de consumo, parámetros de calidad, o costos relacionados con el agua?"
            )
        elif doc_type == "text_document" or doc_type == "text":
            if relevance == "highly_relevant":
                key_points = insights.get("key_points", [])
                point_text = ""
                if key_points:
                    point_text = "\n\nHe identificado algunos puntos relevantes en el documento:\n"
                    for point in key_points[:3]:
                        point_text += f"- {point}\n"

                response_text = (
                    f"He recibido y analizado tu documento '{file.filename}'. "
                    f"Parece contener información relevante sobre sistemas de tratamiento de agua. {point_text}\n\n"
                    f"¿Hay algún aspecto específico del documento sobre el que quieras que nos enfoquemos en la propuesta?"
                )
            else:
                response_text = (
                    f"He recibido tu documento '{file.filename}'. "
                    f"Utilizaré la información relevante para personalizar mejor la propuesta. "
                    f"¿Hay algo específico en este documento que quieras destacar para nuestra solución de tratamiento de agua?"
                )
        else:
            response_text = (
                f"He recibido tu archivo '{file.filename}'. "
                f"Lo tendré en cuenta durante nuestro proceso de evaluación. "
                f"¿Podrías indicarme qué tipo de información contiene este archivo y cómo se relaciona con tu proyecto de tratamiento de agua?"
            )

        # Si el cuestionario esta activo, añadir sugerencia para continuar
        if conversation.is_questionnaire_active():
            response_text += "\n\nPodemos continuar con el cuestionario en cualquier momento para completar la recopilación de información para tu propuesta."

        # Crear y añadir mensaje del asistente
        assistant_message = Message.assistant(response_text)
        await storage_service.add_message_to_conversation(
            conversation_id, assistant_message
        )

        # Programar limpieza de conversaciones antiguas (tareas en segundo plano)
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
