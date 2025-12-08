from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import asyncio

from app.core.database import get_db
from app.models.device import Device
from app.core.config import settings
from app.services.isapi_driver import ISAPIDriver

router = APIRouter()

# 1. READ USERS (LIVE dari Device)
@router.get("/")
async def get_users_live(ip: str = Query(..., description="IP Device"), db: AsyncSession = Depends(get_db)):
    # Cari Device di DB untuk dapat User/Pass
    result = await db.execute(select(Device).where(Device.ip_address == ip))
    device = result.scalars().first()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device tidak terdaftar")
    
    # Init Driver (Pastikan Port HTTP, default 80 jika tidak ada config khusus)
    # Kita abaikan device.port (8000) karena itu untuk SDK
    http_port = settings.HTTP_PORT 
    
    driver = ISAPIDriver(ip=device.ip_address, port=http_port, user=device.username, password=device.password)
    try:
        users = await driver.get_users()
        return users
    finally:
        await driver.close()

# 2. CREATE / BROADCAST USER
@router.post("/")
async def broadcast_user(
    employee_no: str = Form(...),
    name: str = Form(...),
    start_time: Optional[str] = Form(None),
    end_time: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db)
):
    photo_bytes = await photo.read() if photo else None
    
    # Ambil semua device aktif
    result = await db.execute(select(Device).where(Device.is_active == True))
    devices = result.scalars().all()
    
    report = []
    
    for dev in devices:
        http_port = settings.HTTP_PORT 
        driver = ISAPIDriver(ip=dev.ip_address, port=http_port, user=dev.username, password=dev.password)
        
        try:
            status_msg = ""
            
            # SKENARIO 1: HAPUS DULU (Bersih-bersih)
            # Logic ini meniru app.py: memastikan user bersih sebelum ditimpa
            if photo_bytes:
                await driver.delete_user(employee_no)
                # await asyncio.sleep(0.5) # Opsional: jeda

            # SKENARIO 2: BUAT USER (Record)
            ok, msg = await driver.add_user(employee_no, name, start_time, end_time)
            
            # Jika gagal karena 'sudah ada', lakukan UPDATE (Modify)
            if not ok:
                ok, msg = await driver.update_user(employee_no, name, start_time, end_time)
                status_msg = "Updated Info"
            else:
                status_msg = "Created Info"

            # SKENARIO 3: UPLOAD FOTO
            face_res = ""
            if ok and photo_bytes:
                ok_face, msg_face = await driver.add_face(employee_no, photo_bytes)
                face_res = f" | Face: {'OK' if ok_face else msg_face}"
            
            final_status = "OK" if ok else "Fail"
            report.append(f"{dev.name}: {final_status} ({status_msg}){face_res}")
            
        except Exception as e:
            report.append(f"{dev.name}: Error {e}")
        finally:
            await driver.close()

    return {"message": "Broadcast Selesai", "broadcast_report": report}

# 3. DELETE USER
@router.delete("/{employee_no}")
async def broadcast_delete(employee_no: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.is_active == True))
    devices = result.scalars().all()
    
    report = []
    for dev in devices:
        http_port = settings.HTTP_PORT
        driver = ISAPIDriver(ip=dev.ip_address, port=http_port, user=dev.username, password=dev.password)
        try:
            ok, msg = await driver.delete_user(employee_no)
            report.append(f"{dev.name}: {'Deleted' if ok else msg}")
        finally:
            await driver.close()
            
    return {"message": "Delete Selesai", "broadcast_report": report}