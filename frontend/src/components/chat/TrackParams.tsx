// src/components/chat/TrackParams.tsx
import { useTranslation } from 'react-i18next';
import { useState, useRef, useEffect } from 'react';
import { GM_INSTRUMENTS } from '../../constants/instruments';

interface TrackParamsProps {
    instrument: string;
    setInstrument: (val: string) => void;
    tempo: string;
    setTempo: (val: string) => void;
    duration: string;
    setDuration: (val: string) => void;
    filename: string;
    setFilename: (val: string) => void;
    audioDuration?: number;      // 音频总时长（秒），用于限制 duration 最大值;可选，未上传时为 undefined
}

export default function TrackParams({
                                        instrument,
                                        setInstrument,
                                        tempo,
                                        setTempo,
                                        duration,
                                        setDuration,
                                        filename,
                                        setFilename,
                                        audioDuration,
                                    }: TrackParamsProps) {
    const { t } = useTranslation();
    const [showInstrument, setShowInstrument] = useState(false);

    const [searchTerm, setSearchTerm] = useState('');
    const dropdownRef = useRef<HTMLDivElement>(null);

    // 过滤乐器列表
    const filteredInstruments = GM_INSTRUMENTS.filter(inst => {
        const translated = t(`params.instruments.${inst}`, inst);
        return inst.toLowerCase().includes(searchTerm.toLowerCase()) ||
            translated.toLowerCase().includes(searchTerm.toLowerCase());
    });

    // 点击外部关闭下拉框
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setShowInstrument(false);
                setSearchTerm('');
            }
        };
        if (showInstrument) {
            document.addEventListener('mousedown', handleClickOutside);
        }
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [showInstrument]);

    // 处理时长输入（数字校验 + 最大值限制）
    const handleDurationChange = (val: string) => {
        let numVal = parseInt(val, 10);
        if (isNaN(numVal)) {
            setDuration('');
            return;
        }
        // 最小值 1 秒，最大值优先使用 audioDuration，否则使用 60（系统上限）
        let maxVal = audioDuration ? Math.floor(audioDuration) : 60;
        if (maxVal < 1) maxVal = 60;
        numVal = Math.min(Math.max(numVal, 1), maxVal);
        setDuration(String(numVal));
    };

    // 处理 BPM 输入（数字校验，范围 20-300）
    const handleTempoChange = (val: string) => {
        let numVal = parseInt(val, 10);
        if (isNaN(numVal)) {
            setTempo('');
            return;
        }
        numVal = Math.min(Math.max(numVal, 20), 300);
        setTempo(String(numVal));
    };

    // 清除按钮 SVG（简单 X 图标）
    const ClearIcon = () => (
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12" />
        </svg>
    );

    return (
        <div className="bg-white/90 backdrop-blur-sm border border-[#e0f2fe] rounded-3xl p-8">
            <div className="grid grid-cols-2 gap-x-12 gap-y-6">

                {/* INSTRUMENT 行 */}
                <div className="flex flex-row-reverse items-center justify-between h-[42px]">
                    <div className="w-[200px] relative" ref={dropdownRef}>
                        <div className="flex items-center gap-2">
                            <div className="flex-1 relative">
                                <button
                                    onClick={() => setShowInstrument(!showInstrument)}
                                    className="w-full bg-[#f8fafc] border border-[#f1f5f9] rounded-xl py-2.5 px-4 flex items-center justify-between"
                                >
                                    <span className="text-sm font-normal text-[#2f3334] truncate">
                                        {instrument ? t(`params.instruments.${instrument}`, instrument) : t('params.notSelected', '未选择')}
                                    </span>
                                    <svg width="7" height="4.32" viewBox="0 0 7 4.32" fill="none">
                                        <path d="M3.5 4.32L0 0.82L0.81665 0L3.5 2.68335L6.18335 0L7 0.82L3.5 4.32Z" fill="#94a3b8" />
                                    </svg>
                                </button>

                                {showInstrument && (
                                    <div className="absolute bottom-full left-0 w-full bg-white border border-gray-200 rounded-xl mt-1 shadow-lg z-20">
                                        {/* 搜索框 */}
                                        <div className="p-2 border-b border-gray-100">
                                            <input
                                                type="text"
                                                placeholder="搜索乐器..."
                                                value={searchTerm}
                                                onChange={(e) => setSearchTerm(e.target.value)}
                                                className="w-full px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-[#00639d]"
                                                autoFocus
                                            />
                                        </div>
                                        {/* 滚动列表，最大高度约 200px，显示约 4-5 项 */}
                                        <div className="max-h-48 overflow-y-auto">
                                            {filteredInstruments.length === 0 ? (
                                                <div className="px-4 py-2 text-sm text-gray-400">无匹配乐器</div>
                                            ) : (
                                                filteredInstruments.map((inst) => (
                                                    <button
                                                        key={inst}
                                                        onClick={() => {
                                                            setInstrument(inst);
                                                            setShowInstrument(false);
                                                            setSearchTerm('');
                                                        }}
                                                        className={`w-full text-left px-4 py-2.5 text-sm hover:bg-gray-50 ${
                                                            instrument === inst ? 'text-[#0369a1] font-medium bg-blue-50' : 'text-[#2f3334]'
                                                        }`}
                                                    >
                                                        {t(`params.instruments.${inst}`, inst)}
                                                    </button>
                                                ))
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                            {instrument && (
                                <button
                                    onClick={() => setInstrument('')}
                                    className="text-gray-400 hover:text-red-500 transition"
                                    title="清除"
                                >
                                    <ClearIcon />
                                </button>
                            )}
                        </div>
                    </div>
                    <p className="text-[11px] font-semibold uppercase tracking-[2.2px] text-[#94a3b8]">
                        {t('params.instrument')}
                    </p>
                </div>

                {/* DURATION 行 */}
                <div className="flex flex-row-reverse items-center justify-between h-[42px]">
                    <div className="w-[200px] flex items-center gap-2">
                        <div className="flex-1 bg-[#f8fafc] border border-[#f1f5f9] rounded-xl py-2.5 px-4 flex items-center justify-between">
                            <input
                                type="text"
                                inputMode="numeric"
                                pattern="\d*"
                                value={duration}
                                onChange={(e) => handleDurationChange(e.target.value)}
                                className="w-[120px] bg-transparent outline-none text-sm font-semibold text-[#2f3334]"
                                placeholder="-"
                            />
                            <span className="text-[10px] font-semibold uppercase text-[#94a3b8]">{t('params.sec')}</span>
                        </div>
                        {duration && (
                            <button
                                onClick={() => setDuration('')}
                                className="text-gray-400 hover:text-red-500 transition"
                                title="清除"
                            >
                                <ClearIcon />
                            </button>
                        )}
                    </div>
                    <p className="text-[11px] font-semibold uppercase tracking-[2.2px] text-[#94a3b8]">{t('params.duration')}</p>
                    {audioDuration && (
                        <span className="text-[10px] text-gray-400 ml-1">(最长 {Math.floor(audioDuration)}s)</span>
                    )}
                </div>

                {/* TEMPO 行（与 DURATION 同理，添加清除按钮） */}
                <div className="flex flex-row-reverse items-center justify-between h-[42px]">
                    <div className="w-[200px] flex items-center gap-2">
                        <div className="flex-1 bg-[#f8fafc] border border-[#f1f5f9] rounded-xl py-2.5 px-4 flex items-center justify-between">
                            <input
                                type="text"
                                inputMode="numeric"
                                pattern="\d*"
                                value={tempo}
                                onChange={(e) => handleTempoChange(e.target.value)}
                                className="w-[120px] bg-transparent outline-none text-sm font-semibold text-[#2f3334]"
                                placeholder="-"
                            />
                            <span className="text-[10px] font-semibold uppercase text-[#94a3b8]">{t('params.bpm')}</span>
                        </div>
                        {tempo && (
                            <button
                                onClick={() => setTempo('')}
                                className="text-gray-400 hover:text-red-500 transition"
                                title="清除"
                            >
                                <ClearIcon />
                            </button>
                        )}
                    </div>
                    <p className="text-[11px] font-semibold uppercase tracking-[2.2px] text-[#94a3b8]">{t('params.tempo')}</p>
                </div>

                {/* FILENAME 行：不添加清除按钮 */}
                <div className="flex flex-row-reverse items-center justify-between h-[42px]">
                    <div className="w-[200px]">
                        <div className="bg-[#f8fafc] border border-[#f1f5f9] rounded-xl py-2.5 px-4">
                            <input
                                type="text"
                                value={filename}
                                onChange={(e) => setFilename(e.target.value)}
                                className="w-full bg-transparent outline-none text-sm font-semibold text-[#2f3334]"
                            />
                        </div>
                    </div>
                    <p className="text-[11px] font-semibold uppercase tracking-[2.2px] text-[#94a3b8]">{t('params.filename')}</p>
                </div>
            </div>
        </div>
    );
}
