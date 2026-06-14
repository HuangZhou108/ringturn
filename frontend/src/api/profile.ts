// src/api/profile.ts
// Profile相关API

import type { ApiResponse } from './index'

// ==================== 类型定义 ====================

export interface Profile {
  profile_id: number
  name: string
  is_active: boolean
  preferences_data: string | null
  created_at: string
  updated_at?: string
}

export interface ProfilePreferences {
  default_instrument?: string
  default_duration?: number
  default_tempo?: number
  disliked_instruments?: string[]
  liked_instruments?: string[]
  auto_apply?: boolean
  [key: string]: unknown
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

export const profileApi = {
  // 获取所有Profile列表
  list: () => request<Profile[]>('/profiles'),

  // 获取当前活跃Profile
  getActive: () =>
    request<Profile>('/profiles/active'),

  // 获取指定Profile详情
  get: (profileId: number) =>
    request<Profile>(`/profiles/${profileId}`),

  // 创建Profile
  create: (name: string) =>
    request<{ profile_id: number; name: string; is_active: boolean; created_at: string }>(
      '/profiles',
      {
        method: 'POST',
        body: JSON.stringify({ name }),
      }
    ),

  // 更新Profile（名称或偏好配置）
  update: (
    profileId: number,
    data: { name?: string; preferences_data?: string }
  ) =>
    request<{
      profile_id: number
      name: string
      is_active: boolean
      preferences_data: string | null
    }>(`/profiles/${profileId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  // 切换活跃Profile
  activate: (profileId: number) =>
    request<{ profile_id: number; name: string; is_active: boolean }>(
      `/profiles/${profileId}/activate`,
      { method: 'PUT' }
    ),

  // 删除Profile
  delete: (profileId: number) =>
    request<null>(`/profiles/${profileId}`, { method: 'DELETE' }),

  // 导出偏好配置
  exportPreferences: (profileId: number) =>
    request<{ profile_name: string; preferences: ProfilePreferences; exported_at: string }>(
      `/profiles/${profileId}/export`
    ),

  // 导入偏好配置
  importPreferences: (profileId: number, preferences: ProfilePreferences) =>
    request<{ profile_id: number; preferences: ProfilePreferences }>(
      `/profiles/${profileId}/import`,
      {
        method: 'POST',
        body: JSON.stringify({ preferences }),
      }
    ),
}

// 辅助函数：解析偏好配置JSON
export function parsePreferences(preferencesData: string | null): ProfilePreferences {
  if (!preferencesData) {
    return {}
  }
  try {
    return JSON.parse(preferencesData)
  } catch {
    return {}
  }
}

// 辅助函数：序列化偏好配置为JSON
export function stringifyPreferences(preferences: ProfilePreferences): string {
  return JSON.stringify(preferences)
}

// 获取工具链配置
export const getToolPreference = (profileId: number, graphName: string) =>
    request<{ config: any }>(`/profiles/${profileId}/tool-preferences/${graphName}`)

// 保存工具链配置
export const updateToolPreference = (profileId: number, graphName: string, config: any) =>
    request<null>(`/profiles/${profileId}/tool-preferences/${graphName}`, {
      method: 'PUT',
      body: JSON.stringify({ config }),
    })

// 删除工具链配置（恢复默认）
export const deleteToolPreference = (profileId: number, graphName: string) =>
    request<null>(`/profiles/${profileId}/tool-preferences/${graphName}`, {
      method: 'DELETE',
    })
