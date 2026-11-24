export const airlineCode = (flightNumber) => {
  const match = /^[A-Z]{2,3}/.exec(flightNumber || '');
  return match ? match[0] : '??';
};

const BADGE_COLORS = ['#2563eb', '#0d9488', '#b45309', '#7c3aed', '#be123c', '#0f766e', '#4338ca'];

export const airlineColor = (code) => {
  let hash = 0;
  for (const ch of code) hash = (hash * 31 + ch.charCodeAt(0)) % BADGE_COLORS.length;
  return BADGE_COLORS[hash];
};

export const formatDuration = (departure, arrival) => {
  const minutes = Math.max(0, Math.round((new Date(arrival) - new Date(departure)) / 60000));
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h ${m.toString().padStart(2, '0')}m`;
};

export const durationMinutes = (departure, arrival) =>
  Math.max(0, Math.round((new Date(arrival) - new Date(departure)) / 60000));

export const formatTimeUTC = (iso) => {
  const d = new Date(iso);
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) + ' UTC';
};
