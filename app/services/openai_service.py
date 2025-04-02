from openai import OpenAI
from app.core.config import settings
from app.core.logging import get_logger
import time
from typing import List, Optional

logger = get_logger(__name__)


class OpenAIService:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    async def create_assistant(
        self,
        instructions: str,
        name: str = "Hydrous Water Solutions Assistant",
        files: Optional[List[str]] = None,
    ):
        """Crear un asistente de OpenAI con las instrucciones dadas"""
        try:
            logger.info(f"Creating assistant with name: {name}")
            assistant = self.client.beta.assistants.create(
                name=name,
                instructions=instructions,
                model="gpt-4-turbo",
                tools=[],
                file_ids=files or [],
            )
            logger.info(f"Assistant created successfully with ID: {assistant.id}")
            return assistant
        except Exception as e:
            logger.error(f"Error creating assistant: {e}")
            raise

    async def upload_file(self, file_path: str, purpose: str = "assistants"):
        """Subir un archivo a OpenAI"""
        try:
            logger.info(f"Uploading file: {file_path}")
            with open(file_path, "rb") as file:
                response = self.client.files.create(file=file, purpose=purpose)
            logger.info(f"File uploaded successfully with ID: {response.id}")
            return response
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            raise

    async def create_thread(self, metadata=None):
        """Crear un nuevo hilo de conversación"""
        try:
            logger.info("Creating new thread")
            thread = self.client.beta.threads.create(metadata=metadata)
            logger.info(f"Thread created successfully with ID: {thread.id}")
            return thread
        except Exception as e:
            logger.error(f"Error creating thread: {e}")
            raise

    async def add_message(self, thread_id: str, content: str):
        """Añadir un mensaje al hilo de conversación"""
        try:
            logger.info(f"Adding message to thread {thread_id}")
            message = self.client.beta.threads.messages.create(
                thread_id=thread_id, role="user", content=content
            )
            logger.info(f"Message added successfully with ID: {message.id}")
            return message
        except Exception as e:
            logger.error(f"Error adding message: {e}")
            raise

    async def run_assistant(self, thread_id: str, assistant_id: str):
        """Ejecutar el asistente en el hilo dado"""
        try:
            logger.info(f"Running assistant {assistant_id} on thread {thread_id}")
            run = self.client.beta.threads.runs.create(
                thread_id=thread_id, assistant_id=assistant_id
            )

            # Esperar a que finalice la ejecución
            while True:
                run_status = self.client.beta.threads.runs.retrieve(
                    thread_id=thread_id, run_id=run.id
                )
                if run_status.status == "completed":
                    logger.info(f"Run completed successfully: {run.id}")
                    break
                elif run_status.status in ["failed", "cancelled", "expired"]:
                    logger.error(f"Run ended with status {run_status.status}")
                    raise Exception(f"Run failed with status: {run_status.status}")

                logger.debug(f"Run status: {run_status.status}, waiting...")
                time.sleep(1)  # Esperar un segundo antes de verificar de nuevo

            # Obtener los mensajes más recientes
            messages = self.client.beta.threads.messages.list(thread_id=thread_id)

            # Retornar el mensaje más reciente del asistente
            for msg in messages.data:
                if msg.role == "assistant":
                    # Obtener el contenido del mensaje
                    content = [c.text.value for c in msg.content if c.type == "text"]
                    return content[0] if content else ""

            return ""
        except Exception as e:
            logger.error(f"Error running assistant: {e}")
            raise

    async def get_assistant(self, assistant_id: str):
        """Obtener información del asistente"""
        try:
            logger.info(f"Getting assistant with ID: {assistant_id}")
            assistant = self.client.beta.assistants.retrieve(assistant_id)
            logger.info(f"Assistant retrieved successfully: {assistant.name}")
            return assistant
        except Exception as e:
            logger.error(f"Error getting assistant: {e}")
            raise
