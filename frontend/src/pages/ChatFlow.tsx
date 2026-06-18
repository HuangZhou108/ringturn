// src/pages/ChatFlow.tsx
import { useTranslation } from 'react-i18next'
import { useState, useEffect, useRef, useCallback } from 'react'
import { useLocation, useParams, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { profileApi } from '../api/profile'
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
    const navigate = useNavigate()

    // 侧边栏状态
    const [sidebarOpen, setSidebarOpen] = useState(false)

    // 会话状态
    const [activeProfileId, setActiveProfileId] = useState<number | null>(null);
    const { conversationId: urlConversationId } = useParams<{ conversationId?: string }>();
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
    const [audioDuration, setAudioDuration] = useState<number | undefined>(undefined); // 上传的音频长度
    // 清除上传状态的函数
        const clearUploadState = useCallback(() => {
            setAudioFileId(null);
            setUploadedFileName(null);
            setUploadSuccess(null);
            setUploadError(null);
            setUploadProgress(0);
            setIsUploading(false);
            if (fileInputRef.current) {
                fileInputRef.current.value = '';
            }
        }, []);

    // 调试日志 - 每次渲染时打印完整状态
    console.log('[ChatFlow] === RENDER === audioFileId:', audioFileId, '| uploadSuccess:', uploadSuccess, '| isUploading:', isUploading, '| location.state:', JSON.stringify(location.state))
    const fileInputRef = useRef<HTMLInputElement>(null!)

    // UI状态
    const [toastMessage, setToastMessage] = useState<string | null>(null)
    const [isProcessing, setIsProcessing] = useState(false)
    const idCounter = useRef(Date.now())
    const fetchHistoryRef = useRef<(() => Promise<void>) | null>(null)
    const messagesEndRef = useRef<HTMLDivElement>(null)
    const [autoScroll, setAutoScroll] = useState(true); // 处理自动滚动
    const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
    const [refreshSidebar, setRefreshSidebar] = useState(0); // 刷新侧边栏
    // 使用 ref 保存路由状态，避免重新渲染时丢失
    const locationStateRef = useRef(location.state as any)
    // 标题编辑状态
    const [isEditingTitle, setIsEditingTitle] = useState(false);
    const [editingTitleValue, setEditingTitleValue] = useState('');

    // 反馈任务相关
    const [feedbackMode, setFeedbackMode] = useState(false);
    const [availableParentTasks, setAvailableParentTasks] = useState<{ task_id: string; user_request: string }[]>([]);
    const [selectedParentTaskId, setSelectedParentTaskId] = useState<string | null>(null);
    const [feedbackPanelOpen, setFeedbackPanelOpen] = useState(false);
    // 获取当前会话中已完成的任务列表（用于反馈选择）
    const loadCompletedTasks = useCallback(async () => {
        if (!currentConversationId) {
            setAvailableParentTasks([]);
            return;
        }
        // 从消息中提取 assistant 消息且包含 audio_url 的任务
        const tasks = messages
            .filter(m => m.type === 'ai' && m.taskId && m.fileName) // fileName 即 audio_url
            .map(m => ({ task_id: m.taskId!, user_request: m.content || '' }));
        setAvailableParentTasks(tasks);
    }, [messages, currentConversationId]);

    const handleToggleFeedback = useCallback((newMode: boolean) => {
        if (newMode) {
            clearUploadState();          // 开启反馈时清除已上传音频
            loadCompletedTasks();        // 刷新任务列表
            setSelectedParentTaskId(null);
        }
        setFeedbackMode(newMode);
    }, [clearUploadState, loadCompletedTasks]);

    // 获取当前Profile
    useEffect(() => {
        const loadProfile = async () => {
            const res = await profileApi.getActive();
            if (res.code === 200) setActiveProfileId(res.data.profile_id);
        };
        loadProfile();
    }, []);

    const handleScroll = () => {
        const container = messagesEndRef.current;
        if (!container) return;
        const { scrollTop, scrollHeight, clientHeight } = container;
        const isAtBottom = Math.abs(scrollHeight - scrollTop - clientHeight) < 10;
        setAutoScroll(isAtBottom);
    };

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
        // 重置反馈模式
        setFeedbackMode(false)
        setSelectedParentTaskId(null)
        setFeedbackPanelOpen(false);
        try {
            const res = await conversationApi.get(conversationId)
            if (res.code === 200) {
                setCurrentConversation(res.data)
                setIsEditingTitle(false);

                // 将会话消息转换为UI消息
                const uiMessages: Message[] = res.data.messages.map((msg) => ({
                    id: `msg-${msg.id}`,
                    type: msg.role === 'user' ? 'user' : 'ai',
                    content: msg.content,
                    taskId: msg.task_id || undefined,
                    userFile: msg.file_name || (msg.role === 'user' ? uploadedFileName : undefined),
                    thinkingProcess: msg.thinking_process || [],
                    fileName: msg.audio_url,                     // 音频 URL 作为文件名显示
                    fileInfo: msg.audio_duration ? `${msg.audio_duration}s` : undefined,
                }))

                // 如果没有消息，显示欢迎消息
                if (uiMessages.length === 0) {
                    setMessages([])
                } else {
                    setMessages(uiMessages)
                }

                // 直接根据 uiMessages 计算已完成任务列表，避免 state 异步问题
                const tasks = uiMessages
                    .filter(m => m.type === 'ai' && m.taskId && m.fileName)
                    .map(m => ({ task_id: m.taskId!, user_request: m.content || '' }));
                setAvailableParentTasks(tasks);
            }
        } catch (err) {
            console.error('Failed to load conversation:', err)
            showToast('加载会话失败')
        }
    }, [uploadedFileName])

    // 双击标题进入编辑模式
    const handleTitleDoubleClick = () => {
        if (currentConversation) {
            setIsEditingTitle(true);
            setEditingTitleValue(currentConversation.title || '未命名会话');
        }
    };

    // 保存标题
    const handleTitleSave = async () => {
        if (!currentConversation) return;
        const newTitle = editingTitleValue.trim() || '未命名会话';
        try {
            const res = await conversationApi.updateTitle(currentConversation.conversation_id, newTitle);
            if (res.code === 200) {
                // 更新本地会话数据
                setCurrentConversation(prev => prev ? { ...prev, title: newTitle } : prev);
                // 刷新侧边栏会话列表
                setRefreshSidebar(prev => prev + 1);
                setIsEditingTitle(false);
            } else {
                showToast(res.message || '更新标题失败');
            }
        } catch (err) {
            console.error('更新标题失败:', err);
            showToast('更新标题失败');
        }
    };

    // 取消编辑
    const handleTitleCancel = () => {
        setIsEditingTitle(false);
    };

    // 检测到宽度过小时自动关闭侧边栏
    useEffect(() => {
        const handleResize = () => {
            if (window.innerWidth < 1024) {
                setSidebarOpen(false);
            }
        };
        window.addEventListener('resize', handleResize);
        handleResize(); // 初始化时检查一次
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    // 新建空会话
    const handleNewConversation = useCallback(() => {
        // 清除 URL 中的会话 ID，回到干净的新建会话页面
        navigate('/chat', { replace: true })

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
        if (fileInputRef.current) {
            fileInputRef.current.value = ''
        }
        setRefreshSidebar(prev => prev + 1); // 刷新侧边栏
        // 重置反馈模式
        setFeedbackMode(false)
        setSelectedParentTaskId(null)
        setFeedbackPanelOpen(false);
        // 显式清空已完成任务列表，确保重做按钮消失
        setAvailableParentTasks([])
    }, [])

    // 加载历史任务（保留兼容性）
    useEffect(() => {
        const fetchHistory = async () => {
            if (!activeProfileId) return;
            try {
                const res = await api.getProfileTasks(activeProfileId, { page: 1, page_size: 10 });
                if (res.code === 200) setRecentTasks(res.data.tasks);
            } catch { /* ignore */ }
        };
        fetchHistoryRef.current = fetchHistory
    }, [])

    // 页面自动滚动
    useEffect(() => {
        const container = messagesEndRef.current;
        if (!container) return;
        container.addEventListener('scroll', handleScroll);
        return () => container.removeEventListener('scroll', handleScroll);
    }, []);
    useEffect(() => {
        if (autoScroll && messagesEndRef.current) {
            messagesEndRef.current.scrollTop = messagesEndRef.current.scrollHeight;
        }
    }, [messages, autoScroll]);

    // 处理WebSocket状态更新
    useEffect(() => {
        if (taskStatus && currentTaskId) {
            // 如果 currentTaskId 已经被清除（取消），不再处理
            if (!currentTaskId) return;
            // 根据任务状态更新 processing 状态
            if (['pending', 'planning', 'executing'].includes(taskStatus.status)) {
                setIsProcessing(true);
            } else {
                setIsProcessing(false);
            }
            // 更新消息中的思考过程
            // 仅更新思考过程，不覆盖正文
            setMessages((prev) => {
                const lastAiMsgIndex = prev.findLastIndex(m => m.type === 'ai')
                if (lastAiMsgIndex === -1) return prev

                return prev.map((msg, index) => {
                    if (index === lastAiMsgIndex) {
                        return {
                            ...msg,
                            // content: taskStatus.message || taskStatus.current_subtask || msg.content,
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
                // showError(t('chat.failed'))
                // 修改最后一条 AI 消息的内容为错误文案
                setMessages((prev) => {
                    const lastAiIdx = prev.findLastIndex(m => m.type === 'ai')
                    if (lastAiIdx === -1) return prev
                    return prev.map((msg, idx) =>
                        idx === lastAiIdx ? { ...msg, content: t('chat.failed') } : msg
                    )
                })
            }
        }
    }, [taskStatus, currentTaskId, t])

    // 当 WebSocket 连接成功时，停止轮询（降级方案自动停止）
    useEffect(() => {
        if (isConnected && currentTaskId && pollingIntervalRef.current) {
            console.log('[ChatFlow] WebSocket connected, stopping polling for task', currentTaskId)
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
        }
    }, [isConnected, currentTaskId])

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
                // 获取任务的 user_request（用于重做下拉显示）
                let userRequest = '';
                try {
                    const taskRes = await api.getTask(taskId);
                    if (taskRes.code === 200) {
                        userRequest = taskRes.data.user_request;
                    }
                } catch (e) {
                    console.warn('Failed to get task user_request', e);
                }

                // 直接添加到 availableParentTasks，不依赖 messages 的异步更新
                // 延迟到下一帧更新，避免布局未完成时按钮位置偏移
                requestAnimationFrame(() => {
                    setAvailableParentTasks(prev => {
                        if (prev.some(t => t.task_id === taskId)) return prev; // 避免重复
                        return [...prev, { task_id: taskId, user_request: userRequest || '已完成的改编任务' }];
                    });
                });
            }
        } catch (err) {
            console.error('Failed to get task result:', err)
        } finally {
            setIsProcessing(false)
            fetchHistoryRef.current?.()
        }
    }

    const fetchTaskInfo = async (taskId: string) => {
        try {
            const res = await api.getTask(taskId)
            if (res.code === 200 && res.data) {
                const task = res.data
                // 设置会话 ID
                if (task.conversation_id) {
                    setCurrentConversationId(task.conversation_id)
                    // 加载会话消息，补全对话历史
                    loadConversation(task.conversation_id)
                }
                // 设置用户消息（从任务的 user_request）
                setMessages([])
                setCurrentTaskId(taskId)

                // 设置参数
                // if (task.ringtone_params) {
                //     if (task.ringtone_params.instrument) setInstrument(task.ringtone_params.instrument)
                //     if (task.ringtone_params.tempo) setTempo(String(task.ringtone_params.tempo))
                //     if (task.ringtone_params.duration) setDuration(String(task.ringtone_params.duration))
                //     if (task.ringtone_params.filename) setFilename(task.ringtone_params.filename)
                // }

                // 添加用户消息（从 task.user_request）
                const userMsg: Message = {
                    id: nextId(),
                    type: 'user',
                    content: task.user_request,
                    userFile: task.source_value || undefined, // 或者从文件服务获取文件名
                }
                setMessages([userMsg])

                // 添加处理中消息（如果任务未完成）
                if (task.status !== 'completed' && task.status !== 'failed') {
                    // 恢复任务且任务未完成时，设为处理中状态
                    setIsProcessing(true);
                    const processingMsg: Message = {
                        id: nextId(),
                        type: 'ai',
                        taskId: taskId,
                        deepThinking: t('chat.deepThinking'),
                        content: t('chat.taskCreated'),
                        thinkingProcess: [],
                    }
                    setMessages((prev) => [...prev, processingMsg])
                    pollTaskStatus(taskId, processingMsg.id)
                } else if (task.status === 'completed') {
                    // 已完成任务，显示结果
                    const completedMsg: Message = {
                        id: nextId(),
                        type: 'ai',
                        content: t('chat.completed'),
                        fileName: task.final_audio_url,
                        fileInfo: task.audio_duration ? `${task.audio_duration}s` : undefined,
                    }
                    setMessages((prev) => [...prev, completedMsg])
                } else if (task.status === 'failed') {
                    const failedMsg: Message = {
                        id: nextId(),
                        type: 'ai',
                        content: t('chat.failed'),
                    }
                    setMessages((prev) => [...prev, failedMsg])
                }
            }
        } catch (err) {
            console.error('Failed to fetch task info:', err)
            showToast('加载任务失败')
        }
    }

    // 发送消息
    const handleSend = async () => {
        if (!inputValue.trim()) return

        // 反馈模式
        if (feedbackMode) {
            if (!selectedParentTaskId) {
                showToast('请选择要反馈的任务');
                return;
            }
            // 收集当前参数
            const params: Record<string, any> = {};
            if (instrument.trim()) params.instrument = instrument;
            if (tempo.trim()) params.tempo = parseInt(tempo, 10);
            if (duration.trim()) params.duration = parseInt(duration, 10);
            if (filename && filename.trim() !== '') params.filename = filename;
            try {
                const res = await api.createFeedback(selectedParentTaskId, inputValue.trim(), params);
                if (res.code === 200) {
                    // 清空输入，退出反馈模式
                    setInputValue('');
                    setFeedbackMode(false);
                    setSelectedParentTaskId(null);
                    setFeedbackPanelOpen(false);

                    // 获取新创建的子任务 ID
                    const newTaskId = res.data.task_id;
                    setCurrentTaskId(newTaskId);
                    setIsProcessing(true);

                    // 添加 AI 占位消息，用于显示思考过程
                    const processingMsg: Message = {
                        id: nextId(),
                        type: 'ai',
                        taskId: newTaskId,
                        deepThinking: t('chat.deepThinking'),
                        content: '根据您的反馈正在优化...',
                        thinkingProcess: [],
                    };
                    setMessages((prev) => [...prev, processingMsg]);

                    // 如果 WebSocket 未连接，启动轮询
                    if (!isConnected) {
                        pollTaskStatus(newTaskId, processingMsg.id);
                    }
                    // 刷新侧边栏和会话列表
                    setRefreshSidebar(prev => prev + 1);
                    if (currentConversationId) loadConversation(currentConversationId);
                } else {
                    showToast(res.message || '反馈提交失败');
                }
            } catch (err) {
                console.error(err);
                showToast('网络错误，反馈失败');
            }
            return;
        }

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
        // 保存上传文件的原始文件名
        if (uploadedFileName) params.original_filename = uploadedFileName;

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
                setIsProcessing(true);
                const newConvId = res.data.conversation_id;
                if (!currentConversationId) {
                    // 新建会话，跳转到新会话 URL
                    navigate(`/chat/c/${newConvId}`, { replace: true });
                    setCurrentConversationId(newConvId);
                } else {
                    // 已有会话，只更新状态，不改变 URL
                    setCurrentTaskId(res.data.task_id);
                }

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
                } else {
                    // WebSocket 已连接，确保清除可能残留的轮询
                    if (pollingIntervalRef.current) {
                        clearInterval(pollingIntervalRef.current)
                        pollingIntervalRef.current = null
                    }
                }
                setRefreshSidebar(prev => prev + 1);
            } else {
                showError(res.message || t('chat.createFailed'))
            }
        } catch {
            setMessages((prev) => {
                const lastAi = prev.findLastIndex(m => m.type === 'ai')
                if (lastAi !== -1) {
                    return prev.map((msg, idx) =>
                        idx === lastAi ? { ...msg, content: t('chat.networkError') } : msg
                    )
                }
                // 不存在 AI 消息时才新增
                return [...prev, { id: nextId(), type: 'ai', content: t('chat.networkError') }]
            })
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
    // 只从 URL/state 解析 ID
    useEffect(() => {
        const conversationId = urlConversationId || location.state?.conversationId;
        const taskId = location.state?.taskId;
        if (conversationId) {
            setCurrentConversationId(conversationId);
            // 清除可能残留的任务 ID
            setCurrentTaskId(null);
        } else if (taskId) {
            // 如果只有 taskId（理论上不应发生），可以恢复
            setCurrentTaskId(taskId);
            setCurrentConversationId(null);
        } else {
            // 无任何 ID，显示欢迎页
            handleNewConversation();
        }
    }, [urlConversationId, location.state]);

// 单独 effect 加载数据
    useEffect(() => {
        if (currentConversationId) {
            loadConversation(currentConversationId);
            // 可选：调用 active_task 接口恢复任务
            fetchActiveTask(currentConversationId).then(taskId => {
                if (taskId) setCurrentTaskId(taskId);
            });
        } else if (currentTaskId && !currentConversationId) {
            fetchTaskInfo(currentTaskId);
        }
    }, [currentConversationId, currentTaskId]);

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
                if (res.data.duration) {
                    setAudioDuration(res.data.duration);
                }
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

        // 立即清除状态，防止后续更新
        setIsProcessing(false)
        const cancelledTaskId = currentTaskId
        setCurrentTaskId(null)

        if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
        }

        try {
            await api.cancelTask(cancelledTaskId)
        } catch (err) {
            console.error('Cancel task error:', err)
        }
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

    const fetchActiveTask = async (conversationId: string) => {
        try {
            const res = await fetch(`/api/v1/conversations/${conversationId}/active_task`);
            const data = await res.json();
            if (data.code === 200 && data.data?.task_id) {
                setCurrentTaskId(data.data.task_id);
                // 如果需要，可以恢复轮询/WebSocket
                restoreTask(data.data.task_id);
            }
        } catch (err) {
            console.error('Failed to fetch active task', err);
        }
    };

    // 处理Profile切换
    const handleProfileChanged = useCallback(async () => {
        try {
            // 1. 重新获取当前活跃的 Profile
            const res = await profileApi.getActive();
            if (res.code === 200 && res.data) {
                setActiveProfileId(res.data.profile_id);
            }

            // 2. 清空当前会话状态，回到欢迎页
            setCurrentConversationId(null);
            setCurrentConversation(null);
            setMessages([]);
            setCurrentTaskId(null);
            setInputValue('');
            setAudioFileId(null);
            setUploadedFileName(null);
            setUploadSuccess(null);
            setUploadError(null);
            setInstrument('');
            setDuration('');
            setTempo('');
            setFilename('Untitled_Track');
            if (fileInputRef.current) {
                fileInputRef.current.value = '';
            }

            // 3. 清除 URL 中的会话 ID，避免重新加载旧会话
            navigate('/chat', { replace: true });

            // 4. 刷新侧边栏
            setRefreshSidebar(prev => prev + 1);
        } catch (err) {
            console.error('Failed to refresh after profile change:', err);
            showToast('切换档案失败，请刷新页面重试');
        }
    }, [navigate]);

    return (
        <div className="flex flex-col h-screen bg-white text-gray-800 font-sans page-enter">
            <TopBar
                onNewChat={() => handleNewConversation()}
                onProfileChanged={handleProfileChanged}
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
                    refreshTrigger={refreshSidebar}
                    profileId={activeProfileId}
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
                                    {isEditingTitle ? (
                                        <div className="flex items-center justify-center gap-2">
                                            <input
                                                type="text"
                                                value={editingTitleValue}
                                                onChange={(e) => setEditingTitleValue(e.target.value)}
                                                onKeyDown={(e) => {
                                                    if (e.key === 'Enter') handleTitleSave();
                                                    else if (e.key === 'Escape') handleTitleCancel();
                                                }}
                                                onBlur={handleTitleSave}
                                                className="text-lg font-medium text-gray-700 border-b-2 border-[#00639d] focus:outline-none px-2 py-1 text-center min-w-[200px]"
                                                autoFocus
                                            />
                                        </div>
                                    ) : (
                                        <h2
                                            className="text-lg font-medium text-gray-700 cursor-pointer hover:text-[#00639d] transition-colors"
                                            onDoubleClick={handleTitleDoubleClick}
                                            title="双击编辑标题"
                                        >
                                            {currentConversation.title || '未命名会话'}
                                        </h2>
                                    )}
                                    <div className="flex items-center justify-center gap-2 mt-1">
                                        {/* 状态标签等保持不变 */}
                                        <span className={`px-2 py-0.5 text-xs rounded ${
                                            currentConversation.status === 'active'
                                                ? 'bg-green-100 text-green-600'
                                                : 'bg-gray-100 text-gray-500'
                                        }`}>
                {currentConversation.status === 'active' ? '进行中' : '已完成'}
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

                            {/*/!* WebSocket连接状态指示器（已注释） *!/*/}
                            {/*{currentTaskId && isConnected && (*/}
                            {/*    <div className="fixed bottom-24 right-8 flex items-center gap-2 px-3 py-1.5 bg-green-100 text-green-700 text-xs rounded-full shadow">*/}
                            {/*        <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>*/}
                            {/*        WebSocket 已连接*/}
                            {/*    </div>*/}
                            {/*)}*/}
                        </div>
                    </div>

                    {/* 底部输入区域 */}
                    <div className="border-t border-gray-100 px-4 py-3">
                        <div className="flex items-center justify-center">
                            {/* ChatInputArea 占据父容器宽度 */}
                            <div className="flex-shrink-0 w-[768px]">
                            <ChatInputArea
                                isProcessing={isProcessing}
                                onCancel={handleCancel}
                                mode="chat"
                                inputValue={inputValue}
                                setInputValue={setInputValue}
                                handleSend={handleSend}
                                fileInputRef={fileInputRef}
                                handleFileSelect={handleFileSelect}
                                instrument={instrument}
                                setInstrument={setInstrument}
                                tempo={tempo}
                                setTempo={setTempo}
                                audioDuration={audioDuration}
                                duration={duration}
                                setDuration={setDuration}
                                filename={filename}
                                setFilename={setFilename}
                                isUploading={isUploading}
                                uploadProgress={uploadProgress}
                                uploadError={uploadError}
                                uploadSuccess={uploadSuccess}
                                feedbackMode={feedbackMode}
                                setFeedbackMode={handleToggleFeedback}
                                selectedParentTaskId={selectedParentTaskId}
                                setSelectedParentTaskId={setSelectedParentTaskId}
                                availableParentTasks={availableParentTasks}
                                loadCompletedTasks={loadCompletedTasks}
                            />
                            </div>

                            {/* 重做按钮（仅在存在已完成任务时显示） */}
                            {availableParentTasks.length > 0 && (
                                <div className="flex-shrink-0 ml-4">
                                    <div className="relative flex items-center gap-2">
                                        {/* 重做按钮 */}
                                        <button
                                            onClick={async () => {
                                                if (!feedbackMode) {
                                                    // 进入反馈模式，打开面板
                                                    await loadCompletedTasks();
                                                    setSelectedParentTaskId(null);
                                                    setFeedbackMode(true);
                                                    setFeedbackPanelOpen(true);
                                                    clearUploadState();
                                                } else {
                                                    // 已处于反馈模式，切换面板开关
                                                    setFeedbackPanelOpen(!feedbackPanelOpen);
                                                }
                                            }}
                                            title={
                                                selectedParentTaskId
                                                    ? availableParentTasks.find(t => t.task_id === selectedParentTaskId)?.user_request || '已选择任务'
                                                    : '重做'
                                            }
                                            className={`px-4 py-2 rounded-md border transition-all duration-200 font-medium text-sm whitespace-nowrap ${
                                                feedbackMode
                                                    ? 'bg-blue-100 border-blue-300 text-blue-800'
                                                    : 'bg-white border-gray-800 text-gray-800 hover:bg-gray-50'
                                            }`}
                                        >
                                            重做
                                        </button>

                                        {/* 取消按钮（仅在反馈模式显示） */}
                                        {feedbackMode && (
                                            <button
                                                onClick={() => {
                                                    setFeedbackMode(false);
                                                    setSelectedParentTaskId(null);
                                                    setFeedbackPanelOpen(false);
                                                }}
                                                className="px-3 py-2 text-sm text-gray-500 hover:text-red-600 transition"
                                            >
                                                取消
                                            </button>
                                        )}

                                        {/* 反馈模式浮动面板（仅当 feedbackMode 且面板打开时显示） */}
                                        {feedbackMode && feedbackPanelOpen && (
                                            <div className="absolute bottom-full right-0 mb-2 z-20 bg-white rounded-lg shadow-lg border border-gray-200 p-3 min-w-[240px]">
                                                <div className="flex items-center justify-between mb-2">
                                                    <span className="text-xs text-gray-400">选择要反馈的任务</span>
                                                </div>
                                                <select
                                                    value={selectedParentTaskId || ''}
                                                    onChange={(e) => {
                                                        setSelectedParentTaskId(e.target.value || null);
                                                        setFeedbackPanelOpen(false); // 选择后关闭面板
                                                    }}
                                                    className="w-full border border-gray-300 rounded-md px-3 py-1.5 text-sm bg-white focus:outline-none focus:ring-1 focus:ring-blue-400"
                                                >
                                                    <option value="">选择任务</option>
                                                    {availableParentTasks.map((task) => (
                                                        <option key={task.task_id} value={task.task_id}>
                                                            {task.user_request.length > 40
                                                                ? task.user_request.substring(0, 40) + '...'
                                                                : task.user_request}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
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
