"""
">G:0 2E>40 FastAPI ?@8;>65=8O Admin Module.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import settings
from app.core.logging import setup_logging
from app.core.security import init_keys
from app.db.session import close_db, init_db, init_db_engine
from app.services.redis_service import redis_service
from app.utils.logger import get_logger

# 0AB@>9:0 ;>38@>20=8O
setup_logging(
    level=settings.logging.level,
    format_type=settings.logging.format,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle :>=B5:AB <5=5465@ 4;O FastAPI ?@8;>65=8O.

    K?>;=O5BAO ?@8 AB0@B5 8 >AB0=>2:5 ?@8;>65=8O.
    """
    # Startup
    logger.info("Starting Admin Module...")

    # =8F80;870F8O database engine
    logger.info("Initializing database engine...")
    init_db_engine(
        database_url=settings.database.url,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        echo=settings.database.echo,
    )

    # !>740=85 B01;8F (5A;8 =5 ACI5AB2CNB)
    #  production 8A?>;L7C9B5 Alembic <83@0F88
    logger.info("Creating database tables...")
    await init_db()

    # =8F80;870F8O JWT :;NG59
    logger.info("Loading JWT keys...")
    init_keys(
        private_key_path=settings.auth.jwt.private_key_path,
        public_key_path=settings.auth.jwt.public_key_path,
    )

    # =8F80;870F8O Redis ?>4:;NG5=8O
    logger.info("Connecting to Redis...")
    await redis_service.connect(
        host=settings.redis.host,
        port=settings.redis.port,
        db=settings.redis.db,
        decode_responses=settings.redis.decode_responses,
    )

    # !>740=85 default admin ?>;L7>20B5;O (5A;8 =5 ACI5AB2C5B)
    from app.db.session import async_session_maker
    from app.services.user_service import user_service

    async with async_session_maker() as db:
        try:
            await user_service.ensure_default_admin(db, settings.auth.default_admin)
            logger.info("Default admin user ensured")
        except Exception as e:
            logger.error(f"Failed to create default admin: {e}")

    logger.info("Admin Module started successfully!")

    yield

    # Shutdown
    logger.info("Shutting down Admin Module...")

    # 0:@KB85 Redis ?>4:;NG5=8O
    await redis_service.close()
    logger.info("Redis connection closed")

    # 0:@KB85 database ?>4:;NG5=89
    await close_db()
    logger.info("Database connections closed")

    logger.info("Admin Module shut down successfully!")


# !>740=85 FastAPI ?@8;>65=8O
app = FastAPI(
    title=settings.server.title,
    version=settings.server.version,
    description="Admin Module API 4;O A8AB5<K ArtStore",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS middleware
if settings.server.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# >4:;NG5=85 API @>CB5@0
app.include_router(api_router, prefix="/api")

# Root endpoint
@app.get("/")
async def root():
    """
    >@=52>9 endpoint ?@8;>65=8O.
    """
    return {
        "service": "admin-module",
        "version": settings.server.version,
        "status": "running",
        "docs": "/docs",
        "health": "/api/health/health",
    }


# 0?CA: ?@8;>65=8O
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
        log_level="info",
    )
