import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Config
    APP_NAME: str = "Intelligent Middleware"
    VERSION: str = "1.9.0"
    
    # Database (SQLite Async)
    DB_URL: str = "sqlite+aiosqlite:///./hikvision.db"
    
    # --- KONFIGURASI PORT DEFAULT ---
    # Digunakan sebagai fallback jika user tidak mengisi port saat Add Device
    SDK_PORT_DEFAULT: int = 8000  # Port C++ (SDK)
    HTTP_PORT_DEFAULT: int = 80   # Port Web (ISAPI)
    
    # Path ke Library SDK
    # Pastikan path ini sesuai dengan lokasi folder lib di server Anda
    SDK_LIB_PATH: str = "/home/izlal/final-project/lib/"

    class Config:
        env_file = ".env"

settings = Settings()