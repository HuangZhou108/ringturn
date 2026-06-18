// frontend/src/components/profile_settings/SettingsModal.tsx
import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { profileApi, type Profile } from '../../api/profile';
import ProfilePanel from './ProfilePanel';
import PreferencePanel from './PreferencePanel';
import ToolPreferencePanel from './ToolPreferencePanel';

type TabType = 'base' | 'profile' | 'preference' | 'tool_preference';

interface SettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    onProfileChanged?: () => void;
}

export default function SettingsModal({ isOpen, onClose, onProfileChanged }: SettingsModalProps) {
    const { t, i18n } = useTranslation();
    const [activeTab, setActiveTab] = useState<TabType>('base');
    const [profiles, setProfiles] = useState<Profile[]>([]);
    const [activeProfile, setActiveProfile] = useState<Profile | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);

    const loadData = async () => {
        setIsLoading(true);
        try {
            const [listRes, activeRes] = await Promise.all([
                profileApi.list(),
                profileApi.getActive(),
            ]);
            if (listRes.code === 200) setProfiles(listRes.data);
            if (activeRes.code === 200) setActiveProfile(activeRes.data);
        } catch (err) {
            console.error('加载失败', err);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        if (isOpen) loadData();
    }, [isOpen]);

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                onClose();
            }
        };
        if (isOpen) document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [isOpen, onClose]);

    const refresh = async () => {
        await loadData();
        onProfileChanged?.();
    };

    if (!isOpen) return null;

    const tabLabels: Record<TabType, string> = {
        base: t('settings.tabs.base'),
        profile: t('settings.tabs.profile'),
        preference: t('settings.tabs.preference'),
        tool_preference: t('settings.tabs.tool'),
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div ref={containerRef} className="relative">
                {/* 左侧标签栏 */}
                <div className="absolute left-[-52px] top-8 flex flex-col gap-2">
                    {(Object.keys(tabLabels) as TabType[]).map((tab) => (
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
                            title={tabLabels[tab]}
                        >
                            {tabLabels[tab]}
                        </button>
                    ))}
                </div>

                {/* 主体弹窗 */}
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
                            {tabLabels[activeTab]}
                        </h3>
                    </div>

                    <div className="flex-1 overflow-y-auto px-5 pb-5">
                        {activeTab === 'base' && (
                            <div className="space-y-4">
                                <p className="text-sm text-gray-600">{t('settings.languageTitle')}</p>
                                <div className="flex gap-3">
                                    <button
                                        onClick={() => i18n.changeLanguage('en')}
                                        className={`px-4 py-2 rounded-lg border transition ${
                                            i18n.language === 'en'
                                                ? 'bg-[#00639d] text-white border-[#00639d]'
                                                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                                        }`}
                                    >
                                        {t('language.en')}
                                    </button>
                                    <button
                                        onClick={() => i18n.changeLanguage('zh')}
                                        className={`px-4 py-2 rounded-lg border transition ${
                                            i18n.language === 'zh'
                                                ? 'bg-[#00639d] text-white border-[#00639d]'
                                                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                                        }`}
                                    >
                                        {t('language.zh')}
                                    </button>
                                </div>
                                <p className="text-xs text-gray-400 mt-2">{t('settings.currentLanguage')} {i18n.language === 'zh' ? t('language.zh') : t('language.en')}</p>
                            </div>
                        )}

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
                                onSave={refresh}
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
