"""
File naming utility для Storage Element.

Генерирует уникальные storage-friendly имена файлов с автоматическим обрезанием.
Формат: {name}_{username}_{timestamp}_{uuid}.{ext}
"""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4, UUID
from typing import Optional


def generate_storage_filename(
    original_name: str,
    username: str,
    timestamp: Optional[datetime] = None,
    file_uuid: Optional[str] = None,
    max_filename_length: int = 200
) -> str:
    """
    Генерирует уникальное storage filename с автоматическим обрезанием до max_filename_length.

    Формат: {name_without_ext}_{username}_{timestamp}_{uuid}.{ext}

    Где:
    - name_without_ext: оригинальное имя без расширения (обрезается при необходимости)
    - username: имя пользователя, загружающего файл
    - timestamp: ISO 8601 формат (например, 20251108T103045)
    - uuid: уникальный идентификатор файла (без дефисов)
    - ext: оригинальное расширение файла

    Args:
        original_name: Оригинальное имя файла (например, "report.pdf")
        username: Имя пользователя (например, "ivanov")
        timestamp: Timestamp для имени (по умолчанию - текущее время)
        file_uuid: UUID файла (по умолчанию - генерируется новый)
        max_filename_length: Максимальная длина результирующего имени (по умолчанию 200)

    Returns:
        str: Storage filename (например, "report_ivanov_20251108T103045_a1b2c3d4e5f67890.pdf")

    Raises:
        ValueError: Если original_name пустое или username содержит недопустимые символы
        ValueError: Если невозможно создать имя в пределах max_filename_length

    Examples:
        >>> generate_storage_filename("report.pdf", "ivanov")
        'report_ivanov_20251108T103045_a1b2c3d4e5f67890.pdf'

        >>> # Обрезание длинного имени
        >>> long_name = "a" * 300 + ".pdf"
        >>> result = generate_storage_filename(long_name, "user")
        >>> len(result) <= 200
        True

        >>> # С фиксированным UUID и timestamp
        >>> dt = datetime(2025, 11, 8, 10, 30, 45)
        >>> generate_storage_filename(
        ...     "doc.txt",
        ...     "smith",
        ...     timestamp=dt,
        ...     file_uuid="12345678-90ab-cdef-1234-567890abcdef"
        ... )
        'doc_smith_20251108T103045_1234567890abcdef1234567890abcdef.txt'
    """
    # Валидация входных данных
    if not original_name or not original_name.strip():
        raise ValueError("original_name не может быть пустым")

    if not username or not username.strip():
        raise ValueError("username не может быть пустым")

    # Очистка username от недопустимых символов (только латиница, цифры, дефис, подчеркивание)
    username = username.strip()
    # Проверяем что username содержит только ASCII буквы/цифры, дефис и подчеркивание
    if not all(c.isascii() and (c.isalnum() or c in ('-', '_')) for c in username):
        raise ValueError(
            f"username содержит недопустимые символы: '{username}'. "
            "Разрешены только латиница, цифры, дефис и подчеркивание"
        )

    # Получение timestamp в ISO 8601 формате (компактная версия без разделителей)
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    timestamp_str = timestamp.strftime("%Y%m%dT%H%M%S")

    # Генерация или валидация UUID
    if file_uuid is None:
        uuid_str = uuid4().hex  # UUID без дефисов (32 символа)
    else:
        # Валидация и нормализация UUID
        try:
            # Поддержка как UUID объектов, так и строк
            if isinstance(file_uuid, UUID):
                uuid_str = file_uuid.hex
            else:
                uuid_str = UUID(file_uuid).hex
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Недопустимый формат UUID: {file_uuid}") from e

    # Разбор оригинального имени на stem и extension
    path = Path(original_name.strip())
    name_stem = path.stem
    name_ext = path.suffix  # Включает точку (например, ".pdf")

    if not name_stem:
        raise ValueError(f"original_name должно содержать имя файла: '{original_name}'")

    # Вычисление фиксированной части длины (все кроме name_stem)
    # Формат: {name_stem}_{username}_{timestamp}_{uuid}{ext}
    # Фиксированные части: "_" (3 символа) + username + timestamp + uuid + ext
    fixed_length = (
        1 +  # первый подчеркивание после name_stem
        len(username) +
        1 +  # второй подчеркивание
        len(timestamp_str) +
        1 +  # третий подчеркивание
        len(uuid_str) +
        len(name_ext)
    )

    # Вычисление доступного места для name_stem
    available_for_stem = max_filename_length - fixed_length

    # Проверка на минимальную длину
    if available_for_stem < 1:
        raise ValueError(
            f"Невозможно создать filename в пределах {max_filename_length} символов. "
            f"Фиксированная часть занимает {fixed_length} символов "
            f"(username={len(username)}, timestamp={len(timestamp_str)}, "
            f"uuid={len(uuid_str)}, ext={len(name_ext)}). "
            f"Попробуйте использовать более короткий username или увеличить max_filename_length."
        )

    # Обрезание name_stem если необходимо
    if len(name_stem) > available_for_stem:
        truncated_stem = name_stem[:available_for_stem]
        # Для удобства debugging - логирование не реализовано здесь (будет добавлено на уровне API)
    else:
        truncated_stem = name_stem

    # Сборка итогового filename
    storage_filename = f"{truncated_stem}_{username}_{timestamp_str}_{uuid_str}{name_ext}"

    # Финальная проверка длины (должно быть гарантировано математикой выше)
    assert len(storage_filename) <= max_filename_length, (
        f"Internal error: generated filename exceeds max length. "
        f"Generated: {len(storage_filename)}, Max: {max_filename_length}"
    )

    return storage_filename


def parse_storage_filename(storage_filename: str) -> dict:
    """
    Парсит storage filename и извлекает компоненты.

    Args:
        storage_filename: Storage filename для парсинга

    Returns:
        dict: Словарь с ключами:
            - name_stem: имя без расширения (возможно обрезанное)
            - username: имя пользователя
            - timestamp: datetime объект
            - uuid: UUID строка (с дефисами)
            - extension: расширение файла с точкой

    Raises:
        ValueError: Если filename не соответствует ожидаемому формату

    Examples:
        >>> parsed = parse_storage_filename("report_ivanov_20251108T103045_a1b2c3d4.pdf")
        >>> parsed['username']
        'ivanov'
        >>> parsed['timestamp']
        datetime.datetime(2025, 11, 8, 10, 30, 45)
    """
    # Получение расширения
    path = Path(storage_filename)
    extension = path.suffix
    name_without_ext = path.stem

    # Разбор на компоненты (ожидаем минимум 4 части, разделенные "_")
    parts = name_without_ext.split("_")

    if len(parts) < 4:
        raise ValueError(
            f"Недопустимый формат storage filename: '{storage_filename}'. "
            f"Ожидается формат: {{name}}_{{username}}_{{timestamp}}_{{uuid}}.{{ext}}"
        )

    # Последние 3 части - это всегда username, timestamp, uuid
    # Все что перед ними - это name_stem (может содержать подчеркивания)
    uuid_str = parts[-1]
    timestamp_str = parts[-2]
    username = parts[-3]
    name_stem = "_".join(parts[:-3]) if len(parts) > 4 else parts[0]

    # Парсинг timestamp
    try:
        timestamp = datetime.strptime(timestamp_str, "%Y%m%dT%H%M%S")
    except ValueError as e:
        raise ValueError(
            f"Недопустимый формат timestamp в filename: '{timestamp_str}'"
        ) from e

    # Валидация UUID и форматирование с дефисами
    try:
        # UUID в filename хранится без дефисов (32 символа)
        # Восстанавливаем стандартный формат UUID с дефисами
        uuid_obj = UUID(uuid_str)
        uuid_formatted = str(uuid_obj)  # С дефисами
    except ValueError as e:
        raise ValueError(
            f"Недопустимый формат UUID в filename: '{uuid_str}'"
        ) from e

    return {
        "name_stem": name_stem,
        "username": username,
        "timestamp": timestamp,
        "uuid": uuid_formatted,
        "extension": extension
    }


def validate_storage_filename(storage_filename: str) -> bool:
    """
    Проверяет валидность storage filename.

    Args:
        storage_filename: Filename для проверки

    Returns:
        bool: True если filename валиден, False иначе

    Examples:
        >>> validate_storage_filename("report_ivanov_20251108T103045_a1b2c3d4.pdf")
        True
        >>> validate_storage_filename("invalid_filename.pdf")
        False
    """
    try:
        parse_storage_filename(storage_filename)
        return True
    except ValueError:
        return False
