import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

i18n
    .use(LanguageDetector)
    .use(initReactI18next)
    .init({
        resources: {
            en: {
                translation: {
                    header: {
                        chatFlow: 'Chat Flow',
                        newChat: 'New Chat',
                        language: 'Language',
                        viewHistory: 'View History',
                    },
                    sidebar: {
                        ringTurn: 'RingTurn',
                        aiMusic: 'AI MUSIC ADAPTATION',
                        newConversation: 'New Conversation',
                        newAdaptation: 'New Adaptation',
                        mainMenu: 'MAIN MENU',
                        recentTracks: 'Recent Tracks',
                        library: 'Library',
                        studioSessions: 'Studio Sessions',
                        archive: 'Archive',
                        settings: 'Settings',
                        support: 'Support',
                        notAvailable: 'Sidebar is temporarily unavailable',
                        conversations: 'Conversations',
                        noConversation: 'No Conversation',
                    },
                    welcome: {
                        titleBefore: 'Adapt your track, ',
                        titleHighlight: 'perfectly.',
                        titleAfter: '',
                        subtitle: 'How can I help you transform your music today? You can specify instruments, adjust the tempo, or lengthen segments.',
                    },
                    chat: {
                        deepThinking: '> Deep Thinking Process',
                        aiResponse: "I've analyzed your track. I can definitely help with that. I'll isolate the mid-range piano frequencies and apply a bit-crusher effect, then layer it over a dusty drum loop.",
                        userMessage: 'Can you take the piano melody from my uploaded track and adapt it into a Lo-Fi chillhop style with a slower BPM?',
                        fileName: 'Midnight_Lofi_Draft.mp3',
                        fileInfo: '84 BPM • 3:24 • Mastered',
                        taskCreated: 'Task created, processing...',
                        createFailed: 'Task creation failed, please retry.',
                        networkError: 'Network error, please check if the backend service is running.',
                        completed: 'Task completed',
                        failed: 'Task failed',
                    },
                    params: {
                        instrument: 'INSTRUMENT',
                        acousticPiano: 'Acoustic Piano', // 保留备用
                        instruments: {
                            acousticPiano: 'Acoustic Piano',
                            violin: 'Violin',
                        },
                        duration: 'DURATION',
                        sec: 'SEC',
                        tempo: 'TEMPO (BPM)',
                        bpm: 'BPM',
                        filename: 'FILENAME',
                        untitledTrack: 'Untitled_Track',
                    },
                    input: {
                        placeholder: 'Upload an audio file and type in your request.',
                    },
                    toast: {
                        uploadRequired: "Please upload an audio file first~",
                    },
                },
            },
            zh: {
                translation: {
                    header: {
                        chatFlow: '聊天流',
                        newChat: '开始新对话',
                        language: '语言选项',
                        viewHistory: '查看历史',
                    },
                    sidebar: {
                        ringTurn: 'RingTurn',
                        aiMusic: 'AI 音乐改编',
                        newConversation: '新建会话',
                        newAdaptation: '新建改编',
                        mainMenu: '主菜单',
                        recentTracks: '最近曲目',
                        library: '曲库',
                        studioSessions: '录音室会话',
                        archive: '归档',
                        settings: '设置',
                        support: '支持',
                        notAvailable: '侧边栏暂不开放',
                        conversations: '会话',
                        noConversations: '暂无会话',
                    },
                    welcome: {
                        titleBefore: '为您提供，',
                        titleHighlight: '优质的',
                        titleAfter: '音乐改编',
                        subtitle: '希望如何改编你喜欢的音乐？你可以简要描述，并指定乐器、节奏、总长度以及任何你想要的修改。',
                    },
                    chat: {
                        deepThinking: '> 深度思考过程',
                        aiResponse: '我已分析了您的曲目，完全可以帮您处理。我将分离中频钢琴频率并应用降采样效果，然后叠加到复古鼓循环上。',
                        userMessage: '您能提取我上传曲目中的钢琴旋律，并将其改编为更慢 BPM 的 Lo-Fi 放松风格吗？',
                        fileName: '午夜_Lofi_草稿.mp3',
                        fileInfo: '84 BPM • 3:24 • 已母带',
                        taskCreated: '任务已创建，正在处理中...',
                        createFailed: '任务创建失败，请重试。',
                        networkError: '网络错误，请检查后端服务是否启动。',
                        completed: '任务已完成',
                        failed: '任务失败',
                    },
                    params: {
                        instrument: '乐器',
                        acousticPiano: '古典钢琴', // 保留备用
                        instruments: {
                            acousticPiano: '古典钢琴',
                            violin: '小提琴',
                        },
                        duration: '音频长度',
                        sec: 'SEC',
                        tempo: '速度 (BPM)',
                        bpm: 'BPM',
                        filename: '生成文件名',
                        untitledTrack: 'Untitled_Track',
                    },
                    input: {
                        placeholder: '上传音频文件，输入你的需求~',
                    },
                    toast: {
                        uploadRequired: "请上传音频~",
                    },
                },
            },
        },
        fallbackLng: 'en',
        detection: {
            order: ['localStorage', 'navigator'],
            caches: ['localStorage'],
        },
    })

export default i18n
