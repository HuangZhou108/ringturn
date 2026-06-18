// frontend/src/components/UserManualModal.tsx
import { useTranslation } from 'react-i18next';

interface UserManualModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export default function UserManualModal({ isOpen, onClose }: UserManualModalProps) {
    const { t } = useTranslation();
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
            <div
                className="bg-white rounded-2xl shadow-xl w-[480px] max-w-[90%] max-h-[80vh] flex flex-col animate-in fade-in zoom-in duration-200"
                onClick={(e) => e.stopPropagation()}
            >
                {/* 标题栏 */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
                    <h3 className="text-lg font-semibold text-gray-800">{t('userManual.title')}</h3>
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-gray-600 transition"
                    >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M18 6L6 18M6 6l12 12" />
                        </svg>
                    </button>
                </div>

                {/* 内容区域 */}
                <div className="flex-1 overflow-y-auto p-6">
                    <div className="text-center text-gray-500 text-sm leading-relaxed">
                        {t('manual.content')}
                    </div>
                </div>

                {/* 底部按钮（可选） */}
                <div className="px-6 py-4 border-t border-gray-100 flex justify-end">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 bg-[#00639d] text-white rounded-lg hover:bg-[#005288] transition"
                    >
                        {t('userManual.close')}
                    </button>
                </div>
            </div>
        </div>
    );
}
