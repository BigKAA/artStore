"""
Утилиты для генерации уникальных имен файлов в хранилище.

Формат имени:
{original_name_stem}_{username}_{timestamp}_{uuid}.{ext}

Пример:
report_ivanov_20250110T153045_a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf

Гарантии:
- Уникальность через UUID
- Human-readable через original name первым
- Автоматическое обрезание длинных имен до 200 символов
- Поддержка unicode символов в именах
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4


def sanitize_filename(filename: str) -> str:
    """
    Очистка имени файла от недопустимых символов.

    Заменяет все недопустимые символы на подчеркивание.
    Сохраняет unicode символы (русские, китайские и т.д.).

    Args:
        filename: Исходное имя файла

    Returns:
        str: Очищенное имя файла

    Примеры:
        >>> sanitize_filename("report/2024.pdf")
        "report_2024.pdf"
        >>> sanitize_filename("отчет за 2024.docx")
        "отчет_за_2024.docx"
    """
    # Недопустимые символы для файловой системы
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'

    # Замена недопустимых символов на подчеркивание
    sanitized = re.sub(invalid_chars, '_', filename)

    # Удаление множественных подчеркиваний
    sanitized = re.sub(r'_+', '_', sanitized)

    # Удаление подчеркиваний в начале и конце
    sanitized = sanitized.strip('_')

    return sanitized


def truncate_stem(stem: str, max_length: int) -> str:
    """
    Обрезание имени файла с сохранением читаемости.

    Если имя длиннее max_length:
    - Берет первые (max_length - 3) символов
    - Добавляет "..." в конец

    Args:
        stem: Имя файла без расширения
        max_length: Максимальная длина

    Returns:
        str: Обрезанное имя

    Примеры:
        >>> truncate_stem("very_long_filename", 10)
        "very_lo..."
    """
    if len(stem) <= max_length:
        return stem

    # Обрезаем и добавляем многоточие
    return stem[:max_length - 3] + "..."


def generate_storage_filename(
    original_filename: str,
    username: str,
    timestamp: Optional[datetime] = None,
    file_uuid: Optional[UUID] = None,
    max_total_length: int = 200
) -> str:
    """
    Генерация уникального имени файла для хранилища.

    Формат: {stem}_{username}_{timestamp}_{uuid}.{ext}

    Args:
        original_filename: Оригинальное имя файла с расширением
        username: Username пользователя
        timestamp: Timestamp создания (default: now)
        file_uuid: UUID файла (default: новый UUID)
        max_total_length: Максимальная длина итогового имени (default: 200)

    Returns:
        str: Уникальное имя файла для хранилища

    Raises:
        ValueError: Если username пустой или содержит недопустимые символы

    Примеры:
        >>> generate_storage_filename(
        ...     "report.pdf",
        ...     "ivanov",
        ...     datetime(2025, 1, 10, 15, 30, 45),
        ...     UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        ... )
        "report_ivanov_20250110T153045_a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf"
    """
    # Валидация username
    if not username or not username.strip():
        raise ValueError("Username cannot be empty")

    # Очистка username от недопустимых символов
    clean_username = sanitize_filename(username.strip())
    if not clean_username:
        raise ValueError("Username contains only invalid characters")

    # Генерация timestamp если не передан
    if timestamp is None:
        timestamp = datetime.now()

    # Генерация UUID если не передан
    if file_uuid is None:
        file_uuid = uuid4()

    # Парсинг оригинального имени
    original_path = Path(original_filename)
    original_stem = original_path.stem  # Имя без расширения
    original_ext = original_path.suffix  # Расширение с точкой

    # Очистка stem от недопустимых символов
    clean_stem = sanitize_filename(original_stem)
    if not clean_stem:
        # Если имя файла содержало только недопустимые символы
        clean_stem = "file"

    # Форматирование timestamp (ISO 8601 compact)
    timestamp_str = timestamp.strftime("%Y%m%dT%H%M%S")

    # UUID в строковом формате
    uuid_str = str(file_uuid)

    # Расчет доступной длины для stem
    # Формат: {stem}_{username}_{timestamp}_{uuid}.{ext}
    # Фиксированные части: _ + username + _ + timestamp + _ + uuid + ext
    fixed_length = (
        1 +  # первый _
        len(clean_username) +
        1 +  # второй _
        len(timestamp_str) +
        1 +  # третий _
        len(uuid_str) +
        len(original_ext)
    )

    # Проверка что фиксированная часть не превышает лимит
    if fixed_length >= max_total_length:
        raise ValueError(
            f"Fixed parts of filename ({fixed_length} chars) exceed max length ({max_total_length})"
        )

    # Доступная длина для stem
    available_for_stem = max_total_length - fixed_length

    # Обрезание stem если необходимо
    if len(clean_stem) > available_for_stem:
        clean_stem = truncate_stem(clean_stem, available_for_stem)

    # Сборка итогового имени
    storage_filename = (
        f"{clean_stem}_{clean_username}_{timestamp_str}_{uuid_str}{original_ext}"
    )

    return storage_filename


def generate_storage_path(timestamp: Optional[datetime] = None) -> str:
    """
    Генерация пути для хранения файла: /year/month/day/hour/

    Args:
        timestamp: Timestamp для генерации пути (default: now)

    Returns:
        str: Относительный путь в формате "YYYY/MM/DD/HH/"

    Примеры:
        >>> generate_storage_path(datetime(2025, 1, 10, 15, 30, 45))
        "2025/01/10/15/"
    """
    if timestamp is None:
        timestamp = datetime.now()

    # Форматирование: год/месяц/день/час/
    path = timestamp.strftime("%Y/%m/%d/%H/")

    return path


def parse_storage_filename(storage_filename: str) -> dict:
    """
    Парсинг storage filename для извлечения компонентов.

    Args:
        storage_filename: Имя файла в формате хранилища

    Returns:
        dict: Словарь с компонентами {
            "original_stem": str,
            "username": str,
            "timestamp": datetime,
            "uuid": UUID,
            "extension": str
        }

    Raises:
        ValueError: Если имя файла не соответствует формату

    Примеры:
        >>> parse_storage_filename(
        ...     "report_ivanov_20250110T153045_a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf"
        ... )
        {
            "original_stem": "report",
            "username": "ivanov",
            "timestamp": datetime(2025, 1, 10, 15, 30, 45),
            "uuid": UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
            "extension": ".pdf"
        }
    """
    # Разделение имени и расширения
    path = Path(storage_filename)
    filename_without_ext = path.stem
    extension = path.suffix

    # Разбиение по подчеркиваниям (последние 3 части фиксированы)
    parts = filename_without_ext.split('_')

    if len(parts) < 4:
        raise ValueError(
            f"Invalid storage filename format: {storage_filename}. "
            "Expected format: stem_username_timestamp_uuid.ext"
        )

    # Последние 3 части: username, timestamp, uuid
    uuid_str = parts[-1]
    timestamp_str = parts[-2]
    username = parts[-3]

    # Все остальное - original stem (может содержать подчеркивания)
    original_stem = '_'.join(parts[:-3])

    # Парсинг timestamp
    try:
        timestamp = datetime.strptime(timestamp_str, "%Y%m%dT%H%M%S")
    except ValueError as e:
        raise ValueError(f"Invalid timestamp format: {timestamp_str}") from e

    # Парсинг UUID
    try:
        file_uuid = UUID(uuid_str)
    except ValueError as e:
        raise ValueError(f"Invalid UUID format: {uuid_str}") from e

    return {
        "original_stem": original_stem,
        "username": username,
        "timestamp": timestamp,
        "uuid": file_uuid,
        "extension": extension
    }
