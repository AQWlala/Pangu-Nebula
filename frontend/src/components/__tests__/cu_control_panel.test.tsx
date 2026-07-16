import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, fireEvent, waitFor } from '@testing-library/preact';
import { h } from 'preact';

// Mock apiGet/apiPost — components no longer use raw fetch
vi.mock('../../lib/api', () => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}));

// Import components AFTER mocks
import { CUControlPanel } from '../cu/CUControlPanel';
import { apiGet, apiPost } from '../../lib/api';

/** Helper: find a button whose trimmed text matches the given label. */
function findButton(container: HTMLElement, label: string): HTMLButtonElement {
  const buttons = Array.from(container.querySelectorAll('button'));
  const match = buttons.find((b) => (b.textContent || '').trim() === label);
  if (!match) throw new Error(`Button "${label}" not found. Buttons: ${buttons.map((b) => b.textContent).join(', ')}`);
  return match as HTMLButtonElement;
}

describe('CUControlPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiGet).mockReset();
    vi.mocked(apiPost).mockReset();
    // Defaults: empty task list, empty POST response.
    vi.mocked(apiGet).mockResolvedValue({ tasks: [] });
    vi.mocked(apiPost).mockResolvedValue({} as any);
  });

  it('renders task list on mount (apiGet called, tasks displayed)', async () => {
    vi.mocked(apiGet).mockResolvedValueOnce({
      tasks: [
        { task_id: 't1', instruction: '打开网页', status: 'done' },
        { task_id: 't2', instruction: '搜索资料', status: 'running' },
      ],
    });

    const { container } = render(<CUControlPanel />);

    expect(apiGet).toHaveBeenCalledWith('/api/cu/tasks');

    await waitFor(() => {
      expect(container.textContent).toContain('打开网页');
      expect(container.textContent).toContain('搜索资料');
    });
  });

  it('create button calls apiPost with correct payload, then refreshes task list', async () => {
    vi.mocked(apiPost).mockResolvedValueOnce({ task_id: 'new-task-123' });

    const { container } = render(<CUControlPanel />);

    // Wait for initial task list load to complete.
    await waitFor(() => {
      expect(apiGet).toHaveBeenCalledWith('/api/cu/tasks');
    });

    // Type an instruction (Preact onChange maps to DOM 'change' event).
    const input = container.querySelector('input')!;
    fireEvent.change(input, { target: { value: '帮我搜索' } });

    // Click the "生成计划" (create) button.
    fireEvent.click(findButton(container, '生成计划'));

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith(
        '/api/cu/tasks',
        expect.objectContaining({
          instruction: '帮我搜索',
          steps: expect.arrayContaining([
            expect.objectContaining({ action_type: 'browser_navigate' }),
          ]),
        }),
      );
    });

    // Task ID should be displayed after creation.
    await waitFor(() => {
      expect(container.textContent).toContain('new-task-123');
    });

    // Task list should have been refreshed (apiGet called at least twice).
    expect(apiGet.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('execute button calls apiPost, shows loading state, then refreshes', async () => {
    // Chain: create task -> execute task
    vi.mocked(apiPost)
      .mockResolvedValueOnce({ task_id: 'task-abc' })
      .mockResolvedValueOnce({ status: 'executing' });

    const { container } = render(<CUControlPanel />);

    await waitFor(() => expect(apiGet).toHaveBeenCalled());

    // Create a task first so the execute button becomes enabled.
    const input = container.querySelector('input')!;
    fireEvent.change(input, { target: { value: '测试指令' } });
    fireEvent.click(findButton(container, '生成计划'));

    await waitFor(() => {
      expect(container.textContent).toContain('task-abc');
    });

    // Click the "执行" (execute) button.
    fireEvent.click(findButton(container, '执行'));

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/cu/tasks/task-abc/execute', {});
    });

    // Status should be updated to 'executing'.
    await waitFor(() => {
      expect(container.textContent).toContain('executing');
    });

    // Task list refreshed: initial + after create + after execute.
    expect(apiGet.mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  it('stop button calls apiPost', async () => {
    // Create a task so status becomes 'created', enabling the stop button.
    vi.mocked(apiPost).mockResolvedValueOnce({ task_id: 'task-stop' });

    const { container } = render(<CUControlPanel />);

    await waitFor(() => expect(apiGet).toHaveBeenCalled());

    // Create task (status -> 'created').
    const input = container.querySelector('input')!;
    fireEvent.change(input, { target: { value: '指令' } });
    fireEvent.click(findButton(container, '生成计划'));

    await waitFor(() => expect(container.textContent).toContain('task-stop'));

    // Click the "停止" (stop) button.
    fireEvent.click(findButton(container, '停止'));

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/cu/emergency-stop', { reason: 'manual' });
    });
  });

  it('error state when apiPost fails (error banner shown)', async () => {
    vi.mocked(apiPost).mockRejectedValueOnce(new Error('创建任务失败'));

    const { container } = render(<CUControlPanel />);

    await waitFor(() => expect(apiGet).toHaveBeenCalled());

    // Type and click create.
    const input = container.querySelector('input')!;
    fireEvent.change(input, { target: { value: '指令' } });
    fireEvent.click(findButton(container, '生成计划'));

    await waitFor(() => {
      expect(container.textContent).toContain('创建任务失败');
    });
  });

  it('buttons disabled while loading (creating state)', async () => {
    // Controllable promise so the create request stays in-flight.
    let resolveCreate!: (val: any) => void;
    vi.mocked(apiPost).mockImplementationOnce(
      () => new Promise((resolve) => { resolveCreate = resolve; }),
    );

    const { container } = render(<CUControlPanel />);

    await waitFor(() => expect(apiGet).toHaveBeenCalled());

    const input = container.querySelector('input')!;
    fireEvent.change(input, { target: { value: '指令' } });

    const createBtn = findButton(container, '生成计划');
    fireEvent.click(createBtn);

    // While creating: button text changes to "创建中..." and is disabled.
    await waitFor(() => {
      const btn = findButton(container, '创建中...');
      expect(btn.disabled).toBe(true);
    });

    // Resolve to allow the component to settle.
    resolveCreate({ task_id: 'settled' });
    await waitFor(() => {
      const btn = findButton(container, '生成计划');
      expect(btn.disabled).toBe(false);
    });
  });
});
