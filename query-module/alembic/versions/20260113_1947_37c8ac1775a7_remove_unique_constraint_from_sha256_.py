"""Remove unique constraint from sha256_hash

Revision ID: 37c8ac1775a7
Revises: 16c6973431df
Create Date: 2026-01-13 19:47:56.317124

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '37c8ac1775a7'
down_revision: Union[str, None] = '16c6973431df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Удаляем unique constraint с sha256_hash для поддержки duplicate content.

    Use case: Два разных файла могут иметь одинаковое содержимое (sha256_hash),
    но разные file_id, имена, владельцев, storage_element_id.

    Primary key (id=file_id) гарантирует уникальность файлов.
    sha256_hash используется только для integrity verification, не для бизнес-логики.
    """
    # Удаляем существующий unique индекс на sha256_hash
    op.drop_index('ix_file_metadata_cache_sha256_hash', table_name='file_metadata_cache')

    # Создаем новый non-unique индекс для производительности поиска
    op.create_index(
        op.f('ix_file_metadata_cache_sha256_hash'),
        'file_metadata_cache',
        ['sha256_hash'],
        unique=False
    )


def downgrade() -> None:
    """
    Откат изменений: возвращаем unique constraint на sha256_hash.

    ВНИМАНИЕ: Downgrade может FAILED если в БД уже есть duplicate sha256_hash значения!
    """
    # Удаляем non-unique индекс
    op.drop_index('ix_file_metadata_cache_sha256_hash', table_name='file_metadata_cache')

    # Создаем unique индекс (может упасть если есть дубликаты)
    op.create_index(
        op.f('ix_file_metadata_cache_sha256_hash'),
        'file_metadata_cache',
        ['sha256_hash'],
        unique=True
    )
