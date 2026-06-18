// frontend/src/components/profile_settings/index.tsx
import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { profileApi, type Profile } from '../../api/profile';
import ProfilePanel from './ProfilePanel';
import PreferencePanel from './PreferencePanel';
import ToolPreferencePanel from './ToolPreferencePanel';

type TabType = 'profile' | 'preference' | 'tool_preference';

interface ProfileSettingsProps {
    isOpen: boolean;
    onClose: () => void;
    onProfileChanged?: () => void;
}

export default function ProfileSettings({ isOpen, onClose, onProfileChanged }: ProfileSettingsProps) {
    const { t } = useTranslation();
    const [activeTab, setActiveTab] = useState<TabType>('profile');
    const [profiles, setProfiles] = useState<Profile[]>([]);
    const [activeProfile, setActiveProfile] = useState<Profile | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [preferences, setPreferences] = useState<any>({});
    const containerRef = useRef<HTMLDivElement>(null);  // 改为容器 ref

    // 加载数据
    const loadData = async () => {
        setIsLoading(true);
        try {
            const [listRes, activeRes] = await Promise.all([
                profileApi.list(),
                profileApi.getActive(),
            ]);
            if (listRes.code === 200) setProfiles(listRes.data);
            if (activeRes.code === 200) {
                setActiveProfile(activeRes.data);
                try {
                    const prefs = activeRes.data.preferences_data ? JSON.parse(activeRes.data.preferences_data) : {};
                    setPreferences(prefs);
                } catch {
                    setPreferences({});
                }
            }
        } catch (err) {
            console.error('加载失败', err);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) loadData();
    }, [isOpen]);

    // 点击外部关闭：现在容器包含标签和弹框，只有点击完全外部才关闭
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                onClose();
            }
        };
        if (isOpen) document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [isOpen, onClose]);

    // 刷新数据（用于子组件操作后）
    const refresh = async () => {
        await loadData();
        onProfileChanged?.();
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            {/* 相对定位容器，同时包含标签和弹框，整体作为弹窗区域 */}
            <div ref={containerRef} className="relative">
                {/* 标签容器：横向书签样式，垂直排列，只占上半部分 */}
                <div className="absolute left-[-52px] top-8 flex flex-col gap-2">
                    {(['profile', 'preference', 'tool_preference'] as TabType[]).map((tab) => {
                        let label = '';
                        if (tab === 'profile') label = '档案';
                        else if (tab === 'preference') label = '偏好';
                        else label = '工具';
                        return (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={`
                                    px-3 py-2 w-12 rounded-l-lg shadow-md transition-all duration-150
                                    flex items-center justify-center whitespace-nowrap
                                    ${activeTab === tab
                                    ? 'bg-white text-[#00639d] font-medium z-10 border-y border-l border-gray-200'
                                    : 'bg-gray-200 text-gray-600 hover:bg-gray-300'
                                }
                                `}
                                title={label}
                            >
                                {label}
                            </button>
                        );
                    })}
                </div>

                {/* 弹框主体 */}
                <div className="bg-white rounded-2xl shadow-xl w-[520px] h-[360px] relative flex flex-col animate-in fade-in zoom-in duration-200">
                    <button
                        onClick={onClose}
                        className="absolute top-3 right-3 text-gray-400 hover:text-gray-600 transition z-10"
                    >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M18 6L6 18M6 6l12 12" />
                        </svg>
                    </button>

                    <div className="pt-5 px-5 pb-2">
                        <h3 className="text-lg font-semibold text-gray-800 pr-6">
                            {activeTab === 'profile' && t('profile.title')}
                            {activeTab === 'preference' && '音乐偏好设置'}
                            {activeTab === 'tool_preference' && '工具链配置'}
                        </h3>
                    </div>

                    {/* 滚动内容区 */}
                    <div className="flex-1 overflow-y-auto px-5 pb-5">
                        {activeTab === 'profile' && (
                            <ProfilePanel
                                profiles={profiles}
                                activeProfile={activeProfile}
                                isLoading={isLoading}
                                onRefresh={refresh}
                                t={t}
                            />
                        )}
                        {activeTab === 'preference' && activeProfile && (
                            <PreferencePanel
                                profileId={activeProfile.profile_id}
                                preferences={preferences}
                                onSave={refresh}
                                isLoading={isLoading}
                                t={t}
                            />
                        )}
                        {activeTab === 'tool_preference' && activeProfile && (
                            <ToolPreferencePanel profileId={activeProfile.profile_id} t={t} />
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
