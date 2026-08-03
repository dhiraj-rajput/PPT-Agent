import { useState, useEffect, useRef } from 'react';
import { 
  Plus, X, Trash2, Upload, Search, Check, AlertCircle, RefreshCw, Layers, 
  User, Users, ClipboardList, MessageSquare, ChevronRight, Edit2, Play, 
  Pause, Globe, Shield, Activity, CheckCircle2, Loader2, Keyboard, MousePointer,
  Send, Inbox, HelpCircle, Smile, Linkedin, Circle
} from 'lucide-react';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { api, BASE_URL } from '../lib/api.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';

export default function LinkedInOutreach() {
  const { createAlert } = useNotifications();
  const notify = (title, message) => createAlert(title, message).catch(() => {});

  const [currentTab, setCurrentTab] = useState('campaigns'); // 'campaigns' | 'inbox' | 'accounts'

  // =========================================================================
  // CAMPAIGNS TAB STATE
  // =========================================================================
  const [campaigns, setCampaigns] = useState([]);
  const [campaignsLoading, setCampaignsLoading] = useState(true);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [campaignActiveTab, setCampaignActiveTab] = useState('targets'); // 'targets' | 'queue'
  const [targets, setTargets] = useState([]);
  const [queue, setQueue] = useState([]);
  const [targetsLoading, setTargetsLoading] = useState(false);
  const [queueLoading, setQueueLoading] = useState(false);

  const [showNewCampaign, setShowNewCampaign] = useState(false);
  const [newCampaignForm, setNewCampaignForm] = useState({
    name: '',
    mode: 'manual',
    role_filter: '',
    message_generation_mode: 'llm',
    connection_note_prompt: 'Keep it friendly and professional, referencing their headline.',
    followup_prompt: 'Thank them for connecting and ask if they are open to sharing outreach ideas.',
    require_approval: true
  });
  const [csvFile, setCsvFile] = useState(null);
  const [uploadingTargets, setUploadingTargets] = useState(false);
  const [editingMessageId, setEditingMessageId] = useState(null);
  const [editingContent, setEditingContent] = useState('');

  // =========================================================================
  // INBOX TAB STATE
  // =========================================================================
  const [inboxItems, setInboxItems] = useState([]);
  const [inboxLoading, setInboxLoading] = useState(true);
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [replyText, setReplyText] = useState('');
  const [sendingReply, setSendingReply] = useState(false);

  // =========================================================================
  // ACCOUNTS TAB STATE
  // =========================================================================
  const [accounts, setAccounts] = useState([]);
  const [accountsLoading, setAccountsLoading] = useState(true);
  const [accountsError, setAccountsError] = useState('');
  const [isAccountModalOpen, setIsAccountModalOpen] = useState(false);
  const [connectLabel, setConnectLabel] = useState('');
  const [connectRegion, setConnectRegion] = useState('usa');
  const [connectStep, setConnectStep] = useState(1); // 1 = setup, 2 = websocket stream
  const [wsStatus, setWsStatus] = useState('idle');
  const [wsMessage, setWsMessage] = useState('');
  const [screenImage, setScreenImage] = useState(null);
  const [manualText, setManualText] = useState('');
  const wsRef = useRef(null);
  const imageRef = useRef(null);

  // =========================================================================
  // INITIAL LOADERS & FETCHERS
  // =========================================================================
  useEffect(() => {
    if (currentTab === 'campaigns') {
      fetchCampaigns();
    } else if (currentTab === 'inbox') {
      fetchInbox();
    } else if (currentTab === 'accounts') {
      fetchAccounts();
    }
  }, [currentTab]);

  // Campaigns
  const fetchCampaigns = async () => {
    try {
      setCampaignsLoading(true);
      const res = await api.listLinkedInCampaigns();
      setCampaigns(res.campaigns || []);
    } catch (err) {
      notify('Error', `Failed to load campaigns: ${err.message}`);
    } finally {
      setCampaignsLoading(false);
    }
  };

  const loadCampaignData = async (campaign) => {
    setSelectedCampaign(campaign);
    if (!campaign) return;
    
    setTargetsLoading(true);
    try {
      const res = await api.getLinkedInTargets(campaign.id);
      setTargets(res.targets || []);
    } catch (err) {
      notify('Error', `Failed to load targets: ${err.message}`);
    } finally {
      setTargetsLoading(false);
    }

    setQueueLoading(true);
    try {
      const res = await api.getLinkedInQueue(campaign.id);
      setQueue(res.queue || []);
    } catch (err) {
      notify('Error', `Failed to load message queue: ${err.message}`);
    } finally {
      setQueueLoading(false);
    }
  };

  const handleCreateCampaign = async (e) => {
    e.preventDefault();
    if (!newCampaignForm.name.trim()) return;
    
    try {
      await api.createLinkedInCampaign(newCampaignForm);
      notify('Success', 'LinkedIn campaign created successfully.');
      setShowNewCampaign(false);
      setNewCampaignForm({
        name: '',
        mode: 'manual',
        role_filter: '',
        message_generation_mode: 'llm',
        connection_note_prompt: 'Keep it friendly and professional, referencing their headline.',
        followup_prompt: 'Thank them for connecting and ask if they are open to sharing outreach ideas.',
        require_approval: true
      });
      fetchCampaigns();
    } catch (err) {
      notify('Error', `Failed to create campaign: ${err.message}`);
    }
  };

  const handleDeleteCampaign = async (campaignId) => {
    if (!confirm('Are you sure you want to delete this campaign? All targets and logs will be deleted.')) return;
    try {
      await api.deleteLinkedInCampaign(campaignId);
      notify('Success', 'Campaign deleted.');
      if (selectedCampaign?.id === campaignId) {
        setSelectedCampaign(null);
      }
      fetchCampaigns();
    } catch (err) {
      notify('Error', `Failed to delete campaign: ${err.message}`);
    }
  };

  const handleImportTargets = async (e) => {
    e.preventDefault();
    if (!csvFile || !selectedCampaign) return;
    
    setUploadingTargets(true);
    try {
      const res = await api.importLinkedInTargets(selectedCampaign.id, { file: csvFile });
      notify('Import Complete', res.message || `Imported targets successfully.`);
      setCsvFile(null);
      loadCampaignData(selectedCampaign);
    } catch (err) {
      notify('Error', `Failed to import targets: ${err.message}`);
    } finally {
      setUploadingTargets(false);
    }
  };

  const handleReviewMessage = async (messageId, action, finalContent) => {
    try {
      await api.reviewLinkedInMessage(messageId, {
        content: finalContent || editingContent,
        action: action
      });
      notify('Success', `Message ${action}ed.`);
      setEditingMessageId(null);
      loadCampaignData(selectedCampaign);
    } catch (err) {
      notify('Error', `Failed to review message: ${err.message}`);
    }
  };

  // Inbox
  const fetchInbox = async () => {
    try {
      setInboxLoading(true);
      const res = await api.getLinkedInInbox();
      setInboxItems(res.inbox || []);
      if (res.inbox && res.inbox.length > 0 && !selectedConversation) {
        setSelectedConversation(res.inbox[0]);
      }
    } catch (err) {
      notify('Error', `Failed to load LinkedIn inbox: ${err.message}`);
    } finally {
      setInboxLoading(false);
    }
  };

  const handleSendReply = async (e) => {
    e.preventDefault();
    if (!replyText.trim() || !selectedConversation) return;

    setSendingReply(true);
    try {
      await api.sendLinkedInReply(selectedConversation.target_id, replyText);
      notify('Success', 'Manual reply queued for sending.');
      setReplyText('');
      fetchInbox();
    } catch (err) {
      notify('Error', `Failed to send reply: ${err.message}`);
    } finally {
      setSendingReply(false);
    }
  };

  // Accounts
  const fetchAccounts = async () => {
    try {
      setAccountsLoading(true);
      const data = await api.getLinkedInAccounts();
      setAccounts(data || []);
      setAccountsError('');
    } catch (err) {
      setAccountsError(err.message || 'Failed to fetch accounts.');
    } finally {
      setAccountsLoading(false);
    }
  };

  const handlePauseAccount = async (id) => {
    try {
      await api.pauseLinkedInAccount(id);
      fetchAccounts();
    } catch (err) {
      notify('Error', err.message || 'Failed to pause account.');
    }
  };

  const handleResumeAccount = async (id) => {
    try {
      await api.resumeLinkedInAccount(id);
      fetchAccounts();
    } catch (err) {
      notify('Error', err.message || 'Failed to resume account.');
    }
  };

  const handleDeleteAccount = async (id) => {
    if (!window.confirm('Are you sure you want to disconnect this LinkedIn account?')) return;
    try {
      await api.deleteLinkedInAccount(id);
      fetchAccounts();
    } catch (err) {
      notify('Error', err.message || 'Failed to delete account.');
    }
  };

  const startGuidedLogin = () => {
    if (!connectLabel.trim()) {
      alert('Please enter an account label.');
      return;
    }
    setConnectStep(2);
    setWsStatus('connecting');
    setWsMessage('Initializing remote browser context...');
    
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsBase = BASE_URL.replace(/^http/, 'ws');
    const token = localStorage.getItem('orbitavanya_token');
    const wsUrl = `${wsBase}/api/linkedin/accounts/connect/ws?region=${connectRegion}&label=${encodeURIComponent(connectLabel)}&token=${token}`;
    
    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'status') {
          setWsStatus(data.status);
          setWsMessage(data.message);
          if (data.status === 'authenticated') {
            setTimeout(() => {
              closeConnectModal();
              fetchAccounts();
            }, 3000);
          }
        } else if (data.type === 'screen') {
          setScreenImage(data.image);
        }
      } catch (e) {
        console.error('Error parsing WS message:', e);
      }
    };

    socket.onclose = (event) => {
      setWsStatus('closed');
      setWsMessage(event.reason || 'Browser session disconnected.');
    };

    socket.onerror = (err) => {
      console.error('WebSocket error:', err);
      setWsStatus('error');
      setWsMessage('WebSocket connection failed.');
    };
  };

  const handleImageClick = (e) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    if (!imageRef.current) return;

    const rect = imageRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    const scaleX = 1280 / rect.width;
    const scaleY = 800 / rect.height;
    const x = Math.round(clickX * scaleX);
    const y = Math.round(clickY * scaleY);

    wsRef.current.send(JSON.stringify({ type: 'click', x, y }));
  };

  const handleKeyDown = (e) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    
    const preventKeys = ['ArrowUp', 'ArrowDown', 'Space', 'Tab', 'Backspace', 'Enter'];
    if (preventKeys.includes(e.key)) {
      e.preventDefault();
    }

    if (e.key.length === 1) {
      wsRef.current.send(JSON.stringify({ type: 'type', text: e.key }));
    } else {
      wsRef.current.send(JSON.stringify({ type: 'press', key: e.key }));
    }
  };

  const sendManualText = () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    if (!manualText) return;
    wsRef.current.send(JSON.stringify({ type: 'type', text: manualText }));
    setManualText('');
  };

  const sendSpecialKey = (key) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: 'press', key }));
  };

  const closeConnectModal = () => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    wsRef.current = null;
    setScreenImage(null);
    setConnectLabel('');
    setConnectStep(1);
    setWsStatus('idle');
    setIsAccountModalOpen(false);
  };

  const getIntentBadge = (intent) => {
    const styles = {
      interested: 'bg-emerald-100 text-emerald-700',
      meeting_request: 'bg-indigo-100 text-indigo-700',
      objection: 'bg-amber-100 text-amber-700',
      not_interested: 'bg-rose-100 text-rose-700',
      out_of_office: 'bg-slate-100 text-slate-600',
      unclear: 'bg-slate-100 text-slate-500'
    };
    return (
      <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold ${styles[intent] || 'bg-slate-100 text-slate-500'}`}>
        {intent ? intent.replace('_', ' ').toUpperCase() : 'UNCLEAR'}
      </span>
    );
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      {/* Page Header */}
      <PageHeader 
        title="LinkedIn Outreach Console" 
        subtitle="Manage campaigns, monitor outgoing message approvals, configure credentials, and chat with prospects in one place."
      />

      {/* Glassmorphic Navigation Tabs */}
      <div className="mb-6 flex space-x-1 rounded-xl bg-slate-100 p-1 dark:bg-navy-950 max-w-md shadow-inner">
        <button
          onClick={() => setCurrentTab('campaigns')}
          className={`flex items-center gap-2 w-full rounded-lg py-2.5 text-xs font-bold leading-5 transition-all text-center justify-center ${
            currentTab === 'campaigns'
              ? 'bg-white text-brand-600 shadow dark:bg-navy-900 dark:text-white'
              : 'text-slate-600 hover:bg-white/50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-navy-900/50'
          }`}
        >
          <Layers size={15} /> Campaigns
        </button>
        <button
          onClick={() => setCurrentTab('inbox')}
          className={`flex items-center gap-2 w-full rounded-lg py-2.5 text-xs font-bold leading-5 transition-all text-center justify-center ${
            currentTab === 'inbox'
              ? 'bg-white text-brand-600 shadow dark:bg-navy-900 dark:text-white'
              : 'text-slate-600 hover:bg-white/50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-navy-900/50'
          }`}
        >
          <Inbox size={15} /> Inbox
        </button>
        <button
          onClick={() => setCurrentTab('accounts')}
          className={`flex items-center gap-2 w-full rounded-lg py-2.5 text-xs font-bold leading-5 transition-all text-center justify-center ${
            currentTab === 'accounts'
              ? 'bg-white text-brand-600 shadow dark:bg-navy-900 dark:text-white'
              : 'text-slate-600 hover:bg-white/50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-navy-900/50'
          }`}
        >
          <Linkedin size={15} /> Accounts
        </button>
      </div>

      {/* =========================================================================
          CAMPAIGNS TAB PANEL
          ========================================================================= */}
      {currentTab === 'campaigns' && (
        <div>
          <div className="mb-4 flex justify-between items-center">
            <h2 className="text-base font-bold text-navy-900 dark:text-white flex items-center gap-2">
              <Layers size={18} className="text-brand-500" /> Outreach Campaigns
            </h2>
            <button
              onClick={() => setShowNewCampaign(true)}
              className="flex items-center gap-1.5 rounded-xl bg-brand-500 px-3.5 py-2 text-xs font-bold text-white shadow-md shadow-brand-500/20 transition-all hover:bg-brand-600 hover:shadow-brand-600/30"
            >
              <Plus size={15} /> New Campaign
            </button>
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Campaigns Sidebar */}
            <div className="lg:col-span-1 space-y-4">
              <Card>
                {campaignsLoading ? (
                  <div className="flex justify-center py-8">
                    <RefreshCw size={24} className="animate-spin text-slate-400" />
                  </div>
                ) : campaigns.length === 0 ? (
                  <p className="text-center py-6 text-xs text-slate-500 dark:text-slate-400">No campaigns created yet.</p>
                ) : (
                  <div className="divide-y divide-slate-100 dark:divide-navy-800 space-y-1">
                    {campaigns.map((c) => (
                      <div
                        key={c.id}
                        onClick={() => loadCampaignData(c)}
                        className={`flex items-center justify-between py-2.5 cursor-pointer group transition-all rounded-lg px-2 text-xs ${
                          selectedCampaign?.id === c.id
                            ? 'bg-brand-50 dark:bg-navy-800/50 border-l-4 border-brand-500 font-bold'
                            : 'hover:bg-slate-50 dark:hover:bg-navy-800/20'
                        }`}
                      >
                        <div className="min-w-0">
                          <p className="text-navy-900 dark:text-white truncate">{c.name}</p>
                          <p className="text-[10px] text-slate-400 dark:text-slate-500 capitalize">{c.mode} mode</p>
                        </div>
                        <div className="flex items-center gap-1">
                          <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold ${
                            c.status === 'running' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'
                          }`}>
                            {c.status.toUpperCase()}
                          </span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteCampaign(c.id);
                            }}
                            className="opacity-0 group-hover:opacity-100 text-rose-500 hover:text-rose-600 p-1 transition-all"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </div>

            {/* Campaign Details Workspace */}
            <div className="lg:col-span-2 space-y-6">
              {selectedCampaign ? (
                <Card>
                  {/* Summary & Controls */}
                  <div className="border-b border-slate-100 pb-4 dark:border-navy-800 flex justify-between items-start">
                    <div>
                      <h3 className="text-base font-bold text-navy-900 dark:text-white">{selectedCampaign.name}</h3>
                      <div className="mt-1 flex items-center gap-3 text-xs text-slate-500">
                        <span className="capitalize">Mode: {selectedCampaign.mode}</span>
                        <span>•</span>
                        <span>Role Filter: {selectedCampaign.role_filter || 'None'}</span>
                        <span>•</span>
                        <span>Approval: {selectedCampaign.require_approval ? 'Required' : 'Disabled'}</span>
                      </div>
                    </div>
                  </div>

                  {/* CSV Target Uploader */}
                  <form onSubmit={handleImportTargets} className="my-4 p-4 rounded-xl bg-slate-50 dark:bg-navy-950/40 border border-slate-100 dark:border-navy-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="flex items-center gap-2 text-xs">
                      <Upload size={16} className="text-brand-500 shrink-0" />
                      <div>
                        <p className="font-bold text-navy-900 dark:text-white">Import Targets via CSV</p>
                        <p className="text-[10px] text-slate-500">Upload list of contacts (headers: url, name, email)</p>
                      </div>
                    </div>
                    <div className="flex flex-col sm:flex-row sm:items-center gap-2 w-full md:w-auto">
                      <input 
                        type="file" 
                        accept=".csv" 
                        onChange={(e) => setCsvFile(e.target.files[0])}
                        className="text-xs text-slate-500 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-brand-50 file:text-brand-700 hover:file:bg-brand-100 w-full"
                      />
                      <button
                        type="submit"
                        disabled={uploadingTargets || !csvFile}
                        className="rounded-lg bg-brand-500 hover:bg-brand-600 px-3 py-1.5 text-xs font-bold text-white disabled:bg-slate-200 disabled:text-slate-400 w-full sm:w-auto shrink-0"
                      >
                        {uploadingTargets ? 'Uploading...' : 'Import'}
                      </button>
                    </div>
                  </form>

                  {/* Tab switches for Details */}
                  <div className="border-b border-slate-100 dark:border-navy-800 mb-4 flex gap-4">
                    <button
                      onClick={() => setCampaignActiveTab('targets')}
                      className={`pb-2 text-xs font-bold border-b-2 transition-all ${
                        campaignActiveTab === 'targets' ? 'border-brand-500 text-brand-600' : 'border-transparent text-slate-500 hover:text-navy-900'
                      }`}
                    >
                      Targets ({targets.length})
                    </button>
                    <button
                      onClick={() => setCampaignActiveTab('queue')}
                      className={`pb-2 text-xs font-bold border-b-2 transition-all ${
                        campaignActiveTab === 'queue' ? 'border-brand-500 text-brand-600' : 'border-transparent text-slate-500 hover:text-navy-900'
                      }`}
                    >
                      Approval Queue ({queue.length})
                    </button>
                  </div>

                  {/* Targets Sub-panel */}
                  {campaignActiveTab === 'targets' && (
                    <div className="space-y-3">
                      {targetsLoading ? (
                        <div className="flex justify-center py-6">
                          <RefreshCw className="animate-spin text-slate-300" />
                        </div>
                      ) : targets.length === 0 ? (
                        <p className="text-xs py-4 text-slate-400 text-center">No targets imported yet.</p>
                      ) : (
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs border-collapse">
                            <thead>
                              <tr className="border-b border-slate-100 dark:border-navy-800 text-slate-400">
                                <th className="py-2">Name</th>
                                <th className="py-2">Title</th>
                                <th className="py-2">Scrape Status</th>
                                <th className="py-2">Outreach Status</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-50 dark:divide-navy-900">
                              {targets.map((t) => (
                                <tr key={t.id} className="hover:bg-slate-50/50 dark:hover:bg-navy-800/10">
                                  <td className="py-2 font-semibold text-navy-900 dark:text-white">
                                    {t.person?.full_name || 'Prospect'}
                                  </td>
                                  <td className="py-2 text-slate-500 truncate max-w-[150px]">
                                    {t.person?.title || 'Unknown'} at {t.person?.organization_name || 'Unknown'}
                                  </td>
                                  <td className="py-2 capitalize">
                                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold ${
                                      t.scrape_status === 'scraped' ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-600'
                                    }`}>
                                      {t.scrape_status}
                                    </span>
                                  </td>
                                  <td className="py-2 capitalize">
                                    <span className="text-[10px] text-slate-600">{t.connection_status.replace('_', ' ')}</span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Queue Sub-panel */}
                  {campaignActiveTab === 'queue' && (
                    <div className="space-y-4">
                      {queueLoading ? (
                        <div className="flex justify-center py-6">
                          <RefreshCw className="animate-spin text-slate-300" />
                        </div>
                      ) : queue.length === 0 ? (
                        <p className="text-xs py-4 text-slate-400 text-center">No messages in queue requiring review.</p>
                      ) : (
                        <div className="space-y-3">
                          {queue.map((msg) => (
                            <div key={msg.id} className="p-4 rounded-xl border border-slate-100 bg-slate-50/50 dark:border-navy-800 dark:bg-navy-950/20 text-xs">
                              <div className="flex justify-between items-start mb-2">
                                <div>
                                  <p className="font-bold text-navy-900 dark:text-white">
                                    To: {msg.target?.person?.full_name}
                                  </p>
                                  <p className="text-[10px] text-slate-500">
                                    {msg.target?.person?.title} at {msg.target?.person?.organization_name}
                                  </p>
                                </div>
                                <span className="bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase">
                                  {msg.status.replace('_', ' ')}
                                </span>
                              </div>

                              {editingMessageId === msg.id ? (
                                <textarea
                                  className="w-full border rounded-lg p-2 text-xs bg-white dark:bg-navy-900 dark:text-white mb-2"
                                  rows={3}
                                  value={editingContent}
                                  onChange={(e) => setEditingContent(e.target.value)}
                                />
                              ) : (
                                <p className="text-slate-700 dark:text-slate-300 italic whitespace-pre-wrap mb-3 border-l-2 border-brand-500 pl-2">
                                  {msg.content}
                                </p>
                              )}

                              <div className="flex gap-2 justify-end">
                                {editingMessageId === msg.id ? (
                                  <>
                                    <button
                                      onClick={() => handleReviewMessage(msg.id, 'approve')}
                                      className="rounded-lg bg-emerald-500 text-white px-2.5 py-1 text-[11px] font-bold"
                                    >
                                      Save & Approve
                                    </button>
                                    <button
                                      onClick={() => setEditingMessageId(null)}
                                      className="rounded-lg bg-slate-100 text-slate-600 px-2.5 py-1 text-[11px]"
                                    >
                                      Cancel
                                    </button>
                                  </>
                                ) : (
                                  <>
                                    <button
                                      onClick={() => handleReviewMessage(msg.id, 'approve', msg.content)}
                                      className="rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white px-2.5 py-1 text-[11px] font-bold"
                                    >
                                      Approve
                                    </button>
                                    <button
                                      onClick={() => {
                                        setEditingMessageId(msg.id);
                                        setEditingContent(msg.content);
                                      }}
                                      className="rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 dark:bg-navy-800 dark:text-slate-300 px-2.5 py-1 text-[11px]"
                                    >
                                      Edit
                                    </button>
                                    <button
                                      onClick={() => handleReviewMessage(msg.id, 'reject')}
                                      className="rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-600 px-2.5 py-1 text-[11px]"
                                    >
                                      Reject
                                    </button>
                                  </>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </Card>
              ) : (
                <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 dark:border-navy-800 p-8 text-center bg-white dark:bg-navy-900 h-[300px]">
                  <Layers size={36} className="text-slate-300 dark:text-slate-700 mb-2 animate-pulse" />
                  <h3 className="text-sm font-bold text-navy-900 dark:text-white">Select a Campaign</h3>
                  <p className="mt-1 text-xs text-slate-500 max-w-xs">
                    Choose an outreach campaign from the list on the left to start importing targets, managing sequences, or reviewing drafts.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          INBOX TAB PANEL
          ========================================================================= */}
      {currentTab === 'inbox' && (
        <div>
          <div className="mb-4 flex justify-between items-center">
            <h2 className="text-base font-bold text-navy-900 dark:text-white flex items-center gap-2">
              <Inbox size={18} className="text-brand-500" /> Conversations Inbox
            </h2>
            <button
              onClick={fetchInbox}
              className="flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 dark:border-navy-800 dark:bg-navy-950 dark:text-slate-400"
            >
              <RefreshCw size={12} className={inboxLoading ? 'animate-spin' : ''} /> Refresh
            </button>
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Conversations List */}
            <div className="lg:col-span-1 space-y-4">
              <Card className="h-[250px] lg:h-[550px] flex flex-col">
                {inboxLoading ? (
                  <div className="flex flex-1 items-center justify-center">
                    <RefreshCw size={24} className="animate-spin text-slate-400" />
                  </div>
                ) : inboxItems.length === 0 ? (
                  <div className="flex flex-1 flex-col items-center justify-center text-slate-400 dark:text-slate-600 py-12">
                    <MessageSquare size={32} className="mb-2" />
                    <p className="text-xs">Your inbox is empty.</p>
                  </div>
                ) : (
                  <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                    {inboxItems.map((item) => (
                      <div
                        key={item.id}
                        onClick={() => setSelectedConversation(item)}
                        className={`p-3 rounded-xl cursor-pointer border transition-all text-xs ${
                          selectedConversation?.id === item.id
                            ? 'bg-brand-50/50 border-brand-200 dark:bg-navy-800/40 dark:border-navy-700 font-semibold'
                            : 'border-transparent hover:bg-slate-50 dark:hover:bg-navy-800/10'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-bold text-navy-900 dark:text-white truncate">
                            {item.target?.person?.full_name || 'Prospect'}
                          </span>
                          {getIntentBadge(item.classification?.intent)}
                        </div>
                        <div className="mt-1 text-[10px] text-slate-500 truncate">
                          {item.target?.person?.title || 'Unknown'} at {item.target?.person?.organization_name || 'Unknown'}
                        </div>
                        <p className="mt-2 text-slate-600 dark:text-slate-400 line-clamp-2 italic">
                          "{item.content}"
                        </p>
                        <div className="mt-2 text-[10px] text-slate-400">
                          {new Date(item.created_at).toLocaleDateString()}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </div>

            {/* Conversation Details & Replies */}
            <div className="lg:col-span-2">
              {selectedConversation ? (
                <Card className="h-[550px] flex flex-col">
                  <div className="border-b border-slate-100 pb-3 dark:border-navy-800 flex flex-col sm:flex-row justify-between gap-3 sm:items-start">
                    <div>
                      <h3 className="font-bold text-sm text-navy-900 dark:text-white flex items-center gap-2">
                        {selectedConversation.target?.person?.full_name}
                        {selectedConversation.target?.person?.linkedin_url && (
                          <a
                            href={selectedConversation.target.person.linkedin_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-[10px] text-brand-500 hover:underline"
                          >
                            Profile
                          </a>
                        )}
                      </h3>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        {selectedConversation.target?.person?.title} at {selectedConversation.target?.person?.organization_name}
                      </p>
                    </div>
                    {selectedConversation.classification && (
                      <div className="text-right">
                        <div className="text-[9px] text-slate-400 uppercase tracking-wider font-semibold">Classification</div>
                        <div className="mt-0.5 flex items-center gap-1.5 justify-end">
                          {getIntentBadge(selectedConversation.classification.intent)}
                          <span className="text-[10px] font-bold text-slate-500">
                            {Math.round(selectedConversation.classification.confidence * 100)}%
                          </span>
                        </div>
                      </div>
                    )}
                  </div>

                  {selectedConversation.classification?.suggested_next_action && (
                    <div className="mt-2 rounded-lg bg-brand-50/40 p-2.5 text-xs border border-brand-100 dark:bg-navy-800/10 dark:border-navy-800 flex items-start gap-2">
                      <Smile size={14} className="text-brand-500 shrink-0 mt-0.5" />
                      <p className="text-slate-600 dark:text-slate-300">
                        <span className="font-bold text-brand-600">Action: </span>
                        {selectedConversation.classification.suggested_next_action}
                      </p>
                    </div>
                  )}

                  {/* Chat feed */}
                  <div className="flex-1 overflow-y-auto py-4 space-y-4">
                    <div className="flex justify-end">
                      <div className="max-w-[75%] rounded-2xl rounded-tr-none bg-brand-500 p-2.5 text-xs text-white shadow-sm">
                        <p className="leading-relaxed">
                          Hello! I noticed your work as {selectedConversation.target?.person?.title || 'Professional'} and wanted to connect.
                        </p>
                      </div>
                    </div>

                    <div className="flex justify-start">
                      <div className="max-w-[75%] rounded-2xl rounded-tl-none bg-slate-50 border border-slate-100 p-2.5 text-xs text-slate-800 dark:bg-navy-950 dark:border-navy-800 dark:text-slate-300 shadow-sm">
                        <p className="whitespace-pre-line leading-relaxed">
                          {selectedConversation.content}
                        </p>
                        <div className="mt-1 text-right text-[9px] text-slate-400">
                          {new Date(selectedConversation.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Reply text entry */}
                  <form onSubmit={handleSendReply} className="border-t border-slate-100 pt-3 dark:border-navy-800 flex gap-2">
                    <textarea
                      placeholder="Type your manual reply here (queued and scheduled for dispatch)..."
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                      rows={2}
                      required
                      className="flex-1 rounded-xl border border-slate-200 p-2 text-xs focus:border-brand-500 focus:outline-none dark:border-navy-800 dark:bg-navy-950 dark:text-white"
                    />
                    <button
                      type="submit"
                      disabled={sendingReply || !replyText.trim()}
                      className="flex items-center justify-center rounded-xl bg-brand-500 px-4 text-white hover:bg-brand-600 disabled:bg-slate-200 disabled:text-slate-400 shrink-0"
                    >
                      {sendingReply ? <RefreshCw size={14} className="animate-spin" /> : <Send size={14} />}
                    </button>
                  </form>
                </Card>
              ) : (
                <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 dark:border-navy-800 p-8 text-center bg-white dark:bg-navy-900 h-[300px]">
                  <MessageSquare size={36} className="text-slate-300 dark:text-slate-700 mb-2 animate-bounce" />
                  <h3 className="text-sm font-bold text-navy-900 dark:text-white">Select a Conversation</h3>
                  <p className="mt-1 text-xs text-slate-500 max-w-xs">
                    Choose a reply from the left panel to review class match confidence, read conversations history, and compose your manual responses.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          ACCOUNTS TAB PANEL
          ========================================================================= */}
      {currentTab === 'accounts' && (
        <div>
          <div className="mb-4 flex justify-between items-center">
            <h2 className="text-base font-bold text-navy-900 dark:text-white flex items-center gap-2">
              <Globe size={18} className="text-brand-500" /> LinkedIn Outreach Accounts
            </h2>
            <button
              onClick={() => setIsAccountModalOpen(true)}
              className="flex items-center gap-1.5 rounded-xl bg-brand-500 px-3.5 py-2 text-xs font-bold text-white shadow-md shadow-brand-500/20 transition-all hover:bg-brand-600 hover:shadow-brand-600/30"
            >
              <Plus size={15} /> Connect Account
            </button>
          </div>

          {accountsError && (
            <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-3.5 dark:border-rose-900/40 dark:bg-rose-950/20 text-rose-700 dark:text-rose-400 text-xs">
              <p className="font-bold flex items-center gap-1"><AlertCircle size={15} /> Error loading accounts</p>
              <p className="mt-0.5">{accountsError}</p>
            </div>
          )}

          {/* Accounts Overview Row */}
          <div className="mb-6 grid gap-4 grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl border border-slate-100 bg-white p-4 shadow-soft dark:border-navy-800 dark:bg-navy-900 text-xs">
              <div className="flex items-center justify-between text-slate-400 font-semibold uppercase tracking-wider">
                <span>Total Accounts</span>
                <Globe size={16} className="text-brand-500" />
              </div>
              <p className="mt-1 text-xl font-bold text-navy-900 dark:text-white">{accounts.length}</p>
            </div>

            <div className="rounded-xl border border-slate-100 bg-white p-4 shadow-soft dark:border-navy-800 dark:bg-navy-900 text-xs">
              <div className="flex items-center justify-between text-slate-400 font-semibold uppercase tracking-wider">
                <span>Active Sessions</span>
                <CheckCircle2 size={16} className="text-emerald-500" />
              </div>
              <p className="mt-1 text-xl font-bold text-navy-900 dark:text-white">
                {accounts.filter(a => ['active', 'warming_up'].includes(a.status)).length}
              </p>
            </div>

            <div className="rounded-xl border border-slate-100 bg-white p-4 shadow-soft dark:border-navy-800 dark:bg-navy-900 text-xs">
              <div className="flex items-center justify-between text-slate-400 font-semibold uppercase tracking-wider">
                <span>Alerts</span>
                <AlertCircle size={16} className="text-amber-500" />
              </div>
              <p className="mt-1 text-xl font-bold text-navy-900 dark:text-white">
                {accounts.filter(a => ['expired', 'flagged', 'banned'].includes(a.status)).length}
              </p>
            </div>

            <div className="rounded-xl border border-slate-100 bg-white p-4 shadow-soft dark:border-navy-800 dark:bg-navy-900 text-xs">
              <div className="flex items-center justify-between text-slate-400 font-semibold uppercase tracking-wider">
                <span>Warming Up</span>
                <Activity size={16} className="text-blue-500" />
              </div>
              <p className="mt-1 text-xl font-bold text-navy-900 dark:text-white">
                {accounts.filter(a => a.status === 'warming_up').length}
              </p>
            </div>
          </div>

          {/* Accounts Table Grid */}
          <Card>
            {accountsLoading ? (
              <div className="flex justify-center py-8">
                <RefreshCw size={24} className="animate-spin text-slate-400" />
              </div>
            ) : accounts.length === 0 ? (
              <p className="text-center py-8 text-xs text-slate-500 dark:text-slate-400">No accounts connected yet.</p>
            ) : (
              <div className="overflow-x-auto text-xs">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-100 dark:border-navy-800 text-slate-400 font-semibold">
                      <th className="py-2.5">Account Label</th>
                      <th className="py-2.5">Region</th>
                      <th className="py-2.5">Auth Method</th>
                      <th className="py-2.5">Limits (Daily)</th>
                      <th className="py-2.5">Status</th>
                      <th className="py-2.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-50 dark:divide-navy-900">
                    {accounts.map((acc) => (
                      <tr key={acc.id} className="hover:bg-slate-50/50 dark:hover:bg-navy-800/10">
                        <td className="py-3 font-semibold text-navy-900 dark:text-white">{acc.label}</td>
                        <td className="py-3 capitalize text-slate-500">{acc.region}</td>
                        <td className="py-3 text-slate-500">{acc.auth_method === 'guided_login' ? 'Guided Login' : 'Extension Capture'}</td>
                        <td className="py-3 text-slate-500">Conn: {acc.daily_connection_cap} | Msg: {acc.daily_message_cap}</td>
                        <td className="py-3">
                          <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold capitalize ${
                            ['active', 'warming_up'].includes(acc.status) ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'
                          }`}>
                            {acc.status}
                          </span>
                        </td>
                        <td className="py-3 text-right space-x-1.5">
                          {acc.status === 'cooldown' || acc.status === 'expired' ? (
                            <button
                              onClick={() => handleResumeAccount(acc.id)}
                              className="text-emerald-600 hover:text-emerald-700 p-1 font-semibold"
                            >
                              Resume
                            </button>
                          ) : (
                            <button
                              onClick={() => handlePauseAccount(acc.id)}
                              className="text-slate-500 hover:text-slate-700 p-1 font-semibold"
                            >
                              Pause
                            </button>
                          )}
                          <button
                            onClick={() => handleDeleteAccount(acc.id)}
                            className="text-rose-600 hover:text-rose-700 p-1"
                          >
                            Disconnect
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* =========================================================================
          NEW CAMPAIGN CREATION MODAL
          ========================================================================= */}
      {showNewCampaign && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-navy-900 border border-slate-100 dark:border-navy-800 text-xs">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-navy-800">
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">Create LinkedIn Campaign</h3>
              <button onClick={() => setShowNewCampaign(false)} className="text-slate-400 hover:text-slate-600 dark:hover:text-white">
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleCreateCampaign} className="mt-4 space-y-3">
              <div>
                <label className="block font-bold text-navy-900 dark:text-white mb-1">Campaign Name</label>
                <input 
                  type="text" 
                  required
                  placeholder="e.g. Q3 Software Engineers Outreach" 
                  value={newCampaignForm.name}
                  onChange={(e) => setNewCampaignForm({...newCampaignForm, name: e.target.value})}
                  className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:border-brand-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-navy-900 dark:text-white mb-1">Outreach Mode</label>
                  <select 
                    value={newCampaignForm.mode}
                    onChange={(e) => setNewCampaignForm({...newCampaignForm, mode: e.target.value})}
                    className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                  >
                    <option value="manual">Manual (Human review)</option>
                    <option value="auto">Auto (Full Autopilot)</option>
                    <option value="hybrid">Hybrid (Note auto, follow-ups review)</option>
                  </select>
                </div>
                <div>
                  <label className="block font-bold text-navy-900 dark:text-white mb-1">Target Role (Filter)</label>
                  <input 
                    type="text" 
                    placeholder="e.g. CTO, VP of Eng"
                    value={newCampaignForm.role_filter}
                    onChange={(e) => setNewCampaignForm({...newCampaignForm, role_filter: e.target.value})}
                    className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block font-bold text-navy-900 dark:text-white mb-1">Connection Note Prompt (Strict 300 Chars)</label>
                <textarea 
                  rows={2}
                  value={newCampaignForm.connection_note_prompt}
                  onChange={(e) => setNewCampaignForm({...newCampaignForm, connection_note_prompt: e.target.value})}
                  className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-bold text-navy-900 dark:text-white mb-1">Follow-up Message Prompt</label>
                <textarea 
                  rows={2}
                  value={newCampaignForm.followup_prompt}
                  onChange={(e) => setNewCampaignForm({...newCampaignForm, followup_prompt: e.target.value})}
                  className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                />
              </div>

              <div className="flex justify-between items-center pt-2">
                <div className="flex items-center gap-2">
                  <input 
                    type="checkbox" 
                    id="require_approval"
                    checked={newCampaignForm.require_approval}
                    onChange={(e) => setNewCampaignForm({...newCampaignForm, require_approval: e.target.checked})}
                    className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  />
                  <label htmlFor="require_approval" className="font-semibold text-slate-700 dark:text-slate-300">
                    Require approval before sending notes
                  </label>
                </div>
                <button
                  type="submit"
                  className="rounded-xl bg-brand-500 hover:bg-brand-600 px-4 py-2 text-white font-bold"
                >
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =========================================================================
          GUIDED LOGIN CONNECTION MODAL (ACCOUNTS TAB)
          ========================================================================= */}
      {isAccountModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-2xl dark:bg-navy-900 border border-slate-100 dark:border-navy-800 text-xs">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-navy-800">
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">Guided LinkedIn Connection</h3>
              <button onClick={closeConnectModal} className="text-slate-400 hover:text-slate-600 dark:hover:text-white">
                <X size={16} />
              </button>
            </div>

            {connectStep === 1 ? (
              <div className="mt-4 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block font-bold text-navy-900 dark:text-white mb-1">Account Label / Identifier</label>
                    <input 
                      type="text" 
                      required
                      placeholder="e.g. Pradeep's Main Profile" 
                      value={connectLabel}
                      onChange={(e) => setConnectLabel(e.target.value)}
                      className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-bold text-navy-900 dark:text-white mb-1">Target Account Region</label>
                    <select 
                      value={connectRegion}
                      onChange={(e) => setConnectRegion(e.target.value)}
                      className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                    >
                      <option value="usa">United States (USA)</option>
                      <option value="asia">Asia Pacific (APAC)</option>
                      <option value="eu">Europe (EU)</option>
                      <option value="mea">Middle East / Africa (MEA)</option>
                      <option value="other">Global / Other</option>
                    </select>
                  </div>
                </div>

                <div className="rounded-xl bg-slate-50 border p-4 dark:bg-navy-950/20 dark:border-navy-800">
                  <h4 className="font-bold text-navy-900 dark:text-white flex items-center gap-1.5 mb-1">
                    <Shield size={15} className="text-brand-500" /> Security & Cookie Guided Login
                  </h4>
                  <p className="text-[11px] text-slate-500 leading-relaxed">
                    We will spin up a secure, sandboxed instance of Playwright Chrome routed through a dedicated proxy matching your selected region.
                    You will be presented with a live browser screen stream. Simply enter your credentials on the remote page, solve any Captchas, and once signed in, we will capture the session cookie and secure it.
                  </p>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    onClick={startGuidedLogin}
                    disabled={!connectLabel.trim()}
                    className="rounded-xl bg-brand-500 hover:bg-brand-600 px-4 py-2 text-white font-bold disabled:bg-slate-200 disabled:text-slate-400"
                  >
                    Start Guided Login Session
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-4 space-y-4">
                {/* Live Stream Panel */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  {/* Left browser screenshot feed */}
                  <div className="lg:col-span-2">
                    <div className="relative border border-slate-200 dark:border-navy-800 rounded-xl overflow-hidden bg-slate-950 w-full aspect-[1.6] max-h-[380px] flex items-center justify-center">
                      {screenImage ? (
                        <img 
                          ref={imageRef}
                          src={screenImage} 
                          alt="Remote Browser Feed" 
                          onClick={handleImageClick}
                          onKeyDown={handleKeyDown}
                          tabIndex={0}
                          className="w-full h-full object-contain cursor-crosshair focus:outline-none"
                        />
                      ) : (
                        <div className="text-center text-slate-500 flex flex-col items-center">
                          <Loader2 size={28} className="animate-spin text-brand-500 mb-2" />
                          <p>Waiting for remote display feed...</p>
                        </div>
                      )}

                      {/* Screen Control Icons Overlay */}
                      <div className="absolute top-2 right-2 flex gap-1">
                        <span className="bg-slate-900/80 backdrop-blur text-white px-2 py-1 rounded text-[9px] font-bold uppercase">
                          Live View
                        </span>
                      </div>
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1 text-center flex items-center justify-center gap-1">
                      <MousePointer size={10} /> Click on the screen to interact. Click image, then type on keyboard to send keystrokes.
                    </p>
                  </div>

                  {/* Right Control Actions & Inputs */}
                  <div className="lg:col-span-1 space-y-4 flex flex-col justify-between">
                    <div className="space-y-3">
                      <div>
                        <h4 className="font-bold text-navy-900 dark:text-white mb-1">Session Status</h4>
                        <div className="p-3 rounded-xl border border-slate-100 bg-slate-50/50 dark:border-navy-800 dark:bg-navy-950/20">
                          <p className="font-bold text-brand-500 capitalize">{wsStatus}</p>
                          <p className="mt-0.5 text-[10px] text-slate-500 leading-snug">{wsMessage}</p>
                        </div>
                      </div>

                      <div>
                        <h4 className="font-bold text-navy-900 dark:text-white mb-1">Remote Text Sender</h4>
                        <div className="flex gap-1.5">
                          <input 
                            type="text" 
                            placeholder="Type text to paste remotely..."
                            value={manualText}
                            onChange={(e) => setManualText(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && sendManualText()}
                            className="w-full border rounded-lg p-2 text-xs bg-white dark:border-navy-800 dark:bg-navy-950 focus:outline-none"
                          />
                          <button
                            onClick={sendManualText}
                            className="bg-brand-500 hover:bg-brand-600 text-white rounded-lg px-2"
                          >
                            Send
                          </button>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <h4 className="font-bold text-navy-900 dark:text-white text-[10px] uppercase">Special Control Keys</h4>
                      <div className="grid grid-cols-3 gap-1">
                        <button onClick={() => sendSpecialKey('Backspace')} className="bg-slate-100 hover:bg-slate-200 dark:bg-navy-800 dark:hover:bg-navy-700 py-1.5 rounded font-semibold text-[10px]">Backsp</button>
                        <button onClick={() => sendSpecialKey('Enter')} className="bg-slate-100 hover:bg-slate-200 dark:bg-navy-800 dark:hover:bg-navy-700 py-1.5 rounded font-semibold text-[10px]">Enter</button>
                        <button onClick={() => sendSpecialKey('Tab')} className="bg-slate-100 hover:bg-slate-200 dark:bg-navy-800 dark:hover:bg-navy-700 py-1.5 rounded font-semibold text-[10px]">Tab</button>
                      </div>
                      <button 
                        onClick={closeConnectModal} 
                        className="w-full py-2.5 rounded-xl border border-rose-200 text-rose-600 bg-rose-50/50 hover:bg-rose-100/50 font-bold transition-all text-center mt-2 block"
                      >
                        Cancel guided session
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
