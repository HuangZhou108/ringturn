from fastapi import FastAPI, Request, WebSocket, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
from pathlib import Path

from app.core.config import get_settings, ensure_directories
from app.core.exceptions import AppException
from app.db.session import init_db, enable_wal_mode
from app.api.v1 import api_router
from app.api.v1.websocket.chat import websocket_endpoint
from app.api.v1.endpoints.profiles import ensure_profiles_exist

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    ensure_directories()
    init_db()
    enable_wal_mode()
    # 确保至少有一个 Profile（默认）
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        ensure_profiles_exist(db)
        from app.services.knowledge_base import ensure_builtin_knowledge

        ensure_builtin_knowledge(db)
        db.commit()
    finally:
        db.close()
    if settings.AGENT_RECOVER_ON_STARTUP:
        from app.api.v1.endpoints.tasks import recover_incomplete_tasks

        recovered_task_ids = recover_incomplete_tasks()
        if recovered_task_ids:
            print(f"[SCHEDULER] queued {len(recovered_task_ids)} recoverable task(s)")
    yield
    # 关闭时执行：暂停本机任务，等待后台协程退出。
    from app.api.v1.endpoints.tasks import _running_tasks, _background_tasks
    import asyncio

    # 1. 暂停本机执行，不把可恢复任务误标为用户取消。
    suspend_tasks = []
    for task_id, executor in list(_running_tasks.items()):
        if hasattr(executor, 'suspend'):
            suspend_tasks.append(asyncio.create_task(executor.suspend()))
    if suspend_tasks:
        await asyncio.gather(*suspend_tasks, return_exceptions=True)

    # 2. 取消并等待后台任务
    background_tasks = list(_background_tasks)
    for t in background_tasks:
        if not t.done():
            t.cancel()
    if background_tasks:
        await asyncio.gather(*background_tasks, return_exceptions=True)

    # 3. 可选：强制垃圾回收
    import gc
    gc.collect()
    pass

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI音乐改编Agent - 将歌曲自动改编为独特铃声",
    lifespan=lifespan,
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册异常处理器
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "data": None,
            "message": exc.detail,
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "data": None,
            "message": f"服务器内部错误: {str(exc)}",
        }
    )

# 注册路由
app.include_router(api_router)

# WebSocket路由
@app.websocket("/ws/chat/{task_id}")
async def ws_chat(websocket: WebSocket, task_id: str):
    await websocket_endpoint(websocket, task_id)

# 挂载静态文件（用于提供生成的铃声文件）
app.mount("/static", StaticFiles(directory="static"), name="static")

# 上传文件访问（临时）
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# 挂载 tool_graphs 目录，使默认 JSON 可通过 URL 访问
tool_graphs_dir = Path(__file__).parent / "agent" / "tool_graphs"
if tool_graphs_dir.exists():
    app.mount("/tool_graphs", StaticFiles(directory=str(tool_graphs_dir)), name="tool_graphs")

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
