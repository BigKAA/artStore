"""Initial schema with Full-Text Search support

Revision ID: 20250115_0001
Revises:
Create Date: 2025-01-15 00:01:00.000000

Создает:
- Таблицы: file_metadata_cache, search_history, download_statistics
- GIN индексы для Full-Text Search (русский язык)
- GIN индексы для ARRAY поиска (tags)
- B-tree индексы для частых запросов
- Triggers для автоматического обновления search_vector
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20250115_0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Создание схемы базы данных для Query Module.

    Включает:
    - Основные таблицы
    - GIN индексы для Full-Text Search
    - Triggers для автоматического обновления search_vector
    """

    # ========================================
    # 1. FileMetadata Cache Table
    # ========================================
    op.create_table(
        'file_metadata_cache',
        sa.Column('id', sa.String(length=36), nullable=False, comment='UUID файла (совпадает с ID в Storage Element)'),
        sa.Column('filename', sa.String(length=255), nullable=False, comment='Оригинальное имя файла (для отображения пользователю)'),
        sa.Column('storage_filename', sa.String(length=512), nullable=False, comment='Имя файла в Storage Element (с username_timestamp_uuid)'),
        sa.Column('file_size', sa.BigInteger(), nullable=False, comment='Размер файла в bytes'),
        sa.Column('mime_type', sa.String(length=127), nullable=True, comment='MIME тип файла (image/jpeg, application/pdf, etc.)'),
        sa.Column('sha256_hash', sa.String(length=64), nullable=False, comment='SHA256 хеш файла для верификации целостности'),
        sa.Column('username', sa.String(length=255), nullable=False, comment='Владелец файла (из JWT sub или username)'),
        sa.Column('tags', postgresql.ARRAY(sa.String(length=50)), nullable=True, comment='Теги файла для поиска (максимум 50 тегов)'),
        sa.Column('description', sa.Text(), nullable=True, comment='Описание файла'),
        sa.Column('storage_element_id', sa.String(length=50), nullable=False, comment='ID Storage Element где хранится файл'),
        sa.Column('storage_element_url', sa.String(length=512), nullable=False, comment='URL Storage Element для скачивания файла'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='Дата создания файла в Storage Element'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, comment='Дата последнего обновления метаданных'),
        sa.Column('cache_updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Дата последнего обновления кеша'),
        sa.Column('search_vector', postgresql.TSVECTOR(), nullable=True, comment='Полнотекстовый поисковый вектор (auto-generated)'),
        sa.CheckConstraint('file_size >= 0', name='check_file_size_positive'),
        sa.CheckConstraint('array_length(tags, 1) <= 50', name='check_tags_count'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sha256_hash'),
        comment='Кеш метаданных файлов для быстрого поиска и снижения нагрузки на Storage Elements'
    )

    # Индексы для file_metadata_cache
    op.create_index('idx_file_metadata_filename', 'file_metadata_cache', ['filename'])
    op.create_index('idx_file_metadata_mime_type', 'file_metadata_cache', ['mime_type', 'created_at'])
    op.create_index('idx_file_metadata_sha256', 'file_metadata_cache', ['sha256_hash'], unique=True)
    op.create_index('idx_file_metadata_username', 'file_metadata_cache', ['username'])
    op.create_index('idx_file_metadata_storage_elem', 'file_metadata_cache', ['storage_element_id', 'created_at'])
    op.create_index('idx_file_metadata_created_at', 'file_metadata_cache', ['created_at'])
    op.create_index('idx_file_metadata_updated_at', 'file_metadata_cache', ['updated_at'])
    op.create_index('idx_file_metadata_file_size', 'file_metadata_cache', ['file_size', 'created_at'])
    op.create_index('idx_file_metadata_username_created', 'file_metadata_cache', ['username', 'created_at'])

    # GIN индекс для Full-Text Search (search_vector)
    op.create_index(
        'idx_file_metadata_search_vector',
        'file_metadata_cache',
        ['search_vector'],
        postgresql_using='gin'
    )

    # GIN индекс для поиска по тегам (ARRAY)
    op.create_index(
        'idx_file_metadata_tags',
        'file_metadata_cache',
        ['tags'],
        postgresql_using='gin'
    )

    # ========================================
    # 2. Trigger для автоматического обновления search_vector
    # ========================================
    # PostgreSQL функция для обновления search_vector при INSERT/UPDATE
    op.execute("""
        CREATE OR REPLACE FUNCTION update_file_metadata_search_vector()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Создаем поисковый вектор из filename (вес A), description (вес B), tags (вес C)
            -- Используем русскую конфигурацию для правильной стемматизации
            NEW.search_vector :=
                setweight(to_tsvector('russian', COALESCE(NEW.filename, '')), 'A') ||
                setweight(to_tsvector('russian', COALESCE(NEW.description, '')), 'B') ||
                setweight(to_tsvector('russian', COALESCE(array_to_string(NEW.tags, ' '), '')), 'C');

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Trigger на INSERT и UPDATE
    op.execute("""
        CREATE TRIGGER trigger_update_search_vector
        BEFORE INSERT OR UPDATE OF filename, description, tags
        ON file_metadata_cache
        FOR EACH ROW
        EXECUTE FUNCTION update_file_metadata_search_vector();
    """)

    # ========================================
    # 3. SearchHistory Table
    # ========================================
    op.create_table(
        'search_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='Auto-increment ID записи'),
        sa.Column('query_text', sa.Text(), nullable=True, comment='Текст поискового запроса'),
        sa.Column('search_mode', sa.String(length=20), nullable=False, comment='Режим поиска (exact, partial, fulltext)'),
        sa.Column('filters_applied', sa.Text(), nullable=True, comment='Примененные фильтры (JSON строка)'),
        sa.Column('results_count', sa.Integer(), nullable=False, default=0, comment='Количество найденных результатов'),
        sa.Column('response_time_ms', sa.Integer(), nullable=False, comment='Время ответа в миллисекундах'),
        sa.Column('username', sa.String(length=255), nullable=True, comment='Пользователь выполнивший поиск'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Дата и время выполнения поиска'),
        sa.CheckConstraint('results_count >= 0', name='check_results_count_positive'),
        sa.CheckConstraint('response_time_ms >= 0', name='check_response_time_positive'),
        sa.PrimaryKeyConstraint('id'),
        comment='История поисковых запросов для аналитики и оптимизации'
    )

    # Индексы для search_history
    op.create_index('idx_search_history_created', 'search_history', ['created_at'])
    op.create_index('idx_search_history_username', 'search_history', ['username'])
    op.create_index('idx_search_history_username_created', 'search_history', ['username', 'created_at'])
    op.create_index('idx_search_history_mode', 'search_history', ['search_mode', 'created_at'])

    # ========================================
    # 4. DownloadStatistics Table
    # ========================================
    op.create_table(
        'download_statistics',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='Auto-increment ID записи'),
        sa.Column('file_id', sa.String(length=36), nullable=False, comment='UUID файла (FK к FileMetadata)'),
        sa.Column('bytes_transferred', sa.BigInteger(), nullable=False, comment='Количество переданных bytes'),
        sa.Column('download_time_ms', sa.Integer(), nullable=False, comment='Время скачивания в миллисекундах'),
        sa.Column('was_resumed', sa.Boolean(), nullable=False, default=False, comment='Было ли скачивание resumed (HTTP Range request)'),
        sa.Column('username', sa.String(length=255), nullable=True, comment='Пользователь скачавший файл'),
        sa.Column('storage_element_id', sa.String(length=50), nullable=False, comment='ID Storage Element с которого скачан файл'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Дата и время скачивания'),
        sa.CheckConstraint('bytes_transferred >= 0', name='check_bytes_positive'),
        sa.CheckConstraint('download_time_ms >= 0', name='check_download_time_positive'),
        sa.PrimaryKeyConstraint('id'),
        comment='Статистика скачивания файлов для мониторинга и capacity planning'
    )

    # Индексы для download_statistics
    op.create_index('idx_download_stats_file_id', 'download_statistics', ['file_id'])
    op.create_index('idx_download_stats_created', 'download_statistics', ['created_at'])
    op.create_index('idx_download_stats_file_created', 'download_statistics', ['file_id', 'created_at'])
    op.create_index('idx_download_stats_storage_created', 'download_statistics', ['storage_element_id', 'created_at'])
    op.create_index('idx_download_stats_username', 'download_statistics', ['username'])
    op.create_index('idx_download_stats_username_created', 'download_statistics', ['username', 'created_at'])


def downgrade() -> None:
    """
    Откат миграции - удаление всех созданных объектов.
    """
    # Drop tables in reverse order
    op.drop_table('download_statistics')
    op.drop_table('search_history')

    # Drop trigger and function для file_metadata_cache
    op.execute("DROP TRIGGER IF EXISTS trigger_update_search_vector ON file_metadata_cache")
    op.execute("DROP FUNCTION IF EXISTS update_file_metadata_search_vector()")

    op.drop_table('file_metadata_cache')
