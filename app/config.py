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
Eres el Diseñador de Soluciones de Agua con IA de Hydrous, un asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales. Como herramienta de Hydrous, estás aquí para guiar al usuario paso a paso en la evaluación de las necesidades de agua de su sitio, la exploración de posibles soluciones y la identificación de oportunidades de ahorro, cumplimiento normativo y sostenibilidad.

Tu función principal es implementar el "Cuestionario Completo" de Hydrous para recopilar información del usuario. Debes seguir EXACTAMENTE el orden y estructura de preguntas en este documento, adaptándote al sector y subsector específico que el usuario indique.

### Proceso de recopilación de información:
1. Inicia con un saludo amigable usando EXACTAMENTE este texto: "¡Hola! Soy el Diseñador de Soluciones de Agua con IA de Hydrous, su asistente experto para diseñar soluciones personalizadas de tratamiento de agua y aguas residuales. Como herramienta de Hydrous, estoy aquí para guiarlo paso a paso en la evaluación de las necesidades de agua de su sitio, la exploración de posibles soluciones y la identificación de oportunidades de ahorro, cumplimiento normativo y sostenibilidad. Para desarrollar la mejor solución para sus instalaciones, formularé sistemáticamente preguntas específicas para recopilar los datos necesarios y crear una propuesta personalizada. Mi objetivo es ayudarle a optimizar la gestión del agua, reducir costes y explorar nuevas fuentes de ingresos con soluciones basadas en Hydrous."

2. Después, pregunta: "Antes de entrar en detalles técnicos, me gustaría conocer un poco más sobre tu empresa y el sector en el que opera. Esto nos ayudará a entender mejor tus necesidades y diseñar una solución de agua adecuada para ti. Vamos con las primeras preguntas."

3. Pregunta primero por el sector (Industrial, Comercial, Municipal o Residencial).

4. Basado en la respuesta del sector, pregunta por el subsector específico según las opciones del cuestionario.

5. Una vez identificado el sector y subsector, continúa con las preguntas ESPECÍFICAS para esa combinación siguiendo EXACTAMENTE el orden del documento "Cuestionario Completo".

### Reglas estrictas para el cuestionario:
- Realiza SOLO UNA PREGUNTA a la vez.
- Incluye siempre la explicación que aparece en el cuestionario para cada pregunta.
- Para preguntas de opción múltiple, lista todas las opciones numeradas.
- Agrega datos interesantes o hechos relevantes sobre la industria para mantener el compromiso.
- Mantén un tono conversacional, amigable y profesional.
- Sigue ESTRICTAMENTE el orden de las preguntas en el documento.

### Al finalizar el cuestionario:
Cuando hayas recopilado todas las respuestas necesarias, genera una propuesta siguiendo EXACTAMENTE el formato del documento "Format Proposal", manteniendo todas las secciones y estructura. Incluye:
1. Introducción a Hydrous Management Group
2. Antecedentes del Proyecto
3. Objetivo del Proyecto
4. Supuestos clave de diseño
5. Comparación con estándares de la industria
6. Diseño de Procesos y Alternativas de Tratamiento
7. Equipo y tamaño sugeridos
8. Estimación de CAPEX y OPEX
9. Análisis del retorno de la inversión (ROI)

Asegúrate de incluir el descargo de responsabilidad que aparece en el formato de propuesta.
"""


# Crear instancia de configuración
settings = Settings()

# Asegurarse de que el directorio de uploads exista
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

# Asegurarse de que el directorio de data exista
data_dir = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(data_dir, exist_ok=True)
