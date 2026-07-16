import { h } from 'preact';
import { useState, useEffect, useRef } from 'preact/hooks';
import G6 from '@antv/g6';

type ViewMode = 'document' | 'entity' | 'timeline';

export function WikiGraph() {
  const [viewMode, setViewMode] = useState<ViewMode>('document');
  const [loading, setLoading] = useState(false);
  const graphRef = useRef<any>(null);

  useEffect(() => {
    const initGraph = async () => {
      setLoading(true);
      try {
        const resp = await fetch(`/api/graph/${viewMode === 'document' ? 'documents' : viewMode === 'entity' ? 'entities' : 'timeline'}?scope=private`);
        const data = await resp.json();

        if (graphRef.current) {
          graphRef.current.destroy();
        }

        const graph = new G6.Graph({
          container: 'graph-container',
          width: 800,
          height: 600,
          layout: { type: viewMode === 'timeline' ? 'radial' : 'force' },
          modes: { default: ['drag-canvas', 'zoom-canvas', 'drag-node'] },
        });

        graph.data({
          nodes: data.nodes.map((n: any) => ({
            id: n.id, label: n.label,
            style: { fill: n.scope === 'private' ? '#5B8FF9' : '#5AD8A6' },
          })),
          edges: data.edges.map((e: any) => ({
            source: e.source, target: e.target,
          })),
        });
        graph.render();
        graphRef.current = graph;
      } finally {
        setLoading(false);
      }
    };
    initGraph();
    return () => { if (graphRef.current) graphRef.current.destroy(); };
  }, [viewMode]);

  return (
    <div className="p-4">
      <div className="flex gap-2 mb-4">
        <button onClick={() => setViewMode('document')} className={`px-3 py-1 rounded ${viewMode === 'document' ? 'bg-blue-500 text-white' : 'bg-gray-200'}`}>文档关系图</button>
        <button onClick={() => setViewMode('entity')} className={`px-3 py-1 rounded ${viewMode === 'entity' ? 'bg-blue-500 text-white' : 'bg-gray-200'}`}>实体网络图</button>
        <button onClick={() => setViewMode('timeline')} className={`px-3 py-1 rounded ${viewMode === 'timeline' ? 'bg-blue-500 text-white' : 'bg-gray-200'}`}>时间演化图</button>
      </div>
      {loading && <div className="text-center py-8">加载中...</div>}
      <div id="graph-container" style={{ width: '100%', height: '600px' }} />
    </div>
  );
}
