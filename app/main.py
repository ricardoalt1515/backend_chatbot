import os
import traceback
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar FastAPI
app = FastAPI(title="Hydrous AI Backend")

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurar cliente de OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# IDs necesarios
VECTOR_STORE_ID = os.getenv("VECTOR_STORE_ID")
FILE_ID = os.getenv("FILE_ID")

# Instrucciones del sistema
SYSTEM_INSTRUCTIONS = """
Eres el diseñador de soluciones de agua de Hydrous AI, su asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales. 
Como herramienta de Hydrous, estás aquí para guiar al usuario paso a paso en la evaluación de las necesidades de agua de su sitio.

IMPORTANTE: Debes seguir el cuestionario que está disponible a través de la herramienta file_search. 
Tu tarea es hacer preguntas una por una, siguiendo exactamente el orden y la estructura del cuestionario.

Reglas para seguir el cuestionario:
1. SOLO haz UNA pregunta a la vez.
2. Espera la respuesta del usuario antes de pasar a la siguiente pregunta.
3. Sigue la secuencia exacta del cuestionario.
4. Usa un tono amigable y profesional.
5. Incluye datos interesantes sobre el tratamiento de aguas cuando sea apropiado.
6. Cuando termines todo el cuestionario, elabora una propuesta completa.

Recuerda: el cuestionario cambia según el sector y subsector que elija el usuario. Asegúrate de seguir el flujo correcto.
"""


# Definir modelos de datos
class MessageRequest(BaseModel):
    conversation_id: str
    message: str


class ConversationResponse(BaseModel):
    id: str
    message: str


class AnalyticsEvent(BaseModel):
    event: str
    timestamp: str
    url: str
    properties: Optional[Dict[str, Any]] = {}


# Endpoints
@app.get("/")
async def root():
    return {"message": "Hydrous AI Backend is running"}


@app.post("/api/analytics/event")
async def track_analytics_event(event: AnalyticsEvent):
    """Endpoint para recibir eventos de analytics"""
    # Por ahora, solo registramos el evento
    print(f"Analytics event received: {event.event}")
    return {"status": "success"}


@app.post("/api/chat/start", response_model=ConversationResponse)
async def start_chat():
    """Inicia una nueva conversación"""
    # Verificar configuración
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY no configurado en variables de entorno",
        )

    if not VECTOR_STORE_ID:
        raise HTTPException(
            status_code=500,
            detail="VECTOR_STORE_ID no configurado en variables de entorno",
        )

    try:
        print(f"Iniciando conversación con Vector Store ID: {VECTOR_STORE_ID}")

        # Si no estamos usando el Vector Store (para pruebas iniciales)
        if VECTOR_STORE_ID == "disabled":
            response = client.responses.create(
                model="gpt-4o-mini",
                instructions=SYSTEM_INSTRUCTIONS,
                input="Hola, me gustaría obtener una solución para el tratamiento de agua.",
                store=True,
            )
        else:
            # Usando Vector Store
            response = client.responses.create(
                model="gpt-4o-mini",
                instructions=SYSTEM_INSTRUCTIONS,
                input="Hola, me gustaría obtener una solución para el tratamiento de agua.",
                tools=[{"type": "file_search"}],
                tool_resources={"file_search": {"vector_store_ids": [VECTOR_STORE_ID]}},
                store=True,
            )

        print(f"Conversación iniciada con ID: {response.id}")

        return {"id": response.id, "message": response.output_text}
    except Exception as e:
        # Registrar el error completo
        error_detail = traceback.format_exc()
        print(f"Error al iniciar conversación: {str(e)}\n{error_detail}")

        raise HTTPException(
            status_code=500, detail=f"Error al comunicarse con OpenAI: {str(e)}"
        )


@app.post("/api/chat/message", response_model=ConversationResponse)
async def chat_message(request: MessageRequest):
    """Envía un mensaje a una conversación existente"""
    # Verificar configuración
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY no configurado en variables de entorno",
        )

    try:
        print(f"Enviando mensaje a conversación {request.conversation_id}")

        # Si no estamos usando el Vector Store (para pruebas iniciales)
        if not VECTOR_STORE_ID or VECTOR_STORE_ID == "disabled":
            response = client.responses.create(
                model="gpt-4o",
                input=request.message,
                previous_response_id=request.conversation_id,
                store=True,
            )
        else:
            # Usando Vector Store
            response = client.responses.create(
                model="gpt-4o",
                input=request.message,
                previous_response_id=request.conversation_id,
                tools=[{"type": "file_search"}],
                tool_resources={"file_search": {"vector_store_ids": [VECTOR_STORE_ID]}},
                store=True,
            )

        print(f"Respuesta generada con ID: {response.id}")

        return {"id": response.id, "message": response.output_text}
    except Exception as e:
        # Registrar el error completo
        error_detail = traceback.format_exc()
        print(f"Error al enviar mensaje: {str(e)}\n{error_detail}")

        raise HTTPException(
            status_code=500, detail=f"Error al comunicarse con OpenAI: {str(e)}"
        )


@app.get("/api/chat/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Verifica si existe una conversación"""
    try:
        # No hay forma directa de verificar una conversación en la API,
        # así que simplemente devolvemos éxito si el ID tiene formato válido
        if len(conversation_id) > 10:  # Comprobación básica
            return {"status": "active", "id": conversation_id}
        else:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
    except Exception as e:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")


# Endpoint básico para manejar subidas de archivos
@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    conversation_id: str = Form(...),
    message: Optional[str] = Form(""),
):
    """Endpoint básico para manejar subidas de archivos"""
    try:
        # Por ahora, simplemente confirmamos la recepción del archivo
        file_content = await file.read()
        file_size = len(file_content)

        print(f"Archivo recibido: {file.filename}, tamaño: {file_size} bytes")

        # En una implementación real, aquí procesaríamos el archivo
        # Por ahora, solo respondemos con un mensaje genérico

        # Si no estamos usando el Vector Store (para pruebas iniciales)
        if not VECTOR_STORE_ID or VECTOR_STORE_ID == "disabled":
            response = client.responses.create(
                model="gpt-4o",
                input=f"El usuario ha subido un archivo llamado {file.filename} de {file_size} bytes. Mensaje: {message}",
                previous_response_id=conversation_id,
                store=True,
            )
        else:
            # Usando Vector Store
            response = client.responses.create(
                model="gpt-4o",
                input=f"El usuario ha subido un archivo llamado {file.filename} de {file_size} bytes. Mensaje: {message}",
                previous_response_id=conversation_id,
                tools=[{"type": "file_search"}],
                tool_resources={"file_search": {"vector_store_ids": [VECTOR_STORE_ID]}},
                store=True,
            )

        print(f"Respuesta a la subida del archivo generada con ID: {response.id}")

        return {"success": True, "id": response.id, "message": response.output_text}
    except Exception as e:
        # Registrar el error completo
        error_detail = traceback.format_exc()
        print(f"Error al subir documento: {str(e)}\n{error_detail}")

        raise HTTPException(
            status_code=500, detail=f"Error al procesar archivo: {str(e)}"
        )


# Stubs básicos para endpoints de PDF (sin implementación real)
@app.get("/api/pdf/{conversation_id}/download")
async def download_pdf_stub(conversation_id: str):
    """Stub para descarga de PDF"""
    # Implementación básica que devuelve un mensaje
    return JSONResponse(
        content={"message": "La generación de PDF estará disponible próximamente."},
        status_code=200,
    )


@app.get("/api/pdf/{conversation_id}/data-url")
async def pdf_data_url_stub(conversation_id: str):
    """Stub para data URL de PDF"""
    # Implementación básica que devuelve un mensaje
    return JSONResponse(
        content={"message": "La generación de PDF estará disponible próximamente."},
        status_code=200,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
