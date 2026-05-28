// src/components/Sidebar.tsx
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { conversationApi, type ConversationListItem } from '../api/conversation'

interface SidebarProps {
    sidebarOpen: boolean
    setSidebarOpen: (open: boolean) => void
    // 会话相关
    currentConversationId: string | null
    setCurrentConversationId: (id: string | null) => void
    onNewConversation?: () => void
    // 任务相关（保留兼容性）
    recentTasks?: any[]
    currentTaskId?: string | null
    setCurrentTaskId?: (id: string | null) => void
    onRefresh?: () => Promise<void>
    refreshTrigger?: number // 在ChatFlow新建对话时自动刷新侧边栏
    profileId?: number | null
}

export default function Sidebar({
                                    sidebarOpen,
                                    setSidebarOpen,
                                    currentConversationId,
                                    setCurrentConversationId,
                                    onNewConversation,
                                    recentTasks = [],
                                    currentTaskId = null,
                                    setCurrentTaskId,
                                    onRefresh,
                                    refreshTrigger,
                                    profileId,
                                }: SidebarProps) {
    const { t } = useTranslation()
    const navigate = useNavigate()

    // 会话列表状态
    const [conversations, setConversations] = useState<ConversationListItem[]>([])
    const [filter, setFilter] = useState<'all' | 'active' | 'completed'>('all')
    const [isLoading, setIsLoading] = useState(false)

    // 加载会话列表
    const loadConversations = async () => {
        if (!profileId) return;
        setIsLoading(true)
        try {
            const status = filter === 'all' ? undefined : filter
            const res = await conversationApi.list({ page: 1, page_size: 50, status: filter === 'all' ? undefined : filter, profile_id: profileId });            if (res.code === 200) {
                setConversations(res.data.conversations)
            }
        } catch (err) {
            console.error('Failed to load conversations:', err)
        } finally {
            setIsLoading(false)
        }
    }

    useEffect(() => {
        if (sidebarOpen) {
            loadConversations()
        }
    }, [sidebarOpen, filter, profileId])

    // 删除会话
    const handleDeleteConversation = async (e: React.MouseEvent, id: string) => {
        e.stopPropagation()
        e.preventDefault()

        if (!confirm('确定删除该会话？')) return

        try {
            const res = await conversationApi.delete(id)
            if (res.code === 200) {
                setConversations(prev => prev.filter(c => c.conversation_id !== id))
                // 如果当前选中的会话被删除，清除选中状态
                if (currentConversationId === id) {
                    setCurrentConversationId(null)
                    // 如果有回调，调用它
                    if (onNewConversation) {
                        onNewConversation()
                    }
                }
            }
        } catch (err) {
            console.error('Failed to delete conversation:', err)
        }
    }

    // 点击会话
    const handleConversationClick = (conv: ConversationListItem) => {
        setCurrentConversationId(conv.conversation_id)
        // 可以导航到聊天页面并加载该会话
        navigate(`/chat/c/${conv.conversation_id}`, {
            state: { conversationId: conv.conversation_id, newChat: false }
        });
    }

    // 新建会话
    const handleNewChat = () => {
        setCurrentConversationId(null);
        if (onNewConversation) {
            onNewConversation();
        }
        navigate('/chat');
    }

    // 自动刷新
    useEffect(() => {
        if (sidebarOpen) {
            loadConversations();
        }
    }, [refreshTrigger, sidebarOpen, filter]);

    // 添加状态管理编辑中的会话
    const [editingConversationId, setEditingConversationId] = useState<string | null>(null);
    const [editingTitle, setEditingTitle] = useState('');

    // 添加编辑处理函数
    const handleDoubleClick = (conv: ConversationListItem) => {
        setEditingConversationId(conv.conversation_id);
        setEditingTitle(conv.title || '未命名会话');
    };

    const handleEditSubmit = async (convId: string) => {
        if (!editingTitle.trim()) return;

        try {
            const res = await conversationApi.updateTitle(convId, editingTitle.trim());
            if (res.code === 200) {
                // 更新本地列表
                setConversations(prev => prev.map(conv =>
                    conv.conversation_id === convId
                        ? { ...conv, title: editingTitle.trim() }
                        : conv
                ));
            }
        } catch (err) {
            console.error('更新标题失败:', err);
        } finally {
            setEditingConversationId(null);
            setEditingTitle('');
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent, convId: string) => {
        if (e.key === 'Enter') {
            handleEditSubmit(convId);
        } else if (e.key === 'Escape') {
            setEditingConversationId(null);
            setEditingTitle('');
        }
    };

    return (
        <aside
            className={`border-r border-[#e0f2fe] flex flex-col bg-[#f0f9ff] transition-all duration-300 ${
                sidebarOpen ? 'w-72 p-4' : 'w-0 p-0 overflow-hidden border-r-0'
            }`}
        >
            {/* Logo 区域 */}
            <div className="w-full mb-6">
                <div className="flex items-center justify-between">
                    {/* 左侧：Logo区域 */}
                    <div className="flex items-center gap-2">
                        <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center flex-shrink-0">
                            <svg width="12" height="18" viewBox="0 0 12 18" fill="none">
                                <path d="M4 18C2.8999 18 1.9585 17.6083 1.17505 16.825C0.391602 16.0417 0 15.1 0 14C0 12.9 0.391602 11.9583 1.17505 11.175C1.9585 10.3917 2.8999 10 4 10C4.3833 10 4.73755 10.0458 5.0625 10.1375C5.38745 10.2292 5.69995 10.3667 6 10.55V0H12V4H8V14C8 15.1 7.6084 16.0417 6.82495 16.825C6.0415 17.6083 5.1001 18 4 18Z" fill="#458ecb"/>
                            </svg>
                        </div>
                        <div className="relative w-[132px] h-[38px]">
                            <div className="absolute left-0 -top-[1px]">
                                <span className="text-lg font-semibold leading-tight text-[#0c4a6e] font-['Inter']">{t('sidebar.ringTurn')}</span>
                            </div>
                            <div className="absolute left-0 top-[22.5px]">
                                <span className="text-[10px] font-semibold uppercase tracking-[1px] text-[#41565f]/70 font-['Inter']">{t('sidebar.aiMusic')}</span>
                            </div>
                        </div>
                    </div>

                    {/* 右侧：收起按钮 */}
                    <button
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                        className="w-6 h-6 rounded hover:bg-gray-200 flex items-center justify-center flex-shrink-0 text-gray-400 hover:text-gray-600 transition"
                    >
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                            {sidebarOpen ? (
                                <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                            ) : (
                                <path d="M6 12L10 8L6 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                            )}
                        </svg>
                    </button>
                </div>
            </div>

            {/* 新建会话按钮 */}
            <button
                onClick={handleNewChat}
                className="w-full self-stretch mb-4 px-4 py-3 bg-[#00639d] text-[#f7f9ff] rounded-xl hover:bg-[#005288] transition flex items-center justify-center gap-2"
            >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M6 7H0V5H6V0H8V5H14V7H8V14H6V7Z" fill="#f7f9ff"/>
                </svg>
                {t('sidebar.newConversation') || '新建会话'}
            </button>

            {/* 会话列表区域 */}
            <div className="flex-1 overflow-hidden flex flex-col">
                {/* 过滤 tabs */}
                <div className="flex gap-1 mb-3 bg-white rounded-lg p-1">
                    <button
                        onClick={() => setFilter('all')}
                        className={`flex-1 py-1.5 text-xs font-medium rounded-md transition ${
                            filter === 'all' ? 'bg-[#00639d] text-white' : 'text-gray-500 hover:bg-gray-50'
                        }`}
                    >
                        全部
                    </button>
                    <button
                        onClick={() => setFilter('active')}
                        className={`flex-1 py-1.5 text-xs font-medium rounded-md transition ${
                            filter === 'active' ? 'bg-[#00639d] text-white' : 'text-gray-500 hover:bg-gray-50'
                        }`}
                    >
                        进行中
                    </button>
                    <button
                        onClick={() => setFilter('completed')}
                        className={`flex-1 py-1.5 text-xs font-medium rounded-md transition ${
                            filter === 'completed' ? 'bg-[#00639d] text-white' : 'text-gray-500 hover:bg-gray-50'
                        }`}
                    >
                        已完成
                    </button>
                </div>

                {/* 刷新按钮 */}
                <div className="flex items-center justify-between mb-2">
                    <h2 className="text-xs uppercase tracking-wider text-gray-500">
                        {t('sidebar.conversations') || '会话'}
                    </h2>
                    <button
                        onClick={loadConversations}
                        disabled={isLoading}
                        className="p-1 hover:bg-gray-200 rounded transition disabled:opacity-50"
                        title="刷新"
                    >
                        {/* 图标来自：https://heroicons.com/ */}
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor" className={`size-4 ${isLoading ? 'animate-spin' : ''}`}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
                        </svg>

                    </button>
                </div>

                {/* 会话列表 */}
                <div className="flex-1 overflow-y-auto space-y-1">
                    {isLoading && conversations.length === 0 ? (
                        <div className="flex items-center justify-center py-8">
                            <div className="w-6 h-6 border-2 border-[#00639d] border-t-transparent rounded-full animate-spin"></div>
                        </div>
                    ) : conversations.length === 0 ? (
                        <div className="text-center py-8 text-gray-400 text-sm">
                            {filter === 'all' ? '暂无会话记录' : `暂无${filter === 'active' ? '进行中' : '已完成'}的会话`}
                        </div>
                    ) : (
                        conversations.map(conv => (
                            <div
                                key={conv.conversation_id}
                                onClick={() => handleConversationClick(conv)}
                                className={`group relative px-3 py-2.5 rounded-lg cursor-pointer transition-all duration-150 ${
                                    currentConversationId === conv.conversation_id
                                        ? 'bg-[#00639d] text-white shadow-md'
                                        : 'hover:bg-white hover:shadow-sm'
                                }`}
                            >
                                {/* 会话标题 - 支持双击编辑 */}
                                <div className="flex flex-col">
                                    {editingConversationId === conv.conversation_id ? (
                                        <input
                                            type="text"
                                            value={editingTitle}
                                            onChange={(e) => setEditingTitle(e.target.value)}
                                            onBlur={() => handleEditSubmit(conv.conversation_id)}
                                            onKeyDown={(e) => handleKeyDown(e, conv.conversation_id)}
                                            onClick={(e) => e.stopPropagation()}
                                            className={`text-sm font-medium px-1 py-0.5 rounded ${
                                                currentConversationId === conv.conversation_id
                                                    ? 'bg-white/20 text-white'
                                                    : 'bg-gray-100 text-gray-800'
                                            }`}
                                            autoFocus
                                        />
                                    ) : (
                                        <div
                                            onDoubleClick={(e) => {
                                                e.stopPropagation();
                                                handleDoubleClick(conv);
                                            }}
                                            className={`text-sm font-medium truncate ${
                                                currentConversationId === conv.conversation_id
                                                    ? 'text-white'
                                                    : 'text-gray-800'
                                            }`}
                                        >
                                            {conv.title || '未命名会话'}
                                        </div>
                                    )}

                                    {/* 时间 + 状态标签（保持原样） */}
                                    <div className="flex items-center justify-between mt-1">
                <span className={`text-xs ${
                    currentConversationId === conv.conversation_id
                        ? 'text-white/50'
                        : 'text-gray-400'
                }`}>
                    {new Date(conv.updated_at + 'Z').toLocaleDateString('zh-CN', {
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                    })}
                </span>
                                        <span className={`
                    px-1.5 py-0.5 text-[10px] font-medium rounded
                    ${conv.status === 'active'
                                            ? (currentConversationId === conv.conversation_id
                                                ? 'bg-white/20 text-white'
                                                : 'bg-green-100 text-green-600')
                                            : (currentConversationId === conv.conversation_id
                                                ? 'bg-white/20 text-white'
                                                : 'bg-gray-100 text-gray-500')
                                        }
                `}>
                    {conv.status === 'active' ? '进行中' : '已完成'}
                </span>
                                    </div>
                                </div>

                                {/* 删除按钮 */}
                                <button
                                    onClick={(e) => handleDeleteConversation(e, conv.conversation_id)}
                                    className={`
                                        absolute right-2 top-2 p-1.5 rounded-md
                                        transition-all duration-150
                                        ${currentConversationId === conv.conversation_id
                                            ? 'hover:bg-white/20 text-white/50 hover:text-white'
                                            : 'opacity-0 group-hover:opacity-100 hover:bg-red-50 text-gray-400 hover:text-red-500'
                                        }
                                    `}
                                    title="删除会话"
                                >
                                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                                        <path d="M11.5 3.5L2.5 12.5M2.5 3.5L11.5 12.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                                    </svg>
                                </button>

                                {/* 消息数量 */}
                                <div className={`
                                    absolute left-1 top-1/2 -translate-y-1/2
                                    text-[10px]
                                    ${currentConversationId === conv.conversation_id
                                        ? 'text-white/40'
                                        : 'text-gray-300'
                                    }
                                `}>
                                    <svg width="2" height="24" viewBox="0 0 2 24">
                                        <rect width="2" height="24" rx="1" fill="currentColor"/>
                                    </svg>
                                </div>
                            </div>
                        ))
                    )}
                </div>
            </div>

            {/* 底部设置 */}
            <div className="pt-4 border-t border-gray-200 space-y-2">
                <div className="px-3 py-2 text-gray-500 hover:text-blue-600 cursor-pointer flex items-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.214 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.003-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
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
    )
}
