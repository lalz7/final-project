import asyncio
import base64
import os
import uuid  
import httpx
from datetime import datetime, timedelta
from sqlalchemy.future import select
from app.core.database import AsyncSessionLocal
from app.models.event_log import EventLog
from app.models.device import Device
from app.services.isapi_driver import ISAPIDriver
from app.services.sdk_driver import driver_instance

class Middleware:
    def __init__(self):
        # Daftarkan fungsi handle_realtime_event ke SDK Driver
        print("🔗 [MIDDLEWARE] Mendaftarkan Handler ke SDK Driver...")
        driver_instance.set_global_handler(self.handle_realtime_event)

    async def get_device_info_by_ip(self, session, ip_address):
        try:
            result = await session.execute(select(Device).where(Device.ip_address == ip_address))
            device_obj = result.scalars().first()
            if device_obj:
                return device_obj.name, device_obj.target_api
            return ip_address, None
        except Exception as e:
            print(f"⚠️ [DB] Gagal lookup device info: {e}")
            return ip_address, None

    async def send_webhook(self, target_url, payload):
        if not target_url: return
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(target_url, json=payload)
                if resp.status_code != 200 and resp.status_code != 201:
                    print(f"⚠️ [WEBHOOK] Gagal: {resp.status_code} - {resp.text[:50]}")
            except Exception as e:
                print(f"❌ [WEBHOOK] Error Connection: {e}")

    async def save_event_to_db(self, data: dict):
        if not data.get('authId'): return

        async with AsyncSessionLocal() as session:
            try:
                # 1. Cari Info Device
                device_name, target_api = await self.get_device_info_by_ip(session, data['device'])

                # 2. Cek Duplikasi
                q_dup = select(EventLog.id).where(
                    EventLog.device == device_name,
                    EventLog.auth_id == data['authId'],
                    EventLog.date == data['date'] 
                )
                res_dup = await session.execute(q_dup)
                if res_dup.scalars().first():
                    return

                # 3. Simpan ke Database Lokal
                new_event = EventLog(
                    device=device_name,
                    auth_id=data['authId'],
                    date=data['date'],
                    picture_path=data['picture'],
                    temperature=data.get('temperature', 0.0),
                    source=data['source']
                )
                
                session.add(new_event)
                await session.commit()
                
                temp_str = f"| 🌡️ {data.get('temperature')}" if data.get('temperature') else ""
                print(f"💾 [DB] Tersimpan: {device_name} | User {data['authId']} {temp_str} | Src: {data['source']}")

                # 4. Proses Webhook
                if target_api:
                    image_base64 = None
                    if data['picture'] and os.path.exists(data['picture']):
                        try:
                            with open(data['picture'], "rb") as img_file:
                                image_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                        except Exception as img_err:
                            print(f"⚠️ [IMG] Gagal convert base64: {img_err}")

                    webhook_payload = {
                        "device": device_name,
                        "authId": data['authId'],
                        "date": data['date'],
                        "picture": image_base64,
                        "temperature": data.get('temperature', 0.0)
                    }
                    asyncio.create_task(self.send_webhook(target_api, webhook_payload))

            except Exception as e:
                print(f"❌ [DB] Gagal Simpan Event: {e}")
                await session.rollback()

    async def run_catchup(self):
        """
        Fungsi Catch-up: Mengambil log 1 JAM TERAKHIR + DOWNLOAD GAMBAR.
        """
        print("🔄 [MIDDLEWARE] Menjalankan Catch-up (1 Jam Terakhir)...")
        now = datetime.now()
        start = now - timedelta(hours=1) 
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Device).where(Device.is_active == True))
            active_devices = result.scalars().all()

            if not active_devices:
                print("   (Tidak ada device aktif untuk catch-up)")
                return

            for dev in active_devices:
                temp_driver = ISAPIDriver(ip=dev.ip_address, port=dev.port, user=dev.username, password=dev.password)
                
                try:
                    events = await temp_driver.get_events(start, now)
                    
                    if events:
                        print(f"   📥 {dev.name}: Ditarik {len(events)} log mentah. Memproses...")
                        for e in events:
                            raw_time = e.get("time", "")
                            clean_date = raw_time[:19] 
                            final_picture_path = None
                            pic_url = e.get("pictureURL")
                            
                            if pic_url:
                                img_bytes = await temp_driver.get_picture(pic_url)
                                if img_bytes:
                                    filename = f"catchup_{uuid.uuid4().hex[:8]}.jpg"
                                    os.makedirs("static/images", exist_ok=True)
                                    full_path = f"static/images/{filename}"
                                    
                                    try:
                                        with open(full_path, "wb") as f:
                                            f.write(img_bytes)
                                        final_picture_path = full_path
                                    except Exception as err:
                                        print(f"   ⚠️ Gagal tulis URL: {err}")

                            mapped_data = {
                                "device": dev.ip_address,       
                                "authId": e.get("employeeNoString", "Unknown"), 
                                "date": clean_date,      
                                "picture": final_picture_path,
                                "temperature": 0.0,             
                                "source": "CATCHUP"             
                            }
                            await self.save_event_to_db(mapped_data)

                except Exception as e:
                    print(f"   ❌ Gagal catch-up {dev.name}: {e}")
                finally:
                    await temp_driver.close()

        print("✅ [MIDDLEWARE] Catch-up Selesai.")

    def handle_realtime_event(self, event_data):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            loop.create_task(self.save_event_to_db(event_data))
        else:
            loop.run_until_complete(self.save_event_to_db(event_data))

# Instansiasi Global
middleware = Middleware()