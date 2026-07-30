import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Globe, Mail, Video, Landmark, CheckCircle2, XCircle, Loader2, FileText, Bot, Search
} from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';

// ---------------------------------------------------------------------------
// Small shared building blocks
// ---------------------------------------------------------------------------

function ConnectionPill({ connected, checking }) {
  if (checking) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 dark:bg-navy-800 px-2.5 py-1 text-[11px] font-bold text-slate-500 dark:text-slate-400">
        <Loader2 size={11} className="animate-spin" /> Checking…
      </span>
    );
  }
  return connected ? (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 dark:bg-emerald-500/10 px-2.5 py-1 text-[11px] font-bold text-emerald-700 dark:text-emerald-400">
      <CheckCircle2 size={12} /> Connected
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 dark:bg-navy-800 px-2.5 py-1 text-[11px] font-bold text-slate-500 dark:text-slate-400">
      <XCircle size={12} /> Not Connected
    </span>
  );
}

// ---------------------------------------------------------------------------
// Generic env-key integration card — used by every integration that is just a
// set of fields persisted via /api/integrations/env-keys (Zoom, Google Cloud
// OAuth, Companies House, SMTP, Ollama, SerpAPI, Firecrawl, Tavily, Gemini,
// OpenRouter). Reads its connected state from the shared envKeys map fetched
// once by the page, and pre-fills the edit modal with whatever is already saved.
// ---------------------------------------------------------------------------

function GenericIntegrationCard({
  icon: Icon,
  iconWrapClass,
  title,
  description,
  name,
  fields,
  envKeys,
  loading,
  onEdit,
}) {
  const requiredFields = fields.filter((f) => !f.optional);
  const checkFields = requiredFields.length ? requiredFields : fields;
  const connected = !loading && checkFields.every((f) => !!(envKeys[f.key] && String(envKeys[f.key]).trim()));

  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
        <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${iconWrapClass}`}>
          <Icon size={19} />
        </div>
        <ConnectionPill connected={connected} checking={loading} />
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">{title}</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">{description}</p>
      <button
        onClick={() =>
          onEdit({
            name,
            label: title,
            fields,
            initialValues: Object.fromEntries(fields.map((f) => [f.key, envKeys[f.key] || ''])),
          })
        }
        className="mt-auto w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors"
      >
        {connected ? 'Edit / Reconfigure' : 'Connect'}
      </button>
    </Card>
  );
}

// Declarative definitions for every generic card — swap/add integrations here
// without touching the page layout.
const GENERIC_INTEGRATIONS = [
  {
    name: 'zoom',
    icon: Video,
    iconWrapClass: 'bg-blue-50 dark:bg-blue-500/10 text-blue-500',
    title: 'Zoom Video Meetings (Optional)',
    description: 'Zoom API integration for meetings.',
    fields: [
      { key: 'ZOOM_ACCOUNT_ID', label: 'ZOOM_ACCOUNT_ID', type: 'text', optional: true },
      { key: 'ZOOM_CLIENT_ID', label: 'ZOOM_CLIENT_ID', type: 'text', optional: true },
      { key: 'ZOOM_CLIENT_SECRET', label: 'ZOOM_CLIENT_SECRET', type: 'password', optional: true },
    ],
  },
  {
    name: 'google_workspace',
    icon: Globe,
    iconWrapClass: 'bg-blue-50 dark:bg-blue-500/10 text-blue-500',
    title: 'Google Cloud OAuth Client Credentials',
    description: 'Manual GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET configuration.',
    fields: [
      { key: 'GOOGLE_CLIENT_ID', label: 'GOOGLE_CLIENT_ID', type: 'text' },
      { key: 'GOOGLE_CLIENT_SECRET', label: 'GOOGLE_CLIENT_SECRET', type: 'password' },
    ],
  },
  {
    name: 'companies_house',
    icon: Landmark,
    iconWrapClass: 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-500',
    title: 'Companies House UK API',
    description: 'Company data and filings from UK Companies House.',
    fields: [{ key: 'COMPANIES_HOUSE_KEY', label: 'API Key', type: 'password' }],
  },
  {
    name: 'smtp',
    icon: Mail,
    iconWrapClass: 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-500',
    title: 'Email SMTP Server',
    description: 'Send emails directly from the platform.',
    fields: [
      { key: 'SMTP_HOST', label: 'Base URL / Host', type: 'text' },
      { key: 'SMTP_PORT', label: 'Port', type: 'text', optional: true },
      { key: 'SMTP_USER', label: 'Username', type: 'text' },
      { key: 'SMTP_PASS', label: 'Password', type: 'password' },
    ],
  },
  {
    name: 'ollama',
    icon: Bot,
    iconWrapClass: 'bg-purple-50 dark:bg-purple-500/10 text-purple-500',
    title: 'Ollama AI Inference (Codespaces)',
    description: 'Local/Codespaces LLM inference configuration.',
    fields: [
      { key: 'OLLAMA_HOST', label: 'Host URL (e.g. https://xxxx-11434.app.github.dev)', type: 'text' },
      { key: 'OLLAMA_MODEL', label: 'Model Name (e.g. gemma3:4b)', type: 'text' },
      { key: 'OLLAMA_API_KEY', label: 'API Key', type: 'password', optional: true },
      { key: 'OLLAMA_TIMEOUT', label: 'Timeout in Seconds', type: 'text', optional: true },
    ],
  },
  {
    name: 'serpapi',
    icon: Search,
    iconWrapClass: 'bg-teal-50 dark:bg-teal-500/10 text-teal-500',
    title: 'SerpAPI Search Engine (Optional)',
    description: 'Google search results via SerpAPI.',
    fields: [{ key: 'SERPAPI_API_KEY', label: 'SERPAPI_API_KEY', type: 'password', optional: true }],
  },
  {
    name: 'firecrawl',
    icon: Globe,
    iconWrapClass: 'bg-orange-50 dark:bg-orange-500/10 text-orange-500',
    title: 'Firecrawl Web Scraper (Optional)',
    description: 'Advanced web scraping capabilities.',
    fields: [{ key: 'FIRECRAWL_API_KEY', label: 'FIRECRAWL_API_KEY', type: 'password', optional: true }],
  },
  {
    name: 'tavily',
    icon: Search,
    iconWrapClass: 'bg-indigo-50 dark:bg-indigo-500/10 text-indigo-500',
    title: 'Tavily AI Search (Optional)',
    description: 'AI-optimized search engine API.',
    fields: [{ key: 'TAVILY_API_KEY', label: 'TAVILY_API_KEY', type: 'password', optional: true }],
  },
  {
    name: 'gemini',
    icon: Bot,
    iconWrapClass: 'bg-blue-50 dark:bg-blue-500/10 text-blue-500',
    title: 'Gemini AI LLM (Optional)',
    description: 'Google Gemini AI integration.',
    fields: [{ key: 'GEMINI_API_KEY', label: 'GEMINI_API_KEY', type: 'password', optional: true }],
  },
  {
    name: 'openrouter',
    icon: Bot,
    iconWrapClass: 'bg-purple-50 dark:bg-purple-500/10 text-purple-500',
    title: 'OpenRouter AI LLM (Optional)',
    description: 'Access multiple LLMs via OpenRouter.',
    fields: [
      { key: 'OPENROUTER_API_KEY', label: 'API Key', type: 'password', optional: true },
      { key: 'OPENROUTER_MODEL', label: 'Model Name (e.g. nvidia/nemotron-3-ultra-550b-a55b:free)', type: 'text', optional: true },
    ],
  },
  {
    name: 'browserless',
    icon: Globe,
    iconWrapClass: 'bg-slate-100 dark:bg-slate-500/10 text-slate-500',
    title: 'Remote Browser (Browserless CDP)',
    description: "Remote Chrome for scraping on hosts that can't run local Chrome, e.g. cPanel (Browserless.io, ScrapingBee, Crawlbase). Leave empty to keep scraping with a local browser.",
    fields: [
      { key: 'BROWSERLESS_CDP_URL', label: 'CDP WebSocket URL (wss://...&token=...)', type: 'password', optional: true },
    ],
  },
];

// ---------------------------------------------------------------------------
// Google Meet (working, OAuth-based)
// ---------------------------------------------------------------------------

function GoogleMeetCard({ notify }) {
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
    if (result === 'connected') {
      loadStatus();
      notify('Google Meet connected', 'Meetings will now auto-generate Google Meet links.', '/integrations');
    }
    if (result === 'error') setError('Could not connect Google. Please try again.');
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      notify('Google Meet disconnected', 'Meeting links will no longer be auto-generated.', '/integrations');
    } catch (err) {
      setError(err.message || 'Could not disconnect Google integration.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-red-50 dark:bg-red-500/10 text-red-500">
          <Video size={19} />
        </div>
        <ConnectionPill connected={status.connected} checking={loading} />
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Google Meet (One-Click OAuth)</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 flex-1 mb-2">
        {status.connected
          ? `Linked${status.connectedEmail ? ` as ${status.connectedEmail}` : ''}. Meeting links are created automatically.`
          : 'Browser consent for auto-generating meeting links.'}
      </p>
      {error && <p className="mt-2 text-xs text-tomato-600 mb-2">{error}</p>}
      <button
        onClick={status.connected ? handleDisconnect : handleConnect}
        disabled={connecting || loading}
        className={`mt-auto w-full rounded-lg py-2 text-xs font-semibold disabled:opacity-60 transition-all ${
          status.connected
            ? 'bg-rose-50 text-rose-600 hover:bg-rose-100 border border-transparent'
            : 'bg-brand-500 text-white hover:bg-brand-600'
        }`}
      >
        {connecting ? 'Redirecting…' : status.connected ? 'Disconnect' : 'Connect Google Meet'}
      </button>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// SAM.gov API
// ---------------------------------------------------------------------------

function SamGovCard({ notify, onEdit }) {
  const [status, setStatus] = useState({ connected: false, apiKey: '' });
  const [loading, setLoading] = useState(true);

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

  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-sky-50 dark:bg-sky-500/10 text-sky-500">
          <Landmark size={19} />
        </div>
        <ConnectionPill connected={status.connected} checking={loading} />
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">SAM.gov API</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        {status.connected ? `Key configured: ${status.apiKey}` : 'Auto-import federal tenders and opportunities using your key.'}
      </p>

      <div className="mt-auto space-y-2">
        <button
          onClick={() => onEdit({
            name: 'samgov',
            label: 'SAM.gov',
            fields: [{ key: 'SAM_GOV_API_KEY', label: 'API Key', type: 'password' }],
            onSuccess: loadStatus
          })}
          className="w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors"
        >
          Edit / Configure
        </button>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// LinkedIn, Companies House, SMTP, Docling, Ollama, WebSearch
// ---------------------------------------------------------------------------

function LinkedInCard({ notify, onEdit }) {
  const [status, setStatus] = useState({ connected: false, expired: false });
  const [loading, setLoading] = useState(true);

  async function loadStatus() {
    setLoading(true);
    try {
      if (api.getLinkedinStatus) {
        const res = await api.getLinkedinStatus();
        setStatus(res);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStatus();
  }, []);

  return (
    <Card className="flex flex-col">
      {(status.expired || !status.connected) && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/30 dark:text-rose-400 font-semibold mb-3">
          ⚠️ LinkedIn Cookie Expired: Please update your session cookie (li_at) to continue automated research.
        </div>
      )}
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-blue-500 dark:bg-blue-500/10">
           <Globe size={19} />
         </div>
         <ConnectionPill connected={status.connected && !status.expired} checking={loading} />
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">LinkedIn Auto-Researcher</p>
      <p className="mt-1 text-xs text-slate-400 dark:text-slate-500 mb-2 flex-1">
        Automated research for companies and contacts.
      </p>
      <button onClick={() => onEdit({
          name: 'linkedin',
          label: 'LinkedIn',
          fields: [{ key: 'LINKEDIN_LI_AT', label: 'Cookie token (li_at string)', type: 'password' }],
          onSuccess: (formData) => {
             if (formData && formData.LINKEDIN_LI_AT) {
                // Optimistically clear the error
                setStatus({ connected: true, expired: false });
             }
             loadStatus();
          }
      })} className="mt-auto w-full rounded-lg py-2 text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors">
        Edit / Configure
      </button>
    </Card>
  )
}

function DoclingCard() {
  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between">
         <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-purple-50 text-purple-500 dark:bg-purple-500/10">
           <FileText size={19} />
         </div>
         <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 dark:bg-emerald-500/10 px-2.5 py-1 text-[11px] font-bold text-emerald-700 dark:text-emerald-400 border border-emerald-200/60 dark:border-emerald-900/40">
           Active (No API Key Required)
         </span>
      </div>
      <p className="mt-3 text-sm font-bold text-navy-900 dark:text-white">Docling OCR Engine</p>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 leading-relaxed mb-3 flex-1">
        Local CPU document processing for PDFs, tables, and forms by IBM Research. Runs 100% locally on your machine — <strong>no API key, account, or setup needed</strong>.
      </p>
      <div className="rounded-xl bg-slate-50 dark:bg-navy-900 p-2.5 text-[11px] font-semibold text-slate-500 dark:text-slate-400 text-center border border-slate-100 dark:border-navy-800">
        ✓ Built-in Local Engine (Installed & Ready)
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Edit Integration Modal
// ---------------------------------------------------------------------------

function EditIntegrationModal({ isOpen, onClose, integration, onSave }) {
  const [formData, setFormData] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setFormData(integration?.initialValues ? { ...integration.initialValues } : {});
    }
  }, [isOpen, integration]);

  if (!isOpen || !integration) return null;

  const hasExistingValues = Object.values(integration.initialValues || {}).some((v) => v);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSave(integration.name, formData);
      if (integration.onSuccess) {
        integration.onSuccess(formData);
      }
      onClose();
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
      <div className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl bg-white p-5 shadow-xl dark:bg-navy-900 sm:p-6">
        <div className="mb-4 flex items-start justify-between gap-3">
          <h2 className="text-lg font-bold text-navy-900 dark:text-white">Edit {integration.label}</h2>
          <button type="button" onClick={onClose} className="shrink-0 text-slate-400 hover:text-slate-600"><XCircle size={20}/></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
           {hasExistingValues && (
             <p className="text-[11px] text-slate-400 dark:text-slate-500 -mt-1">
               Masked fields (••••) already have a saved value — leave a field as-is to keep it, or type a new value to replace it.
             </p>
           )}
           {integration.fields.map(f => (
             <div key={f.key}>
                <label className="block text-xs font-bold text-slate-500 mb-1">{f.label}{f.optional && <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span>}</label>
                <input 
                  type={f.type || 'text'} 
                  value={formData[f.key] || ''} 
                  onChange={e => setFormData({...formData, [f.key]: e.target.value})}
                  className="w-full rounded-lg border border-slate-200 p-2 text-sm dark:bg-navy-800 dark:border-navy-700 dark:text-white" 
                />
             </div>
           ))}
           <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
             <button type="button" onClick={onClose} className="w-full rounded-lg bg-slate-100 px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300 sm:w-auto sm:py-2">Cancel</button>
             <button type="submit" disabled={saving} className="w-full rounded-lg bg-brand-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-600 sm:w-auto sm:py-2">{saving ? 'Saving...' : 'Save'}</button>
           </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Integrations() {
  const { createAlert } = useNotifications();

  async function notify(title, message, link) {
    try {
      await createAlert(title, message, link);
    } catch {
      // Notifications are best-effort — never block the integration flow.
    }
  }

  const [isModalOpen, setModalOpen] = useState(false);
  const [activeIntegration, setActiveIntegration] = useState(null);
  const [envKeys, setEnvKeys] = useState({});
  const [envKeysLoading, setEnvKeysLoading] = useState(true);

  async function loadEnvKeys() {
    setEnvKeysLoading(true);
    try {
      const data = await api.getEnvKeys();
      setEnvKeys(data || {});
    } catch {
      // leave whatever we had — cards will show "checking" -> fall back to "not connected"
    } finally {
      setEnvKeysLoading(false);
    }
  }

  useEffect(() => {
    loadEnvKeys();
  }, []);

  const handleEdit = (integrationDef) => {
    setActiveIntegration(integrationDef);
    setModalOpen(true);
  };

  const handleSaveConfig = async (name, configData) => {
    if (api.saveIntegrationConfig) {
      await api.saveIntegrationConfig(name, configData);
    } else if (api.saveIntegration) {
      await api.saveIntegration(name, configData);
    }
    notify(`${activeIntegration?.label || 'Integration'} configuration saved`, 'Your changes have been applied.', '/integrations');
    await loadEnvKeys();
  };

  return (
    <div>
      <PageHeader title="Integrations" subtitle="Connect OrbitAvanya with the tools your team already uses" />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 mt-6">
        <GoogleMeetCard notify={notify} />
        <SamGovCard notify={notify} onEdit={handleEdit} />
        <LinkedInCard notify={notify} onEdit={handleEdit} />
        <DoclingCard />
        {GENERIC_INTEGRATIONS.map((def) => (
          <GenericIntegrationCard
            key={def.name}
            {...def}
            envKeys={envKeys}
            loading={envKeysLoading}
            onEdit={handleEdit}
          />
        ))}
      </div>

      <EditIntegrationModal 
        isOpen={isModalOpen} 
        onClose={() => setModalOpen(false)} 
        integration={activeIntegration} 
        onSave={handleSaveConfig} 
      />
    </div>
  );
}
