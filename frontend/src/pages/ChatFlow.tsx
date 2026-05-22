// src/pages/ChatFlow.tsx
import { useTranslation } from 'react-i18next'
import { useState, useEffect, useRef, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import { conversationApi, type ConversationDetail } from '../api/conversation'
import type { TaskListItem, Message as AppMessage } from '../types'
import TopBar from '../components/TopBar'
import Sidebar from '../components/SideBar'
import Toast from '../components/notifications/Toast'
import WelcomeMessage from '../components/chat/WelcomeMessage'
import MessageList from '../components/chat/MessageList'
import ChatInputArea from '../components/chat/ChatInputArea'
import { useWebSocket } from '../hooks'

// 消息类型（与现有代码保持一致）
interface Message {
    id: string
    type: 'ai' | 'user'
    content?: string
    deepThinking?: string
    fileName?: string
    fileInfo?: string
    userFile?: string
    audioFileId?: string
    taskId?: string
    thinkingProcess?: { step: string; content: string; timestamp: string }[]
    showThinking?: boolean
}

function ChatFlow() {
    const { t } = useTranslation()
    const location = useLocation()

    // 侧边栏状态
    const [sidebarOpen, setSidebarOpen] = useState(false)

    // 会话状态
    const [currentConversationId, setCurrentConversationId] = useState<string | null>(null)
    const [currentConversation, setCurrentConversation] = useState<ConversationDetail | null>(null)

    // 消息和任务状态
    const [messages, setMessages] = useState<Message[]>([])
    const [recentTasks, setRecentTasks] = useState<TaskListItem[]>([])
    const [currentTaskId, setCurrentTaskId] = useState<string | null>(null)

    // 音频参数
    const [instrument, setInstrument] = useState('')
    const [duration, setDuration] = useState('')
    const [tempo, setTempo] = useState('')
    const [filename, setFilename] = useState('Untitled_Track')
    const [inputValue, setInputValue] = useState('')

    // 上传状态
    const [audioFileId, setAudioFileId] = useState<string | null>(null)
    const [uploadError, setUploadError] = useState<string | null>(null)
    const [uploadSuccess, setUploadSuccess] = useState<string | null>(null)
    const [uploadProgress, setUploadProgress] = useState<number>(0)
    const [isUploading, setIsUploading] = useState(false)
    const [uploadedFileName, setUploadedFileName] = useState<string | null>(null)

    // 调试日志 - 每次渲染时打印完整状态
    console.log('[ChatFlow] === RENDER === audioFileId:', audioFileId, '| uploadSuccess:', uploadSuccess, '| isUploading:', isUploading, '| location.state:', JSON.stringify(location.state))
    const fileInputRef = useRef<HTMLInputElement>(null)

    // UI状态
    const [toastMessage, setToastMessage] = useState<string | null>(null)
    const [isProcessing, setIsProcessing] = useState(false)
    const idCounter = useRef(Date.now())
    const fetchHistoryRef = useRef<(() => Promise<void>) | null>(null)
    const messagesEndRef = useRef<HTMLDivElement>(null)
    const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
    // 使用 ref 保存路由状态，避免重新渲染时丢失
    const locationStateRef = useRef(location.state as any)

    // WebSocket
    const { isConnected, taskStatus } = useWebSocket(currentTaskId)

    // 基础方法
    const nextId = () => {
        idCounter.current += 1
        return `${Date.now()}-${idCounter.current}`
    }

    // 显示错误消息
    const showError = (message: string) => {
        const errorMsg: Message = {
            id: nextId(),
            type: 'ai',
            content: message,
        }
        setMessages((prev) => [...prev, errorMsg])
    }

    // 显示Toast
    const showToast = (msg: string) => {
        setToastMessage(msg)
    }

    // 加载会话详情
    const loadConversation = useCallback(async (conversationId: string) => {
        try {
            const res = await conversationApi.get(conversationId)
            if (res.code === 200) {
                setCurrentConversation(res.data)

                // 将会话消息转换为UI消息
                const uiMessages: Message[] = res.data.messages.map((msg, index) => ({
                    id: `msg-${msg.id}`,
                    type: msg.role === 'user' ? 'user' : 'ai',
                    content: msg.content,
                    taskId: msg.task_id || undefined,
                    userFile: msg.role === 'user' ? uploadedFileName : undefined,
                }))

                // 如果没有消息，显示欢迎消息
                if (uiMessages.length === 0) {
                    setMessages([])
                } else {
                    setMessages(uiMessages)
                }
            }
        } catch (err) {
            console.error('Failed to load conversation:', err)
            showToast('加载会话失败')
        }
    }, [uploadedFileName])

    // 新建空会话
    const handleNewConversation = useCallback(() => {
        setCurrentConversationId(null)
        setCurrentConversation(null)
        setMessages([])
        setCurrentTaskId(null)
        setInputValue('')
        // 重置上传状态
        setAudioFileId(null)
        setUploadedFileName(null)
        setUploadSuccess(null)
        setUploadError(null)
        // 重置音频参数
        setInstrument('')
        setDuration('')
        setTempo('')
        setFilename('Untitled_Track')
    }, [])

    // 加载历史任务（保留兼容性）
    useEffect(() => {
        const fetchHistory = async () => {
            try {
                const res = await api.getUserTasks(1)
                if (res.code === 200 && res.data) {
                    setRecentTasks(res.data.tasks || [])
                }
            } catch {
                // 静默失败
            }
        }
        fetchHistoryRef.current = fetchHistory
    }, [])

    // 页面自动滚动
    useEffect(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollTop = messagesEndRef.current.scrollHeight
        }
    }, [messages])

    // 处理WebSocket状态更新
    useEffect(() => {
        if (taskStatus && currentTaskId) {
            // 更新消息中的思考过程
            setMessages((prev) => {
                const lastAiMsgIndex = prev.findLastIndex(m => m.type === 'ai')
                if (lastAiMsgIndex === -1) return prev

                return prev.map((msg, index) => {
                    if (index === lastAiMsgIndex) {
                        return {
                            ...msg,
                            content: taskStatus.message || taskStatus.current_subtask || msg.content,
                            thinkingProcess: taskStatus.thinking_process || msg.thinkingProcess,
                        }
                    }
                    return msg
                })
            })

            // 处理完成/失败状态
            if (taskStatus.status === 'completed') {
                // 停止轮询
                if (pollingIntervalRef.current) {
                    clearInterval(pollingIntervalRef.current)
                    pollingIntervalRef.current = null
                }
                // 任务完成，获取结果
                handleTaskCompleted(currentTaskId)
            } else if (taskStatus.status === 'failed') {
                if (pollingIntervalRef.current) {
                    clearInterval(pollingIntervalRef.current)
                    pollingIntervalRef.current = null
                }
                setIsProcessing(false)
                showError(t('chat.failed'))
            }
        }
    }, [taskStatus, currentTaskId, t])

    // 组件卸载时清理轮询
    useEffect(() => {
        return () => {
            if (pollingIntervalRef.current) {
                clearInterval(pollingIntervalRef.current)
                pollingIntervalRef.current = null
            }
        }
    }, [])

    // 任务完成处理
    const handleTaskCompleted = async (taskId: string) => {
        try {
            const resultRes = await api.getTaskResult(taskId)
            if (resultRes.code === 200 && resultRes.data) {
                setMessages((prev) => {
                    const lastAiMsgIndex = prev.findLastIndex(m => m.type === 'ai')
                    if (lastAiMsgIndex === -1) return prev

                    return prev.map((msg, index) => {
                        if (index === lastAiMsgIndex) {
                            return {
                                ...msg,
                                content: t('chat.completed'),
                                fileName: resultRes.data.audio_url,
                                fileInfo: resultRes.data.duration ? `${resultRes.data.duration}s` : undefined,
                            }
                        }
                        return msg
                    })
                })
            }
        } catch (err) {
            console.error('Failed to get task result:', err)
        } finally {
            setIsProcessing(false)
            fetchHistoryRef.current?.()
        }
    }

    // 发送消息
    const handleSend = async () => {
        if (!inputValue.trim()) return

        // 检查是否已上传音频
        if (!audioFileId) {
            showToast(t('toast.uploadRequired'))
            return
        }

        const params: Record<string, any> = {}
        if (instrument.trim()) params.instrument = instrument
        if (tempo.trim()) params.tempo = parseInt(tempo, 10)
        if (duration.trim()) params.duration = parseInt(duration, 10)
        if (filename && filename.trim() !== '') params.filename = filename

        // 添加用户消息
        const newUserMessage: Message = {
            id: nextId(),
            type: 'user',
            content: inputValue.trim(),
            userFile: uploadedFileName || undefined,
        }
        setMessages((prev) => [...prev, newUserMessage])
        setInputValue('')

        try {
            const res = await api.createTask({
                user_request: inputValue.trim(),
                conversation_id: currentConversationId || undefined,
                source_type: 'upload',
                source_value: audioFileId || undefined,
                params,
            })

            if (res.code === 200) {
                setIsProcessing(true)
                setCurrentTaskId(res.data.task_id)

                // 如果创建了新会话，保存会话ID
                if (res.data.conversation_id && !currentConversationId) {
                    setCurrentConversationId(res.data.conversation_id)
                }

                fetchHistoryRef.current?.()

                // 添加处理中消息
                const processingMsg: Message = {
                    id: nextId(),
                    type: 'ai',
                    taskId: res.data.task_id,
                    deepThinking: t('chat.deepThinking'),
                    content: t('chat.taskCreated'),
                }
                setMessages((prev) => [...prev, processingMsg])

                // 如果WebSocket未连接或不是当前任务，使用轮询
                if (!isConnected || currentTaskId !== res.data.task_id) {
                    pollTaskStatus(res.data.task_id, processingMsg.id)
                }
            } else {
                showError(res.message || t('chat.createFailed'))
            }
        } catch {
            showError(t('chat.networkError'))
        }
    }

    // 轮询任务状态（降级方案）
    const pollTaskStatus = async (taskId: string, msgId: string) => {
        // 清除之前的轮询
        if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)
        }

        const poll = setInterval(async () => {
            try {
                const res = await api.getTaskStatus(taskId)
                if (res.code !== 200) return

                const { status, current_subtask, message, thinking_process } = res.data

                if (['pending', 'planning', 'executing'].includes(status)) {
                    setIsProcessing(true)
                } else {
                    setIsProcessing(false)
                }

                // 更新消息
                setMessages((prev) => {
                    const msgIndex = prev.findIndex((m) => m.id === msgId)
                    if (msgIndex === -1) return prev

                    const existingMsg = prev[msgIndex]
                    const existingSteps = existingMsg.thinkingProcess || []
                    const newSteps = thinking_process || []
                    const mergedSteps = [...existingSteps]

                    for (const step of newSteps) {
                        const exists = mergedSteps.some(
                            (s) => s.step === step.step && s.timestamp === step.timestamp
                        )
                        if (!exists) mergedSteps.push(step)
                    }

                    return prev.map((msg) =>
                        msg.id === msgId
                            ? {
                                ...msg,
                                content: message || current_subtask || msg.content,
                                thinkingProcess: mergedSteps,
                            }
                            : msg
                    )
                })

                if (status === 'completed') {
                    clearInterval(poll)
                    pollingIntervalRef.current = null
                    handleTaskCompleted(taskId)
                }

                if (status === 'failed') {
                    clearInterval(poll)
                    pollingIntervalRef.current = null
                    setMessages((prev) =>
                        prev.map((msg) =>
                            msg.id === msgId ? { ...msg, content: t('chat.failed') } : msg
                        )
                    )
                    fetchHistoryRef.current?.()
                }

                if (status === 'cancelled') {
                    clearInterval(poll)
                    pollingIntervalRef.current = null
                    setCurrentTaskId(null)
                    setIsProcessing(false)
                }
            } catch {
                // 忽略网络错误，继续轮询
            }
        }, 5000)

        pollingIntervalRef.current = poll
    }

    // 处理路由状态变化
    useEffect(() => {
        const state = location.state as any || {}
        const newChat = state.newChat as boolean | undefined
        const conversationId = state.conversationId as string | undefined
        const taskId = state.taskId as string | undefined
        const userMessage = state.userMessage as string | undefined
        const userFileId = state.audioFileId as string | undefined
        const params = state.params || {}
        const userFilename = state.filename as string | undefined

        // 处理新建空会话
        if (newChat) {
            handleNewConversation()
            // 清除 location.state 避免重复触发
            if (location.state && (location.state as any).newChat) {
                window.history.replaceState({}, '', location.pathname)
            }
            return
        }

        // 处理加载指定会话
        if (conversationId) {
            setCurrentConversationId(conversationId)
            loadConversation(conversationId)
            return
        }

        // 处理任务ID（旧逻辑兼容）
        if (taskId && userMessage) {
            setMessages([])
            setCurrentTaskId(taskId)

            if (userFilename) setUploadedFileName(userFilename)
            if (params.instrument) setInstrument(params.instrument)
            if (params.tempo) setTempo(String(params.tempo))
            if (params.duration) setDuration(String(params.duration))
            if (params.filename) setFilename(params.filename)

            // 添加用户消息
            const userMsg: Message = {
                id: nextId(),
                type: 'user',
                content: userMessage,
                userFile: userFilename || undefined,
            }
            setMessages([userMsg])

            // 添加处理中消息
            const processingMsg: Message = {
                id: nextId(),
                type: 'ai',
                taskId: taskId,
                deepThinking: t('chat.deepThinking'),
                content: t('chat.taskCreated'),
            }
            setMessages((prev) => [...prev, processingMsg])

            pollTaskStatus(taskId, processingMsg.id)
        }
    }, [location.state, loadConversation, handleNewConversation, t])

    // 文件选择
    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        console.log('[ChatFlow] handleFileSelect called', e)
        const file = e.target.files?.[0]
        if (!file) {
            console.log('[ChatFlow] No file selected')
            return
        }

        console.log('[ChatFlow] File selected:', file.name, file.size)

        const validFormats = ['mp3', 'wav', 'flac', 'm4a', 'ogg']
        const ext = file.name.split('.').pop()?.toLowerCase()
        if (!ext || !validFormats.includes(ext)) {
            setUploadError(`不支持的格式: .${ext}，支持: ${validFormats.join(', ')}`)
            setUploadSuccess(null)
            return
        }
        if (file.size > 50 * 1024 * 1024) {
            console.log('[ChatFlow] File too large')
            setUploadError('文件过大，最大支持 50MB')
            setUploadSuccess(null)
            return
        }

        console.log('[ChatFlow] Setting upload state...')
        setUploadError(null)
        setUploadSuccess(null)
        setIsUploading(true)
        setUploadProgress(0)
        console.log('[ChatFlow] Upload state set, entering try block...')

        try {
            console.log('[ChatFlow] Starting upload...')
            const progressInterval = setInterval(() => {
                setUploadProgress((prev) => Math.min(prev + 10, 90))
            }, 200)

            console.log('[ChatFlow] Calling api.uploadFile...')
            const res = await api.uploadFile(file)
            console.log('[ChatFlow] Upload response received:', res)
            clearInterval(progressInterval)
            setUploadProgress(100)

            if (res.code === 200) {
                console.log('[ChatFlow] Upload success, setting audioFileId:', res.data.file_id)
                setAudioFileId(res.data.file_id)
                setUploadedFileName(res.data.filename)
                setUploadSuccess(
                    `文件已上传: ${res.data.filename} (${res.data.file_size.toFixed(2)} MB)${
                        res.data.duration ? `, 时长: ${Math.round(res.data.duration)}秒` : ''
                    }`
                )
                setUploadError(null)
            } else {
                setUploadError(res.message || '文件上传失败')
                setUploadSuccess(null)
            }
        } catch (err) {
            console.error('上传失败:', err)
            setUploadError(`上传失败: ${err instanceof Error ? err.message : '未知错误'}`)
            setUploadSuccess(null)
        } finally {
            setIsUploading(false)
            setTimeout(() => setUploadProgress(0), 500)
        }
    }

    // 取消任务
    const handleCancel = async () => {
        if (!currentTaskId) return

        if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
        }

        await api.cancelTask(currentTaskId)
        setCurrentTaskId(null)
        setIsProcessing(false)
    }

    // 拖拽相关
    const [position, setPosition] = useState({ x: 24, y: 80 })
    const [isDragging, setIsDragging] = useState(false)
    const dragRef = useRef<{
        startX: number
        startY: number
        initialLeft: number
        initialTop: number
    } | null>(null)

    const handleMouseDown = (e: React.MouseEvent) => {
        e.preventDefault()
        setIsDragging(true)
        dragRef.current = {
            startX: e.clientX,
            startY: e.clientY,
            initialLeft: position.x,
            initialTop: position.y,
        }
    }

    const handleMouseMove = (e: MouseEvent) => {
        if (!isDragging || !dragRef.current) return
        const dx = e.clientX - dragRef.current.startX
        const dy = e.clientY - dragRef.current.startY
        setPosition({
            x: dragRef.current.initialLeft + dx,
            y: dragRef.current.initialTop + dy,
        })
    }

    const handleMouseUp = () => {
        setIsDragging(false)
        dragRef.current = null
    }

    useEffect(() => {
        if (isDragging) {
            window.addEventListener('mousemove', handleMouseMove)
            window.addEventListener('mouseup', handleMouseUp)
        } else {
            window.removeEventListener('mousemove', handleMouseMove)
            window.removeEventListener('mouseup', handleMouseUp)
        }
        return () => {
            window.removeEventListener('mousemove', handleMouseMove)
            window.removeEventListener('mouseup', handleMouseUp)
        }
    }, [isDragging])

    return (
        <div className="flex flex-col h-screen bg-white text-gray-800 font-sans page-enter">
            <TopBar
                onNewChat={() => handleNewConversation()}
            />

            <div className="flex flex-1 overflow-hidden">
                {/* 侧边栏 */}
                <Sidebar
                    sidebarOpen={sidebarOpen}
                    setSidebarOpen={setSidebarOpen}
                    currentConversationId={currentConversationId}
                    setCurrentConversationId={setCurrentConversationId}
                    onNewConversation={handleNewConversation}
                    recentTasks={recentTasks}
                    currentTaskId={currentTaskId}
                    setCurrentTaskId={setCurrentTaskId}
                    onRefresh={async () => {
                        if (fetchHistoryRef.current) await fetchHistoryRef.current()
                    }}
                />

                {/* 主内容区 */}
                <main className="flex-1 flex flex-col bg-white overflow-hidden">
                    {/* 侧边栏悬浮按钮 */}
                    {!sidebarOpen && (
                        <button
                            onClick={() => setSidebarOpen(true)}
                            onMouseDown={handleMouseDown}
                            className="w-10 h-10 bg-[#458ecb] rounded-full flex items-center justify-center border border-[#e0f2fe] hover:bg-[#3a7db5] transition z-10"
                            style={{
                                position: 'fixed',
                                left: position.x,
                                top: position.y,
                                cursor: isDragging ? 'grabbing' : 'grab',
                            }}
                        >
                            <svg width="12" height="18" viewBox="0 0 12 18" fill="none">
                                <path
                                    d="M4 18C2.8999 18 1.9585 17.6083 1.17505 16.825C0.391602 16.0417 0 15.1 0 14C0 12.9 0.391602 11.9583 1.17505 11.175C1.9585 10.3917 2.8999 10 4 10C4.3833 10 4.73755 10.0458 5.0625 10.1375C5.38745 10.2292 5.69995 10.3667 6 10.55V0H12V4H8V14C8 15.1 7.6084 16.0417 6.82495 16.825C6.0415 17.6083 5.1001 18 4 18Z"
                                    fill="white"
                                />
                            </svg>
                        </button>
                    )}

                    {/* 聊天内容区域 */}
                    <div className="flex-1 overflow-y-auto px-8 py-6 relative" ref={messagesEndRef}>
                        <div className="max-w-[768px] mx-auto space-y-6 relative">
                            {/* 会话标题 */}
                            {currentConversation && (
                                <div className="text-center mb-4">
                                    <h2 className="text-lg font-medium text-gray-700">
                                        {currentConversation.title || '未命名会话'}
                                    </h2>
                                    <div className="flex items-center justify-center gap-2 mt-1">
                                        <span
                                            className={`px-2 py-0.5 text-xs rounded ${
                                                currentConversation.status === 'active'
                                                    ? 'bg-green-100 text-green-600'
                                                    : 'bg-gray-100 text-gray-500'
                                            }`}
                                        >
                                            {currentConversation.status === 'active'
                                                ? '进行中'
                                                : '已完成'}
                                        </span>
                                        <span className="text-xs text-gray-400">
                                            {currentConversation.messages.length} 条消息
                                        </span>
                                    </div>
                                </div>
                            )}

                            {/* 欢迎消息（空会话时显示） */}
                            {messages.length === 0 && !currentConversation && <WelcomeMessage />}

                            {/* 消息列表 */}
                            <MessageList messages={messages} t={t} />

                            {/* WebSocket连接状态指示器 */}
                            {currentTaskId && isConnected && (
                                <div className="fixed bottom-24 right-8 flex items-center gap-2 px-3 py-1.5 bg-green-100 text-green-700 text-xs rounded-full shadow">
                                    <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                                    WebSocket 已连接
                                </div>
                            )}
                        </div>
                    </div>

                    {/* 底部输入区域 */}
                    <ChatInputArea
                        isProcessing={isProcessing}
                        onCancel={handleCancel}
                        mode="chat"
                        isFloating={false}
                        inputValue={inputValue}
                        setInputValue={setInputValue}
                        handleSend={handleSend}
                        fileInputRef={fileInputRef}
                        handleFileSelect={handleFileSelect}
                        instrument={instrument}
                        setInstrument={setInstrument}
                        tempo={tempo}
                        setTempo={setTempo}
                        duration={duration}
                        setDuration={setDuration}
                        filename={filename}
                        setFilename={setFilename}
                        isUploading={isUploading}
                        uploadProgress={uploadProgress}
                        uploadError={uploadError}
                        uploadSuccess={uploadSuccess}
                    />
                </main>
            </div>

            {/* Toast */}
            {toastMessage && (
                <Toast
                    message={toastMessage}
                    duration={5000}
                    onClose={() => setToastMessage(null)}
                />
            )}
        </div>
    )
}

export default ChatFlow
