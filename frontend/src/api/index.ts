import type { ApiResponse, CreateTaskRequest, CreateTaskResponse,
    Task, TaskStatusInfo, TaskResult, TaskCancelResult,TaskListResponse, UploadResult } from '../types'

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

    // 获取生成结果
    getTaskResult: (taskId: string) =>
        request<TaskResult>(`/tasks/${taskId}/result`),

    // 取消任务
    cancelTask: (taskId: string) =>
        request<TaskCancelResult>(`/tasks/${taskId}`, { method: 'DELETE' }),

    // 获取用户历史任务列表
    getUserTasks: (userId: number, params?: { page?: number; page_size?: number; status?: string }) => {
        const query = new URLSearchParams()
        if (params?.page) query.append('page', String(params.page))
        if (params?.page_size) query.append('page_size', String(params.page_size))
        if (params?.status) query.append('status', params.status)
        return request<TaskListResponse>(`/users/${userId}/tasks?${query.toString()}`)
    },

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
}

export type { ApiResponse }