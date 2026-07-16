import { h } from 'preact';
import { useState } from 'preact/hooks';
import { apiPost } from '../../lib/api';

export function EmergencyStopButton({ active }: { active: boolean }) {
  const [clicking, setClicking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!active) return null;

  const handleClick = async () => {
    setClicking(true);
    setError(null);
    try {
      await apiPost('/api/cu/emergency-stop', { reason: 'manual' });
    } catch (err: any) {
      setError(err?.message || '停止失败');
    } finally {
      setClicking(false);
    }
  };

  return (
    <div style={{ position: 'fixed', top: '16px', right: '16px', zIndex: 50 }}>
      {error && (
        <div style={{
          color: 'var(--error, red)', padding: '4px 8px', marginBottom: '4px',
          background: 'var(--bg-secondary)', borderRadius: '4px', fontSize: '12px',
        }}>
          {error}
        </div>
      )}
      <button
        style={{
          padding: '12px 24px', borderRadius: '8px', border: 'none', cursor: 'pointer',
          background: clicking ? '#991b1b' : '#dc2626',
          color: 'white', fontSize: '16px', fontWeight: 600,
          boxShadow: '0 4px 12px rgba(0,0,0,0.25)',
          animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        }}
        onClick={handleClick}
        disabled={clicking}
      >
        ⛔ 紧急停止
      </button>
    </div>
  );
}
