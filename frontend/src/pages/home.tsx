// src/pages/Home.tsx
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import TopBar from '../components/TopBar';
import WelcomeMessage from '../components/chat/WelcomeMessage';
import ChatInputArea from '../components/chat/ChatInputArea';
import Toast from '../components/notifications/Toast';

function Home() {
    const navigate = useNavigate();
    const { t } = useTranslation();
    const [inputValue, setInputValue] = useState('');
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [filename, setFilename] = useState('Untitled_Track');
    const [audioFileId, setAudioFileId] = useState<string | null>(null);
    const [uploadError, setUploadError] = useState<string | null>(null);
    const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
    const [uploadProgress, setUploadProgress] = useState<number>(0);
    const [isUploading, setIsUploading] = useState(false);
    const [toastMessage, setToastMessage] = useState<string | null>(null);
    const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
    const [audioDuration, setAudioDuration] = useState<number | undefined>(undefined); // 上传音频长度

    // 参数设置（与 TrackParams 共享）
    const [instrument, setInstrument] = useState('');
    const [tempo, setTempo] = useState('');
    const [duration, setDuration] = useState('');

    const handleSend = async () => {
        if (!inputValue.trim()) return;
        // 检查是否已上传音频
        if (!audioFileId) {
            setToastMessage(t('toast.uploadRequired'));
            return;
        }

        // 构建动态参数对象
        const params: Record<string, any> = {};
        if (instrument.trim()) params.instrument = instrument;
        if (tempo.trim()) params.tempo = parseInt(tempo, 10);
        if (duration.trim()) params.duration = parseInt(duration, 10);
        if (filename && filename.trim() !== '') params.filename = filename;
        // 其他参数后续在此添加

        try {
            const res = await api.createTask({
                user_request: inputValue.trim(),
                source_type: 'upload',
                source_value: audioFileId || undefined,
                params,
            });

            if (res.code === 200) {
                navigate(`/chat/c/${res.data.conversation_id}`, {
                    state: {
                        taskId: res.data.task_id,
                        userMessage: inputValue.trim(),
                        audioFileId: audioFileId,
                        filename: uploadedFileName,
                        params,
                    },
                });
            } else {
                console.error(res.message || '创建任务失败');
            }
        } catch (err) {
            console.error('创建任务失败:', err);
        }
    };

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const validFormats = ['mp3', 'wav', 'flac', 'm4a', 'ogg'];
        const ext = file.name.split('.').pop()?.toLowerCase();
        if (!ext || !validFormats.includes(ext)) {
            setUploadError(`不支持的格式: .${ext}，支持: ${validFormats.join(', ')}`);
            return;
        }
        if (file.size > 50 * 1024 * 1024) {
            setUploadError('文件过大，最大支持 50MB');
            return;
        }

        setUploadError(null);
        setUploadSuccess(null);
        setIsUploading(true);
        setUploadProgress(0);

        try {
            const progressInterval = setInterval(() => {
                setUploadProgress((prev) => Math.min(prev + 10, 90));
            }, 200);

            const res = await api.uploadFile(file);
            clearInterval(progressInterval);
            setUploadProgress(100);

            if (res.code === 200) {
                setAudioFileId(res.data.file_id);
                setUploadedFileName(res.data.filename);
                setUploadSuccess(`文件已上传: ${res.data.filename} (${res.data.file_size.toFixed(2)} MB)`);
                if (res.data.duration) {
                    setAudioDuration(res.data.duration);
                }
            } else {
                setUploadError(res.message || '文件上传失败');
            }
        } catch (err) {
            console.error('上传失败:', err);
            setUploadError(`上传失败: ${err instanceof Error ? err.message : '未知错误'}`);
        } finally {
            setIsUploading(false);
            setTimeout(() => setUploadProgress(0), 500);
        }
    };

    return (
        <div className="flex flex-col h-screen bg-[#cfe9ff] font-['Inter'] page-enter">
            <TopBar
                newChatLabel={t('header.viewHistory')}
                onNewChat={() => navigate('/chat', { state: { newChat: true } })}
            />
            <main className="flex-1 flex flex-col items-center justify-center overflow-hidden bg-[#cfe9ff]">
                <div className="flex-1 flex items-center justify-center">
                    <WelcomeMessage />
                </div>
                <ChatInputArea
                    isProcessing={false}
                    onCancel={undefined}
                    mode="home"
                    isFloating={true}
                    inputValue={inputValue}
                    setInputValue={setInputValue}
                    handleSend={handleSend}
                    fileInputRef={fileInputRef}
                    handleFileSelect={handleFileSelect}
                    instrument={instrument}
                    setInstrument={setInstrument}
                    tempo={tempo}
                    setTempo={setTempo}
                    audioDuration={audioDuration}
                    duration={duration}
                    setDuration={setDuration}
                    filename={filename}
                    setFilename={setFilename}
                    isUploading={isUploading}
                    uploadProgress={uploadProgress}
                    uploadError={uploadError}
                    uploadSuccess={uploadSuccess}
                />
            </main>
            {toastMessage && (
                <Toast message={toastMessage} onClose={() => setToastMessage(null)} />
            )}
        </div>
    );
}

export default Home;
