import type { GraphConfig } from '../types';

export function getAllEdges(config: GraphConfig): { from: string; to: string }[] {
    const edges = config.edges || [];
    const condEdges = (config.conditional_edges || []).flatMap(ce =>
        Object.values(ce.mapping).map(target => ({ from: ce.from, to: target }))
    );
    const defaultEdges = config.default_edges || [];
    return [...edges, ...condEdges, ...defaultEdges];
}

export function cascadeDisable(nodeId: string, disabledSet: Set<string>, edges: { from: string; to: string }[]): Set<string> {
    const newDisabled = new Set(disabledSet);
    const dfs = (id: string) => {
        if (newDisabled.has(id)) return;
        newDisabled.add(id);
        for (const edge of edges.filter(e => e.from === id)) {
            if (edges.filter(e => e.to === edge.to).every(e => newDisabled.has(e.from))) {
                dfs(edge.to);
            }
        }
    };
    dfs(nodeId);
    return newDisabled;
}

export function getEffectiveEdges(
    nodes: { id: string }[],
    edges: { from: string; to: string }[],
    disabled: Set<string>
): { from: string; to: string }[] {
    const remaining = edges.filter(e => !disabled.has(e.from) && !disabled.has(e.to));
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
    return remaining.filter(e => !disabled.has(e.from) && !disabled.has(e.to));
}

export function validateConnectivity(
    nodes: { id: string }[],
    edges: { from: string; to: string }[],
    entry: string,
    exit: string | undefined,
    disabled: Set<string>
): boolean {
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
        for (const nxt of adj.get(cur) || []) {
            if (!visited.has(nxt)) queue.push(nxt);
        }
    }
    const exitNodes = exit ? [exit] : nodes.filter(n => !adj.has(n.id) && enabledSet.has(n.id)).map(n => n.id);
    return exitNodes.some(ex => visited.has(ex));
}

export function generateConfigFromState(
    originalConfig: GraphConfig,
    disabled: Set<string>,
    effectiveEdges: { from: string; to: string }[]
): GraphConfig {
    const enabledNodes = originalConfig.nodes.filter(n => !disabled.has(n.id));
    const newConditionalEdges = (originalConfig.conditional_edges || []).map(ce => ({
        ...ce,
        mapping: Object.fromEntries(
            Object.entries(ce.mapping).filter(([_, target]) => !disabled.has(target as string))
        )
    })).filter(ce => Object.keys(ce.mapping).length > 0);

    return {
        ...originalConfig,
        nodes: enabledNodes,
        edges: effectiveEdges.filter(e => !disabled.has(e.from) && !disabled.has(e.to)),
        conditional_edges: newConditionalEdges,
        default_edges: (originalConfig.default_edges || []).filter(e => !disabled.has(e.from) && !disabled.has(e.to))
    };
}
