import { h } from 'preact';
import { useState } from 'preact/hooks';

export function EmergencyStopButton({ active }: { active: boolean }) {
  const [clicking, setClicking] = useState(false);

  if (!active) return null;

  const handleClick = async () => {
    setClicking(true);
    try {
      await fetch('/api/cu/emergency-stop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'manual' }),
      });
    } finally {
      setClicking(false);
    }
  };

  return (
    <button
      className="fixed top-4 right-4 z-50 bg-red-600 text-white px-6 py-3 rounded-lg shadow-lg animate-pulse hover:bg-red-700"
      onClick={handleClick}
      disabled={clicking}
    >
      ⛔ 紧急停止
    </button>
  );
}
