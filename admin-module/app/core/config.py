from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AmqpDsn, PostgresDsn
from typing import List

class Settings(BaseSettings):
    """
    Класс для хранения настроек приложения.
    Настройки загружаются из переменных окружения.
    """
    # model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

    # Настройки сервера
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    DEBUG: bool = True
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:4200"]

    # База данных
    DATABASE_URL: str = "postgresql+asyncpg://artstore:password@localhost:5432/admin_module"
    DB_USER: str = "artstore"
    DB_PASSWORD: str = "password"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # Настройки аутентификации
    # Секретный ключ для симметричного шифрования (HS256) - для примера, будем менять на RS256
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Список провайдеров аутентификации в порядке их использования
    AUTH_PROVIDERS: List[str] = ["local"]

    # Пути для генерации и хранения ключей RS256
    PRIVATE_KEY_PATH: str = "admin-module/keys/jwt-private.pem"
    PUBLIC_KEY_PATH: str = "admin-module/keys/jwt-public.pem"
    
    # Данные для создания первого суперпользователя
    FIRST_SUPERUSER: str = "admin"
    FIRST_SUPERUSER_PASSWORD: str = "admin123"


settings = Settings()