import { useEffect, useState, useCallback, Fragment } from 'react';
import { Plus, Send, MousePointerClick, MailOpen, Reply, Clock, Globe, X, Play, Pause, Copy, Trash2, Upload, Rocket, RefreshCw, Building2, AlertTriangle, ChevronDown, ChevronUp, RotateCw, Hash, Search, Check, Loader2 } from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';

const SUMMARY_CARDS = [
  { key: 'totalSent', label: 'Total Sent', icon: Send, bg: 'bg-sky-50', fg: 'text-sky-600', format: (v) => (v || 0).toLocaleString() },
  { key: 'openRate', label: 'Open Rate', icon: MailOpen, bg: 'bg-emerald-50', fg: 'text-emerald-600', format: (v) => `${v || 0}%` },
  { key: 'clickRate', label: 'Click Rate', icon: MousePointerClick, bg: 'bg-amber-50', fg: 'text-amber-600', format: (v) => `${v || 0}%` },
  { key: 'replyRate', label: 'Reply Rate', icon: Reply, bg: 'bg-rose-50', fg: 'text-rose-600', format: (v) => `${v || 0}%` },
  { key: 'totalCampaigns', label: 'Campaign Counter', icon: Hash, bg: 'bg-violet-50', fg: 'text-violet-600', format: (v) => (v || 0).toLocaleString() },
  { key: 'totalResent', label: 'Emails Resent', icon: RotateCw, bg: 'bg-teal-50', fg: 'text-teal-600', format: (v) => (v || 0).toLocaleString() },
];

function titleCase(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

const emptyForm = {
  name: '',
  subject: '',
  body: '',
  dailyLimit: 200,
  timezone: 'America/Chicago',
  senderEmail: 'prasannadhamal982005@gmail.com',
  senderName: 'OrbitAvanya Outreach'
};

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
  const [workerStatus, setWorkerStatus] = useState(null);

  // Manual Lead Entry States
  const [showAddLead, setShowAddLead] = useState(null); // campaignId
  const [leadForm, setLeadForm] = useState({
    email: '',
    contactName: '',
    companyName: '',
    title: ''
  });
  const [addingLead, setAddingLead] = useState(false);
  const [leadError, setLeadError] = useState('');

  // Multi-company selection for a campaign
  const [showAddCompanies, setShowAddCompanies] = useState(null); // campaignId
  const [companyQuery, setCompanyQuery] = useState('');
  const [companyResults, setCompanyResults] = useState([]);
  const [companyPage, setCompanyPage] = useState(1);
  const [totalCompaniesCount, setTotalCompaniesCount] = useState(0);
  const [selectedCompanies, setSelectedCompanies] = useState({}); // uei/name -> company obj
  const [companiesInUse, setCompaniesInUse] = useState([]); // [{companyKey, companyName, campaignId, campaignName}]
  const [searchingCompanies, setSearchingCompanies] = useState(false);
  const [addingCompanies, setAddingCompanies] = useState(false);
  const [companiesError, setCompaniesError] = useState('');

  // Per-campaign company breakdown (expand/collapse)
  const [expandedCampaign, setExpandedCampaign] = useState(null);
  const [campaignLeads, setCampaignLeads] = useState({}); // campaignId -> leads[]
  const [loadingLeadsFor, setLoadingLeadsFor] = useState(null);
  const [resendingLead, setResendingLead] = useState(null);

  const [reportsList, setReportsList] = useState([]);
  const [sendMode, setSendMode] = useState('bulk'); // 'bulk' | 'single'
  const [recipientEmail, setRecipientEmail] = useState('');
  const [recipientName, setRecipientName] = useState('');
  const [recipientCompany, setRecipientCompany] = useState('');
  const [selectedReport, setSelectedReport] = useState('');
  const [viewingReplyLead, setViewingReplyLead] = useState(null);
  
  // Attachment Options
  const [attachmentType, setAttachmentType] = useState('none'); // 'none' | 'report' | 'device'
  const [attachedPath, setAttachedPath] = useState('');
  const [attachedFilename, setAttachedFilename] = useState('');
  const [uploadingFile, setUploadingFile] = useState(false);

  const handleAddLead = async (e) => {
    e.preventDefault();
    if (!leadForm.email.trim()) {
      setLeadError('Email is required.');
      return;
    }
    setAddingLead(true);
    setLeadError('');
    try {
      await api.createLead({
        campaignId: showAddLead,
        email: leadForm.email,
        contactName: leadForm.contactName,
        companyName: leadForm.companyName,
        title: leadForm.title
      });
      setShowAddLead(null);
      setLeadForm({ email: '', contactName: '', companyName: '', title: '' });
      await loadAll();
    } catch (err) {
      setLeadError(err.message || 'Could not add lead.');
    } finally {
      setAddingLead(false);
    }
  };

  const fetchWorkerStatus = useCallback(async () => {
    try {
      const status = await api.getCampaignWorkerStatus();
      setWorkerStatus(status);
    } catch (err) {
      console.error('Failed to fetch worker status:', err);
    }
  }, []);

  useEffect(() => {
    fetchWorkerStatus();
    const interval = setInterval(fetchWorkerStatus, 10000);
    return () => clearInterval(interval);
  }, [fetchWorkerStatus]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [ov, tr, cp, eng, reps] = await Promise.all([
        api.getAnalyticsOverview(),
        api.getAnalyticsTrends(),
        api.listCampaigns(),
        api.getWebsiteEngagement(),
        api.getReports().catch(() => []),
      ]);
      setOverview(ov);
      setTrends(tr || []);
      setCampaigns(cp?.campaigns || []);
      setEngagement(eng || []);
      setReportsList(reps || []);
    } catch (err) {
      setError(err.message || 'Could not load campaign data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleDeviceFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFormError('');
    setUploadingFile(true);
    try {
      const res = await api.uploadCampaignAttachment(file);
      setAttachedPath(res.attachmentPath);
      setAttachedFilename(res.attachmentFilename);
    } catch (err) {
      setFormError(err.message || 'File upload failed.');
    } finally {
      setUploadingFile(false);
    }
  };

  const handleReportChange = (filename) => {
    setSelectedReport(filename);
    if (filename) {
      setAttachedPath(`private/reports/${filename}`);
      setAttachedFilename(filename);
    } else {
      setAttachedPath('');
      setAttachedFilename('');
    }
  };

  async function handleCreateCampaign(e) {
    e.preventDefault();
    setFormError('');
    if (!form.name.trim() || !form.subject.trim()) {
      setFormError('Name and subject are required.');
      return;
    }
    if (sendMode === 'single' && !recipientEmail.trim()) {
      setFormError('Recipient Email is required in Single Lead mode.');
      return;
    }
    setCreating(true);
    try {
      let campaignBody = form.body;
      if (attachmentType !== 'none' && attachedPath) {
        const viewerUrl = `{{clientUrl}}/document-viewer?path=${encodeURIComponent(attachedPath)}&campaignId={{campaignId}}&leadId={{leadId}}&filename=${encodeURIComponent(attachedFilename)}`;
        campaignBody += `\n\n<p>Please review the attached document online: <a href="${viewerUrl}" target="_blank" data-track-click="true" data-track-label="${attachedFilename}">View ${attachedFilename}</a></p>`;
      }

      const campaignData = {
        ...form,
        body: campaignBody,
        attachmentPath: attachmentType !== 'none' ? attachedPath : '',
        attachmentFilename: attachmentType !== 'none' ? attachedFilename : ''
      };

      const res = await api.createCampaign(campaignData);
      const campaign = res.campaign;

      if (sendMode === 'single' && campaign) {
        // Automatically add all single/multiple lead recipients with matching names and companies
        const emails = recipientEmail
          .split(/[,;\n]+/)
          .map((e) => e.trim())
          .filter((e) => e.length > 0 && e.includes('@'));

        const names = recipientName
          .split(/[,;\n]+/)
          .map((n) => n.trim());

        const companies = recipientCompany
          .split(/[,;\n]+/)
          .map((c) => c.trim());
        
        for (let i = 0; i < emails.length; i++) {
          await api.createLead({
            campaignId: campaign.id,
            email: emails[i],
            contactName: names[i] || names[0] || 'Contact',
            companyName: companies[i] || companies[0] || '',
            title: 'Recipient'
          });
        }
        // Launch immediately
        await api.launchCampaign(campaign.id);
      } else if (sendMode === 'database' && campaign && Object.keys(selectedCompanies).length > 0) {
        const companyList = Object.values(selectedCompanies).map((c) => ({
          companyName: c.name || '',
          uei: c.uei || '',
          contactName: c.contact || '',
          email: c.email || '',
          title: c.contact_role || c.industry || 'Lead',
        }));
        await api.addCompaniesToCampaign(campaign.id, companyList);
      }

      setShowNewCampaign(false);
      setForm(emptyForm);
      setSendMode('bulk');
      setRecipientEmail('');
      setRecipientName('');
      setRecipientCompany('');
      setSelectedReport('');
      setAttachmentType('none');
      setAttachedPath('');
      setAttachedFilename('');
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

  const normalizeCompanyKey = (name, uei) => {
    if (uei) return `uei:${String(uei).trim().toLowerCase()}`;
    return `name:${String(name || '').toLowerCase().replace(/[^a-z0-9]+/g, '')}`;
  };

  const loadCompaniesInUse = useCallback(async () => {
    try {
      const res = await api.getCompaniesInUse();
      setCompaniesInUse(res?.inUse || []);
    } catch (err) {
      console.error('Failed to load companies-in-use list:', err);
    }
  }, []);

  const openAddCompanies = async (campaignId) => {
    setShowAddCompanies(campaignId);
    setCompanyQuery('');
    setCompanyResults([]);
    setSelectedCompanies({});
    setCompaniesError('');
    await loadCompaniesInUse();
  };

  const searchCompanies = useCallback(async (q, pageNum = 1) => {
    setSearchingCompanies(true);
    try {
      const res = await api.getCompanies({ query: q, page: pageNum, limit: 20 });
      setCompanyResults(res?.companies || []);
      setTotalCompaniesCount(res?.total || 0);
      setCompanyPage(pageNum);
    } catch (err) {
      setCompaniesError(err.message || 'Could not search companies.');
    } finally {
      setSearchingCompanies(false);
    }
  }, []);

  useEffect(() => {
    if (showAddCompanies === null) return;
    const t = setTimeout(() => searchCompanies(companyQuery), 300);
    return () => clearTimeout(t);
  }, [companyQuery, showAddCompanies, searchCompanies]);

  const conflictFor = (company) => {
    const key = normalizeCompanyKey(company.name, company.uei);
    return companiesInUse.find((u) => u.companyKey === key && u.campaignId !== showAddCompanies);
  };

  const toggleCompanySelection = (company) => {
    const key = normalizeCompanyKey(company.name, company.uei);
    setSelectedCompanies((prev) => {
      const next = { ...prev };
      if (next[key]) delete next[key];
      else next[key] = company;
      return next;
    });
  };

  const triggerCompanyResearch = async (name) => {
    try {
      await api.triggerResearch(name);
      searchCompanies(companyQuery);
    } catch (err) {
      alert("Failed to start research: " + err.message);
    }
  };

  const handleAddCompanies = async () => {
    const chosen = Object.values(selectedCompanies);
    if (chosen.length === 0) {
      setCompaniesError('Select at least one company.');
      return;
    }
    setAddingCompanies(true);
    setCompaniesError('');
    try {
      const { report } = await api.addCompaniesToCampaign(
        showAddCompanies,
        chosen.map((c) => ({
          uei: c.uei || '',
          companyName: c.name || '',
          contactName: c.contact || '',
          email: c.email || '',
          title: '',
          website: c.website || '',
          linkedin: c.linkedin || '',
        }))
      );

      if (report.conflicts && report.conflicts.length > 0) {
        window.alert(
          `${report.conflicts.length} compan${report.conflicts.length === 1 ? 'y is' : 'ies are'} already enrolled in another campaign and were skipped:\n\n` +
          report.conflicts.map((c) => `• ${c.message}`).join('\n')
        );
      }
      window.alert(
        `Added ${report.added} compan${report.added === 1 ? 'y' : 'ies'} to the campaign` +
        (report.duplicates ? ` (${report.duplicates} duplicates skipped)` : '') +
        (report.invalidEmail ? ` (${report.invalidEmail} missing/invalid email skipped)` : '')
      );

      setShowAddCompanies(null);
      setSelectedCompanies({});
      await loadAll();
      await loadCompaniesInUse();
    } catch (err) {
      setCompaniesError(err.message || 'Could not add companies to campaign.');
    } finally {
      setAddingCompanies(false);
    }
  };

  const loadCampaignLeads = useCallback(async (campaignId) => {
    setLoadingLeadsFor(campaignId);
    try {
      const res = await api.listLeads(campaignId);
      setCampaignLeads((prev) => ({ ...prev, [campaignId]: res?.leads || [] }));
    } catch (err) {
      setActionError(err.message || 'Could not load company data for this campaign.');
    } finally {
      setLoadingLeadsFor(null);
    }
  }, []);

  const toggleExpandCampaign = async (campaignId) => {
    if (expandedCampaign === campaignId) {
      setExpandedCampaign(null);
      return;
    }
    setExpandedCampaign(campaignId);
    if (!campaignLeads[campaignId]) {
      await loadCampaignLeads(campaignId);
    }
  };

  const handleResendLead = async (campaignId, leadId) => {
    setResendingLead(leadId);
    setActionError('');
    try {
      await api.resendLead(leadId);
      await loadCampaignLeads(campaignId);
      await loadAll();
    } catch (err) {
      setActionError(err.message || 'Could not resend to this lead.');
    } finally {
      setResendingLead(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Email Campaign"
        subtitle={
          <div className="flex items-center gap-2.5 flex-wrap">
            <span>Create, schedule, and track outbound email campaigns</span>
            {workerStatus && (
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${
                workerStatus.active
                  ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/25 dark:text-emerald-400'
                  : 'bg-rose-100 text-rose-800 dark:bg-rose-950/25 dark:text-rose-400'
              }`}>
                <span className={`h-1.5 w-1.5 rounded-full ${workerStatus.active ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
                Outbox Processor: {workerStatus.active ? 'Active' : 'Offline'}
              </span>
            )}
          </div>
        }
        action={
          <div className="flex items-center gap-2.5">
            <button
              onClick={loadAll}
              disabled={loading}
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-500 hover:bg-slate-50 hover:text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-400 dark:hover:bg-navy-700"
              title="Refresh data"
            >
              <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            </button>
            <button
              onClick={() => setShowNewCampaign(true)}
              className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft hover:bg-brand-600"
            >
              <Plus size={16} /> New Campaign
            </button>
          </div>
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

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
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
            <BarChart data={trends} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#E2E8F0" strokeDasharray="3 3" />
              <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#64748B' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#64748B' }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip
                contentStyle={{ backgroundColor: '#0F172A', borderRadius: '12px', border: 'none', color: '#FFF', fontSize: '12px' }}
                cursor={{ fill: 'rgba(148, 163, 184, 0.1)' }}
              />
              <Legend wrapperStyle={{ fontSize: 11, paddingTop: 10 }} iconType="circle" />
              <Bar dataKey="sent" name="Sent" fill="#3B82F6" radius={[4, 4, 0, 0]} barSize={12} />
              <Bar dataKey="opened" name="Opened" fill="#10B981" radius={[4, 4, 0, 0]} barSize={12} />
              <Bar dataKey="clicked" name="Clicked" fill="#F59E0B" radius={[4, 4, 0, 0]} barSize={12} />
              <Bar dataKey="replied" name="Replied" fill="#EF4444" radius={[4, 4, 0, 0]} barSize={12} />
            </BarChart>
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
              <th className="px-5 py-3 font-semibold w-8"></th>
              <th className="px-5 py-3 font-semibold">#</th>
              <th className="px-5 py-3 font-semibold">Campaign</th>
              <th className="px-5 py-3 font-semibold">Status</th>
              <th className="px-5 py-3 font-semibold">Sent</th>
              <th className="px-5 py-3 font-semibold">Opened</th>
              <th className="px-5 py-3 font-semibold">Clicked</th>
              <th className="px-5 py-3 font-semibold">Replied</th>
              <th className="px-5 py-3 font-semibold">Resent</th>
              <th className="px-5 py-3 font-semibold">Created</th>
              <th className="px-5 py-3 font-semibold text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {!loading && campaigns.length === 0 && (
              <tr>
                <td colSpan={10} className="px-5 py-8 text-center text-sm text-slate-400 dark:text-slate-500">
                  No campaigns yet — click "New Campaign" to create your first one.
                </td>
              </tr>
            )}
            {campaigns.map((c) => {
              const isExpanded = expandedCampaign === c.id;
              const leads = campaignLeads[c.id] || [];
              return (
              <Fragment key={c.id}>
                <tr className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60 dark:border-navy-800/40 dark:hover:bg-navy-800/40">
                  <td className="px-5 py-3.5">
                    <button
                      title="Show companies in this campaign"
                      onClick={() => toggleExpandCampaign(c.id)}
                      className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-navy-900 dark:hover:bg-navy-800 dark:hover:text-white"
                    >
                      {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                    </button>
                  </td>
                  <td className="px-5 py-3.5 text-slate-400 dark:text-slate-500 font-mono text-xs">{c.campaignNumber ? `#${c.campaignNumber}` : '—'}</td>
                  <td className="px-5 py-3.5 font-semibold text-navy-900 dark:text-white">{c.name}</td>
                  <td className="px-5 py-3.5"><StatusBadge status={titleCase(c.status)} /></td>
                  <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{(c.stats?.totalSent || 0).toLocaleString()}</td>
                  <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{(c.stats?.totalOpened || 0).toLocaleString()}</td>
                  <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{(c.stats?.totalClicked || 0).toLocaleString()}</td>
                  <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{(c.stats?.totalReplied || 0).toLocaleString()}</td>
                  <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{(c.stats?.totalResent || 0).toLocaleString()}</td>
                  <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{c.createdAt ? new Date(c.createdAt).toLocaleDateString() : ''}</td>
                  <td className="px-5 py-3.5">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        title="Select companies for this campaign"
                        onClick={() => openAddCompanies(c.id)}
                        className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-brand-600 dark:hover:bg-navy-800"
                      >
                        <Building2 size={15} />
                      </button>
                      <button
                        title="Add lead manually"
                        onClick={() => setShowAddLead(c.id)}
                        className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-navy-900 dark:hover:bg-navy-800 dark:hover:text-white"
                      >
                        <Plus size={15} />
                      </button>
                      <label
                        title="Import leads from CSV"
                        className="cursor-pointer rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-navy-900 dark:hover:bg-navy-800 dark:hover:text-white"
                      >
                        <Upload size={15} className={importingFor === c.id ? 'animate-pulse' : ''} />
                        <input
                          type="file"
                          accept=".csv"
                          className="hidden"
                          onChange={(e) => e.target.files?.[0] && handleCsvUpload(c.id, e.target.files[0])}
                        />
                      </label>
                      {(c.status === 'draft' || c.status === 'paused') && (
                        <button title="Launch / resume sending" onClick={() => handleAction(c.status === 'draft' ? 'launch' : 'resume', c.id)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-emerald-600 dark:hover:bg-navy-800">
                          {c.status === 'draft' ? <Rocket size={15} /> : <Play size={15} />}
                        </button>
                      )}
                      {c.status === 'running' && (
                        <button title="Pause" onClick={() => handleAction('pause', c.id)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-amber-600 dark:hover:bg-navy-800">
                          <Pause size={15} />
                        </button>
                      )}
                      <button title="Duplicate" onClick={() => handleAction('duplicate', c.id)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-navy-900 dark:hover:bg-navy-800 dark:hover:text-white">
                        <Copy size={15} />
                      </button>
                      <button title="Delete" onClick={() => handleAction('delete', c.id)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-rose-600 dark:hover:bg-navy-800">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
                {isExpanded && (
                  <tr className="bg-slate-50/60 dark:bg-navy-900/40">
                    <td colSpan={10} className="px-5 py-4">
                      <div className="rounded-xl border border-slate-100 bg-white dark:border-navy-700 dark:bg-navy-800 overflow-hidden">
                        <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-100 dark:border-navy-700">
                          <p className="text-xs font-bold text-navy-900 dark:text-white">Companies in "{c.name}"</p>
                          <p className="text-[11px] text-slate-400">{leads.length} compan{leads.length === 1 ? 'y' : 'ies'}</p>
                        </div>
                        {loadingLeadsFor === c.id ? (
                          <div className="px-4 py-6 text-center text-xs text-slate-400">Loading company data…</div>
                        ) : leads.length === 0 ? (
                          <div className="px-4 py-6 text-center text-xs text-slate-400">No companies added yet. Use the building icon above to select companies.</div>
                        ) : (
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-left text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500 border-b border-slate-100 dark:border-navy-700">
                                <th className="px-4 py-2 font-semibold">Company</th>
                                <th className="px-4 py-2 font-semibold">Contact</th>
                                <th className="px-4 py-2 font-semibold">Email</th>
                                <th className="px-4 py-2 font-semibold">Status</th>
                                <th className="px-4 py-2 font-semibold">Sent</th>
                                <th className="px-4 py-2 font-semibold">Opened</th>
                                <th className="px-4 py-2 font-semibold">Clicked</th>
                                <th className="px-4 py-2 font-semibold">Replied</th>
                                <th className="px-4 py-2 font-semibold">Resends</th>
                                <th className="px-4 py-2 font-semibold text-right">Action</th>
                              </tr>
                            </thead>
                            <tbody>
                              {leads.map((l) => (
                                <tr key={l.id} className="border-b border-slate-50 last:border-0 dark:border-navy-800/40">
                                  <td className="px-4 py-2 font-semibold text-navy-900 dark:text-white">{l.companyName || '—'}</td>
                                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{l.contactName || '—'}</td>
                                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{l.email}</td>
                                  <td className="px-4 py-2"><StatusBadge status={titleCase(l.status)} /></td>
                                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{l.sentAt ? <Check size={13} className="text-emerald-500" /> : '—'}</td>
                                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{l.openedAt ? <Check size={13} className="text-emerald-500" /> : '—'}</td>
                                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{l.clickedAt ? <Check size={13} className="text-emerald-500" /> : '—'}</td>
                                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">
                                    {l.repliedAt || l.status === 'replied' || l.replyMessage ? (
                                      <button
                                        onClick={() => setViewingReplyLead(l)}
                                        className="inline-flex items-center gap-1 rounded-md bg-rose-50 px-2 py-0.5 text-[11px] font-bold text-rose-600 hover:bg-rose-100 dark:bg-rose-950/40 dark:text-rose-400 transition-colors"
                                        title="View incoming email reply text"
                                      >
                                        <Mail size={11} /> View Reply
                                      </button>
                                    ) : '—'}
                                  </td>
                                  <td className="px-4 py-2 text-slate-500 dark:text-slate-400">{l.resendCount || 0}</td>
                                  <td className="px-4 py-2 text-right">
                                    <button
                                      title="Resend email to this company"
                                      onClick={() => handleResendLead(c.id, l.id)}
                                      disabled={resendingLead === l.id}
                                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1 text-[11px] font-semibold text-slate-500 hover:bg-slate-50 hover:text-brand-600 disabled:opacity-50 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-900"
                                    >
                                      <RotateCw size={11} className={resendingLead === l.id ? 'animate-spin' : ''} />
                                      Resend
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
              );
            })}
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
            <form onSubmit={handleCreateCampaign} className="p-5 space-y-4 max-h-[75vh] overflow-y-auto">
              {formError && (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
                  {formError}
                </div>
              )}

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400 font-bold">Campaign Name *</label>
                <input
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="E.g., Q3 GovTech Procurement Outreach"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>

              {/* Recipient Mode Selection */}
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400 font-bold">Recipient Mode</label>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => setSendMode('bulk')}
                    className={`rounded-lg border px-2.5 py-2 text-xs font-semibold transition-all ${
                      sendMode === 'bulk'
                        ? 'border-brand-500 bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-900'
                    }`}
                  >
                    Draft (CSV later)
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSendMode('database');
                      if (companyResults.length === 0) searchCompanies('');
                    }}
                    className={`rounded-lg border px-2.5 py-2 text-xs font-semibold transition-all ${
                      sendMode === 'database'
                        ? 'border-brand-500 bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-900'
                    }`}
                  >
                    Select DB Companies
                  </button>
                  <button
                    type="button"
                    onClick={() => setSendMode('single')}
                    className={`rounded-lg border px-2.5 py-2 text-xs font-semibold transition-all ${
                      sendMode === 'single'
                        ? 'border-brand-500 bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-900'
                    }`}
                  >
                    Single Lead
                  </button>
                </div>
                <p className="mt-1 text-[11px] text-slate-400">
                  {sendMode === 'bulk' && 'Creates a draft campaign. You can import contacts via CSV or add them manually later.'}
                  {sendMode === 'database' && 'Pick registered prospect companies directly from your database to automatically enroll as leads.'}
                  {sendMode === 'single' && 'Sends the email to a single recipient immediately upon creation.'}
                </p>
              </div>

              {/* Database Company Multi-Select Details */}
              {sendMode === 'database' && (
                <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-3 space-y-3 dark:border-navy-700 dark:bg-navy-900/50">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold text-navy-900 dark:text-white uppercase tracking-wider">Select Companies from Database</h4>
                    <span className="text-[11px] font-bold text-brand-600">{Object.keys(selectedCompanies).length} Selected</span>
                  </div>
                  <div className="relative">
                    <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      value={companyQuery}
                      onChange={(e) => setCompanyQuery(e.target.value)}
                      placeholder="Search registered companies by name or contact…"
                      className="w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 py-1.5 text-xs text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                    />
                  </div>
                  <div className="max-h-48 overflow-y-auto rounded-lg border border-slate-200 bg-white dark:border-navy-700 dark:bg-navy-900">
                    {searchingCompanies ? (
                      <div className="p-4 text-center text-xs text-slate-400">Searching database…</div>
                    ) : companyResults.length === 0 ? (
                      <div className="p-4 text-center text-xs text-slate-400">No companies found.</div>
                    ) : (
                      companyResults.map((c) => {
                        const key = normalizeCompanyKey(c.name, c.uei);
                        const selected = !!selectedCompanies[key];
                        const hasEmail = !!c.email;
                        const isResearching = c.isResearching;
                        return (
                          <label key={c.id || key} className="flex items-center justify-between p-2.5 hover:bg-slate-50 dark:hover:bg-navy-800 cursor-pointer border-b border-slate-50 last:border-0">
                            <div>
                              <p className="text-xs font-bold text-navy-900 dark:text-white">{c.name}</p>
                              <p className="text-[11px] text-slate-400">
                                {c.email || (isResearching ? '⏳ Research in progress...' : '❌ No email (requires research)')}
                                {c.contact ? ` · ${c.contact}` : ''}
                              </p>
                            </div>
                            {hasEmail ? (
                              <input
                                type="checkbox"
                                checked={selected}
                                onChange={() => toggleCompanySelection(c)}
                                className="rounded border-slate-300 text-brand-500 focus:ring-brand-500"
                              />
                            ) : isResearching ? (
                              <Loader2 className="animate-spin text-brand-500 animate-duration-1000" size={14} />
                            ) : (
                              <button
                                type="button"
                                onClick={(e) => { e.preventDefault(); e.stopPropagation(); triggerCompanyResearch(c.name); }}
                                className="rounded bg-brand-500 hover:bg-brand-600 px-2 py-1 text-[10px] font-bold text-white shadow-soft transition-colors"
                              >
                                Research
                              </button>
                            )}
                          </label>
                        );
                      })
                    )}
                  </div>
                  <div className="flex items-center justify-between pt-1 text-xs">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        disabled={companyPage <= 1 || searchingCompanies}
                        onClick={() => searchCompanies(companyQuery, companyPage - 1)}
                        className="rounded-lg border border-slate-200 px-2.5 py-1 font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40 dark:border-navy-700 dark:text-slate-300 text-[11px]"
                      >
                        Prev
                      </button>
                      <span className="text-[11px] text-slate-500">
                        Pg {companyPage}/{Math.max(1, Math.ceil(totalCompaniesCount / 20))} ({totalCompaniesCount.toLocaleString()} total)
                      </span>
                      <button
                        type="button"
                        disabled={companyPage >= Math.ceil(totalCompaniesCount / 20) || searchingCompanies}
                        onClick={() => searchCompanies(companyQuery, companyPage + 1)}
                        className="rounded-lg border border-slate-200 px-2.5 py-1 font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40 dark:border-navy-700 dark:text-slate-300 text-[11px]"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Single Recipient Details */}
              {sendMode === 'single' && (
                <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-3 space-y-3 dark:border-navy-700 dark:bg-navy-900/50">
                  <h4 className="text-xs font-bold text-navy-900 dark:text-white uppercase tracking-wider">Recipient Details</h4>
                  <div>
                    <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Recipient Email(s) * <span className="font-normal text-slate-400">(Supports multiple emails separated by comma)</span></label>
                    <input
                      type="text"
                      required={sendMode === 'single'}
                      value={recipientEmail}
                      onChange={(e) => setRecipientEmail(e.target.value)}
                      placeholder="E.g., procurement@client.com, sarah@client.com"
                      className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Recipient Name(s) <span className="font-normal text-slate-400">(Comma separated)</span></label>
                      <input
                        value={recipientName}
                        onChange={(e) => setRecipientName(e.target.value)}
                        placeholder="E.g., John Doe, Sarah Smith"
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                      />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Recipient Company(ies) <span className="font-normal text-slate-400">(Comma separated)</span></label>
                      <input
                        value={recipientCompany}
                        onChange={(e) => setRecipientCompany(e.target.value)}
                        placeholder="E.g., Acme Corp, Tech Inc"
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Attachment Mode Selection */}
              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400 font-bold">Campaign PDF Attachment (Optional)</label>
                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={() => { setAttachmentType('none'); setAttachedPath(''); setAttachedFilename(''); setSelectedReport(''); }}
                    className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-all ${
                      attachmentType === 'none'
                        ? 'border-brand-500 bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-900'
                    }`}
                  >
                    No Attachment
                  </button>
                  <button
                    type="button"
                    onClick={() => { setAttachmentType('report'); setAttachedPath(''); setAttachedFilename(''); setSelectedReport(''); }}
                    className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-all ${
                      attachmentType === 'report'
                        ? 'border-brand-500 bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-900'
                    }`}
                  >
                    Link Report
                  </button>
                  <button
                    type="button"
                    onClick={() => { setAttachmentType('device'); setAttachedPath(''); setAttachedFilename(''); setSelectedReport(''); }}
                    className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-all ${
                      attachmentType === 'device'
                        ? 'border-brand-500 bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-900'
                    }`}
                  >
                    Upload File
                  </button>
                </div>
              </div>

              {/* Conditional inputs */}
              {attachmentType === 'report' && (
                <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-3 dark:border-navy-700 dark:bg-navy-900/50">
                  <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Select Generated Report *</label>
                  <select
                    value={selectedReport}
                    onChange={(e) => handleReportChange(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                  >
                    <option value="">Choose a report...</option>
                    {reportsList.map((rep) => (
                      <option key={rep.filename} value={rep.filename}>
                        {rep.title} ({rep.company_name})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {attachmentType === 'device' && (
                <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-3 space-y-2 dark:border-navy-700 dark:bg-navy-900/50">
                  <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Upload PDF from device *</label>
                  <input
                    type="file"
                    accept=".pdf"
                    onChange={handleDeviceFileUpload}
                    className="w-full text-xs text-slate-500 file:mr-4 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-brand-50 file:text-brand-700 hover:file:bg-brand-100"
                  />
                  {uploadingFile && <p className="text-[10px] text-brand-500 font-medium">Uploading PDF to server...</p>}
                  {attachedFilename && !uploadingFile && (
                    <p className="text-[10px] text-emerald-600 font-bold">✓ Attached: {attachedFilename}</p>
                  )}
                </div>
              )}

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400 font-bold">Subject Line *</label>
                <input
                  required
                  value={form.subject}
                  onChange={(e) => setForm({ ...form, subject: e.target.value })}
                  placeholder="E.g., Business partnership proposal"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Sender Name</label>
                  <input
                    value={form.senderName}
                    onChange={(e) => setForm({ ...form, senderName: e.target.value })}
                    placeholder="E.g., OrbitAvanya Outreach"
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Sender Email</label>
                  <input
                    value={form.senderEmail}
                    onChange={(e) => setForm({ ...form, senderEmail: e.target.value })}
                    placeholder="E.g., sender@verified.com"
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400 font-bold font-bold">Email HTML Body</label>
                <textarea
                  value={form.body}
                  onChange={(e) => setForm({ ...form, body: e.target.value })}
                  placeholder="<p>Hi {{firstName}},</p><p>We analyzed {{companyName}} and...</p>"
                  rows={6}
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>

              <div className="flex justify-end gap-2 border-t border-slate-100 dark:border-navy-700 pt-4">
                <button
                  type="button"
                  onClick={() => setShowNewCampaign(false)}
                  className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating || uploadingFile}
                  className="rounded-lg bg-brand-500 px-4 py-2 text-xs font-bold text-white shadow-soft hover:bg-brand-600 disabled:opacity-60"
                >
                  {creating ? 'Creating…' : 'Create Campaign'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showAddLead && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/60 p-4 backdrop-blur-xs"
          onClick={() => !addingLead && setShowAddLead(null)}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-white dark:bg-navy-800 shadow-soft overflow-hidden border border-slate-100 dark:border-navy-700"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 p-5">
              <div>
                <h3 className="text-sm font-bold text-navy-900 dark:text-white">Add Lead Manually</h3>
                <p className="text-xs text-slate-400 mt-0.5">Add a single recipient email to the campaign outreach list.</p>
              </div>
              <button onClick={() => setShowAddLead(null)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-navy-900">
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleAddLead} className="p-5 space-y-4 text-left">
              {leadError && (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
                  {leadError}
                </div>
              )}

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Recipient Email Address</label>
                <input
                  type="email"
                  required
                  value={leadForm.email}
                  onChange={(e) => setLeadForm({ ...leadForm, email: e.target.value })}
                  placeholder="name@company.com"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Contact Name</label>
                <input
                  type="text"
                  value={leadForm.contactName}
                  onChange={(e) => setLeadForm({ ...leadForm, contactName: e.target.value })}
                  placeholder="John Doe"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Company Name</label>
                <input
                  type="text"
                  value={leadForm.companyName}
                  onChange={(e) => setLeadForm({ ...leadForm, companyName: e.target.value })}
                  placeholder="Acme Corp"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>

              <div>
                <label className="mb-1 block text-xs font-semibold text-slate-500 dark:text-slate-400">Job Title</label>
                <input
                  type="text"
                  value={leadForm.title}
                  onChange={(e) => setLeadForm({ ...leadForm, title: e.target.value })}
                  placeholder="Procurement Officer"
                  className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100 dark:border-navy-700">
                <button
                  type="button"
                  onClick={() => setShowAddLead(null)}
                  className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addingLead}
                  className="rounded-lg bg-brand-500 px-4 py-2 text-xs font-bold text-white shadow-soft hover:bg-brand-600 disabled:opacity-60"
                >
                  {addingLead ? 'Adding...' : 'Add Lead'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showAddCompanies !== null && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/60 p-4 backdrop-blur-xs"
          onClick={() => !addingCompanies && setShowAddCompanies(null)}
        >
          <div
            className="w-full max-w-2xl rounded-2xl bg-white dark:bg-navy-800 shadow-soft overflow-hidden border border-slate-100 dark:border-navy-700"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 p-5">
              <div>
                <h3 className="text-sm font-bold text-navy-900 dark:text-white">Select Companies</h3>
                <p className="text-xs text-slate-400 mt-0.5">Pick one or more companies to enroll in this campaign. A company already running in another campaign can't be selected again.</p>
              </div>
              <button onClick={() => setShowAddCompanies(null)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 dark:hover:bg-navy-900">
                <X size={18} />
              </button>
            </div>

            <div className="p-5 space-y-3">
              {companiesError && (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
                  {companiesError}
                </div>
              )}

              <div className="relative">
                <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  value={companyQuery}
                  onChange={(e) => setCompanyQuery(e.target.value)}
                  placeholder="Search companies by name, UEI, or contact…"
                  className="w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>

              <div className="max-h-80 overflow-y-auto rounded-xl border border-slate-100 dark:border-navy-700">
                {searchingCompanies ? (
                  <div className="px-4 py-6 text-center text-xs text-slate-400">Searching…</div>
                ) : companyResults.length === 0 ? (
                  <div className="px-4 py-6 text-center text-xs text-slate-400">No companies found.</div>
                ) : (
                  companyResults.map((company) => {
                    const key = normalizeCompanyKey(company.name, company.uei);
                    const conflict = conflictFor(company);
                    const selected = !!selectedCompanies[key];
                    const hasEmail = !!company.email;
                    const isResearching = company.isResearching;
                    return (
                      <div
                        key={company.uei || key}
                        className={`flex w-full items-center justify-between gap-3 border-b border-slate-50 px-4 py-2.5 text-left last:border-0 dark:border-navy-800/40 ${
                          selected
                            ? 'bg-brand-50 dark:bg-brand-500/10'
                            : 'hover:bg-slate-50 dark:hover:bg-navy-900/60'
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          {hasEmail ? (
                            <button
                              type="button"
                              onClick={() => toggleCompanySelection(company)}
                              className={`flex h-5 w-5 items-center justify-center rounded-md border ${selected ? 'border-brand-500 bg-brand-500' : 'border-slate-300 dark:border-navy-600'}`}
                            >
                              {selected && <Check size={12} className="text-white" />}
                            </button>
                          ) : isResearching ? (
                            <Loader2 className="animate-spin text-brand-500 animate-duration-1000" size={14} />
                          ) : (
                            <button
                              type="button"
                              onClick={() => triggerCompanyResearch(company.name)}
                              className="rounded bg-brand-500 hover:bg-brand-600 px-2 py-1 text-[10px] font-bold text-white shadow-soft transition-colors"
                            >
                              Research
                            </button>
                          )}
                          <div>
                            <p className="text-xs font-semibold text-navy-900 dark:text-white">{company.name}</p>
                            <p className="text-[11px] text-slate-400">
                              {company.email || (isResearching ? '⏳ Research in progress...' : '❌ No email (requires research)')}
                              {company.contact ? ` · ${company.contact}` : ''}
                            </p>
                          </div>
                        </div>
                        {conflict && (
                          <span className="flex items-center gap-1 rounded-full bg-rose-50 px-2 py-1 text-[10px] font-semibold text-rose-600 dark:bg-rose-950/30 dark:text-rose-400">
                            <AlertTriangle size={11} /> In "{conflict.campaignName}"
                          </span>
                        )}
                      </div>
                    );
                  })
                )}
              </div>

              <div className="flex items-center justify-between border-t border-slate-100 dark:border-navy-700 pt-3 text-xs">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={companyPage <= 1 || searchingCompanies}
                    onClick={() => searchCompanies(companyQuery, companyPage - 1)}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40 dark:border-navy-700 dark:text-slate-300"
                  >
                    Previous
                  </button>
                  <span className="text-slate-500 font-medium">
                    Page {companyPage} of {Math.max(1, Math.ceil(totalCompaniesCount / 20))} ({totalCompaniesCount.toLocaleString()} total)
                  </span>
                  <button
                    type="button"
                    disabled={companyPage >= Math.ceil(totalCompaniesCount / 20) || searchingCompanies}
                    onClick={() => searchCompanies(companyQuery, companyPage + 1)}
                    className="rounded-lg border border-slate-200 px-3 py-1.5 font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-40 dark:border-navy-700 dark:text-slate-300"
                  >
                    Next
                  </button>
                </div>
                <span className="font-bold text-brand-600 dark:text-brand-400">
                  {Object.keys(selectedCompanies).length} Selected
                </span>
              </div>

              <div className="flex justify-end gap-2 border-t border-slate-100 dark:border-navy-700 pt-4">
                <button
                  type="button"
                  onClick={() => setShowAddCompanies(null)}
                  className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleAddCompanies}
                  disabled={addingCompanies || Object.keys(selectedCompanies).length === 0}
                  className="rounded-lg bg-brand-500 px-4 py-2 text-xs font-bold text-white shadow-soft hover:bg-brand-600 disabled:opacity-60"
                >
                  {addingCompanies ? 'Adding…' : `Add ${Object.keys(selectedCompanies).length || ''} to Campaign`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Incoming Reply Email Viewer Modal */}
      {viewingReplyLead && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/70 p-4 backdrop-blur-xs"
          onClick={() => setViewingReplyLead(null)}
        >
          <div
            className="w-full max-w-xl rounded-2xl bg-white dark:bg-navy-800 shadow-2xl overflow-hidden border border-slate-100 dark:border-navy-700"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 px-5 py-4">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-rose-50 text-rose-600 dark:bg-rose-950/40 dark:text-rose-400">
                  <Mail size={18} />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-navy-900 dark:text-white">Incoming Reply Email</h3>
                  <p className="text-xs text-slate-400">
                    From {viewingReplyLead.contactName || viewingReplyLead.companyName} ({viewingReplyLead.email})
                  </p>
                </div>
              </div>
              <button
                onClick={() => setViewingReplyLead(null)}
                className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-100 hover:text-navy-900 dark:hover:bg-navy-700 dark:hover:text-white"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-3.5 dark:border-navy-700 dark:bg-navy-900/50 space-y-1">
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Subject</p>
                <p className="text-xs font-bold text-navy-900 dark:text-white">
                  {viewingReplyLead.replySubject || "Re: Outreach"}
                </p>
              </div>

              <div className="rounded-xl border border-slate-100 bg-white p-4 dark:border-navy-700 dark:bg-navy-900 space-y-1 max-h-60 overflow-y-auto">
                <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-2">Message Body</p>
                <div className="text-xs text-slate-700 dark:text-slate-200 whitespace-pre-wrap leading-relaxed font-sans">
                  {viewingReplyLead.replyMessage || viewingReplyLead.replyPreview || "No reply body text captured yet."}
                </div>
              </div>

              <div className="flex justify-end pt-2">
                <button
                  onClick={() => setViewingReplyLead(null)}
                  className="rounded-xl bg-navy-900 px-4 py-2 text-xs font-bold text-white hover:bg-navy-800 dark:bg-brand-500 dark:hover:bg-brand-600"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
