"""
Add priority and element_id fields to storage_elements table.

Sprint 14: Redis Storage Registry & Adaptive Capacity.
Добавляет поля для Sequential Fill алгоритма и корреляции с Redis Registry.

Revision ID: 20251201_0001
Revises: 20251126_0000
Create Date: 2024-12-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251201_0001'
down_revision = '20251126_0000'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Добавить поля priority и element_id в storage_elements.

    priority: Приоритет для Sequential Fill алгоритма (меньше = выше приоритет)
    element_id: Строковый идентификатор SE для корреляции с Redis Registry
    """
    # Добавляем element_id - уникальный строковый идентификатор SE
    # Используется для корреляции с Redis Registry (storage:elements:{element_id})
    op.add_column(
        'storage_elements',
        sa.Column(
            'element_id',
            sa.String(50),
            nullable=True,  # Сначала nullable для existing rows
            comment='Уникальный строковый ID для Redis Registry (например: se-01)'
        )
    )

    # Добавляем priority - приоритет для Sequential Fill
    # Меньше значение = выше приоритет (100 = default, 1-99 = high priority, 101+ = low priority)
    op.add_column(
        'storage_elements',
        sa.Column(
            'priority',
            sa.Integer(),
            nullable=False,
            server_default='100',
            comment='Приоритет для Sequential Fill алгоритма (меньше = выше приоритет)'
        )
    )

    # Создаём уникальный индекс на element_id (после установки значений для existing rows)
    op.create_index(
        'idx_storage_elements_element_id',
        'storage_elements',
        ['element_id'],
        unique=True
    )

    # Создаём индекс для сортировки по приоритету
    op.create_index(
        'idx_storage_elements_priority',
        'storage_elements',
        ['priority']
    )

    # Составной индекс для фильтрации writable SE по приоритету
    op.create_index(
        'idx_storage_elements_mode_priority',
        'storage_elements',
        ['mode', 'priority']
    )


def downgrade() -> None:
    """Удалить добавленные поля и индексы."""
    # Удаляем индексы
    op.drop_index('idx_storage_elements_mode_priority', table_name='storage_elements')
    op.drop_index('idx_storage_elements_priority', table_name='storage_elements')
    op.drop_index('idx_storage_elements_element_id', table_name='storage_elements')

    # Удаляем колонки
    op.drop_column('storage_elements', 'priority')
    op.drop_column('storage_elements', 'element_id')
