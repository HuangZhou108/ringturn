// src/components/chat/MessageList.tsx
import type { Message } from '../../types';
import { api } from '../../api';

interface MessageListProps {
    messages: Message[];
    t: (key: string) => string;
}

export default function MessageList({ messages, t }: MessageListProps) {
    return (
        <div className="space-y-6">
            {messages.map((msg) => (
                <div key={msg.id}>
                    {msg.type === 'ai' && (
                        <div className="flex gap-3">
                            {/* AI 头像 */}
                            <div className="w-8 h-8 bg-[#f0f9ff] rounded-full flex items-center justify-center flex-shrink-0">
                                <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
                                    <path d="M18 8L16.75 5.25L14 4L16.75 2.75L18 0L19.25 2.75L22 4L19.25 5.25L18 8ZM18 22L16.75 19.25L14 18L16.75 16.75L18 14L19.25 16.75L22 18L19.25 19.25L18 22ZM8 19L5.5 13.5L0 11L5.5 8.5L8 3L10.5 8.5L16 11L10.5 13.5L8 19Z" fill="#00639d"/>
                                </svg>
                            </div>
                            {/* AI 消息气泡 */}
                            <div className="flex-1 bg-[#f3f4f4] rounded-tr-2xl rounded-bl-2xl rounded-br-2xl pt-[14.75px] px-6 pb-4 flex flex-col gap-y-4 max-w-[508.8px]">
                                {/* 思考过程 */}
                                {msg.thinkingProcess && msg.thinkingProcess.length > 0 && (
                                    <div className="bg-white rounded-xl border border-gray-200 p-3 -mx-2">
                                        <p className="text-xs font-medium text-[#00639d] mb-2">
                                            深度思考过程 ({msg.thinkingProcess.length}步)
                                        </p>
                                        <div className="space-y-1.5">
                                            {msg.thinkingProcess.map((thought, idx) => (
                                                <div key={idx} className="flex items-start gap-2">
                          <span className="inline-block px-1.5 py-0.5 bg-[#00639d]/10 text-[#00639d] rounded text-[10px] font-medium flex-shrink-0">
                            {thought.step}
                          </span>
                                                    <span className="text-xs text-gray-600 leading-relaxed">{thought.content}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {/* AI 回复文字 */}
                                {msg.content && <p className="text-gray-700 text-sm leading-relaxed">{msg.content}</p>}
                                {/* 音频卡片 */}
                                {msg.fileName && (
                                    <div className="bg-white border border-gray-200 rounded-xl p-4 -mx-2">
                                        <div className="flex items-center gap-3">
                                            <div className="w-8 h-8 bg-[#0284c7] rounded-lg flex items-center justify-center">
                                                <svg width="11" height="14" viewBox="0 0 11 14" fill="none">
                                                    <path d="M0 14V0H11L0 7V14ZM2 7L7.25 3.65V10.35L2 7Z" fill="white"/>
                                                </svg>
                                            </div>
                                            <div className="flex-1">
                                                <p className="font-medium text-gray-800">{msg.fileName}</p>
                                                {msg.fileInfo && <p className="text-xs text-gray-500">{msg.fileInfo}</p>}
                                            </div>
                                            <button
                                                onClick={() => api.downloadFile(msg.fileName!, msg.fileName!.split('/').pop() || 'audio')}
                                                className="px-3 py-1.5 bg-[#0284c7] text-white text-xs font-medium rounded-lg hover:bg-[#0369a1] transition"
                                            >
                                                下载
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                    {msg.type === 'user' && (
                        <div className="flex justify-end">
                            <div className="max-w-[555px] space-y-[0.5px]">
                                {/* 用户文件附件 */}
                                {msg.userFile && (
                                    <div className="flex items-center gap-4 bg-white border border-[#afb3b3]/60 rounded-t-[15px] rounded-bl-[2px] rounded-br-[10px] px-4 py-[13px] w-fit ml-auto">
                                        <div className="w-[29px] h-[31px] bg-[#e0f2fe] rounded-lg flex items-center justify-center flex-shrink-0">
                                            <svg width="17" height="21" viewBox="0 0 17 21" fill="none">
                                                <path d="M0 21V0H17L3.09 7H0V21ZM2 7L10.2 4.65V9.35L2 7Z" fill="#0284c7"/>
                                            </svg>
                                        </div>
                                        <span className="text-xs font-semibold text-[#2f3334]">{msg.userFile}</span>
                                    </div>
                                )}
                                {/* 用户消息气泡 */}
                                {msg.content && (
                                    <div className="bg-[#cfe6f0] rounded-2xl rounded-tr-none shadow-[0px_1px_2px_0px_#0000000D] px-6 py-[14.88px] max-w-[508.8px]">
                                        <p className="text-sm text-[#40555d] leading-relaxed">{msg.content}</p>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            ))}
        </div>
    );
}
