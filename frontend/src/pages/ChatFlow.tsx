// src/pages/ChatFlow.tsx
import { useTranslation } from 'react-i18next'
import {useState, useEffect, useRef} from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'
import type { TaskListItem } from '../types'
import TopBar from '../components/TopBar';
import Sidebar from '../components/Sidebar';
import Toast from '../components/notifications/Toast';

interface Message {
    id: string
    type: 'ai' | 'user'
    content?: string
    deepThinking?: string
    fileName?: string
    fileInfo?: string
    userFile?: string
    audioFileId?: string  // 上传文件后返回的 file_id
    taskId?: string  // 关联的任务ID
    thinkingProcess?: { step: string; content: string; timestamp: string }[]  // 真实思考过程
    showThinking?: boolean  // 是否展开思考过程
}

function ChatFlow() {
    const { t, i18n } = useTranslation()
    const [showLang, setShowLang] = useState(false)
    const [sidebarOpen, setSidebarOpen] = useState(false)
    const [instrument, setInstrument] = useState('Acoustic Piano')
    const [showInstrument, setShowInstrument] = useState(false)
    const [duration, setDuration] = useState('180')
    const [tempo, setTempo] = useState('120')
    const [filename, setFilename] = useState('Untitled_Track')
    const [inputValue, setInputValue] = useState('')
    const instruments = ['Acoustic Piano', 'Violin']
    const idCounter = useRef(Date.now())  // 用时间戳初始化，避免重复
    const fetchHistoryRef = useRef<(() => Promise<void>) | null>(null)
    const location = useLocation()
    const [audioFile, setAudioFile] = useState<File | null>(null)
    const [audioFileId, setAudioFileId] = useState<string | null>(null)
    const [uploadError, setUploadError] = useState<string | null>(null)
    const [uploadSuccess, setUploadSuccess] = useState<string | null>(null)
    const [uploadProgress, setUploadProgress] = useState<number>(0)
    const [isUploading, setIsUploading] = useState(false)
    const fileInputRef = useRef<HTMLInputElement>(null)
    const [toastMessage, setToastMessage] = useState<string | null>(null);

    const nextId = () => {
        idCounter.current += 1
        return `${Date.now()}-${idCounter.current}`  // 时间戳+计数器组合
    }

    const [messages, setMessages] = useState<Message[]>([
        {
            id: 1,
            type: 'user',
            userFile: 'Midni...ft.mp3',
            content: t('chat.userMessage'),
        },
        {
            id: 2,
            type: 'ai',
            deepThinking: t('chat.deepThinking'),
            content: t('chat.aiResponse'),
            fileName: t('chat.fileName'),
            fileInfo: t('chat.fileInfo'),
        },
    ])

    // 历史任务列表
    const [recentTasks, setRecentTasks] = useState<TaskListItem[]>([])
    const [currentTaskId, setCurrentTaskId] = useState<string | null>(null)

    const showError = (message: string) => {
        const errorMsg: Message = {
            id: nextId(),
            type: 'ai',
            content: message,
        }
        setMessages(prev => [...prev, errorMsg])
    }

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
        // 不再初始加载，等用户手动点击刷新
    }, [])

    const handleSend = async () => {
        if (!inputValue.trim()) return

        // 用户消息
        const newUserMessage: Message = {
            id: nextId(),
            type: 'user',
            content: inputValue.trim(),
        }
        setMessages(prev => [...prev, newUserMessage])
        setInputValue('')

        try {
            const res = await api.createTask({
                user_request: inputValue.trim(),
                source_type: 'upload',
                source_value: audioFileId || undefined,
                instrument,
                duration: parseInt(duration) || 30,
                tempo: parseInt(tempo) || 120,
                filename,
            })


            if (res.code === 200) {
                setCurrentTaskId(res.data.task_id)
                fetchHistoryRef.current?.()

                // 添加"处理中"消息，关联任务ID
                const processingMsg: Message = {
                    id: nextId(),
                    type: 'ai',
                    taskId: res.data.task_id,
                    deepThinking: t('chat.deepThinking'),
                    content: t('chat.taskCreated'),
                }
                setMessages(prev => [...prev, processingMsg])

                // 轮询任务状态直到完成（后续优化，先占位）
                pollTaskStatus(res.data.task_id, processingMsg.id)
            } else {
                showError(res.message || t('chat.createFailed'))
            }
        } catch  {
            showError(t('chat.networkError'))

        }
    }

    const pollTaskStatus = async (taskId: string, msgId: string) => {
        let attempts = 0
        const maxAttempts = 30

        const poll = setInterval(async () => {
            attempts++
            if (attempts > maxAttempts) {
                clearInterval(poll)
                updateMessage(msgId, { content: t('chat.timeout') || '任务超时，请重试。' })
                return
            }

            try {
                const res = await api.getTaskStatus(taskId)
                if (res.code !== 200) return

                const { status, current_subtask, subtask_progress, message, thinking_process } = res.data

                console.log('[DEBUG] getTaskStatus:', { status, current_subtask, thinking_process })

                // 合并思考过程（追加新条目，避免覆盖）
                setMessages(prev => {
                    const msgIndex = prev.findIndex(m => m.id === msgId)
                    if (msgIndex === -1) return prev

                    const existingMsg = prev[msgIndex]
                    const existingSteps = existingMsg.thinkingProcess || []
                    const newSteps = thinking_process || []

                    // 合并：保留旧条目，追加新条目
                    const mergedSteps = [...existingSteps]
                    for (const step of newSteps) {
                        const exists = mergedSteps.some(
                            s => s.step === step.step && s.timestamp === step.timestamp
                        )
                        if (!exists) {
                            mergedSteps.push(step)
                        }
                    }

                    return prev.map(msg =>
                        msg.id === msgId ? {
                            ...msg,
                            content: message || current_subtask || msg.content,
                            thinkingProcess: mergedSteps,
                        } : msg
                    )
                })

                if (status === 'completed') {
                    clearInterval(poll)
                    console.log('[DEBUG] Task completed, fetching result...')
                    // 获取最终结果
                    const resultRes = await api.getTaskResult(taskId)
                    console.log('[DEBUG] getTaskResult result:', resultRes)

                    // 合并思考过程
                    const finalThinking = resultRes?.data?.thinking_process || []
                    console.log('[DEBUG] finalThinking:', finalThinking)

                    setMessages(prev => {
                        const msgIndex = prev.findIndex(m => m.id === msgId)
                        if (msgIndex === -1) return prev
                        const existingMsg = prev[msgIndex]
                        const existingSteps = existingMsg.thinkingProcess || []
                        const mergedSteps = [...existingSteps]
                        for (const step of finalThinking) {
                            const exists = mergedSteps.some(
                                s => s.step === step.step && s.timestamp === step.timestamp
                            )
                            if (!exists) {
                                mergedSteps.push(step)
                            }
                        }
                        console.log('[DEBUG] mergedSteps:', mergedSteps)

                        const updates: Partial<Message> = {
                        content: t('chat.completed'),
                        fileName: resultRes?.data?.audio_url,
                        fileInfo: resultRes?.data?.duration ? `${resultRes.data.duration}s` : undefined,
                        thinkingProcess: mergedSteps,
                    }
                        console.log('[DEBUG] Updating message with:', updates)

                        return prev.map(msg =>
                            msg.id === msgId ? { ...msg, ...updates } : msg
                        )
                    })
                    fetchHistoryRef.current?.()
                }

                if (status === 'failed') {
                    clearInterval(poll)
                    updateMessage(msgId, { content: t('chat.failed') })
                    fetchHistoryRef.current?.()
                }
            } catch {
                // 忽略网络错误，继续轮询
            }
        }, 5000)
    }

    // 更新消息内容
    const updateMessage = (msgId: string, updates: Partial<Message>) => {
        setMessages(prev => prev.map(msg =>
            msg.id === msgId ? { ...msg, ...updates } : msg
        ))
    }

    const handleAutoSend = async (text: string) => {
        const newUserMessage: Message = {
            id: nextId(),
            type: 'user',
            content: text,
        }
        setMessages(prev => [...prev, newUserMessage])

        try {
            const res = await api.createTask({
                user_request: text.trim(),
                source_type: 'upload',
                source_value: audioFileId || undefined,
                instrument,
                duration: parseInt(duration) || 30,
                tempo: parseInt(tempo) || 120,
                filename,
            })

            if (res.code === 200) {
                setCurrentTaskId(res.data.task_id)

                // 添加"处理中"消息
                const processingMsg: Message = {
                    id: nextId(),
                    type: 'ai',
                    taskId: res.data.task_id,
                    deepThinking: t('chat.deepThinking'),
                    content: t('chat.taskCreated'),
                }
                setMessages(prev => [...prev, processingMsg])

                // 轮询任务状态直到完成
                pollTaskStatus(res.data.task_id, processingMsg.id)
            } else {
                showError(res.message || t('chat.createFailed'))
            }
        } catch {
            showError(t('chat.networkError'))
        }
    }

    useEffect(() => {
        const userMessage = location.state?.userMessage as string | undefined
        const userFileId = location.state?.audioFileId as string | undefined
        const userInstrument = location.state?.instrument as string | undefined
        const userTempo = location.state?.tempo as string | undefined
        const userDuration = location.state?.duration as string | undefined

        setAudioFileId(userFileId || null)
        if (userInstrument) setInstrument(userInstrument)
        if (userTempo) setTempo(userTempo)
        if (userDuration) setDuration(userDuration)

        // 使用 sessionStorage 防止页面刷新后重复发送
        const hasSent = sessionStorage.getItem('chat_auto_sent')
        if (userMessage && !hasSent) {
            sessionStorage.setItem('chat_auto_sent', 'true')
            handleAutoSend(userMessage)
        }
    }, [location.state])

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return

        // 验证格式
        const validFormats = ['mp3', 'wav', 'flac', 'm4a', 'ogg']
        const ext = file.name.split('.').pop()?.toLowerCase()
        if (!ext || !validFormats.includes(ext)) {
            setUploadError(`不支持的格式: .${ext}，支持: ${validFormats.join(', ')}`)
            setUploadSuccess(null)
            return
        }

        // 验证大小 (50MB)
        if (file.size > 50 * 1024 * 1024) {
            setUploadError('文件过大，最大支持 50MB')
            setUploadSuccess(null)
            return
        }

        setAudioFile(file)
        setUploadError(null)
        setUploadSuccess(null)
        setIsUploading(true)
        setUploadProgress(0)

        try {
            console.log('开始上传文件:', file.name)
            // 模拟进度
            const progressInterval = setInterval(() => {
                setUploadProgress(prev => Math.min(prev + 10, 90))
            }, 200)

            const res = await api.uploadFile(file)
            clearInterval(progressInterval)
            setUploadProgress(100)

            console.log('上传响应:', res)
            if (res.code === 200) {
                setAudioFileId(res.data.file_id)
                setUploadSuccess(`文件已上传: ${res.data.filename} (${(res.data.file_size).toFixed(2)} MB)${res.data.duration ? `, 时长: ${Math.round(res.data.duration)}秒` : ''}`)
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


    // const handleSend = () => {
    //     if (!inputValue.trim()) return
    //
    //     const newUserMessage: Message = {
    //         id: Date.now(),
    //         type: 'user',
    //         content: inputValue.trim(),
    //     }
    //
    //     setMessages(prev => [...prev, newUserMessage])
    //     setInputValue('')
    //
    //     // 模拟 AI 回复（可选，2秒后自动回复）
    //     setTimeout(() => {
    //         const aiReply: Message = {
    //             id: Date.now() + 1,
    //             type: 'ai',
    //             deepThinking: t('chat.deepThinking'),
    //             content: "I've received your request. Let me analyze that for you.",
    //         }
    //         setMessages(prev => [...prev, aiReply])
    //     }, 2000)
    // }

    const showToast = (msg: string) => {
        setToastMessage(msg);
    };

    return (
        <div className="flex flex-col h-screen bg-white text-gray-800 font-sans page-enter">
            {/* 顶栏同级独立于左侧边栏和 main */}
            <TopBar />

            <div className="flex flex-1 overflow-hidden">
                {/* ========== 左侧边栏 ========== */}
                <Sidebar
                    sidebarOpen={sidebarOpen}
                    setSidebarOpen={setSidebarOpen}
                    recentTasks={recentTasks}
                    currentTaskId={currentTaskId}
                    setCurrentTaskId={setCurrentTaskId}
                    onRefresh={async () => {
                        if (fetchHistoryRef.current) await fetchHistoryRef.current();
                    }}
                />
                {/* ========== 中间主内容区 ========== */}
                <main className="flex-1 flex flex-col bg-white">
                    {/* 侧边栏收起时的 Logo 按钮 - absolute 悬浮 */}
                    {/* 暂不允许打开侧边栏，待完成历史消息后允许 */}
                    {/*{!sidebarOpen && (*/}
                    {/*    <button*/}
                    {/*        onClick={() => setSidebarOpen(true)}*/}
                    {/*        className="fixed left-6 top-20 w-10 h-10 bg-[#458ecb] rounded-full flex items-center justify-center border border-[#e0f2fe] hover:bg-[#3a7db5] transition z-10"*/}
                    {/*    >*/}
                    {/*        <svg width="12" height="18" viewBox="0 0 12 18" fill="none">*/}
                    {/*            <path d="M4 18C2.8999 18 1.9585 17.6083 1.17505 16.825C0.391602 16.0417 0 15.1 0 14C0 12.9 0.391602 11.9583 1.17505 11.175C1.9585 10.3917 2.8999 10 4 10C4.3833 10 4.73755 10.0458 5.0625 10.1375C5.38745 10.2292 5.69995 10.3667 6 10.55V0H12V4H8V14C8 15.1 7.6084 16.0417 6.82495 16.825C6.0415 17.6083 5.1001 18 4 18Z" fill="white"/>*/}
                    {/*        </svg>*/}
                    {/*    </button>*/}
                    {/*)}*/}
                    {!sidebarOpen && (
                        <button
                            onClick={() => showToast(t('sidebar.notAvailable') || '侧边栏暂不开放')}
                            className="fixed left-6 top-20 w-10 h-10 bg-[#458ecb] rounded-full flex items-center justify-center border border-[#e0f2fe] hover:bg-[#3a7db5] transition z-10"
                        >
                            <svg width="12" height="18" viewBox="0 0 12 18" fill="none">
                                <path d="M4 18C2.8999 18 1.9585 17.6083 1.17505 16.825C0.391602 16.0417 0 15.1 0 14C0 12.9 0.391602 11.9583 1.17505 11.175C1.9585 10.3917 2.8999 10 4 10C4.3833 10 4.73755 10.0458 5.0625 10.1375C5.38745 10.2292 5.69995 10.3667 6 10.55V0H12V4H8V14C8 15.1 7.6084 16.0417 6.82495 16.825C6.0415 17.6083 5.1001 18 4 18Z" fill="white"/>
                            </svg>
                        </button>
                    )}

                    {/* 聊天内容区域 - 可滚动 */}
                    <div className="flex-1 overflow-y-auto px-8 py-6 relative">
                        <div className="max-w-[768px] mx-auto space-y-6 relative">

                            {/* 欢迎区域 */}
                            <div className="w-[600px] py-5 flex flex-col gap-y-2 relative overflow-visible">
                                <div className="absolute -left-[18px] top-[15px] opacity-10 pointer-events-none">
                                    <svg width="60" height="90" viewBox="0 0 60 90" fill="none">
                                        <path d="M20 90C14.5 90 9.7915 88.0417 5.875 84.125C1.9585 80.2083 0 75.5 0 70C0 64.5 1.9585 59.7917 5.875 55.875C9.7915 51.9583 14.5 50 20 50C21.9167 50 23.6875 50.2292 25.3125 50.6875C26.9375 51.1458 28.5 51.8333 30 52.75V0H60V20H40V70C40 75.5 38.0417 80.2083 34.125 84.125C30.2083 88.0417 25.5 90 20 90Z" fill="#00639d"/>
                                    </svg>
                                </div>
                                <h3 className="text-3xl font-extrabold leading-tight font-['Manrope'] welcome-text">
                                    <span className="text-[#2f3334]">{t('welcome.titleBefore')}</span>
                                    <span className="text-[#00639d]">{t('welcome.titleHighlight')}</span>
                                    {t('welcome.titleAfter') && <span className="text-[#2f3334]">{t('welcome.titleAfter')}</span>}
                                </h3>
                                <div className="welcome-subtitle">
                                    <p className="text-base text-[#5b6061] leading-relaxed font-['Inter']">
                                        {t('welcome.subtitle')}
                                    </p>
                                </div>
                            </div>

                            {/* 对话列表 */}
                            {messages.map((msg) => (
                                <div key={msg.id}>
                                    {msg.type === 'ai' && (
                                        <div className="flex gap-3">
                                            {/* AI 头像 */}
                                            <div className="w-8 h-8 bg-[#f0f9ff] rounded-full flex items-center justify-center flex-shrink-0">
                                                <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
                                                    <path d="M18 8L16.75 5.25L14 4L16.75 2.75L18 0L19.25 2.75L22 4L19.25 5.25L18 8ZM18 22L16.75 19.25L14 18L16.75 16.75L18 14L19.25 16.75L22 18L19.25 19.25L18 22ZM8 19L5.5 13.5L0 11L5.5 8.5L8 3L10.5 8.5L16 11L10.5 13.5L8 19Z" fill="#00639d"/>
                                                </svg>
                                            </div>
                                            {/* 灰色背景容器 */}
                                            <div className="flex-1 bg-[#f3f4f4] rounded-tr-2xl rounded-bl-2xl rounded-br-2xl pt-[14.75px] px-6 pb-4 flex flex-col gap-y-4 max-w-[508.8px]">
                                                {/* 思考过程展示 */}
                                                {msg.thinkingProcess && msg.thinkingProcess.length > 0 && (
                                                    <div className="bg-white rounded-xl border border-gray-200 p-3 -mx-2">
                                                        <p className="text-xs font-medium text-[#00639d] mb-2">
                                                            深度思考过程 ({msg.thinkingProcess.length}步)
                                                        </p>
                                                        <div className="space-y-1.5">
                                                            {msg.thinkingProcess.map((thought, idx) => (
                                                                <div key={idx} className="flex items-start gap-2">
                                                                <span className="inline-block px-1.5 py-0.5 bg-[#00639d]/10 text-[#00639d] rounded text-[10px] font-medium flex-shrink-0">
                                                                    {thought.step}
                                                                </span>
                                                                    <span className="text-xs text-gray-600 leading-relaxed">{thought.content}</span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}

                                                {/* AI 回复文字 */}
                                                {msg.content && (
                                                    <p className="text-gray-700 text-sm leading-relaxed">{msg.content}</p>
                                                )}

                                                {/* 音频文件卡片 */}
                                                {msg.fileName && (
                                                    <div className="bg-white border border-gray-200 rounded-xl p-4 -mx-2">
                                                        <div className="flex items-center gap-3">
                                                            <div className="w-8 h-8 bg-[#0284c7] rounded-lg flex items-center justify-center">
                                                                <svg width="11" height="14" viewBox="0 0 11 14" fill="none">
                                                                    <path d="M0 14V0H11L0 7V14ZM2 7L7.25 3.65V10.35L2 7Z" fill="white"/>
                                                                </svg>
                                                            </div>
                                                            <div className="flex-1">
                                                                <p className="font-medium text-gray-800">{msg.fileName}</p>
                                                                {msg.fileInfo && (
                                                                    <p className="text-xs text-gray-500">{msg.fileInfo}</p>
                                                                )}
                                                            </div>
                                                            <button
                                                                onClick={() => api.downloadFile(msg.fileName!, msg.fileName!.split('/').pop() || 'audio')}
                                                                className="px-3 py-1.5 bg-[#0284c7] text-white text-xs font-medium rounded-lg hover:bg-[#0369a1] transition"
                                                            >
                                                                下载
                                                            </button>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    )}

                                    {msg.type === 'user' && (
                                        <div className="flex justify-end">
                                            <div className="max-w-[555px] space-y-[0.5px]">
                                                {/* 用户文件附件 */}
                                                {msg.userFile && (
                                                    <div className="flex items-center gap-4 bg-white border border-[#afb3b3]/60 rounded-t-[15px] rounded-bl-[2px] rounded-br-[10px] px-4 py-[13px] w-fit ml-auto">
                                                        {/* 音频图标 */}
                                                        <div className="w-[29px] h-[31px] bg-[#e0f2fe] rounded-lg flex items-center justify-center flex-shrink-0">
                                                            <svg width="17" height="21" viewBox="0 0 17 21" fill="none">
                                                                <path d="M0 21V0H17L3.09 7H0V21ZM2 7L10.2 4.65V9.35L2 7Z" fill="#0284c7"/>
                                                            </svg>
                                                        </div>
                                                        {/* 文件名 */}
                                                        <span className="text-xs font-semibold text-[#2f3334]">{msg.userFile}</span>
                                                    </div>
                                                )}
                                                {/* 用户消息气泡 */}
                                                {msg.content && (
                                                    <div className="bg-[#cfe6f0] rounded-2xl rounded-tr-none shadow-[0px_1px_2px_0px_#0000000D] px-6 py-[14.88px] max-w-[508.8px]">
                                                        <p className="text-sm text-[#40555d] leading-relaxed">{msg.content}</p>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* 参数面板 */}
                    <div className="mt-6 max-w-[768px] mx-auto px-4">
                        <div className="bg-white border border-[#e0f2fe] rounded-3xl p-8">
                            <div className="grid grid-cols-2 gap-x-12 gap-y-6">
                                {/* INSTRUMENT - 下拉 */}
                                <div className="flex flex-row-reverse items-center justify-between h-[42px]">
                                    <div className="w-[200px] relative">
                                        <button
                                            onClick={() => setShowInstrument(!showInstrument)}
                                            className="w-full bg-[#f8fafc] border border-[#f1f5f9] rounded-xl py-2.5 px-4 flex items-center justify-between"
                                        >
                                            <span className="text-sm font-normal text-[#2f3334]">{instrument}</span>
                                            <svg width="7" height="4.32" viewBox="0 0 7 4.32" fill="none">
                                                <path d="M3.5 4.32L0 0.82L0.81665 0L3.5 2.68335L6.18335 0L7 0.82L3.5 4.32Z" fill="#94a3b8"/>
                                            </svg>
                                        </button>
                                        {showInstrument && (
                                            <div className="absolute top-full left-0 w-full bg-white border border-[#f1f5f9] rounded-xl mt-1 shadow-lg z-10">
                                                {instruments.map((inst) => (
                                                    <button
                                                        key={inst}
                                                        onClick={() => { setInstrument(inst); setShowInstrument(false) }}
                                                        className={`w-full text-left px-4 py-2.5 text-sm hover:bg-gray-50 first:rounded-t-xl last:rounded-b-xl ${instrument === inst ? 'text-[#0369a1] font-medium' : 'text-[#2f3334]'}`}
                                                    >
                                                        {inst}
                                                    </button>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                    <p className="text-[11px] font-semibold uppercase tracking-[2.2px] text-[#94a3b8]">{t('params.instrument')}</p>
                                </div>

                                {/* DURATION - 输入框 */}
                                <div className="flex flex-row-reverse items-center justify-between h-[42px]">
                                    <div className="w-[200px]">
                                        <div className="bg-[#f8fafc] border border-[#f1f5f9] rounded-xl py-2.5 px-4 flex items-center justify-between">
                                            <input
                                                type="text"
                                                value={duration}
                                                onChange={(e) => setDuration(e.target.value)}
                                                className="w-[120px] bg-transparent outline-none text-sm font-semibold text-[#2f3334]"
                                            />
                                            <span className="text-[10px] font-semibold uppercase text-[#94a3b8]">{t('params.sec')}</span>
                                        </div>
                                    </div>
                                    <p className="text-[11px] font-semibold uppercase tracking-[2.2px] text-[#94a3b8]">{t('params.duration')}</p>
                                </div>

                                {/* TEMPO (BPM) - 输入框 */}
                                <div className="flex flex-row-reverse items-center justify-between h-[42px]">
                                    <div className="w-[200px]">
                                        <div className="bg-[#f8fafc] border border-[#f1f5f9] rounded-xl py-2.5 px-4 flex items-center justify-between">
                                            <input
                                                type="text"
                                                value={tempo}
                                                onChange={(e) => setTempo(e.target.value)}
                                                className="w-[120px] bg-transparent outline-none text-sm font-semibold text-[#2f3334]"
                                            />
                                            <span className="text-[10px] font-semibold uppercase text-[#94a3b8]">{t('params.bpm')}</span>
                                        </div>
                                    </div>
                                    <p className="text-[11px] font-semibold uppercase tracking-[2.2px] text-[#94a3b8]">{t('params.tempo')}</p>
                                </div>

                                {/* FILENAME - 输入框 */}
                                <div className="flex flex-row-reverse items-center justify-between h-[42px]">
                                    <div className="w-[200px]">
                                        <div className="bg-[#f8fafc] border border-[#f1f5f9] rounded-xl py-2.5 px-4">
                                            <input
                                                type="text"
                                                value={filename}
                                                onChange={(e) => setFilename(e.target.value)}
                                                className="w-full bg-transparent outline-none text-sm font-semibold text-[#2f3334]"
                                            />
                                        </div>
                                    </div>
                                    <p className="text-[11px] font-semibold uppercase tracking-[2.2px] text-[#94a3b8]">{t('params.filename')}</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* 底部输入栏 */}
                    <div className="border-t border-gray-100 px-4 py-3">
                        <div className="max-w-[768px] mx-auto">
                            {/* 上传状态显示 - 紧凑样式 */}
                            {(isUploading || uploadError || uploadSuccess) && (
                                <div className="mb-2 px-2 py-2 bg-[#f8fafc] rounded-xl border border-gray-100">
                                    {isUploading && (
                                        <div className="flex items-center gap-3">
                                            <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
                                            <span className="text-sm text-gray-600">正在上传... {uploadProgress}%</span>
                                        </div>
                                    )}
                                    {uploadError && (
                                        <div className="flex items-center gap-2 text-red-600">
                                            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                                                <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm-.75 4.75v4.5a.75.75 0 001.5 0v-4.5a.75.75 0 00-1.5 0zM8 10.5a.875.875 0 110-1.75.875.875 0 010 1.75z"/>
                                            </svg>
                                            <span className="text-sm">{uploadError}</span>
                                        </div>
                                    )}
                                    {uploadSuccess && (
                                        <div className="flex items-center gap-2 text-green-600">
                                            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                                                <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z"/>
                                            </svg>
                                            <span className="text-sm">{uploadSuccess}</span>
                                        </div>
                                    )}
                                </div>
                            )}

                            <div className="relative flex flex-row-reverse items-center gap-2 bg-white border border-[#e0f2fe] rounded-3xl px-2.5 py-2.5">
                                <button
                                    onClick={handleSend}
                                    className="w-11 h-11 bg-[#00639d] rounded-2xl flex items-center justify-center flex-shrink-0 shadow-[0px_10px_15px_-3px_#00639d4D,0px_4px_6px_-4px_#00639d4D] hover:bg-[#005288] transition"
                                >
                                    <svg width="19" height="16" viewBox="0 0 19 16" fill="none">
                                        <path d="M0 16V0L19 8L0 16ZM2 13L13.85 8L2 3V6.5L8 8L2 9.5V13Z" fill="#f7f9ff"/>
                                    </svg>
                                </button>
                                {/* 输入框 */}
                                <div className="flex-1 px-3 py-2.5 min-h-[39px]">
                                <textarea
                                    placeholder={t('input.placeholder')}
                                    value={inputValue}
                                    onChange={(e) => setInputValue(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' && !e.shiftKey) {
                                            e.preventDefault()
                                            handleSend()
                                        }
                                    }}
                                    className="w-full bg-transparent outline-none resize-none text-[15px] text-gray-700 placeholder-[#94a3b8] leading-tight"
                                    rows={1}
                                />
                                </div>
                                <div className="w-px h-8 bg-[#f1f5f9] mx-1"></div>
                                <div className="flex flex-row-reverse items-center gap-4 px-1">
                                    <svg width="13" height="20" viewBox="0 0 13 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                        <path d="M12.5 13.75C12.5 15.48315 11.8916 16.95801 10.67505 18.1748C9.4585 19.39136 7.9834 20 6.25 20C4.5166 20 3.0415 19.39136 1.82495 18.1748C0.608398 16.95801 0 15.48315 0 13.75V4.5C0 3.25 0.4375 2.1875 1.3125 1.3125C2.1875 0.4375 3.25 0 4.5 0C5.75 0 6.8125 0.4375 7.6875 1.3125C8.5625 2.1875 9 3.25 9 4.5V13.25C9 14.0166 8.7334 14.6665 8.19995 15.19995C7.6665 15.7334 7.0166 16 6.25 16C5.4834 16 4.8335 15.7334 4.30005 15.19995C3.7666 14.6665 3.5 14.0166 3.5 13.25V4H5.5V13.25C5.5 13.4668 5.5708 13.6455 5.7124 13.78735C5.854 13.92896 6.0332 14 6.25 14C6.4668 14 6.646 13.92896 6.7876 13.78735C6.9292 13.6455 7 13.4668 7 13.25V4.5C6.9834 3.8 6.73755 3.20825 6.26245 2.72485C5.7876 2.24145 5.19995 2 4.5 2C3.80005 2 3.2085 2.24145 2.7251 2.72485C2.2417 3.20825 2 3.8 2 4.5V13.75C1.9834 14.93335 2.3916 15.9375 3.2251 16.7622C4.05835 17.5872 5.06665 18 6.25 18C7.4165 18 8.4082 17.5872 9.2251 16.7622C10.0417 15.9375 10.4668 14.93335 10.5 13.75V4H12.5V13.75H12.5V20H10.5V20H6.25H12.5Z" fill="#94a3b8"/>
                                    </svg>
                                    <button
                                        onClick={() => fileInputRef.current?.click()}
                                        className="w-11 h-11 bg-[#f0f9ff] rounded-2xl flex items-center justify-center shadow-[inset_0px_2px_4px_0px_#0000000D] hover:bg-[#e0f2fe] transition"
                                    >
                                        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                                            <path d="M8 17.99976L8 11.99976L10 11.99976L10 13.99976L18 13.99976L18 15.99976L10 15.99976L10 17.99976L8 17.99976ZM0 15.99976L0 13.99976L6 13.99976L6 15.99976L0 15.99976ZM4 11.99976L4 9.99976L0 9.99976L0 7.99976L4 7.99976L4 5.99976L6 5.99976L6 11.99976L4 11.99976ZM8 9.99976L8 7.99976L18 7.99976L18 9.99976L8 9.99976ZM12 5.99976L12 -0.00024L14 -0.00024L14 1.99976L18 1.99976L18 3.99976L14 3.99976L14 5.99976L12 5.99976ZM0 3.99976L0 1.99976L10 1.99976L10 3.99976L0 3.99976Z" fill="#00639d"/>
                                        </svg>
                                    </button>
                                    {/* 隐藏的文件输入 */}
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept=".mp3,.wav,.flac,.m4a,.ogg"
                                        onChange={handleFileSelect}
                                        className="hidden"
                                    />
                                </div>
                            </div>
                        </div>
                    </div>
                </main>
            </div>

            {/* 全局 Toast */}
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
