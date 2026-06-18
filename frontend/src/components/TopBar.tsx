// src/components/TopBar.tsx
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import ProfileSettings from './profile_settings';

interface TopBarProps {
    title?: string;               // 左侧标题，默认使用 t('header.chatFlow')
    showNewChat?: boolean;        // 是否显示“新建”按钮，默认 true
    onNewChat?: () => void;       // 新建按钮点击回调，若不传则内部 navigate('/')
    newChatLabel?: string;        // 自定义新建按钮文本
    onProfileChanged?: () => void;// Profile切换后的回调
}

export default function TopBar({
                                   title,
                                   showNewChat = true,
                                   onNewChat,
                                   newChatLabel,
                                   onProfileChanged,
                               }: TopBarProps) {
    const { t, i18n } = useTranslation();
    const navigate = useNavigate();
    const [showLang, setShowLang] = useState(false);
    const [showProfileModal, setShowProfileModal] = useState(false);

    const handleNewChat = () => {
        if (onNewChat) {
            onNewChat();
        } else {
            navigate('/chat');
        }
    };

    return (
        <header className="h-16 px-6 bg-white/80 border-b border-[#e2e8f0]/60 flex items-center justify-between flex-shrink-0">
            {/* 左侧区域：标题 + 新建按钮 */}
            <div className="flex items-center gap-6">
                <h2 className="text-xl font-semibold text-[#0f172a] tracking-[-0.5px] font-['Inter']">
                    {title || t('header.chatFlow')}
                </h2>
                {showNewChat && (
                    <button
                        onClick={handleNewChat}
                        className="text-sm font-semibold text-[#0284c7] hover:text-[#00639d] transition font-['Inter']"
                    >
                        {newChatLabel || t('header.newChat')}
                    </button>
                )}
            </div>

            {/* 右侧区域：语言切换 + 用户头像 */}
            <div className="flex items-center gap-4">
                {/* 语言下拉 */}
                <div className="relative">
                    <button
                        onClick={() => setShowLang(!showLang)}
                        className="text-sm font-medium text-[#64748b] hover:text-[#0284c7] transition font-['Inter']"
                    >
                        {t('header.language')}
                    </button>
                    {showLang && (
                        <div className="absolute right-0 top-8 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-50 min-w-[100px]">
                            <button
                                onClick={() => { i18n.changeLanguage('en'); setShowLang(false); }}
                                className={`block w-full text-left px-4 py-2 text-sm hover:bg-gray-50 ${
                                    i18n.language === 'en' ? 'text-[#0284c7] font-medium' : 'text-gray-700'
                                }`}
                            >
                                {t('language.en')}
                            </button>
                            <button
                                onClick={() => { i18n.changeLanguage('zh'); setShowLang(false); }}
                                className={`block w-full text-left px-4 py-2 text-sm hover:bg-gray-50 ${
                                    i18n.language === 'zh' ? 'text-[#0284c7] font-medium' : 'text-gray-700'
                                }`}
                            >
                                {t('language.zh')}
                            </button>
                        </div>
                    )}
                </div>

                {/* 用户头像 */}
                <button
                    onClick={() => setShowProfileModal(true)}
                    className="w-8 h-8 bg-[#e6e9e9] rounded-full flex items-center justify-center focus:outline-none hover:ring-2 hover:ring-[#00639d] transition"
                >                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M3.8501 15.1001C4.7002 14.45 5.6499 13.9375 6.7002 13.5625C7.75 13.1875 8.8501 13 10 13C11.1499 13 12.25 13.1875 13.2998 13.5625C14.3501 13.9375 15.2998 14.45 16.1499 15.1001C16.7334 14.4167 17.1875 13.6418 17.5127 12.7751C17.8374 11.9084 18 10.9834 18 10C18 7.78345 17.2207 5.896 15.6626 4.33765C14.1045 2.7793 12.2168 2 10 2C7.7832 2 5.896 2.7793 4.3374 4.33765C2.7793 5.896 2 7.78345 2 10C2 10.9834 2.1626 11.9084 2.4873 12.7751C2.8125 13.6418 3.2666 14.4167 3.8501 15.1001ZM10 11C9.0166 11 8.1875 10.6626 7.5127 9.98755C6.8374 9.3125 6.5 8.4834 6.5 7.5C6.5 6.51685 6.8374 5.6875 7.5127 5.01245C8.1875 4.33765 9.0166 4 10 4C10.9834 4 11.8125 4.33765 12.4873 5.01245C13.1626 5.6875 13.5 6.51685 13.5 7.5C13.5 8.4834 13.1626 9.3125 12.4873 9.98755C11.8125 10.6626 10.9834 11 10 11Z" fill="#475569"/>
                    </svg>
                </button>
            </div>
            {/* Profile设置 弹窗 */}
            <ProfileSettings isOpen={showProfileModal} onClose={() => setShowProfileModal(false)} onProfileChanged={onProfileChanged} />
        </header>
    );
}
