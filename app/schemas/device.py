from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class DeviceBase(BaseModel):
    name: str
    ip_address: str
    port: int = 8000
    username: str
    password: str
    target_api: Optional[str] = None
    is_active: bool = True

class DeviceCreate(DeviceBase):
    pass

class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    target_api: Optional[str] = None
    is_active: Optional[bool] = None

class DeviceResponse(DeviceBase):
    id: int
    last_seen: Optional[datetime] = None
    created_at: datetime
    is_online: bool = False 

    class Config:
        from_attributes = True