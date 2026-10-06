from fastapi import APIRouter
from app.api.v1.endpoints import (conversations, feedback, health, memory,
                                  profiles, tasks, upload)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(tasks.router)
api_router.include_router(upload.router)
api_router.include_router(conversations.router)
api_router.include_router(profiles.router)
api_router.include_router(feedback.router)
api_router.include_router(memory.router)
