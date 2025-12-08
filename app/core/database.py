from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# 1. Buat Engine Async
engine = create_async_engine(
    settings.DB_URL,
    echo=False, # Set True kalau mau lihat log SQL di terminal
    future=True
)

# 2. Buat Session Factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# 3. Base Class untuk Model
Base = declarative_base()

# 4. Fungsi Dependency (Dipakai di API nanti)
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()