from fastapi import APIRouter, BackgroundTasks
import logging
from typing import Dict, Any

router = APIRouter()
logger = logging.getLogger("hydrous")


@router.post("/event")
async def log_event(event: Dict[str, Any], background_tasks: BackgroundTasks):
    """
    Endpoint simplificado para registrar eventos de analítica.
    Solo acepta eventos pero no realiza procesamiento complejo.
    """
    logger.info(f"Evento registrado: {event.get('event', 'desconocido')}")
    return {"status": "accepted"}
