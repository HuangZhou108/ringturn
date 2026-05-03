import { useTranslation } from 'react-i18next'
import {useState, useEffect, useRef} from 'react'
import { useLocation } from 'react-router-dom'
import { api } from './api'
import type { TaskListItem } from './types'

interface Message {
    id: number
    type: 'ai' | 'user'
    content?: string
    deepThinking?: string
    fileName?: string
    fileInfo?: string
    userFile?: string
    taskId?: string  // 关联的任务ID
}

function ChatFlow1() {
    const { t, i18n } = useTranslation()
    const [showLang, setShowLang] = useState(false)
    const [instrument, setInstrument] = useState('Acoustic Piano')
    const [showInstrument, setShowInstrument] = useState(false)
    const [duration, setDuration] = useState('180')
    const [tempo, setTempo] = useState('120')
    const [filename, setFilename] = useState('Untitled_Track')
    const [inputValue, setInputValue] = useState('')
    const instruments = ['Acoustic Piano', 'Violin']
    const idCounter = useRef(0)
    const fetchHistoryRef = useRef<(() => Promise<void>) | null>(null)
    const location = useLocation()
    const sentRef = useRef(false)
    const [audioFile, setAudioFile] = useState<File | null>(null)
    const [audioFileId, setAudioFileId] = useState<string | null>(null)
    const fileInputRef = useRef<HTMLInputElement>(null)
    const fileId = useRef<string | null>(null)

    const nextId = () => {
        idCounter.current += 1
        return idCounter.current
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
        fetchHistory()
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
                source_value: audioFileId || JSON.stringify({
                    instrument: instrument,
                    duration: duration,
                    tempo: tempo,
                    filename: filename,
                }),
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

    const pollTaskStatus = async (taskId: string, msgId: number) => {
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

                const { status, current_subtask, subtask_progress, message } = res.data

                // 更新进度提示
                if (current_subtask) {
                    updateMessage(msgId, {
                        content: `${message || current_subtask} (${Math.round(subtask_progress * 100)}%)`
                    })
                }

                if (status === 'completed') {
                    clearInterval(poll)
                    // 获取最终结果
                    const resultRes = await api.getTaskResult(taskId)
                    if (resultRes.code === 200 && resultRes.data) {
                        updateMessage(msgId, {
                            content: t('chat.completed'),
                            fileName: resultRes.data.audio_url,
                            fileInfo: `${resultRes.data.duration}s • ${resultRes.data.format}`,
                        })
                    }
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
        }, 2000)
    }

    // 更新消息内容
    const updateMessage = (msgId: number, updates: Partial<Message>) => {
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

        // 调用后端接口 + 模拟 AI 回复...
    }

    useEffect(() => {
        const userMessage = location.state?.userMessage as string | undefined
        const userFileId = location.state?.audioFileId as string | undefined

        fileId.current = userFileId || null

        if (userMessage && !sentRef.current) {
            sentRef.current = true
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
            showError(`不支持的格式: .${ext}，支持: ${validFormats.join(', ')}`)
            return
        }

        // 验证大小 (50MB)
        if (file.size > 50 * 1024 * 1024) {
            showError('文件过大，最大支持 50MB')
            return
        }

        setAudioFile(file)

        try {
            const res = await api.uploadFile(file)
            if (res.code === 200) {
                setAudioFileId(res.data.file_id)
                // 显示上传成功消息
                const fileMsg: Message = {
                    id: nextId(),
                    type: 'user',
                    userFile: res.data.filename,
                }
                setMessages(prev => [...prev, fileMsg])
            } else {
                showError(res.message || '文件上传失败')
            }
        } catch {
            showError(t('chat.networkError'))
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

    return (
        <div className="flex h-screen bg-white text-gray-800 font-sans">
            {/* ========== 左侧边栏 ========== */}
            <aside className="w-64 border-r border-[#e0f2fe] p-4 flex flex-col bg-[#f0f9ff]">
                {/* Logo 区域 */}
                <div className="w-full mb-6">
                    <div className="flex flex-row-reverse items-center justify-end gap-3">
                        <div className="relative w-[132px] h-[38px]">
                            <div className="absolute left-0 -top-[1px]">
                                <span className="text-lg font-semibold leading-tight text-[#0c4a6e] font-['Inter']">
                                  {t('sidebar.ringTurn')}
                                </span>
                            </div>
                            <div className="absolute left-0 top-[22.5px]">
                                <span className="text-[10px] font-semibold uppercase tracking-[1px] text-[#41565f]/70 font-['Inter']">
                                  {t('sidebar.aiMusic')}
                                </span>
                            </div>
                        </div>
                        <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center flex-shrink-0">
                            <svg width="12" height="18" viewBox="0 0 12 18" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M4 18C2.8999 18 1.9585 17.6083 1.17505 16.825C0.391602 16.0417 0 15.1 0 14C0 12.9 0.391602 11.9583 1.17505 11.175C1.9585 10.3917 2.8999 10 4 10C4.3833 10 4.73755 10.0458 5.0625 10.1375C5.38745 10.2292 5.69995 10.3667 6 10.55V0H12V4H8V14C8 15.1 7.6084 16.0417 6.82495 16.825C6.0415 17.6083 5.1001 18 4 18Z" fill="#458ecb"/>
                            </svg>
                        </div>
                    </div>
                </div>

                {/* 新建 Adaptation 按钮 */}
                <button className="w-[227px] self-stretch mb-6 px-4 py-3 bg-[#00639d] text-[#f7f9ff] rounded-xl hover:bg-[#005288] transition flex flex-row-reverse items-center justify-center gap-2">
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M6 7H0V5H6V0H8V5H14V7H8V14H6V7Z" fill="#f7f9ff"/>
                    </svg>
                    {t('sidebar.newAdaptation')}
                </button>

                {/* 静态主菜单 */}
                <div className="flex-1">
                    <h2 className="text-xs uppercase tracking-wider text-gray-500 mb-3">
                        {t('sidebar.mainMenu')}
                    </h2>
                    <ul className="space-y-1">
                        <li className="px-4 py-2.5 rounded-lg bg-white text-[#0369a1] cursor-pointer flex items-center gap-3 shadow-[0px_1px_2px_0px_#0000000D]">
                            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M9 18C6.69995 18 4.6958 17.2375 2.98755 15.7125C1.2793 14.1875 0.300049 12.2833 0.0500488 10H2.1001C2.3335 11.7333 3.104 13.1667 4.4126 14.3C5.7207 15.4333 7.25 16 9 16C10.95 16 12.6042 15.3208 13.9624 13.9625C15.3208 12.6042 16 10.95 16 9C16 7.05 15.3208 5.39587 13.9624 4.03748C12.6042 2.6792 10.95 2 9 2C7.8501 2 6.7749 2.26672 5.7749 2.80005C4.7749 3.33337 3.93335 4.06665 3.25 5H6V7H0V1H2V3.34998C2.8501 2.28333 3.88745 1.45837 5.11255 0.875C6.3374 0.291626 7.6333 0 9 0C10.25 0 11.4209 0.237549 12.5125 0.712524C13.6042 1.1875 14.5542 1.82922 15.3625 2.63745C16.1709 3.4458 16.8125 4.39587 17.2876 5.48755C17.7625 6.57922 18 7.75 18 9C18 10.25 17.7625 11.4208 17.2876 12.5125C16.8125 13.6042 16.1709 14.5542 15.3625 15.3625C14.5542 16.1708 13.6042 16.8125 12.5125 17.2875C11.4209 17.7625 10.25 18 9 18ZM11.8 13.2L8 9.40002V4H10V8.59998L13.2 11.8L11.8 13.2Z" fill="#0369a1"/>
                            </svg>
                            <span className="text-base font-normal">{t('sidebar.recentTracks')}</span>
                        </li>

                        <li className="px-3 py-2 rounded-lg hover:bg-gray-100 text-gray-700 cursor-pointer flex items-center gap-2">
                            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M10.5 13C11.2 13 11.7917 12.7583 12.2749 12.275C12.7583 11.7917 13 11.2 13 10.5V5H16V3H12V8.5C11.7832 8.33337 11.55 8.20837 11.3 8.125C11.05 8.04163 10.7832 8 10.5 8C9.80005 8 9.2085 8.2417 8.7251 8.72498C8.2417 9.20837 8 9.80005 8 10.5C8 11.2 8.2417 11.7917 8.7251 12.275C9.2085 12.7583 9.80005 13 10.5 13ZM6 16C5.44995 16 4.979 15.8042 4.5874 15.4125C4.1958 15.0208 4 14.55 4 14V2C4 1.44995 4.1958 0.979126 4.5874 0.587524C4.979 0.195801 5.44995 0 6 0H18C18.55 0 19.0208 0.195801 19.4126 0.587524C19.8042 0.979126 20 1.44995 20 2V14C20 14.55 19.8042 15.0208 19.4126 15.4125C19.0208 15.8042 18.55 16 18 16H6ZM6 14H18V14V14V2H18V2V2H6V2V2V2V14V14V14V14ZM2 20C1.44995 20 0.979004 19.8042 0.587402 19.4125C0.195801 19.0208 0 18.55 0 18V4H2V18V18V18H16V20H2ZM6 2V2V2V2V14V14V14V14V14V14V2V2V2V2Z" fill="#475569"/>
                            </svg>
                            {t('sidebar.library')}
                        </li>

                        <li className="px-3 py-2 rounded-lg hover:bg-gray-100 text-gray-700 cursor-pointer flex items-center gap-2">
                            <svg width="16" height="20" viewBox="0 0 16 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M0.800049 5C0.550049 4.71667 0.354004 4.40833 0.212402 4.07495C0.0708008 3.7417 0 3.3833 0 3C0 2.16663 0.291504 1.45837 0.875 0.875C1.4585 0.291626 2.1665 0 3 0C3.8335 0 4.5415 0.291626 5.125 0.875C5.7085 1.45837 6 2.16663 6 3C6 3.3833 5.9292 3.7417 5.7876 4.07495C5.646 4.40833 5.44995 4.71667 5.19995 5H0.800049ZM6 20C4.8999 20 3.9585 19.6083 3.17505 18.825C2.3916 18.0417 2 17.1 2 16H1L0 6H6L5 16H4C4 16.55 4.1958 17.0208 4.5874 17.4125C4.979 17.8042 5.44995 18 6 18C6.55005 18 7.021 17.8042 7.4126 17.4125C7.8042 17.0208 8 16.55 8 16V4C8 2.90002 8.3916 1.95837 9.17505 1.17505C9.9585 0.391724 10.8999 0 12 0C13.1001 0 14.0417 0.391724 14.825 1.17505C15.6084 1.95837 16 2.90002 16 4V20H14V4C14 3.44995 13.8042 2.97913 13.4126 2.58752C13.0208 2.1958 12.55 2 12 2C11.45 2 10.9792 2.1958 10.5874 2.58752C10.1958 2.97913 10 3.44995 10 4V16C10 17.1 9.6084 18.0417 8.82495 18.825C8.0415 19.6083 7.1001 20 6 20ZM2.80005 14H3.19995L3.80005 8H2.19995L2.80005 14ZM3.19995 8H2.80005L2.19995 8H3.80005L3.19995 8Z" fill="#475569"/>
                            </svg>
                            {t('sidebar.studioSessions')}
                        </li>

                        <li className="px-3 py-2 rounded-lg hover:bg-gray-100 text-gray-700 cursor-pointer flex items-center gap-2">
                            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M3 20C2.44995 20 1.979 19.8042 1.5874 19.4125C1.1958 19.0208 1 18.55 1 18V6.72498C0.699951 6.54163 0.458496 6.3042 0.274902 6.01245C0.0917969 5.72083 0 5.3833 0 5V2C0 1.44995 0.195801 0.979126 0.587402 0.587524C0.979004 0.195801 1.44995 0 2 0H18C18.55 0 19.0208 0.195801 19.4126 0.587524C19.8042 0.979126 20 1.44995 20 2V5C20 5.3833 19.9082 5.72083 19.7251 6.01245C19.5417 6.3042 19.3 6.54163 19 6.72498V18C19 18.55 18.8042 19.0208 18.4126 19.4125C18.0208 19.8042 17.55 20 17 20H3ZM3 7V18V18V18H17V18V18V18V7H3ZM2 5H18V5V5V2V2V2H2V2V2V2V5V5V5V5ZM7 12H13V10H7V12Z" fill="#475569"/>
                            </svg>
                            {t('sidebar.archive')}
                        </li>
                    </ul>
                </div>

                {/*/!* 主菜单 *!/*/}
                {/*<div className="flex-1">*/}
                {/*    <h2 className="text-xs uppercase tracking-wider text-gray-500 mb-3">*/}
                {/*        {t('sidebar.recentTracks')}*/}
                {/*    </h2>*/}
                {/*    <ul className="space-y-1">*/}
                {/*        {recentTasks.map((task) => (*/}
                {/*            <li*/}
                {/*                key={task.task_id}*/}
                {/*                onClick={() => setCurrentTaskId(task.task_id)}*/}
                {/*                className={`px-3 py-2 rounded-lg cursor-pointer flex items-center gap-2 transition ${*/}
                {/*                    currentTaskId === task.task_id*/}
                {/*                        ? 'bg-white text-[#0369a1] shadow-[0px_1px_2px_0px_#0000000D]'*/}
                {/*                        : 'hover:bg-gray-100 text-gray-700'*/}
                {/*                }`}*/}
                {/*            >*/}
                {/*                <svg width="18" height="18" viewBox="0 0 18 18" fill="none" className="flex-shrink-0">*/}
                {/*                    <path d="M9 18C6.69995 18 4.6958 17.2375 2.98755 15.7125C1.2793 14.1875 0.300049 12.2833 0.0500488 10H2.1001C2.3335 11.7333 3.104 13.1667 4.4126 14.3C5.7207 15.4333 7.25 16 9 16C10.95 16 12.6042 15.3208 13.9624 13.9625C15.3208 12.6042 16 10.95 16 9C16 7.05 15.3208 5.39587 13.9624 4.03748C12.6042 2.6792 10.95 2 9 2C7.8501 2 6.7749 2.26672 5.7749 2.80005C4.7749 3.33337 3.93335 4.06665 3.25 5H6V7H0V1H2V3.34998C2.8501 2.28333 3.88745 1.45837 5.11255 0.875C6.3374 0.291626 7.6333 0 9 0C10.25 0 11.4209 0.237549 12.5125 0.712524C13.6042 1.1875 14.5542 1.82922 15.3625 2.63745C16.1709 3.4458 16.8125 4.39587 17.2876 5.48755C17.7625 6.57922 18 7.75 18 9C18 10.25 17.7625 11.4208 17.2876 12.5125C16.8125 13.6042 16.1709 14.5542 15.3625 15.3625C14.5542 16.1708 13.6042 16.8125 12.5125 17.2875C11.4209 17.7625 10.25 18 9 18ZM11.8 13.2L8 9.40002V4H10V8.59998L13.2 11.8L11.8 13.2Z" fill={currentTaskId === task.task_id ? '#0369a1' : '#475569'}/>*/}
                {/*                </svg>*/}
                {/*                <div className="flex-1 min-w-0">*/}
                {/*                    <p className={`text-sm truncate ${currentTaskId === task.task_id ? 'text-[#0369a1]' : 'text-gray-700'}`}>*/}
                {/*                        {task.user_request.length > 12*/}
                {/*                            ? task.user_request.slice(0, 12) + '...'*/}
                {/*                            : task.user_request}*/}
                {/*                    </p>*/}
                {/*                    <p className="text-xs text-gray-400 mt-0.5">{task.created_at}</p>*/}
                {/*                </div>*/}
                {/*                /!* 状态标签 *!/*/}
                {/*                {task.status === 'completed' && (*/}
                {/*                    <span className="text-xs text-green-500 bg-green-50 px-1.5 py-0.5 rounded">完成</span>*/}
                {/*                )}*/}
                {/*                {task.status === 'failed' && (*/}
                {/*                    <span className="text-xs text-red-500 bg-red-50 px-1.5 py-0.5 rounded">失败</span>*/}
                {/*                )}*/}
                {/*                {task.status === 'executing' && (*/}
                {/*                    <span className="text-xs text-blue-500 bg-blue-50 px-1.5 py-0.5 rounded">进行中</span>*/}
                {/*                )}*/}
                {/*            </li>*/}
                {/*        ))}*/}
                {/*    </ul>*/}
                {/*</div>*/}

                {/* 底部设置 */}
                <div className="pt-4 border-t border-gray-200 space-y-2">
                    <div className="px-3 py-2 text-gray-500 hover:text-blue-600 cursor-pointer flex items-center gap-2">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.003-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
                            <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                        </svg>
                        {t('sidebar.settings')}
                    </div>
                    <div className="px-3 py-2 text-gray-500 hover:text-blue-600 cursor-pointer flex items-center gap-2">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z" />
                        </svg>
                        {t('sidebar.support')}
                    </div>
                </div>
            </aside>

            {/* ========== 中间主内容区 ========== */}
            <main className="flex-1 flex flex-col bg-white">
                {/* 顶部导航栏 */}
                <header className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
                    <div className="flex items-center gap-6">
                        <h2 className="text-xl font-semibold text-gray-800">{t('header.chatFlow')}</h2>
                        <button className="text-sm font-semibold text-[#0284c7] hover:text-[#00639d] transition">
                            {t('header.newChat')}
                        </button>
                    </div>
                    <div className="flex items-center gap-4">
                        {/* 语言设置 */}
                        <div className="relative">
                            <button
                                onClick={() => setShowLang(!showLang)}
                                className="text-sm font-medium text-[#64748b] hover:text-[#0284c7] transition"
                            >
                                {t('header.language')}
                            </button>
                            {showLang && (
                                <div className="absolute right-0 top-8 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-50 min-w-[100px]">
                                    <button
                                        onClick={() => { i18n.changeLanguage('en'); setShowLang(false) }}
                                        className={`block w-full text-left px-4 py-2 text-sm hover:bg-gray-50 ${i18n.language === 'en' ? 'text-[#0284c7] font-medium' : 'text-gray-700'}`}
                                    >
                                        English
                                    </button>
                                    <button
                                        onClick={() => { i18n.changeLanguage('zh'); setShowLang(false) }}
                                        className={`block w-full text-left px-4 py-2 text-sm hover:bg-gray-50 ${i18n.language === 'zh' ? 'text-[#0284c7] font-medium' : 'text-gray-700'}`}
                                    >
                                        中文
                                    </button>
                                </div>
                            )}
                        </div>
                        <div className="w-8 h-8 bg-gray-100 rounded-full flex items-center justify-center">
                            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M3.8501 15.1001C4.7002 14.45 5.6499 13.9375 6.7002 13.5625C7.75 13.1875 8.8501 13 10 13C11.1499 13 12.25 13.1875 13.2998 13.5625C14.3501 13.9375 15.2998 14.45 16.1499 15.1001C16.7334 14.4167 17.1875 13.6418 17.5127 12.7751C17.8374 11.9084 18 10.9834 18 10C18 7.78345 17.2207 5.896 15.6626 4.33765C14.1045 2.7793 12.2168 2 10 2C7.7832 2 5.896 2.7793 4.3374 4.33765C2.7793 5.896 2 7.78345 2 10C2 10.9834 2.1626 11.9084 2.4873 12.7751C2.8125 13.6418 3.2666 14.4167 3.8501 15.1001ZM10 11C9.0166 11 8.1875 10.6626 7.5127 9.98755C6.8374 9.3125 6.5 8.4834 6.5 7.5C6.5 6.51685 6.8374 5.6875 7.5127 5.01245C8.1875 4.33765 9.0166 4 10 4C10.9834 4 11.8125 4.33765 12.4873 5.01245C13.1626 5.6875 13.5 6.51685 13.5 7.5C13.5 8.4834 13.1626 9.3125 12.4873 9.98755C11.8125 10.6626 10.9834 11 10 11ZM10 20C8.6167 20 7.3164 19.7375 6.1001 19.2126C4.8833 18.6875 3.8252 17.9751 2.9248 17.075C2.0249 16.175 1.3125 15.1167 0.7876 13.9001C0.2627 12.6833 0 11.3833 0 10C0 8.6167 0.2627 7.31665 0.7876 6.1001C1.3125 4.8833 2.0249 3.82495 2.9248 2.92505C3.8252 2.02515 4.8833 1.3125 6.1001 0.787598C7.3164 0.262451 8.6167 0 10 0C11.3833 0 12.6836 0.262451 13.8999 0.787598C15.1167 1.3125 16.1748 2.02515 17.0752 2.92505C17.9751 3.82495 18.6875 4.8833 19.2124 6.1001C19.7373 7.31665 20 8.6167 20 10C20 11.3833 19.7373 12.6833 19.2124 13.9001C18.6875 15.1167 17.9751 16.175 17.0752 17.075C16.1748 17.9751 15.1167 18.6875 13.8999 19.2126C12.6836 19.7375 11.3833 20 10 20ZM10 18C10.8833 18 11.7168 17.8708 12.5 17.6125C13.2832 17.3542 14 16.9834 14.6499 16.5C14 16.0168 13.2832 15.6458 12.5 15.3875C11.7168 15.1292 10.8833 15 10 15C9.1167 15 8.2832 15.1292 7.5 15.3875C6.7168 15.6458 6 16.0168 5.3501 16.5C6 16.9834 6.7168 17.3542 7.5 17.6125C8.2832 17.8708 9.1167 18 10 18ZM10 9C10.4336 9 10.792 8.8584 11.0752 8.57495C11.3584 8.29175 11.5 7.93335 11.5 7.5C11.5 7.06665 11.3584 6.7085 11.0752 6.42505C10.792 6.14185 10.4336 6 10 6C9.5664 6 9.2085 6.14185 8.9248 6.42505C8.6416 6.7085 8.5 7.06665 8.5 7.5C8.5 7.93335 8.6416 8.29175 8.9248 8.57495C9.2085 8.8584 9.5664 9 10 9Z" fill="#475569"/>
                            </svg>
                        </div>
                    </div>
                </header>

                {/* 聊天内容区域 - 可滚动 */}
                <div className="flex-1 overflow-y-auto px-8 py-6">
                    <div className="max-w-[768px] mx-auto space-y-6">
                        {/* 欢迎区域 */}
                        <div className="w-[600px] py-5 flex flex-col gap-y-2 relative overflow-visible">
                            <div className="absolute -left-[18px] top-[15px] opacity-10 pointer-events-none">
                                <svg width="60" height="90" viewBox="0 0 60 90" fill="none">
                                    <path d="M20 90C14.5 90 9.7915 88.0417 5.875 84.125C1.9585 80.2083 0 75.5 0 70C0 64.5 1.9585 59.7917 5.875 55.875C9.7915 51.9583 14.5 50 20 50C21.9167 50 23.6875 50.2292 25.3125 50.6875C26.9375 51.1458 28.5 51.8333 30 52.75V0H60V20H40V70C40 75.5 38.0417 80.2083 34.125 84.125C30.2083 88.0417 25.5 90 20 90Z" fill="#00639d"/>
                                </svg>
                            </div>
                            <h3 className="text-3xl font-extrabold leading-tight font-['Manrope']">
                                <span className="text-[#2f3334]">{t('welcome.titleBefore')}</span>
                                <span className="text-[#00639d]">{t('welcome.titleHighlight')}</span>
                                {t('welcome.titleAfter') && <span className="text-[#2f3334]">{t('welcome.titleAfter')}</span>}
                            </h3>
                            <p className="text-base text-[#5b6061] leading-relaxed font-['Inter']">
                                {t('welcome.subtitle')}
                            </p>
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
                                            {/* 深度思考标题 */}
                                            {msg.deepThinking && (
                                                <p className="text-sm font-medium text-[#00639d]">{msg.deepThinking}</p>
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
                                                        <div>
                                                            <p className="font-medium text-gray-800">{msg.fileName}</p>
                                                            {msg.fileInfo && (
                                                                <p className="text-xs text-gray-500">{msg.fileInfo}</p>
                                                            )}
                                                        </div>
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
                    <div className="max-w-[768px] mx-auto px-2">
                        <div className="relative flex flex-row-reverse items-center gap-2 bg-white border border-[#e0f2fe] rounded-3xl px-2.5 py-2.5">
                            <button className="w-11 h-11 bg-[#00639d] rounded-2xl flex items-center justify-center flex-shrink-0 shadow-[0px_10px_15px_-3px_#00639d4D,0px_4px_6px_-4px_#00639d4D]">
                                <svg width="19" height="16" viewBox="0 0 19 16" fill="none">
                                    <path d="M0 16V0L19 8L0 16ZM2 13L13.85 8L2 3V6.5L8 8L2 9.5V13Z" fill="#f7f9ff"/>
                                </svg>
                            </button>
                            {/* 输入框 */}
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
    )
}

export default ChatFlow1