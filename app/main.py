import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from sqlalchemy.future import select
from datetime import datetime, timedelta
import os

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.device import Device
from app.api import devices, events, users
from app.services.sdk_driver import driver_instance
from app.services.middleware import middleware 

# [REVISI] Scheduler Pintar (Sync ke Menit 00)
async def periodic_catchup_task():
    """
    Menjalankan proses catch-up tepat setiap pergantian jam (XX:00:00).
    Contoh: 08:00, 09:00, 10:00...
    """
    while True:
        now = datetime.now()
        
        # 1. Hitung target waktu jam berikutnya (Menit 0, Detik 0)
        # Jika sekarang 10:15, targetnya 11:00
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        
        # 2. Hitung berapa detik harus tidur
        sleep_seconds = (next_hour - now).total_seconds()
        
        print(f"⏰ [SCHEDULER] Menunggu {int(sleep_seconds)} detik sampai jam {next_hour.strftime('%H:%M')} untuk Catch-up...")
        
        # 3. Tidur sampai waktu target tercapai
        await asyncio.sleep(sleep_seconds)
        
        # 4. Jalankan Catch-up
        try:
            print(f"🕒 [SCHEDULER] Memulai Catch-up Jam {datetime.now().strftime('%H:%M')}")
            await middleware.run_catchup()
        except Exception as e:
            print(f"⚠️ [SCHEDULER] Error saat catch-up: {e}")
        
        # 5. Beri jeda sedikit (misal 5 detik) agar tidak double-run di detik yang sama, 
        # lalu loop akan hitung jam berikutnya lagi.
        await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 [SYSTEM] Starting Up Intelligent Middleware...")
    
    os.makedirs("static/images", exist_ok=True)

    print("🔄 [SYSTEM] Loading Devices from Database...")
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(Device).where(Device.is_active == True))
            active_devices = result.scalars().all()
            
            count = 0
            for dev in active_devices:
                print(f"   ➥ Connecting to: {dev.name} ({dev.ip_address})")
                success = driver_instance.login(dev.ip_address, dev.username, dev.password, dev.port)
                if success: count += 1
                
            print(f"✅ [SYSTEM] Connected to {count} devices.")
        except Exception as e:
            print(f"⚠️ [SYSTEM] Gagal load device: {e}")

    # [BARU] Jalankan Catch-up Awal (Saat aplikasi baru nyala)
    print("🔄 [SYSTEM] Menjalankan Initial Catch-up...")
    asyncio.create_task(middleware.run_catchup())

    # [BARU] Jalankan Scheduler Presisi
    asyncio.create_task(periodic_catchup_task())

    yield
    print("🛑 [SYSTEM] Shutting Down...")

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# --- REGISTER ROUTER ---
app.include_router(devices.router, prefix="/api/devices", tags=["Devices"])
app.include_router(events.router, prefix="/api/events", tags=["Events"]) 
app.include_router(users.router, prefix="/api/users", tags=["Users"])

@app.get("/")
async def root():
    return FileResponse("static/tester.html")