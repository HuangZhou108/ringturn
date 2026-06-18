// frontend/src/components/profile_settings/PreferencePanel.tsx
import { useState, useEffect } from 'react';
import { profileApi } from '../../api/profile';
import type { PreferenceResponse, PreferenceUpdateRequest } from '../../types';
import { GM_INSTRUMENTS } from '../../constants/instruments';

interface PreferencePanelProps {
    profileId: number;
    onSave?: () => void;     // 保存成功后可选回调（刷新父组件）
    t: (key: string) => string;
}

export default function PreferencePanel({ profileId, onSave, t }: PreferencePanelProps) {
    // 从后端获取的完整偏好数据
    const [prefData, setPrefData] = useState<PreferenceResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    // 本地编辑状态（用户覆盖部分）
    // const [useAi, setUseAi] = useState(true);           // use_ai_preferences
    const [instrument, setInstrument] = useState('');
    const [tempo, setTempo] = useState<number | null>(null);
    const [duration, setDuration] = useState<number | null>(null);
    const [styleTagsStr, setStyleTagsStr] = useState(''); // 逗号分隔的字符串

    // 加载偏好数据
    const loadPreferences = async () => {
        if (!profileId) return;
        setLoading(true);
        try {
            const res = await profileApi.getPreferences(profileId);
            if (res.code === 200 && res.data) {
                setPrefData(res.data);
                const overrides = res.data.user_overrides;
                // setUseAi(overrides?.use_ai_preferences ?? true);
                setInstrument(overrides?.instrument ?? '');
                setTempo(overrides?.tempo ?? null);
                setDuration(overrides?.duration ?? null);
                setStyleTagsStr((overrides?.style_tags ?? []).join(', '));
            }
        } catch (err) {
            console.error('加载偏好失败', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadPreferences();
    }, [profileId]);

    // 保存用户覆盖
    const handleSave = async () => {
        if (!profileId) return;
        setSaving(true);
        try {
            const styleTags = styleTagsStr
                .split(',')
                .map(s => s.trim())
                .filter(s => s !== '');

            // 检查是否有任何有效输入
            const hasAnyValue = instrument !== '' || tempo !== null || duration !== null || styleTags.length > 0;

            if (!hasAnyValue) {
                // 如果所有字段为空，等同于清除覆盖
                await profileApi.resetPreferences(profileId);
                await loadPreferences();
                onSave?.();
                alert('已恢复 AI 推荐设置');
                setSaving(false);
                return;
            }

            const updateData: PreferenceUpdateRequest = {
                use_ai_preferences: false,
                instrument: instrument || null,
                tempo: tempo ?? null,
                duration: duration ?? null,
                style_tags: styleTags.length ? styleTags : null,
            };
            const res = await profileApi.updatePreferences(profileId, updateData);
            if (res.code === 200) {
                // 重新加载最新数据
                await loadPreferences();
                onSave?.();
                alert('偏好已保存');
            } else {
                alert(res.message || '保存失败');
            }
        } catch (err) {
            console.error('保存失败', err);
            alert('保存失败，请稍后重试');
        } finally {
            setSaving(false);
        }
    };

    // 恢复 AI 推荐（清除用户覆盖）
    const handleReset = async () => {
        if (!profileId) return;
        if (!confirm('确定要清除所有用户覆盖，恢复使用 AI 推荐吗？')) return;
        setSaving(true);
        try {
            const res = await profileApi.resetPreferences(profileId);
            if (res.code === 200) {
                await loadPreferences();
                onSave?.();
                alert('已恢复 AI 推荐设置');
            } else {
                alert(res.message || '恢复失败');
            }
        } catch (err) {
            console.error('恢复失败', err);
            alert('恢复失败，请稍后重试');
        } finally {
            setSaving(false);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-40">
                <div className="w-6 h-6 border-2 border-[#00639d] border-t-transparent rounded-full animate-spin" />
            </div>
        );
    }

    if (!prefData) {
        return <div className="text-gray-500 text-center">无法加载偏好数据</div>;
    }

    const ai = prefData.ai_recommendation;
    const effective = prefData.effective;

    return (
        <div className="space-y-6">
            {/* AI 推荐区（只读） */}
            <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
                    <svg className="w-4 h-4 text-[#00639d]" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" />
                    </svg>
                    AI 智能推荐
                </h4>
                <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                    <div className="text-gray-500">乐器</div>
                    <div className="font-medium text-gray-800">{ai.instrument || '—'}</div>
                    <div className="text-gray-500">速度 (BPM)</div>
                    <div className="font-medium text-gray-800">{ai.tempo ?? '—'}</div>
                    <div className="text-gray-500">时长 (秒)</div>
                    <div className="font-medium text-gray-800">{ai.duration ?? '—'}</div>
                    <div className="text-gray-500">风格标签</div>
                    <div className="font-medium text-gray-800">
                        {ai.style_tags?.length ? ai.style_tags.join(', ') : '—'}
                    </div>
                </div>
            </div>

            {/* 用户覆盖区 */}
            <div className="border border-gray-200 rounded-xl p-4">
                <div className="flex items-center justify-between mb-4">
                    <h4 className="text-sm font-semibold text-gray-700">个人偏好设置</h4>
                    {prefData?.user_overrides !== null && (
                        <button
                            onClick={handleReset}
                            disabled={saving}
                            className="text-xs text-red-500 hover:text-red-700 transition disabled:opacity-50"
                        >
                            恢复 AI 推荐
                        </button>
                    )}
                </div>

            {/*    /!* 是否使用 AI 推荐开关 *!/*/}
            {/*    <div className="flex items-center justify-between mb-5">*/}
            {/*        <span className="text-sm text-gray-700">使用 AI 智能推荐</span>*/}
            {/*        <button*/}
            {/*            onClick={() => setUseAi(!useAi)}*/}
            {/*            className={`relative inline-flex h-6 w-11 items-center rounded-full transition ${*/}
            {/*                useAi ? 'bg-[#00639d]' : 'bg-gray-300'*/}
            {/*            }`}*/}
            {/*        >*/}
            {/*<span*/}
            {/*    className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${*/}
            {/*        useAi ? 'translate-x-6' : 'translate-x-1'*/}
            {/*    }`}*/}
            {/*/>*/}
            {/*        </button>*/}
            {/*    </div>*/}

                {/* 当不使用 AI 推荐时，显示自定义表单 */}
                    <div className="space-y-4 mt-2">
                        {/* 乐器选择 */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">乐器</label>
                            <select
                                value={instrument}
                                onChange={(e) => setInstrument(e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-1 focus:ring-[#00639d] text-sm"
                            >
                                <option value="">不指定</option>
                                {GM_INSTRUMENTS.map((inst) => (
                                    <option key={inst} value={inst}>
                                        {t(`params.instruments.${inst}`, inst)}
                                    </option>
                                ))}
                            </select>
                        </div>

                        {/* 速度 */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">
                                速度 (BPM)
                            </label>
                            <input
                                type="number"
                                min="20"
                                max="300"
                                value={tempo ?? ''}
                                onChange={(e) => setTempo(e.target.value ? Number(e.target.value) : null)}
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                placeholder="自动"
                            />
                        </div>

                        {/* 时长 */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">
                                时长 (秒)
                            </label>
                            <input
                                type="number"
                                min="5"
                                max="60"
                                value={duration ?? ''}
                                onChange={(e) => setDuration(e.target.value ? Number(e.target.value) : null)}
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                placeholder="自动"
                            />
                        </div>

                        {/* 风格标签（逗号分隔） */}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">
                                风格标签（逗号分隔）
                            </label>
                            <input
                                type="text"
                                value={styleTagsStr}
                                onChange={(e) => setStyleTagsStr(e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                                placeholder="例如: 欢快, 钢琴, 电子"
                            />
                            <p className="text-xs text-gray-400 mt-1">
                                多个标签请用英文逗号分隔
                            </p>
                        </div>
                    </div>

                {/* 当前有效偏好提示 */}
                <div className="mt-5 pt-3 border-t border-gray-100 text-xs text-gray-400">
                    当前有效配置：
                    <span className="ml-1 font-medium text-gray-600">
            乐器 {effective.instrument || '自动'}，速度 {effective.tempo || '自动'} BPM，
            时长 {effective.duration || '自动'} 秒
                        {effective.style_tags?.length ? `，风格: ${effective.style_tags.join(', ')}` : ''}
          </span>
                </div>

                {/* 保存按钮 */}
                <button
                    onClick={handleSave}
                    disabled={saving}
                    className="mt-5 w-full py-2 bg-[#00639d] text-white rounded-lg hover:bg-[#005288] transition disabled:opacity-50"
                >
                    {saving ? '保存中...' : '保存个人偏好'}
                </button>
            </div>
        </div>
    );
}
