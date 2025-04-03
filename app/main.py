import os
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict
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

# Instrucciones del sistema
SYSTEM_INSTRUCTIONS = """
Eres el diseñador de soluciones de agua de Hydrous AI, su asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales. 
Como herramienta de Hydrous, estás aquí para guiar al usuario paso a paso en la evaluación de las necesidades de agua de su sitio.

Tu tarea es hacer preguntas detalladas siguiendo este patrón:

1. Primero, pregunta en qué sector opera su empresa: Industrial, Comercial, Municipal o Residencial.
2. Basado en su respuesta, pregunta sobre el subsector específico dentro de ese sector.
3. Luego, haz preguntas sobre su ubicación, costos de agua, consumo, etc.
4. Sólo haz UNA pregunta a la vez y espera la respuesta.
5. Cuando hayas recopilado suficiente información, ofrece algunas recomendaciones preliminares.

Mantén un tono profesional, cálido y conversacional.
"""


# Definir modelos de datos
class MessageRequest(BaseModel):
    conversation_id: str
    message: str


class ConversationResponse(BaseModel):
    id: str
    message: str


# Endpoints
@app.get("/")
async def root():
    return {"message": "Hydrous AI Backend is running"}


@app.post("/api/chat/start", response_model=ConversationResponse)
async def start_chat():
    """Inicia una nueva conversación"""
    try:
        response = client.responses.create(
            model="gpt-4o",
            instructions=SYSTEM_INSTRUCTIONS,
            input="Estoy listo para ayudarte con tus necesidades de tratamiento de agua.",
            store=True,
        )

        return {"id": response.id, "message": response.output_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/message", response_model=ConversationResponse)
async def chat_message(request: MessageRequest):
    """Envía un mensaje a una conversación existente"""
    try:
        response = client.responses.create(
            model="gpt-4o",
            input=request.message,
            previous_response_id=request.conversation_id,
            store=True,
        )

        return {"id": response.id, "message": response.output_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


# Para manejo básico de archivos (stub, sin implementación real)
@app.post("/api/documents/upload")
async def upload_document_stub():
    """Stub para subida de documentos"""
    return {
        "success": True,
        "message": "He recibido tu archivo, pero actualmente no puedo procesarlo. Por favor, continúa con el cuestionario.",
    }


# Stubs básicos para endpoints de PDF (sin implementación real)
@app.get("/api/pdf/{conversation_id}/download")
async def download_pdf_stub(conversation_id: str):
    """Stub para descarga de PDF"""
    raise HTTPException(status_code=501, detail="Generación de PDF no implementada")


@app.get("/api/pdf/{conversation_id}/data-url")
async def pdf_data_url_stub(conversation_id: str):
    """Stub para data URL de PDF"""
    raise HTTPException(status_code=501, detail="Generación de PDF no implementada")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
