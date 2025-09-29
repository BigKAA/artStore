from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Код, который выполнится при старте приложения
    print("Приложение запускается...")
    yield
    # Код, который выполнится при остановке приложения
    print("Приложение останавливается...")

app = FastAPI(
    title="ArtStore Admin Module",
    description="Модуль администратора для системы распределенного файлового хранилища ArtStore.",
    version="0.1.0",
    lifespan=lifespan
)

@app.get("/", tags=["Root"])
async def read_root():
    """
    Корневой эндпоинт, возвращает информацию о сервисе.
    """
    return {"service": "Admin Module", "status": "ok"}

# Подключаем роутеры
from app.api.api import api_router
app.include_router(api_router, prefix="/api")