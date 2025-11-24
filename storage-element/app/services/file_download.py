"""
File download service для Storage Element.

Реализует streaming download с HTTP Range requests support (RFC 7233).
"""

from pathlib import Path
from typing import Optional, Tuple, List
from datetime import datetime, timezone
import hashlib
import re

from app.core.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)
config = get_config()


class RangeNotSatisfiableError(Exception):
    """Raised when requested range is not satisfiable."""
    pass


class FileDownloadService:
    """
    Service для загрузки файлов с HTTP Range requests support.

    Features:
    - Streaming download для больших файлов
    - HTTP Range requests (RFC 7233)
    - ETag generation для кеширования
    - Resumable downloads
    - Path traversal protection
    """

    def __init__(self):
        """Initialize download service."""
        self.config = config
        self.logger = logger
        self.storage_base = Path(config.storage.local_base_path)

    def get_file_path(
        self,
        storage_path: str,
        storage_filename: str
    ) -> Path:
        """
        Get absolute file path с path traversal protection.

        Args:
            storage_path: Relative storage path (e.g., "2024/01/01/12")
            storage_filename: Storage filename

        Returns:
            Path: Absolute file path

        Raises:
            ValueError: Path traversal attempt detected
        """
        # Construct full path
        full_path = self.storage_base / storage_path / storage_filename

        # Resolve to absolute path
        resolved_path = full_path.resolve()

        # Ensure path is within storage_base (path traversal protection)
        try:
            resolved_path.relative_to(self.storage_base.resolve())
        except ValueError:
            raise ValueError(
                f"Path traversal attempt detected: {storage_path}/{storage_filename}"
            )

        return resolved_path

    def generate_etag(
        self,
        file_path: Path,
        file_size: int,
        modified_time: datetime
    ) -> str:
        """
        Generate ETag для файла.

        ETag based on: file_path + size + modified_time для эффективности.
        Не используем полный SHA256 для performance.

        Args:
            file_path: Path to file
            file_size: File size in bytes
            modified_time: Last modification time

        Returns:
            str: ETag value
        """
        etag_data = f"{file_path}:{file_size}:{modified_time.isoformat()}"
        etag_hash = hashlib.md5(etag_data.encode()).hexdigest()
        return f'"{etag_hash}"'

    def parse_range_header(
        self,
        range_header: str,
        file_size: int
    ) -> List[Tuple[int, int]]:
        """
        Parse HTTP Range header и validate ranges.

        Supports:
        - bytes=0-1023 (single range)
        - bytes=0-1023,2048-4095 (multiple ranges)
        - bytes=-500 (suffix range - last 500 bytes)
        - bytes=1000- (open range - from position to end)

        Args:
            range_header: Range header value (e.g., "bytes=0-1023")
            file_size: Total file size in bytes

        Returns:
            List[Tuple[int, int]]: List of (start, end) byte positions

        Raises:
            RangeNotSatisfiableError: Invalid or unsatisfiable range
        """
        # Range header format: "bytes=start-end,start-end,..."
        if not range_header.startswith("bytes="):
            raise RangeNotSatisfiableError("Range header must start with 'bytes='")

        range_spec = range_header[6:]  # Remove "bytes=" prefix
        range_parts = range_spec.split(",")

        ranges = []

        for part in range_parts:
            part = part.strip()

            # Suffix range: bytes=-500 (last 500 bytes)
            if part.startswith("-"):
                try:
                    suffix_length = int(part[1:])
                except ValueError:
                    raise RangeNotSatisfiableError(f"Invalid suffix range: {part}")

                if suffix_length <= 0:
                    raise RangeNotSatisfiableError("Suffix length must be positive")

                start = max(0, file_size - suffix_length)
                end = file_size - 1
                ranges.append((start, end))
                continue

            # Regular range: bytes=start-end or bytes=start-
            match = re.match(r"(\d+)-(\d*)", part)
            if not match:
                raise RangeNotSatisfiableError(f"Invalid range format: {part}")

            start_str, end_str = match.groups()

            try:
                start = int(start_str)
            except ValueError:
                raise RangeNotSatisfiableError(f"Invalid start position: {start_str}")

            # Open range: bytes=1000-
            if not end_str:
                end = file_size - 1
            else:
                try:
                    end = int(end_str)
                except ValueError:
                    raise RangeNotSatisfiableError(f"Invalid end position: {end_str}")

            # Validate range
            if start < 0 or end < 0:
                raise RangeNotSatisfiableError("Range positions must be non-negative")

            if start > end:
                raise RangeNotSatisfiableError(f"Start position ({start}) > end position ({end})")

            if start >= file_size:
                raise RangeNotSatisfiableError(
                    f"Start position ({start}) >= file size ({file_size})"
                )

            # Clamp end to file size
            end = min(end, file_size - 1)

            ranges.append((start, end))

        return ranges

    def stream_file(
        self,
        file_path: Path,
        start: int = 0,
        end: Optional[int] = None,
        chunk_size: int = 64 * 1024  # 64KB chunks
    ):
        """
        Stream file content с заданного диапазона.

        Args:
            file_path: Path to file
            start: Start byte position (inclusive)
            end: End byte position (inclusive), None for entire file
            chunk_size: Chunk size for streaming (default 64KB)

        Yields:
            bytes: File chunks
        """
        file_size = file_path.stat().st_size

        # Default end to file size
        if end is None:
            end = file_size - 1

        # Validate range
        if start < 0 or start >= file_size:
            raise ValueError(f"Invalid start position: {start}")

        if end < start or end >= file_size:
            raise ValueError(f"Invalid end position: {end}")

        bytes_to_read = end - start + 1

        self.logger.info(
            "Streaming file",
            file_path=str(file_path),
            start=start,
            end=end,
            bytes_to_read=bytes_to_read
        )

        with open(file_path, "rb") as f:
            # Seek to start position
            f.seek(start)

            bytes_read = 0

            while bytes_read < bytes_to_read:
                # Calculate chunk size for this iteration
                current_chunk_size = min(chunk_size, bytes_to_read - bytes_read)

                # Read chunk
                chunk = f.read(current_chunk_size)

                if not chunk:
                    break

                bytes_read += len(chunk)
                yield chunk

        self.logger.info(
            "File streaming completed",
            file_path=str(file_path),
            bytes_read=bytes_read
        )

    def stream_multipart_ranges(
        self,
        file_path: Path,
        ranges: List[Tuple[int, int]],
        content_type: str,
        chunk_size: int = 64 * 1024
    ):
        """
        Stream multiple ranges в multipart/byteranges format.

        Format (RFC 7233):
        --BOUNDARY
        Content-Type: application/pdf
        Content-Range: bytes 0-1023/5000

        [bytes 0-1023]
        --BOUNDARY
        Content-Type: application/pdf
        Content-Range: bytes 2048-4095/5000

        [bytes 2048-4095]
        --BOUNDARY--

        Args:
            file_path: Path to file
            ranges: List of (start, end) byte ranges
            content_type: MIME type of file
            chunk_size: Chunk size for streaming

        Yields:
            bytes: Multipart response chunks
        """
        file_size = file_path.stat().st_size
        boundary = "RANGE_SEPARATOR"

        for start, end in ranges:
            # Part header
            part_header = (
                f"\r\n--{boundary}\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Range: bytes {start}-{end}/{file_size}\r\n"
                f"\r\n"
            )

            yield part_header.encode()

            # Part body (file data)
            for chunk in self.stream_file(file_path, start, end, chunk_size):
                yield chunk

        # Final boundary
        final_boundary = f"\r\n--{boundary}--\r\n"
        yield final_boundary.encode()
