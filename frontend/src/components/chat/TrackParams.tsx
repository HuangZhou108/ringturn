// src/components/chat/TrackParams.tsx
import { useTranslation } from 'react-i18next';
import { useState } from 'react';

interface TrackParamsProps {
    instrument: string;
    setInstrument: (val: string) => void;
    tempo: string;
    setTempo: (val: string) => void;
    duration: string;
    setDuration: (val: string) => void;
    filename: string;
    setFilename: (val: string) => void;
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
                                    }: TrackParamsProps) {
    const { t } = useTranslation();
    const [showInstrument, setShowInstrument] = useState(false);
    // 乐器列表：value 是实际存储的值（英文），labelKey 是 i18n 键
    const instruments = [
        { value: 'Acoustic Piano', labelKey: 'params.instruments.acousticPiano' },
        { value: 'Violin', labelKey: 'params.instruments.violin' },
    ];
    // 获取当前选中乐器的显示文本
    const currentInstrumentLabel = instruments.find(inst => inst.value === instrument)?.labelKey || instrument;

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
                    <div className="w-[200px] relative flex items-center gap-2">
                        <div className="flex-1 relative">
                            <button
                                onClick={() => setShowInstrument(!showInstrument)}
                                className="w-full bg-[#f8fafc] border border-[#f1f5f9] rounded-xl py-2.5 px-4 flex items-center justify-between"
                            >
                <span className="text-sm font-normal text-[#2f3334]">
                  {instrument ? t(currentInstrumentLabel) : '未选择'}
                </span>
                                <svg width="7" height="4.32" viewBox="0 0 7 4.32" fill="none">
                                    <path d="M3.5 4.32L0 0.82L0.81665 0L3.5 2.68335L6.18335 0L7 0.82L3.5 4.32Z" fill="#94a3b8" />
                                </svg>
                            </button>
                            {showInstrument && (
                                <div className="absolute top-full left-0 w-full bg-white border border-[#f1f5f9] rounded-xl mt-1 shadow-lg z-10">
                                    {instruments.map((inst) => (
                                        <button
                                            key={inst.value}
                                            onClick={() => { setInstrument(inst.value); setShowInstrument(false); }}
                                            className={`w-full text-left px-4 py-2.5 text-sm hover:bg-gray-50 first:rounded-t-xl last:rounded-b-xl ${
                                                instrument === inst.value ? 'text-[#0369a1] font-medium' : 'text-[#2f3334]'
                                            }`}
                                        >
                                            {t(inst.labelKey)}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                        {/* 清除按钮 */}
                        {instrument && (
                            <button
                                onClick={() => setInstrument('')}
                                className="text-gray-400 hover:text-red-500 transition"
                                title={t('common.clear') || 'clear'}
                            >
                                <ClearIcon />
                            </button>
                        )}
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
                                value={duration}
                                onChange={(e) => setDuration(e.target.value)}
                                className="w-[120px] bg-transparent outline-none text-sm font-semibold text-[#2f3334]"
                                placeholder="-"
                            />
                            <span className="text-[10px] font-semibold uppercase text-[#94a3b8]">{t('params.sec')}</span>
                        </div>
                        {duration && (
                            <button
                                onClick={() => setDuration('')}
                                className="text-gray-400 hover:text-red-500 transition"
                                title="clear"
                            >
                                <ClearIcon />
                            </button>
                        )}
                    </div>
                    <p className="text-[11px] font-semibold uppercase tracking-[2.2px] text-[#94a3b8]">{t('params.duration')}</p>
                </div>

                {/* TEMPO 行（与 DURATION 同理，添加清除按钮） */}
                <div className="flex flex-row-reverse items-center justify-between h-[42px]">
                    <div className="w-[200px] flex items-center gap-2">
                        <div className="flex-1 bg-[#f8fafc] border border-[#f1f5f9] rounded-xl py-2.5 px-4 flex items-center justify-between">
                            <input
                                type="text"
                                value={tempo}
                                onChange={(e) => setTempo(e.target.value)}
                                className="w-[120px] bg-transparent outline-none text-sm font-semibold text-[#2f3334]"
                                placeholder="-"
                            />
                            <span className="text-[10px] font-semibold uppercase text-[#94a3b8]">{t('params.bpm')}</span>
                        </div>
                        {tempo && (
                            <button
                                onClick={() => setTempo('')}
                                className="text-gray-400 hover:text-red-500 transition"
                                title="clear"
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
