import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path

# Obtener el directorio base del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = BASE_DIR / "logs"

# Crear el directorio de logs si no existe
os.makedirs(LOG_DIR, exist_ok=True)

# Configurar el formato de los logs
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Configurar el handler para archivos
file_handler = RotatingFileHandler(
    LOG_DIR / "hydrous_backend.log", maxBytes=10485760, backupCount=5  # 10MB
)
file_handler.setFormatter(formatter)

# Configurar el handler para la consola
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Configurar el logger raíz
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Obtener un logger configurado para un módulo específico"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    return logger
