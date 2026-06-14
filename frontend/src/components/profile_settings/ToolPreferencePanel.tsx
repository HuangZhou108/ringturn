// frontend/src/components/profile_settings/ToolPreferencePanel.tsx
import { useState, useEffect } from 'react';
import { getToolPreference, updateToolPreference, deleteToolPreference } from '../../api/profile';
import GraphViewer from './GraphViewer';

interface ToolPreferencePanelProps {
    profileId: number;
    t: (key: string) => string;
}

const GRAPHS = ['analysis', 'extract', 'arrange', 'render', 'reflect', 'quality'];

export default function ToolPreferencePanel({ profileId, t }: ToolPreferencePanelProps) {
    const [selectedGraph, setSelectedGraph] = useState<string>(GRAPHS[0]);
    const [defaultGraphData, setDefaultGraphData] = useState<any>(null);
    const [loadingGraph, setLoadingGraph] = useState(false);

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

    return (
        <div className="flex flex-col h-full overflow-hidden">
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

            <div className="flex-1 min-h-0 relative">
                {loadingGraph ? (
                    <div className="flex items-center justify-center h-full bg-gray-50 rounded-lg">
                        <div className="w-6 h-6 border-2 border-[#00639d] border-t-transparent rounded-full animate-spin"></div>
                    </div>
                ) : defaultGraphData ? (
                    <GraphViewer
                        graphConfig={defaultGraphData}
                        profileId={profileId}
                        graphName={selectedGraph}
                        height="100%"
                        onSaveSuccess={() => {
                            // 保存成功后可选刷新
                        }}
                    />
                ) : (
                    <div className="flex items-center justify-center h-full bg-gray-50 rounded-lg text-gray-400 text-sm">
                        无法加载图结构
                    </div>
                )}
            </div>
        </div>
    );
}
