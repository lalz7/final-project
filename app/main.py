from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from sqlalchemy.future import select
import os

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.device import Device
from app.api import devices, events, users
from app.services.sdk_driver import driver_instance
from app.services.middleware import middleware 

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
    # Menyajikan file HTML yang ada di folder static
    return FileResponse("static/tester.html")