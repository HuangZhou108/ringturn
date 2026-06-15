// frontend/src/components/profile_settings/GraphViewer.tsx
import React, { useEffect, useState, useCallback, useRef } from 'react';
import ReactFlow, {
    type Node,
    type Edge,
    Background,
    Controls,
    MiniMap,
    useNodesState,
    useEdgesState,
    type OnNodesChange,
    type OnEdgesChange,
    applyNodeChanges,
    applyEdgeChanges,
} from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import { updateToolPreference } from '../../api/profile';

interface GraphViewerProps {
    graphConfig: {
        nodes: { id: string; type?: string }[];
        edges?: { from: string; to: string }[];
        conditional_edges?: { from: string; mapping: Record<string, string> }[];
        default_edges?: { from: string; to: string }[];
        entry?: string;
        exit?: string;
        height?: number | string;
    };
    profileId: number;
    graphName: string;
    height?: number;
    onSaveSuccess?: () => void;
}

// 节点样式
const nodeStyle = (selected: boolean = false) => ({
    background: selected ? '#e0f2fe' : '#f0f9ff',
    border: `1px solid ${selected ? '#0284c7' : '#94a3b8'}`,
    borderRadius: '8px',
    padding: '8px 12px',
    fontSize: '12px',
    fontWeight: 500,
    color: '#0c4a6e',
    boxShadow: selected ? '0 0 0 2px #0ea5e9, 0 0 8px rgba(2,132,199,0.5)' : 'none',
    transition: 'all 0.2s ease',
});

const hoverStyle = {
    boxShadow: '0 0 0 2px #3b82f6, 0 0 12px rgba(59,130,246,0.4)',
    borderColor: '#2563eb',
    cursor: 'pointer',
};

// dagre 布局
function getLayoutedElements(
    nodes: { id: string }[],
    edges: Edge[]
): { nodes: Node[]; edges: Edge[] } {
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    dagreGraph.setGraph({ rankdir: 'TB', align: 'UL', nodesep: 60, ranksep: 70 });

    const nodeWidth = 120;
    const nodeHeight = 50;
    nodes.forEach((node) => {
        dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
    });
    edges.forEach((edge) => {
        dagreGraph.setEdge(edge.source, edge.target);
    });
    dagre.layout(dagreGraph);

    const layoutedNodes = nodes.map((node) => {
        const nodeWithPosition = dagreGraph.node(node.id);
        return {
            id: node.id,
            data: { label: node.id },
            position: {
                x: nodeWithPosition.x - nodeWidth / 2,
                y: nodeWithPosition.y - nodeHeight / 2,
            },
            style: nodeStyle(false),
        };
    });
    return { nodes: layoutedNodes, edges };
}

export default function GraphViewer({ graphConfig, profileId, graphName, height = 400, onSaveSuccess }: GraphViewerProps) {
    const [nodes, setNodes] = useNodesState([]);
    const [edges, setEdges] = useEdgesState([]);
    const [disabledNodes, setDisabledNodes] = useState<Set<string>>(new Set());
    const [isValid, setIsValid] = useState(true);
    const [editMode, setEditMode] = useState(false);
    const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
    const [saving, setSaving] = useState(false);
    const [currentConfig, setCurrentConfig] = useState<any>(null);
    const [showFullscreen, setShowFullscreen] = useState(false);
    const initialLoadRef = useRef(false);

    // 获取所有边的原始定义（不包括重连逻辑）
    const getAllEdges = useCallback((config: GraphViewerProps['graphConfig']) => {
        const edges = config.edges || [];
        const condEdges = (config.conditional_edges || []).flatMap(ce =>
            Object.values(ce.mapping).map(target => ({ from: ce.from, to: target }))
        );
        const defaultEdges = config.default_edges || [];
        return [...edges, ...condEdges, ...defaultEdges];
    }, []);

    // 根据禁用集生成有效边（串行节点自动重连）
    const getEffectiveEdges = useCallback((nodes: { id: string }[], edges: { from: string; to: string }[], disabled: Set<string>) => {
        let remaining = edges.filter(e => !disabled.has(e.from) && !disabled.has(e.to));
        for (const nodeId of disabled) {
            const inEdges = remaining.filter(e => e.to === nodeId);
            const outEdges = remaining.filter(e => e.from === nodeId);
            if (inEdges.length === 1 && outEdges.length === 1) {
                const pred = inEdges[0].from;
                const succ = outEdges[0].to;
                if (!remaining.some(e => e.from === pred && e.to === succ)) {
                    remaining.push({ from: pred, to: succ });
                }
            }
        }
        remaining = remaining.filter(e => !disabled.has(e.from) && !disabled.has(e.to));
        return remaining;
    }, []);

    // 连通性验证
    const validateConnectivity = useCallback((nodes: { id: string }[], edges: { from: string; to: string }[], entry: string, exit: string | undefined, disabled: Set<string>) => {
        const enabledSet = new Set(nodes.map(n => n.id).filter(id => !disabled.has(id)));
        if (!enabledSet.has(entry)) return false;

        const adj = new Map<string, string[]>();
        for (const e of edges) {
            if (enabledSet.has(e.from) && enabledSet.has(e.to)) {
                if (!adj.has(e.from)) adj.set(e.from, []);
                adj.get(e.from)!.push(e.to);
            }
        }

        const queue = [entry];
        const visited = new Set<string>();
        while (queue.length) {
            const cur = queue.shift()!;
            if (visited.has(cur)) continue;
            visited.add(cur);
            const out = adj.get(cur) || [];
            for (const nxt of out) {
                if (!visited.has(nxt)) queue.push(nxt);
            }
        }
        const exitNodes = exit ? [exit] : nodes.filter(n => !adj.has(n.id) && enabledSet.has(n.id)).map(n => n.id);
        return exitNodes.some(ex => visited.has(ex));
    }, []);

    // 生成保存的图配置
    const generateConfigFromState = useCallback((originalConfig: any, disabled: Set<string>, effectiveEdges: any[]) => {
        const enabledNodes = originalConfig.nodes.filter((n: any) => !disabled.has(n.id));
        const newConditionalEdges = (originalConfig.conditional_edges || []).map((ce: any) => ({
            ...ce,
            mapping: Object.fromEntries(
                Object.entries(ce.mapping).filter(([_, target]) => !disabled.has(target as string))
            )
        })).filter((ce: any) => Object.keys(ce.mapping).length > 0);

        return {
            ...originalConfig,
            nodes: enabledNodes,
            edges: effectiveEdges.filter(e => !disabled.has(e.from) && !disabled.has(e.to)),
            conditional_edges: newConditionalEdges,
            default_edges: (originalConfig.default_edges || []).filter((e: any) => !disabled.has(e.from) && !disabled.has(e.to))
        };
    }, []);

    // 级联禁用
    const cascadeDisable = useCallback((nodeId: string, allEdges: { from: string; to: string }[]) => {
        const newDisabled = new Set(disabledNodes);
        const dfs = (id: string) => {
            if (newDisabled.has(id)) return;
            newDisabled.add(id);
            const outEdges = allEdges.filter(e => e.from === id);
            for (const edge of outEdges) {
                const inEdges = allEdges.filter(e => e.to === edge.to);
                if (inEdges.every(e => newDisabled.has(e.from))) {
                    dfs(edge.to);
                }
            }
        };
        dfs(nodeId);
        return newDisabled;
    }, [disabledNodes]);

    // 切换节点禁用状态
    const toggleNode = useCallback((nodeId: string) => {
        const allEdges = getAllEdges(graphConfig);
        let newDisabled: Set<string>;
        if (disabledNodes.has(nodeId)) {
            newDisabled = new Set(disabledNodes);
            newDisabled.delete(nodeId);
        } else {
            newDisabled = cascadeDisable(nodeId, allEdges);
        }
        setDisabledNodes(newDisabled);
        setHasUnsavedChanges(true);

        const effectiveEdges = getEffectiveEdges(graphConfig.nodes, allEdges, newDisabled);
        const connectivityOk = validateConnectivity(
            graphConfig.nodes,
            effectiveEdges,
            graphConfig.entry || graphConfig.nodes[0]?.id || '',
            graphConfig.exit,
            newDisabled
        );
        setIsValid(connectivityOk);

        const newConfig = generateConfigFromState(graphConfig, newDisabled, effectiveEdges);
        setCurrentConfig(newConfig);
    }, [disabledNodes, graphConfig, getAllEdges, cascadeDisable, getEffectiveEdges, validateConnectivity, generateConfigFromState]);

    // 重置为默认状态（清除所有禁用）
    const loadDefaultConfig = useCallback(() => {
        setDisabledNodes(new Set());
        setHasUnsavedChanges(false);
        const allEdges = getAllEdges(graphConfig);
        const effectiveEdges = getEffectiveEdges(graphConfig.nodes, allEdges, new Set());
        const connectivityOk = validateConnectivity(
            graphConfig.nodes,
            effectiveEdges,
            graphConfig.entry || graphConfig.nodes[0]?.id || '',
            graphConfig.exit,
            new Set()
        );
        setIsValid(connectivityOk);
        const defaultConfig = generateConfigFromState(graphConfig, new Set(), effectiveEdges);
        setCurrentConfig(defaultConfig);
    }, [graphConfig, getAllEdges, getEffectiveEdges, validateConnectivity, generateConfigFromState]);

    // 保存配置
    const handleSave = async () => {
        if (!currentConfig) return;
        setSaving(true);
        try {
            await updateToolPreference(profileId, graphName, currentConfig);
            setHasUnsavedChanges(false);
            alert('保存成功');
            onSaveSuccess?.();
        } catch (err) {
            console.error('保存失败', err);
            alert('保存失败');
        } finally {
            setSaving(false);
        }
    };

    // 退出编辑模式
    const handleExitEditMode = () => {
        if (hasUnsavedChanges) {
            if (confirm('有未保存的修改，是否保存？')) {
                handleSave();
            } else {
                loadDefaultConfig();
            }
        }
        setEditMode(false);
    };

    // 初次加载时生成默认 config
    useEffect(() => {
        if (!initialLoadRef.current && graphConfig) {
            loadDefaultConfig();
            initialLoadRef.current = true;
        }
    }, [graphConfig, loadDefaultConfig]);

    // 根据禁用集动态渲染图（包含条件边样式）
    useEffect(() => {
        if (!graphConfig || !graphConfig.nodes) return;
        const allEdges = getAllEdges(graphConfig);
        const effectiveEdges = getEffectiveEdges(graphConfig.nodes, allEdges, disabledNodes);
        const enabledNodes = graphConfig.nodes.filter(n => !disabledNodes.has(n.id));

        // 构建条件边标识集合
        const conditionalEdgeKeys = new Set<string>();
        graphConfig.conditional_edges?.forEach(ce => {
            Object.values(ce.mapping).forEach(target => {
                conditionalEdgeKeys.add(`${ce.from}->${target}`);
            });
        });

        const basicEdges: Edge[] = effectiveEdges.map(edge => {
            const edgeKey = `${edge.from}->${edge.to}`;
            const isConditional = conditionalEdgeKeys.has(edgeKey);
            return {
                id: edgeKey,
                source: edge.from,
                target: edge.to,
                animated: isConditional,
                style: {
                    stroke: isConditional ? '#3b82f6' : '#94a3b8',
                    strokeWidth: 2,
                    ...(isConditional ? { strokeDasharray: '5,5' } : {}),
                },
                markerEnd: { type: 'arrowclosed', color: isConditional ? '#3b82f6' : '#64748b' },
            };
        });

        const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(enabledNodes, basicEdges);
        setNodes(layoutedNodes);
        setEdges(layoutedEdges);
    }, [graphConfig, disabledNodes, getAllEdges, getEffectiveEdges]);

    // 交互事件
    const onNodeMouseEnter = useCallback((_: React.MouseEvent, node: Node) => {
        setNodes((nds) =>
            nds.map((n) => {
                if (n.id === node.id) {
                    return { ...n, style: { ...nodeStyle(true), ...hoverStyle } };
                }
                return n;
            })
        );
    }, [setNodes]);

    const onNodeMouseLeave = useCallback((_: React.MouseEvent, node: Node) => {
        setNodes((nds) =>
            nds.map((n) => {
                if (n.id === node.id) {
                    return { ...n, style: nodeStyle(false) };
                }
                return n;
            })
        );
    }, [setNodes]);

    const onEdgeMouseEnter = useCallback((_: React.MouseEvent, edge: Edge) => {
        setEdges((eds) =>
            eds.map((e) => {
                if (e.id === edge.id) {
                    return {
                        ...e,
                        style: { ...e.style, strokeWidth: 4, stroke: '#1d4ed8' },
                        markerEnd: { ...e.markerEnd, color: '#1d4ed8' },
                    };
                }
                return e;
            })
        );
    }, [setEdges]);

    const onEdgeMouseLeave = useCallback((_: React.MouseEvent, edge: Edge) => {
        setEdges((eds) =>
            eds.map((e) => {
                if (e.id === edge.id) {
                    const isConditional = e.animated || e.style?.strokeDasharray;
                    return {
                        ...e,
                        style: {
                            ...e.style,
                            strokeWidth: 2,
                            stroke: isConditional ? '#3b82f6' : '#94a3b8',
                            strokeDasharray: isConditional ? '5,5' : undefined,
                        },
                        markerEnd: { ...e.markerEnd, color: isConditional ? '#3b82f6' : '#64748b' },
                    };
                }
                return e;
            })
        );
    }, [setEdges]);

    const onNodesChange: OnNodesChange = useCallback((changes) => {
        setNodes((nds) => applyNodeChanges(changes, nds));
    }, [setNodes]);

    const onEdgesChange: OnEdgesChange = useCallback((changes) => {
        setEdges((eds) => applyEdgeChanges(changes, eds));
    }, [setEdges]);

    if (!graphConfig || !graphConfig.nodes) {
        return <div className="flex items-center justify-center h-[400px] text-gray-400">暂无图结构数据</div>;
    }

    return (
        <>
            {/* 控制栏 */}
            <div className="absolute top-2 left-2 z-10 flex gap-2 bg-white/80 p-2 rounded shadow">
                <button
                    onClick={() => setEditMode(true)}
                    className={`px-3 py-1 rounded ${editMode ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}
                >
                    编辑模式
                </button>
                {editMode && (
                    <>
                        <button
                            onClick={handleSave}
                            disabled={!hasUnsavedChanges || !isValid || saving}
                            className="px-3 py-1 bg-green-600 text-white rounded disabled:opacity-50"
                        >
                            {saving ? '保存中...' : '保存'}
                        </button>
                        <button
                            onClick={handleExitEditMode}
                            className="px-3 py-1 bg-gray-400 text-white rounded"
                        >
                            退出
                        </button>
                        {!isValid && (
                            <span className="text-red-600 text-sm">⚠️ 当前配置无效，无法保存</span>
                        )}
                    </>
                )}
            </div>
            <div
                style={{
                    height: typeof height === 'number' ? `${height}px` : height,
                    width: '100%',
                    border: '1px solid #e2e8f0',
                    borderRadius: '12px',
                    background: '#fafcff',
                    position: 'relative',
                }}
            >
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodeClick={editMode ? (_, node) => toggleNode(node.id) : undefined}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onNodeMouseEnter={onNodeMouseEnter}
                    onNodeMouseLeave={onNodeMouseLeave}
                    onEdgeMouseEnter={onEdgeMouseEnter}
                    onEdgeMouseLeave={onEdgeMouseLeave}
                    fitView
                    attributionPosition="bottom-right"
                    minZoom={0.5}
                    maxZoom={1.5}
                >
                    <Background color="#cbd5e1" gap={16} />
                    <Controls />
                </ReactFlow>
                <button
                    onClick={() => setShowFullscreen(true)}
                    className="absolute top-2 right-2 z-10 p-1.5 bg-white rounded-full shadow-md hover:bg-gray-100 transition"
                    title="放大查看"
                >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
                    </svg>
                </button>
            </div>

            {showFullscreen && (
                <div
                    className="fixed inset-0 z-[100] bg-black/50 flex items-center justify-center p-8"
                    onClick={() => setShowFullscreen(false)}
                >
                    <div
                        className="bg-white rounded-xl w-[90vw] h-[85vh] relative"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <button
                            onClick={() => setShowFullscreen(false)}
                            className="absolute top-2 right-2 z-10 p-2 bg-white rounded-full shadow-md hover:bg-gray-100"
                        >
                            ✕
                        </button>
                        <div style={{ width: '100%', height: '100%' }}>
                            <ReactFlow
                                nodes={nodes}
                                edges={edges}
                                onNodeClick={editMode ? (_, node) => toggleNode(node.id) : undefined}
                                onNodesChange={onNodesChange}
                                onEdgesChange={onEdgesChange}
                                onNodeMouseEnter={onNodeMouseEnter}
                                onNodeMouseLeave={onNodeMouseLeave}
                                onEdgeMouseEnter={onEdgeMouseEnter}
                                onEdgeMouseLeave={onEdgeMouseLeave}
                                fitView
                                attributionPosition="bottom-right"
                                minZoom={0.5}
                                maxZoom={2}
                            >
                                <Background color="#cbd5e1" gap={16} />
                                <Controls />
                                <MiniMap nodeStrokeWidth={3} zoomable pannable />
                            </ReactFlow>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
