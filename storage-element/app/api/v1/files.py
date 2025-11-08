"""
File operations API endpoints для Storage Element.

Endpoints для загрузки, скачивания, удаления файлов с streaming support.
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, status, Depends, Header
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import uuid as uuid_lib

from app.core.config import get_config
from app.core.logging import get_logger
from app.api.deps.database import get_db
from app.services.file_upload import FileUploadService
from app.models import FileMetadata

# Router configuration
router = APIRouter()
logger = get_logger()
config = get_config()


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload file with streaming support",
    description="Upload a file to storage with metadata and retention configuration"
)
async def upload_file(
    file: UploadFile = File(..., description="File to upload"),
    description: Optional[str] = Form(None, description="File description"),
    retention_days: int = Form(365, description="Retention period in days"),
    tags: Optional[str] = Form(None, description="Comma-separated tags"),
    uploaded_by: str = Form(..., description="Username of uploader"),
    uploader_full_name: Optional[str] = Form(None, description="Full name from LDAP"),
    db: Session = Depends(get_db)
):
    """
    Upload file endpoint с streaming support.

    Features:
    - Streaming upload для больших файлов
    - WAL-based transactional safety
    - Atomic file write с fsync
    - Database metadata caching
    - File naming с auto-truncation

    Args:
        file: Uploaded file (multipart/form-data)
        description: Optional file description
        retention_days: Retention period (default 365 days)
        tags: Optional comma-separated tags
        uploaded_by: Username (required for file naming)
        uploader_full_name: Full name from LDAP/AD
        db: Database session dependency

    Returns:
        FileMetadata: Created file metadata with file_id and storage info

    Raises:
        HTTPException 400: Invalid file, size, or parameters
        HTTPException 507: Insufficient storage space
        HTTPException 500: Upload failed or internal error
    """
    logger.info(
        "File upload request",
        original_filename=file.filename,
        content_type=file.content_type,
        uploaded_by=uploaded_by
    )

    try:
        # Parse tags
        tag_list = None
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

        # Initialize upload service
        upload_service = FileUploadService(db=db)

        # Process upload with streaming
        file_metadata = await upload_service.upload_file(
            file=file,
            uploaded_by=uploaded_by,
            uploader_full_name=uploader_full_name,
            description=description,
            retention_days=retention_days,
            tags=tag_list
        )

        logger.info(
            "File uploaded successfully",
            file_id=str(file_metadata.file_id),
            storage_filename=file_metadata.storage_filename,
            file_size=file_metadata.file_size
        )

        # Return metadata as dict
        return file_metadata.to_dict()

    except ValueError as e:
        logger.warning("Invalid upload parameters", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except OSError as e:
        if "No space left" in str(e):
            logger.error("Insufficient storage space", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                detail="Insufficient storage space available"
            )
        logger.error("File system error during upload", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File upload failed due to storage error"
        )
    except Exception as e:
        logger.exception("Unexpected error during file upload", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(e)}"
        )


@router.get(
    "/{file_id}",
    summary="Get file metadata",
    description="Retrieve file metadata by file_id"
)
async def get_file_metadata(
    file_id: str,
    db: Session = Depends(get_db)
):
    """
    Get file metadata by file_id.

    Args:
        file_id: UUID of the file
        db: Database session dependency

    Returns:
        FileMetadata: File metadata dictionary

    Raises:
        HTTPException 404: File not found
    """
    # Convert file_id to UUID
    try:
        file_uuid = uuid_lib.UUID(file_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file_id format"
        )

    file_meta = db.query(FileMetadata).filter_by(file_id=file_uuid).first()

    if not file_meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found"
        )

    return file_meta.to_dict()


@router.get(
    "/search",
    summary="Search files with full-text search",
    description="Search files using PostgreSQL full-text search with advanced filtering"
)
async def search_files(
    q: Optional[str] = None,
    uploaded_by: Optional[str] = None,
    min_size: Optional[int] = None,
    max_size: Optional[int] = None,
    uploaded_after: Optional[str] = None,
    uploaded_before: Optional[str] = None,
    expires_in_days: Optional[int] = None,
    tags: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    Search files с PostgreSQL full-text search и advanced filtering.

    Args:
        q: Full-text search query (searches filename, description, tags)
        uploaded_by: Filter by uploader username
        min_size: Minimum file size in bytes
        max_size: Maximum file size in bytes
        uploaded_after: Filter files uploaded after date (ISO format)
        uploaded_before: Filter files uploaded before date (ISO format)
        expires_in_days: Filter files expiring within N days
        tags: Comma-separated tags to filter by
        limit: Maximum results (default 100, max 1000)
        offset: Pagination offset (default 0)
        db: Database session dependency

    Returns:
        dict: Search results with pagination and match scores
    """
    from app.services.file_search import FileSearchService

    search_service = FileSearchService(db=db)

    # Parse tags
    tag_list = None
    if tags:
        tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]

    # Validate and parse dates
    uploaded_after_dt = None
    uploaded_before_dt = None

    if uploaded_after:
        try:
            uploaded_after_dt = datetime.fromisoformat(uploaded_after.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid uploaded_after date format: {uploaded_after}"
            )

    if uploaded_before:
        try:
            uploaded_before_dt = datetime.fromisoformat(uploaded_before.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid uploaded_before date format: {uploaded_before}"
            )

    # Validate limit
    if limit > 1000:
        limit = 1000

    # Execute search
    results = search_service.search_files(
        search_query=q,
        uploaded_by=uploaded_by,
        min_size=min_size,
        max_size=max_size,
        uploaded_after=uploaded_after_dt,
        uploaded_before=uploaded_before_dt,
        expires_in_days=expires_in_days,
        tags=tag_list,
        limit=limit,
        offset=offset
    )

    return results


@router.get(
    "/{file_id}/download",
    summary="Download file",
    description="Download file with HTTP Range requests support (RFC 7233)"
)
async def download_file(
    file_id: str,
    range_header: Optional[str] = Header(None, alias="Range"),
    if_none_match: Optional[str] = Header(None, alias="If-None-Match"),
    if_modified_since: Optional[str] = Header(None, alias="If-Modified-Since"),
    db: Session = Depends(get_db)
):
    """
    Download file с поддержкой HTTP Range requests.

    Supports:
    - Full file download (200 OK)
    - Single range (206 Partial Content)
    - Multiple ranges (206 Partial Content, multipart/byteranges)
    - Resumable downloads
    - Conditional requests (ETag, If-Modified-Since)

    Args:
        file_id: File UUID
        range_header: Range header (e.g., "bytes=0-1023")
        if_none_match: ETag for conditional request
        if_modified_since: Last modification time for conditional request
        db: Database session dependency

    Returns:
        StreamingResponse: File content stream

    Raises:
        HTTPException 404: File not found
        HTTPException 416: Range Not Satisfiable
        HTTPException 304: Not Modified (cache valid)
    """
    from app.services.file_download import FileDownloadService, RangeNotSatisfiableError

    # Get file metadata from database
    try:
        file_uuid = uuid_lib.UUID(file_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file_id format"
        )

    file_meta = db.query(FileMetadata).filter_by(file_id=file_uuid).first()

    if not file_meta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File {file_id} not found"
        )

    # Initialize download service
    download_service = FileDownloadService()

    # Get file path with path traversal protection
    try:
        file_path = download_service.get_file_path(
            storage_path=file_meta.storage_path,
            storage_filename=file_meta.storage_filename
        )
    except ValueError as e:
        logger.error("Path traversal attempt", file_id=file_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # Check file exists
    if not file_path.exists():
        logger.error("File not found on disk", file_id=file_id, path=str(file_path))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on storage"
        )

    # Get file stats
    file_stat = file_path.stat()
    file_size = file_stat.st_size
    modified_time = datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc)

    # Generate ETag
    etag = download_service.generate_etag(
        file_path=file_path,
        file_size=file_size,
        modified_time=modified_time
    )

    # Check conditional requests
    # If-None-Match (ETag validation)
    if if_none_match and if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    # If-Modified-Since (timestamp validation)
    if if_modified_since:
        try:
            from email.utils import parsedate_to_datetime
            ims_time = parsedate_to_datetime(if_modified_since)
            if modified_time <= ims_time:
                return Response(status_code=status.HTTP_304_NOT_MODIFIED)
        except Exception:
            pass  # Invalid date format, ignore

    # Prepare headers
    headers = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Last-Modified": modified_time.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "Content-Type": file_meta.mime_type or "application/octet-stream",
        "Content-Disposition": f'attachment; filename="{file_meta.original_filename}"'
    }

    # Handle Range request
    if range_header:
        try:
            # Parse ranges
            ranges = download_service.parse_range_header(range_header, file_size)

            # Single range
            if len(ranges) == 1:
                start, end = ranges[0]
                content_length = end - start + 1

                headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
                headers["Content-Length"] = str(content_length)

                logger.info(
                    "Serving single range",
                    file_id=file_id,
                    start=start,
                    end=end,
                    content_length=content_length
                )

                return StreamingResponse(
                    download_service.stream_file(file_path, start, end),
                    status_code=status.HTTP_206_PARTIAL_CONTENT,
                    headers=headers
                )

            # Multiple ranges (multipart/byteranges)
            else:
                boundary = "RANGE_SEPARATOR"
                headers["Content-Type"] = f"multipart/byteranges; boundary={boundary}"

                logger.info(
                    "Serving multiple ranges",
                    file_id=file_id,
                    num_ranges=len(ranges)
                )

                return StreamingResponse(
                    download_service.stream_multipart_ranges(
                        file_path=file_path,
                        ranges=ranges,
                        content_type=file_meta.mime_type or "application/octet-stream"
                    ),
                    status_code=status.HTTP_206_PARTIAL_CONTENT,
                    headers=headers
                )

        except RangeNotSatisfiableError as e:
            logger.warning(
                "Range not satisfiable",
                file_id=file_id,
                range_header=range_header,
                error=str(e)
            )

            return Response(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                headers={
                    "Content-Range": f"bytes */{file_size}"
                }
            )

    # Full file download
    headers["Content-Length"] = str(file_size)

    logger.info(
        "Serving full file",
        file_id=file_id,
        file_size=file_size
    )

    return StreamingResponse(
        download_service.stream_file(file_path),
        status_code=status.HTTP_200_OK,
        headers=headers
    )


@router.get(
    "/",
    summary="List files",
    description="List files with optional filtering"
)
async def list_files(
    uploaded_by: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    List files with pagination and filtering.

    Args:
        uploaded_by: Filter by uploader username
        limit: Maximum number of results (default 100)
        offset: Pagination offset (default 0)
        db: Database session dependency

    Returns:
        dict: List of files and pagination info
    """
    query = db.query(FileMetadata)

    if uploaded_by:
        query = query.filter_by(uploaded_by=uploaded_by)

    total = query.count()
    files = query.order_by(FileMetadata.uploaded_at.desc()).limit(limit).offset(offset).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "files": [f.to_dict() for f in files]
    }
