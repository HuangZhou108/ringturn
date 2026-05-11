// src/pages/ChatFlow.tsx
import { useTranslation } from 'react-i18next';
import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { api } from '../api';
import type { TaskListItem } from '../types';
import TopBar from '../components/TopBar';
import Sidebar from '../components/SideBar';
import Toast from '../components/notifications/Toast';
import WelcomeMessage from '../components/chat/WelcomeMessage';
import MessageList from '../components/chat/MessageList';
import ChatInputArea from '../components/chat/ChatInputArea';

interface Message {
    id: string;
    type: 'ai' | 'user';
    content?: string;
    deepThinking?: string;
    fileName?: string;
    fileInfo?: string;
    userFile?: string;
    audioFileId?: string;
    taskId?: string;
    thinkingProcess?: { step: string; content: string; timestamp: string }[];
    showThinking?: boolean;
}

function ChatFlow() {
    const { t } = useTranslation();
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [instrument, setInstrument] = useState('');
    const [duration, setDuration] = useState('');
    const [tempo, setTempo] = useState('');
    const [filename, setFilename] = useState('Untitled_Track');
    const [inputValue, setInputValue] = useState('');
    const idCounter = useRef(Date.now());
    const fetchHistoryRef = useRef<(() => Promise<void>) | null>(null);
    const location = useLocation();
    const [audioFileId, setAudioFileId] = useState<string | null>(null);
    const [uploadError, setUploadError] = useState<string | null>(null);
    const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
    const [uploadProgress, setUploadProgress] = useState<number>(0);
    const [isUploading, setIsUploading] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [toastMessage, setToastMessage] = useState<string | null>(null);
    const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null); // 处理页面自动滚动
    const [isProcessing, setIsProcessing] = useState(false)
    const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null) // 保存轮询定时器

    // 处理侧边栏开关拖拽
    const [position, setPosition] = useState({ x: 24, y: 80 }); // left: 1.5rem=24px, top: 5rem=80px
    const [isDragging, setIsDragging] = useState(false);
    const dragRef = useRef<{ startX: number; startY: number; initialLeft: number; initialTop: number } | null>(null);
    const handleMouseDown = (e: React.MouseEvent) => {
        e.preventDefault();
        setIsDragging(true);
        dragRef.current = {
            startX: e.clientX,
            startY: e.clientY,
            initialLeft: position.x,
            initialTop: position.y,
        };
    };

    const handleMouseMove = (e: MouseEvent) => {
        if (!isDragging || !dragRef.current) return;
        const dx = e.clientX - dragRef.current.startX;
        const dy = e.clientY - dragRef.current.startY;
        setPosition({
            x: dragRef.current.initialLeft + dx,
            y: dragRef.current.initialTop + dy,
        });
    };

    const handleMouseUp = () => {
        setIsDragging(false);
        dragRef.current = null;
    };

    useEffect(() => {
        if (isDragging) {
            window.addEventListener('mousemove', handleMouseMove);
            window.addEventListener('mouseup', handleMouseUp);
        } else {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
        }
        return () => {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
        };
    }, [isDragging]);

    // 基础方法：
    const nextId = () => {
        idCounter.current += 1;
        return `${Date.now()}-${idCounter.current}`;
    };

    const [messages, setMessages] = useState<Message[]>([
        {
            id: '1',
            type: 'user',
            userFile: 'Midni...ft.mp3',
            content: t('chat.userMessage'),
        },
        {
            id: '2',
            type: 'ai',
            deepThinking: t('chat.deepThinking'),
            content: t('chat.aiResponse'),
            fileName: t('chat.fileName'),
            fileInfo: t('chat.fileInfo'),
        },
    ]);

    const [recentTasks, setRecentTasks] = useState<TaskListItem[]>([]);
    const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);

    const showError = (message: string) => {
        const errorMsg: Message = {
            id: nextId(),
            type: 'ai',
            content: message,
        };
        setMessages((prev) => [...prev, errorMsg]);
    };

    useEffect(() => {
        const fetchHistory = async () => {
            try {
                const res = await api.getUserTasks(1);
                if (res.code === 200 && res.data) {
                    setRecentTasks(res.data.tasks || []);
                }
            } catch {
                // 静默失败
            }
        };
        fetchHistoryRef.current = fetchHistory;
    }, []);

    // 页面自动滚动
    useEffect(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollTop = messagesEndRef.current.scrollHeight;
        }
    }, [messages]);

    const handleSend = async () => {
        if (!inputValue.trim()) return;
        // 检查是否已上传音频
        if (!audioFileId) {
            showToast(t('toast.uploadRequired'));
            return;
        }

        const params: Record<string, any> = {};
        if (instrument.trim()) params.instrument = instrument;
        if (tempo.trim()) params.tempo = parseInt(tempo, 10);
        if (duration.trim()) params.duration = parseInt(duration, 10);
        if (filename && filename.trim() !== '') params.filename = filename;

        const newUserMessage: Message = {
            id: nextId(),
            type: 'user',
            content: inputValue.trim(),
            userFile: uploadedFileName || undefined,
        };
        setMessages((prev) => [...prev, newUserMessage]);
        setInputValue('');

        try {
            const res = await api.createTask({
                user_request: inputValue.trim(),
                source_type: 'upload',
                source_value: audioFileId || undefined,
                params,
            });

            if (res.code === 200) {
                setIsProcessing(true);
                setCurrentTaskId(res.data.task_id);
                fetchHistoryRef.current?.();

                const processingMsg: Message = {
                    id: nextId(),
                    type: 'ai',
                    taskId: res.data.task_id,
                    deepThinking: t('chat.deepThinking'),
                    content: t('chat.taskCreated'),
                };
                setMessages((prev) => [...prev, processingMsg]);
                pollTaskStatus(res.data.task_id, processingMsg.id);
            } else {
                showError(res.message || t('chat.createFailed'));
            }
        } catch {
            showError(t('chat.networkError'));
        }
    };

    const pollTaskStatus = async (taskId: string, msgId: string) => {
        const poll = setInterval(async () => {
            try {
                const res = await api.getTaskStatus(taskId);
                if (res.code !== 200) return;

                const { status, current_subtask, message, thinking_process } = res.data;
                if (['pending', 'planning', 'executing'].includes(status)) {
                    setIsProcessing(true);
                } else {
                    setIsProcessing(false);
                }

                // 更新思考过程（与原逻辑完全一致，此处保留原样）
                setMessages((prev) => {
                    const msgIndex = prev.findIndex((m) => m.id === msgId);
                    if (msgIndex === -1) return prev;
                    const existingMsg = prev[msgIndex];
                    const existingSteps = existingMsg.thinkingProcess || [];
                    const newSteps = thinking_process || [];
                    const mergedSteps = [...existingSteps];
                    for (const step of newSteps) {
                        const exists = mergedSteps.some((s) => s.step === step.step && s.timestamp === step.timestamp);
                        if (!exists) mergedSteps.push(step);
                    }
                    return prev.map((msg) =>
                        msg.id === msgId
                            ? {
                                ...msg,
                                content: message || current_subtask || msg.content,
                                thinkingProcess: mergedSteps,
                            }
                            : msg
                    );
                });

                if (status === 'completed') {
                    clearInterval(poll);
                    const resultRes = await api.getTaskResult(taskId);
                    const finalThinking = resultRes?.data?.thinking_process || [];
                    setMessages((prev) => {
                        const msgIndex = prev.findIndex((m) => m.id === msgId);
                        if (msgIndex === -1) return prev;
                        const existingMsg = prev[msgIndex];
                        const existingSteps = existingMsg.thinkingProcess || [];
                        const mergedSteps = [...existingSteps];
                        for (const step of finalThinking) {
                            const exists = mergedSteps.some((s) => s.step === step.step && s.timestamp === step.timestamp);
                            if (!exists) mergedSteps.push(step);
                        }
                        const updates: Partial<Message> = {
                            content: t('chat.completed'),
                            fileName: resultRes?.data?.audio_url,
                            fileInfo: resultRes?.data?.duration ? `${resultRes.data.duration}s` : undefined,
                            thinkingProcess: mergedSteps,
                        };
                        return prev.map((msg) => (msg.id === msgId ? { ...msg, ...updates } : msg));
                    });
                    fetchHistoryRef.current?.();
                }

                if (status === 'failed') {
                    clearInterval(poll);
                    updateMessage(msgId, { content: t('chat.failed') });
                    fetchHistoryRef.current?.();
                }

                if (status === 'cancelled') {
                    clearInterval(poll);
                    pollingIntervalRef.current = null;
                    setCurrentTaskId(null);
                    setIsProcessing(false);
                    // 可选：更新消息提示“任务已取消”
                }
            } catch {
                // 忽略网络错误，继续轮询
            }
        }, 5000);
        pollingIntervalRef.current = poll;
    };

    const updateMessage = (msgId: string, updates: Partial<Message>) => {
        setMessages((prev) => prev.map((msg) => (msg.id === msgId ? { ...msg, ...updates } : msg)));
    };

    const handleAutoSend = async (text: string) => {
        const newUserMessage: Message = {
            id: nextId(),
            type: 'user',
            content: text,
            userFile: uploadedFileName || undefined,
        };
        setMessages((prev) => [...prev, newUserMessage]);

        try {
            const res = await api.createTask({
                user_request: text.trim(),
                source_type: 'upload',
                source_value: audioFileId || undefined,
                instrument,
                duration: parseInt(duration) || 30,
                tempo: parseInt(tempo) || 120,
                filename,
            });

            if (res.code === 200) {
                setIsProcessing(true);
                setCurrentTaskId(res.data.task_id);
                const processingMsg: Message = {
                    id: nextId(),
                    type: 'ai',
                    taskId: res.data.task_id,
                    deepThinking: t('chat.deepThinking'),
                    content: t('chat.taskCreated'),
                };
                setMessages((prev) => [...prev, processingMsg]);
                pollTaskStatus(res.data.task_id, processingMsg.id);
            } else {
                showError(res.message || t('chat.createFailed'));
            }
        } catch {
            showError(t('chat.networkError'));
        }
    };

    useEffect(() => {
        const newChat = location.state?.newChat as boolean | undefined;
        const taskId = location.state?.taskId as string | undefined;
        const userMessage = location.state?.userMessage as string | undefined;
        const userFileId = location.state?.audioFileId as string | undefined;
        const params = location.state?.params || {};   // 获取动态参数
        const userFilename = location.state?.filename as string | undefined;

        setAudioFileId(userFileId || null);
        if (userFilename) setFilename(userFilename);
        // 回填到各个状态变量（用于参数输入框显示）
        if (params.instrument) setInstrument(params.instrument);
        if (params.tempo) setTempo(String(params.tempo));
        if (params.duration) setDuration(String(params.duration));
        if (params.filename) setFilename(params.filename);

        // 如果是新建空对话（从“开始新对话”按钮进入）
        if (newChat) {
            // 重置消息列表为空（清空示例消息）
            setMessages([]);
            setCurrentTaskId(null);
            // 清除 sessionStorage 标记，避免自动发送残留
            sessionStorage.removeItem('chat_auto_sent');
            // 可选：清空其他相关状态（如 audioFileId 等）
            setAudioFileId(null);
            setUploadedFileName(null);
            return;  // 不再继续处理其他 state
        }

        // 优先处理从 Home 传入的 taskId（任务已创建）
        if (taskId && userMessage) {
            setMessages([]);  // 清空示例消息
            setCurrentTaskId(taskId);
            // 同步更新文件名状态，以便显示文件附件
            if (userFilename) setUploadedFileName(userFilename);
            // 添加用户消息
            const userMsg: Message = {
                id: nextId(),
                type: 'user',
                content: userMessage,
                userFile: userFilename || undefined,
            };
            setMessages(prev => [...prev, userMsg]);
            // 添加处理中消息
            const processingMsg: Message = {
                id: nextId(),
                type: 'ai',
                taskId: taskId,
                deepThinking: t('chat.deepThinking'),
                content: t('chat.taskCreated'),
            };
            setMessages(prev => [...prev, processingMsg]);
            // 开始轮询任务状态
            pollTaskStatus(taskId, processingMsg.id);
            // 清除 sessionStorage 标记（若有）
            sessionStorage.removeItem('chat_auto_sent');
        } else if (userMessage && !taskId) {
            // 兼容旧逻辑：没有 taskId 时由 handleAutoSend 创建任务
            const hasSent = sessionStorage.getItem('chat_auto_sent');
            if (userMessage && !hasSent) {
                sessionStorage.setItem('chat_auto_sent', 'true');
                handleAutoSend(userMessage);
            }
        }
    }, [location.state]);

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const validFormats = ['mp3', 'wav', 'flac', 'm4a', 'ogg'];
        const ext = file.name.split('.').pop()?.toLowerCase();
        if (!ext || !validFormats.includes(ext)) {
            setUploadError(`不支持的格式: .${ext}，支持: ${validFormats.join(', ')}`);
            setUploadSuccess(null);
            return;
        }
        if (file.size > 50 * 1024 * 1024) {
            setUploadError('文件过大，最大支持 50MB');
            setUploadSuccess(null);
            return;
        }

        setUploadError(null);
        setUploadSuccess(null);
        setIsUploading(true);
        setUploadProgress(0);

        try {
            const progressInterval = setInterval(() => {
                setUploadProgress((prev) => Math.min(prev + 10, 90));
            }, 200);

            const res = await api.uploadFile(file);
            clearInterval(progressInterval);
            setUploadProgress(100);

            if (res.code === 200) {
                setAudioFileId(res.data.file_id);
                setUploadedFileName(res.data.filename);
                setUploadSuccess(
                    `文件已上传: ${res.data.filename} (${res.data.file_size.toFixed(2)} MB)${
                        res.data.duration ? `, 时长: ${Math.round(res.data.duration)}秒` : ''
                    }`
                );
                setUploadError(null);
            } else {
                setUploadError(res.message || '文件上传失败');
                setUploadSuccess(null);
            }
        } catch (err) {
            console.error('上传失败:', err);
            setUploadError(`上传失败: ${err instanceof Error ? err.message : '未知错误'}`);
            setUploadSuccess(null);
        } finally {
            setIsUploading(false);
            setTimeout(() => setUploadProgress(0), 500);
        }
    };

    const showToast = (msg: string) => {
        setToastMessage(msg);
    };

    const handleCancel = async () => {
        if (!currentTaskId) return
        await api.cancelTask(currentTaskId)
        // 停止轮询
        if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
        }
        setCurrentTaskId(null)
        setIsProcessing(false)
        // 可选择更新消息列表，提示任务已取消
    }

    return (
        <div className="flex flex-col h-screen bg-white text-gray-800 font-sans page-enter">
            <TopBar
                onNewChat={() => navigate('/chat', { state: { newChat: true } })}
            />
            <div className="flex flex-1 overflow-hidden">
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
                <main className="flex-1 flex flex-col bg-white overflow-hidden">
                    {/* 侧边栏悬浮按钮（暂不允许打开） */}
                    {!sidebarOpen && (
                        <button
                            onClick={(e) => {
                                // 防止拖拽结束误触发点击（可选：增加位移阈值判断）
                                if (!dragRef.current) showToast(t('sidebar.notAvailable') || '侧边栏暂不开放');
                            }}
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
                            <WelcomeMessage />
                            {/* 始终显示消息列表（即使为空） */}
                            <MessageList messages={messages} t={t} />
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
            {toastMessage && (
                <Toast message={toastMessage} duration={5000} onClose={() => setToastMessage(null)} />
            )}
        </div>
    );
}

export default ChatFlow;
