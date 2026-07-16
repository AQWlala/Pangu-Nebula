import { h } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import { EmergencyStopButton } from './EmergencyStopButton';

export function CUControlPanel() {
  const [instruction, setInstruction] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>('idle');
  const [tasks, setTasks] = useState<any[]>([]);

  const createTask = async () => {
    const resp = await fetch('/api/cu/tasks', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        instruction,
        steps: [{ action_type: 'browser_navigate',
          action_payload: { url: 'https://example.com' },
          success_criteria: { url_contains: 'example' } }],
      }),
    });
    const data = await resp.json();
    setTaskId(data.task_id);
    setStatus('created');
  };

  const executeTask = async () => {
    if (!taskId) return;
    await fetch(`/api/cu/tasks/${taskId}/execute`, { method: 'POST' });
    setStatus('executing');
  };

  const emergencyStop = async () => {
    await fetch('/api/cu/emergency-stop', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'manual' }),
    });
    setStatus('stopped');
  };

  useEffect(() => {
    fetch('/api/cu/tasks').then(r => r.json()).then(d => setTasks(d.tasks || []));
  }, []);

  return (
    <div className="p-4">
      <EmergencyStopButton active={status === 'executing'} />

      <div className="mb-4">
        <input
          type="text" value={instruction}
          onChange={(e) => setInstruction((e.target as HTMLInputElement).value)}
          placeholder="输入指令..."
          className="border px-3 py-2 rounded w-full"
        />
        <div className="flex gap-2 mt-2">
          <button onClick={createTask} className="px-4 py-2 bg-blue-500 text-white rounded">生成计划</button>
          <button onClick={executeTask} className="px-4 py-2 bg-green-500 text-white rounded" disabled={!taskId}>执行</button>
          <button onClick={emergencyStop} className="px-4 py-2 bg-red-500 text-white rounded">停止</button>
        </div>
      </div>

      {taskId && <div className="text-sm text-gray-600">任务ID: {taskId} | 状态: {status}</div>}

      <div className="mt-4">
        <h3 className="font-bold mb-2">任务列表</h3>
        {tasks.map((t) => (
          <div key={t.task_id} className="border p-2 mb-1 rounded text-sm">
            {t.instruction} - {t.status}
          </div>
        ))}
      </div>
    </div>
  );
}
