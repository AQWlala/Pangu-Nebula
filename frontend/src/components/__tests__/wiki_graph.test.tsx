import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/preact';
import { h } from 'preact';

// Mock @antv/g6 BEFORE importing WikiGraph — G6 needs canvas/WebGL which jsdom lacks
vi.mock('@antv/g6', () => ({
  default: {
    Graph: vi.fn().mockImplementation(() => ({
      data: vi.fn(),
      render: vi.fn(),
      destroy: vi.fn(),
    })),
  },
}));

// Mock global fetch (WikiGraph and CUControlPanel call fetch in useEffect)
const mockFetch = vi.fn().mockResolvedValue({
  ok: true,
  json: async () => ({ nodes: [], edges: [], tasks: [] }),
});
global.fetch = mockFetch as any;

// Import components AFTER mocks
import { WikiGraph } from '../graph/WikiGraph';
import { EmergencyStopButton } from '../cu/EmergencyStopButton';

describe('WikiGraph', () => {
  beforeEach(() => {
    mockFetch.mockClear();
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
