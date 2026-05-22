// src/api/conversation.ts
// 会话相关API

import type { ApiResponse } from './index'

// ==================== 类型定义 ====================

export interface Conversation {
  conversation_id: string
  title: string
  status: 'active' | 'completed'
  created_at: string
  updated_at: string
}

export interface ConversationListItem {
  conversation_id: string
  title: string
  status: string
  message_count: number
  last_message: string | null
  created_at: string
  updated_at: string
}

export interface ConversationListResponse {
  total: number
  page: number
  page_size: number
  conversations: ConversationListItem[]
}

export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  task_id: string | null
  created_at: string
}

export interface ConversationDetail {
  conversation_id: string
  title: string
  status: string
  messages: Message[]
  created_at: string
  updated_at: string
}

// ==================== API 函数 ====================

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

export const conversationApi = {
  // 获取会话列表
  list: (params?: { page?: number; page_size?: number; status?: string }) => {
    const query = new URLSearchParams()
    if (params?.page) query.append('page', String(params.page))
    if (params?.page_size) query.append('page_size', String(params.page_size))
    if (params?.status) query.append('status', params.status)
    const queryStr = query.toString() ? `?${query.toString()}` : ''
    return request<ConversationListResponse>(`/conversations${queryStr}`)
  },

  // 获取会话详情
  get: (conversationId: string) =>
    request<ConversationDetail>(`/conversations/${conversationId}`),

  // 创建会话
  create: (data: { title?: string; user_request: string }) =>
    request<{ conversation_id: string; title: string; status: string; created_at: string }>(
      '/conversations',
      {
        method: 'POST',
        body: JSON.stringify(data),
      }
    ),

  // 删除会话
  delete: (conversationId: string) =>
    request<{ conversation_id: string }>(`/conversations/${conversationId}`, {
      method: 'DELETE',
    }),

  // 更新会话标题
  updateTitle: (conversationId: string, title: string) =>
    request<{ conversation_id: string; title: string }>(`/conversations/${conversationId}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),

  // 标记会话完成
  complete: (conversationId: string) =>
    request<{ conversation_id: string; status: string }>(
      `/conversations/${conversationId}/complete`,
      { method: 'POST' }
    ),

  // 添加消息
  addMessage: (
    conversationId: string,
    data: { role: 'user' | 'assistant'; content: string; task_id?: string }
  ) =>
    request<{
      message_id: number
      conversation_id: string
      role: string
      content: string
      task_id: string | null
      created_at: string
    }>(`/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),
}
