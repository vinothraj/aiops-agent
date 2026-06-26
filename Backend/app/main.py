import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.router import api_router
from app.services.watcher import log_watcher_service
from app.database.session import Base, engine

# Setup logging
setup_logging(log_level="INFO")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    logger.info("Starting up AIOps Platform Foundation...")
    try:
        # Create database tables automatically
        Base.metadata.create_all(bind=engine)
        if not settings.DATABASE_URL.startswith("sqlite"):
            log_watcher_service.start()
        else:
            # For SQLite environments, perform a synchronous catch-up scan at startup
            log_watcher_service.scan_directory()
    except Exception as e:
        logger.error(f"Error starting Log Watcher Service: {str(e)}", exc_info=True)
    
    yield
    
    # Shutdown actions
    logger.info("Shutting down AIOps Platform Foundation...")
    try:
        log_watcher_service.stop()
    except Exception as e:
        logger.error(f"Error stopping Log Watcher Service: {str(e)}", exc_info=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception occurred on path {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please contact support or check system logs."},
    )

# Configure CORS
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include main API router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": settings.PROJECT_NAME}
