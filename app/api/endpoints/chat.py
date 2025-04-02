from fastapi import APIRouter, HTTPException, Depends
from app.models.schemas import ChatRequest, ChatResponse
from app.services.openai_service import OpenAIService
from app.core.config import settings
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


async def get_openai_service():
    return OpenAIService()


@router.post("/", response_model=ChatResponse)
async def chat_with_assistant(
    request: ChatRequest, openai_service: OpenAIService = Depends(get_openai_service)
):
    """
    Envía un mensaje al asistente y recibe una respuesta.
    Si no se proporciona thread_id, se crea uno nuevo.
    """
    if not settings.ASSISTANT_ID:
        logger.error("Assistant ID not configured")
        raise HTTPException(status_code=500, detail="Assistant not configured")

    try:
        # Si no hay thread_id, crear uno nuevo
        thread_id = request.thread_id
        if not thread_id:
            logger.info("No thread_id provided, creating new thread")
            thread = await openai_service.create_thread()
            thread_id = thread.id

        # Añadir mensaje al hilo
        await openai_service.add_message(thread_id, request.message)

        # Ejecutar el asistente y obtener respuesta
        response = await openai_service.run_assistant(thread_id, settings.ASSISTANT_ID)

        return ChatResponse(thread_id=thread_id, response=response)
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Error processing request: {str(e)}"
        )
