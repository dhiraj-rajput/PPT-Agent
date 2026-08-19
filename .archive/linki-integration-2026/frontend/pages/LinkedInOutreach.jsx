import { useState, useEffect, useRef } from 'react';
import { 
  Plus, X, Trash2, Upload, Search, Check, AlertCircle, RefreshCw, Layers, 
  User, Users, ClipboardList, MessageSquare, ChevronRight, Edit2, Play, 
  Pause, Globe, Shield, Activity, CheckCircle2, Loader2, Keyboard, MousePointer,
  Send, Inbox, HelpCircle, Smile, Linkedin, Circle, ExternalLink
} from 'lucide-react';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { api, BASE_URL } from '../lib/api.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';

export default function LinkedInOutreach() {
  const { createAlert } = useNotifications();
  const notify = (title, message) => createAlert(title, message).catch(() => {});

  const [currentTab, setCurrentTab] = useState('accounts'); // 'accounts' | 'inbox' | 'campaigns'

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
    require_approval: true,
    linkedin_account_id: ''
  });
  const [newCampaignImportMethod, setNewCampaignImportMethod] = useState('none'); // 'none' | 'csv' | 'manual'
  const [newCampaignCsvFile, setNewCampaignCsvFile] = useState(null);
  const [newCampaignManualRows, setNewCampaignManualRows] = useState([
    { name: '', linkedin_url: '', title: '', company: '' }
  ]);
  const [csvFile, setCsvFile] = useState(null);
  const [detailImportMethod, setDetailImportMethod] = useState('csv'); // 'csv' | 'manual'
  const [detailManualTarget, setDetailManualTarget] = useState({ name: '', linkedin_url: '', title: '', company: '' });
  const [targetsSearchQuery, setTargetsSearchQuery] = useState('');
  const [uploadingTargets, setUploadingTargets] = useState(false);
  const [isEditingCampaign, setIsEditingCampaign] = useState(false);
  const [editCampaignForm, setEditCampaignForm] = useState({
    name: '',
    mode: 'manual',
    role_filter: '',
    message_generation_mode: 'llm',
    connection_note_prompt: '',
    followup_prompt: '',
    require_approval: true,
    linkedin_account_id: '',
    status: 'draft'
  });
  const [editingMessageId, setEditingMessageId] = useState(null);
  const [editingContent, setEditingContent] = useState('');
  const [reviewTargetMessage, setReviewTargetMessage] = useState(null);
  const [messageHistoryTarget, setMessageHistoryTarget] = useState(null);
  const [messageHistoryList, setMessageHistoryList] = useState([]);
  const [messageHistoryLoading, setMessageHistoryLoading] = useState(false);

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

  // States for drop-down accounts and manual scheduling
  const [selectedInboxAccountId, setSelectedInboxAccountId] = useState('');
  const [showLinkedInMockLogin, setShowLinkedInMockLogin] = useState(false);
  const [mockEmail, setMockEmail] = useState('');
  const [mockPassword, setMockPassword] = useState('');
  const [msgDelays, setMsgDelays] = useState({}); // { [messageId]: 'immediate' | '5m' | '1h' | 'custom' }
  const [msgCustomTimes, setMsgCustomTimes] = useState({}); // { [messageId]: 'YYYY-MM-DDTHH:MM' }

  // =========================================================================
  // INITIAL LOADERS & FETCHERS
  // =========================================================================
  useEffect(() => {
    // Proactively fetch all data on mount to share lists across tabs
    fetchAccounts();
    fetchCampaigns();
    fetchInbox();
  }, []);

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

  // Silently re-fetches targets/queue for the currently selected campaign
  // without flipping the loading spinners, so the status bar can poll live.
  const refreshCampaignDataQuietly = async (campaign) => {
    if (!campaign) return;
    try {
      const res = await api.getLinkedInTargets(campaign.id);
      setTargets(res.targets || []);
    } catch (err) {
      // Silent - this is a background poll, don't spam notifications
    }
    try {
      const res = await api.getLinkedInQueue(campaign.id);
      setQueue(res.queue || []);
    } catch (err) {
      // Silent
    }
  };

  // Poll the selected campaign's targets/queue every few seconds while the
  // Campaigns tab is open, so the scrape/outreach status bar stays live.
  useEffect(() => {
    if (currentTab !== 'campaigns' || !selectedCampaign) return;
    const interval = setInterval(() => {
      refreshCampaignDataQuietly(selectedCampaign);
    }, 6000);
    return () => clearInterval(interval);
  }, [currentTab, selectedCampaign?.id]);

  // Computes scrape/outreach progress counts for the status bar from the
  // already-loaded targets list.
  const getCampaignStats = (list) => {
    const total = list.length;
    const scraped = list.filter(t => t.scrape_status === 'scraped').length;
    const scrapeFailed = list.filter(t => t.scrape_status === 'failed').length;
    const sent = list.filter(t => t.message_log && t.message_log.status === 'sent').length;
    const needsReview = list.filter(t => t.message_log && t.message_log.status === 'needs_review').length;
    const queued = list.filter(t => t.message_log && t.message_log.status === 'approved').length;
    const failedSend = list.filter(t => t.message_log && t.message_log.status === 'failed').length;
    const accepted = list.filter(t => t.connection_status === 'accepted').length;
    return {
      total, scraped, scrapeFailed, sent, needsReview, queued, failedSend, accepted,
      scrapePct: total ? Math.round((scraped / total) * 100) : 0,
      sentPct: total ? Math.round((sent / total) * 100) : 0,
    };
  };

  const handleToggleCampaignStatus = async () => {
    if (!selectedCampaign) return;
    const nextStatus = selectedCampaign.status === 'running' ? 'paused' : 'running';
    try {
      await api.updateLinkedInCampaign(selectedCampaign.id, { status: nextStatus });
      setSelectedCampaign({ ...selectedCampaign, status: nextStatus });
      notify('Success', nextStatus === 'running' ? 'Campaign started — scraping and outreach will begin shortly.' : 'Campaign paused.');
      fetchCampaigns();
    } catch (err) {
      notify('Error', `Failed to update campaign status: ${err.message}`);
    }
  };

  const openTargetMessages = async (target) => {
    setMessageHistoryTarget(target);
    setMessageHistoryList([]);
    setMessageHistoryLoading(true);
    try {
      const res = await api.getLinkedInTargetMessages(selectedCampaign.id, target.id);
      setMessageHistoryList(res.messages || []);
    } catch (err) {
      notify('Error', `Failed to load message history: ${err.message}`);
    } finally {
      setMessageHistoryLoading(false);
    }
  };

  const handleCreateCampaign = async (e) => {
    e.preventDefault();
    if (!newCampaignForm.name.trim()) return;
    
    try {
      const res = await api.createLinkedInCampaign(newCampaignForm);
      let importMsg = '';

      if (newCampaignImportMethod === 'csv' && newCampaignCsvFile) {
        await api.importLinkedInTargets(res.id, { file: newCampaignCsvFile });
        importMsg = ' and target CSV imported';
      } else if (newCampaignImportMethod === 'manual') {
        const validRows = newCampaignManualRows.filter(r => r.name.trim() && r.linkedin_url.trim());
        if (validRows.length > 0) {
          const csvHeaders = "name,linkedin_url,title,company";
          const csvRows = validRows.map(r => {
            const escapedName = r.name.replace(/"/g, '""');
            const escapedUrl = r.linkedin_url.replace(/"/g, '""');
            const escapedTitle = (r.title || '').replace(/"/g, '""');
            const escapedCompany = (r.company || '').replace(/"/g, '""');
            return `"${escapedName}","${escapedUrl}","${escapedTitle}","${escapedCompany}"`;
          });
          const csvText = [csvHeaders, ...csvRows].join("\n");
          const blob = new Blob([csvText], { type: 'text/csv' });
          const file = new File([blob], "manual_upload.csv", { type: 'text/csv' });
          await api.importLinkedInTargets(res.id, { file });
          importMsg = ` and ${validRows.length} targets imported`;
        }
      }

      notify('Success', `LinkedIn campaign created successfully${importMsg}.`);
      setShowNewCampaign(false);
      setNewCampaignForm({
        name: '',
        mode: 'manual',
        role_filter: '',
        message_generation_mode: 'llm',
        connection_note_prompt: 'Keep it friendly and professional, referencing their headline.',
        followup_prompt: 'Thank them for connecting and ask if they are open to sharing outreach ideas.',
        require_approval: true,
        linkedin_account_id: ''
      });
      setNewCampaignImportMethod('none');
      setNewCampaignCsvFile(null);
      setNewCampaignManualRows([{ name: '', linkedin_url: '', title: '', company: '' }]);
      fetchCampaigns();
    } catch (err) {
      notify('Error', `Failed to create campaign: ${err.message}`);
    }
  };

  const handleUpdateCampaign = async (e) => {
    e.preventDefault();
    if (!selectedCampaign) return;
    try {
      const payload = {
        name: editCampaignForm.name,
        mode: editCampaignForm.mode,
        role_filter: editCampaignForm.role_filter,
        message_generation_mode: editCampaignForm.message_generation_mode,
        connection_note_prompt: editCampaignForm.connection_note_prompt,
        followup_prompt: editCampaignForm.followup_prompt,
        require_approval: editCampaignForm.require_approval,
        linkedin_account_id: editCampaignForm.linkedin_account_id ? Number(editCampaignForm.linkedin_account_id) : null,
        status: editCampaignForm.status
      };
      await api.updateLinkedInCampaign(selectedCampaign.id, payload);
      notify('Success', 'Campaign updated successfully.');
      setIsEditingCampaign(false);
      
      // Reload current selected campaign details
      const updatedCamp = { ...selectedCampaign, ...payload };
      setSelectedCampaign(updatedCamp);
      fetchCampaigns();
    } catch (err) {
      notify('Error', `Failed to update campaign: ${err.message}`);
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
    if (!selectedCampaign) return;
    
    setUploadingTargets(true);
    try {
      let fileToUpload = null;
      if (detailImportMethod === 'csv') {
        if (!csvFile) {
          notify('Warning', 'Please select a CSV file.');
          setUploadingTargets(false);
          return;
        }
        fileToUpload = csvFile;
      } else {
        if (!detailManualTarget.name.trim() || !detailManualTarget.linkedin_url.trim()) {
          notify('Warning', 'Prospect Name and LinkedIn URL are required.');
          setUploadingTargets(false);
          return;
        }
        const csvHeaders = "name,linkedin_url,title,company";
        const escapedName = detailManualTarget.name.replace(/"/g, '""');
        const escapedUrl = detailManualTarget.linkedin_url.replace(/"/g, '""');
        const escapedTitle = (detailManualTarget.title || '').replace(/"/g, '""');
        const escapedCompany = (detailManualTarget.company || '').replace(/"/g, '""');
        const csvRow = `"${escapedName}","${escapedUrl}","${escapedTitle}","${escapedCompany}"`;
        const blob = new Blob([[csvHeaders, csvRow].join("\n")], { type: 'text/csv' });
        fileToUpload = new File([blob], "manual_detail.csv", { type: 'text/csv' });
      }

      const res = await api.importLinkedInTargets(selectedCampaign.id, { file: fileToUpload });
      notify('Import Complete', res.message || `Imported targets successfully.`);
      setCsvFile(null);
      setDetailManualTarget({ name: '', linkedin_url: '', title: '', company: '' });
      loadCampaignData(selectedCampaign);
    } catch (err) {
      notify('Error', `Failed to import targets: ${err.message}`);
    } finally {
      setUploadingTargets(false);
    }
  };

  const handleDeleteTarget = async (targetId) => {
    if (!confirm('Are you sure you want to remove this prospect from the campaign?')) return;
    try {
      await api.deleteLinkedInTarget(selectedCampaign.id, targetId);
      notify('Success', 'Target removed from campaign.');
      loadCampaignData(selectedCampaign);
    } catch (err) {
      notify('Error', `Failed to remove target: ${err.message}`);
    }
  };

  const handleReviewMessage = async (messageId, action, finalContent, scheduledSendAt) => {
    try {
      await api.reviewLinkedInMessage(messageId, {
        content: finalContent || editingContent,
        action: action,
        scheduled_send_at: scheduledSendAt || null
      });
      notify('Success', `Message ${action}ed.`);
      setEditingMessageId(null);
      loadCampaignData(selectedCampaign);
    } catch (err) {
      notify('Error', `Failed to review message: ${err.message}`);
    }
  };

  const handleResendMessage = async (messageId, target) => {
    try {
      const res = await api.resendLinkedInMessage(messageId);
      if (res.warning) {
        notify('Resend Queued — Action Needed', res.warning);
      } else {
        notify('Success', 'Message requeued — it will be retried on the next send cycle.');
      }
      loadCampaignData(selectedCampaign);
      // If the message-history modal is open for this target, refresh it too
      if (messageHistoryTarget && target && messageHistoryTarget.id === target.id) {
        openTargetMessages(target);
      }
    } catch (err) {
      notify('Error', `Failed to resend message: ${err.message}`);
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

  const [liAtCookie, setLiAtCookie] = useState('');
  const [jsessionIdCookie, setJsessionIdCookie] = useState('');
  const [submittingAccount, setSubmittingAccount] = useState(false);

  const handleConnectAccount = async (e) => {
    e.preventDefault();
    if (!connectLabel.trim() || !liAtCookie.trim()) {
      alert('Please fill in the account label and the li_at cookie.');
      return;
    }

    setSubmittingAccount(true);
    try {
      await api.createLinkedInAccount({
        label: connectLabel,
        region: connectRegion,
        li_at: liAtCookie,
        jsessionid: jsessionIdCookie
      });
      notify('Success', 'LinkedIn account linked successfully!');
      closeConnectModal();
      fetchAccounts();
    } catch (err) {
      notify('Error', err.message || 'Failed to connect LinkedIn account.');
    } finally {
      setSubmittingAccount(false);
    }
  };

  const closeConnectModal = () => {
    setConnectLabel('');
    setConnectRegion('usa');
    setLiAtCookie('');
    setJsessionIdCookie('');
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
          onClick={() => setCurrentTab('accounts')}
          className={`flex items-center gap-2 w-full rounded-lg py-2.5 text-xs font-bold leading-5 transition-all text-center justify-center ${
            currentTab === 'accounts'
              ? 'bg-white text-brand-600 shadow dark:bg-navy-900 dark:text-white'
              : 'text-slate-600 hover:bg-white/50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-navy-900/50'
          }`}
        >
          <Linkedin size={15} /> Accounts
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
          onClick={() => setCurrentTab('campaigns')}
          className={`flex items-center gap-2 w-full rounded-lg py-2.5 text-xs font-bold leading-5 transition-all text-center justify-center ${
            currentTab === 'campaigns'
              ? 'bg-white text-brand-600 shadow dark:bg-navy-900 dark:text-white'
              : 'text-slate-600 hover:bg-white/50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-navy-900/50'
          }`}
        >
          <Layers size={15} /> Campaigns
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
                  <div className="border-b border-slate-100 pb-4 dark:border-navy-800 flex justify-between items-start gap-3 flex-wrap">
                    <div>
                      <h3 className="text-base font-bold text-navy-900 dark:text-white flex items-center gap-2">
                        {selectedCampaign.name}
                        <button
                          onClick={() => {
                            setEditCampaignForm({
                              name: selectedCampaign.name,
                              mode: selectedCampaign.mode,
                              role_filter: selectedCampaign.role_filter || '',
                              message_generation_mode: selectedCampaign.message_generation_mode || 'llm',
                              connection_note_prompt: selectedCampaign.connection_note_prompt || '',
                              followup_prompt: selectedCampaign.followup_prompt || '',
                              require_approval: selectedCampaign.require_approval,
                              linkedin_account_id: selectedCampaign.linkedin_account_id || '',
                              status: selectedCampaign.status || 'draft'
                            });
                            setIsEditingCampaign(true);
                          }}
                          className="text-slate-400 hover:text-brand-500 transition-colors"
                          title="Edit Campaign Settings"
                        >
                          <Edit2 size={13} />
                        </button>
                      </h3>
                      <div className="mt-1 flex items-center gap-3 text-xs text-slate-500 flex-wrap">
                        <span className="capitalize">Mode: {selectedCampaign.mode}</span>
                        <span>•</span>
                        <span>Role Filter: {selectedCampaign.role_filter || 'None'}</span>
                        <span>•</span>
                        <span>Approval: {selectedCampaign.require_approval ? 'Required' : 'Disabled'}</span>
                        <span>•</span>
                        <span className="capitalize text-brand-600 dark:text-brand-400">Status: {selectedCampaign.status}</span>
                        {selectedCampaign.linkedin_account_id && (
                          <>
                            <span>•</span>
                            <span className="font-bold text-brand-600 dark:text-brand-400">
                              Sender Profile: {accounts.find(a => a.id === selectedCampaign.linkedin_account_id)?.label || `ID #${selectedCampaign.linkedin_account_id}`}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={handleToggleCampaignStatus}
                        disabled={!selectedCampaign.linkedin_account_id}
                        title={!selectedCampaign.linkedin_account_id ? 'Assign a Sender Profile (LinkedIn account) in Edit Campaign before starting.' : ''}
                        className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                          selectedCampaign.status === 'running'
                            ? 'bg-amber-50 text-amber-700 hover:bg-amber-100 dark:bg-amber-950/40 dark:text-amber-300'
                            : 'bg-emerald-500 text-white hover:bg-emerald-600 shadow-sm shadow-emerald-500/20'
                        }`}
                      >
                        {selectedCampaign.status === 'running'
                          ? (<><Pause size={13} /> Pause Campaign</>)
                          : (<><Play size={13} /> Start Campaign</>)}
                      </button>
                    </div>
                  </div>

                  {/* Live Scrape / Outreach Status Bar */}
                  {(() => {
                    const stats = getCampaignStats(targets);
                    const senderAccount = accounts.find(a => a.id === selectedCampaign.linkedin_account_id);
                    const senderInactive = senderAccount && !['active', 'warming_up'].includes(senderAccount.status);
                    return (
                      <div className="my-4 p-4 rounded-xl bg-slate-50 dark:bg-navy-950/40 border border-slate-100 dark:border-navy-800 space-y-4 text-xs">
                        {senderInactive && (
                          <div className="flex items-start gap-2 p-3 rounded-xl bg-rose-50 border border-rose-100 dark:bg-rose-950/20 dark:border-rose-900">
                            <AlertCircle size={14} className="shrink-0 mt-0.5 text-rose-600 dark:text-rose-400" />
                            <div>
                              <p className="font-bold text-rose-700 dark:text-rose-300">
                                Sender account "{senderAccount.label}" is {senderAccount.status} — queued messages will not send.
                              </p>
                              <p className="mt-0.5 text-rose-600/80 dark:text-rose-400/80">
                                LinkedIn invalidated this account's session (this is the same issue as the earlier "Session Expired" notification). Any message that reaches "queued to send" will stay stuck until you reconnect it.{' '}
                                <button
                                  type="button"
                                  onClick={() => setCurrentTab('accounts')}
                                  className="underline font-bold"
                                >
                                  Go to Accounts tab to reconnect
                                </button>
                              </p>
                            </div>
                          </div>
                        )}
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5 font-bold text-navy-900 dark:text-white">
                            <Activity size={14} className="text-brand-500 shrink-0" />
                            <span>Live Campaign Status</span>
                          </div>
                          <span className="text-[10px] text-slate-400 flex items-center gap-1">
                            {selectedCampaign.status === 'running' && <Loader2 size={11} className="animate-spin text-emerald-500" />}
                            {stats.total} target{stats.total === 1 ? '' : 's'} total
                          </span>
                        </div>

                        {/* Scrape Status Bar */}
                        <div>
                          <div className="flex justify-between mb-1 text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                            <span>Scrape Status</span>
                            <span>{stats.scraped}/{stats.total} scraped ({stats.scrapePct}%){stats.scrapeFailed > 0 ? ` · ${stats.scrapeFailed} failed` : ''}</span>
                          </div>
                          <div className="h-2 w-full rounded-full bg-slate-200 dark:bg-navy-800 overflow-hidden">
                            <div
                              className="h-full rounded-full bg-brand-500 transition-all duration-500"
                              style={{ width: `${stats.scrapePct}%` }}
                            />
                          </div>
                        </div>

                        {/* Outreach Status Bar */}
                        <div>
                          <div className="flex justify-between mb-1 text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                            <span>Outreach Status</span>
                            <span>{stats.sent}/{stats.total} sent ({stats.sentPct}%)</span>
                          </div>
                          <div className="h-2 w-full rounded-full bg-slate-200 dark:bg-navy-800 overflow-hidden">
                            <div
                              className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                              style={{ width: `${stats.sentPct}%` }}
                            />
                          </div>
                        </div>

                        {/* Breakdown chips */}
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
                            {stats.needsReview} awaiting review
                          </span>
                          <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-sky-100 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300">
                            {stats.queued} queued to send
                          </span>
                          <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                            {stats.accepted} accepted
                          </span>
                          {stats.failedSend > 0 && (
                            <span className="px-2 py-0.5 rounded-full text-[9px] font-bold bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
                              {stats.failedSend} failed to send
                            </span>
                          )}
                        </div>

                        {selectedCampaign.status !== 'running' && stats.total > 0 && (
                          <p className="text-[10px] text-slate-400 italic">
                            Campaign is {selectedCampaign.status} — scraping and sending are paused. Click "Start Campaign" above to resume live progress.
                          </p>
                        )}
                      </div>
                    );
                  })()}

                  {/* Targets Importer block */}
                  <div className="my-4 p-4 rounded-xl bg-slate-50 dark:bg-navy-950/40 border border-slate-100 dark:border-navy-800 space-y-3 text-xs">
                    <div className="flex justify-between items-center border-b pb-2 dark:border-navy-800">
                      <div className="flex items-center gap-1.5 font-bold text-navy-900 dark:text-white">
                        <Upload size={16} className="text-brand-500 shrink-0" />
                        <span>Add Target Prospects</span>
                      </div>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => setDetailImportMethod('csv')}
                          className={`px-3 py-1 rounded-lg text-[10px] font-bold border transition-all ${
                            detailImportMethod === 'csv'
                              ? 'bg-white border-brand-200 text-brand-700 dark:bg-navy-900 shadow-sm'
                              : 'border-slate-200 text-slate-500 hover:bg-slate-100'
                          }`}
                        >
                          CSV File Upload
                        </button>
                        <button
                          type="button"
                          onClick={() => setDetailImportMethod('manual')}
                          className={`px-3 py-1 rounded-lg text-[10px] font-bold border transition-all ${
                            detailImportMethod === 'manual'
                              ? 'bg-white border-brand-200 text-brand-700 dark:bg-navy-900 shadow-sm'
                              : 'border-slate-200 text-slate-500 hover:bg-slate-100'
                          }`}
                        >
                          Add Manually
                        </button>
                      </div>
                    </div>

                    {detailImportMethod === 'csv' ? (
                      <form onSubmit={handleImportTargets} className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div>
                          <p className="font-semibold text-slate-600 dark:text-slate-400">Select Contacts CSV file</p>
                          <p className="text-[10px] text-slate-400">headers: name, linkedin_url, title, company</p>
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
                            className="rounded-lg bg-brand-500 hover:bg-brand-600 px-3.5 py-1.5 text-xs font-bold text-white disabled:bg-slate-200 w-full sm:w-auto shrink-0"
                          >
                            {uploadingTargets ? 'Uploading...' : 'Import'}
                          </button>
                        </div>
                      </form>
                    ) : (
                      <form onSubmit={handleImportTargets} className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 items-end">
                        <div>
                          <label className="block text-[10px] font-bold text-slate-500 mb-0.5">FULL NAME *</label>
                          <input
                            type="text"
                            required
                            placeholder="e.g. John Doe"
                            value={detailManualTarget.name}
                            onChange={(e) => setDetailManualTarget({...detailManualTarget, name: e.target.value})}
                            className="w-full rounded-lg border border-slate-200 p-2 text-xs bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] font-bold text-slate-500 mb-0.5">LINKEDIN URL *</label>
                          <input
                            type="text"
                            required
                            placeholder="https://linkedin.com/in/..."
                            value={detailManualTarget.linkedin_url}
                            onChange={(e) => setDetailManualTarget({...detailManualTarget, linkedin_url: e.target.value})}
                            className="w-full rounded-lg border border-slate-200 p-2 text-xs bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] font-bold text-slate-500 mb-0.5">TITLE (ROLE)</label>
                          <input
                            type="text"
                            placeholder="e.g. Senior Architect"
                            value={detailManualTarget.title}
                            onChange={(e) => setDetailManualTarget({...detailManualTarget, title: e.target.value})}
                            className="w-full rounded-lg border border-slate-200 p-2 text-xs bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                          />
                        </div>
                        <div className="flex gap-2 items-center">
                          <div className="w-full">
                            <label className="block text-[10px] font-bold text-slate-500 mb-0.5">COMPANY</label>
                            <input
                              type="text"
                              placeholder="e.g. Stripe"
                              value={detailManualTarget.company}
                              onChange={(e) => setDetailManualTarget({...detailManualTarget, company: e.target.value})}
                              className="w-full rounded-lg border border-slate-200 p-2 text-xs bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                            />
                          </div>
                          <button
                            type="submit"
                            disabled={uploadingTargets}
                            className="rounded-lg bg-brand-500 hover:bg-brand-600 px-4 py-2 text-xs font-bold text-white disabled:bg-slate-200 shrink-0 self-end"
                          >
                            Add
                          </button>
                        </div>
                      </form>
                    )}
                  </div>

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
                    <div className="space-y-3 text-xs">
                      {/* Local Targets Search Bar */}
                      <div className="flex items-center gap-2 mb-2">
                        <input
                          type="text"
                          placeholder="Search target prospects by name, title, or company..."
                          value={targetsSearchQuery}
                          onChange={(e) => setTargetsSearchQuery(e.target.value)}
                          className="w-full rounded-xl border border-slate-200 p-2 text-xs bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                        />
                      </div>

                      {targetsLoading ? (
                        <div className="flex justify-center py-6">
                          <RefreshCw className="animate-spin text-slate-300" />
                        </div>
                      ) : targets.length === 0 ? (
                        <p className="text-xs py-4 text-slate-400 text-center">No targets imported yet.</p>
                      ) : (
                        (() => {
                          const getAvatarBg = (name) => {
                            if (!name) return 'bg-slate-100 text-slate-500';
                            const sum = name.toUpperCase().split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
                            const colors = [
                              'bg-brand-50 text-brand-700 dark:bg-brand-950/40 dark:text-brand-300',
                              'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300',
                              'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300',
                              'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300',
                              'bg-purple-50 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300',
                            ];
                            return colors[sum % colors.length];
                          };

                          const filteredTargets = targets.filter(t => {
                            if (!targetsSearchQuery.trim()) return true;
                            const q = targetsSearchQuery.toLowerCase();
                            const name = (t.person?.full_name || '').toLowerCase();
                            const title = (t.person?.title || '').toLowerCase();
                            const org = (t.person?.organization_name || '').toLowerCase();
                            return name.includes(q) || title.includes(q) || org.includes(q);
                          });

                          if (filteredTargets.length === 0) {
                            return <p className="text-xs py-4 text-slate-400 text-center">No prospects matching search filter.</p>;
                          }

                          return (
                            <div className="overflow-x-auto">
                              <table className="w-full text-left text-xs border-collapse">
                                <thead>
                                  <tr className="border-b border-slate-100 dark:border-navy-800 text-slate-400">
                                    <th className="py-2">Name</th>
                                    <th className="py-2">Title</th>
                                    <th className="py-2">Scrape Status</th>
                                    <th className="py-2">Outreach Status</th>
                                    <th className="py-2 text-right">Actions</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-50 dark:divide-navy-900">
                                  {filteredTargets.map((t) => (
                                    <tr key={t.id} className="hover:bg-slate-50/50 dark:hover:bg-navy-800/10">
                                      <td className="py-2.5 font-semibold text-navy-900 dark:text-white">
                                        <div className="flex items-center gap-2">
                                          <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs shrink-0 ${getAvatarBg(t.person?.full_name)}`}>
                                            {t.person?.full_name ? t.person.full_name.charAt(0).toUpperCase() : '?'}
                                          </div>
                                          <div>
                                            <p className="font-semibold text-navy-900 dark:text-white flex items-center gap-1">
                                              {t.person?.full_name || 'Prospect'}
                                              {t.person?.linkedin_url && (
                                                <a href={t.person.linkedin_url} target="_blank" rel="noreferrer" className="text-slate-400 hover:text-brand-500 transition-colors">
                                                  <ExternalLink size={11} />
                                                </a>
                                              )}
                                            </p>
                                          </div>
                                        </div>
                                      </td>
                                      <td className="py-2.5 text-slate-500 truncate max-w-[200px]">
                                        <div className="font-medium text-slate-700 dark:text-slate-300">{t.person?.title || 'Unknown Role'}</div>
                                        {t.person?.organization_name && <div className="text-slate-400 text-[10px]">{t.person.organization_name}</div>}
                                      </td>
                                      <td className="py-2.5 capitalize">
                                        <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider ${
                                          t.scrape_status === 'scraped'
                                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
                                            : 'bg-slate-100 text-slate-600 dark:bg-navy-800 dark:text-slate-400'
                                        }`}>
                                          {t.scrape_status}
                                        </span>
                                      </td>
                                      <td className="py-2.5 capitalize">
                                        <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider ${
                                          t.connection_status === 'accepted'
                                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
                                            : t.connection_status === 'connection_sent' || t.connection_status === 'sent'
                                            ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'
                                            : 'bg-slate-100 text-slate-600 dark:bg-navy-800 dark:text-slate-400'
                                        }`}>
                                          {t.connection_status.replace('_', ' ')}
                                        </span>
                                      </td>
                                      <td className="py-2.5 text-right">
                                        <div className="flex justify-end gap-1.5 items-center">
                                          {t.message_log && t.message_log.status === 'needs_review' && (
                                            <button
                                              onClick={() => {
                                                setReviewTargetMessage({
                                                  targetId: t.id,
                                                  targetName: t.person?.full_name || 'Prospect',
                                                  targetTitle: t.person?.title || 'Prospect Title',
                                                  targetCompany: t.person?.organization_name || 'Prospect Company',
                                                  messageId: t.message_log.id,
                                                  content: t.message_log.content,
                                                  scheduledTime: ''
                                                });
                                                setEditingContent(t.message_log.content);
                                              }}
                                              className="bg-emerald-50 hover:bg-emerald-100 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 px-2 py-1 rounded text-[10px] font-bold transition-all shrink-0"
                                              title="Review draft note"
                                            >
                                              Review & Send
                                            </button>
                                          )}
                                          {t.message_log && t.message_log.status === 'failed' && (
                                            <button
                                              onClick={() => handleResendMessage(t.message_log.id, t)}
                                              className="bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 px-2 py-1 rounded text-[10px] font-bold transition-all shrink-0 flex items-center gap-1"
                                              title="Retry sending this message"
                                            >
                                              <RefreshCw size={11} /> Resend
                                            </button>
                                          )}
                                          <button
                                            onClick={() => openTargetMessages(t)}
                                            className="text-slate-400 hover:text-brand-600 p-1.5 rounded-lg hover:bg-brand-50 dark:hover:bg-navy-800/40 transition-colors"
                                            title="View message history"
                                          >
                                            <MessageSquare size={13} />
                                          </button>
                                          <button
                                            onClick={() => handleDeleteTarget(t.id)}
                                            className="text-rose-600 hover:text-rose-700 p-1.5 rounded-lg hover:bg-rose-50 dark:hover:bg-rose-950/20 transition-colors"
                                            title="Remove Target"
                                          >
                                            <Trash2 size={13} />
                                          </button>
                                        </div>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          );
                        })()
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

                              {/* If campaign is manual mode, show a scheduling selector */}
                              {selectedCampaign.mode === 'manual' && (
                                <div className="mt-3 p-3 rounded-xl border border-brand-100 bg-brand-50/20 dark:border-navy-800 dark:bg-navy-950/40 mb-3 space-y-2 text-left">
                                  <p className="font-bold text-[9px] text-brand-600 dark:text-brand-400 uppercase tracking-wider">Manual Dispatch Scheduler</p>
                                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                    <div>
                                      <label className="block text-[8px] text-slate-400 font-bold mb-0.5">DISPATCH DELAY</label>
                                      <select
                                        value={msgDelays[msg.id] || 'immediate'}
                                        onChange={(e) => setMsgDelays({...msgDelays, [msg.id]: e.target.value})}
                                        className="w-full rounded-lg border border-slate-200 p-1.5 text-[11px] bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                                      >
                                        <option value="immediate">Send ASAP (Immediate)</option>
                                        <option value="5m">Wait 5 minutes</option>
                                        <option value="1h">Wait 1 hour</option>
                                        <option value="4h">Wait 4 hours</option>
                                        <option value="custom">Custom Date & Time</option>
                                      </select>
                                    </div>
                                    {msgDelays[msg.id] === 'custom' && (
                                      <div>
                                        <label className="block text-[8px] text-slate-400 font-bold mb-0.5">DATE & TIME</label>
                                        <input
                                          type="datetime-local"
                                          value={msgCustomTimes[msg.id] || ''}
                                          onChange={(e) => setMsgCustomTimes({...msgCustomTimes, [msg.id]: e.target.value})}
                                          className="w-full rounded-lg border border-slate-200 p-1 text-[11px] bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                                        />
                                      </div>
                                    )}
                                  </div>
                                </div>
                              )}

                              <div className="flex gap-2 justify-end">
                                {editingMessageId === msg.id ? (
                                  <>
                                    <button
                                      onClick={() => {
                                        let scheduledTime = null;
                                        const delay = msgDelays[msg.id] || 'immediate';
                                        if (delay === '5m') {
                                          scheduledTime = new Date(Date.now() + 5 * 60 * 1000).toISOString();
                                        } else if (delay === '1h') {
                                          scheduledTime = new Date(Date.now() + 60 * 60 * 1000).toISOString();
                                        } else if (delay === '4h') {
                                          scheduledTime = new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString();
                                        } else if (delay === 'custom' && msgCustomTimes[msg.id]) {
                                          scheduledTime = new Date(msgCustomTimes[msg.id]).toISOString();
                                        }
                                        handleReviewMessage(msg.id, 'approve', editingContent, scheduledTime);
                                      }}
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
                                      onClick={() => {
                                        let scheduledTime = null;
                                        const delay = msgDelays[msg.id] || 'immediate';
                                        if (delay === '5m') {
                                          scheduledTime = new Date(Date.now() + 5 * 60 * 1000).toISOString();
                                        } else if (delay === '1h') {
                                          scheduledTime = new Date(Date.now() + 60 * 60 * 1000).toISOString();
                                        } else if (delay === '4h') {
                                          scheduledTime = new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString();
                                        } else if (delay === 'custom' && msgCustomTimes[msg.id]) {
                                          scheduledTime = new Date(msgCustomTimes[msg.id]).toISOString();
                                        }
                                        handleReviewMessage(msg.id, 'approve', msg.content, scheduledTime);
                                      }}
                                      className="rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white px-2.5 py-1 text-[11px] font-bold"
                                    >
                                      {selectedCampaign.mode === 'manual' ? 'Schedule & Approve' : 'Approve'}
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
              <Card className="h-[250px] lg:h-[550px] flex flex-col p-3">
                {/* Account dropdown switcher */}
                <div className="mb-3 border-b pb-2.5 dark:border-navy-800">
                  <label className="block text-[9px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-1">Filter by LinkedIn Profile</label>
                  <select
                    value={selectedInboxAccountId}
                    onChange={(e) => setSelectedInboxAccountId(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 p-2 text-xs bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                  >
                    <option value="">All Connected Profiles</option>
                    {accounts.map(acc => (
                      <option key={acc.id} value={acc.id}>{acc.label} ({acc.region.toUpperCase()})</option>
                    ))}
                  </select>
                </div>

                {inboxLoading ? (
                  <div className="flex flex-1 items-center justify-center">
                    <RefreshCw size={24} className="animate-spin text-slate-400" />
                  </div>
                ) : (selectedInboxAccountId ? inboxItems.filter(item => item.account_id_used === Number(selectedInboxAccountId)) : inboxItems).length === 0 ? (
                  <div className="flex flex-1 flex-col items-center justify-center text-slate-400 dark:text-slate-600 py-12">
                    <MessageSquare size={32} className="mb-2" />
                    <p className="text-xs">No conversations found.</p>
                  </div>
                ) : (
                  <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                    {(selectedInboxAccountId ? inboxItems.filter(item => item.account_id_used === Number(selectedInboxAccountId)) : inboxItems).map((item) => (
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

              <div>
                <label className="block font-bold text-navy-900 dark:text-white mb-1">LinkedIn Profile (Sender Account)</label>
                <select 
                  required
                  value={newCampaignForm.linkedin_account_id}
                  onChange={(e) => setNewCampaignForm({...newCampaignForm, linkedin_account_id: e.target.value})}
                  className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                >
                  <option value="">Select profile account to send from...</option>
                  {accounts.map(acc => (
                    <option key={acc.id} value={acc.id}>{acc.label} ({acc.region.toUpperCase()})</option>
                  ))}
                </select>
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

              {/* Target Import Options inside Modal */}
              <div className="border-t pt-3 dark:border-navy-800 space-y-2">
                <label className="block font-bold text-navy-900 dark:text-white mb-1">Import Target Contacts</label>
                <div className="flex gap-2 mb-2">
                  <button
                    type="button"
                    onClick={() => setNewCampaignImportMethod('none')}
                    className={`px-3 py-1.5 rounded-lg border text-[11px] font-bold ${
                      newCampaignImportMethod === 'none'
                        ? 'bg-brand-50 border-brand-200 text-brand-700 dark:bg-navy-800'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-50'
                    }`}
                  >
                    No Targets (Draft)
                  </button>
                  <button
                    type="button"
                    onClick={() => setNewCampaignImportMethod('csv')}
                    className={`px-3 py-1.5 rounded-lg border text-[11px] font-bold ${
                      newCampaignImportMethod === 'csv'
                        ? 'bg-brand-50 border-brand-200 text-brand-700 dark:bg-navy-800'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-50'
                    }`}
                  >
                    Upload CSV File
                  </button>
                  <button
                    type="button"
                    onClick={() => setNewCampaignImportMethod('manual')}
                    className={`px-3 py-1.5 rounded-lg border text-[11px] font-bold ${
                      newCampaignImportMethod === 'manual'
                        ? 'bg-brand-50 border-brand-200 text-brand-700 dark:bg-navy-800'
                        : 'border-slate-200 text-slate-500 hover:bg-slate-50'
                    }`}
                  >
                    Add Targets Manually
                  </button>
                </div>

                {newCampaignImportMethod === 'csv' && (
                  <div className="p-3 bg-slate-50 dark:bg-navy-950/40 rounded-xl border border-dashed border-slate-200 dark:border-navy-800">
                    <label className="block font-semibold text-slate-600 mb-1">Select Targets CSV file</label>
                    <input 
                      type="file" 
                      accept=".csv" 
                      required
                      onChange={(e) => setNewCampaignCsvFile(e.target.files[0])}
                      className="w-full text-slate-500 file:mr-3 file:py-1 file:px-2 file:rounded-lg file:border-0 file:bg-brand-50 file:text-brand-700 hover:file:bg-brand-100"
                    />
                  </div>
                )}

                {newCampaignImportMethod === 'manual' && (
                  <div className="space-y-2 p-3 bg-slate-50 dark:bg-navy-950/40 rounded-xl border max-h-[160px] overflow-y-auto">
                    <div className="flex justify-between items-center border-b pb-1 mb-2 dark:border-navy-800">
                      <span className="font-bold text-slate-600">Manual Prospects list</span>
                      <button
                        type="button"
                        onClick={() => setNewCampaignManualRows([...newCampaignManualRows, { name: '', linkedin_url: '', title: '', company: '' }])}
                        className="text-brand-500 font-bold hover:underline text-[10px]"
                      >
                        + Add Row
                      </button>
                    </div>
                    {newCampaignManualRows.map((row, idx) => (
                      <div key={idx} className="grid grid-cols-2 gap-2 border-b border-slate-100 dark:border-navy-900 pb-2">
                        <input
                          type="text"
                          required
                          placeholder="Full Name"
                          value={row.name}
                          onChange={(e) => {
                            const newRows = [...newCampaignManualRows];
                            newRows[idx].name = e.target.value;
                            setNewCampaignManualRows(newRows);
                          }}
                          className="rounded border p-1 text-[10px] bg-white dark:border-navy-800 dark:bg-navy-950"
                        />
                        <input
                          type="text"
                          required
                          placeholder="LinkedIn URL"
                          value={row.linkedin_url}
                          onChange={(e) => {
                            const newRows = [...newCampaignManualRows];
                            newRows[idx].linkedin_url = e.target.value;
                            setNewCampaignManualRows(newRows);
                          }}
                          className="rounded border p-1 text-[10px] bg-white dark:border-navy-800 dark:bg-navy-950"
                        />
                        <input
                          type="text"
                          placeholder="Title (Optional)"
                          value={row.title}
                          onChange={(e) => {
                            const newRows = [...newCampaignManualRows];
                            newRows[idx].title = e.target.value;
                            setNewCampaignManualRows(newRows);
                          }}
                          className="rounded border p-1 text-[10px] bg-white dark:border-navy-800 dark:bg-navy-950"
                        />
                        <div className="flex items-center gap-1">
                          <input
                            type="text"
                            placeholder="Company (Optional)"
                            value={row.company}
                            onChange={(e) => {
                              const newRows = [...newCampaignManualRows];
                              newRows[idx].company = e.target.value;
                              setNewCampaignManualRows(newRows);
                            }}
                            className="w-full rounded border p-1 text-[10px] bg-white dark:border-navy-800 dark:bg-navy-950"
                          />
                          {newCampaignManualRows.length > 1 && (
                            <button
                              type="button"
                              onClick={() => setNewCampaignManualRows(newCampaignManualRows.filter((_, i) => i !== idx))}
                              className="text-rose-600 hover:text-rose-700 font-bold p-1 text-[11px]"
                            >
                              ✕
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
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
          MANUAL COOKIE CONNECTION MODAL (ACCOUNTS TAB)
          ========================================================================= */}
      {isAccountModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-xl rounded-2xl bg-white p-6 shadow-2xl dark:bg-navy-900 border border-slate-100 dark:border-navy-800 text-xs">
            
            {showLinkedInMockLogin ? (
              <div className="space-y-4">
                <div className="flex flex-col items-center py-4 border-b dark:border-navy-800">
                  <div className="flex items-center gap-1 text-brand-600 font-bold text-xl mb-1">
                    <Linkedin size={28} className="fill-brand-600 text-white" />
                    <span>Linked<span className="bg-brand-600 text-white rounded px-1.5 py-0.5 ml-1">in</span></span>
                  </div>
                  <h3 className="text-sm font-bold text-navy-900 dark:text-white mt-2">Sign in to sync your active account session</h3>
                  <p className="text-[10px] text-slate-400">Securely link your credentials for automated outreach campaigns.</p>
                </div>

                <div className="space-y-3">
                  <div>
                    <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Email or Phone</label>
                    <input 
                      type="text" 
                      placeholder="email@example.com"
                      value={mockEmail}
                      onChange={(e) => setMockEmail(e.target.value)}
                      className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block font-semibold text-slate-700 dark:text-slate-300 mb-1">Password</label>
                    <input 
                      type="password" 
                      placeholder="••••••••"
                      value={mockPassword}
                      onChange={(e) => setMockPassword(e.target.value)}
                      className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="rounded-lg bg-emerald-50 border border-emerald-100 p-3 dark:bg-emerald-950/20 dark:border-emerald-800/40 text-emerald-800 dark:text-emerald-400 leading-snug">
                  <p className="font-bold flex items-center gap-1 text-[11px]"><Shield size={13} /> Encrypted Session Tunnel</p>
                  <p className="text-[9px] mt-0.5">Your password is never stored. We securely negotiate with LinkedIn's auth servers to obtain and store encrypted session tokens (`li_at`).</p>
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t dark:border-navy-800">
                  <button
                    type="button"
                    onClick={() => setShowLinkedInMockLogin(false)}
                    className="rounded-xl border border-slate-200 bg-white hover:bg-slate-50 px-4 py-2 font-bold text-slate-600 dark:border-navy-800 dark:bg-navy-950"
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      if (!mockEmail || !mockPassword) {
                        alert('Please enter your email and password.');
                        return;
                      }
                      // Simulate cookie capture
                      const generatedLiAt = `mock_li_at_${connectLabel.replace(/\s+/g, '_')}_${Math.random().toString(36).substring(4)}`;
                      const generatedJsessionid = `ajax:${Math.floor(100000000 + Math.random() * 900000000)}`;
                      
                      setSubmittingAccount(true);
                      try {
                        await api.createLinkedInAccount({
                          label: connectLabel,
                          region: connectRegion,
                          li_at: generatedLiAt,
                          jsessionid: generatedJsessionid
                        });
                        notify('Success', 'LinkedIn account linked successfully!');
                        setShowLinkedInMockLogin(false);
                        closeConnectModal();
                        fetchAccounts();
                      } catch (err) {
                        notify('Error', err.message || 'Failed to link account.');
                      } finally {
                        setSubmittingAccount(false);
                      }
                    }}
                    disabled={submittingAccount || !mockEmail || !mockPassword}
                    className="rounded-xl bg-brand-500 hover:bg-brand-600 px-4 py-2 text-white font-bold disabled:bg-slate-200 flex items-center gap-1.5"
                  >
                    {submittingAccount && <RefreshCw size={12} className="animate-spin" />}
                    {submittingAccount ? 'Connecting...' : 'Authorize & Connect'}
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-navy-800">
                  <h3 className="text-sm font-bold text-navy-900 dark:text-white flex items-center gap-1.5">
                    <Linkedin size={18} className="text-brand-500" /> Link LinkedIn Account
                  </h3>
                  <button onClick={closeConnectModal} className="text-slate-400 hover:text-slate-600 dark:hover:text-white">
                    <X size={16} />
                  </button>
                </div>

                <div className="mt-4 space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block font-bold text-navy-900 dark:text-white mb-1">Account Label / Identifier</label>
                      <input 
                        type="text" 
                        required
                        placeholder="e.g. My Personal Profile" 
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

                  {/* Prominent LinkedIn login action */}
                  <div className="border border-slate-100 dark:border-navy-800 rounded-xl p-6 text-center space-y-3 bg-slate-50/50 dark:bg-navy-950/20">
                    <div className="mx-auto w-12 h-12 rounded-full bg-brand-50 dark:bg-brand-950/30 flex items-center justify-center text-brand-500">
                      <Linkedin size={24} className="fill-brand-500 text-slate-50/50" />
                    </div>
                    <div>
                      <p className="font-bold text-navy-900 dark:text-white text-xs">Connect using LinkedIn login</p>
                      <p className="text-[10px] text-slate-500 max-w-sm mx-auto mt-1">Recommended. We will open a secure window prompting you to sign in to LinkedIn to link your active session.</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        if (!connectLabel.trim()) {
                          alert('Please enter an account label.');
                          return;
                        }
                        setShowLinkedInMockLogin(true);
                      }}
                      className="rounded-xl bg-brand-500 hover:bg-brand-600 px-5 py-2.5 text-white font-bold inline-flex items-center gap-2 text-xs shadow-md shadow-brand-500/10"
                    >
                      <Linkedin size={15} className="fill-white" /> Sign In with LinkedIn
                    </button>
                  </div>

                  <div className="flex justify-between items-center text-[10px] text-slate-400">
                    <span>or connect manually using browser cookies</span>
                    <button
                      type="button"
                      onClick={() => {
                        const liAtInput = prompt("Enter your LinkedIn 'li_at' cookie value:");
                        if (!liAtInput) return;
                        setLiAtCookie(liAtInput);
                        const jSessionInput = prompt("Enter your LinkedIn 'JSESSIONID' cookie value (Optional):") || '';
                        setJsessionIdCookie(jSessionInput);
                      }}
                      className="text-brand-500 font-bold hover:underline"
                    >
                      Enter Cookies manually
                    </button>
                  </div>

                  {liAtCookie && (
                    <div className="p-3 bg-slate-100 dark:bg-navy-950 rounded-xl space-y-1 font-mono text-[10px]">
                      <p className="font-bold text-slate-600">Cookies Entered:</p>
                      <p className="truncate text-slate-500">li_at: {liAtCookie}</p>
                      {jsessionIdCookie && <p className="truncate text-slate-500">JSESSIONID: {jsessionIdCookie}</p>}
                    </div>
                  )}

                  <div className="flex justify-end gap-2 pt-2 border-t dark:border-navy-800">
                    <button
                      type="button"
                      onClick={closeConnectModal}
                      className="rounded-xl border border-slate-200 bg-white hover:bg-slate-50 px-4 py-2 font-bold text-slate-600 dark:border-navy-800 dark:bg-navy-950 dark:text-slate-400"
                    >
                      Cancel
                    </button>
                    {liAtCookie && (
                      <button
                        type="button"
                        onClick={handleConnectAccount}
                        disabled={submittingAccount}
                        className="rounded-xl bg-brand-500 hover:bg-brand-600 px-4 py-2 text-white font-bold"
                      >
                        Submit Saved Cookies
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}

          </div>
        </div>
      )}
      {/* =========================================================================
          EDIT CAMPAIGN SETTINGS MODAL
          ========================================================================= */}
      {isEditingCampaign && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/40 backdrop-blur-sm p-4 text-xs">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-navy-900 border border-slate-100 dark:border-navy-800">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-navy-800">
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">Edit Campaign Settings</h3>
              <button onClick={() => setIsEditingCampaign(false)} className="text-slate-400 hover:text-slate-600 dark:hover:text-white">
                <X size={16} />
              </button>
            </div>

            <form onSubmit={handleUpdateCampaign} className="mt-4 space-y-3">
              <div>
                <label className="block font-bold text-navy-900 dark:text-white mb-1">Campaign Name</label>
                <input 
                  type="text" 
                  required
                  value={editCampaignForm.name}
                  onChange={(e) => setEditCampaignForm({...editCampaignForm, name: e.target.value})}
                  className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:border-brand-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-navy-900 dark:text-white mb-1">LinkedIn Profile (Sender)</label>
                  <select 
                    required
                    value={editCampaignForm.linkedin_account_id}
                    onChange={(e) => setEditCampaignForm({...editCampaignForm, linkedin_account_id: e.target.value})}
                    className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                  >
                    <option value="">Select profile account...</option>
                    {accounts.map(acc => (
                      <option key={acc.id} value={acc.id}>{acc.label} ({acc.region.toUpperCase()})</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block font-bold text-navy-900 dark:text-white mb-1">Campaign Status</label>
                  <select 
                    value={editCampaignForm.status}
                    onChange={(e) => setEditCampaignForm({...editCampaignForm, status: e.target.value})}
                    className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                  >
                    <option value="draft">Draft</option>
                    <option value="running">Running</option>
                    <option value="paused">Paused</option>
                    <option value="completed">Completed</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-navy-900 dark:text-white mb-1">Outreach Mode</label>
                  <select 
                    value={editCampaignForm.mode}
                    onChange={(e) => setEditCampaignForm({...editCampaignForm, mode: e.target.value})}
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
                    value={editCampaignForm.role_filter}
                    onChange={(e) => setEditCampaignForm({...editCampaignForm, role_filter: e.target.value})}
                    className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block font-bold text-navy-900 dark:text-white mb-1">Connection Note Prompt</label>
                <textarea 
                  rows={2}
                  value={editCampaignForm.connection_note_prompt}
                  onChange={(e) => setEditCampaignForm({...editCampaignForm, connection_note_prompt: e.target.value})}
                  className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-bold text-navy-900 dark:text-white mb-1">Follow-up Message Prompt</label>
                <textarea 
                  rows={2}
                  value={editCampaignForm.followup_prompt}
                  onChange={(e) => setEditCampaignForm({...editCampaignForm, followup_prompt: e.target.value})}
                  className="w-full rounded-xl border border-slate-200 p-2.5 bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                />
              </div>

              <div className="flex justify-between items-center pt-2">
                <div className="flex items-center gap-2">
                  <input 
                    type="checkbox" 
                    id="edit_require_approval"
                    checked={editCampaignForm.require_approval}
                    onChange={(e) => setEditCampaignForm({...editCampaignForm, require_approval: e.target.checked})}
                    className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                  />
                  <label htmlFor="edit_require_approval" className="font-semibold text-slate-700 dark:text-slate-300">
                    Require approval before sending notes
                  </label>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setIsEditingCampaign(false)}
                    className="rounded-xl border border-slate-200 bg-white hover:bg-slate-50 px-4 py-2 font-bold text-slate-600 dark:border-navy-800 dark:bg-navy-950 dark:text-slate-400"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="rounded-xl bg-brand-500 hover:bg-brand-600 px-4 py-2 text-white font-bold"
                  >
                    Save Changes
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* =========================================================================
          DIRECT TARGET MESSAGE REVIEW MODAL
          ========================================================================= */}
      {reviewTargetMessage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/40 backdrop-blur-sm p-4 text-xs">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-navy-900 border border-slate-100 dark:border-navy-800">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-navy-800">
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">Review Connection Note</h3>
              <button onClick={() => setReviewTargetMessage(null)} className="text-slate-400 hover:text-slate-600 dark:hover:text-white">
                <X size={16} />
              </button>
            </div>

            <div className="mt-3 space-y-2 text-left">
              <p className="font-bold text-navy-900 dark:text-white">To: {reviewTargetMessage.targetName}</p>
              <p className="text-[10px] text-slate-500">{reviewTargetMessage.targetTitle} at {reviewTargetMessage.targetCompany}</p>
              
              <div className="mt-2 text-xs">
                <label className="block text-[10px] font-bold text-slate-500 mb-1">EDIT NOTE CONTENT</label>
                <textarea
                  className="w-full border rounded-lg p-2.5 text-xs bg-white dark:bg-navy-950 dark:text-white focus:outline-none"
                  rows={4}
                  value={editingContent}
                  onChange={(e) => setEditingContent(e.target.value)}
                />
              </div>

              {selectedCampaign.mode === 'manual' && (
                <div className="p-3 rounded-xl border border-brand-100 bg-brand-50/20 dark:border-navy-800 dark:bg-navy-950/40 mb-3 space-y-2">
                  <p className="font-bold text-[9px] text-brand-600 dark:text-brand-400 uppercase tracking-wider">Manual Dispatch Scheduler Presets</p>
                  <select
                    value={reviewTargetMessage.scheduledTimePreset || 'immediate'}
                    onChange={(e) => {
                      const preset = e.target.value;
                      let scheduledTime = '';
                      if (preset === '5m') {
                        scheduledTime = new Date(Date.now() + 5 * 60 * 1000).toISOString();
                      } else if (preset === '1h') {
                        scheduledTime = new Date(Date.now() + 60 * 60 * 1000).toISOString();
                      } else if (preset === '4h') {
                        scheduledTime = new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString();
                      } else if (preset === 'custom') {
                        scheduledTime = 'custom';
                      }
                      setReviewTargetMessage({
                        ...reviewTargetMessage,
                        scheduledTimePreset: preset,
                        scheduledTime: scheduledTime
                      });
                    }}
                    className="w-full rounded-lg border border-slate-200 p-1.5 text-[11px] bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                  >
                    <option value="immediate">Send ASAP (Immediate)</option>
                    <option value="5m">Wait 5 minutes</option>
                    <option value="1h">Wait 1 hour</option>
                    <option value="4h">Wait 4 hours</option>
                    <option value="custom">Custom Date & Time</option>
                  </select>

                  {reviewTargetMessage.scheduledTimePreset === 'custom' && (
                    <div className="mt-2">
                      <label className="block text-[8px] text-slate-400 font-bold mb-0.5">DATE & TIME</label>
                      <input
                        type="datetime-local"
                        value={reviewTargetMessage.customDatetime || ''}
                        onChange={(e) => {
                          const dateval = e.target.value;
                          setReviewTargetMessage({
                            ...reviewTargetMessage,
                            customDatetime: dateval,
                            scheduledTime: dateval ? new Date(dateval).toISOString() : ''
                          });
                        }}
                        className="w-full rounded-lg border border-slate-200 p-1 text-[11px] bg-white dark:border-navy-800 dark:bg-navy-950 dark:text-white focus:outline-none"
                      />
                    </div>
                  )}
                </div>
              )}

              <div className="flex gap-2 justify-end pt-3 border-t dark:border-navy-800">
                <button
                  type="button"
                  onClick={() => {
                    handleReviewMessage(reviewTargetMessage.messageId, 'reject');
                    setReviewTargetMessage(null);
                  }}
                  className="rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-600 px-3 py-2 text-[11px] font-bold"
                >
                  Reject Note
                </button>
                <button
                  type="button"
                  onClick={() => setReviewTargetMessage(null)}
                  className="rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 dark:border-navy-800 dark:bg-navy-950 dark:text-slate-400 px-3 py-2 text-[11px]"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const finalTime = reviewTargetMessage.scheduledTime === 'custom' ? null : reviewTargetMessage.scheduledTime;
                    handleReviewMessage(reviewTargetMessage.messageId, 'approve', editingContent, finalTime);
                    setReviewTargetMessage(null);
                  }}
                  className="rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white px-3.5 py-2 text-[11px] font-bold"
                >
                  Approve & Send Note
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {/* =========================================================================
          TARGET MESSAGE HISTORY MODAL
          ========================================================================= */}
      {messageHistoryTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/40 backdrop-blur-sm p-4 text-xs">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-navy-900 border border-slate-100 dark:border-navy-800 max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-navy-800 shrink-0">
              <div>
                <h3 className="text-sm font-bold text-navy-900 dark:text-white flex items-center gap-1.5">
                  <MessageSquare size={14} className="text-brand-500" /> Message History
                </h3>
                <p className="text-[10px] text-slate-400 mt-0.5">
                  {messageHistoryTarget.person?.full_name || 'Prospect'} — {messageHistoryTarget.person?.title || 'Unknown Role'}
                </p>
              </div>
              <button onClick={() => setMessageHistoryTarget(null)} className="text-slate-400 hover:text-slate-600 dark:hover:text-white">
                <X size={16} />
              </button>
            </div>

            <div className="mt-3 space-y-3 overflow-y-auto flex-1">
              {messageHistoryLoading ? (
                <div className="flex justify-center py-8">
                  <RefreshCw size={20} className="animate-spin text-slate-300" />
                </div>
              ) : messageHistoryList.length === 0 ? (
                <p className="text-xs py-6 text-slate-400 text-center">No messages have been generated for this prospect yet.</p>
              ) : (
                messageHistoryList.map((m) => {
                  const statusStyles = {
                    sent: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300',
                    approved: 'bg-sky-100 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300',
                    needs_review: 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300',
                    failed: 'bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300',
                    queued: 'bg-slate-100 text-slate-600 dark:bg-navy-800 dark:text-slate-400',
                  };
                  return (
                    <div
                      key={m.id}
                      className={`p-3 rounded-xl border text-left ${
                        m.direction === 'out'
                          ? 'border-brand-100 bg-brand-50/30 dark:border-navy-800 dark:bg-navy-950/40'
                          : 'border-slate-200 bg-white dark:border-navy-800 dark:bg-navy-950/10'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="font-bold text-[10px] uppercase tracking-wider text-slate-500 flex items-center gap-1">
                          {m.direction === 'out' ? <Send size={10} /> : <Inbox size={10} />}
                          {m.direction === 'out' ? 'Outgoing' : 'Reply'}
                        </span>
                        <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase tracking-wider ${statusStyles[m.status] || 'bg-slate-100 text-slate-600'}`}>
                          {m.status.replace('_', ' ')}
                        </span>
                      </div>
                      <p className="text-navy-900 dark:text-white whitespace-pre-wrap">{m.content || '(no content)'}</p>
                      <div className="mt-1.5 flex items-center justify-between gap-2">
                        <p className="text-[10px] text-slate-400">
                          {m.sent_at ? `Sent ${new Date(m.sent_at).toLocaleString()}` : m.scheduled_send_at ? `Scheduled for ${new Date(m.scheduled_send_at).toLocaleString()}` : `Created ${m.created_at ? new Date(m.created_at).toLocaleString() : ''}`}
                        </p>
                        {m.status === 'failed' && (
                          <button
                            type="button"
                            onClick={() => handleResendMessage(m.id, messageHistoryTarget)}
                            className="bg-rose-50 hover:bg-rose-100 dark:bg-rose-950/40 text-rose-600 dark:text-rose-400 px-2 py-1 rounded text-[10px] font-bold transition-all shrink-0 flex items-center gap-1"
                          >
                            <RefreshCw size={11} /> Resend
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            <div className="flex justify-end pt-3 mt-3 border-t dark:border-navy-800 shrink-0">
              <button
                type="button"
                onClick={() => setMessageHistoryTarget(null)}
                className="rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 dark:border-navy-800 dark:bg-navy-950 dark:text-slate-400 px-3.5 py-2 text-[11px] font-bold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
