// frontend/src/components/profile_settings/ToolPreferencePanel.tsx
import { useState, useEffect } from 'react';
import { getToolPreference } from '../../api/profile';
import GraphViewer from './GraphViewer';

interface ToolPreferencePanelProps {
    profileId: number;
    t: (key: string) => string;
}

const GRAPHS = ['analysis', 'extract', 'arrange']
// 后续按需开放
// const GRAPHS = ['analysis', 'extract', 'arrange', 'render', 'reflect', 'quality'];

export default function ToolPreferencePanel({ profileId, t }: ToolPreferencePanelProps) {
    const [selectedGraph, setSelectedGraph] = useState<string>(GRAPHS[0]);
    const [graphConfig, setGraphConfig] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchGraphConfig = async (graphName: string) => {
        if (!profileId) {
            setError('无有效 Profile ID');
            return;
        }
        setLoading(true);
        setError(null);
        try {
            // 1. 优先尝试获取后端保存的自定义配置
            const customRes = await getToolPreference(profileId, graphName);
            if (customRes.code === 200 && customRes.data) {
                setGraphConfig(customRes.data);
                return;
            }

            // 2. 无自定义配置，则加载默认 JSON 文件
            const response = await fetch(`/tool_graphs/${graphName}_graph.json`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            const defaultConfig = await response.json();
            setGraphConfig(defaultConfig);
        } catch (err) {
            console.error(`加载图配置失败 (${graphName}):`, err);
            setError(`加载失败: ${err instanceof Error ? err.message : '未知错误'}`);
            setGraphConfig(null);
        } finally {
            setLoading(false);
        }
    };

    // 当选择的图或 profileId 变化时重新加载
    useEffect(() => {
        fetchGraphConfig(selectedGraph);
    }, [selectedGraph, profileId]);

    const handleSaveSuccess = () => {
        // 保存成功后重新加载当前图，以显示最新配置
        fetchGraphConfig(selectedGraph);
    };

    return (
        <div className="flex flex-col h-full overflow-hidden">
            {/* 图切换标签栏 */}
            <div className="flex flex-nowrap overflow-x-auto gap-2 mb-4 border-b border-gray-200 pb-2 whitespace-nowrap">
                {GRAPHS.map((graph) => (
                    <button
                        key={graph}
                        onClick={() => setSelectedGraph(graph)}
                        className={`px-3 py-1.5 text-sm font-medium rounded-md transition ${
                            selectedGraph === graph
                                ? 'bg-[#00639d] text-white shadow-sm'
                                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                        }`}
                    >
                        {graph.charAt(0).toUpperCase() + graph.slice(1)}
                    </button>
                ))}
            </div>

            {/* 内容区域 */}
            <div className="flex-1 min-h-0 relative">
                {loading && (
                    <div className="flex items-center justify-center h-full bg-gray-50 rounded-lg">
                        <div className="w-6 h-6 border-2 border-[#00639d] border-t-transparent rounded-full animate-spin"></div>
                    </div>
                )}
                {!loading && error && (
                    <div className="flex items-center justify-center h-full bg-gray-50 rounded-lg text-red-500 text-sm">
                        {error}
                    </div>
                )}
                {!loading && !error && graphConfig && (
                    <GraphViewer
                        graphConfig={graphConfig}
                        profileId={profileId}
                        graphName={selectedGraph}
                        height="100%"
                        onSaveSuccess={handleSaveSuccess}
                    />
                )}
                {!loading && !error && !graphConfig && (
                    <div className="flex items-center justify-center h-full bg-gray-50 rounded-lg text-gray-400 text-sm">
                        无法加载图结构
                    </div>
                )}
            </div>
        </div>
    );
}
