// src/components/chat/MessageList.tsx
import { useState } from 'react';
import type { Message } from '../../types';
import { api } from '../../api';

interface MessageListProps {
    messages: Message[];
    t: (key: string) => string;
}

// 截断文件名（保留扩展名）
const truncateFilename = (filename: string, maxBaseLen: number = 20): string => {
    if (!filename) return '';
    const lastDot = filename.lastIndexOf('.');
    if (lastDot === -1) {
        return filename.length > maxBaseLen ? filename.slice(0, maxBaseLen - 3) + '...' : filename;
    }
    const baseName = filename.slice(0, lastDot);
    const ext = filename.slice(lastDot);
    if (baseName.length <= maxBaseLen) return filename;
    return baseName.slice(0, maxBaseLen - 3) + '...' + ext;
};

// ---------- 深度思考子组件 ----------
interface ThinkingEntry {
    step: string;
    content: string;
    timestamp: string;
    type?: 'info' | 'llm' | 'tool_call' | 'tool_result';
    status?: 'success' | 'failed' | 'pending' | 'retry';
}

function ThinkingProcess({ entries, t }: { entries: ThinkingEntry[]; t: (key: string) => string }) {
    const [isDeepExpanded, setIsDeepExpanded] = useState(true);
    const [expandedToolGroups, setExpandedToolGroups] = useState<Record<string, boolean>>({});

    const toggleDeep = () => setIsDeepExpanded(!isDeepExpanded);
    const toggleToolGroup = (step: string) => {
        setExpandedToolGroups((prev) => ({
            ...prev,
            [step]: !prev[step],
        }));
    };

    // 按 step 分组
    const groups: { step: string; entries: ThinkingEntry[] }[] = [];
    for (const entry of entries) {
        const last = groups[groups.length - 1];
        if (last && last.step === entry.step) {
            last.entries.push(entry);
        } else {
            groups.push({ step: entry.step, entries: [entry] });
        }
    }

    // 判断是否为工具相关条目
    const isToolEntry = (e: ThinkingEntry) => e.type === 'tool_call' || e.type === 'tool_result';

    // 从 tool_call 内容中提取工具名
    const extractToolName = (content: string): string => {
        const match = content.match(/调用工具:\s*([^\s,，]+)/);
        return match ? match[1] : '工具';
    };

    // 生成工具摘要（取前 3 个工具名，多余截断）
    const getToolSummary = (toolEntries: ThinkingEntry[]): string => {
        const names: string[] = [];
        for (const e of toolEntries) {
            if (e.type === 'tool_call') {
                const name = extractToolName(e.content);
                if (!names.includes(name)) names.push(name);
            }
        }
        if (names.length === 0) return '工具调用完成';
        const display = names.slice(0, 3);
        let summary = display.join('、');
        if (names.length > 3) summary += `…（共${names.length}个）`;
        return `工具调用完成：${summary}`;
    };

    // 获取状态对应的样式
    const statusColor = (status?: string): string => {
        switch (status) {
            case 'success':
                return 'text-green-800 bg-green-100';
            case 'failed':
                return 'text-red-800 bg-red-100';
            case 'pending':
                return 'text-yellow-800 bg-yellow-100';
            default:
                return 'text-gray-700 bg-gray-50';
        }
    };

    return (
        <div className="bg-white rounded-xl border border-gray-200 p-3 -mx-2">
            {/* 头部：可点击折叠/展开 */}
            <div
                className="flex items-center justify-between cursor-pointer select-none"
                onClick={toggleDeep}
            >
                <p
                    className={`text-xs font-medium text-[#00639d] ${
                        !isDeepExpanded ? 'underline' : ''
                    }`}
                >
                    深度思考过程
                </p>
                <span className="text-xs text-gray-400">
                    {isDeepExpanded ? '▼' : '▶'}
                </span>
            </div>

            {isDeepExpanded && (
                <div className="mt-3 space-y-3">
                    {groups.map((group) => {
                        const toolEntries = group.entries.filter(isToolEntry);
                        const otherEntries = group.entries.filter((e) => !isToolEntry(e));
                        const isToolGroupExpanded = expandedToolGroups[group.step] || false;

                        return (
                            <div key={group.step} className="space-y-1.5">
                                {/* 步骤名称（仅在存在非工具条目或工具组展开时显示，避免重复） */}
                                {(otherEntries.length > 0 || toolEntries.length > 0) && (
                                    <span className="inline-block px-1.5 py-0.5 bg-[#00639d]/10 text-[#00639d] rounded text-[10px] font-medium">
                                        {group.step}
                                    </span>
                                )}

                                {/* 非工具条目：直接显示文本 */}
                                {otherEntries.map((entry, idx) => (
                                    <div key={idx} className="text-xs text-gray-600 leading-relaxed">
                                        {entry.content}
                                    </div>
                                ))}

                                {/* 工具条目组 */}
                                {toolEntries.length > 0 && (
                                    <div className="mt-1">
                                        {/* 摘要行（可点击展开/收起） */}
                                        <div
                                            className="flex items-center gap-1 cursor-pointer text-xs text-[#00639d] hover:underline"
                                            onClick={() => toggleToolGroup(group.step)}
                                        >
                                            <span>{getToolSummary(toolEntries)}</span>
                                            <span className="text-gray-400">
                                                {isToolGroupExpanded ? '▲' : '▼'}
                                            </span>
                                        </div>

                                        {/* 展开的工具列表 */}
                                        {isToolGroupExpanded && (
                                            <ul className="mt-1 ml-2 space-y-0.5 list-disc list-inside">
                                                {toolEntries.map((entry, idx) => {
                                                    const isCall = entry.type === 'tool_call';
                                                    const statusClass = statusColor(entry.status);
                                                    // 展示内容：对于 tool_call，只显示工具名；对于 tool_result，显示结果摘要
                                                    let displayContent = entry.content;
                                                    if (isCall) {
                                                        const name = extractToolName(entry.content);
                                                        displayContent = `调用工具： ${name}`;
                                                    } else {
                                                        // 结果可能很长，截断
                                                        displayContent = entry.content.length > 100
                                                            ? entry.content.slice(0, 100) + '...'
                                                            : entry.content;
                                                    }
                                                    return (
                                                        <li
                                                            key={idx}
                                                            className={`text-xs px-2 py-0.5 rounded ${statusClass}`}
                                                        >
                                                            {displayContent}
                                                        </li>
                                                    );
                                                })}
                                            </ul>
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

// ---------- 主组件 ----------
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
                                    <path
                                        d="M18 8L16.75 5.25L14 4L16.75 2.75L18 0L19.25 2.75L22 4L19.25 5.25L18 8ZM18 22L16.75 19.25L14 18L16.75 16.75L18 14L19.25 16.75L22 18L19.25 19.25L18 22ZM8 19L5.5 13.5L0 11L5.5 8.5L8 3L10.5 8.5L16 11L10.5 13.5L8 19Z"
                                        fill="#00639d"
                                    />
                                </svg>
                            </div>
                            <div className="flex-1 bg-[#f3f4f4] rounded-tr-2xl rounded-bl-2xl rounded-br-2xl pt-[14.75px] px-6 pb-4 flex flex-col gap-y-4 max-w-[508.8px]">
                                {/* 深度思考区域 */}
                                {msg.thinkingProcess && msg.thinkingProcess.length > 0 && (
                                    <ThinkingProcess entries={msg.thinkingProcess} t={t} />
                                )}

                                {/* AI 回复正文 */}
                                {msg.content && (
                                    <p className="text-gray-700 text-sm leading-relaxed">{msg.content}</p>
                                )}

                                {/* 音频卡片 */}
                                {msg.fileName && (
                                    <div className="bg-white border border-gray-200 rounded-xl p-4 -mx-2">
                                        <div className="flex items-center gap-3">
                                            <div className="w-8 h-8 bg-[#0284c7] rounded-lg flex items-center justify-center">
                                                <svg width="11" height="14" viewBox="0 0 11 14" fill="none">
                                                    <path
                                                        d="M0 14V0L11 0L0 7V14ZM2 7L7.25 3.65V10.35L2 7Z"
                                                        fill="white"
                                                    />
                                                </svg>
                                            </div>
                                            <div className="flex-1">
                                                <p className="font-medium text-gray-800">{msg.fileName}</p>
                                                {msg.fileInfo && (
                                                    <p className="text-xs text-gray-500">{msg.fileInfo}</p>
                                                )}
                                            </div>
                                            <button
                                                onClick={() =>
                                                    api.downloadFile(
                                                        msg.fileName!,
                                                        msg.fileName!.split('/').pop() || 'audio'
                                                    )
                                                }
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
                            <div className="max-w-[555px] flex flex-col items-end gap-1">
                                {/* 用户文件附件 */}
                                {msg.userFile && (
                                    <div className="flex items-center gap-4 bg-white border border-[#afb3b3]/60 rounded-t-[15px] rounded-bl-[2px] rounded-br-[10px] px-4 py-[13px] w-44 ml-auto">
                                        <div className="w-[29px] h-[31px] bg-[#e0f2fe] rounded-lg flex items-center justify-center flex-shrink-0">
                                            <svg width="17" height="21" viewBox="0 0 17 21" fill="none">
                                                <path
                                                    d="M0 21V0H17L3.09 7H0V21ZM2 7L10.2 4.65V9.35L2 7Z"
                                                    fill="#0284c7"
                                                />
                                            </svg>
                                        </div>
                                        <span className="text-xs font-semibold text-[#2f3334] truncate flex-1">
                                            {truncateFilename(msg.userFile, 20)}
                                        </span>
                                    </div>
                                )}
                                {/* 用户消息气泡 */}
                                {msg.content && (
                                    <div className="bg-[#cfe6f0] rounded-2xl rounded-tr-none shadow-[0px_1px_2px_0px_#0000000D] px-6 py-[14.88px] w-fit max-w-[508.8px]">
                                        <p className="text-sm text-[#40555d] leading-relaxed">
                                            {msg.content}
                                        </p>
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
