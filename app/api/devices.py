from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from app.core.database import get_db
from app.models.device import Device
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse
from app.services.sdk_driver import driver_instance

router = APIRouter()

# 1. GET ALL
@router.get("/", response_model=List[DeviceResponse])
async def get_devices(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device))
    return result.scalars().all()

# 2. CREATE (POST)
@router.post("/", response_model=DeviceResponse)
async def create_device(device_in: DeviceCreate, db: AsyncSession = Depends(get_db)):
    # Cek IP Duplikat
    existing = await db.execute(select(Device).where(Device.ip_address == device_in.ip_address))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Device dengan IP ini sudah ada.")

    # Coba Login SDK
    success = driver_instance.login(
        device_in.ip_address, device_in.username, device_in.password, device_in.port
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Gagal Login ke Device. Cek koneksi/password.")

    # Simpan DB
    new_device = Device(**device_in.dict())
    db.add(new_device)
    await db.commit()
    await db.refresh(new_device)
    return new_device

# 3. GET ONE
@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

# 4. UPDATE (PUT) - [FITUR BARU]
@router.put("/{device_id}", response_model=DeviceResponse)
async def update_device(device_id: int, device_in: DeviceUpdate, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Ambil data lama untuk logout
    old_ip = device.ip_address

    # Update field di object database
    update_data = device_in.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(device, key, value)

    # Re-Connect Logic
    # 1. Logout sesi lama
    driver_instance.logout(old_ip)
    
    # 2. Login sesi baru (jika aktif)
    if device.is_active:
        success = driver_instance.login(
            device.ip_address, device.username, device.password, device.port
        )
        if not success:
            # Opsional: Tetap simpan tapi kasih warning, atau batalkan?
            # Di sini kita tetap simpan tapi status koneksi di log akan error.
            print(f"⚠️ [API] Device updated but failed to reconnect: {device.ip_address}")

    await db.commit()
    await db.refresh(device)
    return device

# 5. DELETE
@router.delete("/{device_id}")
async def delete_device(device_id: int, db: AsyncSession = Depends(get_db)):
    device = await db.get(Device, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Logout SDK
    driver_instance.logout(device.ip_address)
    
    await db.delete(device)
    await db.commit()
    return {"message": "Device deleted"}