from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime
import uuid


class AnalyticsEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event: str
    timestamp: datetime = Field(default_factory=datetime.now)
    url: Optional[str] = None
    properties: Dict[str, Any] = {}

    @classmethod
    def create(
        cls, event: str, url: str = None, properties: Dict[str, Any] = None
    ) -> "AnalyticsEvent":
        """Crea un nuevo evento de analítica"""
        return cls(event=event, url=url, properties=properties or {})


class AnalyticsEventCreate(BaseModel):
    event: str
    timestamp: Optional[datetime] = None
    url: Optional[str] = None
    properties: Dict[str, Any] = {}
