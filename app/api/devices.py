from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from app.core.database import get_db
from app.models.device import Device
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse
from app.services.sdk_driver import driver_instance

router = APIRouter()

# 1. GET ALL (Dengan Realtime Check)
@router.get("/", response_model=List[DeviceResponse])
async def get_devices(db: AsyncSession = Depends(get_db)):
    # Ambil semua data device dari database
    result = await db.execute(select(Device))
    devices_db = result.scalars().all()
    
    # List untuk menampung respon akhir
    devices_response = []
    
    for dev in devices_db:
        # Konversi object SQLAlchemy ke Pydantic Model
        dev_data = DeviceResponse.from_orm(dev)
        
        # Logika Cek Status Realtime
        # Jika di DB 'is_active' = True, kita cek koneksi fisiknya (Ping Socket)
        # Jika 'is_active' = False, otomatis kita anggap offline.
        if dev.is_active:
            is_connected = driver_instance.check_online(dev.ip_address, dev.port)
            dev_data.is_online = is_connected
        else:
            dev_data.is_online = False
            
        devices_response.append(dev_data)
        
    return devices_response

# 2. CREATE (POST)
@router.post("/", response_model=DeviceResponse)
async def create_device(device_in: DeviceCreate, db: AsyncSession = Depends(get_db)):
    # Validasi IP Duplikat
    existing = await db.execute(select(Device).where(Device.ip_address == device_in.ip_address))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Device dengan IP ini sudah ada.")

    # Coba Login ke Device (Validasi Koneksi di Awal)
    success = driver_instance.login(
        device_in.ip_address, device_in.username, device_in.password, device_in.port
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Gagal Login ke Device. Periksa IP/Port/Password.")

    # Simpan ke Database
    new_device = Device(**device_in.dict())
    db.add(new_device)
    await db.commit()
    await db.refresh(new_device)
    
    # Set status online true karena baru saja berhasil login
    new_device.is_online = True 
    return new_device

# 3. GET ONE
@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Cek realtime untuk single device juga
    if device.is_active:
        device.is_online = driver_instance.check_online(device.ip_address, device.port)
    else:
        device.is_online = False
        
    return device

# 4. UPDATE (PUT) - STRICT MODE
@router.put("/{device_id}", response_model=DeviceResponse)
async def update_device(device_id: int, device_in: DeviceUpdate, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Simpan IP lama untuk keperluan logout
    old_ip = device.ip_address

    # Update atribut object secara lokal (belum commit ke DB)
    update_data = device_in.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(device, key, value)

    # Re-Connect Logic
    # 1. Logout sesi lama
    if old_ip:
        driver_instance.logout(old_ip)
    
    # 2. Coba Login dengan kredensial BARU
    # Jika device diset aktif, kita WAJIB bisa login. Jika gagal, tolak update.
    if device.is_active:
        print(f"🔄 [API] Reconnecting {device.ip_address}...")
        success = driver_instance.login(
            device.ip_address, device.username, device.password, device.port
        )
        if not success:
            # [STRICT] Raise Error 400. 
            # Transaksi DB otomatis rollback, data lama aman.
            raise HTTPException(
                status_code=400, 
                detail="Gagal Koneksi! Periksa IP, Username, atau Password."
            )

    # Jika lolos login (atau device diset non-aktif), simpan ke DB.
    await db.commit()
    await db.refresh(device)
    
    # Update status online di respon
    device.is_online = True if device.is_active else False
    return device

# 5. DELETE
@router.delete("/{device_id}")
async def delete_device(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Logout SDK sebelum hapus
    driver_instance.logout(device.ip_address)
    
    await db.delete(device)
    await db.commit()
    return {"message": "Device deleted"}