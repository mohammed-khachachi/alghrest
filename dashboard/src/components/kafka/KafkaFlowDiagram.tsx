import { TIER_COLORS } from '@/types/ws';

interface TierNode {
  id: number;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface FlowEdge {
  from: number;
  to: number;
  label: string;
}

const NODES: TierNode[] = [
  { id: 2, label: 'Intelligence\n(T2)', x: 30,  y: 40,  width: 110, height: 44 },
  { id: 3, label: 'Quant\n(T3)',        x: 30,  y: 130, width: 110, height: 44 },
  { id: 4, label: 'Strategies\n(T4)',   x: 200, y: 85,  width: 110, height: 44 },
  { id: 1, label: 'Executive\n(T1)',    x: 200, y: 190, width: 110, height: 44 },
  { id: 5, label: 'Execution\n(T5)',    x: 370, y: 85,  width: 110, height: 44 },
  { id: 6, label: 'DeFi\n(T6)',         x: 370, y: 190, width: 110, height: 44 },
  { id: 7, label: 'Monitoring\n(T7)',   x: 540, y: 130, width: 110, height: 44 },
];

const EDGES: FlowEdge[] = [
  { from: 2, to: 3, label: 'indicators' },
  { from: 2, to: 4, label: 'signals' },
  { from: 3, to: 4, label: 'patterns' },
  { from: 4, to: 1, label: 'proposals' },
  { from: 1, to: 5, label: 'approved' },
  { from: 1, to: 6, label: 'approved' },
  { from: 5, to: 7, label: 'fills' },
  { from: 6, to: 7, label: 'fills' },
  { from: 4, to: 7, label: 'risk.alerts' },
];

function nodeCenter(n: TierNode): { x: number; y: number } {
  return { x: n.x + n.width / 2, y: n.y + n.height / 2 };
}

export function KafkaFlowDiagram() {
  const nodeMap = new Map(NODES.map((n) => [n.id, n]));

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox="0 0 700 270"
        className="w-full max-w-2xl mx-auto"
        aria-label="Kafka message flow topology"
      >
        <defs>
          <marker
            id="arrow"
            markerWidth="6"
            markerHeight="6"
            refX="5"
            refY="3"
            orient="auto"
          >
            <path d="M0,0 L0,6 L6,3 z" fill="rgba(99,102,241,0.8)" />
          </marker>
          {/* Animated dash */}
          <style>{`
            .flow-path { stroke-dasharray: 6 4; animation: dash 1.4s linear infinite; }
            @keyframes dash { to { stroke-dashoffset: -20; } }
          `}</style>
        </defs>

        {/* Edges */}
        {EDGES.map((edge, i) => {
          const fromNode = nodeMap.get(edge.from);
          const toNode = nodeMap.get(edge.to);
          if (!fromNode || !toNode) return null;
          const fc = nodeCenter(fromNode);
          const tc = nodeCenter(toNode);
          const mx = (fc.x + tc.x) / 2;
          const my = (fc.y + tc.y) / 2;
          return (
            <g key={i}>
              <path
                d={`M${fc.x},${fc.y} L${tc.x},${tc.y}`}
                stroke="rgba(99,102,241,0.5)"
                strokeWidth="1.5"
                fill="none"
                markerEnd="url(#arrow)"
                className="flow-path"
              />
              <text
                x={mx}
                y={my - 4}
                textAnchor="middle"
                fill="#64748b"
                fontSize="8"
                fontFamily="JetBrains Mono, monospace"
              >
                {edge.label}
              </text>
            </g>
          );
        })}

        {/* Nodes */}
        {NODES.map((node) => {
          const color = TIER_COLORS[node.id] ?? '#64748b';
          const lines = node.label.split('\n');
          return (
            <g key={node.id}>
              <rect
                x={node.x}
                y={node.y}
                width={node.width}
                height={node.height}
                rx={8}
                fill={`${color}15`}
                stroke={color}
                strokeWidth="1.5"
              />
              {lines.map((line, li) => (
                <text
                  key={li}
                  x={node.x + node.width / 2}
                  y={node.y + 16 + li * 14}
                  textAnchor="middle"
                  fill={li === 0 ? '#fff' : color}
                  fontSize={li === 0 ? 11 : 9}
                  fontWeight={li === 0 ? '600' : '400'}
                  fontFamily="Inter, sans-serif"
                >
                  {line}
                </text>
              ))}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
