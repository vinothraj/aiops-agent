from fastapi import APIRouter
from app.api.endpoints import logs, stats, sources, rca, knowledge, incidents, gitlab, notifications

api_router = APIRouter()

api_router.include_router(logs.router, prefix="/logs", tags=["logs"])
api_router.include_router(stats.router, prefix="/stats", tags=["stats"])
api_router.include_router(sources.router, prefix="/log-sources", tags=["log-sources"])
api_router.include_router(rca.router, prefix="/rca", tags=["rca"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"])
api_router.include_router(incidents.router, prefix="/incidents", tags=["incidents"])
api_router.include_router(incidents.router, prefix="/incident", tags=["incident-triage"])
api_router.include_router(gitlab.router, prefix="/gitlab", tags=["gitlab"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
