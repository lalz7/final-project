from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
import asyncio

from app.core.database import get_db
from app.models.device import Device
from app.services.isapi_driver import ISAPIDriver

router = APIRouter()

# Helper untuk inisialisasi driver dari object database
def get_driver_for_device(dev: Device) -> ISAPIDriver:
    return ISAPIDriver(
        ip=dev.ip_address,
        port=dev.port,
        user=dev.username,
        password=dev.password
    )

# 1. GET USERS (Live dari Device tertentu)
@router.get("/")
async def get_users_live(ip: str, db: AsyncSession = Depends(get_db)):
    """
    Mengambil daftar user langsung dari device berdasarkan IP yang dikirim.
    """
    # Cari credentials device di database
    result = await db.execute(select(Device).where(Device.ip_address == ip))
    device = result.scalars().first()

    if not device:
        raise HTTPException(status_code=404, detail="Device tidak ditemukan di database. Pastikan device sudah ditambahkan.")

    # Gunakan credentials dari DB
    driver = get_driver_for_device(device)
    
    try:
        users = await driver.get_users()
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal ambil data: {str(e)}")
    finally:
        await driver.close()

# 2. BROADCAST USER (Kirim ke SEMUA Device Aktif)
@router.post("/")
async def broadcast_user(
    employee_no: str = Form(...),
    name: str = Form(...),
    start_time: Optional[str] = Form(None),
    end_time: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Menambahkan user ke SEMUA device yang statusnya Active.
    """
    # 1. Ambil semua device aktif
    result = await db.execute(select(Device).where(Device.is_active == True))
    active_devices = result.scalars().all()
    
    if not active_devices:
        raise HTTPException(status_code=400, detail="Tidak ada device aktif untuk broadcast.")

    report = []
    
    # Baca file foto sekali saja (jika ada)
    photo_bytes = None
    if photo:
        photo_bytes = await photo.read()

    # 2. Loop ke setiap device
    for dev in active_devices:
        driver = get_driver_for_device(dev)
        try:
            # A. Tambah Data User
            success, msg = await driver.add_user(employee_no, name, start_time, end_time)
            status_str = f"[{dev.name}] Data: {'✅' if success else '❌ ' + msg}"
            
            # B. Upload Foto (Jika data user sukses & ada foto)
            if success and photo_bytes:
                # Perlu inisialisasi ulang atau reset client terkadang diperlukan untuk multipart, 
                # tapi dengan httpx async biasanya aman.
                ok_foto, msg_foto = await driver.add_face(employee_no, photo_bytes)
                status_str += f" | Foto: {'✅' if ok_foto else '❌ ' + msg_foto}"
            
            report.append(status_str)
            
        except Exception as e:
            report.append(f"[{dev.name}] Error System: {str(e)}")
        finally:
            await driver.close()

    return {"message": "Broadcast Selesai", "broadcast_report": report}

# 3. DELETE USER (Hapus dari SEMUA Device)
@router.delete("/{employee_no}")
async def delete_user_broadcast(employee_no: str, db: AsyncSession = Depends(get_db)):
    """
    Menghapus user dari SEMUA device aktif.
    """
    result = await db.execute(select(Device).where(Device.is_active == True))
    active_devices = result.scalars().all()
    
    if not active_devices:
        raise HTTPException(status_code=400, detail="Tidak ada device aktif.")

    report = []
    
    for dev in active_devices:
        driver = get_driver_for_device(dev)
        try:
            success, msg = await driver.delete_user(employee_no)
            icon = "✅" if success else "❌"
            report.append(f"[{dev.name}] {icon} {msg}")
        except Exception as e:
            report.append(f"[{dev.name}] Error: {str(e)}")
        finally:
            await driver.close()

    return {"message": "Delete Broadcast Selesai", "report": report}