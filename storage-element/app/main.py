"""
Storage Element FastAPI Application.

Main application entry point с routing, middleware и lifecycle management.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import time

from app.core.config import get_config
from app.core.logging import get_logger, configure_logging
from app.api.v1 import health, files, mode


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager для FastAPI application.

    Handles:
    - Startup: Configuration loading, logging setup, directory creation
    - Shutdown: Cleanup resources
    """
    # Startup
    config = get_config()
    logger = configure_logging(
        log_level=config.log_level,
        log_format=config.log_format
    )

    logger.info(
        "Storage Element starting",
        app_name=config.app_name,
        version=config.app_version,
        mode=config.mode.mode,
        storage_type=config.storage.type
    )

    # Create necessary directories
    from pathlib import Path

    storage_path = Path(config.storage.local_base_path)
    storage_path.mkdir(parents=True, exist_ok=True)
    logger.info("Storage directory created", path=str(storage_path))

    if config.wal.enabled:
        wal_path = Path(config.wal.wal_dir)
        wal_path.mkdir(parents=True, exist_ok=True)
        logger.info("WAL directory created", path=str(wal_path))

    yield

    # Shutdown
    logger.info("Storage Element shutting down")


# Create FastAPI application
config = get_config()

app = FastAPI(
    title=config.app_name,
    description="Distributed file storage element with metadata caching",
    version=config.app_version,
    lifespan=lifespan,
    docs_url="/docs" if config.debug else None,  # Disable in production
    redoc_url="/redoc" if config.debug else None,
)

# Get logger
logger = get_logger()


# Middleware configuration
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """
    Request/response logging middleware.

    Logs:
    - Request method, path, client IP
    - Response status code, duration
    """
    start_time = time.time()

    # Process request
    response = await call_next(request)

    # Calculate duration
    duration = time.time() - start_time

    # Log request/response
    logger.info(
        "HTTP request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration * 1000, 2),
        client_ip=request.client.host if request.client else None
    )

    return response


# CORS middleware (configure as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if config.debug else [],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler.

    Catches all unhandled exceptions and returns structured error response.
    """
    logger.exception(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        error=str(exc)
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An internal error occurred. Please try again later.",
            "path": request.url.path
        }
    )


# Route registration
app.include_router(
    health.router,
    prefix="/health",
    tags=["health"]
)

app.include_router(
    files.router,
    prefix="/api/v1/files",
    tags=["files"]
)

app.include_router(
    mode.router,
    prefix="/api/v1/mode",
    tags=["mode"]
)


# Root endpoint
@app.get(
    "/",
    tags=["root"],
    summary="Root endpoint",
    description="Application information"
)
async def root():
    """
    Root endpoint - provides basic application information.

    Returns:
        Dict: Application info
    """
    return {
        "name": config.app_name,
        "version": config.app_version,
        "mode": config.mode.mode,
        "storage_type": config.storage.type,
        "endpoints": {
            "health": {
                "liveness": "/health/live",
                "readiness": "/health/ready"
            },
            "docs": "/docs" if config.debug else "disabled",
            "api": "/api/v1"
        }
    }


# API v1 placeholder (to be implemented)
@app.get(
    "/api/v1",
    tags=["api"],
    summary="API v1 info"
)
async def api_v1_info():
    """API v1 информация."""
    return {
        "version": "1.0",
        "endpoints": {
            "files": "/api/v1/files",
            "search": "/api/v1/files/search",
            "mode": "/api/v1/mode",
            "admin": "/api/v1/admin"
        },
        "status": "partial (admin endpoints not yet implemented)"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_level=config.log_level.lower()
    )
