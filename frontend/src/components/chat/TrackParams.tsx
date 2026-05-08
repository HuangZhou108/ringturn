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
    const instruments = ['Acoustic Piano', 'Violin'];

    return (
        <div className="bg-white border border-[#e0f2fe] rounded-3xl p-8">
            <div className="grid grid-cols-2 gap-x-12 gap-y-6">
                {/* INSTRUMENT */}
                <div className="flex flex-row-reverse items-center justify-between h-[42px]">
                    <div className="w-[200px] relative">
                        <button
                            onClick={() => setShowInstrument(!showInstrument)}
                            className="w-full bg-[#f8fafc] border border-[#f1f5f9] rounded-xl py-2.5 px-4 flex items-center justify-between"
                        >
                            <span className="text-sm font-normal text-[#2f3334]">{instrument}</span>
                            <svg width="7" height="4.32" viewBox="0 0 7 4.32" fill="none">
                                <path d="M3.5 4.32L0 0.82L0.81665 0L3.5 2.68335L6.18335 0L7 0.82L3.5 4.32Z" fill="#94a3b8"/>
                            </svg>
                        </button>
                        {showInstrument && (
                            <div className="absolute top-full left-0 w-full bg-white border border-[#f1f5f9] rounded-xl mt-1 shadow-lg z-10">
                                {instruments.map((inst) => (
                                    <button
                                        key={inst}
                                        onClick={() => { setInstrument(inst); setShowInstrument(false); }}
                                        className={`w-full text-left px-4 py-2.5 text-sm hover:bg-gray-50 first:rounded-t-xl last:rounded-b-xl ${instrument === inst ? 'text-[#0369a1] font-medium' : 'text-[#2f3334]'}`}
                                    >
                                        {inst}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                    <p className="text-[11px] font-semibold uppercase tracking-[2.2px] text-[#94a3b8]">{t('params.instrument')}</p>
                </div>

                {/* DURATION */}
                <div className="flex flex-row-reverse items-center justify-between h-[42px]">
                    <div className="w-[200px]">
                        <div className="bg-[#f8fafc] border border-[#f1f5f9] rounded-xl py-2.5 px-4 flex items-center justify-between">
                            <input
                                type="text"
                                value={duration}
                                onChange={(e) => setDuration(e.target.value)}
                                className="w-[120px] bg-transparent outline-none text-sm font-semibold text-[#2f3334]"
                            />
                            <span className="text-[10px] font-semibold uppercase text-[#94a3b8]">{t('params.sec')}</span>
                        </div>
                    </div>
                    <p className="text-[11px] font-semibold uppercase tracking-[2.2px] text-[#94a3b8]">{t('params.duration')}</p>
                </div>

                {/* TEMPO */}
                <div className="flex flex-row-reverse items-center justify-between h-[42px]">
                    <div className="w-[200px]">
                        <div className="bg-[#f8fafc] border border-[#f1f5f9] rounded-xl py-2.5 px-4 flex items-center justify-between">
                            <input
                                type="text"
                                value={tempo}
                                onChange={(e) => setTempo(e.target.value)}
                                className="w-[120px] bg-transparent outline-none text-sm font-semibold text-[#2f3334]"
                            />
                            <span className="text-[10px] font-semibold uppercase text-[#94a3b8]">{t('params.bpm')}</span>
                        </div>
                    </div>
                    <p className="text-[11px] font-semibold uppercase tracking-[2.2px] text-[#94a3b8]">{t('params.tempo')}</p>
                </div>

                {/* FILENAME */}
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
