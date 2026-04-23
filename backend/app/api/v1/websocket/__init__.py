"""
WebSocket模块初始化
"""

from app.api.v1.websocket.chat import manager, websocket_endpoint

__all__ = [
    "manager",
    "websocket_endpoint",
]
