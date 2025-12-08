from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class EventLogResponse(BaseModel):
    id: int
    device: str
    auth_id: str
    date: str
    picture_path: Optional[str] = None
    temperature: float = 0.0
    mask: str = "Unknown"
    source: str
    created_at: datetime

    class Config:
        from_attributes = True # Agar bisa membaca objek SQLAlchemy