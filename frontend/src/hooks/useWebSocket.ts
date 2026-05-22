// src/hooks/useWebSocket.ts
// WebSocket Hook

import { useEffect, useCallback, useRef, useState } from 'react'
import { wsClient, type WebSocketMessage } from '../utils/websocket'

export interface TaskStatusInfo {
    task_id: string
    status: string
    current_subtask?: string
    subtask_progress?: number
    message?: string
    thinking_process?: { step: string; content: string; timestamp: string }[]
}

export function useWebSocket(taskId: string | null) {
    const [isConnected, setIsConnected] = useState(false)
    const [taskStatus, setTaskStatus] = useState<TaskStatusInfo | null>(null)
    const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null)
    const [error, setError] = useState<string | null>(null)
    const unsubscribeRef = useRef<(() => void)[]>([])
    const taskIdRef = useRef<string | null>(null)

    // 连接WebSocket
    const connect = useCallback((id: string) => {
        // 清除之前的订阅
        unsubscribeRef.current.forEach(unsub => unsub())
        unsubscribeRef.current = []

        // 断开旧连接
        wsClient.disconnect()

        // 连接
        const success = wsClient.connect(id)
        if (!success) {
            setError('WebSocket连接失败')
            return
        }

        setError(null)

        // 订阅连接事件
        const unsubConnected = wsClient.on('connected', () => {
            setIsConnected(true)
        })

        // 订阅错误事件
        const unsubError = wsClient.on('error', (data) => {
            setError(data.message || 'WebSocket错误')
            setIsConnected(false)
        })

        // 订阅状态更新
        const unsubStatusUpdate = wsClient.on('status_update', (data: WebSocketMessage) => {
            // 只处理当前任务的状态更新
            if (taskIdRef.current !== data.task_id) return

            setTaskStatus({
                task_id: data.task_id,
                status: data.status || '',
                current_subtask: data.current_subtask,
                subtask_progress: data.subtask_progress,
                message: data.message,
                thinking_process: data.thinking_process,
            })
            setLastMessage(data)
        })

        // 订阅任务完成
        const unsubCompleted = wsClient.on('completed', (data: WebSocketMessage) => {
            // 只处理当前任务的状态更新
            if (taskIdRef.current !== data.task_id) return

            setTaskStatus(prev => prev ? {
                ...prev,
                status: 'completed',
            } : null)
            setLastMessage(data)
            setIsConnected(false)
        })

        // 订阅任务失败
        const unsubFailed = wsClient.on('failed', (data: WebSocketMessage) => {
            // 只处理当前任务的状态更新
            if (taskIdRef.current !== data.task_id) return

            setTaskStatus(prev => prev ? {
                ...prev,
                status: 'failed',
            } : null)
            setLastMessage(data)
            setError(data.error || '任务执行失败')
            setIsConnected(false)
        })

        // 保存取消订阅函数
        unsubscribeRef.current = [
            unsubConnected,
            unsubError,
            unsubStatusUpdate,
            unsubCompleted,
            unsubFailed,
        ]
    }, [])

    // 断开连接
    const disconnect = useCallback(() => {
        unsubscribeRef.current.forEach(unsub => unsub())
        unsubscribeRef.current = []
        wsClient.disconnect()
        setIsConnected(false)
        setTaskStatus(null)
    }, [])

    // 当taskId变化时自动连接/断开
    useEffect(() => {
        taskIdRef.current = taskId

        if (taskId) {
            connect(taskId)
        } else {
            disconnect()
        }

        return () => {
            // 组件卸载或taskId变化时断开连接
            disconnect()
        }
    }, [taskId, connect, disconnect])

    return {
        isConnected,
        taskStatus,
        lastMessage,
        error,
        connect,
        disconnect,
    }
}
