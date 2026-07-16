import { useState, useEffect, useCallback } from 'preact/hooks';
import { EmergencyStopButton } from './EmergencyStopButton';
import { apiGet, apiPost } from '../../lib/api';

export function CUControlPanel() {
  const [instruction, setInstruction] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>('idle');
  const [tasks, setTasks] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [executing, setExecuting] = useState(false);

  const refreshTasks = useCallback(async () => {
    try {
      const data = await apiGet<{ tasks: any[] }>('/api/cu/tasks');
      setTasks(data.tasks || []);
    } catch (err: any) {
      console.error('Failed to load tasks:', err);
    }
  }, []);

  useEffect(() => { refreshTasks(); }, [refreshTasks]);

  const createTask = async () => {
    setCreating(true);
    setError(null);
    try {
      const data = await apiPost<{ task_id: string }>('/api/cu/tasks', {
        instruction,
        steps: [{
          action_type: 'browser_navigate',
          action_payload: { url: 'https://example.com' },
          success_criteria: { url_contains: 'example' },
        }],
      });
      setTaskId(data.task_id);
      setStatus('created');
      refreshTasks();
    } catch (err: any) {
      setError(err?.message || '创建任务失败');
    } finally {
      setCreating(false);
    }
  };

  const executeTask = async () => {
    if (!taskId) return;
    setExecuting(true);
    setError(null);
    try {
      const data = await apiPost<{ status: string }>(`/api/cu/tasks/${taskId}/execute`, {});
      setStatus(data.status || 'executing');
      refreshTasks();
    } catch (err: any) {
      setError(err?.message || '执行任务失败');
    } finally {
      setExecuting(false);
    }
  };

  const emergencyStop = async () => {
    setError(null);
    try {
      await apiPost('/api/cu/emergency-stop', { reason: 'manual' });
      setStatus('stopped');
      refreshTasks();
    } catch (err: any) {
      setError(err?.message || '停止失败');
    }
  };

  return (
    <div style={{ padding: '16px' }}>
      <EmergencyStopButton active={status === 'executing'} />

      {error && (
        <div style={{ color: 'var(--error, red)', padding: '8px', marginBottom: '12px',
                       background: 'var(--bg-secondary)', borderRadius: '4px' }}>
          {error}
        </div>
      )}

      <div style={{ marginBottom: '16px' }}>
        <input
          type="text"
          value={instruction}
          onChange={(e) => setInstruction((e.target as HTMLInputElement).value)}
          placeholder="输入指令..."
          style={{
            width: '100%', padding: '8px 12px',
            border: '1px solid var(--border)', borderRadius: '4px',
            background: 'var(--bg-primary)', color: 'var(--text-primary)',
          }}
        />
        <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
          <button
            onClick={createTask}
            disabled={creating || !instruction}
            style={{
              padding: '8px 16px', borderRadius: '4px', border: 'none', cursor: 'pointer',
              background: creating || !instruction ? 'var(--bg-tertiary, #ccc)' : 'var(--accent)',
              color: 'white',
            }}
          >{creating ? '创建中...' : '生成计划'}</button>
          <button
            onClick={executeTask}
            disabled={!taskId || executing}
            style={{
              padding: '8px 16px', borderRadius: '4px', border: 'none', cursor: 'pointer',
              background: !taskId || executing ? 'var(--bg-tertiary, #ccc)' : '#22c55e',
              color: 'white',
            }}
          >{executing ? '执行中...' : '执行'}</button>
          <button
            onClick={emergencyStop}
            disabled={status !== 'executing' && status !== 'created'}
            style={{
              padding: '8px 16px', borderRadius: '4px', border: 'none', cursor: 'pointer',
              background: status !== 'executing' && status !== 'created' ? 'var(--bg-tertiary, #ccc)' : '#ef4444',
              color: 'white',
            }}
          >停止</button>
        </div>
      </div>

      {taskId && (
        <div style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '12px' }}>
          任务ID: {taskId} | 状态: {status}
        </div>
      )}

      <div>
        <h3 style={{ fontWeight: 700, marginBottom: '8px', color: 'var(--text-primary)' }}>任务列表</h3>
        {tasks.length === 0 ? (
          <div style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>暂无任务</div>
        ) : (
          tasks.map((t) => (
            <div key={t.task_id} style={{
              border: '1px solid var(--border)', padding: '8px',
              marginBottom: '4px', borderRadius: '4px', fontSize: '14px',
              color: 'var(--text-primary)',
            }}>
              {t.instruction || t.task_id} - {t.status}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
