import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { api } from '../lib/api.js';

const integrations = [
  { name: 'SAM.gov', desc: 'Auto-import federal tenders and opportunities', connected: true, color: 'bg-sky-50 text-sky-600' },
  { name: 'Salesforce', desc: 'Sync companies and pipeline data', connected: true, color: 'bg-brand-50 text-brand-600' },
  { name: 'Gmail / Outlook', desc: 'Send and track outbound email campaigns', connected: true, color: 'bg-rose-50 text-rose-600' },
  { name: 'Slack', desc: 'Get notified about new matches and deadlines', connected: false, color: 'bg-violet-50 text-violet-600' },
  { name: 'DocuSign', desc: 'Send proposals for e-signature', connected: false, color: 'bg-amber-50 text-amber-600' },
  { name: 'QuickBooks', desc: 'Sync contract values to accounting', connected: false, color: 'bg-emerald-50 text-emerald-600' },
];

// This card is wired to a real backend integration (unlike the mock cards
// above): connecting lets Meetings create real Google Meet links.
function GoogleMeetCard() {
  const [status, setStatus] = useState({ connected: false, connectedEmail: '' });
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState('');
  const [searchParams] = useSearchParams();

  async function loadStatus() {
    setLoading(true);
    try {
      const data = await api.googleIntegrationStatus();
      setStatus(data);
    } catch {
      // leave status as "not connected" if the check itself fails
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStatus();
  }, []);

  useEffect(() => {
    const result = searchParams.get('google');
    if (result === 'connected') loadStatus();
    if (result === 'error') setError('Could not connect Google. Please try again.');
  }, [searchParams]);

  async function handleConnect() {
    setError('');
    setConnecting(true);
    try {
      const { url } = await api.googleIntegrationAuthUrl();
      window.location.href = url;
    } catch (err) {
      setError(err.message || 'Could not start Google connection.');
      setConnecting(false);
    }
  }

  return (
    <Card>
      <div className="flex items-start justify-between">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-50 text-sm font-bold text-red-600">GM</div>
        {loading ? (
          <span className="rounded-full bg-slate-100 dark:bg-navy-800 px-2.5 py-1 text-[11px] font-bold text-slate-500 dark:text-slate-400">Checking…</span>
        ) : status.connected ? (
          <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-bold text-emerald-700">Connected</span>
        ) : (
          <span className="rounded-full bg-slate-100 dark:bg-navy-800 px-2.5 py-1 text-[11px] font-bold text-slate-500 dark:text-slate-400">Not Connected</span>
        )}
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Google Meet</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
        {status.connected ? `Connected as ${status.connectedEmail}` : 'Auto-create Google Meet links when scheduling meetings'}
      </p>
      {error && <p className="mt-2 text-xs text-tomato-600">{error}</p>}
      <button
        onClick={handleConnect}
        disabled={connecting || loading}
        className={`mt-4 w-full rounded-lg py-2 text-xs font-semibold disabled:opacity-60 ${
          status.connected ? 'border border-slate-200 text-navy-900 dark:border-navy-700 dark:text-white' : 'bg-brand-500 text-white'
        }`}
      >
        {connecting ? 'Redirecting…' : status.connected ? 'Reconnect' : 'Connect'}
      </button>
    </Card>
  );
}

export default function Integrations() {
  return (
    <div>
      <PageHeader title="Integrations" subtitle="Connect OrbitAvanya with the tools your team already uses" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <GoogleMeetCard />
        {integrations.map((i) => (
          <Card key={i.name}>
            <div className="flex items-start justify-between">
              <div className={`flex h-10 w-10 items-center justify-center rounded-xl text-sm font-bold ${i.color}`}>
                {i.name.slice(0, 2).toUpperCase()}
              </div>
              {i.connected ? (
                <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-bold text-emerald-700">Connected</span>
              ) : (
                <span className="rounded-full bg-slate-100 dark:bg-navy-800 px-2.5 py-1 text-[11px] font-bold text-slate-500 dark:text-slate-400">Not Connected</span>
              )}
            </div>
            <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">{i.name}</p>
            <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">{i.desc}</p>
            <button className={`mt-4 w-full rounded-lg py-2 text-xs font-semibold ${i.connected ? 'border border-slate-200 text-navy-900 dark:border-navy-700 dark:text-white' : 'bg-brand-500 text-white'}`}>
              {i.connected ? 'Manage' : 'Connect'}
            </button>
          </Card>
        ))}
      </div>
    </div>
  );
}
