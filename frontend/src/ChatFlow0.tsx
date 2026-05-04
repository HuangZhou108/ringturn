import {useRef, useState} from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { api } from './api'

function ChatFlow0() {
    const navigate = useNavigate()
    const { t, i18n } = useTranslation()
    const [showLang, setShowLang] = useState(false)
    const [inputValue, setInputValue] = useState('')
    const fileInputRef = useRef<HTMLInputElement>(null)
    const [audioFile, setAudioFile] = useState<File | null>(null)
    const [audioFileId, setAudioFileId] = useState<string | null>(null)
    const [uploadError, setUploadError] = useState<string | null>(null)
    const [uploadSuccess, setUploadSuccess] = useState<string | null>(null)

    const handleSend = () => {
        if (!inputValue.trim()) return
        navigate('/chat', {
            state: {
                userMessage: inputValue.trim(),
                audioFileId: audioFileId,
            }
        })
    }

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return

        const validFormats = ['mp3', 'wav', 'flac', 'm4a', 'ogg']
        const ext = file.name.split('.').pop()?.toLowerCase()
        if (!ext || !validFormats.includes(ext)) {
            setUploadError(`不支持的格式: .${ext}，支持: ${validFormats.join(', ')}`)
            return
        }
        if (file.size > 50 * 1024 * 1024) {
            setUploadError('文件过大，最大支持 50MB')
            return
        }

        setAudioFile(file)
        setUploadError(null)
        try {
            console.log('开始上传文件:', file.name)
            const res = await api.uploadFile(file)
            console.log('上传响应:', res)
            if (res.code === 200) {
                setAudioFileId(res.data.file_id)
                setUploadSuccess(`文件已上传: ${res.data.filename} (${(res.data.file_size).toFixed(2)} MB)`)
                setUploadError(null)
            } else {
                setUploadError(res.message || '文件上传失败')
                setUploadSuccess(null)
            }
        } catch (err) {
            console.error('上传失败:', err)
            setUploadError(`上传失败: ${err instanceof Error ? err.message : '未知错误'}`)
            setUploadSuccess(null)
        }
    }

    return (
        <div className="flex flex-col h-screen bg-[#cfe9ff] font-['Inter']">
            {/* ========== 顶部导航栏 ========== */}
            <header className="flex flex-row-reverse items-center justify-between h-16 px-6 bg-white/80 border border-[#e2e8f0]/60 flex-shrink-0">
                {/* 右侧图标组 */}
                <div className="flex flex-row-reverse items-center gap-4">
                    {/* 用户头像 */}
                    <div className="w-8 h-8 bg-[#e6e9e9] rounded-full flex items-center justify-center">
                        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M3.8501 15.1001C4.7002 14.45 5.6499 13.9375 6.7002 13.5625C7.75 13.1875 8.8501 13 10 13C11.1499 13 12.25 13.1875 13.2998 13.5625C14.3501 13.9375 15.2998 14.45 16.1499 15.1001C16.7334 14.4167 17.1875 13.6418 17.5127 12.7751C17.8374 11.9084 18 10.9834 18 10C18 7.78345 17.2207 5.896 15.6626 4.33765C14.1045 2.7793 12.2168 2 10 2C7.7832 2 5.896 2.7793 4.3374 4.33765C2.7793 5.896 2 7.78345 2 10C2 10.9834 2.1626 11.9084 2.4873 12.7751C2.8125 13.6418 3.2666 14.4167 3.8501 15.1001ZM10 11C9.0166 11 8.1875 10.6626 7.5127 9.98755C6.8374 9.3125 6.5 8.4834 6.5 7.5C6.5 6.51685 6.8374 5.6875 7.5127 5.01245C8.1875 4.33765 9.0166 4 10 4C10.9834 4 11.8125 4.33765 12.4873 5.01245C13.1626 5.6875 13.5 6.51685 13.5 7.5C13.5 8.4834 13.1626 9.3125 12.4873 9.98755C11.8125 10.6626 10.9834 11 10 11ZM10 20C8.6167 20 7.3164 19.7375 6.1001 19.2126C4.8833 18.6875 3.8252 17.9751 2.9248 17.075C2.0249 16.175 1.3125 15.1167 0.7876 13.9001C0.2627 12.6833 0 11.3833 0 10C0 8.6167 0.2627 7.31665 0.7876 6.1001C1.3125 4.8833 2.0249 3.82495 2.9248 2.92505C3.8252 2.02515 4.8833 1.3125 6.1001 0.787598C7.3164 0.262451 8.6167 0 10 0C11.3833 0 12.6836 0.262451 13.8999 0.787598C15.1167 1.3125 16.1748 2.02515 17.0752 2.92505C17.9751 3.82495 18.6875 4.8833 19.2124 6.1001C19.7373 7.31665 20 8.6167 20 10C20 11.3833 19.7373 12.6833 19.2124 13.9001C18.6875 15.1167 17.9751 16.175 17.0752 17.075C16.1748 17.9751 15.1167 18.6875 13.8999 19.2126C12.6836 19.7375 11.3833 20 10 20ZM10 18C10.8833 18 11.7168 17.8708 12.5 17.6125C13.2832 17.3542 14 16.9834 14.6499 16.5C14 16.0168 13.2832 15.6458 12.5 15.3875C11.7168 15.1292 10.8833 15 10 15C9.1167 15 8.2832 15.1292 7.5 15.3875C6.7168 15.6458 6 16.0168 5.3501 16.5C6 16.9834 6.7168 17.3542 7.5 17.6125C8.2832 17.8708 9.1167 18 10 18ZM10 9C10.4336 9 10.792 8.8584 11.0752 8.57495C11.3584 8.29175 11.5 7.93335 11.5 7.5C11.5 7.06665 11.3584 6.7085 11.0752 6.42505C10.792 6.14185 10.4336 6 10 6C9.5664 6 9.2085 6.14185 8.9248 6.42505C8.6416 6.7085 8.5 7.06665 8.5 7.5C8.5 7.93335 8.6416 8.29175 8.9248 8.57495C9.2085 8.8584 9.5664 9 10 9Z" fill="#475569"/>
                        </svg>
                    </div>
                    {/* Language 下拉 */}
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
                                    onClick={() => { i18n.changeLanguage('en'); setShowLang(false) }}
                                    className={`block w-full text-left px-4 py-2 text-sm hover:bg-gray-50 ${i18n.language === 'en' ? 'text-[#0284c7] font-medium' : 'text-gray-700'}`}
                                >
                                    English
                                </button>
                                <button
                                    onClick={() => { i18n.changeLanguage('zh'); setShowLang(false) }}
                                    className={`block w-full text-left px-4 py-2 text-sm hover:bg-gray-50 ${i18n.language === 'zh' ? 'text-[#0284c7] font-medium' : 'text-gray-700'}`}
                                >
                                    中文
                                </button>
                            </div>
                        )}
                    </div>
                </div>

                {/* 左侧标题组 */}
                <div className="flex flex-row-reverse items-center gap-6">
                    {/* New Chat 按钮 */}
                    <button className="text-sm font-semibold text-[#0284c7] font-['Inter']">
                        {t('header.newChat')}
                    </button>
                    {/* Chat Flow 标题 */}
                    <h2 className="text-xl font-semibold text-[#0f172a] tracking-[-0.5px] font-['Inter']">
                        {t('header.chatFlow')}
                    </h2>
                </div>
            </header>

            {/* ========== 聊天区域 ========== */}
            <main className="flex-1 flex items-center justify-center overflow-hidden bg-[#cfe9ff] min-w-[984px]">
                <div className="w-full min-w-[984px] flex flex-col-reverse items-center justify-start px-[192px] pb-16 min-h-[260px]">
                    {/* 欢迎区域 */}
                    <div className="w-[600px] py-5 flex flex-col gap-y-2 relative">
                        {/* 背景装饰音符图标 */}
                        <div className="absolute -left-[18px] top-[15px] opacity-10 pointer-events-none">
                            <svg width="60" height="90" viewBox="0 0 60 90" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M20 90C14.5 90 9.7915 88.0416 5.875 84.1249C1.9585 80.2081 0 75.5 0 70C0 64.5 1.9585 59.7916 5.875 55.8749C9.7915 51.9581 14.5 50 20 50C21.917 50 23.6875 50.2291 25.3125 50.6874C26.9375 51.1456 28.5 51.8331 30 52.7499V0H60V20H40V70C40 75.5 38.0417 80.2081 34.125 84.1249C30.208 88.0416 25.5 90 20 90Z" fill="#00639d"/>
                            </svg>
                        </div>

                        {/* 标题 */}
                        <h3 className="text-3xl font-extrabold leading-tight font-['Manrope']">
                            <span className="text-[#2f3334]">{t('welcome.titleBefore')}</span>
                            <span className="text-[#00639d]">{t('welcome.titleHighlight')}</span>
                            {t('welcome.titleAfter') && <span className="text-[#2f3334]">{t('welcome.titleAfter')}</span>}
                        </h3>

                        {/* 副标题 */}
                        <div className="max-w-[512px]">
                            <p className="text-base text-[#5b6061] leading-relaxed font-['Inter']">
                                {t('welcome.subtitle')}
                            </p>
                        </div>
                    </div>
                </div>
            </main>

            {/* ========== 底部浮动区域 ========== */}
            <div className="flex flex-col-reverse items-center px-4 mb-[240px] flex-shrink-0">
                {/* 输入栏容器 */}
                <div className="w-[768px] bg-[#cfe9ff] border-2 border-[#f0f9ff] rounded-3xl px-2.5 py-2.5 flex flex-col justify-evenly">
                    {/* 多行文本输入框 */}
                    <div className="min-w-[715px] h-[169px] flex flex-col-reverse justify-around px-3 py-2.5 flex-1">
                        <div className="flex-1 min-h-[25px]">
                            <textarea
                                placeholder={t('input.placeholder')}
                                value={inputValue}
                                onChange={(e) => setInputValue(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && !e.shiftKey) {
                                        e.preventDefault()
                                        handleSend()
                                    }
                                }}
                                className="w-full h-full bg-transparent outline-none resize-none text-xl text-[#94a3b8] placeholder-[#94a3b8] leading-tight"
                            />
                        </div>
                    </div>

                    {/* 上传状态显示 */}
                    {uploadError && (
                        <div className="w-[691px] h-[30px] mt-2 flex items-center px-4 bg-red-50 border border-red-200 rounded-lg self-center">
                            <span className="text-sm text-red-600">{uploadError}</span>
                        </div>
                    )}
                    {uploadSuccess && (
                        <div className="w-[691px] h-[30px] mt-2 flex items-center px-4 bg-green-50 border border-green-200 rounded-lg self-center">
                            <span className="text-sm text-green-600">{uploadSuccess}</span>
                        </div>
                    )}

                    {/* 按钮容器 */}
                    <div className="w-[691px] h-[41px] mt-[30px] mb-10 flex items-center justify-between bg-white/50 self-center rounded-lg px-4">
                        {/* 左侧按钮组 */}
                        <div className="flex flex-row-reverse items-center gap-1">
                            {/* 语音按钮 */}
                            <button className="w-10 h-10 bg-[#f0f9ff]/65 rounded-2xl flex items-center justify-center shadow-[inset_0px_2px_4px_0px_#0000000D]">
                                <svg width="13" height="20" viewBox="0 0 13 20" fill="none">
                                    <path d="M12.5 13.75C12.5 15.48315 11.8916 16.95801 10.67505 18.1748C9.4585 19.39136 7.9834 20 6.25 20C4.5166 20 3.0415 19.39136 1.82495 18.1748C0.608398 16.95801 0 15.48315 0 13.75V4.5C0 3.25 0.4375 2.1875 1.3125 1.3125C2.1875 0.4375 3.25 0 4.5 0C5.75 0 6.8125 0.4375 7.6875 1.3125C8.5625 2.1875 9 3.25 9 4.5V13.25C9 14.0166 8.7334 14.6665 8.19995 15.19995C7.6665 15.7334 7.0166 16 6.25 16C5.4834 16 4.8335 15.7334 4.30005 15.19995C3.7666 14.6665 3.5 14.0166 3.5 13.25V4H5.5V13.25C5.5 13.4668 5.5708 13.6455 5.7124 13.78735C5.854 13.92896 6.0332 14 6.25 14C6.4668 14 6.646 13.92896 6.7876 13.78735C6.9292 13.6455 7 13.4668 7 13.25V4.5C6.9834 3.8 6.73755 3.20825 6.26245 2.72485C5.7876 2.24145 5.19995 2 4.5 2C3.80005 2 3.2085 2.24145 2.7251 2.72485C2.2417 3.20825 2 3.8 2 4.5V13.75C1.9834 14.93335 2.3916 15.9375 3.2251 16.7622C4.05835 17.5872 5.06665 18 6.25 18C7.4165 18 8.4082 17.5872 9.2251 16.7622C10.0417 15.9375 10.4668 14.93335 10.5 13.75V4H12.5V13.75H12.5V20H10.5V20H6.25H12.5Z" fill="#94a3b8"/>
                                </svg>
                            </button>
                            {/* 附件按钮 */}
                            <button
                                onClick={() => fileInputRef.current?.click()}
                                className="w-10 h-10 bg-[#f0f9ff] rounded-2xl flex items-center justify-center shadow-[inset_0px_2px_4px_0px_#0000000D] hover:bg-[#e0f2fe] transition"
                            >
                                <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                                    <path d="M8 17.99976L8 11.99976L10 11.99976L10 13.99976L18 13.99976L18 15.99976L10 15.99976L10 17.99976L8 17.99976ZM0 15.99976L0 13.99976L6 13.99976L6 15.99976L0 15.99976ZM4 11.99976L4 9.99976L0 9.99976L0 7.99976L4 7.99976L4 5.99976L6 5.99976L6 11.99976L4 11.99976ZM8 9.99976L8 7.99976L18 7.99976L18 9.99976L8 9.99976ZM12 5.99976L12 -0.00024L14 -0.00024L14 1.99976L18 1.99976L18 3.99976L14 3.99976L14 5.99976L12 5.99976ZM0 3.99976L0 1.99976L10 1.99976L10 3.99976L0 3.99976Z" fill="#00639d"/>
                                </svg>
                            </button>
                            <input ref={fileInputRef} type="file" accept=".mp3,.wav,.flac,.m4a,.ogg" onChange={handleFileSelect} className="hidden" />
                        </div>
                        {/* 发送按钮 */}
                        <button
                            onClick={handleSend}
                            className="w-10 h-10 bg-[#00639d] rounded-2xl flex items-center justify-center self-center shadow-[0px_10px_15px_-3px_#00639d4D,0px_4px_6px_-4px_#00639d4D] hover:bg-[#005288] transition"
                        >
                            <svg width="19" height="16" viewBox="0 0 19 16" fill="none">
                                <path d="M0 16V0L19 8L0 16ZM2 13L13.85 8L2 3V6.5L8 8L2 9.5V13Z" fill="#f7f9ff"/>
                            </svg>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    )
}

export default ChatFlow0