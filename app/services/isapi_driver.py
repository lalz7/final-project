import httpx
import json
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from app.core.config import settings

class ISAPIDriver:
    def __init__(self, ip: str, port: int = 80, user: str = "admin", password: str = "12345"):
        """
        Inisialisasi Driver ISAPI.
        Parameter IP wajib diisi (tidak ada fallback ke config global lagi).
        """
        self.ip = ip
        
        # Logika Port Pintar: Jika port 8000 (SDK), ganti ke default HTTP (80)
        if port == settings.SDK_PORT_DEFAULT: # atau angka 8000
             self.port = settings.HTTP_PORT_DEFAULT
        else:
             self.port = port
            
        self.user = user
        self.password = password
        
        self.base_url = f"http://{self.ip}:{self.port}"
        
        # Setup Authentication
        self.auth = httpx.DigestAuth(self.user, self.password)
        self.client = httpx.AsyncClient(auth=self.auth, timeout=30.0)

    async def close(self):
        await self.client.aclose()

    # ==========================================
    # 1. FITUR LOG / EVENT (CATCH-UP)
    # ==========================================

    async def get_events(self, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """
        Mengambil log absensi (AcsEvent) dalam rentang waktu tertentu.
        """
        url = f"{self.base_url}/ISAPI/AccessControl/AcsEvent?format=json"
        search_id = str(uuid.uuid4())
        
        # Format waktu ISO 8601 (Contoh: 2025-12-08T10:00:00+07:00)
        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%S+07:00")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%S+07:00")

        payload = {
            "AcsEventCond": {
                "searchID": search_id,
                "searchResultPosition": 0,
                "maxResults": 50, # Ambil 50 data per request
                "major": 5,       # Major 5 = Event Access Control
                "minor": 75,      # Minor 75 = Face Authentication Passed
                "startTime": start_str,
                "endTime": end_str
            }
        }

        try:
            print(f"📡 [ISAPI] Request Logs {self.ip}:{self.port}...")
            response = await self.client.post(url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                if "AcsEvent" in data and "InfoList" in data["AcsEvent"]:
                    events = data["AcsEvent"]["InfoList"]
                    print(f"✅ [ISAPI] Diterima {len(events)} event.")
                    return events
                else:
                    print("⚠️ [ISAPI] Tidak ada event (List Kosong).")
                    return []
            else:
                print(f"❌ [ISAPI] Gagal Ambil Event. Status: {response.status_code} | Msg: {response.text}")
                return []

        except Exception as e:
            print(f"❌ [ISAPI] Exception Get Events: {str(e)}")
            return []

    # ==========================================
    # 2. FITUR MANAJEMEN USER (CRUD)
    # ==========================================

    async def get_users(self) -> List[Dict[str, Any]]:
        """
        Mengambil semua user yang terdaftar di perangkat.
        Menggunakan loop pagination untuk mengambil semua data jika lebih dari 30.
        """
        url = f"{self.base_url}/ISAPI/AccessControl/UserInfo/Search?format=json"
        
        all_users = []
        search_id = f"search_{uuid.uuid4()}"
        position = 0
        max_results = 30 # Safe limit per request

        print(f"📡 [ISAPI] Mengambil daftar user dari {self.ip}:{self.port}...")

        try:
            while True:
                payload = {
                    "UserInfoSearchCond": {
                        "searchID": search_id,
                        "searchResultPosition": position,
                        "maxResults": max_results
                    }
                }
                
                response = await self.client.post(url, json=payload)
                
                if response.status_code != 200:
                    print(f"   ⚠️ Gagal di posisi {position}: {response.status_code}")
                    break
                
                data = response.json().get('UserInfoSearch', {})
                users_batch = data.get('UserInfo', [])
                
                if users_batch:
                    all_users.extend(users_batch)
                
                matches = data.get('numOfMatches', 0)
                total_matches = data.get('totalMatches', 0)
                
                position += matches
                
                # Stop jika sudah ambil semua atau batch kosong
                if not users_batch or position >= total_matches:
                    break
            
            print(f"✅ [ISAPI] Total User: {len(all_users)}")
            return all_users
            
        except Exception as e:
            print(f"❌ [ISAPI] Exception Get Users: {str(e)}")
            return []

    async def add_user(self, employee_no, name, start_time=None, end_time=None):
        """
        Menambahkan User Baru (Data Teks).
        Endpoint: POST /ISAPI/AccessControl/UserInfo/Record
        """
        url = f"{self.base_url}/ISAPI/AccessControl/UserInfo/Record?format=json"
        
        # Set default waktu jika kosong
        if not start_time: start_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        if not end_time: end_time = (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%dT%H:%M:%S")

        payload = {
            "UserInfo": {
                "employeeNo": str(employee_no),
                "name": name,
                "userType": "normal",
                "Valid": {
                    "enable": True,
                    "beginTime": start_time,
                    "endTime": end_time,
                    "timeType": "local"
                },
                "doorRight": "1",
                "RightPlan": [{"doorNo": 1, "planTemplateNo": "1"}]
            }
        }
        
        try:
            response = await self.client.post(url, json=payload)
            
            # Cek respon sukses (Hikvision standard: statusCode 1 = OK)
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get('statusCode') == 1:
                    return True, "Sukses"
                else:
                    return False, f"Gagal: {resp_json.get('statusString')}"
            
            return False, f"HTTP {response.status_code}: {response.text}"
            
        except Exception as e:
            return False, f"Ex: {str(e)}"

    async def update_user(self, employee_no, name, start_time=None, end_time=None):
        """
        Update User yang sudah ada.
        Endpoint: PUT /ISAPI/AccessControl/UserInfo/Modify
        """
        url = f"{self.base_url}/ISAPI/AccessControl/UserInfo/Modify?format=json"
        
        if not start_time: start_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        if not end_time: end_time = (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%dT%H:%M:%S")

        payload = {
            "UserInfo": {
                "employeeNo": str(employee_no),
                "name": name,
                "userType": "normal",
                "Valid": {
                    "enable": True,
                    "beginTime": start_time,
                    "endTime": end_time,
                    "timeType": "local"
                },
                "doorRight": "1",
                "RightPlan": [{"doorNo": 1, "planTemplateNo": "1"}]
            }
        }
        
        try:
            response = await self.client.put(url, json=payload)
            
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get('statusCode') == 1:
                    return True, "Sukses Update"
                else:
                    return False, f"Gagal Update: {resp_json.get('statusString')}"
            
            return False, f"HTTP {response.status_code}: {response.text}"
            
        except Exception as e:
            return False, f"Ex: {str(e)}"

    async def delete_user(self, employee_no):
        """
        Menghapus User dari perangkat.
        Endpoint: PUT /ISAPI/AccessControl/UserInfo/Delete
        """
        url = f"{self.base_url}/ISAPI/AccessControl/UserInfo/Delete?format=json"
        
        payload = {
            "UserInfoDelCond": {
                "employeeNoList": [
                    {"employeeNo": str(employee_no)}
                ]
            }
        }
        
        try:
            response = await self.client.put(url, json=payload)
            
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get('statusCode') == 1:
                    return True, "Sukses Hapus"
                else:
                    return False, f"Gagal Hapus: {resp_json.get('statusString')}"
            
            return False, f"HTTP {response.status_code}: {response.text}"
            
        except Exception as e:
            return False, f"Ex: {str(e)}"

    async def add_face(self, employee_no, image_bytes):
        """
        Upload Foto Wajah ke User.
        Endpoint: POST /ISAPI/Intelligent/FDLib/FaceDataRecord
        Format: Multipart Form-Data (JSON Metadata + Binary Image)
        """
        url = f"{self.base_url}/ISAPI/Intelligent/FDLib/FaceDataRecord?format=json"
        
        # 1. Metadata JSON untuk Wajah
        face_info = {
            "faceLibType": "blackFD",
            "FDID": "1",
            "FPID": str(employee_no) # FPID harus sama dengan Employee No
        }
        
        # 2. Siapkan Multipart
        # httpx akan otomatis mengatur boundary dan header Content-Type
        files = {
            'FaceDataRecord': (None, json.dumps(face_info), 'application/json'),
            'FaceImage': (f'{employee_no}.jpg', image_bytes, 'image/jpeg')
        }
        
        try:
            print(f"📸 [ISAPI] Uploading Face for {employee_no}...")
            response = await self.client.post(url, files=files)
            
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get('statusCode') == 1:
                    return True, "Sukses Upload Foto"
                else:
                    error_msg = resp_json.get('subStatusCode', 'Unknown Error')
                    return False, f"Gagal Foto: {error_msg}"
            
            return False, f"HTTP Foto {response.status_code}: {response.text}"
            
        except Exception as e:
            return False, f"Ex Foto: {str(e)}"