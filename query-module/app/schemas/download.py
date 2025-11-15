"""
Query Module - Download API Schemas.

Pydantic <>45;8 4;O download endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DownloadMetadata(BaseModel):
    """
    5B040==K5 D09;0 4;O A:0G820=8O.

    A?>;L7C5BAO 4;O ?>;CG5=8O 8=D>@<0F88 > D09;5 ?5@54 A:0G820=85<.
    """
    id: str = Field(..., description="UUID D09;0")
    filename: str = Field(..., description="@838=0;L=>5 8<O D09;0")
    file_size: int = Field(..., ge=0, description=" 07<5@ D09;0 (bytes)")
    mime_type: Optional[str] = Field(None, description="MIME B8?")
    sha256_hash: str = Field(..., description="SHA256 E5H 4;O 25@8D8:0F88")
    created_at: datetime = Field(..., description="0B0 A>740=8O")
    storage_element_id: str = Field(..., description="ID storage element")
    storage_element_url: str = Field(..., description="URL storage element 4;O A:0G820=8O")

    # >?>;=8B5;L=0O 8=D>@<0F8O
    download_url: Optional[str] = Field(
        None,
        description="@O<>9 URL 4;O A:0G820=8O D09;0",
    )
    supports_range_requests: bool = Field(
        default=True,
        description=">445@6:0 resumable downloads (HTTP Range)",
    )


class RangeRequest(BaseModel):
    """
    HTTP Range request 4;O resumable downloads.

    $>@<0B: bytes=start-end
    """
    start: int = Field(..., ge=0, description="0G0;L=K9 109B")
    end: Optional[int] = Field(None, ge=0, description=">=5G=K9 109B (>?F8>=0;L=>)")

    def to_header_value(self) -> str:
        """
        >=25@B0F8O 2 7=0G5=85 HTTP Range header.

        Returns:
            str: "bytes=start-end" 8;8 "bytes=start-"
        """
        if self.end is not None:
            return f"bytes={self.start}-{self.end}"
        return f"bytes={self.start}-"


class DownloadProgress(BaseModel):
    """
    @>3@5AA A:0G820=8O D09;0.

    A?>;L7C5BAO 4;O >BA;56820=8O resumable downloads.
    """
    file_id: str = Field(..., description="UUID D09;0")
    total_size: int = Field(..., ge=0, description="1I89 @07<5@ D09;0")
    downloaded_size: int = Field(..., ge=0, description="!:0G0=> bytes")
    resume_from: Optional[int] = Field(
        None,
        ge=0,
        description=">78F8O 4;O ?@>4>;65=8O A:0G820=8O",
    )

    @property
    def progress_percent(self) -> float:
        """
        @>F5=B 7025@H5=8O A:0G820=8O.

        Returns:
            float: 0.0 - 100.0
        """
        if self.total_size == 0:
            return 0.0
        return (self.downloaded_size / self.total_size) * 100.0

    @property
    def is_complete(self) -> bool:
        """
        @>25@:0 7025@H5==>AB8 A:0G820=8O.

        Returns:
            bool: True 5A;8 D09; ?>;=>ABLN A:0G0=
        """
        return self.downloaded_size >= self.total_size


class DownloadResponse(BaseModel):
    """
    B25B =0 70?@>A A:0G820=8O D09;0.

    !>45@68B 8=D>@<0F8N > stream 8;8 redirect URL.
    """
    file_id: str = Field(..., description="UUID D09;0")
    filename: str = Field(..., description="<O D09;0 4;O A>E@0=5=8O")
    content_type: str = Field(..., description="Content-Type 4;O HTTP header")
    content_length: int = Field(..., ge=0, description="Content-Length 4;O HTTP header")

    # ;O resumable downloads
    supports_resume: bool = Field(
        default=True,
        description=">445@6:0 HTTP Range requests",
    )
    accept_ranges: str = Field(
        default="bytes",
        description="Accept-Ranges HTTP header value",
    )

    # ;O 25@8D8:0F88 ?>A;5 A:0G820=8O
    sha256_hash: str = Field(..., description="SHA256 E5H 4;O ?@>25@:8 F5;>AB=>AB8")


class DownloadStats(BaseModel):
    """
    !B0B8AB8:0 A:0G820=8O D09;0.

    A?>;L7C5BAO 4;O <>=8B>@8=30 8 0=0;8B8:8.
    """
    file_id: str = Field(..., description="UUID D09;0")
    download_count: int = Field(..., ge=0, description=">;8G5AB2> A:0G820=89")
    last_download_at: Optional[datetime] = Field(
        None,
        description=">A;54=55 A:0G820=85",
    )
    total_bytes_served: int = Field(
        ...,
        ge=0,
        description="A53> ?5@540=> bytes",
    )
