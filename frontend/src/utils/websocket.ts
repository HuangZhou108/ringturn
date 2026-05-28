// src/utils/websocket.ts
// WebSocket客户端工具类

export interface WebSocketMessage {
  type: 'status_update' | 'completed' | 'failed' | 'error' | 'connected'
  task_id: string
  status?: string
  current_subtask?: string
  subtask_progress?: number
  thinking_process?: { step: string; content: string; timestamp: string }[]
  audio_url?: string
  duration?: number
  error?: string
  message?: string
  code?: number
  timestamp: string
}

export type MessageHandler = (data: WebSocketMessage) => void

class WebSocketClient {
  private ws: WebSocket | null = null
  private handlers: Map<string, MessageHandler[]> = new Map()
  private reconnectAttempts = 0
  private maxReconnectAttempts = 3  // 减少重试次数
  private currentTaskId: string | null = null
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  private taskCompleted = false  // 标记任务是否已完成
  private connectionRejected = false  // 标记连接是否被拒绝

  connect(taskId: string): boolean {
    // 如果已连接，先断开
    if (this.ws) {
      this.disconnect()
    }

    this.currentTaskId = taskId
    this.taskCompleted = false  // 重置完成标志
    this.connectionRejected = false  // 重置拒绝标志
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const url = `${protocol}//${host}/ws/chat/${taskId}`

    try {
      this.ws = new WebSocket(url)

      this.ws.onopen = () => {
        console.log('[WebSocket] Connected')
        this.reconnectAttempts = 0
        this.emit('connected', {
          type: 'connected',
          task_id: taskId,
          timestamp: new Date().toISOString(),
        })
      }

      this.ws.onmessage = (event) => {
        try {
          const data: WebSocketMessage = JSON.parse(event.data)
          // 标记任务完成状态，停止后续重连
          if (data.type === 'completed' || data.type === 'failed') {
            this.taskCompleted = true
          }
          this.emit(data.type, data)
          this.emit('*', data) // 广播所有消息
        } catch (err) {
          console.error('[WebSocket] Failed to parse message:', err)
        }
      }

      this.ws.onclose = (event) => {
        console.log('[WebSocket] Disconnected', event.code, event.reason)
        // 只有当前任务且未完成且未拒绝时才重连
        if (this.currentTaskId === taskId && !this.taskCompleted && !this.connectionRejected) {
          this.attemptReconnect(taskId)
        } else {
          console.log('[WebSocket] Skipping reconnect: completed=', this.taskCompleted, 'rejected=', this.connectionRejected)
        }
      }

      this.ws.onerror = (error) => {
        console.error('[WebSocket] Error:', error)
        // 如果连接失败，标记并停止重连
        this.connectionRejected = true
        this.emit('error', {
          type: 'error',
          task_id: taskId,
          message: 'WebSocket连接失败',
          timestamp: new Date().toISOString(),
        })
      }

      return true
    } catch (err) {
      console.error('[WebSocket] Failed to connect:', err)
      return false
    }
  }

  private attemptReconnect(taskId: string) {
    // 如果任务已完成或连接被拒绝，不再重连
    if (this.taskCompleted || this.connectionRejected || this.currentTaskId !== taskId) {
      console.log('[WebSocket] Skipping reconnect: task completed or connection rejected')
      return
    }

    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++
      // 重连间隔从5秒开始，最多30秒
      const delay = Math.min(5000 * this.reconnectAttempts, 30000)
      console.log(`[WebSocket] Reconnecting in ${delay}ms... (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`)

      this.reconnectTimeout = setTimeout(() => {
        // 再次检查
        if (this.currentTaskId === taskId && !this.taskCompleted && !this.connectionRejected) {
          this.connect(taskId)
        }
      }, delay)
    } else {
      console.log('[WebSocket] Max reconnect attempts reached, giving up')
      this.connectionRejected = true  // 标记为拒绝
      this.emit('error', {
        type: 'error',
        task_id: taskId,
        message: 'WebSocket连接失败，已停止重试',
        timestamp: new Date().toISOString(),
      })
    }
  }

  disconnect() {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }

    if (this.ws) {
      this.ws.onclose = null // 防止触发重连
      this.ws.close()
      this.ws = null
    }

    this.currentTaskId = null
    this.reconnectAttempts = 0
    this.taskCompleted = false
    this.connectionRejected = false
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN
  }

  getCurrentTaskId(): string | null {
    return this.currentTaskId
  }

  on(event: string, handler: MessageHandler): () => void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, [])
    }
    this.handlers.get(event)!.push(handler)

    // 返回取消订阅函数
    return () => {
      this.off(event, handler)
    }
  }

  off(event: string, handler: MessageHandler) {
    const handlers = this.handlers.get(event)
    if (handlers) {
      this.handlers.set(
        event,
        handlers.filter((h) => h !== handler)
      )
    }
  }

  private emit(event: string, data: WebSocketMessage) {
    const handlers = this.handlers.get(event)
    if (handlers) {
      handlers.forEach((h) => {
        try {
          h(data)
        } catch (err) {
          console.error(`[WebSocket] Handler error for event "${event}":`, err)
        }
      })
    }
  }
}

// 单例
export const wsClient = new WebSocketClient()
