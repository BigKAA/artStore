"""
Модуль расчёта адаптивных порогов ёмкости Storage Element.

Реализует динамические пороги на основе размера SE по формуле:
threshold = max(percentage, minimum_GB)

Это обеспечивает:
- Для больших SE (>1TB): процентные пороги работают корректно
- Для малых SE (<1TB): минимальные GB гарантируют безопасный буфер
"""

from enum import Enum
from typing import Optional


class CapacityStatus(Enum):
    """
    Многоуровневый статус ёмкости хранилища.

    Переходы: OK → WARNING → CRITICAL → FULL
    """
    OK = "ok"           # Нормальное состояние, приём файлов разрешён
    WARNING = "warning"  # Предупреждение, начать мониторинг
    CRITICAL = "critical"  # Критический уровень, только мелкие файлы
    FULL = "full"        # Полное, приём файлов запрещён


# Конфигурация порогов по режимам хранилища
# Формат: (percentage, minimum_gb)
THRESHOLDS_CONFIG = {
    "rw": {
        # RW хранилище - основное долгосрочное хранение
        # Требует больший буфер для надёжности
        "warning": (0.15, 150),   # 15% или 150GB свободного места
        "critical": (0.08, 80),   # 8% или 80GB свободного места
        "full": (0.02, 20),       # 2% или 20GB свободного места
    },
    "edit": {
        # Edit хранилище - временное хранение
        # Меньший буфер, так как файлы будут перемещены
        "warning": (0.10, 100),   # 10% или 100GB свободного места
        "critical": (0.05, 50),   # 5% или 50GB свободного места
        "full": (0.01, 10),       # 1% или 10GB свободного места
    },
}


def calculate_adaptive_threshold(
    total_capacity_bytes: int,
    mode: str
) -> Optional[dict]:
    """
    Рассчитывает адаптивные пороги на основе размера SE и режима.

    Формула: required_free_gb = max(total_gb * percentage, minimum_gb)

    Это гарантирует:
    - Для SE 10TB в RW режиме: warning при 1.5TB (15%) свободного места
    - Для SE 500GB в RW режиме: warning при 150GB (30%) свободного места

    Args:
        total_capacity_bytes: Общая ёмкость в байтах
        mode: Режим хранилища ("rw", "edit", "ro", "ar")

    Returns:
        dict с порогами или None для ro/ar режимов (запись запрещена)

    Example:
        >>> thresholds = calculate_adaptive_threshold(10 * 1024**4, "rw")  # 10TB
        >>> thresholds["warning_threshold"]  # ~85% (при 15% свободного)
        85.0
    """
    # Для режимов только чтения пороги не нужны
    if mode not in THRESHOLDS_CONFIG:
        return None

    config = THRESHOLDS_CONFIG[mode]
    total_gb = total_capacity_bytes / (1024 ** 3)

    # Рассчитываем свободное место в GB для каждого уровня
    # Формула: max(total_gb * percentage, minimum_gb)
    warning_pct, warning_min = config["warning"]
    critical_pct, critical_min = config["critical"]
    full_pct, full_min = config["full"]

    warning_free_gb = max(total_gb * warning_pct, warning_min)
    critical_free_gb = max(total_gb * critical_pct, critical_min)
    full_free_gb = max(total_gb * full_pct, full_min)

    # Конвертируем свободное место в процент заполнения (threshold)
    # threshold = 100% - (free_gb / total_gb * 100%)
    def free_to_threshold(free_gb: float) -> float:
        if total_gb <= 0:
            return 100.0
        threshold = (1 - free_gb / total_gb) * 100
        # Ограничиваем диапазон 0-100%
        return max(0.0, min(100.0, threshold))

    return {
        # Пороги заполнения (когда достигнут этот %, срабатывает статус)
        "warning_threshold": free_to_threshold(warning_free_gb),
        "critical_threshold": free_to_threshold(critical_free_gb),
        "full_threshold": free_to_threshold(full_free_gb),
        # Требуемое свободное место в GB для каждого уровня
        "warning_free_gb": warning_free_gb,
        "critical_free_gb": critical_free_gb,
        "full_free_gb": full_free_gb,
    }


def get_capacity_status(
    used_bytes: int,
    total_bytes: int,
    thresholds: Optional[dict]
) -> CapacityStatus:
    """
    Определяет статус ёмкости на основе адаптивных порогов.

    Args:
        used_bytes: Использованное место в байтах
        total_bytes: Общая ёмкость в байтах
        thresholds: Пороги от calculate_adaptive_threshold() или None

    Returns:
        CapacityStatus: OK, WARNING, CRITICAL или FULL

    Example:
        >>> status = get_capacity_status(900 * 1024**3, 1000 * 1024**3, thresholds)
        >>> status == CapacityStatus.CRITICAL
        True
    """
    # Для режимов без порогов всегда OK (ro/ar)
    if thresholds is None:
        return CapacityStatus.OK

    # Защита от деления на ноль
    if total_bytes <= 0:
        return CapacityStatus.FULL

    # Текущий процент заполнения
    used_percent = (used_bytes / total_bytes) * 100

    # Проверяем пороги от наиболее критичного к наименее критичному
    if used_percent >= thresholds["full_threshold"]:
        return CapacityStatus.FULL
    elif used_percent >= thresholds["critical_threshold"]:
        return CapacityStatus.CRITICAL
    elif used_percent >= thresholds["warning_threshold"]:
        return CapacityStatus.WARNING

    return CapacityStatus.OK


def can_accept_file(
    file_size_bytes: int,
    used_bytes: int,
    total_bytes: int,
    thresholds: Optional[dict]
) -> tuple[bool, str]:
    """
    Проверяет, может ли SE принять файл заданного размера.

    Pre-flight check перед началом загрузки.

    Args:
        file_size_bytes: Размер файла в байтах
        used_bytes: Текущее использованное место
        total_bytes: Общая ёмкость
        thresholds: Адаптивные пороги

    Returns:
        tuple[bool, str]: (можно ли принять, причина отказа или "ok")

    Example:
        >>> can_accept, reason = can_accept_file(10 * 1024**3, used, total, thresholds)
        >>> if not can_accept:
        ...     raise InsufficientSpaceError(reason)
    """
    # Для режимов без порогов - проверяем только физическое место
    if thresholds is None:
        return False, "storage_mode_readonly"

    # Проверяем текущий статус
    current_status = get_capacity_status(used_bytes, total_bytes, thresholds)

    if current_status == CapacityStatus.FULL:
        return False, "storage_full"

    # Проверяем, хватит ли места после загрузки
    projected_used = used_bytes + file_size_bytes
    projected_status = get_capacity_status(projected_used, total_bytes, thresholds)

    if projected_status == CapacityStatus.FULL:
        return False, "insufficient_space_after_upload"

    # В критическом состоянии принимаем только мелкие файлы (<100MB)
    if current_status == CapacityStatus.CRITICAL:
        max_file_size_critical = 100 * 1024 * 1024  # 100MB
        if file_size_bytes > max_file_size_critical:
            return False, "file_too_large_for_critical_capacity"

    return True, "ok"


def format_capacity_info(
    used_bytes: int,
    total_bytes: int,
    thresholds: Optional[dict]
) -> dict:
    """
    Форматирует информацию о ёмкости для логирования и API.

    Args:
        used_bytes: Использованное место в байтах
        total_bytes: Общая ёмкость в байтах
        thresholds: Адаптивные пороги

    Returns:
        dict: Форматированная информация о ёмкости
    """
    free_bytes = total_bytes - used_bytes
    used_percent = (used_bytes / total_bytes * 100) if total_bytes > 0 else 0

    status = get_capacity_status(used_bytes, total_bytes, thresholds)

    result = {
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "total_gb": round(total_bytes / (1024 ** 3), 2),
        "used_gb": round(used_bytes / (1024 ** 3), 2),
        "free_gb": round(free_bytes / (1024 ** 3), 2),
        "used_percent": round(used_percent, 2),
        "status": status.value,
    }

    if thresholds:
        result["thresholds"] = {
            "warning_percent": round(thresholds["warning_threshold"], 2),
            "critical_percent": round(thresholds["critical_threshold"], 2),
            "full_percent": round(thresholds["full_threshold"], 2),
            "warning_free_gb": round(thresholds["warning_free_gb"], 2),
            "critical_free_gb": round(thresholds["critical_free_gb"], 2),
            "full_free_gb": round(thresholds["full_free_gb"], 2),
        }

    return result
