"""
FastAPI Application Entry Point.

REST API server for Product Service.
"""
import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from internal.transport.http.v1.handlers import router, set_dependencies
from internal.transport.http.v1.crm import router as crm_router, set_crm_repository
from internal.transport.http.middleware import MetricsMiddleware
from internal.infrastructure.postgres.repository import (
    PostgresProductRepository,
    create_pool,
)
from internal.infrastructure.postgres.crm_repository import CRMRepository
from internal.infrastructure.redis.cache import RedisCache, ProductCacheService
from internal.infrastructure.ai_provider.vertex_client import (
    VertexAIClientWithFallback,
    VertexAIEmbeddingClient,
)
from internal.usecase.create_product import CreateProductUseCase
from internal.usecase.enrich_product import EnrichProductUseCase
from internal.usecase.search_products import SearchProductsUseCase
from internal.usecase.semantic_search import SemanticSearchUseCase
from pkg.logger.logger import setup_logging, get_logger, set_request_id


# Load environment variables
load_dotenv()

# Setup logging
setup_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_format=os.getenv("LOG_FORMAT", "json") == "json",
)

logger = get_logger(__name__)


# Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/product_service",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
VERTEX_PROJECT_ID = os.getenv("VERTEX_PROJECT_ID", "")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
VERTEX_EMBEDDING_MODEL = os.getenv("VERTEX_EMBEDDING_MODEL", "text-embedding-004")


# Global resources
db_pool = None
redis_cache = None
ai_client = None
embedding_client = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    
    Handles startup and shutdown of resources.
    """
    global db_pool, redis_cache, ai_client, embedding_client
    
    logger.info("Starting Product Service API...")
    
    # Initialize database pool
    try:
        db_pool = await create_pool(DATABASE_URL)
        logger.info("Database pool created")
    except Exception as e:
        logger.error("Failed to create database pool", error=str(e))
        raise
    
    # Initialize Redis cache
    try:
        redis_cache = RedisCache(redis_url=REDIS_URL)
        await redis_cache.connect()
        logger.info("Redis cache connected")
    except Exception as e:
        logger.warning("Failed to connect to Redis, caching disabled", error=str(e))
        redis_cache = None
    
    # Initialize AI client
    if VERTEX_PROJECT_ID:
        try:
            ai_client = VertexAIClientWithFallback(
                project_id=VERTEX_PROJECT_ID,
                location=VERTEX_LOCATION,
            )
            await ai_client.initialize()
            logger.info("Vertex AI client initialized")
        except Exception as e:
            logger.warning("Failed to initialize Vertex AI", error=str(e))
            ai_client = None

        try:
            embedding_client = VertexAIEmbeddingClient(
                project_id=VERTEX_PROJECT_ID,
                location=VERTEX_LOCATION,
                model_id=VERTEX_EMBEDDING_MODEL,
            )
            await embedding_client.initialize()
            logger.info("Vertex AI embedding client initialized")
        except Exception as e:
            logger.warning("Failed to initialize Vertex embeddings", error=str(e))
            embedding_client = None
    else:
        logger.warning("VERTEX_PROJECT_ID not set, AI enrichment disabled")
        embedding_client = None
    
    # Create repositories and services
    repository = PostgresProductRepository(db_pool)
    cache_service = ProductCacheService(redis_cache) if redis_cache else None
    
    # Create use cases
    create_use_case = CreateProductUseCase(
        repository=repository,
        cache=cache_service,
        embedding_client=embedding_client,
    )
    enrich_use_case = EnrichProductUseCase(
        repository=repository,
        ai_provider=ai_client,
        cache=cache_service,
    )
    search_use_case = SearchProductsUseCase(
        repository=repository,
    )
    semantic_search_use_case = SemanticSearchUseCase(
        repository=repository,
        embedding_client=embedding_client,
    )
    
    # Set dependencies for handlers
    set_dependencies(
        create_use_case=create_use_case,
        enrich_use_case=enrich_use_case,
        search_use_case=search_use_case,
        semantic_search_use_case=semantic_search_use_case,
        repository=repository,
    )
    
    # Initialize CRM repository
    crm_repository = CRMRepository(db_pool)
    set_crm_repository(crm_repository)
    logger.info("CRM repository initialized")
    
    logger.info("Product Service API started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Product Service API...")
    
    if redis_cache:
        await redis_cache.disconnect()
    
    if db_pool:
        await db_pool.close()
    
    logger.info("Product Service API shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Product Service API",
    description="High-load microservice for product family management",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Metrics middleware
app.add_middleware(MetricsMiddleware)


# Request ID middleware
@app.middleware("http")
async def request_id_middleware(request: Request, call_next) -> Response:
    """
    Add request ID to context for logging and tracing.
    """
    import uuid
    
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    
    set_request_id(request_id)
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    
    return response


# Include routers
app.include_router(router)
app.include_router(crm_router)


# Root endpoint
@app.get("/")
async def root() -> dict:
    """Root endpoint with service information."""
    return {
        "service": "product-service",
        "version": "1.0.0",
        "status": "running",
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
        workers=int(os.getenv("WORKERS", "1")),
    )
