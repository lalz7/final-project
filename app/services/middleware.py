import asyncio
import base64
import os
import httpx  # Pastikan httpx terinstall (ada di requirements.txt)
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import AsyncSessionLocal
from app.models.event_log import EventLog
from app.models.device import Device
from app.services.isapi_driver import ISAPIDriver
from app.services.sdk_driver import driver_instance

class Middleware:
    def __init__(self):
        self.isapi_driver = ISAPIDriver()
        print("🔗 [MIDDLEWARE] Mendaftarkan Handler ke SDK Driver...")
        driver_instance.set_global_handler(self.handle_realtime_event)

    async def get_device_info_by_ip(self, session, ip_address):
        """
        [MODIFIED] Mengembalikan (name, target_api) berdasarkan IP.
        """
        try:
            result = await session.execute(select(Device).where(Device.ip_address == ip_address))
            device_obj = result.scalars().first()
            if device_obj:
                # Kembalikan Nama dan Target API
                return device_obj.name, device_obj.target_api
            return ip_address, None
        except Exception as e:
            print(f"⚠️ [DB] Gagal lookup device info: {e}")
            return ip_address, None

    async def send_webhook(self, target_url, payload):
        """
        [NEW] Mengirim payload ke Target API secara Asynchronous
        """
        if not target_url:
            return

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                print(f"🚀 [WEBHOOK] Mengirim event ke {target_url}...")
                resp = await client.post(target_url, json=payload)
                if resp.status_code in [200, 201]:
                    print(f"✅ [WEBHOOK] Sukses terkirim: {resp.status_code}")
                else:
                    print(f"⚠️ [WEBHOOK] Gagal: {resp.status_code} - {resp.text[:50]}")
            except Exception as e:
                print(f"❌ [WEBHOOK] Error Connection: {e}")

    async def save_event_to_db(self, data: dict):
        if not data.get('authId'): 
            return

        async with AsyncSessionLocal() as session:
            try:
                # 1. Ambil Nama Device DAN Target API
                device_name, target_api = await self.get_device_info_by_ip(session, data['device'])

                # 2. Simpan ke Database Lokal
                new_event = EventLog(
                    device=device_name,
                    auth_id=data['authId'],
                    date=data['date'],
                    picture_path=data['picture'],
                    temperature=data.get('temperature', 0.0),
                    mask=data.get('mask', 'Unknown'),
                    source=data['source']
                )
                session.add(new_event)
                await session.commit()
                
                temp_info = f" | 🌡️ {data.get('temperature')}°C" if data.get('temperature') else ""
                print(f"💾 [DB] Tersimpan: {device_name} | User {data['authId']} {temp_info}")

                # 3. [NEW] KIRIM KE TARGET API (Jika ada)
                if target_api:
                    # A. Proses Gambar ke Base64
                    image_base64 = None
                    if data['picture'] and os.path.exists(data['picture']):
                        try:
                            # Baca file gambar secara binary
                            with open(data['picture'], "rb") as img_file:
                                image_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                        except Exception as img_err:
                            print(f"⚠️ [IMG] Gagal convert base64: {img_err}")

                    # B. Susun Payload (4 Poin)
                    webhook_payload = {
                        "device": device_name,
                        "authId": data['authId'],
                        "date": data['date'],     # Format sudah ISO dari sdk_driver
                        "picture": image_base64   # String Base64 atau None
                    }

                    # C. Kirim Async (Fire and Forget agar tidak memblokir)
                    # Kita gunakan asyncio.create_task agar berjalan di background
                    asyncio.create_task(self.send_webhook(target_api, webhook_payload))

            except Exception as e:
                print(f"❌ [DB] Gagal Simpan/Kirim: {e}")
                await session.rollback()

    async def run_catchup(self):
        print("🔄 [MIDDLEWARE] Menjalankan Catch-up (ISAPI)...")
        now = datetime.now()
        start = now - timedelta(hours=24) 
        events = await self.isapi_driver.get_events(start, now)
        if events:
            print(f"   📥 Memproses {len(events)} event catch-up...")
            for e in events:
                await self.save_event_to_db(e)
        else:
            print("   (Tidak ada data catch-up baru)")
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

middleware = Middleware()