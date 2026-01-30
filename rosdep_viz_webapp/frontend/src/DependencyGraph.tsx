import { useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { TreeNode } from './types'

const NODE_WIDTH = 200
const HORIZONTAL_GAP = 80
const VERTICAL_GAP = 24

function buildLayout(tree: TreeNode): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = []
  const edges: Edge[] = []
  let idGen = 0
  const makeId = () => `n${idGen++}`

  function layout(node: TreeNode, parentId: string | null, x: number, y: number): number {
    const id = makeId()
    nodes.push({
      id,
      type: 'default',
      position: { x, y },
      data: {
        label: (
          <div className="px-3 py-2 min-w-[180px] rounded-lg border border-edge bg-surface-muted">
            <div className="font-semibold text-accent truncate" title={node.name}>
              {node.name}
            </div>
            <div className="text-xs text-slate-400 truncate" title={node.description || node.path}>
              {node.version ? `v${node.version}` : ''}{' '}
              {node.description ? '— ' + node.description : ''}
            </div>
          </div>
        ),
        pkg: node,
      },
    })
    if (parentId) edges.push({ id: `e-${parentId}-${id}`, source: parentId, target: id })
    let nextY = y
    for (const child of node.children) {
      nextY = layout(child, id, x + NODE_WIDTH + HORIZONTAL_GAP, nextY)
      nextY += VERTICAL_GAP
    }
    return nextY
  }
  layout(tree, null, 0, 0)
  return { nodes, edges }
}

type Props = { tree: TreeNode }

export function DependencyGraph({ tree }: Props) {
  const { nodes, edges } = useMemo(() => buildLayout(tree), [tree])

  return (
    <div className="w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        className="bg-surface"
        defaultEdgeOptions={{ type: 'smoothstep' }}
      >
        <Background color="#334155" gap={16} />
        <Controls className="!bg-surface-elevated !border-edge" />
        <MiniMap
          nodeColor="#22d3ee"
          maskColor="rgba(15, 20, 25, 0.8)"
          className="!bg-surface-elevated !border-edge"
        />
      </ReactFlow>
    </div>
  )
}
