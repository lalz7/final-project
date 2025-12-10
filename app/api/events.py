from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import List
from datetime import datetime

from app.core.database import get_db
from app.models.event_log import EventLog
from app.schemas.event import EventLogResponse

router = APIRouter()

# --- [Endpoint Statistik Tetap Ada] ---
@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    q_events = select(func.count(EventLog.id)).where(EventLog.date.like(f"{today_str}%"))
    result_events = await db.execute(q_events)
    events_today = result_events.scalar() or 0

    q_people = select(func.count(func.distinct(EventLog.auth_id))).where(EventLog.date.like(f"{today_str}%"))
    result_people = await db.execute(q_people)
    people_today = result_people.scalar() or 0

    return {
        "events_today": events_today,
        "people_today": people_today
    }

# --- [MODIFIKASI DI SINI] ---
# Sebelumnya: get_recent_events (Limit 50)
# Sekarang: get_today_events (Semua event hari ini)

@router.get("/", response_model=List[EventLogResponse])
async def get_events(db: AsyncSession = Depends(get_db)):
    """
    Mengambil semua event yang terjadi HARI INI.
    """
    # 1. Ambil tanggal hari ini dalam format string "YYYY-MM-DD"
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 2. Query filter menggunakan LIKE 'YYYY-MM-DD%'
    #    Ini akan mencocokkan semua waktu mulai dari 00:00:00 sampai 23:59:59 hari ini.
    query = select(EventLog).where(
        EventLog.date.like(f"{today_str}%")
    ).order_by(EventLog.id.desc()) # Tetap urutkan dari yang paling baru
    
    result = await db.execute(query)
    return result.scalars().all()