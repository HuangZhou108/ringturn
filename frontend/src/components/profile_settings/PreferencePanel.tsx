// frontend/src/components/profile_settings/PreferencePanel.tsx
import { useState } from 'react';
import { profileApi } from '../../api/profile';

interface PreferencePanelProps {
    profileId: number;
    preferences: any;
    onSave: () => void;
    isLoading: boolean;
    t: (key: string) => string;
}

export default function PreferencePanel({ profileId, preferences, onSave, isLoading, t }: PreferencePanelProps) {
    const [instrument, setInstrument] = useState(preferences.default_instrument || '');
    const [duration, setDuration] = useState(preferences.default_duration || 30);
    const [tempo, setTempo] = useState(preferences.default_tempo || 120);
    const [saving, setSaving] = useState(false);

    const handleSave = async () => {
        setSaving(true);
        const newPrefs = {
            ...preferences,
            default_instrument: instrument,
            default_duration: duration,
            default_tempo: tempo,
        };
        const res = await profileApi.update(profileId, { preferences_data: JSON.stringify(newPrefs) });
        if (res.code === 200) {
            onSave();
            alert('偏好保存成功');
        } else {
            alert(res.message);
        }
        setSaving(false);
    };

    return (
        <div>
            <div className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">默认乐器</label>
                    <select
                        value={instrument}
                        onChange={(e) => setInstrument(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-1 focus:ring-[#00639d]"
                    >
                        <option value="">不指定</option>
                        <option value="Acoustic Piano">Acoustic Piano</option>
                        <option value="Violin">Violin</option>
                        <option value="Guitar">Guitar</option>
                        <option value="Flute">Flute</option>
                    </select>
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">默认时长 (秒)</label>
                    <input
                        type="number"
                        min="5"
                        max="60"
                        value={duration}
                        onChange={(e) => setDuration(Number(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    />
                </div>
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">默认速度 (BPM)</label>
                    <input
                        type="number"
                        min="40"
                        max="200"
                        value={tempo}
                        onChange={(e) => setTempo(Number(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    />
                </div>
            </div>
            <div className="mt-6">
                <button
                    onClick={handleSave}
                    disabled={saving || isLoading}
                    className="w-full py-2 bg-[#00639d] text-white rounded-lg hover:bg-[#005288] disabled:opacity-50"
                >
                    保存偏好
                </button>
            </div>
        </div>
    );
}
