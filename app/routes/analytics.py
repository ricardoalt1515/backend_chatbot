from fastapi import APIRouter, HTTPException, BackgroundTasks
import logging
from typing import List, Optional

from app.models.analytics import AnalyticsEvent, AnalyticsEventCreate
from app.services.storage_service import storage_service

logger = logging.getLogger("hydrous-backend")

router = APIRouter()


@router.post("/event", status_code=202)
async def log_event(event: AnalyticsEventCreate, background_tasks: BackgroundTasks):
    """
    Registra un evento de analítica.
    Se procesa en segundo plano para no bloquear al cliente.
    """
    try:
        # Crear evento
        analytics_event = AnalyticsEvent(
            event=event.event,
            timestamp=event.timestamp or None,
            url=event.url,
            properties=event.properties,
        )

        # Almacenar en segundo plano
        background_tasks.add_task(
            storage_service.store_analytics_event, analytics_event
        )

        return {"status": "accepted"}
    except Exception as e:
        logger.error(f"Error al registrar evento: {str(e)}")
        # No devolvemos error al cliente para no bloquear la interfaz
        # Simplemente registramos el error y devolvemos éxito
        return {"status": "accepted"}


@router.get("/events", response_model=List[AnalyticsEvent])
async def get_events(limit: Optional[int] = 100):
    """
    Obtiene los eventos de analítica más recientes.
    Solo disponible para administradores (se implementará autenticación en versiones futuras).
    """
    try:
        events = await storage_service.get_recent_analytics(limit)
        return events
    except Exception as e:
        logger.error(f"Error al obtener eventos: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Error al obtener eventos de analítica"
        )
