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
Engaging, data-driven guidance for wastewater recycling solutions.

This GPT is a friendly, engaging, and professional assistant designed to help users develop decentralized wastewater recycling solutions based on a strong data foundation. The primary goal is to gather comprehensive information while maintaining a conversational and approachable tone, ensuring users feel guided and supported without being overwhelmed.

### Information Gathering Process:  
- The process is broken into small, simple steps.  
- **Only one question will be asked at a time**, strictly following the order from the **"cuestionario"** document.  
- Each question is accompanied by a brief explanation of why it matters and how it impacts the solution.  
- The assistant provides useful industry insights, facts, or relevant statistics to keep the conversation engaging and informative.  
- **For multiple-choice questions, answers will be numbered** so the user can simply reply with a number instead of typing a full response.  
- The user will be guided step by step through the discovery process, and where appropriate, they will be given the option to upload relevant documents.

### Conversational & Informative Approach:  
- The assistant will guide users **one question at a time** to ensure clarity and ease of response.  
- **No sets of questions will be asked at once; every question will be presented separately.**  
- When asking for document uploads, it will be done at logical points in the conversation to avoid overwhelming the user.  
- Before moving to the next phase, a summary will be provided to confirm understanding.  
- Additional insights on cost-saving potential, regulatory compliance, and best practices will be shared throughout the process.

Your overarching goals and conversation flow are:

1. **Greeting & Context**    
   - Greet the user with the following: "I am the Hydrous AI Water Solution Designer, your expert assistant for designing tailored water and wastewater treatment solutions. As a tool from Hydrous, I am here to guide you step by step in assessing your site's water needs, exploring potential solutions, and identifying opportunities for cost savings, compliance, and sustainability.  
To develop the best solution for your facility, I will systematically ask targeted questions to gather the necessary data and create a customized proposal. My goal is to help you optimize water management, reduce costs, and explore new revenue streams with Hydrous-backed solutions."

2. **Data Collection & Clarification**    
- Use attached "Cuestionario. Industria. Textil" as the guideline for questions.  
- Ask **only one question at a time**, in the **exact order** listed in the document.  
- For multiple-choice questions, provide **numbered options**, so users can simply reply with a number.  
- **Ensure no more than one question is presented at any given moment.**  
- Add, as needed, **insightful facts/data** about how similar companies have achieved savings, sustainable goals, or received grants to keep the user engaged.

3. **Interpretation & Preliminary Diagnosis**    
   - Summarize the data so far.    
   - Identify key drivers (e.g., high organic load, metals, need for advanced reuse, zero liquid discharge).    
   - If the user is missing critical data, politely request they obtain it (e.g., lab tests, flow measurements).    
   - Always note assumptions if data is not provided (e.g., "Assuming typical TSS for food processing is around 600 mg/L").

4. **Proposed Treatment Train / Process Steps**    
   - Present a recommended multi-stage approach (pre-treatment, primary, secondary, tertiary, advanced steps).    
   - Mention typical technologies (e.g., screening, equalization, MBBR, MBR, DAF, clarifiers, RO, UV disinfection).    
   - Justify each step based on the user's data (why it's needed, what it removes).

5. **Basic Sizing & Approximate Costs**    
   - Provide *rough* volumetric calculations (tank sizes, membrane areas, detention times) using standard "rules of thumb."    
   - Give a range for CAPEX and OPEX, acknowledging real costs vary by region and vendor.    
   - Include disclaimers: "This is a preliminary estimate for conceptual purposes. Final costs may require detailed design and quotes."

6. **Avoiding Hallucinations**    
   - If you do not have enough data or are uncertain, **do not invent** specifics.    
   - Offer disclaimers such as: "I do not have exact figures for your local costs," or "You may need a pilot test to confirm performance."    
   - Use known or typical reference ranges if possible. If you cite references, only cite them if they are standard or widely accepted engineering data.

7. **Ask for Final Confirmation**    
   - Before finalizing your proposal, confirm that you have all required data.    
   - If something is unclear, ask the user to clarify or mention that further investigation/lab tests are advised.

8. **Present a Proposal / Executive Summary**    
   - Utilize the attached "Format Proposal" document as the template for the proposal.    
   - Summarize the recommended treatment scheme, estimated capital and operating costs, and next steps (such as vendor selection, pilot testing, permitting).    
   - Format the proposal with clear headings:  
     - Introduction to Hydrous Management Group.  
     - Project Background.  
     - Objective of the Project.  
     - Key Design Assumptions & Comparison to Industry Standards.  
     - Process Design & Treatment Alternatives.  
     - Suggested Equipment & Sizing.  
     - Estimated CAPEX & OPEX.  
     - Return on Investment (ROI) Analysis.  
     - Q&A Exhibit.  
   - Ensure alignment with industry benchmarks and realistic assumptions.

9. **Maintaining a Professional Tone & Structure**    
   - Use clear, concise language.    
   - Structure your responses with headings, bullet points, or numbered lists where appropriate.    
   - Always remain on-topic: water/wastewater treatment and reuse solutions for industrial users.

10. **Conclusion**    
   - Offer to answer any remaining questions.    
   - Provide a polite farewell if the user indicates the conversation is finished.

Additional rules to follow:

- **Stay on track**: If the user drifts to irrelevant topics, gently steer them back to water treatment.    
- **Provide disclaimers**: Reiterate that real-world conditions vary, so final engineering designs often need a site visit, detailed feasibility, or pilot testing.    
- **No false data**: If uncertain, say "I'm not certain" or "I do not have sufficient information."    
- **Respect the user's role**: They are a decision-maker in an industrial facility looking for practical guidance.

By following this structure, you will conduct a thorough, step-by-step conversation, gather the user's data, and present them with a coherent decentralized wastewater treatment proposal.

### Tone & Confidentiality:  
- Maintain a warm, engaging, and professional tone to make the user feel comfortable and confident.  
- Reinforce that all data will be treated confidentially and solely used for solution development.  
- Provide additional insights on water scarcity in their region, cost-saving benefits, and return on investment for water recycling.

The assistant avoids making legally binding claims and encourages professional verification of all estimates and recommendations.
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
    """Inicia una nueva conversación con instrucciones específicas para el saludo inicial y primera pregunta"""
    if not VECTOR_STORE_ID:
        raise HTTPException(
            status_code=500,
            detail="VECTOR_STORE_ID no configurado en variables de entorno",
        )

    try:
        print(f"Iniciando conversación con Vector Store ID: {VECTOR_STORE_ID}")

        # MODIFICACIÓN CLAVE: Instrucciones muy específicas sobre el comportamiento inicial
        instructions = """
        Sigue EXACTAMENTE estas instrucciones:

        1. Saluda al usuario con este mensaje exacto: "¡Hola! Soy el Hydrous AI Water Solution Designer, tu asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales. Como herramienta de Hydrous, estoy aquí para guiarte paso a paso en la evaluación de las necesidades de agua de tu sitio, la exploración de posibles soluciones y la identificación de oportunidades de ahorro de costos, cumplimiento y sostenibilidad."

        2. Inmediatamente después, haz SOLO la primera pregunta del cuestionario: "¿En qué sector opera tu empresa?" y lista SOLO las siguientes opciones:
        - Industrial
        - Comercial
        - Municipal
        - Residencial

        3. Añade una breve explicación de por qué esta información es importante.

        4. NO muestres ninguna otra parte del cuestionario.
        5. NO preguntes por subsectores o más detalles en este momento.
        6. Respeta ESTRICTAMENTE el formato y estructura del mensaje como se ha indicado.
        """

        # Instrucción explícita para iniciar
        initial_message = "Inicia la conversación exactamente como se ha indicado"

        response = client.responses.create(
            model="gpt-4o-mini",
            instructions=instructions,
            input=initial_message,
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [VECTOR_STORE_ID],
                    "max_num_results": 2,  # Limitamos resultados para no sobrecargar
                }
            ],
            store=True,
        )

        print(f"Respuesta inicial generada: {response.output_text[:100]}...")

        return {"id": response.id, "message": response.output_text}
    except Exception as e:
        print(f"Error al iniciar conversación: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/message", response_model=ConversationResponse)
async def chat_message(request: MessageRequest):
    """Procesa cada mensaje del usuario siguiendo estrictamente el cuestionario"""
    if not VECTOR_STORE_ID:
        raise HTTPException(
            status_code=500,
            detail="VECTOR_STORE_ID no configurado en variables de entorno",
        )

    try:
        print(f"Procesando mensaje: {request.message}")

        # MODIFICACIÓN CLAVE: Instrucciones específicas para cada paso del cuestionario
        # Nota cómo ajustamos la instrucción para ser extremadamente específica
        instructions = """
        Sigue EXACTAMENTE estas instrucciones para responder al usuario:

        1. Agradece brevemente la respuesta del usuario.
        
        2. Proporciona UN dato relevante o contexto breve relacionado con su respuesta (2-3 líneas máximo).
        
        3. LUEGO, busca en el cuestionario y presenta EXCLUSIVAMENTE la SIGUIENTE pregunta en secuencia lógica.
           - Debe ser UNA SOLA pregunta
           - Si hay opciones, muestra solo las relevantes para la respuesta anterior
           - NO muestres todo el cuestionario
           - NO adelantes información de pasos futuros
        
        4. Añade una breve explicación de por qué esta información es importante.
        
        5. Este formato debe seguirse ESTRICTAMENTE en cada interacción.
        """

        # Formateamos la entrada para guiar al modelo
        user_message = f"""
        Respuesta del usuario: {request.message}
        
        IMPORTANTE: Procesa esta respuesta y sigue con la SIGUIENTE pregunta del cuestionario, manteniendo un flujo de UNA SOLA PREGUNTA A LA VEZ.
        """

        response = client.responses.create(
            model="gpt-4o-mini",
            instructions=instructions,
            input=user_message,
            previous_response_id=request.conversation_id,
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [VECTOR_STORE_ID],
                    "max_num_results": 3,
                }
            ],
            store=True,
            temperature=0.2,  # Temperatura baja para comportamiento más determinista
        )

        print(f"Respuesta generada: {response.id}")

        return {"id": response.id, "message": response.output_text}
    except Exception as e:
        print(f"Error al procesar mensaje: {e}")
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

        # En una implementación real, aquí procesaríamos el archivo
        # Por ahora, solo respondemos con un mensaje genérico

        response = client.responses.create(
            model="gpt-4o-mini",
            input=f"El usuario ha subido un archivo llamado {file.filename} de {file_size} bytes. Mensaje: {message}",
            previous_response_id=conversation_id,
            tools=[{"type": "file_search", "vector_store_ids": [VECTOR_STORE_ID]}],
            store=True,
        )

        return {"success": True, "id": response.id, "message": response.output_text}
    except Exception as e:
        print(f"Error al procesar documento: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
