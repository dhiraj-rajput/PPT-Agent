import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';

const mockIntegrations = [
  { name: 'Salesforce', desc: 'Sync companies and pipeline data', connected: true, color: 'bg-brand-50 text-brand-600' },
  { name: 'Gmail / Outlook', desc: 'Send and track outbound email campaigns', connected: true, color: 'bg-rose-50 text-rose-600' },
  { name: 'Slack', desc: 'Get notified about new matches and deadlines', connected: false, color: 'bg-violet-50 text-violet-600' },
  { name: 'DocuSign', desc: 'Send proposals for e-signature', connected: false, color: 'bg-amber-50 text-amber-600' },
  { name: 'QuickBooks', desc: 'Sync contract values to accounting', connected: false, color: 'bg-emerald-50 text-emerald-600' },
];

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
      // leave status as "not connected"
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

  async function handleDisconnect() {
    setError('');
    setLoading(true);
    try {
      await api.googleDisconnect();
      setStatus({ connected: false, connectedEmail: '' });
    } catch (err) {
      setError(err.message || 'Could not disconnect Google integration.');
    } finally {
      setLoading(false);
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
        {status.connected ? 'Google Meet account linked successfully.' : 'Auto-create Google Meet links when scheduling meetings'}
      </p>
      {error && <p className="mt-2 text-xs text-tomato-600">{error}</p>}
      <button
        onClick={status.connected ? handleDisconnect : handleConnect}
        disabled={connecting || loading}
        className={`mt-4 w-full rounded-lg py-2 text-xs font-semibold disabled:opacity-60 transition-all ${
          status.connected 
            ? 'bg-rose-50 text-rose-600 hover:bg-rose-100 border border-transparent' 
            : 'bg-brand-500 text-white hover:bg-brand-600'
        }`}
      >
        {connecting ? 'Redirecting…' : status.connected ? 'Disconnect' : 'Connect'}
      </button>
    </Card>
  );
}

function SamGovCard() {
  const [status, setStatus] = useState({ connected: false, apiKey: '' });
  const [loading, setLoading] = useState(true);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  async function loadStatus() {
    setLoading(true);
    try {
      const data = await api.getSamStatus();
      setStatus(data);
    } catch {
      // leave as not connected
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStatus();
  }, []);

  async function handleConnect(e) {
    e.preventDefault();
    if (!apiKeyInput.trim()) return;
    setError('');
    setSaving(true);
    try {
      await api.connectSam(apiKeyInput.trim());
      await loadStatus();
      setApiKeyInput('');
    } catch (err) {
      setError(err.message || 'Failed to save SAM.gov API key.');
    } finally {
      setSaving(false);
    }
  }

  async function handleDisconnect() {
    setError('');
    setLoading(true);
    try {
      await api.disconnectSam();
      setStatus({ connected: false, apiKey: '' });
    } catch (err) {
      setError(err.message || 'Could not disconnect SAM.gov.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <div className="flex items-start justify-between">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-50 text-sm font-bold text-sky-600">SM</div>
        {loading ? (
          <span className="rounded-full bg-slate-100 dark:bg-navy-800 px-2.5 py-1 text-[11px] font-bold text-slate-500 dark:text-slate-400">Checking…</span>
        ) : status.connected ? (
          <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-bold text-emerald-700">Connected</span>
        ) : (
          <span className="rounded-full bg-slate-100 dark:bg-navy-800 px-2.5 py-1 text-[11px] font-bold text-slate-500 dark:text-slate-400">Not Connected</span>
        )}
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">SAM.gov API</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2">
        {status.connected ? `API Key configured: ${status.apiKey}` : 'Auto-import federal tenders and opportunities directly using your key.'}
      </p>

      {error && <p className="text-xs text-tomato-600 mb-2">{error}</p>}

      {!status.connected ? (
        <form onSubmit={handleConnect} className="space-y-2 mt-2">
          <input
            type="password"
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
            placeholder="Enter SAM.gov API Key..."
            className="w-full text-xs rounded-lg border border-slate-200 bg-white p-2 outline-none dark:border-navy-700 dark:bg-navy-900 text-navy-900 dark:text-white"
            disabled={saving || loading}
          />
          <button
            type="submit"
            disabled={!apiKeyInput.trim() || saving || loading}
            className="w-full rounded-lg py-2 text-xs font-semibold bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-60"
          >
            {saving ? 'Saving...' : 'Connect Key'}
          </button>
        </form>
      ) : (
        <button
          onClick={handleDisconnect}
          disabled={loading}
          className="mt-4 w-full rounded-lg py-2 text-xs font-semibold bg-rose-50 text-rose-600 hover:bg-rose-100 border border-transparent disabled:opacity-60 transition-all"
        >
          Disconnect
        </button>
      )}
    </Card>
  );
}

export default function Integrations() {
  return (
    <div>
      <PageHeader title="Integrations" subtitle="Connect OrbitAvanya with the tools your team already uses" />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <GoogleMeetCard />
        <SamGovCard />
        {mockIntegrations.map((i) => (
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
