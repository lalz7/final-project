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
        """
        self.ip = ip
        
        # Logika Port Pintar
        if port == 8000: 
            self.port = 80
        else:
            self.port = port
            
        self.user = user
        self.password = password
        
        self.base_url = f"http://{self.ip}:{self.port}"
        self.auth = httpx.DigestAuth(self.user, self.password)
        self.client = httpx.AsyncClient(auth=self.auth, timeout=30.0)

    async def close(self):
        await self.client.aclose()

    # --- FITUR DOWNLOAD GAMBAR (BARU) ---
    async def get_picture(self, picture_url: str) -> Optional[bytes]:
        """
        Download gambar event dari URL yang diberikan oleh log AcsEvent.
        """
        # Normalisasi URL (jika relative path)
        if not picture_url.startswith("http"):
            # Hapus slash awal jika ada, biar rapi gabungnya
            clean_path = picture_url.lstrip("/")
            url = f"{self.base_url}/{clean_path}"
        else:
            url = picture_url

        try:
            # print(f"   📸 [ISAPI] Downloading image: {url}...")
            response = await self.client.get(url)
            if response.status_code == 200:
                return response.content
            return None
        except Exception as e:
            print(f"   ❌ Exception Download Gambar: {e}")
            return None

    # --- FITUR LOG / EVENT ---
    async def get_events(self, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/ISAPI/AccessControl/AcsEvent?format=json"
        search_id = str(uuid.uuid4())
        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%S+07:00")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%S+07:00")

        payload = {
            "AcsEventCond": {
                "searchID": search_id,
                "searchResultPosition": 0,
                "maxResults": 50,
                "major": 5,
                "minor": 75,
                "startTime": start_str,
                "endTime": end_str
            }
        }

        try:
            # print(f"📡 [ISAPI] Request Logs {self.ip}:{self.port}...")
            response = await self.client.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                if "AcsEvent" in data and "InfoList" in data["AcsEvent"]:
                    return data["AcsEvent"]["InfoList"]
                return []
            return []
        except Exception as e:
            print(f"❌ [ISAPI] Exception Get Events: {str(e)}")
            return []

    # --- FITUR CRUD USER ---
    async def get_users(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/ISAPI/AccessControl/UserInfo/Search?format=json"
        all_users = []
        search_id = f"search_{uuid.uuid4()}"
        position = 0
        max_results = 30 

        try:
            while True:
                payload = {"UserInfoSearchCond": {"searchID": search_id, "searchResultPosition": position, "maxResults": max_results}}
                response = await self.client.post(url, json=payload)
                if response.status_code != 200: break
                
                data = response.json().get('UserInfoSearch', {})
                users_batch = data.get('UserInfo', [])
                if users_batch: all_users.extend(users_batch)
                
                matches = data.get('numOfMatches', 0)
                total_matches = data.get('totalMatches', 0)
                position += matches
                if not users_batch or position >= total_matches: break
            
            return all_users
        except Exception as e:
            print(f"❌ [ISAPI] Exception Get Users: {str(e)}")
            return []

    async def add_user(self, employee_no, name, start_time=None, end_time=None):
        url = f"{self.base_url}/ISAPI/AccessControl/UserInfo/Record?format=json"
        if not start_time: start_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        if not end_time: end_time = (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%dT%H:%M:%S")

        payload = {
            "UserInfo": {
                "employeeNo": str(employee_no),
                "name": name,
                "userType": "normal",
                "Valid": {"enable": True, "beginTime": start_time, "endTime": end_time, "timeType": "local"},
                "doorRight": "1",
                "RightPlan": [{"doorNo": 1, "planTemplateNo": "1"}]
            }
        }
        try:
            response = await self.client.post(url, json=payload)
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get('statusCode') == 1: return True, "Sukses"
                else: return False, f"Gagal: {resp_json.get('statusString')}"
            return False, f"HTTP {response.status_code}: {response.text}"
        except Exception as e: return False, f"Ex: {str(e)}"

    async def update_user(self, employee_no, name, start_time=None, end_time=None):
        url = f"{self.base_url}/ISAPI/AccessControl/UserInfo/Modify?format=json"
        if not start_time: start_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        if not end_time: end_time = (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%dT%H:%M:%S")
        
        payload = {
            "UserInfo": {
                "employeeNo": str(employee_no),
                "name": name,
                "userType": "normal",
                "Valid": {"enable": True, "beginTime": start_time, "endTime": end_time, "timeType": "local"},
                "doorRight": "1",
                "RightPlan": [{"doorNo": 1, "planTemplateNo": "1"}]
            }
        }
        try:
            response = await self.client.put(url, json=payload)
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get('statusCode') == 1: return True, "Sukses Update"
                else: return False, f"Gagal Update: {resp_json.get('statusString')}"
            return False, f"HTTP {response.status_code}: {response.text}"
        except Exception as e: return False, f"Ex: {str(e)}"

    async def delete_user(self, employee_no):
        url = f"{self.base_url}/ISAPI/AccessControl/UserInfo/Delete?format=json"
        payload = {"UserInfoDelCond": {"employeeNoList": [{"employeeNo": str(employee_no)}]}}
        try:
            response = await self.client.put(url, json=payload)
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get('statusCode') == 1: return True, "Sukses Hapus"
                else: return False, f"Gagal Hapus: {resp_json.get('statusString')}"
            return False, f"HTTP {response.status_code}: {response.text}"
        except Exception as e: return False, f"Ex: {str(e)}"

    async def add_face(self, employee_no, image_bytes):
        url = f"{self.base_url}/ISAPI/Intelligent/FDLib/FaceDataRecord?format=json"
        face_info = {"faceLibType": "blackFD", "FDID": "1", "FPID": str(employee_no)}
        files = {'FaceDataRecord': (None, json.dumps(face_info), 'application/json'), 'FaceImage': (f'{employee_no}.jpg', image_bytes, 'image/jpeg')}
        try:
            response = await self.client.post(url, files=files)
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get('statusCode') == 1: return True, "Sukses Upload Foto"
                else: return False, f"Gagal Foto: {resp_json.get('subStatusCode', 'Unknown Error')}"
            return False, f"HTTP Foto {response.status_code}: {response.text}"
        except Exception as e: return False, f"Ex Foto: {str(e)}"