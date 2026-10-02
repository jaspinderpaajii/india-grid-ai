import { useEffect, useState } from 'react';
const configuredApiBase = (import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '');
export const apiUrl = (path: string) => `${configuredApiBase}/api/${path.replace(/^\/+/, '')}`;
export async function api<T>(url: string, signal?: AbortSignal): Promise<T> {
  const endpoint = apiUrl(url);
  const response = await fetch(endpoint, { signal, headers: { Accept: 'application/json' } });
  if (!response.ok) {
    let message = `Request failed (${response.status}).`;
    try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : 'Please check the selected date and forecast settings.'; } catch { /* Non-JSON proxy failure. */ }
    throw new Error(message);
  }
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    const body = await response.text();
    const hint = body.trimStart().startsWith('<')
      ? 'The API returned the web page instead of JSON. Start the FastAPI backend and verify the /api proxy.'
      : 'The API returned an unexpected response format.';
    throw new Error(`${hint} Endpoint: ${endpoint}`);
  }
  return response.json() as Promise<T>;
}
export function useResource<T>(url: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    setLoading(true); setError(''); setData(null);
    api<T>(url, controller.signal).then(setData).catch(e => {
      if (e.name !== 'AbortError') setError(e.message || 'Cannot reach the forecast service. Start the app with npm run dev.');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [url, version]);
  return { data, error, loading, retry: () => setVersion(v => v + 1) };
}
export const formatGW = (value: number) => (value / 1000).toFixed(3);
export const formatGWh = (value: number) => (value / 1000).toFixed(2);
export const time = (value: string) => new Date(value).toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' });
export const date = (value: string) => new Date(value).toLocaleDateString('en-GB', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', year: 'numeric' });
export const shortDate = (value: string) => new Date(value).toLocaleDateString('en-GB', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short' });
export const featureLabel = (name: string) => name.replace(/^weather_/, '').replaceAll('_', ' ').replace('lag ', 'previous ').replace(/\b\w/g, c => c.toUpperCase());
