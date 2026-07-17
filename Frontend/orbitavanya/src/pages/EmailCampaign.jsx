import { useEffect, useState, useCallback } from 'react';
import { Plus, Send, MousePointerClick, MailOpen, Reply, Clock, Globe, X, Play, Pause, Copy, Trash2, Upload, Rocket } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';

const SUMMARY_CARDS = [
  { key: 'totalSent', label: 'Total Sent', icon: Send, bg: 'bg-sky-50', fg: 'text-sky-600', format: (v) => (v || 0).toLocaleString() },
  { key: 'openRate', label: 'Open Rate', icon: MailOpen, bg: 'bg-emerald-50', fg: 'text-emerald-600', format: (v) => `${v || 0}%` },
  { key: 'clickRate', label: 'Click Rate', icon: MousePointerClick, bg: 'bg-amber-50', fg: 'text-amber-600', format: (v) => `${v || 0}%` },
  { key: 'replyRate', label: 'Reply Rate', icon: Reply, bg: 'bg-rose-50', fg: 'text-rose-600', format: (v) => `${v || 0}%` },
];

function titleCase(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

const emptyForm = { name: '', subject: '', body: '', dailyLimit: 200, timezone: 'America/Chicago' };

export default function EmailCampaign() {
  const [overview, setOverview] = useState(null);
  const [trends, setTrends] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [engagement, setEngagement] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [showNewCampaign, setShowNewCampaign] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState('');

  const [importingFor, setImportingFor] = useState(null); // campaignId currently importing a CSV
  const [actionError, setActionError] = useState('');

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [ov, tr, cp, eng] = await Promise.all([
        api.getAnalyticsOverview(),
        api.getAnalyticsTrends(),
        api.listCampaigns(),
        api.getWebsiteEngagement(),
      ]);
      setOverview(ov);
      setTrends(tr || []);
      setCampaigns(cp?.campaigns || []);
      setEngagement(eng || []);
    } catch (err) {
      setError(err.message || 'Could not load campaign data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  async function handleCreateCampaign(e) {
    e.preventDefault();
    setFormError('');
    if (!form.name.trim() || !form.subject.trim()) {
      setFormError('Name and subject are required.');
      return;
    }
    setCreating(true);
    try {
      await api.createCampaign(form);
      setShowNewCampaign(false);
      setForm(emptyForm);
      await loadAll();
    } catch (err) {
      setFormError(err.message || 'Could not create campaign.');
    } finally {
      setCreating(false);
    }
  }

  async function handleAction(action, campaignId) {
    setActionError('');
    try {
      if (action === 'pause') await api.pauseCampaign(campaignId);
      if (action === 'resume') await api.resumeCampaign(campaignId);
      if (action === 'launch') await api.launchCampaign(campaignId);
      if (action === 'duplicate') await api.duplicateCampaign(campaignId);
      if (action === 'delete') {
        if (!window.confirm('Delete this campaign and all its leads? This cannot be undone.')) return;
        await api.deleteCampaign(campaignId);
      }
      await loadAll();
    } catch (err) {
      setActionError(err.message || `Could not ${action} campaign.`);
    }
  }

  async function handleCsvUpload(campaignId, file) {
    setImportingFor(campaignId);
    setActionError('');
    try {
      const { report } = await api.importLeadsCsv(campaignId, file);
      window.alert(
        `Imported ${report.imported} leads (${report.duplicates} duplicates, ${report.invalidEmail} invalid, ${report.suppressed} suppressed skipped).`
      );
      await loadAll();
    } catch (err) {
      setActionError(err.message || 'CSV import failed.');
    } finally {
      setImportingFor(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Email Campaign"
        subtitle="Create, schedule, and track outbound email campaigns"
        action={
          <button
            onClick={() => setShowNewCampaign(true)}
            className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft"
          >
            <Plus size={16} /> New Campaign
          </button>
        }
      />

      {error && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
          {error}
        </div>
      )}
      {actionError && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
          {actionError}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {SUMMARY_CARDS.map((s) => (
          <Card key={s.key}>
            <div className={`flex h-9 w-9 items-center justify-center rounded-xl ${s.bg} ${s.fg}`}>
              <s.icon size={17} />
            </div>
            <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">{s.label}</p>
            <p className="text-xl font-extrabold text-navy-900 dark:text-white">
              {loading ? '—' : s.format(overview?.[s.key])}
            </p>
          </Card>
        ))}
      </div>

      <Card className="mt-5">
        <h3 className="text-sm font-bold text-navy-900 dark:text-white">Performance Trend</h3>
        <div className="mt-3 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trends}>
              <CartesianGrid vertical={false} stroke="#F1F3F9" />
              <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#94A3B8' }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 10, border: '1px solid #F1F3F9' }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="sent" name="Sent" stroke="#1c151e" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="opened" name="Opened" stroke="#2f879d" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="clicked" name="Clicked" stroke="#f7b708" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="replied" name="Replied" stroke="#e41b50" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card className="mt-5 !p-0">
        <div className="flex items-center justify-between p-5 pb-0">
          <h3 className="text-sm font-bold text-navy-900 dark:text-white">Campaigns</h3>
        </div>
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 dark:border-navy-800 text-left text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
              <th className="px-5 py-3 font-semibold">Campaign</th>
              <th className="px-5 py-3 font-semibold">Status</th>
              <th className="px-5 py-3 font-semibold">Sent</th>
              <th className="px-5 py-3 font-semibold">Opened</th>
              <th className="px-5 py-3 font-semibold">Clicked</th>
              <th className="px-5 py-3 font-semibold">Replied</th>
              <th className="px-5 py-3 font-semibold">Created</th>
              <th className="px-5 py-3 font-semibold text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {!loading && campaigns.length === 0 && (
              <tr>
                <td colSpan={8} className="px-5 py-8 text-center text-sm text-slate-400 dark:text-slate-500">
                  No campaigns yet — click "New Campaign" to create your first one.
                </td>
              </tr>
            )}
            {campaigns.map((c) => (
              <tr key={c._id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60 dark:border-navy-800/40 dark:hover:bg-navy-800/40">
                <td className="px-5 py-3.5 font-semibold text-navy-900 dark:text-white">{c.name}</td>
                <td className="px-5 py-3.5"><StatusBadge status={titleCase(c.status)} /></td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{(c.stats?.totalSent || 0).toLocaleString()}</td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{(c.stats?.totalOpened || 0).toLocaleString()}</td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{(c.stats?.totalClicked || 0).toLocaleString()}</td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{(c.stats?.totalReplied || 0).toLocaleString()}</td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{new Date(c.createdAt).toLocaleDateString()}</td>
                <td className="px-5 py-3.5">
                  <div className="flex items-center justify-end gap-1">
                    <label
                      title="Import leads from CSV"
                      className="cursor-pointer rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-navy-900 dark:hover:bg-navy-800 dark:hover:text-white"
                    >
                      <Upload size={15} className={importingFor === c._id ? 'animate-pulse' : ''} />
                      <input
                        type="file"
                        accept=".csv"
                        className="hidden"
                        onChange={(e) => e.target.files?.[0] && handleCsvUpload(c._id, e.target.files[0])}
                      />
                    </label>
                    {(c.status === 'draft' || c.status === 'paused') && (
                      <button title="Launch / resume sending" onClick={() => handleAction(c.status === 'draft' ? 'launch' : 'resume', c._id)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-emerald-600 dark:hover:bg-navy-800">
                        {c.status === 'draft' ? <Rocket size={15} /> : <Play size={15} />}
                      </button>
                    )}
                    {c.status === 'running' && (
                      <button title="Pause" onClick={() => handleAction('pause', c._id)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-amber-600 dark:hover:bg-navy-800">
                        <Pause size={15} />
                      </button>
                    )}
                    <button title="Duplicate" onClick={() => handleAction('duplicate', c._id)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-navy-900 dark:hover:bg-navy-800 dark:hover:text-white">
                      <Copy size={15} />
                    </button>
                    <button title="Delete" onClick={() => handleAction('delete', c._id)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-rose-600 dark:hover:bg-navy-800">
                      <Trash2 size={15} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card className="mt-5 !p-0">
        <div className="flex items-center justify-between p-5 pb-0">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-bold text-navy-900 dark:text-white">
              <Globe size={15} className="text-brand-500" /> Website Engagement Tracking
            </h3>
            <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">Which companies clicked through and how long they spent on the site</p>
          </div>
        </div>
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 dark:border-navy-800 text-left text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
              <th className="px-5 py-3 font-semibold">Campaign</th>
              <th className="px-5 py-3 font-semibold">Unique Visitors</th>
              <th className="px-5 py-3 font-semibold">Page Views</th>
              <th className="px-5 py-3 font-semibold">Avg. Time on Site</th>
              <th className="px-5 py-3 font-semibold text-right">Form Submits</th>
            </tr>
          </thead>
          <tbody>
            {!loading && engagement.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-8 text-center text-sm text-slate-400 dark:text-slate-500">
                  No website visits recorded yet — this fills in once the tracker.js SDK is installed on your site and leads start clicking through.
                </td>
              </tr>
            )}
            {engagement.map((w) => (
              <tr key={w.campaignId} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60 dark:border-navy-800/40 dark:hover:bg-navy-800/40">
                <td className="px-5 py-3.5 font-semibold text-navy-900 dark:text-white">{w.campaignName}</td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{w.uniqueVisitors}</td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{w.pageViews}</td>
                <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">
                  <span className="flex items-center gap-1.5"><Clock size={12} /> {w.avgDuration}s</span>
                </td>
                <td className="px-5 py-3.5 text-right text-slate-500 dark:text-slate-400">{w.formSubmits}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {showNewCampaign && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/60 p-4 backdrop-blur-xs"
          onClick={() => !creating && setShowNewCampaign(false)}
        >
          <div
            className="w-full max-w-lg rounded-2xl bg-white dark:bg-navy-800 shadow-soft overflow-hidden border border-slate-100 dark:border-navy-700"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 p-5">
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">New Campaign</h3>
              <button onClick={() => setShowNewCampaign(false)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-navy-900">
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleCreateCampaign} className="p-5 space-y-4">
              {formError && (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
                  {formError}
                </div>
              )}

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Campaign name</label>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Q3 Procurement Officers Outreach"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Subject line</label>
                <input
                  value={form.subject}
                  onChange={(e) => setForm({ ...form, subject: e.target.value })}
                  placeholder="Quick question about {{companyName}}'s procurement pipeline"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Email body (HTML, supports {'{{firstName}}'}, {'{{companyName}}'})</label>
                <textarea
                  value={form.body}
                  onChange={(e) => setForm({ ...form, body: e.target.value })}
                  rows={4}
                  placeholder="<p>Hi {{firstName}}, ...</p>"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Daily send limit</label>
                  <input
                    type="number"
                    min={1}
                    value={form.dailyLimit}
                    onChange={(e) => setForm({ ...form, dailyLimit: Number(e.target.value) })}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Timezone</label>
                  <input
                    value={form.timezone}
                    onChange={(e) => setForm({ ...form, timezone: e.target.value })}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowNewCampaign(false)}
                  className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="rounded-lg bg-brand-500 px-4 py-2 text-xs font-bold text-white shadow-soft hover:bg-brand-600 disabled:opacity-60"
                >
                  {creating ? 'Creating…' : 'Create Campaign'}
                </button>
              </div>
              <p className="text-[11px] text-slate-400 dark:text-slate-500">
                Created as a draft — add leads (CSV/manual) from the campaigns table, then launch when ready.
              </p>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
