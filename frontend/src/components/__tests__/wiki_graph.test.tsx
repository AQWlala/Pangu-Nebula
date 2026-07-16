import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/preact';

// Capture all Graph instances created by the mock so we can assert on
// setData / render / destroy / resize calls.
const graphInstances: any[] = [];

// Mock @antv/g6 with v5 named export — G6 needs canvas/WebGL which jsdom lacks
vi.mock('@antv/g6', () => ({
  Graph: vi.fn().mockImplementation((opts: any) => {
    const instance = {
      constructorOptions: opts,
      setData: vi.fn(),
      render: vi.fn().mockResolvedValue(undefined),
      destroy: vi.fn(),
      resize: vi.fn(),
    };
    graphInstances.push(instance);
    return instance;
  }),
}));

// Mock apiGet/apiPost — components no longer use raw fetch
vi.mock('../../lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

// ResizeObserver is not available in jsdom — stub it while capturing the
// callback so we can simulate resize events in tests.
const resizeCallbacks: Array<(entries: any[]) => void> = [];
class ResizeObserverStub {
  constructor(cb: (entries: any[]) => void) {
    resizeCallbacks.push(cb);
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as any).ResizeObserver = ResizeObserverStub;

// Import components AFTER mocks
import { WikiGraph } from '../graph/WikiGraph';
import { apiGet } from '../../lib/api';

describe('WikiGraph', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    graphInstances.length = 0;
    resizeCallbacks.length = 0;
    vi.mocked(apiGet).mockReset();
    vi.mocked(apiGet).mockResolvedValue({ nodes: [], edges: [] });
  });

  it('renders container div with id graph-container', () => {
    render(<WikiGraph />);
    const container = document.getElementById('graph-container');
    expect(container).toBeTruthy();
  });

  it('renders three view-mode buttons', () => {
    const { container } = render(<WikiGraph />);
    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBeGreaterThanOrEqual(3);
  });

  it('calls Graph.setData and render (async) after apiGet resolves', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce({
      nodes: [{ id: 'n1', label: 'Node 1' }],
      edges: [{ source: 'n1', target: 'n1' }],
    });

    render(<WikiGraph />);

    // Wait for the async initGraph flow to create a Graph instance.
    await waitFor(() => {
      expect(graphInstances.length).toBe(1);
    });

    const graph = graphInstances[0];
    expect(graph.setData).toHaveBeenCalledTimes(1);
    expect(graph.render).toHaveBeenCalledTimes(1);

    // setData should receive the mapped nodes/edges payload.
    const setDataArg = graph.setData.mock.calls[0][0];
    expect(setDataArg.nodes).toHaveLength(1);
    expect(setDataArg.nodes[0].id).toBe('n1');
    expect(setDataArg.nodes[0].label).toBe('Node 1');
    expect(setDataArg.edges).toHaveLength(1);
    expect(setDataArg.edges[0].source).toBe('n1');
  });

  it('shows error state when apiGet fails', async () => {
    vi.mocked(apiGet).mockRejectedValueOnce(new Error('网络错误'));

    const { container } = render(<WikiGraph />);

    await waitFor(() => {
      expect(container.textContent).toContain('网络错误');
    });
  });

  it('cancelled flag prevents state updates after unmount', async () => {
    // Return a controllable promise that we resolve manually AFTER unmount.
    let resolveApi!: (val: any) => void;
    vi.mocked(apiGet).mockImplementationOnce(
      () => new Promise((resolve) => { resolveApi = resolve; }),
    );

    const { unmount } = render(<WikiGraph />);

    // Unmount before apiGet resolves — triggers cleanup which sets
    // cancelled = true on the effect closure.
    unmount();

    // Now resolve apiGet — the cancelled flag should cause an early return
    // before a Graph instance is ever constructed.
    resolveApi({ nodes: [], edges: [] });
    // Flush microtasks so the async initGraph continues past the await.
    await new Promise((r) => setTimeout(r, 0));

    expect(graphInstances.length).toBe(0);
  });

  it('ResizeObserver triggers graph.resize()', async () => {
    render(<WikiGraph />);

    // Wait for the graph instance to be created.
    await waitFor(() => {
      expect(graphInstances.length).toBe(1);
    });

    const graph = graphInstances[0];
    expect(resizeCallbacks.length).toBeGreaterThan(0);

    // Stub container dimensions so resize receives concrete values.
    const containerEl = document.getElementById('graph-container') as HTMLElement;
    Object.defineProperty(containerEl, 'offsetWidth', { configurable: true, value: 500 });
    Object.defineProperty(containerEl, 'offsetHeight', { configurable: true, value: 400 });

    // Simulate a resize event by invoking the registered ResizeObserver callback.
    resizeCallbacks[0]([{ target: containerEl }]);

    expect(graph.resize).toHaveBeenCalledWith(500, 400);
  });
});
