"""
Alembic environment для Admin Module.
Загружает конфигурацию из config.yaml и .env.
"""

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import sys
from pathlib import Path

# Добавляем родительскую директорию в sys.path для импорта app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.models import Base  # Импортируем Base с зарегистрированными моделями

# Это Alembic Config объект, который предоставляет
# доступ к значениям из .ini файла
config = context.config

# Интерпретируем конфигурацию для Python logging
# Это устанавливает логгеры для всех 'sqlalchemy.engine'
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Устанавливаем sqlalchemy.url из наших настроек (sync для Alembic)
config.set_main_option("sqlalchemy.url", settings.database.sync_url)

# Добавляем MetaData модели для поддержки 'autogenerate'
target_metadata = Base.metadata

# Дополнительные параметры из config могут быть здесь переданы
# configure() как context.configure(). Следующий пример
# показывает как передать параметры для сравнения типов
# ... etc.


def run_migrations_offline() -> None:
    """
    Запуск миграций в 'offline' режиме.

    Это конфигурирует context только с URL
    и не с Engine, хотя Engine также приемлем здесь.
    Пропуская создание Engine, мы даже не нуждаемся в DBAPI.

    Вызов context.execute() здесь генерирует SQL скрипт в STDOUT.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # Сравнивать типы колонок при autogenerate
        compare_server_default=True,  # Сравнивать server defaults
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Запуск миграций в 'online' режиме.

    В этом сценарии мы должны создать Engine
    и связать connection с context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # Сравнивать типы колонок при autogenerate
            compare_server_default=True,  # Сравнивать server defaults
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
