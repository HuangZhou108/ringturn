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
    """
    await manager.connect(task_id, websocket)

    db = SessionLocal()
    try:
        # 获取任务
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            await websocket.send_json({
                "type": "error",
                "message": "任务不存在",
                "code": 404,
            })
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

        while True:
            # 每2秒查询一次数据库状态
            await asyncio.sleep(2)

            db.refresh(task)

            # 检测状态变化
            if (task.status != last_status or
                task.current_subtask != last_subtask or
                task.subtask_progress != last_progress):

                last_status = task.status
                last_subtask = task.current_subtask
                last_progress = task.subtask_progress

                await manager.send_message(task_id, {
                    "type": "status_update",
                    "task_id": task_id,
                    "status": task.status.value,
                    "current_subtask": task.current_subtask,
                    "subtask_progress": task.subtask_progress or 0.0,
                    "message": get_step_message(task.current_subtask),
                    "timestamp": datetime.utcnow().isoformat(),
                })

                # 任务完成或失败时发送最终结果
                if task.status in [TaskStatus.completed, TaskStatus.failed]:
                    if task.status == TaskStatus.completed:
                        await manager.send_message(task_id, {
                            "type": "completed",
                            "task_id": task_id,
                            "audio_url": task.final_audio_url,
                            "duration": task.audio_duration,
                            "timestamp": datetime.utcnow().isoformat(),
                        })
                    else:
                        await manager.send_message(task_id, {
                            "type": "failed",
                            "task_id": task_id,
                            "error": task.error_message,
                            "timestamp": datetime.utcnow().isoformat(),
                        })
                    break

    except WebSocketDisconnect:
        manager.disconnect(task_id)
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": str(e),
        })
    finally:
        db.close()
        manager.disconnect(task_id)
