import type { ApiResponse, CreateTaskRequest, CreateTaskResponse, Task, TaskStatusInfo, TaskResult, TaskCancelResult,TaskListResponse } from '../types'

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
}

export type { ApiResponse }