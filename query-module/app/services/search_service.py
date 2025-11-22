"""
Query Module - Search Service.

Реализует поиск файлов с использованием:
- PostgreSQL Full-Text Search (GIN индексы)
- Multi-level caching (Local → Redis → PostgreSQL)
- Различные режимы поиска (exact, partial, fulltext)
- Ранжирование результатов по релевантности
"""

import logging
import hashlib
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FileMetadata, SearchHistory
from app.schemas.search import (
    SearchRequest,
    SearchResponse,
    FileMetadataResponse,
    SearchMode,
    SortField,
    SortOrder
)
from app.services.cache_service import cache_service
from app.core.config import settings

logger = logging.getLogger(__name__)


class SearchService:
    """
    Сервис поиска файлов с PostgreSQL Full-Text Search.

    Поддерживает:
    - Exact match (точное совпадение)
    - Partial match (частичное совпадение через LIKE)
    - Full-text search (PostgreSQL ts_rank через GIN индексы)
    - Multi-level caching результатов
    - Фильтрация по различным атрибутам
    """

    def __init__(self, db: AsyncSession):
        """
        Инициализация Search Service.

        Args:
            db: Async database session
        """
        self.db = db

    def _compute_search_hash(self, search_request: SearchRequest) -> str:
        """
        Вычисление хеша параметров поиска для кеширования.

        Args:
            search_request: Параметры поиска

        Returns:
            str: SHA256 хеш параметров
        """
        # Сериализация параметров в JSON (сортированный для консистентности)
        params = {
            "query": search_request.query,
            "filename": search_request.filename,
            "file_extension": search_request.file_extension,
            "tags": sorted(search_request.tags) if search_request.tags else None,
            "username": search_request.username,
            "min_size": search_request.min_size,
            "max_size": search_request.max_size,
            "created_after": search_request.created_after.isoformat() if search_request.created_after else None,
            "created_before": search_request.created_before.isoformat() if search_request.created_before else None,
            "mode": search_request.mode.value,
            "limit": search_request.limit,
            "offset": search_request.offset,
            "sort_by": search_request.sort_by.value,
            "sort_order": search_request.sort_order.value,
        }

        params_json = json.dumps(params, sort_keys=True)
        return hashlib.sha256(params_json.encode()).hexdigest()

    async def search_files(self, search_request: SearchRequest) -> SearchResponse:
        """
        Поиск файлов с кешированием результатов.

        Args:
            search_request: Параметры поиска

        Returns:
            SearchResponse: Результаты поиска с метаданными
        """
        start_time = datetime.utcnow()

        # Проверка кеша (если включено)
        search_hash = self._compute_search_hash(search_request)
        if settings.cache.cache_search_results:
            cached_results = self._get_cached_search(search_hash)
            if cached_results:
                logger.info(
                    "Search cache hit",
                    extra={"search_hash": search_hash}
                )
                return SearchResponse(**cached_results)

        # Построение query
        query = self._build_search_query(search_request)

        # Выполнение поиска
        result = await self.db.execute(query)
        files = result.scalars().all()

        # Подсчет total count (без LIMIT/OFFSET)
        count_query = self._build_count_query(search_request)
        count_result = await self.db.execute(count_query)
        total_count = count_result.scalar() or 0

        # Конвертация в response schema
        file_responses = [
            FileMetadataResponse(
                id=file.id,
                filename=file.filename,
                storage_filename=file.storage_filename,
                file_size=file.file_size,
                mime_type=file.mime_type,
                sha256_hash=file.sha256_hash,
                username=file.username,
                tags=file.tags or [],
                description=file.description,
                created_at=file.created_at,
                updated_at=file.updated_at,
                storage_element_id=file.storage_element_id,
                relevance_score=None  # TODO: implement relevance scoring для FTS
            )
            for file in files
        ]

        response = SearchResponse(
            results=file_responses,
            total_count=total_count,
            limit=search_request.limit,
            offset=search_request.offset,
            has_more=(search_request.offset + len(file_responses)) < total_count
        )

        # Сохранение в кеш
        if settings.cache.cache_search_results:
            self._cache_search_results(search_hash, response.dict())

        # Запись в search history
        response_time_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        await self._record_search_history(search_request, len(file_responses), response_time_ms)

        logger.info(
            "Search completed",
            extra={
                "mode": search_request.mode.value,
                "results_count": len(file_responses),
                "total_count": total_count,
                "response_time_ms": response_time_ms
            }
        )

        return response

    def _build_search_query(self, search_request: SearchRequest):
        """Построение SQLAlchemy query для поиска."""
        query = select(FileMetadata)

        # Применение фильтров
        conditions = []

        # Full-text search (если mode == FULLTEXT и есть query)
        if search_request.mode == SearchMode.FULLTEXT and search_request.query:
            # PostgreSQL ts_query для full-text search
            ts_query = func.plainto_tsquery('russian', search_request.query)
            conditions.append(
                FileMetadata.search_vector.op('@@')(ts_query)
            )

        # Partial search (через LIKE)
        elif search_request.mode == SearchMode.PARTIAL and search_request.query:
            conditions.append(
                or_(
                    FileMetadata.filename.ilike(f"%{search_request.query}%"),
                    FileMetadata.description.ilike(f"%{search_request.query}%")
                )
            )

        # Exact match
        elif search_request.mode == SearchMode.EXACT and search_request.query:
            conditions.append(
                or_(
                    FileMetadata.filename == search_request.query,
                    FileMetadata.description == search_request.query
                )
            )

        # Фильтр по filename
        if search_request.filename:
            conditions.append(
                FileMetadata.filename.ilike(f"%{search_request.filename}%")
            )

        # Фильтр по file_extension
        if search_request.file_extension:
            conditions.append(
                FileMetadata.filename.ilike(f"%{search_request.file_extension}")
            )

        # Фильтр по тегам (PostgreSQL ARRAY overlap operator)
        if search_request.tags:
            conditions.append(
                FileMetadata.tags.op('&&')(search_request.tags)
            )

        # Фильтр по username
        if search_request.username:
            conditions.append(
                FileMetadata.username == search_request.username
            )

        # Фильтр по размеру файла
        if search_request.min_size is not None:
            conditions.append(
                FileMetadata.file_size >= search_request.min_size
            )

        if search_request.max_size is not None:
            conditions.append(
                FileMetadata.file_size <= search_request.max_size
            )

        # Фильтр по дате создания
        if search_request.created_after:
            conditions.append(
                FileMetadata.created_at >= search_request.created_after
            )

        if search_request.created_before:
            conditions.append(
                FileMetadata.created_at <= search_request.created_before
            )

        # Применение всех условий
        if conditions:
            query = query.where(and_(*conditions))

        # Сортировка
        if search_request.sort_by == SortField.CREATED_AT:
            sort_column = FileMetadata.created_at
        elif search_request.sort_by == SortField.UPDATED_AT:
            sort_column = FileMetadata.updated_at
        elif search_request.sort_by == SortField.FILE_SIZE:
            sort_column = FileMetadata.file_size
        elif search_request.sort_by == SortField.FILENAME:
            sort_column = FileMetadata.filename
        else:  # RELEVANCE для FTS
            # TODO: implement ts_rank sorting для full-text search
            sort_column = FileMetadata.created_at

        if search_request.sort_order == SortOrder.DESC:
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # LIMIT and OFFSET
        query = query.limit(search_request.limit).offset(search_request.offset)

        return query

    def _build_count_query(self, search_request: SearchRequest):
        """Построение count query (без LIMIT/OFFSET)."""
        query = select(func.count(FileMetadata.id))

        # Применение тех же фильтров (код идентичен _build_search_query)
        conditions = []

        if search_request.mode == SearchMode.FULLTEXT and search_request.query:
            ts_query = func.plainto_tsquery('russian', search_request.query)
            conditions.append(FileMetadata.search_vector.op('@@')(ts_query))

        elif search_request.mode == SearchMode.PARTIAL and search_request.query:
            conditions.append(
                or_(
                    FileMetadata.filename.ilike(f"%{search_request.query}%"),
                    FileMetadata.description.ilike(f"%{search_request.query}%")
                )
            )

        elif search_request.mode == SearchMode.EXACT and search_request.query:
            conditions.append(
                or_(
                    FileMetadata.filename == search_request.query,
                    FileMetadata.description == search_request.query
                )
            )

        if search_request.filename:
            conditions.append(FileMetadata.filename.ilike(f"%{search_request.filename}%"))

        if search_request.file_extension:
            conditions.append(FileMetadata.filename.ilike(f"%{search_request.file_extension}"))

        if search_request.tags:
            conditions.append(FileMetadata.tags.op('&&')(search_request.tags))

        if search_request.username:
            conditions.append(FileMetadata.username == search_request.username)

        if search_request.min_size is not None:
            conditions.append(FileMetadata.file_size >= search_request.min_size)

        if search_request.max_size is not None:
            conditions.append(FileMetadata.file_size <= search_request.max_size)

        if search_request.created_after:
            conditions.append(FileMetadata.created_at >= search_request.created_after)

        if search_request.created_before:
            conditions.append(FileMetadata.created_at <= search_request.created_before)

        if conditions:
            query = query.where(and_(*conditions))

        return query

    def _get_cached_search(self, search_hash: str) -> Optional[Dict[str, Any]]:
        """Получение результатов поиска из кеша."""
        # TODO: implement caching через cache_service
        return None

    def _cache_search_results(self, search_hash: str, results: Dict[str, Any]) -> None:
        """Сохранение результатов поиска в кеш."""
        # TODO: implement caching через cache_service
        pass

    async def _record_search_history(
        self,
        search_request: SearchRequest,
        results_count: int,
        response_time_ms: int
    ) -> None:
        """Запись поискового запроса в историю."""
        try:
            history = SearchHistory(
                query_text=search_request.query,
                search_mode=search_request.mode.value,
                filters_applied=json.dumps({
                    "filename": search_request.filename,
                    "tags": search_request.tags,
                    "username": search_request.username,
                    "min_size": search_request.min_size,
                    "max_size": search_request.max_size,
                }),
                results_count=results_count,
                response_time_ms=response_time_ms,
                username=search_request.username
            )

            self.db.add(history)
            await self.db.commit()

        except Exception as e:
            logger.warning(
                "Failed to record search history",
                extra={"error": str(e)}
            )
            # Не прерываем поиск из-за ошибки логирования
            await self.db.rollback()

    async def get_file_by_id(self, file_id: str) -> Optional[FileMetadata]:
        """Получение метаданных файла по ID.

        Args:
            file_id: Уникальный идентификатор файла

        Returns:
            FileMetadata или None если файл не найден
        """
        try:
            query = select(FileMetadata).where(FileMetadata.id == file_id)
            result = await self.db.execute(query)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(
                "Failed to get file by ID",
                extra={"file_id": file_id, "error": str(e)}
            )
            return None
