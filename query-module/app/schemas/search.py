"""
Query Module - Search API Schemas.

Pydantic <>45;8 4;O search endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator


class SearchMode(str, Enum):
    """ 568<K ?>8A:0 D09;>2."""
    EXACT = "exact"  # ">G=>5 A>2?045=85
    PARTIAL = "partial"  # '0AB8G=>5 A>2?045=85
    FULLTEXT = "fulltext"  # Full-text search (Phase 2)


class SortOrder(str, Enum):
    """>@O4>: A>@B8@>2:8 @57C;LB0B>2."""
    ASC = "asc"
    DESC = "desc"


class SortField(str, Enum):
    """>;O 4;O A>@B8@>2:8."""
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    FILE_SIZE = "file_size"
    FILENAME = "filename"
    RELEVANCE = "relevance"  # ;O FTS


class SearchRequest(BaseModel):
    """
    0?@>A =0 ?>8A: D09;>2.

    >445@68205B ?>8A: ?> @07;8G=K< ?>;O< <5B040==KE.
    """
    # A=>2=K5 ?>;O ?>8A:0
    query: Optional[str] = Field(
        None,
        min_length=1,
        max_length=500,
        description=">8A:>2K9 70?@>A (filename, tags, description)",
    )
    filename: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="<O D09;0 4;O ?>8A:0",
    )
    file_extension: Optional[str] = Field(
        None,
        min_length=1,
        max_length=10,
        description=" 0AH8@5=85 D09;0 (.pdf, .jpg, 8 B.4.)",
    )
    tags: Optional[List[str]] = Field(
        None,
        description="!?8A>: B53>2 4;O ?>8A:0",
    )

    # $8;LB@K
    username: Optional[str] = Field(
        None,
        description="$8;LB@ ?> 8<5=8 ?>;L7>20B5;O",
    )
    min_size: Optional[int] = Field(
        None,
        ge=0,
        description="8=8<0;L=K9 @07<5@ D09;0 (bytes)",
    )
    max_size: Optional[int] = Field(
        None,
        ge=0,
        description="0:A8<0;L=K9 @07<5@ D09;0 (bytes)",
    )
    created_after: Optional[datetime] = Field(
        None,
        description="$8;LB@: A>740==K5 ?>A;5 C:070==>9 40BK",
    )
    created_before: Optional[datetime] = Field(
        None,
        description="$8;LB@: A>740==K5 4> C:070==>9 40BK",
    )

    #  568< 8 ?0@0<5B@K ?>8A:0
    mode: SearchMode = Field(
        default=SearchMode.PARTIAL,
        description=" 568< ?>8A:0 (exact, partial, fulltext)",
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="0:A8<C< @57C;LB0B>2",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="!<5I5=85 4;O ?038=0F88",
    )

    # !>@B8@>2:0
    sort_by: SortField = Field(
        default=SortField.CREATED_AT,
        description=">;5 4;O A>@B8@>2:8",
    )
    sort_order: SortOrder = Field(
        default=SortOrder.DESC,
        description=">@O4>: A>@B8@>2:8",
    )

    @field_validator("min_size", "max_size")
    @classmethod
    def validate_size_range(cls, v: Optional[int], info) -> Optional[int]:
        """0;840F8O 480?07>=0 @07<5@>2."""
        if v is not None and v < 0:
            raise ValueError("File size must be non-negative")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """0;840F8O B53>2."""
        if v is not None:
            if len(v) > 50:
                raise ValueError("Maximum 50 tags allowed")
            for tag in v:
                if len(tag) > 50:
                    raise ValueError("Tag length must not exceed 50 characters")
        return v

    def has_search_criteria(self) -> bool:
        """
        @>25@:0 =0;8G8O E>BO 1K >4=>3> :@8B5@8O ?>8A:0.

        Returns:
            bool: True 5A;8 5ABL E>BO 1K >48= :@8B5@89
        """
        return any([
            self.query,
            self.filename,
            self.file_extension,
            self.tags,
            self.username,
            self.min_size is not None,
            self.max_size is not None,
            self.created_after,
            self.created_before,
        ])


class FileMetadataResponse(BaseModel):
    """
    5B040==K5 D09;0 2 @57C;LB0B0E ?>8A:0.
    """
    id: str = Field(..., description="UUID D09;0")
    filename: str = Field(..., description="@838=0;L=>5 8<O D09;0")
    storage_filename: str = Field(..., description="<O D09;0 2 storage")
    file_size: int = Field(..., ge=0, description=" 07<5@ D09;0 (bytes)")
    mime_type: Optional[str] = Field(None, description="MIME B8?")
    sha256_hash: str = Field(..., description="SHA256 E5H D09;0")
    username: str = Field(..., description=";045;5F D09;0")
    tags: Optional[List[str]] = Field(default=[], description="Теги файла")
    description: Optional[str] = Field(None, description="?8A0=85 D09;0")
    created_at: datetime = Field(..., description="0B0 A>740=8O")
    updated_at: datetime = Field(..., description="0B0 >1=>2;5=8O")
    storage_element_id: str = Field(..., description="ID storage element")

    # ;O FTS (Phase 2)
    relevance_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description=" 5;520=B=>ABL 4;O full-text search",
    )


class SearchResponse(BaseModel):
    """
    B25B =0 ?>8A: D09;>2.
    """
    results: List[FileMetadataResponse] = Field(
        default=[],
        description="0945==K5 D09;K",
    )
    total_count: int = Field(
        ...,
        ge=0,
        description="1I55 :>;8G5AB2> @57C;LB0B>2",
    )
    limit: int = Field(..., ge=1, description="8<8B @57C;LB0B>2")
    offset: int = Field(..., ge=0, description="!<5I5=85")
    has_more: bool = Field(
        ...,
        description="ABL ;8 5I5 @57C;LB0BK",
    )

    @property
    def current_page(self) -> int:
        """"5:CI0O AB@0=8F0 (1-based)."""
        return (self.offset // self.limit) + 1

    @property
    def total_pages(self) -> int:
        """1I55 :>;8G5AB2> AB@0=8F."""
        if self.total_count == 0:
            return 0
        return (self.total_count + self.limit - 1) // self.limit
