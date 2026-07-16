import { h } from 'preact';
import { useState, useEffect, useRef } from 'preact/hooks';
import { Graph } from '@antv/g6';
import { apiGet } from '../../lib/api';

type ViewMode = 'document' | 'entity' | 'timeline';

export function WikiGraph() {
  const [viewMode, setViewMode] = useState<ViewMode>('document');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;

    const initGraph = async () => {
      setLoading(true);
      setError(null);
      try {
        const endpoint = viewMode === 'document' ? 'documents'
                       : viewMode === 'entity' ? 'entities'
                       : 'timeline';
        const data = await apiGet<{ nodes: any[]; edges: any[] }>(`/api/graph/${endpoint}?scope=private`);

        if (cancelled) return;

        // Destroy old graph
        if (graphRef.current) {
          graphRef.current.destroy();
          graphRef.current = null;
        }

        if (!containerRef.current) return;

        const container = containerRef.current;
        const width = container.offsetWidth || 800;
        const height = container.offsetHeight || 600;

        const graph = new Graph({
          container,
          width,
          height,
          layout: {
            type: viewMode === 'timeline' ? 'radial' : 'force',
            preventOverlap: true,
          },
          behaviors: ['drag-canvas', 'zoom-canvas', 'drag-node'],
        });

        graph.setData({
          nodes: (data.nodes || []).map((n: any) => ({
            id: n.id,
            label: n.label || n.title || n.id,
            style: { fill: n.scope === 'private' ? '#5B8FF9' : '#5AD8A6' },
          })),
          edges: (data.edges || []).map((e: any) => ({
            source: e.source,
            target: e.target,
          })),
        });

        await graph.render();

        if (!cancelled) {
          graphRef.current = graph;
        } else {
          graph.destroy();
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || '加载图谱失败');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    initGraph();

    return () => {
      cancelled = true;
      if (graphRef.current) {
        graphRef.current.destroy();
        graphRef.current = null;
      }
    };
  }, [viewMode]);

  // Resize observer
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver(() => {
      if (graphRef.current && containerRef.current) {
        const { offsetWidth, offsetHeight } = containerRef.current;
        graphRef.current.resize(offsetWidth, offsetHeight);
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  return (
    <div style={{ padding: '16px', height: '100%' }}>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        <button
          onClick={() => setViewMode('document')}
          style={{
            padding: '4px 12px',
            borderRadius: '4px',
            border: 'none',
            cursor: 'pointer',
            background: viewMode === 'document' ? 'var(--accent)' : 'var(--bg-secondary)',
            color: viewMode === 'document' ? 'white' : 'var(--text-primary)',
          }}
        >文档关系图</button>
        <button
          onClick={() => setViewMode('entity')}
          style={{
            padding: '4px 12px',
            borderRadius: '4px',
            border: 'none',
            cursor: 'pointer',
            background: viewMode === 'entity' ? 'var(--accent)' : 'var(--bg-secondary)',
            color: viewMode === 'entity' ? 'white' : 'var(--text-primary)',
          }}
        >实体网络图</button>
        <button
          onClick={() => setViewMode('timeline')}
          style={{
            padding: '4px 12px',
            borderRadius: '4px',
            border: 'none',
            cursor: 'pointer',
            background: viewMode === 'timeline' ? 'var(--accent)' : 'var(--bg-secondary)',
            color: viewMode === 'timeline' ? 'white' : 'var(--text-primary)',
          }}
        >时间演化图</button>
      </div>
      {error && (
        <div style={{ color: 'var(--error, red)', padding: '16px', textAlign: 'center' }}>
          {error}
        </div>
      )}
      {loading && <div style={{ textAlign: 'center', padding: '32px', color: 'var(--text-secondary)' }}>加载中...</div>}
      <div
        ref={containerRef}
        id="graph-container"
        style={{ width: '100%', height: 'calc(100% - 60px)', minHeight: '400px' }}
      />
    </div>
  );
}
