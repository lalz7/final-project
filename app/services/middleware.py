import asyncio
import base64
import os
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
        """
        Mencari Nama Device dan Target API berdasarkan IP Address.
        """
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
        """
        Mengirim payload ke Target API (Tanpa simpan status ke DB).
        """
        if not target_url:
            return

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                # print(f"🚀 [WEBHOOK] Mengirim event ke {target_url}...")
                resp = await client.post(target_url, json=payload)
                if resp.status_code in [200, 201]:
                    # print(f"✅ [WEBHOOK] Sukses: {resp.status_code}")
                    pass
                else:
                    print(f"⚠️ [WEBHOOK] Gagal: {resp.status_code} - {resp.text[:50]}")
            except Exception as e:
                print(f"❌ [WEBHOOK] Error Connection: {e}")

    async def save_event_to_db(self, data: dict):
        """
        Menyimpan event ke database lokal dan memicu pengiriman webhook.
        """
        if not data.get('authId'): 
            return

        async with AsyncSessionLocal() as session:
            try:
                # 1. Cari Info Device
                device_name, target_api = await self.get_device_info_by_ip(session, data['device'])

                # 2. Simpan ke Database Lokal
                new_event = EventLog(
                    device=device_name,
                    auth_id=data['authId'],
                    date=data['date'],
                    picture_path=data['picture'],
                    temperature=data.get('temperature', 0.0),
                    # mask dihapus
                    source=data['source']
                )
                
                session.add(new_event)
                await session.commit()
                
                # Log di terminal
                temp_str = f"| 🌡️ {data.get('temperature')}" if data.get('temperature') else ""
                print(f"💾 [DB] Tersimpan: {device_name} | User {data['authId']} {temp_str} | Src: {data['source']}")

                # 3. Proses Webhook (Jika ada Target API)
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

                    # Kirim Async (Tanpa passing event_id)
                    asyncio.create_task(self.send_webhook(target_api, webhook_payload))

            except Exception as e:
                print(f"❌ [DB] Gagal Simpan Event: {e}")
                await session.rollback()

    async def run_catchup(self):
        """
        Fungsi Catch-up: Mengambil log dari SEMUA perangkat aktif di database.
        """
        print("🔄 [MIDDLEWARE] Menjalankan Catch-up (ISAPI)...")
        now = datetime.now()
        start = now - timedelta(hours=24) 
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Device).where(Device.is_active == True))
            active_devices = result.scalars().all()

            if not active_devices:
                print("   (Tidak ada device aktif untuk catch-up)")
                return

            for dev in active_devices:
                # print(f"   🔎 Cek log tertinggal di: {dev.name}...")
                
                # Inisialisasi Driver ISAPI per device
                temp_driver = ISAPIDriver(ip=dev.ip_address, port=dev.port, user=dev.username, password=dev.password)
                
                try:
                    events = await temp_driver.get_events(start, now)
                    
                    if events:
                        print(f"   📥 Ditemukan {len(events)} log di {dev.name}. Menyimpan...")
                        
                        for e in events:
                            # Mapping Data ISAPI -> App
                            mapped_data = {
                                "device": dev.ip_address,       
                                "authId": e.get("employeeNoString", "Unknown"), 
                                "date": e.get("time", ""),      
                                "picture": None,                
                                "temperature": 0.0,             
                                "source": "CATCHUP"             
                            }
                            await self.save_event_to_db(mapped_data)
                    # else:
                        # print(f"   (Bersih, tidak ada log tertinggal di {dev.name})")

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