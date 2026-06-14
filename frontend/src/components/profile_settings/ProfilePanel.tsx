// frontend/src/components/profile_settings/ProfilePanel.tsx
import { useState } from 'react';
import { profileApi, type Profile } from '../../api/profile';

interface ProfilePanelProps {
    profiles: Profile[];
    activeProfile: Profile | null;
    isLoading: boolean;
    onRefresh: () => void;
    t: (key: string) => string;
}

export default function ProfilePanel({ profiles, activeProfile, isLoading, onRefresh, t }: ProfilePanelProps) {
    const [editingName, setEditingName] = useState('');
    const [editingProfileId, setEditingProfileId] = useState<number | null>(null);
    const [showProfileList, setShowProfileList] = useState(false);
    const [showCreateInput, setShowCreateInput] = useState(false);
    const [newProfileName, setNewProfileName] = useState('');
    const [isCreating, setIsCreating] = useState(false);

    const handleEditSubmit = async () => {
        if (!editingProfileId || !editingName.trim()) return;
        const res = await profileApi.update(editingProfileId, { name: editingName.trim() });
        if (res.code === 200) {
            onRefresh();
            setEditingProfileId(null);
            setEditingName('');
        } else {
            alert(res.message);
        }
    };

    const handleSwitchProfile = async (profile: Profile) => {
        if (profile.is_active) return;
        const res = await profileApi.activate(profile.profile_id);
        if (res.code === 200) {
            onRefresh();
            setShowProfileList(false);
        } else {
            alert(res.message);
        }
    };

    const handleCreateProfile = async () => {
        if (!newProfileName.trim()) return;
        setIsCreating(true);
        const res = await profileApi.create(newProfileName.trim());
        if (res.code === 200) {
            onRefresh();
            setShowCreateInput(false);
            setNewProfileName('');
        } else {
            alert(res.message);
        }
        setIsCreating(false);
    };

    return (
        <div>
            {/* 当前 Profile 信息 */}
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-[#e6e9e9] rounded-full flex items-center justify-center">
                        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                            <path d="M3.8501 15.1001C4.7002 14.45 5.6499 13.9375 6.7002 13.5625C7.75 13.1875 8.8501 13 10 13C11.1499 13 12.25 13.1875 13.2998 13.5625C14.3501 13.9375 15.2998 14.45 16.1499 15.1001C16.7334 14.4167 17.1875 13.6418 17.5127 12.7751C17.8374 11.9084 18 10.9834 18 10C18 7.78345 17.2207 5.896 15.6626 4.33765C14.1045 2.7793 12.2168 2 10 2C7.7832 2 5.896 2.7793 4.3374 4.33765C2.7793 5.896 2 7.78345 2 10C2 10.9834 2.1626 11.9084 2.4873 12.7751C2.8125 13.6418 3.2666 14.4167 3.8501 15.1001ZM10 11C9.0166 11 8.1875 10.6626 7.5127 9.98755C6.8374 9.3125 6.5 8.4834 6.5 7.5C6.5 6.51685 6.8374 5.6875 7.5127 5.01245C8.1875 4.33765 9.0166 4 10 4C10.9834 4 11.8125 4.33765 12.4873 5.01245C13.1626 5.6875 13.5 6.51685 13.5 7.5C13.5 8.4834 13.1626 9.3125 12.4873 9.98755C11.8125 10.6626 10.9834 11 10 11Z" fill="#475569"/>
                        </svg>
                    </div>
                    <div className="flex-1">
                        {editingProfileId === activeProfile?.profile_id ? (
                            <div className="flex items-center gap-2">
                                <input
                                    type="text"
                                    value={editingName}
                                    onChange={(e) => setEditingName(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleEditSubmit()}
                                    className="border border-gray-300 rounded-md px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-[#00639d]"
                                    autoFocus
                                />
                                <button onClick={handleEditSubmit} className="text-xs bg-[#00639d] text-white px-2 py-1 rounded">保存</button>
                                <button onClick={() => setEditingProfileId(null)} className="text-xs text-gray-500">取消</button>
                            </div>
                        ) : (
                            <div className="flex items-center gap-2">
                                <span className="text-gray-800 font-medium">{activeProfile?.name || t('profile.defaultName')}</span>
                                <button
                                    onClick={() => {
                                        setEditingProfileId(activeProfile!.profile_id);
                                        setEditingName(activeProfile?.name || '');
                                    }}
                                    className="text-gray-400 hover:text-[#00639d] transition"
                                >
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                        <path d="M17 3l4 4-7 7H10v-4l7-7zM4 20l4-4" />
                                    </svg>
                                </button>
                            </div>
                        )}
                        <div className="text-xs text-gray-400 mt-0.5">{t('profile.current')}</div>
                    </div>
                </div>
            </div>

            {/* 切换 Profile 按钮 */}
            <button
                onClick={() => setShowProfileList(!showProfileList)}
                className="w-full text-left px-4 py-2.5 rounded-lg bg-gray-50 hover:bg-gray-100 transition flex items-center justify-between text-gray-700"
            >
                <span>{t('profile.switchProfile')}</span>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M19 9l-7 7-7-7" />
                </svg>
            </button>

            {showProfileList && (
                <div className="mt-2 border border-gray-100 rounded-lg bg-white shadow-lg max-h-48 overflow-y-auto">
                    {profiles.map((profile) => (
                        <div
                            key={profile.profile_id}
                            onClick={() => handleSwitchProfile(profile)}
                            className={`px-4 py-2 cursor-pointer flex items-center justify-between hover:bg-gray-50 ${
                                profile.is_active ? 'bg-blue-50 text-[#00639d]' : 'text-gray-700'
                            }`}
                        >
                            <span>{profile.name}</span>
                            {profile.is_active && (
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M20 6L9 17l-5-5" />
                                </svg>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* 新建档案 */}
            <div className="mt-3 pt-2 border-t border-gray-100">
                {!showCreateInput ? (
                    <button
                        onClick={() => setShowCreateInput(true)}
                        className="w-full text-left px-4 py-2 rounded-lg text-[#00639d] hover:bg-blue-50 transition flex items-center gap-2"
                    >
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                            <path d="M8 3V13M3 8H13" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                        </svg>
                        {t('profile.createNew')}
                    </button>
                ) : (
                    <div className="px-1 py-2">
                        <div className="flex items-center gap-2">
                            <input
                                type="text"
                                value={newProfileName}
                                onChange={(e) => setNewProfileName(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleCreateProfile()}
                                placeholder={t('profile.newNamePlaceholder')}
                                className="flex-1 px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#00639d]"
                                autoFocus
                            />
                            <button
                                onClick={handleCreateProfile}
                                disabled={isCreating}
                                className="px-3 py-1.5 bg-[#00639d] text-white text-sm rounded-lg hover:bg-[#005288] disabled:opacity-50"
                            >
                                {isCreating ? '...' : t('profile.save')}
                            </button>
                            <button
                                onClick={() => {
                                    setShowCreateInput(false);
                                    setNewProfileName('');
                                }}
                                className="px-3 py-1.5 text-gray-500 text-sm rounded-lg hover:bg-gray-100"
                            >
                                {t('profile.cancel')}
                            </button>
                        </div>
                    </div>
                )}
            </div>

            {isLoading && (
                <div className="absolute inset-0 bg-white/60 flex items-center justify-center rounded-2xl">
                    <div className="w-6 h-6 border-2 border-[#00639d] border-t-transparent rounded-full animate-spin"></div>
                </div>
            )}
        </div>
    );
}
