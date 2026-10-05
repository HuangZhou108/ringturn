import type { ApiResponse, CreateTaskRequest, CreateTaskResponse,
    Task, TaskStatusInfo, TaskResult, TaskCancelResult,TaskListResponse, UploadResult,
    ConversationListItem, ConversationDetail, ConversationMessage, Profile,
    ProfilePreferences, ProfileTasksResponse, AgentTraceEvent} from '../types'

const BASE_URL = '/api/v1'

async function request<T>(url: string, options?: RequestInit): Promise<ApiResponse<T>> {
    const res = await fetch(`${BASE_URL}${url}`, {
        headers: {
            'Content-Type': 'application/json',
        },
        ...options,
    })

    if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
    }

    return res.json()
}

export const api = {
    // 创建任务
    createTask: (data: CreateTaskRequest) =>
        request<CreateTaskResponse>('/tasks', {
            method: 'POST',
            body: JSON.stringify(data),
        }),

    // 获取任务详情
    getTask: (taskId: string) =>
        request<Task>(`/tasks/${taskId}`),

    // 获取任务状态
    getTaskStatus: (taskId: string) =>
        request<TaskStatusInfo>(`/tasks/${taskId}/status`),

    // 获取结构化 Agent 执行轨迹（开发/诊断用途）
    getTaskTrace: (taskId: string) =>
        request<{ task_id: string; status: string; events: AgentTraceEvent[] }>(
            `/tasks/${taskId}/trace`,
        ),

    // 获取生成结果
    getTaskResult: (taskId: string) =>
        request<TaskResult>(`/tasks/${taskId}/result`),

    // 取消任务
    cancelTask: (taskId: string) =>
        request<TaskCancelResult>(`/tasks/${taskId}`, { method: 'DELETE' }),


    // 上传音频文件
    uploadFile: async (file: File, metadata?: { title?: string; artist?: string }) => {
        const formData = new FormData()
        formData.append('file', file)
        if (metadata) {
            formData.append('metadata', JSON.stringify(metadata))
        }

        const res = await fetch('/api/v1/upload', {
            method: 'POST',
            body: formData,
        })

        return res.json() as Promise<ApiResponse<UploadResult>>
    },

    // 下载音频文件
    downloadFile: async (fileUrl: string, filename: string) => {
        try {
            const res = await fetch(fileUrl)
            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            const blob = await res.blob()
            const url = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = url
            link.download = filename
            document.body.appendChild(link)
            link.click()
            document.body.removeChild(link)
            URL.revokeObjectURL(url)
        } catch (err) {
            console.error('下载失败:', err)
            // 降级：直接打开链接
            window.open(fileUrl, '_blank')
        }
    },
    // 获取会话列表
    getConversations: (params?: { page?: number; page_size?: number; status?: string }) => {
        const query = new URLSearchParams()
        if (params?.page) query.append('page', String(params.page))
        if (params?.page_size) query.append('page_size', String(params.page_size))
        if (params?.status) query.append('status', params.status)
        return request<{ total: number; page: number; page_size: number; conversations: ConversationListItem[] }>(`/conversations?${query.toString()}`)
    },

    // 获取会话详情
    getConversation: (conversationId: string) =>
        request<ConversationDetail>(`/conversations/${conversationId}`),

    // 删除会话
    deleteConversation: (conversationId: string) =>
        request<{ conversation_id: string }>(`/conversations/${conversationId}`, { method: 'DELETE' }),

    // 更新会话标题
    updateConversation: (conversationId: string, title: string) =>
        request<{ conversation_id: string; title: string }>(`/conversations/${conversationId}`, {
            method: 'PATCH',
            body: JSON.stringify({ title }),
        }),

    // 添加消息到会话
    addMessage: (conversationId: string, data: { role: 'user' | 'assistant'; content: string; task_id?: string }) =>
        request<ConversationMessage>(`/conversations/${conversationId}/messages`, {
            method: 'POST',
            body: JSON.stringify(data),
        }),

    // 标记会话完成
    completeConversation: (conversationId: string) =>
        request<{ conversation_id: string; status: string }>(`/conversations/${conversationId}/complete`, {
            method: 'POST',
        }),

    // 创建 Profile
    createProfile: (name: string) =>
        request<Profile>(`/profiles`, {
            method: 'POST',
            body: JSON.stringify({ name }),
        }),

    // 获取所有 Profile 列表
    getProfiles: () =>
        request<Profile[]>(`/profiles`),

    // 获取当前活跃的 Profile
    getActiveProfile: () =>
        request<Profile>(`/profiles/active`),

    // 切换活跃 Profile
    activateProfile: (profileId: number) =>
        request<Profile>(`/profiles/${profileId}/activate`, { method: 'PUT' }),

    // 更新 Profile 名称
    updateProfile: (profileId: number, name: string) =>
        request<Profile>(`/profiles/${profileId}`, {
            method: 'PUT',
            body: JSON.stringify({ name }),
        }),

    // 删除 Profile
    deleteProfile: (profileId: number) =>
        request<null>(`/profiles/${profileId}`, { method: 'DELETE' }),

    // 获取 Profile 的任务列表
    getProfileTasks: (profileId: number, params?: { page?: number; page_size?: number; status?: string }) => {
        const query = new URLSearchParams()
        if (params?.page) query.append('page', String(params.page))
        if (params?.page_size) query.append('page_size', String(params.page_size))
        if (params?.status) query.append('status', params.status)
        return request<ProfileTasksResponse>(`/profiles/${profileId}/tasks?${query.toString()}`)
    },

    // 获取 Profile 的所有偏好
    getProfilePreferences: (profileId: number) =>
        request<ProfilePreferences>(`/profiles/${profileId}/preferences`),

    // 创建反馈
    createFeedback: (taskId: string, feedback: string, params?: Record<string, any>) =>
        request<{ task_id: string; parent_task_id: string; status: string }>(
            `/tasks/${taskId}/feedback`,
            {
                method: 'POST',
                body: JSON.stringify({ feedback, parent_task_id: taskId, params }), // 注意 schema 要求 parent_task_id
            }
        ),
}

export type { ApiResponse }
