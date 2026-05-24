// src/components/ProfileSwitcher.tsx
// Profile切换组件

import { useState, useEffect, useRef } from 'react'
import { profileApi, parsePreferences, type Profile, type ProfilePreferences } from '../api/profile'

interface ProfileSwitcherProps {
  onProfileSwitch?: (profile: Profile) => void
}

export default function ProfileSwitcher({ onProfileSwitch }: ProfileSwitcherProps) {
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [activeProfile, setActiveProfile] = useState<Profile | null>(null)
  const [isOpen, setIsOpen] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newProfileName, setNewProfileName] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // 加载Profile列表
  const loadProfiles = async () => {
    try {
      const [listRes, activeRes] = await Promise.all([
        profileApi.list(),
        profileApi.getActive(),
      ])

      if (listRes.code === 200) {
        setProfiles(listRes.data)
      }

      if (activeRes.code === 200) {
        setActiveProfile(activeRes.data)
      }
    } catch (err) {
      console.error('Failed to load profiles:', err)
    }
  }

  useEffect(() => {
    loadProfiles()
  }, [])

  // 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  // 切换Profile
  const handleSwitchProfile = async (profile: Profile) => {
    if (profile.is_active) {
      setIsOpen(false)
      return
    }

    setIsLoading(true)
    try {
      const res = await profileApi.activate(profile.profile_id)
      if (res.code === 200) {
        await loadProfiles()
        const newActive = profiles.find(p => p.profile_id === profile.profile_id)
        if (newActive && onProfileSwitch) {
          onProfileSwitch(newActive)
        }
      }
    } catch (err) {
      console.error('Failed to switch profile:', err)
    } finally {
      setIsLoading(false)
      setIsOpen(false)
    }
  }

  // 创建新Profile
  const handleCreateProfile = async () => {
    if (!newProfileName.trim()) return

    setIsLoading(true)
    try {
      const res = await profileApi.create(newProfileName.trim())
      if (res.code === 200) {
        await loadProfiles()
        setShowCreateModal(false)
        setNewProfileName('')
      }
    } catch (err) {
      console.error('Failed to create profile:', err)
    } finally {
      setIsLoading(false)
    }
  }

  // 删除Profile
  const handleDeleteProfile = async (e: React.MouseEvent, profile: Profile) => {
    e.stopPropagation()

    if (profiles.length <= 1) {
      alert('至少需要保留一个Profile')
      return
    }

    if (!confirm(`确定删除Profile "${profile.name}"？`)) {
      return
    }

    setIsLoading(true)
    try {
      const res = await profileApi.delete(profile.profile_id)
      if (res.code === 200) {
        await loadProfiles()
      }
    } catch (err) {
      console.error('Failed to delete profile:', err)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="relative" ref={dropdownRef}>
      {/* 切换按钮 */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-gray-100 transition"
        disabled={isLoading}
      >
        <div className="w-8 h-8 bg-[#00639d] rounded-full flex items-center justify-center">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path
              d="M8 8C9.65685 8 11 6.65685 11 5C11 3.34315 9.65685 2 8 2C6.34315 2 5 3.34315 5 5C5 6.65685 6.34315 8 8 8Z"
              fill="white"
            />
            <path
              d="M2 14C2 11.7909 3.79086 10 6 10H10C12.2091 10 14 11.7909 14 14V15C14 15.5523 13.5523 16 13 16H3C2.44772 16 2 15.5523 2 15V14Z"
              fill="white"
            />
          </svg>
        </div>
        <div className="text-left">
          <div className="text-sm font-medium text-gray-700">
            {activeProfile?.name || '默认'}
          </div>
          <div className="text-xs text-gray-500">
            Profile
          </div>
        </div>
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          className={`transition-transform ${isOpen ? 'rotate-180' : ''}`}
        >
          <path
            d="M3 4.5L6 7.5L9 4.5"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {/* 下拉菜单 */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-64 bg-white rounded-xl shadow-lg border border-gray-100 py-2 z-50">
          <div className="px-3 py-2 text-xs font-medium text-gray-500 uppercase tracking-wider">
            选择 Profile
          </div>

          {/* Profile列表 */}
          <div className="max-h-64 overflow-y-auto">
            {profiles.map((profile) => (
              <div
                key={profile.profile_id}
                onClick={() => handleSwitchProfile(profile)}
                className={`
                  px-3 py-2 cursor-pointer flex items-center justify-between
                  ${profile.is_active ? 'bg-blue-50' : 'hover:bg-gray-50'}
                `}
              >
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <div
                    className={`
                      w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium
                      ${profile.is_active ? 'bg-[#00639d] text-white' : 'bg-gray-200 text-gray-500'}
                    `}
                  >
                    {profile.name.charAt(0).toUpperCase()}
                  </div>
                  <span className={`text-sm truncate ${profile.is_active ? 'text-[#00639d] font-medium' : 'text-gray-700'}`}>
                    {profile.name}
                  </span>
                  {profile.is_active && (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="ml-auto">
                      <path
                        d="M13.5 4.5L6 12L2.5 8.5"
                        stroke="#00639d"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </div>

                {/* 删除按钮 */}
                {!profile.is_active && profiles.length > 1 && (
                  <button
                    onClick={(e) => handleDeleteProfile(e, profile)}
                    className="p-1 hover:bg-red-50 rounded transition opacity-0 group-hover:opacity-100"
                    title="删除"
                  >
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path
                        d="M10.5 3.5L3.5 10.5M3.5 3.5L10.5 10.5"
                        stroke="#ef4444"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                      />
                    </svg>
                  </button>
                )}
              </div>
            ))}
          </div>

          {/* 分隔线 */}
          <div className="border-t border-gray-100 my-2"></div>

          {/* 新建Profile按钮 */}
          <button
            onClick={() => setShowCreateModal(true)}
            className="w-full px-3 py-2 text-left text-sm text-[#00639d] hover:bg-blue-50 flex items-center gap-2"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M8 3V13M3 8H13"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
            新建 Profile
          </button>
        </div>
      )}

      {/* 新建Profile弹窗 */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 w-80 shadow-2xl">
            <h3 className="text-lg font-semibold text-gray-800 mb-4">新建 Profile</h3>
            <input
              type="text"
              value={newProfileName}
              onChange={(e) => setNewProfileName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreateProfile()
                if (e.key === 'Escape') setShowCreateModal(false)
              }}
              placeholder="输入 Profile 名称"
              className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#00639d] focus:border-transparent"
              autoFocus
            />
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => setShowCreateModal(false)}
                className="flex-1 px-4 py-2 border border-gray-200 rounded-lg text-gray-600 hover:bg-gray-50 transition"
              >
                取消
              </button>
              <button
                onClick={handleCreateProfile}
                disabled={!newProfileName.trim() || isLoading}
                className="flex-1 px-4 py-2 bg-[#00639d] text-white rounded-lg hover:bg-[#005288] transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? '创建中...' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
