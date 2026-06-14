// frontend/src/components/profile_settings/ToolPreferencePanel.tsx
import { useState, useEffect } from 'react';
import { getToolPreference, updateToolPreference, deleteToolPreference } from '../../api/profile';
import GraphViewer from './GraphViewer';

interface ToolPreferencePanelProps {
    profileId: number;
    t: (key: string) => string;
}

// 后端支持的所有图名称
const GRAPHS = ['analysis', 'extract', 'arrange', 'render', 'reflect', 'quality'];

export default function ToolPreferencePanel({ profileId, t }: ToolPreferencePanelProps) {
    const [selectedGraph, setSelectedGraph] = useState<string>(GRAPHS[0]);
    const [configs, setConfigs] = useState<Record<string, any>>({});
    const [loading, setLoading] = useState<Record<string, boolean>>({});
    const [defaultGraphData, setDefaultGraphData] = useState<any>(null);
    const [loadingGraph, setLoadingGraph] = useState(false);
    const [resetting, setResetting] = useState(false);

    // 加载默认图 JSON
    const loadDefaultGraph = async (graphName: string) => {
        setLoadingGraph(true);
        try {
            const res = await fetch(`/tool_graphs/${graphName}_graph.json`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setDefaultGraphData(data);
        } catch (err) {
            console.error(`加载默认图 ${graphName} 失败:`, err);
            setDefaultGraphData(null);
        } finally {
            setLoadingGraph(false);
        }
    };

    useEffect(() => {
        loadDefaultGraph(selectedGraph);
    }, [selectedGraph]);

    // 加载自定义配置（用于判断是否已自定义）
    const loadConfig = async (graphName: string) => {
        setLoading((prev) => ({ ...prev, [graphName]: true }));
        try {
            const res = await getToolPreference(profileId, graphName);
            setConfigs((prev) => ({ ...prev, [graphName]: res.data?.config || null }));
        } catch (err) {
            console.error(`加载 ${graphName} 配置失败:`, err);
            setConfigs((prev) => ({ ...prev, [graphName]: null }));
        } finally {
            setLoading((prev) => ({ ...prev, [graphName]: false }));
        }
    };

    // 初始加载所有图的配置（并行）
    useEffect(() => {
        GRAPHS.forEach((g) => loadConfig(g));
    }, [profileId]);

    const isCustom = configs[selectedGraph] !== null && configs[selectedGraph] !== undefined;

    // 重置为默认（删除自定义配置）
    const handleReset = async () => {
        if (!selectedGraph) return;
        if (!confirm(`确定要重置 "${selectedGraph}" 图的配置吗？将恢复为默认设置。`)) return;
        setResetting(true);
        try {
            await deleteToolPreference(profileId, selectedGraph);
            await loadConfig(selectedGraph);
        } catch (err) {
            console.error('重置失败:', err);
            alert('重置失败，请稍后重试');
        } finally {
            setResetting(false);
        }
    };

    return (
        <div className="flex flex-col h-full overflow-hidden">
            {/* 顶部标签栏 */}
            <div className="flex flex-nowrap overflow-x-auto gap-2 mb-4 border-b border-gray-200 pb-2 whitespace-nowrap">
                {GRAPHS.map((graph) => (
                    <button
                        key={graph}
                        onClick={() => setSelectedGraph(graph)}
                        className={`
                            px-3 py-1.5 text-sm font-medium rounded-md transition
                            ${selectedGraph === graph
                            ? 'bg-[#00639d] text-white shadow-sm'
                            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                        }
                        `}
                    >
                        {graph.charAt(0).toUpperCase() + graph.slice(1)}
                    </button>
                ))}
            </div>

            {/* 状态提示（放在图上方，深绿色） */}
            <div className="text-xs text-green-700 mb-2">
                {isCustom ? (
                    <span>⚙️ 已自定义配置</span>
                ) : (
                    <span>✓ 使用默认配置</span>
                )}
            </div>

            {/* 图形查看器 */}
            <div className="flex-1 min-h-0 relative">
                {loadingGraph ? (
                    <div className="flex items-center justify-center h-full bg-gray-50 rounded-lg">
                        <div className="w-6 h-6 border-2 border-[#00639d] border-t-transparent rounded-full animate-spin"></div>
                    </div>
                ) : defaultGraphData ? (
                    <GraphViewer graphConfig={defaultGraphData} height="100%" />
                ) : (
                    <div className="flex items-center justify-center h-full bg-gray-50 rounded-lg text-gray-400 text-sm">
                        无法加载图结构
                    </div>
                )}
            </div>

            {/* 重置按钮（仅当已自定义时显示） */}
            {isCustom && (
                <div className="flex justify-end">
                    <button
                        onClick={handleReset}
                        disabled={resetting}
                        className="px-4 py-2 border border-red-300 text-red-600 rounded-lg hover:bg-red-50 disabled:opacity-50 transition"
                    >
                        {resetting ? '重置中...' : '重置为默认'}
                    </button>
                </div>
            )}
        </div>
    );
}
