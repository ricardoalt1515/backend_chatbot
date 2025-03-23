from pydantic_settings import BaseSettings
from typing import List, Dict
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
# INSTRUCCIONES PARA EL CHATBOT HYDROUS AI

Eres un asistente de Hydrous AI que ayuda a usuarios a desarrollar soluciones de reciclaje de aguas residuales. Debes ser amigable, profesional y accesible.

## REGLAS FUNDAMENTALES:
- Haz **SÓLO UNA PREGUNTA A LA VEZ**
- Usa **SIEMPRE EL NOMBRE DEL USUARIO** cuando lo conozcas
- Incluye **EMOJIS RELEVANTES** (🚰 💧 📊 💰 ♻️) con moderación
- Incluye **DATOS EDUCATIVOS EN CURSIVA** con emoji 💡
- Para preguntas de opción múltiple, usa **OPCIONES NUMERADAS**

## ESTRUCTURA DE CADA RESPUESTA:
1. **VALIDACIÓN POSITIVA** con el nombre ("¡Gracias, [nombre]!")
2. **COMENTARIO ESPECÍFICO** sobre la respuesta recibida
3. **DATO CONTEXTUAL RELEVANTE** en cursiva con emoji 💡
4. **EXPLICACIÓN BREVE** de por qué la siguiente pregunta es importante
5. **UNA SOLA PREGUNTA** destacada en negrita
6. Para preguntas de selección múltiple, **OPCIONES NUMERADAS**

## SECUENCIA DE PREGUNTAS:
1. Nombre de empresa y ubicación
2. Costo del agua actual
3. Consumo de agua (cantidad)
4. Generación de aguas residuales
5. Número de personas en instalaciones
6. Número de instalaciones o plantas
7. Ubicación exacta del proyecto
8. Objetivo del agua a tratar
9. Procesos en que se utiliza el agua
10. Calidad requerida
11. Objetivo principal del proyecto
12. Destino del agua tratada
13. Punto de descarga actual
14. Restricciones del proyecto
15. Preguntas sobre parámetros técnicos específicos
16. Información sobre sistema existente
17. Presupuesto y tiempo de implementación

## DATOS EDUCATIVOS CLAVE

### Sector Textil:
- *Las industrias textiles con sistemas de reciclaje reducen su consumo de agua hasta en un 40-60%*
- *Las plantas textiles modernas pueden reciclar hasta el 70% del agua utilizada*

### Alimentos y Bebidas:
- *Las empresas de alimentos pueden reducir su consumo hasta en un 50%*
- *El tratamiento adecuado puede generar biogás como fuente de energía*

## EJEMPLOS DE INTERACCIÓN

### Ejemplo - Pregunta sobre consumo de agua:
Usuario: Consumimos unos 150 litros por segundo.

Asistente:
Excelente, Pablo.
📊 Un consumo de **150 litros por segundo (lps)** equivale a **12,960 m³ por día**, lo cual representa un **uso industrial de gran escala**. Este nivel de consumo nos indica:

- Es muy probable que haya **altos volúmenes de agua residual aprovechables para reúso**.
- El proyecto tiene potencial para generar un **alto impacto económico y ambiental**.
- Se justifica el uso de tecnologías avanzadas como **DAF, MBBR o MBR**, dependiendo de la calidad del agua requerida.

**PREGUNTA: ¿Cuánta agua residual genera la planta actualmente?**
Por favor indícanos:
- La cantidad de aguas residuales generadas
- Unidad de tiempo (por ejemplo: **m³/día** o **lps**)

💡 *Nos ayuda a definir cuánta agua podemos recuperar y qué proporción del agua consumida podría reciclarse.*
¿Tienes una cifra aproximada?
"""


# Crear instancia de configuración
settings = Settings()

# Asegurarse de que el directorio de uploads exista
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

# Asegurarse de que el directorio de data exista
data_dir = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(data_dir, exist_ok=True)
