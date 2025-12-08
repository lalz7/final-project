import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Config
    APP_NAME: str = "Intelligent Middleware Q-Learning"
    VERSION: str = "1.0.0"
    
    # Database (SQLite Async)
    DB_URL: str = "sqlite+aiosqlite:///./hikvision.db"
    
    # Device Config (Login)
    DEVICE_IP: str = "10.1.248.221"
    DEVICE_USER: str = "admin"
    DEVICE_PASS: str = "Hik3421@" # <-- Pastikan password ini benar
    
    # --- PEMISAHAN PORT (INI YANG TADI HILANG) ---
    SDK_PORT: int = 8000  # Port C++ (Default 8000)
    HTTP_PORT: int = 80   # Port Web/ISAPI (Default 80)
    
    # Path ke Library SDK
    SDK_LIB_PATH: str = "/home/izlal/final-project/lib/"

    # Q-Learning Hyperparameters
    RL_ALPHA: float = 0.1
    RL_GAMMA: float = 0.9
    RL_EPSILON: float = 0.1

    class Config:
        env_file = ".env"

settings = Settings()