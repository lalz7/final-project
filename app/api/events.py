from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from app.core.database import get_db
from app.models.event_log import EventLog
from app.schemas.event import EventLogResponse

router = APIRouter()

@router.get("/", response_model=List[EventLogResponse])
async def get_recent_events(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """
    Mengambil 50 event terakhir (dari yang terbaru).
    """
    result = await db.execute(
        select(EventLog).order_by(EventLog.id.desc()).limit(limit)
    )
    return result.scalars().all()