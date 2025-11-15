"""
Query Module - Logging Configuration.

JSON 8 text D>@<0B8@>20=85 A ?>445@6:>9 structured logging.
!;54C5B 0@E8B5:BC@=K< ?0BB5@=0< Ingester Module.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from pythonjsonlogger.json import JsonFormatter

from app.core.config import settings


class CustomJsonFormatter(JsonFormatter):
    """
    0AB><=K9 JSON formatter A 4>?>;=8B5;L=K<8 ?>;O<8 4;O Query Module.

    >102;O5B AB0=40@B=K5 ?>;O: timestamp, level, logger, module, function, line.
    >102;O5B context: app_name 4;O 845=B8D8:0F88 <>4C;O 2 ;>30E.
    """

    def add_fields(self, log_record, record, message_dict):
        """>102;O5B 4>?>;=8B5;L=K5 ?>;O 2 JSON ;>3."""
        super().add_fields(log_record, record, message_dict)

        # >102;O5< AB0=40@B=K5 ?>;O
        log_record['timestamp'] = self.formatTime(record, self.datefmt)
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        log_record['line'] = record.lineno

        # >102;O5< application context
        log_record['app_name'] = settings.app_name


def setup_logging(
    level: Optional[str] = None,
    log_format: Optional[str] = None,
    log_file: Optional[Path] = None
) -> None:
    """
    0AB@>9:0 ;>38@>20=8O 4;O Query Module.

    Args:
        level: #@>25=L ;>38@>20=8O (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: $>@<0B ;>3>2 (json, text)
        log_file: CBL : D09;C ;>3>2 (>?F8>=0;L=>)

    @8<5@K:
        >>> setup_logging(level="DEBUG", log_format="text")
        >>> setup_logging(level="INFO", log_format="json", log_file=Path("/var/log/query.log"))
    """
    # A?>;L7C5< =0AB@>9:8 87 config 5A;8 =5 ?5@540=K ?0@0<5B@K
    log_level = level or settings.log_level
    format_type = log_format or settings.log_format
    file_path = log_file

    # 0AB@>9:0 :>@=52>3> ;>335@0
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # #40;O5< ACI5AB2CNI85 handlers
    root_logger.handlers.clear()

    # !>7405< handler 4;O :>=A>;8
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # K1>@ formatter'0
    if format_type == "json":
        # JSON D>@<0B 4;O production (>1O70B5;5= A>3;0A=> CLAUDE.md)
        formatter = CustomJsonFormatter(
            fmt='%(timestamp)s %(level)s %(name)s %(message)s',
            datefmt='%Y-%m-%dT%H:%M:%S'
        )
    else:
        # Text D>@<0B 4;O development (B>;L:> 4;O ;>:0;L=>9 @07@01>B:8)
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ?F8>=0;L=> 4>102;O5< file handler
    if file_path:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(file_path, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # 0AB@>9:0 C@>2=59 ;>38@>20=8O 4;O 181;8>B5:
    # #<5=LH05< verbosity uvicorn 8 fastapi
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # >38@C5< CA?5H=CN 8=8F80;870F8N
    logger = logging.getLogger(__name__)
    logger.info(
        "Query Module logging configured",
        extra={
            "log_level": log_level,
            "log_format": format_type,
            "log_file": str(file_path) if file_path else None
        }
    )


def get_logger(name: str) -> logging.Logger:
    """
    >;CG8BL logger A 7040==K< 8<5=5<.

    Args:
        name: <O ;>335@0 (>1KG=> __name__ <>4C;O)

    Returns:
        0AB@>5==K9 logger instance

    @8<5@:
        >>> logger = get_logger(__name__)
        >>> logger.info("Search query executed", extra={"query": "test", "results": 10})
    """
    return logging.getLogger(name)
