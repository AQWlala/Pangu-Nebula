import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/preact';
import { h } from 'preact';

// Mock apiGet/apiPost — components no longer use raw fetch
vi.mock('../../lib/api', () => ({
  apiPost: vi.fn(),
}));

// Import components AFTER mocks
import { EmergencyStopButton } from '../cu/EmergencyStopButton';
import { apiPost } from '../../lib/api';

describe('EmergencyStopButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiPost).mockReset();
    vi.mocked(apiPost).mockResolvedValue({} as any);
  });

  it('renders nothing when active is false', () => {
    const { container } = render(<EmergencyStopButton active={false} />);
    expect(container.querySelector('button')).toBeNull();
  });

  it('renders button when active is true', () => {
    const { container } = render(<EmergencyStopButton active={true} />);
    expect(container.querySelector('button')).toBeTruthy();
    expect(container.querySelector('button')?.textContent).toContain('紧急停止');
  });

  it('click triggers apiPost to /api/cu/emergency-stop', async () => {
    const { container } = render(<EmergencyStopButton active={true} />);
    const button = container.querySelector('button')!;
    fireEvent.click(button);

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/cu/emergency-stop', { reason: 'manual' });
    });
  });

  it('shows error state when apiPost fails', async () => {
    vi.mocked(apiPost).mockRejectedValueOnce(new Error('停止失败'));

    const { container } = render(<EmergencyStopButton active={true} />);
    fireEvent.click(container.querySelector('button')!);

    await waitFor(() => {
      expect(container.textContent).toContain('停止失败');
    });
  });

  it('shows loading state (disabled) during request', async () => {
    // Controllable promise so we can inspect the in-flight state.
    let resolveApi!: (val: any) => void;
    vi.mocked(apiPost).mockImplementationOnce(
      () => new Promise((resolve) => { resolveApi = resolve; }),
    );

    const { container } = render(<EmergencyStopButton active={true} />);
    const button = container.querySelector('button') as HTMLButtonElement;
    fireEvent.click(button);

    // While the request is in flight the button must be disabled.
    await waitFor(() => {
      expect(button.disabled).toBe(true);
    });

    // Resolve to allow the component to settle.
    resolveApi({});
    await waitFor(() => {
      expect(button.disabled).toBe(false);
    });
  });
});
