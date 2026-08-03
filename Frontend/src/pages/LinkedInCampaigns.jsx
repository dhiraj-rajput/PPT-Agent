import { useEffect, useState } from 'react';
import { Plus, X, Trash2, Upload, Search, Check, AlertCircle, RefreshCw, Layers, User, Users, ClipboardList, MessageSquare, ChevronRight, Edit2, Play, Circle } from 'lucide-react';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';

export default function LinkedInCampaigns() {
  const { createAlert } = useNotifications();
  const notify = (title, message) => createAlert(title, message).catch(() => {});

  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  
  // Tab states for campaign details
  const [activeTab, setActiveTab] = useState('targets'); // 'targets' | 'queue'
  
  // Campaign targets & queue
  const [targets, setTargets] = useState([]);
  const [queue, setQueue] = useState([]);
  const [targetsLoading, setTargetsLoading] = useState(false);
  const [queueLoading, setQueueLoading] = useState(false);

  // Forms & Modals
  const [showNewCampaign, setShowNewCampaign] = useState(false);
  const [newCampaignForm, setNewCampaignForm] = useState({
    name: '',
    mode: 'manual', // 'auto', 'manual', 'hybrid'
    role_filter: '',
    message_generation_mode: 'llm',
    connection_note_prompt: 'Keep it friendly and professional, referencing their headline.',
    followup_prompt: 'Thank them for connecting and ask if they are open to sharing outreach ideas.',
    require_approval: true
  });
  
  const [csvFile, setCsvFile] = useState(null);
  const [uploadingTargets, setUploadingTargets] = useState(false);
  
  // Message Editing
  const [editingMessageId, setEditingMessageId] = useState(null);
  const [editingContent, setEditingContent] = useState('');

  // Fetch campaigns
  const fetchCampaigns = async () => {
    try {
      setLoading(true);
      const res = await api.listLinkedInCampaigns();
      setCampaigns(res.campaigns || []);
    } catch (err) {
      notify('Error', `Failed to load campaigns: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCampaigns();
  }, []);

  // Fetch targets and queue when campaign changes
  const loadCampaignData = async (campaign) => {
    setSelectedCampaign(campaign);
    if (!campaign) return;
    
    // Fetch targets
    setTargetsLoading(true);
    try {
      const res = await api.getLinkedInTargets(campaign.id);
      setTargets(res.targets || []);
    } catch (err) {
      notify('Error', `Failed to load targets: ${err.message}`);
    } finally {
      setTargetsLoading(false);
    }

    // Fetch queue
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

  // Create Campaign
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

  // Delete Campaign
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

  // Upload Target CSV
  const handleImportTargets = async (e) => {
    e.preventDefault();
    if (!csvFile || !selectedCampaign) return;
    
    setUploadingTargets(true);
    try {
      const res = await api.importLinkedInTargets(selectedCampaign.id, { file: csvFile });
      notify('Import Complete', res.message || `Imported targets successfully.`);
      setCsvFile(null);
      // Reload targets
      loadCampaignData(selectedCampaign);
    } catch (err) {
      notify('Error', `Failed to import targets: ${err.message}`);
    } finally {
      setUploadingTargets(false);
    }
  };

  // Approve / Reject / Edit message
  const handleReviewMessage = async (messageId, action, finalContent) => {
    try {
      await api.reviewLinkedInMessage(messageId, {
        content: finalContent || editingContent,
        action: action
      });
      notify('Success', `Message ${action}ed.`);
      setEditingMessageId(null);
      // Reload data
      loadCampaignData(selectedCampaign);
    } catch (err) {
      notify('Error', `Failed to review message: ${err.message}`);
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <PageHeader 
        title="LinkedIn Outreach Campaigns" 
        subtitle="Manage targeted LinkedIn sequences, approve outreach notes, and track campaign connections."
        action={
          <button
            onClick={() => setShowNewCampaign(true)}
            className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2 text-sm font-bold text-white shadow-lg shadow-brand-500/20 transition-all hover:bg-brand-600 hover:shadow-brand-600/30"
          >
            <Plus size={16} /> New Campaign
          </button>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left Column: Campaigns List */}
        <div className="lg:col-span-1 space-y-4">
          <Card>
            <h2 className="mb-4 text-lg font-bold text-navy-900 dark:text-white flex items-center gap-2">
              <Layers size={18} className="text-brand-500" /> Outreach Campaigns
            </h2>
            
            {loading ? (
              <div className="flex justify-center py-8">
                <RefreshCw size={24} className="animate-spin text-slate-400" />
              </div>
            ) : campaigns.length === 0 ? (
              <p className="text-center py-6 text-sm text-slate-500 dark:text-slate-400">No campaigns created yet.</p>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-navy-800">
                {campaigns.map((c) => (
                  <div
                    key={c.id}
                    onClick={() => loadCampaignData(c)}
                    className={`flex items-center justify-between py-3 cursor-pointer group transition-all rounded-xl px-2 ${
                      selectedCampaign?.id === c.id
                        ? 'bg-brand-50 dark:bg-navy-800/50 border-l-4 border-brand-500'
                        : 'hover:bg-slate-50 dark:hover:bg-navy-800/20'
                    }`}
                  >
                    <div className="min-w-0 flex-1 pr-2">
                      <div className="flex items-center gap-2">
                        <h3 className="truncate font-semibold text-sm text-navy-900 dark:text-white group-hover:text-brand-500">
                          {c.name}
                        </h3>
                        <StatusBadge status={c.status === 'draft' ? 'Draft' : c.status === 'running' ? 'Running' : 'Paused'} />
                      </div>
                      <div className="mt-1 flex items-center gap-3 text-xs text-slate-500">
                        <span>Mode: {c.mode.toUpperCase()}</span>
                        <span>Role: {c.role_filter || 'All'}</span>
                      </div>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteCampaign(c.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 text-rose-500 hover:text-rose-600 transition-opacity p-1"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Right Column: Campaign Details & Operations */}
        <div className="lg:col-span-2 space-y-6">
          {selectedCampaign ? (
            <Card>
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4 dark:border-navy-800">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-xl font-bold text-navy-900 dark:text-white">{selectedCampaign.name}</h2>
                    <StatusBadge status={selectedCampaign.status === 'draft' ? 'Draft' : selectedCampaign.status === 'running' ? 'Running' : 'Paused'} />
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    Mode: {selectedCampaign.mode.toUpperCase()} | Message generation: {selectedCampaign.message_generation_mode.toUpperCase()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {selectedCampaign.status !== 'running' ? (
                    <button
                      onClick={async () => {
                        try {
                          await api.updateLinkedInCampaign(selectedCampaign.id, { status: 'running' });
                          notify('Success', 'Campaign started.');
                          fetchCampaigns();
                          setSelectedCampaign(prev => ({ ...prev, status: 'running' }));
                        } catch (err) {
                          notify('Error', err.message);
                        }
                      }}
                      className="flex items-center gap-1.5 rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-600"
                    >
                      <Play size={12} /> Run Campaign
                    </button>
                  ) : (
                    <button
                      onClick={async () => {
                        try {
                          await api.updateLinkedInCampaign(selectedCampaign.id, { status: 'paused' });
                          notify('Success', 'Campaign paused.');
                          fetchCampaigns();
                          setSelectedCampaign(prev => ({ ...prev, status: 'paused' }));
                        } catch (err) {
                          notify('Error', err.message);
                        }
                      }}
                      className="flex items-center gap-1.5 rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-bold text-white hover:bg-amber-600"
                    >
                      <Circle size={12} /> Pause Campaign
                    </button>
                  )}
                </div>
              </div>

              {/* Tabs */}
              <div className="mt-4 flex border-b border-slate-100 dark:border-navy-800">
                <button
                  onClick={() => setActiveTab('targets')}
                  className={`flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-sm font-bold transition-all ${
                    activeTab === 'targets'
                      ? 'border-brand-500 text-brand-500'
                      : 'border-transparent text-slate-500 hover:text-slate-700'
                  }`}
                >
                  <Users size={16} /> Targets ({targets.length})
                </button>
                <button
                  onClick={() => setActiveTab('queue')}
                  className={`flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-sm font-bold transition-all ${
                    activeTab === 'queue'
                      ? 'border-brand-500 text-brand-500'
                      : 'border-transparent text-slate-500 hover:text-slate-700'
                  }`}
                >
                  <ClipboardList size={16} /> Approval Queue ({queue.length})
                </button>
              </div>

              {/* Tab Contents */}
              <div className="mt-6">
                {activeTab === 'targets' && (
                  <div className="space-y-6">
                    {/* Add Targets Uploader */}
                    <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-4 dark:border-navy-800 dark:bg-navy-800/10">
                      <h3 className="text-sm font-bold text-navy-900 dark:text-white mb-2 flex items-center gap-1.5">
                        <Upload size={14} className="text-brand-500" /> Import Target List (CSV)
                      </h3>
                      <form onSubmit={handleImportTargets} className="flex items-center gap-3">
                        <input
                          type="file"
                          accept=".csv"
                          onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                          className="block w-full text-xs text-slate-500 file:mr-4 file:py-1.5 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-semibold file:bg-brand-50 file:text-brand-700 hover:file:bg-brand-100"
                        />
                        <button
                          type="submit"
                          disabled={!csvFile || uploadingTargets}
                          className="rounded-lg bg-brand-500 px-3 py-1.5 text-xs font-bold text-white hover:bg-brand-600 disabled:bg-slate-200 disabled:text-slate-400"
                        >
                          {uploadingTargets ? 'Uploading...' : 'Import'}
                        </button>
                      </form>
                      <p className="mt-1 text-[10px] text-slate-400">
                        CSV requires: <strong>name</strong> and <strong>linkedin</strong> (URL). Optional: title, company.
                      </p>
                    </div>

                    {/* Targets Table */}
                    {targetsLoading ? (
                      <div className="flex justify-center py-6">
                        <RefreshCw size={20} className="animate-spin text-slate-400" />
                      </div>
                    ) : targets.length === 0 ? (
                      <p className="text-center py-8 text-sm text-slate-500">No targets imported yet.</p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse text-xs">
                          <thead>
                            <tr className="border-b border-slate-100 text-slate-500 dark:border-navy-800 font-bold uppercase">
                              <th className="py-2">Prospect</th>
                              <th className="py-2">Role / Company</th>
                              <th className="py-2">Scrape Status</th>
                              <th className="py-2">Connection</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-50 dark:divide-navy-800/40">
                            {targets.map((t) => (
                              <tr key={t.id} className="hover:bg-slate-50/50 dark:hover:bg-navy-800/10">
                                <td className="py-3 font-semibold text-navy-900 dark:text-white">
                                  {t.person?.full_name}
                                  {t.person?.linkedin_url && (
                                    <a
                                      href={t.person.linkedin_url}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="ml-2 text-xs text-brand-500 hover:underline"
                                    >
                                      in
                                    </a>
                                  )}
                                </td>
                                <td className="py-3 text-slate-600 dark:text-slate-400">
                                  {t.person?.title || 'Unknown'} at {t.person?.organization_name || 'Unknown'}
                                </td>
                                <td className="py-3">
                                  <StatusBadge status={t.scrape_status === 'scraped' ? 'Open' : t.scrape_status === 'failed' ? 'Failed' : 'Pending'} />
                                </td>
                                <td className="py-3">
                                  <StatusBadge status={t.connection_status === 'accepted' ? 'Active' : t.connection_status === 'pending' ? 'Pending' : 'Draft'} />
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}

                {activeTab === 'queue' && (
                  <div className="space-y-4">
                    {queueLoading ? (
                      <div className="flex justify-center py-6">
                        <RefreshCw size={20} className="animate-spin text-slate-400" />
                      </div>
                    ) : queue.length === 0 ? (
                      <div className="text-center py-8 text-sm text-slate-500 flex flex-col items-center justify-center gap-2">
                        <Check size={28} className="text-emerald-500" />
                        <p>Approval queue is clean. No outreach drafts waiting.</p>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        {queue.map((msg) => (
                          <div
                            key={msg.id}
                            className="rounded-xl border border-slate-100 p-4 dark:border-navy-800 dark:bg-navy-800/10 hover:border-slate-200 transition-all"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <h4 className="font-bold text-sm text-navy-900 dark:text-white">
                                  To: {msg.target?.person?.full_name || 'Prospect'}
                                </h4>
                                <p className="text-xs text-slate-500">
                                  {msg.target?.person?.title} at {msg.target?.person?.organization_name}
                                </p>
                              </div>
                              <span className="rounded-md bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                                Requires Approval
                              </span>
                            </div>

                            {/* Message content editor */}
                            <div className="mt-3">
                              {editingMessageId === msg.id ? (
                                <div className="space-y-2">
                                  <textarea
                                    value={editingContent}
                                    onChange={(e) => setEditingContent(e.target.value)}
                                    rows={4}
                                    maxLength={300}
                                    className="w-full rounded-lg border border-slate-200 p-2.5 text-xs focus:border-brand-500 focus:outline-none dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                                  />
                                  <div className="flex items-center justify-between">
                                    <span className="text-[10px] text-slate-400">{editingContent.length}/300 chars</span>
                                    <div className="flex gap-2">
                                      <button
                                        onClick={() => setEditingMessageId(null)}
                                        className="rounded px-2.5 py-1 text-xs font-semibold text-slate-500 hover:text-slate-700"
                                      >
                                        Cancel
                                      </button>
                                      <button
                                        onClick={() => handleReviewMessage(msg.id, 'approve', editingContent)}
                                        className="rounded bg-brand-500 px-2.5 py-1 text-xs font-bold text-white hover:bg-brand-600"
                                      >
                                        Save & Approve
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              ) : (
                                <div>
                                  <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-700 dark:bg-navy-900/60 dark:text-slate-300 whitespace-pre-line leading-relaxed">
                                    {msg.content}
                                  </p>
                                  <div className="mt-3 flex items-center justify-between flex-wrap gap-2">
                                    <button
                                      onClick={() => {
                                        setEditingMessageId(msg.id);
                                        setEditingContent(msg.content);
                                      }}
                                      className="flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-brand-500"
                                    >
                                      <Edit2 size={12} /> Edit Draft
                                    </button>
                                    <div className="flex gap-2">
                                      <button
                                        onClick={() => handleReviewMessage(msg.id, 'reject')}
                                        className="rounded bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-600 hover:bg-rose-100"
                                      >
                                        Reject
                                      </button>
                                      <button
                                        onClick={() => handleReviewMessage(msg.id, 'approve', msg.content)}
                                        className="rounded bg-brand-500 px-3 py-1.5 text-xs font-bold text-white hover:bg-brand-600"
                                      >
                                        Approve & Queue
                                      </button>
                                    </div>
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </Card>
          ) : (
            <div className="flex h-64 flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 dark:border-navy-800 p-8 text-center">
              <ClipboardList size={40} className="text-slate-300 dark:text-slate-700 mb-3" />
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">No Campaign Selected</h3>
              <p className="mt-1 text-xs text-slate-500 max-w-sm">
                Select an outreach campaign from the list on the left to manage targets, import contacts, and approve message queues.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* New Campaign Modal */}
      {showNewCampaign && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-900/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-navy-900 border border-slate-100 dark:border-navy-800">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-navy-800">
              <h3 className="text-lg font-bold text-navy-900 dark:text-white">Create LinkedIn Campaign</h3>
              <button onClick={() => setShowNewCampaign(false)} className="text-slate-400 hover:text-slate-600">
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleCreateCampaign} className="mt-4 space-y-4 text-xs">
              <div>
                <label className="block font-bold text-navy-900 dark:text-slate-300 mb-1">Campaign Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. CEO Outreach MEA Region"
                  value={newCampaignForm.name}
                  onChange={(e) => setNewCampaignForm({ ...newCampaignForm, name: e.target.value })}
                  className="w-full rounded-lg border border-slate-200 p-2 focus:border-brand-500 focus:outline-none dark:border-navy-700 dark:bg-navy-800 dark:text-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block font-bold text-navy-900 dark:text-slate-300 mb-1">Outreach Mode</label>
                  <select
                    value={newCampaignForm.mode}
                    onChange={(e) => setNewCampaignForm({ ...newCampaignForm, mode: e.target.value })}
                    className="w-full rounded-lg border border-slate-200 p-2 focus:border-brand-500 focus:outline-none dark:border-navy-800 dark:bg-navy-800 dark:text-white"
                  >
                    <option value="manual">Manual Approval</option>
                    <option value="auto">Fully Automated</option>
                    <option value="hybrid">Hybrid Handoff</option>
                  </select>
                </div>

                <div>
                  <label className="block font-bold text-navy-900 dark:text-slate-300 mb-1">Target Seniority/Role Filter</label>
                  <input
                    type="text"
                    placeholder="e.g. CEO, Founder, Owner"
                    value={newCampaignForm.role_filter}
                    onChange={(e) => setNewCampaignForm({ ...newCampaignForm, role_filter: e.target.value })}
                    className="w-full rounded-lg border border-slate-200 p-2 focus:border-brand-500 focus:outline-none dark:border-navy-700 dark:bg-navy-800 dark:text-white"
                  />
                </div>
              </div>

              <div>
                <label className="block font-bold text-navy-900 dark:text-slate-300 mb-1">Connection Note Prompt (LLM)</label>
                <textarea
                  rows={3}
                  value={newCampaignForm.connection_note_prompt}
                  onChange={(e) => setNewCampaignForm({ ...newCampaignForm, connection_note_prompt: e.target.value })}
                  className="w-full rounded-lg border border-slate-200 p-2 focus:border-brand-500 focus:outline-none dark:border-navy-700 dark:bg-navy-800 dark:text-white"
                />
              </div>

              <div>
                <label className="block font-bold text-navy-900 dark:text-slate-300 mb-1">Follow-up Message Prompt (LLM)</label>
                <textarea
                  rows={3}
                  value={newCampaignForm.followup_prompt}
                  onChange={(e) => setNewCampaignForm({ ...newCampaignForm, followup_prompt: e.target.value })}
                  className="w-full rounded-lg border border-slate-200 p-2 focus:border-brand-500 focus:outline-none dark:border-navy-700 dark:bg-navy-800 dark:text-white"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="requireApproval"
                  checked={newCampaignForm.require_approval}
                  onChange={(e) => setNewCampaignForm({ ...newCampaignForm, require_approval: e.target.checked })}
                  className="rounded border-slate-200 text-brand-500 focus:ring-brand-500"
                />
                <label htmlFor="requireApproval" className="font-semibold text-slate-700 dark:text-slate-300">
                  Require manual review before sending messages
                </label>
              </div>

              <div className="flex justify-end gap-2 border-t border-slate-100 pt-3 dark:border-navy-800">
                <button
                  type="button"
                  onClick={() => setShowNewCampaign(false)}
                  className="rounded-lg border border-slate-200 px-4 py-2 font-semibold text-slate-500 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-brand-500 px-4 py-2 font-bold text-white hover:bg-brand-600"
                >
                  Create Campaign
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
