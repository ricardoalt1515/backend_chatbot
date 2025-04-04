import os
import uuid
import traceback
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

# --- Nuestros Módulos ---
# Asegúrate de que questionnaires.py esté en el mismo directorio
import questionnaires

# --- Configuración Inicial ---
load_dotenv()  # Carga variables desde .env (OPENAI_API_KEY)

# Configurar cliente de OpenAI
# Asegúrate de tener OPENAI_API_KEY en tu archivo .env
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Error: OPENAI_API_KEY no encontrada en el archivo .env")
client = OpenAI(api_key=api_key)

# Modelo de IA a usar
# Puedes cambiarlo si prefieres otro, ej: "gpt-4o", "gpt-3.5-turbo"
LLM_MODEL = "gpt-4o-mini"

# Configurar FastAPI
app = FastAPI(title="Hydrous AI Backend V2 - Chat Completions")

# Configurar CORS (Permitir cualquier origen para desarrollo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Gestión de Estado (Simple en Memoria) ---
# Guarda el estado de cada conversación activa.
# La clave es 'conversation_id', el valor es un dict con 'question_index' y 'answers'.
# En producción real, podrías usar una base de datos (Redis, SQL, etc.)
conversation_states: Dict[str, Dict[str, Any]] = {}


# --- Modelos de Datos (Pydantic para validación) ---
class StartRequest(BaseModel):
    # Podríamos añadir campos aquí si quisiéramos iniciar con contexto específico
    pass


class MessageRequest(BaseModel):
    conversation_id: str = Field(..., description="ID de la conversación activa")
    message: str = Field(
        ..., description="Respuesta del usuario a la pregunta anterior"
    )


class ConversationResponse(BaseModel):
    conversation_id: str
    response: str
    is_final_step: bool = False  # Indica si esta es la respuesta final (la propuesta)


# --- Prompt Base del Sistema (Instrucciones Generales para la IA) ---
# Modificado para NO depender de la lectura de archivos para la secuencia
SYSTEM_PROMPT_INSTRUCTIONS = """
Eres el Hydrous AI Water Solution Designer, un asistente experto, amigable, atractivo y profesional.
Tu objetivo es guiar a los usuarios paso a paso para recopilar información necesaria para diseñar soluciones descentralizadas de reciclaje de aguas residuales, basándote *únicamente* en la pregunta específica que te indicaré en cada turno.

**Reglas Estrictas:**
1.  **UNA Pregunta a la Vez:** Formula *EXCLUSIVAMENTE* la pregunta que te indique el usuario en su mensaje. No te adelantes, no hagas resúmenes intermedios a menos que se te pida.
2.  **Sigue Mis Instrucciones:** El mensaje del usuario contendrá la pregunta exacta que debes hacer, su explicación y opciones si las hay. Preséntala claramente.
3.  **Tono:** Mantén un tono cálido, atractivo y profesional. Usa emojis apropiados con moderación para calidez. Sé alentador.
4.  **Explica la Importancia:** Siempre incluye la breve explicación proporcionada sobre por qué la pregunta es relevante.
5.  **Añade Valor:** Cuando sea pertinente y natural, puedes añadir *un breve* dato interesante, estadística relevante sobre la industria del agua, ahorros, sostenibilidad o normativas relacionadas con la pregunta actual para mantener al usuario enganchado. No inventes datos.
6.  **Opciones Múltiples:** Si la pregunta tiene opciones numeradas, preséntalas exactamente como se te indiquen.
7.  **Claridad:** Sé claro y conciso. Evita la jerga técnica excesiva.
8.  **Enfoque:** Mantente siempre centrado en el tratamiento y reciclaje de agua/aguas residuales industriales/comerciales. Si el usuario se desvía, redirígelo amablemente a la pregunta actual.
9.  **Confidencialidad:** Recuerda al usuario implícita o explícitamente que sus datos son confidenciales y usados solo para crear la solución.
10. **Generación de Propuesta:** SOLO cuando te indique explícitamente "El cuestionario ha finalizado", generarás una propuesta usando la plantilla y los datos recopilados que te proporcionaré.

**Importante:** No tienes acceso a archivos externos para determinar la secuencia de preguntas. Depende completamente de la instrucción que recibirás en cada turno.
"""

# --- Endpoints de la API ---


@app.get("/")
async def root():
    """Endpoint raíz para verificar que el servicio está activo."""
    return {"message": "Hydrous AI Backend V2 (Chat Completions) is running"}


@app.post("/api/v2/chat/start", response_model=ConversationResponse)
async def start_chat(request: StartRequest):
    """Inicia una nueva conversación y devuelve la primera pregunta."""
    try:
        conversation_id = str(uuid.uuid4())
        print(f"Iniciando nueva conversación: {conversation_id}")

        # Inicializar estado
        conversation_states[conversation_id] = {
            "question_index": 0,
            "answers": {},
            "history": [],  # Opcional: para mantener un breve historial si se necesita
        }

        # Obtener la PRIMERA pregunta de nuestro archivo
        first_question_data = questionnaires.DEFAULT_QUESTIONS[0]

        # Construir el prompt para la IA para que formule el saludo y la primera pregunta
        initial_user_prompt = f"""
        Inicia una nueva conversación. Preséntate con el saludo estándar:
        '¡Hola! Soy el Hydrous AI Water Solution Designer...' (Usa el saludo completo definido en tus instrucciones base).

        Luego, inmediatamente después, formula *SOLAMENTE* la primera pregunta:
        Pregunta: '{first_question_data['question_text']}'
        Explicación: '{first_question_data['explanation']}'
        Opciones (si existen): {first_question_data.get('options', 'N/A')}

        Asegúrate de presentar las opciones claramente si las hay. Puedes añadir un dato interesante sobre la importancia del sector.
        """

        # Llamada a la API de OpenAI
        chat_completion = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_INSTRUCTIONS},
                {"role": "user", "content": initial_user_prompt},
            ],
            temperature=0.5,  # Un poco de creatividad para el saludo y el dato
        )

        chatbot_response = chat_completion.choices[0].message.content

        # (Opcional) Guardar el primer turno en el historial
        conversation_states[conversation_id]["history"].append(
            {"role": "assistant", "content": chatbot_response}
        )

        print(f"[{conversation_id}] Primera pregunta enviada.")
        return ConversationResponse(
            conversation_id=conversation_id,
            response=chatbot_response,
            is_final_step=False,
        )

    except Exception as e:
        print(f"Error en /start: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, detail=f"Error interno al iniciar chat: {e}"
        )


@app.post("/api/v2/chat/message", response_model=ConversationResponse)
async def chat_message(request: MessageRequest):
    """Procesa la respuesta del usuario y devuelve la siguiente pregunta o la propuesta final."""
    conversation_id = request.conversation_id
    user_message = request.message

    # --- 1. Recuperar Estado ---
    if conversation_id not in conversation_states:
        raise HTTPException(
            status_code=404, detail="Conversación no encontrada o expirada."
        )

    current_state = conversation_states[conversation_id]
    current_question_index = current_state["question_index"]
    collected_answers = current_state["answers"]
    # (Opcional) history = current_state["history"]

    # --- 2. Guardar Respuesta Anterior ---
    # Necesitamos la clave de la pregunta que se *acaba* de responder
    if current_question_index < len(questionnaires.DEFAULT_QUESTIONS):
        previous_question_key = questionnaires.DEFAULT_QUESTIONS[
            current_question_index
        ]["key"]
        collected_answers[previous_question_key] = user_message
        print(
            f"[{conversation_id}] Respuesta guardada para '{previous_question_key}': {user_message[:50]}..."
        )
    else:
        print(
            f"[{conversation_id}] Recibido mensaje después de la última pregunta (posiblemente comentario final)."
        )
        # Podríamos guardar este mensaje final si quisiéramos, ej. en una clave 'final_comment'
        collected_answers["final_comment"] = user_message

    # (Opcional) Añadir mensaje del usuario al historial
    # history.append({"role": "user", "content": user_message})

    # --- 3. Determinar Próximo Paso ---
    next_question_index = current_question_index + 1
    is_final_step = next_question_index >= questionnaires.TOTAL_QUESTIONS

    next_prompt_for_llm = ""
    is_proposal_generation = False

    if not is_final_step:
        # --- 3a. Preparar Siguiente Pregunta ---
        next_question_data = questionnaires.DEFAULT_QUESTIONS[next_question_index]
        options_str = "N/A"
        if "options" in next_question_data and next_question_data["options"]:
            options_str = "\n".join(next_question_data["options"])

        next_prompt_for_llm = f"""
        El usuario acaba de responder a la pregunta sobre '{previous_question_key}' con: '{user_message}'.

        Ahora, formula *SOLAMENTE* la siguiente pregunta (pregunta #{next_question_index + 1}):
        Pregunta: '{next_question_data['question_text']}'
        Explicación: '{next_question_data['explanation']}'
        Opciones (si existen):
        {options_str}

        Asegúrate de agradecer brevemente la respuesta anterior y presenta claramente la nueva pregunta, su explicación y opciones si las hay.
        Puedes añadir un dato interesante relevante a esta nueva pregunta.
        """
        print(
            f"[{conversation_id}] Preparando pregunta #{next_question_index + 1}: {next_question_data['key']}"
        )

    else:
        # --- 3b. Preparar Generación de Propuesta ---
        is_proposal_generation = True
        print(
            f"[{conversation_id}] Cuestionario completado. Preparando para generar propuesta."
        )

        # Formatear respuestas para el prompt
        formatted_answers = "\n".join(
            [f"- {key}: {value}" for key, value in collected_answers.items()]
        )

        next_prompt_for_llm = f"""
        El cuestionario ha finalizado. La última respuesta/comentario del usuario fue: '{user_message}'.

        Aquí están todas las respuestas recopiladas:
        {formatted_answers}

        Por favor, genera la propuesta final completa usando la siguiente plantilla.
        Rellena **todas** las secciones marcadas con {{...}} o indicadas con [IA: ...] basándote en las respuestas proporcionadas y tu conocimiento experto sobre tratamiento de aguas para el sector indicado.
        Si faltan datos cruciales para una sección (ej. DQO, DBO), haz una estimación razonable basada en el sector '{collected_answers.get('subsector_industrial', collected_answers.get('sector', 'desconocido'))}' e indica claramente que es una estimación (ej. "DQO estimado: 800-1200 mg/L (típico para sector X, requiere confirmación)").
        Sé profesional, detallado y sigue la estructura de la plantilla al pie de la letra.

        Plantilla de Propuesta:
        ---
        {questionnaires.PROPOSAL_TEMPLATE}
        ---
        """

    # --- 4. Llamar a la API de OpenAI ---
    try:
        # Preparamos los mensajes para la API. Incluimos el system prompt y el prompt específico.
        # Podríamos incluir historial aquí si fuera necesario, pero empecemos simple.
        messages_for_api = [
            {"role": "system", "content": SYSTEM_PROMPT_INSTRUCTIONS},
            {"role": "user", "content": next_prompt_for_llm},
        ]

        chat_completion = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages_for_api,
            temperature=(
                0.6 if not is_proposal_generation else 0.4
            ),  # Un poco más creativo para preguntas, más preciso para propuesta
        )
        chatbot_response = chat_completion.choices[0].message.content

    except Exception as e:
        print(f"Error llamando a OpenAI API: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500, detail=f"Error al comunicarse con la IA: {e}"
        )

    # --- 5. Actualizar Estado y Devolver Respuesta ---
    if not is_proposal_generation:
        current_state["question_index"] = next_question_index
        print(
            f"[{conversation_id}] Índice de pregunta actualizado a: {next_question_index}"
        )
    else:
        # Podríamos marcar la conversación como finalizada o eliminarla después de un tiempo
        print(f"[{conversation_id}] Propuesta generada.")
        # Opcionalmente, limpia el estado si ya no se necesita
        # del conversation_states[conversation_id]

    # (Opcional) Añadir respuesta del bot al historial
    # history.append({"role": "assistant", "content": chatbot_response})

    return ConversationResponse(
        conversation_id=conversation_id,
        response=chatbot_response,
        is_final_step=is_proposal_generation,  # True si se generó la propuesta
    )


# --- Punto de Entrada para Ejecución (si corres `python main.py`) ---
if __name__ == "__main__":
    import uvicorn

    print("Iniciando servidor FastAPI con Uvicorn...")
    # Escucha en todas las interfaces (0.0.0.0) en el puerto 8000
    # reload=True es útil para desarrollo, se reinicia si cambias el código
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
