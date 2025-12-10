import ctypes
import sys
import os
import time
import struct
import uuid
import socket
from ctypes import (
    c_byte, c_char, c_int, c_uint32, c_uint16, c_float, c_void_p, 
    Structure, POINTER, CFUNCTYPE, cast, sizeof, byref, c_ubyte, create_string_buffer
)
from app.core.config import settings

# --- 1. SETUP LIBRARY ---
try:
    ctypes.CDLL(os.path.join(settings.SDK_LIB_PATH, "libcrypto.so.1.1"), mode=ctypes.RTLD_GLOBAL)
    ctypes.CDLL(os.path.join(settings.SDK_LIB_PATH, "libssl.so.1.1"), mode=ctypes.RTLD_GLOBAL)
    hccore = ctypes.cdll.LoadLibrary(os.path.join(settings.SDK_LIB_PATH, "libHCCore.so"))
    hcnetsdk = ctypes.cdll.LoadLibrary(os.path.join(settings.SDK_LIB_PATH, "libhcnetsdk.so"))
    
    hcnetsdk.NET_DVR_Init()
    hcnetsdk.NET_DVR_SetConnectTime(2000, 1)
    hcnetsdk.NET_DVR_SetReconnect(10000, True)
    print("✅ [SDK] Library Loaded Successfully")
except OSError as e:
    print(f"❌ [SDK-FATAL] Gagal load library: {e}")

# --- 2. DEFINISI STRUKTUR (Sama seperti sebelumnya) ---
class NET_DVR_USER_LOGIN_INFO(Structure):
    _fields_ = [("sDeviceAddress", c_char * 129), ("byUseTransport", c_byte), ("wPort", c_uint16), ("sUserName", c_char * 64), ("sPassword", c_char * 64), ("bUseAsynLogin", c_int), ("byProxyType", c_byte), ("byUseUTCTime", c_byte), ("byLoginMode", c_byte), ("byHttps", c_byte), ("iProxyID", c_int), ("byVerifyMode", c_byte), ("byRes3", c_byte * 119)]

class NET_DVR_DEVICEINFO_V40(Structure):
    _fields_ = [("struDeviceV30", c_byte * 256), ("bySupportLock", c_byte), ("byRetryLoginTime", c_byte), ("byPasswordLevel", c_byte), ("byProxyType", c_byte), ("bySurplusLockTime", c_byte), ("byCharEncodeType", c_byte), ("bySupportDev5", c_byte), ("bySupportLoginMode", c_byte), ("byLoginMode", c_byte), ("byHttps", c_byte), ("byRes2", c_byte * 246)]

class NET_DVR_SETUPALARM_PARAM(Structure):
    _fields_ = [("dwSize", c_uint32), ("byLevel", c_byte), ("byAlarmInfoOnly", c_byte), ("byRetAlarmTypeV40", c_byte), ("byRetDevInfoVersion", c_byte), ("byFaceAlarmDetection", c_byte), ("bySupport", c_byte), ("byBrokenNetHttp", c_byte), ("wTaskNo", c_uint16), ("byDeployType", c_byte), ("byRes1", c_byte * 3), ("byAlarmTypeURL", c_byte), ("bySupportCustomCfg", c_byte), ("byRes", c_byte * 128)]

class NET_DVR_ALARMER(Structure):
    _fields_ = [
        ("byUserIDValid", c_byte), ("bySerialValid", c_byte), ("byVersionValid", c_byte),
        ("byDeviceNameValid", c_byte), ("byMacAddrValid", c_byte), ("byLinkPortValid", c_byte),
        ("byDeviceIPValid", c_byte), ("bySocketIPValid", c_byte), ("lUserID", c_int),
        ("sSerialNumber", c_char * 48), ("dwDeviceVersion", c_uint32), ("sDeviceName", c_char * 32),
        ("byMacAddr", c_char * 6), ("wLinkPort", c_uint16), 
        ("sDeviceIP", c_char * 128), 
        ("sSocketIP", c_char * 128), ("byIpProtocol", c_byte), ("byRes2", c_byte * 6)
    ]

MSG_CALLBACK_FUNC = CFUNCTYPE(None, c_int, c_void_p, c_void_p, c_uint32, c_void_p)

# --- 3. CLASS DRIVER UTAMA ---

class SDKDriver:
    def __init__(self):
        self.sessions = {} 
        self.callback_ref = None 
        self.global_event_handler = None

    def set_global_handler(self, handler_func):
        self.global_event_handler = handler_func

    # --- CALLBACK (LOGIKA PARSING) ---
    def _internal_callback(self, lCommand, pAlarmer, pAlarmInfo, dwBufLen, pUser):
        # 0x5002 = COMM_ALARM_ACS (Event Absen)
        if lCommand == 0x5002:
            try:
                # 1. Ambil IP Pengirim
                alarmer = cast(pAlarmer, POINTER(NET_DVR_ALARMER)).contents
                device_ip = alarmer.sDeviceIP.decode('utf-8', errors='ignore').strip('\x00')

                # 2. Ambil Buffer Data Mentah
                raw_data = cast(pAlarmInfo, POINTER(c_ubyte * dwBufLen)).contents
                buffer = bytearray(raw_data)

                # --- BEDAH MEMORI ---
                
                # A. Waktu (Offset 12)
                year = struct.unpack('i', buffer[12:16])[0]
                month = struct.unpack('i', buffer[16:20])[0]
                day = struct.unpack('i', buffer[20:24])[0]
                hour = struct.unpack('i', buffer[24:28])[0]
                minute = struct.unpack('i', buffer[28:32])[0]
                second = struct.unpack('i', buffer[32:36])[0]
                date_str = f"{year}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"

                # B. User ID (Offset 360)
                user_id_raw = buffer[360:392]
                auth_id = user_id_raw.split(b'\x00')[0].decode('utf-8', errors='ignore')

                # C. Suhu (Offset 524)
                temp_bytes = buffer[524:528]
                temperature = struct.unpack('f', temp_bytes)[0]
                temperature = round(temperature, 1)

                # D. Gambar (REVISI PENTING DI SINI)
                # Cari header JPEG (FF D8) mulai dari index 0 (bukan 600)
                # Ini memastikan gambar ditemukan dimanapun posisinya
                picture_path = None
                start_img = buffer.find(b'\xff\xd8', 0) # <--- UBAH JADI 0
                
                if start_img != -1:
                    img_data = buffer[start_img:]
                    # Validasi minimal: pastikan bukan header palsu (misal ukurannya masuk akal > 1KB)
                    if len(img_data) > 1024:
                        filename = f"sdk_{uuid.uuid4().hex[:8]}.jpg"
                        os.makedirs("static/images", exist_ok=True)
                        full_path = f"static/images/{filename}"
                        with open(full_path, "wb") as f:
                            f.write(img_data)
                        picture_path = full_path
                        # Debugging: Print jika foto ketemu
                        # print(f"   📸 Foto extracted: {filename}")

                print(f"⚡ [REAL-TIME] ID:{auth_id} | 🌡️ {temperature}°C | 📸 {picture_path is not None}")

                # Bungkus Data
                final_data = {
                    "device": device_ip,
                    "authId": auth_id,
                    "date": date_str,
                    "picture": picture_path,
                    "temperature": temperature, 
                    "source": "REALTIME"
                }

                if self.global_event_handler:
                    self.global_event_handler(final_data)

            except Exception as e:
                print(f"❌ [SDK-ERROR] Callback Parsing: {e}")
        return

    def init_callback(self):
        if not self.callback_ref:
            self.callback_ref = MSG_CALLBACK_FUNC(self._internal_callback)
            hcnetsdk.NET_DVR_SetDVRMessageCallBack_V31(self.callback_ref, None)

    # --- KONEKSI ---
    def login(self, ip, user, password, port=8000):
        if ip in self.sessions and self.sessions[ip]['user_id'] >= 0:
            return True
        
        print(f"--- [SDK] Connecting to {ip}:{port} ---")
        login_info = NET_DVR_USER_LOGIN_INFO()
        login_info.sDeviceAddress = ip.encode('utf-8')
        login_info.sUserName = user.encode('utf-8')
        login_info.sPassword = password.encode('utf-8')
        login_info.wPort = port
        login_info.bUseAsynLogin = 0
        device_info = NET_DVR_DEVICEINFO_V40()
        
        user_id = hcnetsdk.NET_DVR_Login_V40(byref(login_info), byref(device_info))

        if user_id < 0:
            err = hcnetsdk.NET_DVR_GetLastError()
            print(f"❌ [SDK] Gagal Login {ip}. Code: {err}")
            return False
        
        print(f"✅ [SDK] Berhasil Login {ip} (ID: {user_id})")
        
        self.sessions[ip] = {
            "user_id": user_id,
            "alarm_handle": -1
        }
        
        self.start_listening(ip)
        return True

    def start_listening(self, ip):
        if ip not in self.sessions: return False
        session = self.sessions[ip]
        if session["alarm_handle"] >= 0: return True

        self.init_callback() 

        setup_param = NET_DVR_SETUPALARM_PARAM()
        setup_param.dwSize = sizeof(NET_DVR_SETUPALARM_PARAM)
        setup_param.byLevel = 1 
        setup_param.byAlarmInfoOnly = 0 # 0 = Kirim Gambar
        setup_param.byDeployType = 1    

        alarm_handle = hcnetsdk.NET_DVR_SetupAlarmChan_V41(session["user_id"], byref(setup_param))
        
        if alarm_handle < 0:
            print(f"❌ [SDK] Gagal Setup Alarm {ip}. Code: {hcnetsdk.NET_DVR_GetLastError()}")
            return False

        session["alarm_handle"] = alarm_handle
        print(f"🎧 [SDK] Listening AKTIF untuk {ip}")
        return True

    def logout(self, ip):
        if ip in self.sessions:
            session = self.sessions[ip]
            if session["alarm_handle"] >= 0:
                hcnetsdk.NET_DVR_CloseAlarmChan_V30(session["alarm_handle"])
            if session["user_id"] >= 0:
                hcnetsdk.NET_DVR_Logout(session["user_id"])
            print(f"👋 [SDK] Logout {ip}")
            del self.sessions[ip]

    def check_online(self, ip, port=8000):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5) 
            result = sock.connect_ex((ip, int(port)))
            sock.close()
            return result == 0 
        except:
            return False

    def set_user_info(self, ip, emp_no, name, start_dt=None, end_dt=None): return False
    def set_user_face(self, ip, emp_no, image_data): return False
    def del_user(self, ip, emp_no): return False

driver_instance = SDKDriver()