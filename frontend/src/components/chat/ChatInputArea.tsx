// src/components/chat/ChatInputArea.tsx
import { useTranslation } from 'react-i18next';
import { useState, useCallback } from 'react';
import TrackParams from './TrackParams';

interface ChatInputAreaProps {
    inputValue: string;
    setInputValue: (val: string) => void;
    handleSend: () => void;
    fileInputRef: React.RefObject<HTMLInputElement>;
    handleFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void;
    // 参数
    instrument: string;
    setInstrument: (val: string) => void;
    tempo: string;
    setTempo: (val: string) => void;
    audioDuration?: number;
    duration: string;
    setDuration: (val: string) => void;
    filename: string;
    setFilename: (val: string) => void;
    // 上传状态
    isUploading: boolean;
    uploadProgress: number;
    uploadError: string | null;
    uploadSuccess: string | null;
    // 布局模式
    mode?: 'home' | 'chat';   // home: 大输入框+透明底边；chat: 紧凑固定底部
    // 任务终止判断
    isProcessing?: boolean;
    onCancel?: () => void;
    // 反馈任务
    feedbackMode?: boolean;
    setFeedbackMode?: (val: boolean) => void;
    selectedParentTaskId?: string | null;
    setSelectedParentTaskId?: (id: string | null) => void;
    availableParentTasks?: { task_id: string; user_request: string }[];
    loadCompletedTasks?: () => Promise<void>;
}

export default function ChatInputArea({
                                          inputValue,
                                          setInputValue,
                                          handleSend,
                                          fileInputRef,
                                          handleFileSelect,
                                          instrument,
                                          setInstrument,
                                          tempo,
                                          setTempo,
                                          audioDuration,
                                          duration,
                                          setDuration,
                                          filename,
                                          setFilename,
                                          isUploading,
                                          uploadProgress,
                                          uploadError,
                                          uploadSuccess,
                                          mode = 'chat',
                                          isProcessing,
                                          onCancel,
                                          feedbackMode = false,
                                          setFeedbackMode,
                                          selectedParentTaskId,
                                          setSelectedParentTaskId,
                                          availableParentTasks = [],
                                          loadCompletedTasks,
                                      }: ChatInputAreaProps) {
    const { t } = useTranslation();
    const [showParams, setShowParams] = useState(false); // chat模式下参数面板折叠

    // 参数图标
    const OpenParaIcon = (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M8 17.99976L8 11.99976L10 11.99976L10 13.99976L18 13.99976L18 15.99976L10 15.99976L10 17.99976L8 17.99976ZM0 15.99976L0 13.99976L6 13.99976L6 15.99976L0 15.99976ZM4 11.99976L4 9.99976L0 9.99976L0 7.99976L4 7.99976L4 5.99976L6 5.99976L6 11.99976L4 11.99976ZM8 9.99976L8 7.99976L18 7.99976L18 9.99976L8 9.99976ZM12 5.99976L12 -0.00024L14 -0.00024L14 1.99976L18 1.99976L18 3.99976L14 3.99976L14 5.99976L12 5.99976ZM0 3.99976L0 1.99976L10 1.99976L10 3.99976L0 3.99976Z" fill="#00639d"/>
        </svg>
    );

    // 上传文件图标
    const AttachmentIcon = (
        <svg width="13" height="20" viewBox="0 0 13 20" fill="none">
            <path d="M12.5 13.75C12.5 15.48315 11.8916 16.95801 10.67505 18.1748C9.4585 19.39136 7.9834 20 6.25 20C4.5166 20 3.0415 19.39136 1.82495 18.1748C0.608398 16.95801 0 15.48315 0 13.75V4.5C0 3.25 0.4375 2.1875 1.3125 1.3125C2.1875 0.4375 3.25 0 4.5 0C5.75 0 6.8125 0.4375 7.6875 1.3125C8.5625 2.1875 9 3.25 9 4.5V13.25C9 14.0166 8.7334 14.6665 8.19995 15.19995C7.6665 15.7334 7.0166 16 6.25 16C5.4834 16 4.8335 15.7334 4.30005 15.19995C3.7666 14.6665 3.5 14.0166 3.5 13.25V4H5.5V13.25C5.5 13.4668 5.5708 13.6455 5.7124 13.78735C5.854 13.92896 6.0332 14 6.25 14C6.4668 14 6.646 13.92896 6.7876 13.78735C6.9292 13.6455 7 13.4668 7 13.25V4.5C6.9834 3.8 6.73755 3.20825 6.26245 2.72485C5.7876 2.24145 5.19995 2 4.5 2C3.80005 2 3.2085 2.24145 2.7251 2.72485C2.2417 3.20825 2 3.8 2 4.5V13.75C1.9834 14.93335 2.3916 15.9375 3.2251 16.7622C4.05835 17.5872 5.06665 18 6.25 18C7.4165 18 8.4082 17.5872 9.2251 16.7622C10.0417 15.9375 10.4668 14.93335 10.5 13.75V4H12.5V13.75H12.5V20H10.5V20H6.25H12.5Z" fill="#94a3b8"/>
        </svg>
    );

    // 用于参数框自动关闭
    const wrappedHandleSend = () => {
        handleSend();
        if (mode === 'chat') {
            setShowParams(false);
        }
    };

    // ==================== Home 模式 ====================
    if (mode === 'home') {
        // ==================== Home 模式（完全复刻原 Home 页面输入区域） ====================
        return (
            <div className="flex flex-col-reverse items-center px-4 mb-[240px] flex-shrink-0 relative">
                {/* 参数面板（折叠，悬浮，不影响布局，带滑入滑出动画） */}
                <div
                    className={`absolute left-0 right-0 mx-auto transition-all duration-300 ease-out z-20 ${
                        showParams ? 'opacity-100 translate-y-0 visible' : 'opacity-0 -translate-y-4 invisible'
                    }`}
                    style={{ top: 'calc(100% + 2px)', width: 'min(100% - 2rem, 768px)' }}
                >
                    <TrackParams
                        instrument={instrument}
                        setInstrument={setInstrument}
                        tempo={tempo}
                        setTempo={setTempo}
                        audioDuration={audioDuration}
                        duration={duration}
                        setDuration={setDuration}
                        filename={filename}
                        setFilename={setFilename}
                    />
                </div>
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
                                        e.preventDefault();
                                        handleSend();
                                    }
                                }}
                                className="w-full h-full bg-transparent outline-none resize-none text-xl text-[#94a3b8] placeholder-[#94a3b8] leading-tight"
                            />
                        </div>
                    </div>

                    {/*/!* 上传状态显示（已删除） *!/*/}
                    {/*{(isUploading || uploadError || uploadSuccess) && (*/}
                    {/*    <div className="w-[691px] mt-2 self-center">*/}
                    {/*        {isUploading && (*/}
                    {/*            <>*/}
                    {/*                <div className="flex items-center justify-between mb-1">*/}
                    {/*                    <span className="text-sm text-blue-600">正在上传...</span>*/}
                    {/*                    <span className="text-sm text-blue-600">{uploadProgress}%</span>*/}
                    {/*                </div>*/}
                    {/*                <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">*/}
                    {/*                    <div className="h-full bg-blue-500 rounded-full transition-all duration-200" style={{ width: `${uploadProgress}%` }} />*/}
                    {/*                </div>*/}
                    {/*            </>*/}
                    {/*        )}*/}
                    {/*        {uploadError && (*/}
                    {/*            <div className="h-[30px] flex items-center px-4 bg-red-50 border border-red-200 rounded-lg">*/}
                    {/*                <span className="text-sm text-red-600">{uploadError}</span>*/}
                    {/*            </div>*/}
                    {/*        )}*/}
                    {/*        {uploadSuccess && (*/}
                    {/*            <div className="h-[30px] flex items-center px-4 bg-green-50 border border-green-200 rounded-lg">*/}
                    {/*                <span className="text-sm text-green-600">{uploadSuccess}</span>*/}
                    {/*            </div>*/}
                    {/*        )}*/}
                    {/*    </div>*/}
                    {/*)}*/}

                    {/* 按钮区域：直接放在对话框容器底部，左右分布 */}
                    <div className="flex items-center justify-between mt-[30px] mb-3 px-3">
                        {/* 左侧按钮组 */}
                        <div className="flex items-center gap-1">
                            <input ref={fileInputRef} type="file" accept=".mp3,.wav,.flac,.m4a,.ogg" onChange={handleFileSelect} className="hidden" />
                            {/* 参数开关按钮 */}
                            <button
                                onClick={() => setShowParams(!showParams)}
                                className="w-11 h-11 bg-[#f0f9ff] rounded-2xl flex items-center justify-center shadow-[inset_0px_2px_4px_0px_#0000000D] hover:bg-[#e0f2fe] transition"
                                title={t('chat.showParams') || '参数设置'}
                            >
                                {OpenParaIcon}
                            </button>
                            {/* 附件按钮 – 带高亮和 tooltip */}
                            <div className="relative group">
                                <button
                                    onClick={() => fileInputRef.current?.click()}
                                    className="flex items-center justify-center w-11 h-11 rounded-2xl transition hover:bg-gray-100"
                                >
                                    <svg
                                        width="13"
                                        height="20"
                                        viewBox="0 0 13 20"
                                        fill="none"
                                        className="transition-colors duration-200"
                                        style={{ fill: isUploading || uploadSuccess || uploadError ? '#3b82f6' : '#94a3b8' }}
                                    >
                                        <path d="M12.5 13.75C12.5 15.48315 11.8916 16.95801 10.67505 18.1748C9.4585 19.39136 7.9834 20 6.25 20C4.5166 20 3.0415 19.39136 1.82495 18.1748C0.608398 16.95801 0 15.48315 0 13.75V4.5C0 3.25 0.4375 2.1875 1.3125 1.3125C2.1875 0.4375 3.25 0 4.5 0C5.75 0 6.8125 0.4375 7.6875 1.3125C8.5625 2.1875 9 3.25 9 4.5V13.25C9 14.0166 8.7334 14.6665 8.19995 15.19995C7.6665 15.7334 7.0166 16 6.25 16C5.4834 16 4.8335 15.7334 4.30005 15.19995C3.7666 14.6665 3.5 14.0166 3.5 13.25V4H5.5V13.25C5.5 13.4668 5.5708 13.6455 5.7124 13.78735C5.854 13.92896 6.0332 14 6.25 14C6.4668 14 6.646 13.92896 6.7876 13.78735C6.9292 13.6455 7 13.4668 7 13.25V4.5C6.9834 3.8 6.73755 3.20825 6.26245 2.72485C5.7876 2.24145 5.19995 2 4.5 2C3.80005 2 3.2085 2.24145 2.7251 2.72485C2.2417 3.20825 2 3.8 2 4.5V13.75C1.9834 14.93335 2.3916 15.9375 3.2251 16.7622C4.05835 17.5872 5.06665 18 6.25 18C7.4165 18 8.4082 17.5872 9.2251 16.7622C10.0417 15.9375 10.4668 14.93335 10.5 13.75V4H12.5V13.75H12.5V20H10.5V20H6.25H12.5Z" />
                                    </svg>
                                </button>
                                {/* 自定义 Tooltip – 瞬间显示 */}
                                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-1.5 text-xs text-white bg-gray-800 rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none">
                                    {isUploading
                                        ? `正在上传... ${uploadProgress}%`
                                        : uploadSuccess || uploadError || '上传音频文件'}
                                </div>
                            </div>
                        </div>
                        {/* 右侧发送按钮 */}
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
        );
    }

    // ==================== Chat 模式 ====================
    return (
        <div className="w-full relative">
            {/*/!* 上传状态显示（已删除） *!/*/}
            {/*{(isUploading || uploadError || uploadSuccess) && (*/}
            {/*    <div className="mb-2 px-2 py-2 bg-[#f8fafc] rounded-xl border border-gray-100">*/}
            {/*        {isUploading && (*/}
            {/*            <div className="flex items-center gap-3">*/}
            {/*                <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />*/}
            {/*                <span className="text-sm text-gray-600">正在上传... {uploadProgress}%</span>*/}
            {/*            </div>*/}
            {/*        )}*/}
            {/*        {uploadError && (*/}
            {/*            <div className="flex items-center gap-2 text-red-600">*/}
            {/*                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">*/}
            {/*                    <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm-.75 4.75v4.5a.75.75 0 001.5 0v-4.5a.75.75 0 00-1.5 0zM8 10.5a.875.875 0 110-1.75.875.875 0 010 1.75z"/>*/}
            {/*                </svg>*/}
            {/*                <span className="text-sm">{uploadError}</span>*/}
            {/*            </div>*/}
            {/*        )}*/}
            {/*        {uploadSuccess && (*/}
            {/*            <div className="flex items-center gap-2 text-green-600">*/}
            {/*                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">*/}
            {/*                    <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 011.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z"/>*/}
            {/*                </svg>*/}
            {/*                <span className="text-sm">{uploadSuccess}</span>*/}
            {/*            </div>*/}
            {/*        )}*/}
            {/*    </div>*/}
            {/*)}*/}

            {/* 参数面板（折叠） */}
            <div
                className={`absolute left-0 w-full transition-all duration-300 ease-out z-20 ${
                    showParams ? 'opacity-100 translate-y-0 visible' : 'opacity-0 translate-y-4 invisible'
                }`}
                style={{ bottom: '100%' }}
            >
                <TrackParams
                    instrument={instrument}
                    setInstrument={setInstrument}
                    tempo={tempo}
                    setTempo={setTempo}
                    audioDuration={audioDuration}
                    duration={duration}
                    setDuration={setDuration}
                    filename={filename}
                    setFilename={setFilename}
                />
            </div>

            {/* 输入栏主体（保持原布局，无重做按钮） */}
            <div className="relative flex flex-row-reverse items-center gap-2 bg-white border border-[#e0f2fe] rounded-3xl px-2.5 py-2.5">
                {/* 发送按钮 */}
                <button
                    onClick={isProcessing ? onCancel : wrappedHandleSend}
                    className={`w-11 h-11 rounded-2xl flex items-center justify-center flex-shrink-0 transition ${
                        isProcessing
                            ? 'bg-red-500 hover:bg-red-600 shadow-[0_10px_15px_-3px_rgba(239,68,68,0.3)]'
                            : 'bg-[#00639d] hover:bg-[#005288] shadow-[0px_10px_15px_-3px_#00639d4D,0px_4px_6px_-4px_#00639d4D]'
                    }`}
                >
                    {isProcessing ? (
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
                            <rect x="4" y="4" width="16" height="16" rx="2" />
                        </svg>
                    ) : (
                        <svg width="19" height="16" viewBox="0 0 19 16" fill="none">
                            <path d="M0 16V0L19 8L0 16ZM2 13L13.85 8L2 3V6.5L8 8L2 9.5V13Z" fill="#f7f9ff"/>
                        </svg>
                    )}
                </button>

                {/* 文本输入框 */}
                <div className="flex-1 px-3 py-2.5 min-h-[39px] min-w-0">
                    <textarea
                        placeholder={t('input.placeholder')}
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        disabled={isProcessing}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                wrappedHandleSend();
                            }
                        }}
                        className="w-full bg-transparent outline-none resize-none text-[15px] text-gray-700 placeholder-[#94a3b8] leading-tight"
                        rows={1}
                    />
                </div>

                <div className="w-px h-8 bg-[#f1f5f9] mx-1 flex-shrink-0"></div>

                <div className="flex flex-row-reverse items-center gap-4 px-1 flex-shrink-0">
                    {/* 附件按钮 – 修改后带高亮和 tooltip */}
                    <div className="relative group">
                        <button
                            onClick={() => {
                                if (feedbackMode) {
                                    alert('反馈模式下不可上传文件');
                                    return;
                                }
                                if (!fileInputRef.current) {
                                    console.error('[ChatInputArea] fileInputRef is null!')
                                    return
                                }
                                fileInputRef.current.click()
                            }}
                            className="flex items-center justify-center w-11 h-11 rounded-2xl transition hover:bg-gray-100"
                        >
                            <svg
                                width="13"
                                height="20"
                                viewBox="0 0 13 20"
                                fill="none"
                                className="transition-colors duration-200"
                                style={{ fill: isUploading || uploadSuccess || uploadError ? '#3b82f6' : '#94a3b8' }}
                            >
                                <path d="M12.5 13.75C12.5 15.48315 11.8916 16.95801 10.67505 18.1748C9.4585 19.39136 7.9834 20 6.25 20C4.5166 20 3.0415 19.39136 1.82495 18.1748C0.608398 16.95801 0 15.48315 0 13.75V4.5C0 3.25 0.4375 2.1875 1.3125 1.3125C2.1875 0.4375 3.25 0 4.5 0C5.75 0 6.8125 0.4375 7.6875 1.3125C8.5625 2.1875 9 3.25 9 4.5V13.25C9 14.0166 8.7334 14.6665 8.19995 15.19995C7.6665 15.7334 7.0166 16 6.25 16C5.4834 16 4.8335 15.7334 4.30005 15.19995C3.7666 14.6665 3.5 14.0166 3.5 13.25V4H5.5V13.25C5.5 13.4668 5.5708 13.6455 5.7124 13.78735C5.854 13.92896 6.0332 14 6.25 14C6.4668 14 6.646 13.92896 6.7876 13.78735C6.9292 13.6455 7 13.4668 7 13.25V4.5C6.9834 3.8 6.73755 3.20825 6.26245 2.72485C5.7876 2.24145 5.19995 2 4.5 2C3.80005 2 3.2085 2.24145 2.7251 2.72485C2.2417 3.20825 2 3.8 2 4.5V13.75C1.9834 14.93335 2.3916 15.9375 3.2251 16.7622C4.05835 17.5872 5.06665 18 6.25 18C7.4165 18 8.4082 17.5872 9.2251 16.7622C10.0417 15.9375 10.4668 14.93335 10.5 13.75V4H12.5V13.75H12.5V20H10.5V20H6.25H12.5Z" />
                            </svg>
                        </button>
                        {/* 自定义 Tooltip – 瞬间显示 */}
                        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-1.5 text-xs text-white bg-gray-800 rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity duration-150 pointer-events-none">
                            {isUploading
                                ? `正在上传... ${uploadProgress}%`
                                : uploadSuccess || uploadError || '上传音频文件'}
                        </div>
                    </div>

                    {/* 参数开关按钮 */}
                    <button
                        onClick={() => setShowParams(!showParams)}
                        className="w-11 h-11 bg-[#f0f9ff] rounded-2xl flex items-center justify-center shadow-[inset_0px_2px_4px_0px_#0000000D] hover:bg-[#e0f2fe] transition"
                        title={t('chat.showParams') || '参数设置'}
                    >
                        {OpenParaIcon}
                    </button>
                    <input ref={fileInputRef} type="file" accept=".mp3,.wav,.flac,.m4a,.ogg" onChange={handleFileSelect} className="hidden" />
                </div>
            </div>
        </div>
    );
}
