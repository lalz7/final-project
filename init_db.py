import asyncio
from app.core.database import engine, Base
from app.models.event_log import EventLog
from app.models.device import Device

async def init_models():
    async with engine.begin() as conn:       
        print("🛠️  Memperbarui Struktur Database (Devices & Events)...")
        
        # SQLAlchemy akan melihat model yang di-import di atas dan membuat tabelnya
        await conn.run_sync(Base.metadata.create_all)
        
        print("✅ Database siap! Tabel 'devices' dan 'events' telah dicek/dibuat.")

if __name__ == "__main__":
    asyncio.run(init_models())