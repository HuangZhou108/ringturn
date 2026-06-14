// frontend/src/components/profile_settings/GraphViewer.tsx
import React, { useEffect, useState, useCallback } from 'react';
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

interface GraphViewerProps {
    graphConfig: {
        nodes: { id: string; type?: string }[];
        edges: { from: string; to: string }[];
        conditional_edges?: { from: string; mapping: Record<string, string> }[];
        entry?: string;
        height?: number | string; // 允许 string 如 "100%"
    };
    height?: number;
}

// 节点样式（保持原有）
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

// 使用 dagre 进行自动布局
function getLayoutedElements(
    nodes: { id: string; type?: string }[],
    edges: Edge[]
): { nodes: Node[]; edges: Edge[] } {
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    // 设置布局方向：TB = 从上到下，LR = 从左到右（根据执行顺序，TB 更符合数据流方向）
    dagreGraph.setGraph({ rankdir: 'TB', align: 'UL', nodesep: 60, ranksep: 70 });

    // 添加节点，设置宽度和高度
    const nodeWidth = 120;
    const nodeHeight = 50;
    nodes.forEach((node) => {
        dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
    });

    // 添加边
    edges.forEach((edge) => {
        dagreGraph.setEdge(edge.source, edge.target);
    });

    // 执行布局计算
    dagre.layout(dagreGraph);

    // 生成带位置的节点
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
            ...(node.type ? { type: node.type } : {}),
        };
    });

    return { nodes: layoutedNodes, edges };
}

export default function GraphViewer({ graphConfig, height = 400 }: GraphViewerProps) {
    const [nodes, setNodes] = useNodesState([]);
    const [edges, setEdges] = useEdgesState([]);

    useEffect(() => {
        if (graphConfig && graphConfig.nodes) {
            const conditionalEdgeKeys = new Set<string>();
            graphConfig.conditional_edges?.forEach(ce => {
                Object.values(ce.mapping).forEach(target => {
                    conditionalEdgeKeys.add(`${ce.from}->${target}`);
                });
            });

            // 合并普通边和条件边的源-目标对（用于布局）
            const allEdges = [
                ...(graphConfig.edges || []),
                ...(graphConfig.conditional_edges?.flatMap(ce =>
                    Object.values(ce.mapping).map(target => ({ from: ce.from, to: target }))
                ) || []),
            ];

            // 构建基本边（包含完整样式，不再依赖后续映射）
            const basicEdges: Edge[] = allEdges.map((edge) => {
                const edgeKey = `${edge.from}->${edge.to}`;
                const isConditional = conditionalEdgeKeys.has(edgeKey);
                return {
                    id: edgeKey,   // 使用干净的 from->to 作为 id
                    source: edge.from,
                    target: edge.to,
                    animated: isConditional,          // 条件边带动画
                    style: {
                        stroke: isConditional ? '#3b82f6' : '#94a3b8',
                        strokeWidth: 2,
                        ...(isConditional ? { strokeDasharray: '5,5' } : {}),
                    },
                    markerEnd: { type: 'arrowclosed', color: isConditional ? '#3b82f6' : '#64748b' },
                };
            });

            // 执行布局
            const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
                graphConfig.nodes,
                basicEdges
            );

            setNodes(layoutedNodes);
            setEdges(layoutedEdges);
        }
    }, [graphConfig, setNodes, setEdges]);

    // 交互事件（保持原有）
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

    const [showFullscreen, setShowFullscreen] = useState(false);

    return (
        <>
            <div style={{
                height: typeof height === 'number' ? `${height}px` : height,
                width: '100%',
                border: '1px solid #e2e8f0',
                borderRadius: '12px',
                background: '#fafcff',
                position: 'relative'
            }}>
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
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
                        <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
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
