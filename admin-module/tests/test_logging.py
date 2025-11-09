"""
Тесты для JSON логирования.
Проверяет корректность настройки и формата логов.
"""

import json
import logging
import pytest
from io import StringIO

from app.core.logging_config import setup_logging, get_logger, CustomJsonFormatter


def test_json_logging_format():
    """
    Тест проверяет что логи выводятся в валидном JSON формате
    со всеми обязательными полями.
    """
    # Создаем строковый буфер для захвата логов
    log_capture = StringIO()

    # Настраиваем handler для записи в буфер
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.INFO)

    # Применяем JSON formatter
    formatter = CustomJsonFormatter('%(message)s', timestamp=True)
    handler.setFormatter(formatter)

    # Создаем тестовый logger
    test_logger = logging.getLogger('test_json_logging')
    test_logger.setLevel(logging.INFO)
    test_logger.addHandler(handler)

    # Записываем тестовое сообщение
    test_logger.info("Test message", extra={'user_id': 123, 'request_id': 'abc-123'})

    # Получаем вывод
    log_output = log_capture.getvalue().strip()

    # Парсим JSON
    log_entry = json.loads(log_output)

    # Проверяем обязательные поля
    assert 'message' in log_entry
    assert log_entry['message'] == 'Test message'

    assert 'timestamp' in log_entry
    assert 'level' in log_entry
    assert log_entry['level'] == 'INFO'

    assert 'logger' in log_entry
    assert log_entry['logger'] == 'test_json_logging'

    assert 'module' in log_entry
    assert 'function' in log_entry
    assert 'line' in log_entry

    # Проверяем дополнительные поля
    assert 'user_id' in log_entry
    assert log_entry['user_id'] == 123

    assert 'request_id' in log_entry
    assert log_entry['request_id'] == 'abc-123'


def test_setup_logging_json_format():
    """
    Тест проверяет настройку логирования в JSON формате.
    """
    # Сбрасываем текущую конфигурацию
    logging.root.handlers = []

    # Настраиваем логирование
    setup_logging(level='INFO', format_type='json')

    # Проверяем что handler установлен
    assert len(logging.root.handlers) > 0

    # Проверяем что formatter это CustomJsonFormatter
    handler = logging.root.handlers[0]
    assert isinstance(handler.formatter, CustomJsonFormatter)


def test_setup_logging_text_format_requires_debug():
    """
    Тест проверяет что text формат разрешен только в debug режиме.
    """
    # Сбрасываем текущую конфигурацию
    logging.root.handlers = []

    # Временно устанавливаем debug=False
    from app.core.config import settings
    original_debug = settings.debug
    settings.debug = False

    try:
        # Попытка использовать text формат в production должна вызвать ошибку
        with pytest.raises(ValueError, match="Text log format is only allowed in development mode"):
            setup_logging(level='INFO', format_type='text')
    finally:
        settings.debug = original_debug


def test_get_logger():
    """
    Тест проверяет функцию get_logger.
    """
    logger = get_logger('test_module')

    assert isinstance(logger, logging.Logger)
    assert logger.name == 'test_module'


def test_json_logging_with_exception():
    """
    Тест проверяет логирование исключений в JSON формате.
    """
    # Создаем строковый буфер для захвата логов
    log_capture = StringIO()

    # Настраиваем handler
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.ERROR)

    # Применяем JSON formatter
    formatter = CustomJsonFormatter('%(message)s', timestamp=True)
    handler.setFormatter(formatter)

    # Создаем тестовый logger
    test_logger = logging.getLogger('test_exception_logging')
    test_logger.setLevel(logging.ERROR)
    test_logger.addHandler(handler)

    # Генерируем исключение и логируем
    try:
        raise ValueError("Test exception")
    except ValueError as e:
        test_logger.error(
            f"Error occurred: {str(e)}",
            extra={'error_type': type(e).__name__},
            exc_info=True
        )

    # Получаем вывод
    log_output = log_capture.getvalue()

    # Первая строка должна быть JSON
    first_line = log_output.split('\n')[0]
    log_entry = json.loads(first_line)

    # Проверяем поля
    assert 'message' in log_entry
    assert 'Error occurred: Test exception' in log_entry['message']
    assert 'error_type' in log_entry
    assert log_entry['error_type'] == 'ValueError'
    assert 'level' in log_entry
    assert log_entry['level'] == 'ERROR'

    # Проверяем что есть traceback (в следующих строках после JSON)
    assert 'Traceback' in log_output
    assert 'ValueError: Test exception' in log_output


def test_logging_levels():
    """
    Тест проверяет различные уровни логирования.
    """
    # Создаем строковый буфер
    log_capture = StringIO()

    # Настраиваем handler
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.DEBUG)

    # Применяем JSON formatter
    formatter = CustomJsonFormatter('%(message)s', timestamp=True)
    handler.setFormatter(formatter)

    # Создаем тестовый logger
    test_logger = logging.getLogger('test_levels')
    test_logger.setLevel(logging.DEBUG)
    test_logger.addHandler(handler)

    # Логируем на разных уровнях
    test_logger.debug("Debug message")
    test_logger.info("Info message")
    test_logger.warning("Warning message")
    test_logger.error("Error message")
    test_logger.critical("Critical message")

    # Получаем все строки
    log_lines = log_capture.getvalue().strip().split('\n')

    # Должно быть 5 строк
    assert len(log_lines) == 5

    # Проверяем уровни
    levels = []
    for line in log_lines:
        log_entry = json.loads(line)
        levels.append(log_entry['level'])

    assert levels == ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
