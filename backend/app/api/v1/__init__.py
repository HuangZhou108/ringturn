from fastapi import APIRouter
from app.api.v1.endpoints import tasks, health, upload, conversations, profiles, feedback

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(tasks.router)
api_router.include_router(upload.router)
api_router.include_router(conversations.router)
api_router.include_router(profiles.router)
api_router.include_router(feedback.router)
