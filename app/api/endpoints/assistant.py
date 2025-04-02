from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks
from app.models.schemas import (
    AssistantCreate,
    AssistantResponse,
    FileUploadResponse,
    StatusResponse,
)
from app.services.openai_service import OpenAIService
from app.core.config import settings
from app.core.logging import get_logger
import os
import tempfile
from typing import List

router = APIRouter()
logger = get_logger(__name__)


async def get_openai_service():
    return OpenAIService()


@router.post("/create", response_model=AssistantResponse)
async def create_assistant(
    assistant_data: AssistantCreate,
    openai_service: OpenAIService = Depends(get_openai_service),
):
    """
    Crea un nuevo asistente con las instrucciones proporcionadas
    y actualiza la configuración con el ID del asistente.
    """
    try:
        assistant = await openai_service.create_assistant(
            name=assistant_data.name,
            instructions=assistant_data.instructions,
            files=assistant_data.file_ids,
        )

        # Guardar el ID del asistente en la configuración
        settings.ASSISTANT_ID = assistant.id

        # Actualizar el archivo .env (requiere permisos de escritura)
        try:
            with open(".env", "r") as env_file:
                lines = env_file.readlines()

            with open(".env", "w") as env_file:
                for line in lines:
                    if line.startswith("ASSISTANT_ID="):
                        env_file.write(f"ASSISTANT_ID={assistant.id}\n")
                    else:
                        env_file.write(line)

                # Si no existe la línea ASSISTANT_ID, añadirla
                if not any(line.startswith("ASSISTANT_ID=") for line in lines):
                    env_file.write(f"ASSISTANT_ID={assistant.id}\n")

            logger.info(f"Updated .env file with assistant ID: {assistant.id}")
        except Exception as e:
            logger.warning(f"Could not update .env file: {e}")

        return AssistantResponse(
            id=assistant.id, name=assistant.name, created_at=assistant.created_at
        )
    except Exception as e:
        logger.error(f"Error creating assistant: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error creating assistant: {str(e)}"
        )


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    openai_service: OpenAIService = Depends(get_openai_service),
):
    """
    Sube un archivo a OpenAI para usarlo con el asistente.
    """
    try:
        # Guardar el archivo temporalmente
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(await file.read())
            temp_path = temp_file.name

        # Subir el archivo a OpenAI
        response = await openai_service.upload_file(temp_path)

        # Eliminar el archivo temporal
        os.unlink(temp_path)

        return FileUploadResponse(file_id=response.id, filename=file.filename)
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        # Asegurarse de eliminar el archivo temporal en caso de error
        if "temp_path" in locals():
            try:
                os.unlink(temp_path)
            except:
                pass
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")


@router.get("/status", response_model=StatusResponse)
async def get_status(openai_service: OpenAIService = Depends(get_openai_service)):
    """
    Verifica el estado del asistente.
    """
    if not settings.ASSISTANT_ID:
        return StatusResponse(
            status="not_configured",
            assistant_id=None,
            message="Assistant not configured",
        )

    try:
        assistant = await openai_service.get_assistant(settings.ASSISTANT_ID)
        return StatusResponse(
            status="ready",
            assistant_id=assistant.id,
            message=f"Assistant '{assistant.name}' is ready",
        )
    except Exception as e:
        logger.error(f"Error checking assistant status: {e}")
        return StatusResponse(
            status="error",
            assistant_id=settings.ASSISTANT_ID,
            message=f"Error: {str(e)}",
        )


@router.post("/init", response_model=StatusResponse)
async def initialize_assistant(
    background_tasks: BackgroundTasks,
    openai_service: OpenAIService = Depends(get_openai_service),
):
    """
    Inicializa el asistente con los archivos y configuraciones predeterminadas.
    """
    try:
        # Verificar si ya existe un asistente configurado
        if settings.ASSISTANT_ID:
            try:
                assistant = await openai_service.get_assistant(settings.ASSISTANT_ID)
                return StatusResponse(
                    status="already_configured",
                    assistant_id=assistant.id,
                    message=f"Assistant '{assistant.name}' already configured",
                )
            except:
                # Si no se puede obtener el asistente, continuar con la inicialización
                pass

        # Cargar instrucciones desde el archivo
        try:
            with open(settings.INSTRUCTIONS_FILE, "r", encoding="utf-8") as f:
                instructions = f.read()
        except Exception as e:
            logger.error(f"Error reading instructions file: {e}")
            raise HTTPException(
                status_code=500, detail=f"Error reading instructions file: {str(e)}"
            )

        # Subir los archivos necesarios
        file_ids = []
        try:
            questionnaire_file = await openai_service.upload_file(
                settings.QUESTIONNAIRE_FILE
            )
            file_ids.append(questionnaire_file.id)

            proposal_format_file = await openai_service.upload_file(
                settings.PROPOSAL_FORMAT_FILE
            )
            file_ids.append(proposal_format_file.id)
        except Exception as e:
            logger.error(f"Error uploading files: {e}")
            raise HTTPException(
                status_code=500, detail=f"Error uploading files: {str(e)}"
            )

        # Crear el asistente
        assistant = await openai_service.create_assistant(
            name="Hydrous Water Solutions Assistant",
            instructions=instructions,
            files=file_ids,
        )

        # Guardar el ID del asistente
        settings.ASSISTANT_ID = assistant.id

        # Actualizar el archivo .env
        try:
            with open(".env", "r") as env_file:
                lines = env_file.readlines()

            with open(".env", "w") as env_file:
                for line in lines:
                    if line.startswith("ASSISTANT_ID="):
                        env_file.write(f"ASSISTANT_ID={assistant.id}\n")
                    else:
                        env_file.write(line)

                # Si no existe la línea ASSISTANT_ID, añadirla
                if not any(line.startswith("ASSISTANT_ID=") for line in lines):
                    env_file.write(f"ASSISTANT_ID={assistant.id}\n")
        except Exception as e:
            logger.warning(f"Could not update .env file: {e}")

        return StatusResponse(
            status="initialized",
            assistant_id=assistant.id,
            message="Assistant initialized successfully",
        )
    except Exception as e:
        logger.error(f"Error initializing assistant: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error initializing assistant: {str(e)}"
        )
