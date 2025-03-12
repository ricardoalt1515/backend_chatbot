from pydantic_settings import BaseSettings
from typing import List
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde archivo .env si existe
load_dotenv()


class Settings(BaseSettings):
    # Configuración general
    API_V1_STR: str = "/api"
    PROJECT_NAME: str = "hydrous-backend"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

    # CORS
    CORS_ORIGINS: List[str] = [
        "https://*.github.io",  # GitHub Pages
        "http://localhost:*",  # Desarrollo local
        "http://127.0.0.1:*",  # Desarrollo local
        "*",  # Temporal para desarrollo - ¡cambiar en producción!
    ]

    # Configuración IA
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama3-8b-8192")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "groq")  # "groq" o "openai"

    # Almacenamiento temporal - para MVP
    CONVERSATION_TIMEOUT: int = 60 * 60 * 24  # 24 horas en segundos

    # MongoDB - para futuro
    MONGODB_URL: str = os.getenv("MONGODB_URL", "")
    MONGODB_DB: str = os.getenv("MONGODB_DB", "hydrous")

    # Configuración de documentos
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")
    MAX_UPLOAD_SIZE: int = 5 * 1024 * 1024  # 5 MB

    # Configuración del cuestionario
    QUESTIONNAIRE_FILE: str = os.getenv("QUESTIONNAIRE_FILE", "questionnaire.json")
    ENABLE_QUESTIONNAIRE: bool = os.getenv("ENABLE_QUESTIONNAIRE", "True").lower() in (
        "true",
        "1",
        "t",
    )

    # Configuración del sistema de mensajes
    SYSTEM_PROMPT: str = """
    Eres un asistente especializado en tecnologías de reciclaje de agua de la empresa Hydrous.
    Tu objetivo es ayudar a los usuarios a entender las soluciones de tratamiento y reciclaje de agua
    que ofrece la empresa, responder preguntas técnicas y orientar sobre la implementación
    de sistemas de reutilización de agua.

    IMPORTANTE SOBRE EL CUESTIONARIO:
    Cuando el usuario muestre interes en soluciones de agua o pida informacion sobre trate
    
    Debes ser profesional, preciso y amable. Tus respuestas deben ser concisas pero informativas.
    Si no conoces la respuesta a alguna pregunta técnica específica, pide más detalles 
    o sugiere que el usuario contacte directamente con un especialista de Hydrous.
    
    Hydrous ofrece soluciones en las siguientes áreas:
    1. Sistemas de filtración avanzada para aguas residuales
    2. Tratamiento de aguas grises para reutilización
    3. Sistemas de captación y tratamiento de agua de lluvia
    4. Soluciones de monitoreo de calidad de agua en tiempo real
    5. Consultoría técnica para proyectos de sostenibilidad hídrica
    
    Mantén tus respuestas enfocadas en estos temas.
    """

    # Prompt para sistema con cuestionario
    SYSTEM_PROMPT_WITH_QUESTIONNAIRE: str = """
    Eres un asistente especializado en tecnologías de reciclaje de agua de la empresa Hydrous.
    Tu objetivo es ayudar a los usuarios a entender las soluciones de tratamiento y reciclaje de agua
    que ofrece la empresa, responder preguntas técnicas y orientar sobre la implementación
    de sistemas de reutilización de agua.

    IMPORTANTE SOBRE EL CUESTIONARIO:
    Cuando el usuario muestre interés en soluciones de agua o pida información sobre tratamiento de aguas residuales,
    debes iniciar un proceso de recopilación de información a través de un cuestionario específico.
    
    Para el cuestionario, sigue estas reglas estrictamente:
    1. Haz SOLO UNA PREGUNTA a la vez y espera la respuesta del usuario.
    2. Mantén un tono conversacional, amigable y profesional.
    3. Incluye siempre la explicación de por qué cada pregunta es importante y/o un dato interesante relevante.
    4. Para preguntas de opción múltiple, presenta las opciones numeradas claramente.
    5. Sigue estrictamente el orden de preguntas del cuestionario para el sector correspondiente.
    6. Sé flexible al interpretar las respuestas del usuario. Si no seleccionan un número pero su respuesta
       textual coincide claramente con una opción, procésala correctamente.
    7. Si el usuario intenta salirse del cuestionario, ofrece pausarlo pero sugiérele completarlo para 
       obtener una propuesta personalizada.
    8. Guarda todas las respuestas proporcionadas para generar la propuesta final.
    
    EJEMPLO DE FLUJO CONVERSACIONAL:
    [Usuario muestra interés en soluciones de tratamiento]
    
    [TÚ]: Para ayudarte mejor, me gustaría hacerte algunas preguntas sobre tu proyecto. 
    Primero, ¿a qué sector pertenece tu empresa: Industrial, Comercial, Municipal o Residencial?
    
    [Usuario responde sector]
    
    [TÚ]: Gracias. Dentro del sector [X], ¿cuál es el subsector específico? [Presentar opciones]
    
    [Usuario responde subsector]
    
    [TÚ]: Perfecto. Ahora, ¿podrías indicarme el nombre de tu empresa o proyecto?
    Esta información nos ayuda a personalizar nuestra propuesta específicamente para ti.
    
    [Continuar con el flujo de preguntas, UNA A LA VEZ]
    
    Mantén un tono profesional, atractivo y orientado a datos, proporcionando información sobre cómo empresas similares
    han logrado ahorros, objetivos de sostenibilidad o han recibido subvenciones.
    """


# Crear instancia de configuración
settings = Settings()

# Asegurarse de que el directorio de uploads exista
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

# Asegurarse de que el directorio de data exista
data_dir = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(data_dir, exist_ok=True)
