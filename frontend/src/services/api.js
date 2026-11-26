const BASE_URL = 'http://localhost:5050';

export const fetchState = async () => {
  const res = await fetch(`${BASE_URL}/state`);
  if (!res.ok) throw new Error('Failed to fetch state');
  return res.json();
};

export const fetchStats = async () => {
  const res = await fetch(`${BASE_URL}/stats`);
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
};

export const sendTerminalCommand = async (text) => {
  const res = await fetch(`${BASE_URL}/command?text=${encodeURIComponent(text)}`);
  if (!res.ok) throw new Error('Failed to send terminal command');
  return res.json();
};

export const activateJarvis = async () => {
  const res = await fetch(`${BASE_URL}/activate`, { method: 'POST' });
  // 404/405 = backend running older code without /activate
  if (res.status === 404 || res.status === 405) return { status: 'outdated', message: 'Restart jarvis.py to enable tap-to-activate' };
  if (!res.ok) throw new Error('Failed to activate');
  return res.json();
};
