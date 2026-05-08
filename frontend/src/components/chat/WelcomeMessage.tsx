// src/components/chat/WelcomeMessage.tsx
import { useTranslation } from 'react-i18next';
import { motion } from 'framer-motion';

export default function WelcomeMessage() {
    const { t } = useTranslation();
    return (
        <motion.div
            layoutId="welcome"
            className="w-[600px] py-5 flex flex-col gap-y-2 relative overflow-visible"
            transition={{ type: 'spring', duration: 0.6 }}
        >
            {/* 背景音符图标 */}
            <div className="absolute -left-[18px] top-[15px] opacity-10 pointer-events-none">
                <svg width="60" height="90" viewBox="0 0 60 90" fill="none">
                    <path d="M20 90C14.5 90 9.7915 88.0417 5.875 84.125C1.9585 80.2083 0 75.5 0 70C0 64.5 1.9585 59.7917 5.875 55.875C9.7915 51.9583 14.5 50 20 50C21.9167 50 23.6875 50.2292 25.3125 50.6875C26.9375 51.1458 28.5 51.8333 30 52.75V0H60V20H40V70C40 75.5 38.0417 80.2083 34.125 84.125C30.2083 88.0417 25.5 90 20 90Z" fill="#00639d"/>
                </svg>
            </div>
            <h3 className="text-3xl font-extrabold leading-tight font-['Manrope'] welcome-text">
                <span className="text-[#2f3334]">{t('welcome.titleBefore')}</span>
                <span className="text-[#00639d]">{t('welcome.titleHighlight')}</span>
                {t('welcome.titleAfter') && <span className="text-[#2f3334]">{t('welcome.titleAfter')}</span>}
            </h3>
            <div className="welcome-subtitle">
                <p className="text-base text-[#5b6061] leading-relaxed font-['Inter']">
                    {t('welcome.subtitle')}
                </p>
            </div>
        </motion.div>
    );
}
