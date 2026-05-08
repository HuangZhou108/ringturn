// src/pages/home.tsx
import {useRef, useState} from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar';

function Home() {
    const navigate = useNavigate()
    const { t, i18n } = useTranslation()
    const [showLang, setShowLang] = useState(false)
    const [inputValue, setInputValue] = useState('')
    const fileInputRef = useRef<HTMLInputElement>(null)
    const [audioFile, setAudioFile] = useState<File | null>(null)
    const [audioFileId, setAudioFileId] = useState<string | null>(null)
    const [uploadError, setUploadError] = useState<string | null>(null)
    const [uploadSuccess, setUploadSuccess] = useState<string | null>(null)
    const [uploadProgress, setUploadProgress] = useState<number>(0)
    const [isUploading, setIsUploading] = useState(false)

    // 参数设置
    const [instrument, setInstrument] = useState('Acoustic Piano')
    const [tempo, setTempo] = useState('120')
    const [duration, setDuration] = useState('180')
    const [showInstrument, setShowInstrument] = useState(false)
    const instruments = ['Acoustic Piano', 'Violin']

    const handleSend = () => {
        if (!inputValue.trim()) return
        navigate('/chat', {
            state: {
                userMessage: inputValue.trim(),
                audioFileId: audioFileId,
                instrument,
                tempo,
                duration,
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
        setUploadSuccess(null)
        setIsUploading(true)
        setUploadProgress(0)

        try {
            console.log('开始上传文件:', file.name)
            // 模拟进度（因为 fetch 不提供上传进度，需要 XMLHttpRequest）
            const progressInterval = setInterval(() => {
                setUploadProgress(prev => Math.min(prev + 10, 90))
            }, 200)

            const res = await api.uploadFile(file)
            clearInterval(progressInterval)
            setUploadProgress(100)

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
        } finally {
            setIsUploading(false)
            setTimeout(() => setUploadProgress(0), 500)
        }
    }

    return (
        <div className="flex flex-col h-screen bg-[#cfe9ff] font-['Inter'] page-enter">
            {/*  顶部导航栏： 使用统一组件 */}
            <TopBar />

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
                        <h3 className="text-3xl font-extrabold leading-tight font-['Manrope']  welcome-text">
                            <span className="text-[#2f3334]">{t('welcome.titleBefore')}</span>
                            <span className="text-[#00639d]">{t('welcome.titleHighlight')}</span>
                            {t('welcome.titleAfter') && <span className="text-[#2f3334]">{t('welcome.titleAfter')}</span>}
                        </h3>

                        {/* 副标题 */}
                        <div className="max-w-[512px]  welcome-subtitle">
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
                    {isUploading && (
                        <div className="w-[691px] mt-2 self-center">
                            <div className="flex items-center justify-between mb-1">
                                <span className="text-sm text-blue-600">正在上传...</span>
                                <span className="text-sm text-blue-600">{uploadProgress}%</span>
                            </div>
                            <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-blue-500 rounded-full transition-all duration-200"
                                    style={{ width: `${uploadProgress}%` }}
                                />
                            </div>
                        </div>
                    )}
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
                            {/* Instrument 下拉 */}
                            <div className="relative mr-2">
                                <button
                                    onClick={() => setShowInstrument(!showInstrument)}
                                    className="px-3 py-1.5 bg-white border border-gray-200 rounded-lg text-sm text-gray-700 hover:bg-gray-50 transition"
                                >
                                    {instrument}
                                </button>
                                {showInstrument && (
                                    <div className="absolute bottom-full left-0 mb-1 w-40 bg-white border border-gray-200 rounded-lg shadow-lg z-20">
                                        {instruments.map((inst) => (
                                            <button
                                                key={inst}
                                                onClick={() => { setInstrument(inst); setShowInstrument(false) }}
                                                className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 first:rounded-t-lg last:rounded-b-lg ${instrument === inst ? 'text-[#0284c7] font-medium' : 'text-gray-700'}`}
                                            >
                                                {inst}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                            {/* Tempo 输入 */}
                            <div className="flex items-center gap-1 mr-2">
                                <span className="text-xs text-gray-500">BPM:</span>
                                <input
                                    type="number"
                                    value={tempo}
                                    onChange={(e) => setTempo(e.target.value)}
                                    className="w-14 px-2 py-1 bg-white border border-gray-200 rounded text-sm text-gray-700 outline-none"
                                    min="40"
                                    max="240"
                                />
                            </div>
                            {/* Duration 输入 */}
                            <div className="flex items-center gap-1 mr-3">
                                <span className="text-xs text-gray-500">秒:</span>
                                <input
                                    type="number"
                                    value={duration}
                                    onChange={(e) => setDuration(e.target.value)}
                                    className="w-14 px-2 py-1 bg-white border border-gray-200 rounded text-sm text-gray-700 outline-none"
                                    min="10"
                                    max="600"
                                />
                            </div>
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

export default Home
