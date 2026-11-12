from fastapi import APIRouter, Depends
from app.api.endpoints import logs, stats, sources, rca, knowledge, incidents, gitlab, notifications, incident_groups, settings, fix_sessions, auth
from app.services.auth import get_current_user

api_router = APIRouter()

api_router.include_router(logs.router, prefix="/logs", tags=["logs"], dependencies=[Depends(get_current_user)])
api_router.include_router(stats.router, prefix="/stats", tags=["stats"], dependencies=[Depends(get_current_user)])
api_router.include_router(sources.router, prefix="/log-sources", tags=["log-sources"], dependencies=[Depends(get_current_user)])
api_router.include_router(rca.router, prefix="/rca", tags=["rca"], dependencies=[Depends(get_current_user)])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["knowledge"], dependencies=[Depends(get_current_user)])
api_router.include_router(incidents.router, prefix="/incidents", tags=["incidents"], dependencies=[Depends(get_current_user)])
api_router.include_router(incidents.router, prefix="/incident", tags=["incident-triage"], dependencies=[Depends(get_current_user)])
api_router.include_router(gitlab.router, prefix="/gitlab", tags=["gitlab"], dependencies=[Depends(get_current_user)])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"], dependencies=[Depends(get_current_user)])
api_router.include_router(incident_groups.router, prefix="/incident-groups", tags=["incident-groups"], dependencies=[Depends(get_current_user)])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"], dependencies=[Depends(get_current_user)])
# Fix-session routes carry their own auth: the agent callback (/events) uses a per-session token.
api_router.include_router(fix_sessions.router, prefix="/fix-sessions", tags=["fix-sessions"])

# Authentication: register/login are public, everything else needs a valid token.
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(auth.users_router, prefix="/auth", tags=["auth"])
api_router.include_router(auth.admin_router, prefix="/users", tags=["users"])
