"""
WebSocket处理模块

提供实时流式输出Agent执行过程
"""

import json
import asyncio
from datetime import datetime
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Task, TaskStatus
from app.agent.state import get_step_message

class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[task_id] = websocket

    def disconnect(self, task_id: str):
        if task_id in self.active_connections:
            del self.active_connections[task_id]

    async def send_message(self, task_id: str, message: dict):
        """发送消息到指定客户端"""
        if task_id in self.active_connections:
            await self.active_connections[task_id].send_json(message)

    async def broadcast(self, message: dict):
        """广播消息到所有客户端"""
        for task_id, connection in self.active_connections.items():
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """
    WebSocket端点

    实时推送Agent执行状态

    不长期持有数据库会话，避免占用连接池。
    """
    await manager.connect(task_id, websocket)

    # 验证任务是否存在（用独立会话，用完即关）
    with SessionLocal() as db:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            await websocket.send_json({
                "type": "error",
                "message": "任务不存在",
                "code": 404,
            })
            manager.disconnect(task_id)
            return

        # 发送初始状态
        await manager.send_message(task_id, {
            "type": "status_update",
            "task_id": task_id,
            "status": task.status.value,
            "current_subtask": task.current_subtask,
            "subtask_progress": task.subtask_progress or 0.0,
            "message": "连接成功，等待Agent执行...",
            "timestamp": datetime.utcnow().isoformat(),
        })

        # 循环监听状态变化
        last_status = task.status
        last_subtask = task.current_subtask
        last_progress = task.subtask_progress
        last_thinking_count = len(task.thinking_process) if task.thinking_process else 0

    # 进入轮询循环，每次迭代都创建新的数据库会话
    try:
        while True:
            await asyncio.sleep(2)   # 每2秒检查一次

            # 每次独立查询，使用 with 语句自动管理会话生命周期
            with SessionLocal() as db:
                # 重新获取任务最新状态
                task = db.query(Task).filter(Task.id == task_id).first()
                if not task:
                    # 任务可能已被删除，断开连接
                    break

                thinking_count = len(task.thinking_process) if task.thinking_process else 0

                # 检测是否有变化
                has_change = (
                    task.status != last_status or
                    task.current_subtask != last_subtask or
                    task.subtask_progress != last_progress or
                    thinking_count > last_thinking_count
                )

                if not has_change:
                    continue   # 无变化，跳过发送

                # 更新缓存的值
                last_status = task.status
                last_subtask = task.current_subtask
                last_progress = task.subtask_progress
                last_thinking_count = thinking_count

                # 获取最新的思考过程(全部)
                thinking_process = task.thinking_process

                # 发送状态更新
                await manager.send_message(task_id, {
                    "type": "status_update",
                    "task_id": task_id,
                    "status": task.status.value,
                    "current_subtask": task.current_subtask,
                    "subtask_progress": task.subtask_progress or 0.0,
                    "message": get_step_message(task.current_subtask),
                    "thinking_process": thinking_process,
                    "timestamp": datetime.utcnow().isoformat(),
                })

                # 任务完成或失败时，发送最终结果并退出循环
                if task.status == TaskStatus.completed:
                    await manager.send_message(task_id, {
                        "type": "completed",
                        "task_id": task_id,
                        "audio_url": task.final_audio_url,
                        "duration": task.audio_duration,
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    break
                elif task.status == TaskStatus.failed:
                    await manager.send_message(task_id, {
                        "type": "failed",
                        "task_id": task_id,
                        "error": task.error_message,
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    break

    except WebSocketDisconnect:
        # 客户端主动断开
        manager.disconnect(task_id)
    except Exception as e:
        # 其他异常，尝试发送错误消息
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except:
            pass
        manager.disconnect(task_id)
    finally:
        # 确保断开连接（如果还没有断开）
        manager.disconnect(task_id)
