"""
File search service для Storage Element.

Реализует PostgreSQL full-text search с расширенной фильтрацией.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from app.core.config import get_config
from app.core.logging import get_logger
from app.models import FileMetadata

logger = get_logger(__name__)
config = get_config()


class FileSearchService:
    """
    Service для поиска файлов с PostgreSQL full-text search.

    Features:
    - Full-text search через TSVECTOR + GIN индексы
    - Rank scoring для релевантности результатов
    - Advanced filtering (size, date, tags, retention)
    - Pagination поддержка
    """

    def __init__(self, db: Session):
        """
        Initialize search service.

        Args:
            db: Database session
        """
        self.db = db
        self.config = config
        self.logger = logger

    def search_files(
        self,
        search_query: Optional[str] = None,
        uploaded_by: Optional[str] = None,
        min_size: Optional[int] = None,
        max_size: Optional[int] = None,
        uploaded_after: Optional[datetime] = None,
        uploaded_before: Optional[datetime] = None,
        expires_in_days: Optional[int] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Search files с full-text search и advanced filtering.

        Args:
            search_query: Full-text search query (filename, description, tags)
            uploaded_by: Filter by uploader username
            min_size: Minimum file size in bytes
            max_size: Maximum file size in bytes
            uploaded_after: Files uploaded after this date
            uploaded_before: Files uploaded before this date
            expires_in_days: Files expiring within N days
            tags: List of tags to filter by
            limit: Maximum results
            offset: Pagination offset

        Returns:
            dict: {
                "total": int,
                "limit": int,
                "offset": int,
                "files": List[dict],
                "query": str (optional),
                "search_info": dict (optional)
            }
        """
        # Base query
        query = self.db.query(FileMetadata)

        # Full-text search
        search_rank = None
        if search_query:
            # Convert search query to tsquery
            ts_query = func.plainto_tsquery('english', search_query)

            # Filter by search_vector match
            query = query.filter(
                FileMetadata.search_vector.op('@@')(ts_query)
            )

            # Calculate rank for sorting
            search_rank = func.ts_rank(
                FileMetadata.search_vector,
                ts_query
            ).label('rank')

            # Add rank to select
            query = query.add_columns(search_rank)

            self.logger.info(
                "Full-text search executed",
                search_query=search_query
            )

        # Filter by uploader
        if uploaded_by:
            query = query.filter(FileMetadata.uploaded_by == uploaded_by)

        # Filter by file size
        if min_size is not None:
            query = query.filter(FileMetadata.file_size >= min_size)

        if max_size is not None:
            query = query.filter(FileMetadata.file_size <= max_size)

        # Filter by upload date
        if uploaded_after:
            query = query.filter(FileMetadata.uploaded_at >= uploaded_after)

        if uploaded_before:
            query = query.filter(FileMetadata.uploaded_at <= uploaded_before)

        # Filter by retention expiration
        if expires_in_days is not None:
            expiry_threshold = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
            query = query.filter(
                and_(
                    FileMetadata.retention_expires_at <= expiry_threshold,
                    FileMetadata.retention_expires_at >= datetime.now(timezone.utc)
                )
            )

        # Filter by tags
        if tags:
            # PostgreSQL JSONB contains check
            for tag in tags:
                query = query.filter(
                    func.jsonb_path_exists(
                        FileMetadata.tags,
                        f'$[*] ? (@ == "{tag}")'
                    )
                )

        # Count total before pagination
        total = query.count()

        # Sort by relevance if search query provided, otherwise by date
        if search_rank is not None:
            query = query.order_by(search_rank.desc(), FileMetadata.uploaded_at.desc())
        else:
            query = query.order_by(FileMetadata.uploaded_at.desc())

        # Pagination
        query = query.limit(limit).offset(offset)

        # Execute query
        if search_rank is not None:
            results = query.all()
            files = []
            for file_meta, rank in results:
                file_dict = file_meta.to_dict()
                file_dict['search_rank'] = float(rank)
                files.append(file_dict)
        else:
            results = query.all()
            files = [f.to_dict() for f in results]

        self.logger.info(
            "Search completed",
            total=total,
            returned=len(files),
            has_search_query=search_query is not None
        )

        # Build response
        response = {
            "total": total,
            "limit": limit,
            "offset": offset,
            "files": files
        }

        # Add search metadata if search query was used
        if search_query:
            response["query"] = search_query
            response["search_info"] = {
                "ranked": True,
                "language": "english"
            }

        return response

    def suggest_similar_files(
        self,
        file_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find similar files based on filename and description.

        Args:
            file_id: Reference file ID
            limit: Maximum similar files to return

        Returns:
            List of similar file metadata dicts with similarity scores
        """
        # Get reference file
        ref_file = self.db.query(FileMetadata).filter_by(file_id=file_id).first()

        if not ref_file:
            return []

        # Build similarity query using search_vector
        # Use filename + description as search query
        search_text = f"{ref_file.original_filename} {ref_file.description or ''}"
        ts_query = func.plainto_tsquery('english', search_text)

        # Calculate similarity rank
        similarity_rank = func.ts_rank(
            FileMetadata.search_vector,
            ts_query
        ).label('similarity')

        # Query for similar files (excluding the reference file)
        query = self.db.query(FileMetadata, similarity_rank).filter(
            and_(
                FileMetadata.file_id != file_id,
                FileMetadata.search_vector.op('@@')(ts_query)
            )
        ).order_by(
            similarity_rank.desc()
        ).limit(limit)

        results = query.all()

        similar_files = []
        for file_meta, similarity in results:
            file_dict = file_meta.to_dict()
            file_dict['similarity_score'] = float(similarity)
            similar_files.append(file_dict)

        return similar_files
