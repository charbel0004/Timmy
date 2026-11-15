import { useMemo } from 'react';
import { Background, Controls, MiniMap, ReactFlow, Position } from '@xyflow/react';
import { useReducedMotion } from 'motion/react';
import { criticalPath } from './execution-model';
import type { SpanView } from './execution-model';
import '@xyflow/react/dist/style.css';
const numeric = (value: number, suffix = '') => value.toLocaleString(undefined, { maximumFractionDigits: 1 }) + suffix;
export default function ExecutionGraph({ runId, spans, filtered, onSelect, onCollapse }: {
  runId: string; spans: SpanView[]; filtered: SpanView[]; onSelect: (id: string) => void; onCollapse: (id: string) => void;
}) {
  const reduced = useReducedMotion();
  const graph = useMemo(() => {
    const critical = criticalPath(spans);
    const depth = new Map<string, number>(), rows = new Map<number, number>();
    const longest = spans.filter((s) => s.category !== 'request' && s.duration !== undefined).reduce<SpanView | undefined>((a, b) => (a?.duration ?? -1) > (b.duration ?? -1) ? a : b, undefined);
    const visible = new Set(filtered.map((s) => s.id));
    return { nodes: filtered.map((s) => {
      const d = Math.max(s.parent ? (depth.get(s.parent) ?? 0) + 1 : 0, ...s.dependencies.map(dep => (depth.get(dep) ?? 0) + 1)); depth.set(s.id, d);
      const row = rows.get(d) ?? 0; rows.set(d, row + 1);
      return { id: s.id, position: { x: d * 275, y: row * 135 }, sourcePosition: Position.Right, targetPosition: Position.Left,
        className: `execution-node state-${s.status}${longest?.id === s.id ? ' longest-operation' : ''}${critical.has(s.id) ? ' critical-operation' : ''}`,
        data: { label: <><span className="node-category">{s.category.replaceAll('_', ' ')}</span><strong>{s.operation}</strong><span className="node-state">{s.status} {s.duration !== undefined && `· ${numeric(s.duration, ' ms')}`}</span></> } };
    }), edges: [...filtered.filter((s) => s.parent && visible.has(s.parent)).map((s) => ({ id: `${s.parent}-${s.id}`, source: s.parent!, target: s.id,
      animated: s.status === 'running' && !reduced, style: { stroke: s.status === 'failed' ? '#f87171' : '#64748b', strokeDasharray: '4 4' } })),
      ...filtered.flatMap(s => s.dependencies.filter(dep => visible.has(dep)).map(dep => ({ id: `dependency-${dep}-${s.id}`, source: dep, target: s.id, label: 'depends on', animated: s.status === 'running' && !reduced, style: { stroke: critical.has(s.id) && critical.has(dep) ? '#38bdf8' : '#64748b' } }))) ] };
  }, [filtered, spans, reduced]);
  return <div className="flow-viewport"><ReactFlow colorMode="light" key={runId} nodes={graph.nodes} edges={graph.edges} fitView minZoom={0.1} maxZoom={2} onlyRenderVisibleElements
    nodesDraggable={false} nodesConnectable={false} onNodeClick={(_event, node) => onSelect(node.id)} onNodeDoubleClick={(_event, node) => onCollapse(node.id)}>
    <Background gap={24} color="#94a3b825" /><MiniMap pannable zoomable /><Controls showInteractive={false} />
  </ReactFlow></div>;
}
