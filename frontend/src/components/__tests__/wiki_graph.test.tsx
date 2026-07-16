import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/preact';
import { h } from 'preact';

// Mock @antv/g6 with v5 named export — G6 needs canvas/WebGL which jsdom lacks
vi.mock('@antv/g6', () => ({
  Graph: vi.fn().mockImplementation(() => ({
    setData: vi.fn(),
    render: vi.fn().mockResolvedValue(undefined),
    destroy: vi.fn(),
    resize: vi.fn(),
  })),
}));

// Mock apiGet/apiPost — components no longer use raw fetch
vi.mock('../../lib/api', () => ({
  apiGet: vi.fn().mockResolvedValue({ nodes: [], edges: [] }),
  apiPost: vi.fn().mockResolvedValue({ task_id: 'test', status: 'created' }),
}));

// ResizeObserver is not available in jsdom — stub it to avoid errors
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as any).ResizeObserver = ResizeObserverStub;

// Import components AFTER mocks
import { WikiGraph } from '../graph/WikiGraph';
import { EmergencyStopButton } from '../cu/EmergencyStopButton';

describe('WikiGraph', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
});

describe('EmergencyStopButton', () => {
  it('renders nothing when active is false', () => {
    const { container } = render(<EmergencyStopButton active={false} />);
    expect(container.querySelector('button')).toBeNull();
  });

  it('renders button when active is true', () => {
    const { container } = render(<EmergencyStopButton active={true} />);
    expect(container.querySelector('button')).toBeTruthy();
    expect(container.querySelector('button')?.textContent).toContain('紧急停止');
  });
});
