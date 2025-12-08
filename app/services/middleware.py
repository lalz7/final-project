import asyncio
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
        # Driver untuk Catch-up (Pull)
        self.isapi_driver = ISAPIDriver()
        
        # [PENTING] Daftarkan Middleware ini sebagai penerima event dari SDK
        # Agar saat ada data masuk dari alat manapun, fungsi handle_realtime_event dipanggil
        print("🔗 [MIDDLEWARE] Mendaftarkan Handler ke SDK Driver...")
        driver_instance.set_global_handler(self.handle_realtime_event)

    async def get_device_name_by_ip(self, session, ip_address):
        """
        Helper: Mencari nama device di database berdasarkan IP.
        Jika tidak ketemu, kembalikan IP-nya saja.
        """
        try:
            result = await session.execute(select(Device).where(Device.ip_address == ip_address))
            device_obj = result.scalars().first()
            if device_obj:
                return device_obj.name
            return ip_address
        except Exception as e:
            print(f"⚠️ [DB] Gagal lookup device name: {e}")
            return ip_address

    async def save_event_to_db(self, data: dict):
        """
        Fungsi sentral untuk menyimpan event ke Database.
        Data dict wajib punya keys: device, authId, date, picture, source
        Opsional: temperature, mask
        """
        # Validasi sederhana: Jangan simpan jika tidak ada ID User
        if not data.get('authId'): 
            return

        async with AsyncSessionLocal() as session:
            try:
                # 1. Ubah IP menjadi Nama Device
                device_name = await self.get_device_name_by_ip(session, data['device'])

                # 2. Buat Objek Event
                new_event = EventLog(
                    device=device_name,      # Simpan Nama, bukan IP
                    auth_id=data['authId'],
                    date=data['date'],
                    picture_path=data['picture'],
                    
                    # Data Kesehatan (Jika ada)
                    temperature=data.get('temperature', 0.0),
                    mask=data.get('mask', 'Unknown'),
                    
                    source=data['source']
                )
                
                session.add(new_event)
                await session.commit()
                
                # Log Sukses
                temp_info = f" | 🌡️ {data.get('temperature')}°C" if data.get('temperature') else ""
                print(f"💾 [DB] Tersimpan: {device_name} | User {data['authId']} | {data['source']}{temp_info}")
                
            except Exception as e:
                print(f"❌ [DB] Gagal Simpan: {e}")
                await session.rollback()

    async def run_catchup(self):
        """
        Menjalankan proses pengambilan data lawas (Catch-up) via ISAPI.
        Biasanya dijalankan saat startup.
        """
        print("🔄 [MIDDLEWARE] Menjalankan Catch-up (ISAPI)...")
        
        now = datetime.now()
        # Tarik data 24 jam terakhir
        start = now - timedelta(hours=24) 
        
        # Panggil driver ISAPI
        events = await self.isapi_driver.get_events(start, now)
        
        if events:
            print(f"   📥 Memproses {len(events)} event catch-up...")
            for e in events:
                await self.save_event_to_db(e)
        else:
            print("   (Tidak ada data catch-up baru)")
        
        print("✅ [MIDDLEWARE] Catch-up Selesai.")

    def handle_realtime_event(self, event_data):
        """
        Callback ini dipanggil otomatis oleh SDK Driver saat ada data masuk.
        Karena SDK berjalan di Thread terpisah (Sync), kita harus 'menitipkan'
        proses simpan ke Database ke dalam Event Loop Asyncio utama.
        """
        # print(f"⚡ [MIDDLEWARE] Event Masuk dari IP: {event_data.get('device')}")
        
        try:
            # Coba dapatkan loop yang sedang berjalan
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Jika tidak ada loop, buat baru
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        # Jadwalkan penyimpanan ke DB
        if loop.is_running():
            loop.create_task(self.save_event_to_db(event_data))
        else:
            loop.run_until_complete(self.save_event_to_db(event_data))

# Inisialisasi Middleware (Single Instance)
middleware = Middleware()