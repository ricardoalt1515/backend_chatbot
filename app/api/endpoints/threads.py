from fastapi import APIRouter, HTTPException, Depends
from app.models.schemas import ThreadCreate, ThreadResponse
from app.services.openai_service import OpenAIService
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


async def get_openai_service():
    return OpenAIService()


@router.post("/", response_model=ThreadResponse)
async def create_thread(
    request: ThreadCreate = None,
    openai_service: OpenAIService = Depends(get_openai_service),
):
    """
    Crea un nuevo hilo de conversación.
    """
    try:
        metadata = request.metadata if request and request.metadata else None
        thread = await openai_service.create_thread(metadata)
        return ThreadResponse(id=thread.id)
    except Exception as e:
        logger.error(f"Error creating thread: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating thread: {str(e)}")
