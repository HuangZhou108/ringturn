from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "message": "RingTurn API is running"}
