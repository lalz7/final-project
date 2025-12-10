import asyncio
from app.core.database import engine, Base
from app.models.device import Device
from app.models.event_log import EventLog

async def init_models():
    async with engine.begin() as conn:
        # Hapus tabel lama (opsional, biar bersih)
        # await conn.run_sync(Base.metadata.drop_all)
        
        # Buat tabel baru sesuai definisi Model di atas
        print("🔄 Membuat tabel database...")
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Tabel berhasil dibuat!")

if __name__ == "__main__":
    asyncio.run(init_models())