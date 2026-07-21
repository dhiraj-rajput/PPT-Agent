import { useState, useEffect } from 'react';
import { Mail, Plus, Users, Send, Check, Loader2, Sparkles, Building2, Search, AlertCircle, Trash2, Image, Edit2 } from 'lucide-react';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { api, BASE_URL } from '../lib/api.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';

export default function Newsletter() {
  const { createAlert } = useNotifications();
  const notify = (title, message, link) => createAlert(title, message, link).catch(() => {});
  const [newsletters, setNewsletters] = useState([]);
  const [selectedNewsletter, setSelectedNewsletter] = useState(null);
  const [subscribers, setSubscribers] = useState([]);
  const [editions, setEditions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('editions'); // 'editions' | 'subscribers'

  // Modals
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newNewsletterForm, setNewNewsletterForm] = useState({ name: '', description: '', senderName: 'OrbitAvanya Tech', senderEmail: 'newsletter@orbitavanyatech.com' });
  const [showComposeModal, setShowComposeModal] = useState(false);
  const [editionForm, setEditionForm] = useState({ subject: '', body: '', imageUrl: '', sendNow: true });
  const [editingEditionId, setEditingEditionId] = useState(null);
  const [uploadingImage, setUploadingImage] = useState(false);

  // Company import modal
  const [showCompanyImport, setShowCompanyImport] = useState(false);
  const [companies, setCompanies] = useState([]);
  const [selectedCompanyIds, setSelectedCompanyIds] = useState({});
  const [importingCompanies, setImportingCompanies] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState('');

  const fetchNewsletters = () => {
    setLoading(true);
    api.getNewsletters()
      .then((res) => {
        const list = res?.newsletters || [];
        setNewsletters(list);
        if (list.length > 0 && !selectedNewsletter) {
          setSelectedNewsletter(list[0]);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to fetch newsletters:', err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchNewsletters();
  }, []);

  const fetchNewsletterDetails = (nl) => {
    if (!nl) return;
    api.getNewsletterSubscribers(nl.id)
      .then((res) => setSubscribers(res?.subscribers || []))
      .catch((err) => console.error(err));

    api.getNewsletterEditions(nl.id)
      .then((res) => setEditions(res?.editions || []))
      .catch((err) => console.error(err));
  };

  useEffect(() => {
    if (selectedNewsletter) {
      fetchNewsletterDetails(selectedNewsletter);
    }
  }, [selectedNewsletter]);

  const handleCreateNewsletter = (e) => {
    e.preventDefault();
    setSubmitting(true);
    api.createNewsletter(newNewsletterForm)
      .then((res) => {
        setSubmitting(false);
        setShowCreateModal(false);
        setNewNewsletterForm({ name: '', description: '', senderName: 'OrbitAvanya Tech', senderEmail: 'newsletter@orbitavanyatech.com' });
        fetchNewsletters();
        if (res?.newsletter) setSelectedNewsletter(res.newsletter);
        notify('Newsletter created', `"${newNewsletterForm.name}" is ready for subscribers.`, '/newsletter');
      })
      .catch((err) => {
        setSubmitting(false);
        setMessage(err.message || 'Failed to create newsletter');
      });
  };

  const handleDeleteNewsletter = async (nlId) => {
    if (!window.confirm("Are you sure you want to delete this publication and all its broadcast history?")) return;
    try {
      await api.deleteNewsletter(nlId);
      setSelectedNewsletter(null);
      fetchNewsletters();
    } catch (err) {
      alert(err.message || "Failed to delete newsletter");
    }
  };

  const handleSendEdition = async (e) => {
    e.preventDefault();
    if (!selectedNewsletter) return;
    setSubmitting(true);
    try {
      if (editingEditionId) {
        await api.updateNewsletterEdition(editingEditionId, {
          subject: editionForm.subject,
          body: editionForm.body,
          imageUrl: editionForm.imageUrl,
        });
      } else {
        if (recipientTargetMode === 'companies') {
          const companyIds = Object.keys(selectedBroadcastCompanyIds).filter(k => selectedBroadcastCompanyIds[k]);
          if (companyIds.length > 0) {
            await api.addNewsletterSubscribersFromCompanies(selectedNewsletter.id, companyIds);
          }
        } else if (recipientTargetMode === 'manual' && manualRecipientEmails.trim()) {
          await api.addNewsletterSubscribersFromCompanies(selectedNewsletter.id, [], manualRecipientEmails.trim());
        }

        await api.createNewsletterEdition(selectedNewsletter.id, editionForm);
      }

      setSubmitting(false);
      setShowComposeModal(false);
      setEditingEditionId(null);
      setEditionForm({ subject: '', body: '', imageUrl: '', sendNow: true });
      setSelectedBroadcastCompanyIds({});
      setManualRecipientEmails('');
      fetchNewsletterDetails(selectedNewsletter);
      notify(
        editingEditionId ? 'Edition updated' : 'Newsletter edition sent',
        `"${editionForm.subject}" ${editingEditionId ? 'was updated' : `was sent to ${selectedNewsletter.name} subscribers`}.`,
        '/newsletter'
      );
    } catch (err) {
      setSubmitting(false);
      setMessage(err.message || 'Failed to process edition');
    }
  };

  const openCompanyImport = () => {
    setShowCompanyImport(true);
    api.getCompanies({ limit: 50 })
      .then((res) => setCompanies(res?.companies || []))
      .catch((err) => console.error(err));
  };

  const handleImportSelectedCompanies = () => {
    if (!selectedNewsletter) return;
    const ids = Object.keys(selectedCompanyIds).filter((k) => selectedCompanyIds[k]);
    if (ids.length === 0) return;
    setImportingCompanies(true);
    api.addNewsletterSubscribersFromCompanies(selectedNewsletter.id, ids)
      .then((res) => {
        setImportingCompanies(false);
        setShowCompanyImport(false);
        setSelectedCompanyIds({});
        fetchNewsletterDetails(selectedNewsletter);
      })
      .catch((err) => {
        setImportingCompanies(false);
        console.error(err);
      });
  };

  // Manual & company email selection for broadcast
  const [recipientTargetMode, setRecipientTargetMode] = useState('subscribers'); // 'subscribers' | 'companies' | 'manual'
  const [manualRecipientEmails, setManualRecipientEmails] = useState('');
  const [selectedBroadcastCompanyIds, setSelectedBroadcastCompanyIds] = useState({});
  const [companySearchQuery, setCompanySearchQuery] = useState('');
  const [companyPage, setCompanyPage] = useState(1);
  const [companyTotalCount, setCompanyTotalCount] = useState(0);
  const [dbCompanies, setDbCompanies] = useState([]);
  const [subscribingUser, setSubscribingUser] = useState(false);
  const [userEmailInput, setUserEmailInput] = useState('');
  const [showSelfSubscribeModal, setShowSelfSubscribeModal] = useState(false);

  const fetchDbCompanies = (q = '', pageNum = 1) => {
    api.getCompanies({ query: q, page: pageNum, limit: 20 })
      .then((res) => {
        setDbCompanies(res?.companies || []);
        setCompanyTotalCount(res?.total || 0);
        setCompanyPage(pageNum);
      })
      .catch((err) => console.error(err));
  };

  const handleSelfSubscribe = (e) => {
    e.preventDefault();
    if (!selectedNewsletter || !userEmailInput.trim()) return;
    setSubscribingUser(true);
    api.addNewsletterSubscribersFromCompanies(selectedNewsletter.id, [], userEmailInput.trim())
      .then(() => {
        setSubscribingUser(false);
        setShowSelfSubscribeModal(false);
        setUserEmailInput('');
        fetchNewsletterDetails(selectedNewsletter);
      })
      .catch((err) => {
        setSubscribingUser(false);
        setMessage(err.message || 'Failed to subscribe user');
      });
  };

  useEffect(() => {
    if (showComposeModal || showCompanyImport) {
      const timer = setTimeout(() => fetchDbCompanies(companySearchQuery, 1), 250);
      return () => clearTimeout(timer);
    }
  }, [companySearchQuery, showComposeModal, showCompanyImport]);

  const openBroadcastModal = () => {
    setEditingEditionId(null);
    setEditionForm({ subject: '', body: '', imageUrl: '', sendNow: true });
    setShowComposeModal(true);
    fetchDbCompanies(companySearchQuery, 1);
  };

  const handleEditEdition = (edition) => {
    setEditingEditionId(edition.id);
    setEditionForm({
      subject: edition.subject,
      body: edition.body,
      imageUrl: edition.imageUrl || '',
      sendNow: edition.status === 'sent' ? false : edition.sendNow,
    });
    setShowComposeModal(true);
  };

  const handleNewsletterImageUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingImage(true);
    try {
      const res = await api.uploadNewsletterImage(file);
      setEditionForm(prev => ({ ...prev, imageUrl: res.imageUrl }));
    } catch (err) {
      alert(err.message || 'Image upload failed.');
    } finally {
      setUploadingImage(false);
    }
  };

  const handleDeleteEdition = async (editionId) => {
    if (!window.confirm("Are you sure you want to delete this broadcast edition? This will remove its history and tracking stats.")) return;
    try {
      await api.deleteNewsletterEdition(editionId);
      if (selectedNewsletter) {
        fetchNewsletterDetails(selectedNewsletter);
      }
    } catch (err) {
      alert("Failed to delete edition: " + err.message);
    }
  };

  const triggerCompanyResearch = async (name) => {
    try {
      await api.triggerResearch(name);
      fetchDbCompanies(companySearchQuery, companyPage);
    } catch (err) {
      alert("Failed to start research: " + err.message);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Newsletter Publications & Broadcasting"
        subtitle="Manage recurring publications, global subscriber lists, and broadcast issue distributions"
        action={
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-bold text-navy-900 shadow-soft hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white"
            >
              <Plus size={15} /> New Publication
            </button>
            {selectedNewsletter && (
              <button
                onClick={openBroadcastModal}
                className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-xs font-bold text-white shadow-soft hover:bg-brand-600 transition-colors"
              >
                <Send size={15} /> Send Broadcast Edition
              </button>
            )}
          </div>
        }
      />

      {/* Explanatory Guide Box: Publication vs Broadcasting */}
      <div className="rounded-2xl border border-brand-200 bg-gradient-to-r from-brand-50/80 via-white to-slate-50 p-5 dark:border-navy-700 dark:from-navy-800 dark:to-navy-900">
        <div className="flex items-start justify-between gap-4">
          <div className="flex gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-500 text-white shadow-soft">
              <Sparkles size={20} />
            </div>
            <div>
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">Publication & Broadcasting Guide</h3>
              <p className="mt-1 text-xs leading-relaxed text-slate-600 dark:text-slate-300">
                <strong className="text-brand-600 dark:text-brand-400">Publication:</strong> A recurring newsletter series or thematic channel (e.g., <em>Federal Tech Digest</em>). Users & companies subscribe to publications to receive regular market news.<br/>
                <strong className="text-brand-600 dark:text-brand-400">Broadcasting & Editions:</strong> Creating an issue (edition) and sending it out to your global subscriber list, multi-selected company emails, or manual email recipients.
              </p>
            </div>
          </div>
          {selectedNewsletter && (
            <button
              onClick={() => setShowSelfSubscribeModal(true)}
              className="shrink-0 flex items-center gap-1.5 rounded-xl bg-emerald-600 px-3.5 py-2 text-xs font-bold text-white shadow-soft hover:bg-emerald-700 transition-colors"
            >
              <Users size={14} /> Subscribe Contact / Company
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <Card className="flex flex-col items-center justify-center py-20">
          <Loader2 className="animate-spin text-brand-500" size={32} />
          <p className="mt-4 text-sm font-medium text-slate-500">Loading publication list...</p>
        </Card>
      ) : newsletters.length === 0 ? (
        <Card className="flex flex-col items-center justify-center py-16 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 dark:bg-navy-800 dark:text-brand-400">
            <Mail size={28} />
          </div>
          <h3 className="mt-4 text-base font-bold text-navy-900 dark:text-white">No Newsletter Publications</h3>
          <p className="mt-1 max-w-sm text-xs text-slate-500 dark:text-slate-400">Create your first newsletter broadcast series to start building subscriber lists and sending regular market updates.</p>
          <button
            onClick={() => setShowCreateModal(true)}
            className="mt-5 flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white shadow-soft hover:bg-brand-600"
          >
            <Plus size={15} /> Create Newsletter
          </button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
          {/* Left Column: Publication selector list */}
          <div className="space-y-3 lg:col-span-1">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Your Publications</h3>
            {newsletters.map((nl) => {
              const isSelected = selectedNewsletter?.id === nl.id;
              return (
                <div
                  key={nl.id}
                  onClick={() => setSelectedNewsletter(nl)}
                  className={`cursor-pointer rounded-2xl border p-4 transition-all ${
                    isSelected
                      ? 'border-brand-500 bg-brand-50/50 shadow-soft dark:border-brand-400 dark:bg-navy-800'
                      : 'border-slate-200 bg-white hover:border-slate-300 dark:border-navy-700 dark:bg-navy-900'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-bold text-navy-900 dark:text-white truncate pr-2">{nl.name}</h4>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className="rounded-full bg-brand-100 px-2 py-0.5 text-[10px] font-bold text-brand-700 dark:bg-navy-700 dark:text-brand-300">
                        {nl.stats?.totalSubscribers || 0} subs
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteNewsletter(nl.id);
                        }}
                        className="rounded-lg p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/40 transition-colors"
                        title="Delete Publication"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{nl.description || 'No description provided.'}</p>
                </div>
              );
            })}
          </div>

          {/* Right Column: Selected Publication Details */}
          <div className="space-y-6 lg:col-span-3">
            {selectedNewsletter && (
              <>
                {/* Stats Header */}
                <div className="grid grid-cols-3 gap-4">
                  <Card className="flex items-center gap-4">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-50 text-violet-600 dark:bg-violet-950/30 dark:text-violet-400">
                      <Users size={20} />
                    </div>
                    <div>
                      <p className="text-[11px] font-medium text-slate-400">Subscribers</p>
                      <p className="text-lg font-bold text-navy-900 dark:text-white">{selectedNewsletter.stats?.totalSubscribers || 0}</p>
                    </div>
                  </Card>

                  <Card className="flex items-center gap-4">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600 dark:bg-emerald-950/30 dark:text-emerald-400">
                      <Send size={20} />
                    </div>
                    <div>
                      <p className="text-[11px] font-medium text-slate-400">Total Sent</p>
                      <p className="text-lg font-bold text-navy-900 dark:text-white">{selectedNewsletter.stats?.totalSent || 0}</p>
                    </div>
                  </Card>

                  <Card className="flex items-center gap-4">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-50 text-amber-600 dark:bg-amber-950/30 dark:text-amber-400">
                      <Sparkles size={20} />
                    </div>
                    <div>
                      <p className="text-[11px] font-medium text-slate-400">Editions Broadcast</p>
                      <p className="text-lg font-bold text-navy-900 dark:text-white">{editions.length}</p>
                    </div>
                  </Card>
                </div>

                {/* Tabs */}
                <div className="flex items-center justify-between border-b border-slate-200 dark:border-navy-700 pb-2">
                  <div className="flex gap-4">
                    <button
                      onClick={() => setActiveTab('editions')}
                      className={`text-xs font-bold pb-2 border-b-2 transition-all ${
                        activeTab === 'editions' ? 'border-brand-500 text-brand-600 dark:text-brand-400' : 'border-transparent text-slate-400'
                      }`}
                    >
                      Past Broadcast Editions ({editions.length})
                    </button>
                    <button
                      onClick={() => setActiveTab('subscribers')}
                      className={`text-xs font-bold pb-2 border-b-2 transition-all ${
                        activeTab === 'subscribers' ? 'border-brand-500 text-brand-600 dark:text-brand-400' : 'border-transparent text-slate-400'
                      }`}
                    >
                      Subscriber List ({subscribers.length})
                    </button>
                  </div>

                  {activeTab === 'subscribers' && (
                    <button
                      onClick={openCompanyImport}
                      className="flex items-center gap-1.5 rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-200 dark:bg-navy-800 dark:text-white"
                    >
                      <Building2 size={14} /> Import from Companies
                    </button>
                  )}
                </div>

                {/* Tab Content */}
                {activeTab === 'editions' ? (
                  <div className="space-y-4">
                    {editions.length === 0 ? (
                      <Card className="py-12 text-center text-xs text-slate-400">
                        No broadcast editions sent yet. Click "Send Broadcast Edition" above to send your first newsletter issue.
                      </Card>
                    ) : (
                      editions.map((e) => (
                        <Card key={e.id} className="p-5">
                          <div className="flex items-center justify-between">
                            <h4 className="text-sm font-bold text-navy-900 dark:text-white">{e.subject}</h4>
                            <div className="flex items-center gap-2">
                              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-bold text-emerald-600 dark:bg-emerald-950/30 dark:text-emerald-400">
                                {e.stats?.sent || 0} Delivered
                              </span>
                              <button
                                onClick={() => handleEditEdition(e)}
                                className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-navy-800 transition-colors"
                                title="Edit Edition"
                              >
                                <Edit2 size={13} />
                              </button>
                              <button
                                onClick={() => handleDeleteEdition(e.id)}
                                className="rounded-lg p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/40 transition-colors"
                                title="Delete Edition"
                              >
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </div>
                          <p className="mt-2 line-clamp-3 text-xs text-slate-600 dark:text-slate-300 font-mono bg-slate-50 dark:bg-navy-900 p-3 rounded-xl whitespace-pre-wrap">{e.body}</p>
                          <div className="mt-3 flex items-center justify-between text-[11px] text-slate-400">
                            <span>Status: {e.status}</span>
                            <span>Sent at: {e.sentAt || 'N/A'}</span>
                          </div>
                        </Card>
                      ))
                    )}
                  </div>
                ) : (
                  <Card className="!p-0 overflow-hidden">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-50 dark:bg-navy-800 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        <tr>
                          <th className="p-3.5">Email</th>
                          <th className="p-3.5">Contact Name</th>
                          <th className="p-3.5">Company</th>
                          <th className="p-3.5">Source</th>
                          <th className="p-3.5">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-navy-800">
                        {subscribers.length === 0 ? (
                          <tr>
                            <td colSpan={5} className="p-6 text-center text-slate-400">No subscribers enrolled in this publication list yet.</td>
                          </tr>
                        ) : (
                          subscribers.map((s) => (
                            <tr key={s.id}>
                              <td className="p-3.5 font-medium text-navy-900 dark:text-white">{s.email}</td>
                              <td className="p-3.5 text-slate-500 dark:text-slate-400">{s.contactName || '—'}</td>
                              <td className="p-3.5 text-slate-500 dark:text-slate-400">{s.companyName || '—'}</td>
                              <td className="p-3.5 text-slate-400 uppercase text-[10px]">{s.source}</td>
                              <td className="p-3.5">
                                <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${s.status === 'subscribed' ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'}`}>
                                  {s.status}
                                </span>
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </Card>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* Modal: Create Publication */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-900/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl dark:bg-navy-800">
            <h3 className="text-base font-bold text-navy-900 dark:text-white">Create Publication Series</h3>
            <form onSubmit={handleCreateNewsletter} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1">Publication Name *</label>
                <input
                  required
                  value={newNewsletterForm.name}
                  onChange={(e) => setNewNewsletterForm({ ...newNewsletterForm, name: e.target.value })}
                  placeholder="e.g. Defense IT Weekly Digest"
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none focus:border-brand-500 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1">Description</label>
                <textarea
                  rows={3}
                  value={newNewsletterForm.description}
                  onChange={(e) => setNewNewsletterForm({ ...newNewsletterForm, description: e.target.value })}
                  placeholder="Brief outline of what content this broadcast newsletter provides."
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none focus:border-brand-500 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>
              <div className="flex justify-end gap-3 pt-3">
                <button type="button" onClick={() => setShowCreateModal(false)} className="rounded-xl border px-4 py-2 text-xs font-semibold">Cancel</button>
                <button type="submit" disabled={submitting} className="rounded-xl bg-brand-500 px-4 py-2 text-xs font-bold text-white">{submitting ? <Loader2 className="animate-spin" size={14} /> : 'Create'}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Broadcast Issue Edition */}
      {showComposeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-900/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-xl rounded-2xl bg-white p-6 shadow-2xl dark:bg-navy-800 max-h-[90vh] flex flex-col overflow-y-auto">
            <h3 className="text-base font-bold text-navy-900 dark:text-white">
              {editingEditionId ? 'Edit Broadcast Edition' : 'Broadcast Newsletter Issue'}
            </h3>
            <p className="mt-1 text-xs text-slate-400">
              {editingEditionId 
                ? 'Update the subject or body content of this broadcast publication edition.'
                : 'Target your publication to active subscribers, multi-selected company emails, or manual email addresses.'}
            </p>

            <form onSubmit={handleSendEdition} className="mt-4 space-y-4">
              {/* Recipient Mode Selection */}
              {!editingEditionId && (
                <div>
                  <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1">Target Recipients</label>
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      type="button"
                      onClick={() => setRecipientTargetMode('subscribers')}
                      className={`rounded-xl border px-3 py-2 text-xs font-semibold transition-all ${
                        recipientTargetMode === 'subscribers'
                          ? 'border-brand-500 bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400'
                          : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-700'
                      }`}
                    >
                      All Subscribers ({subscribers.length})
                    </button>
                    <button
                      type="button"
                      onClick={() => setRecipientTargetMode('companies')}
                      className={`rounded-xl border px-3 py-2 text-xs font-semibold transition-all ${
                        recipientTargetMode === 'companies'
                          ? 'border-brand-500 bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400'
                          : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-700'
                      }`}
                    >
                      Select Company Emails
                    </button>
                    <button
                      type="button"
                      onClick={() => setRecipientTargetMode('manual')}
                      className={`rounded-xl border px-3 py-2 text-xs font-semibold transition-all ${
                        recipientTargetMode === 'manual'
                          ? 'border-brand-500 bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400'
                          : 'border-slate-200 text-slate-500 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-700'
                      }`}
                    >
                      Manual Email(s)
                    </button>
                  </div>
                </div>
              )}

              {/* Conditional Recipient Inputs */}
              {!editingEditionId && recipientTargetMode === 'companies' && (
                <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-3 space-y-2 dark:border-navy-700 dark:bg-navy-900/50">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-navy-900 dark:text-white">Multi-Select Registered Companies</label>
                    <span className="text-[11px] font-bold text-brand-600">{Object.values(selectedBroadcastCompanyIds).filter(Boolean).length} Selected</span>
                  </div>
                  <div className="relative">
                    <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      value={companySearchQuery}
                      onChange={(e) => setCompanySearchQuery(e.target.value)}
                      placeholder="Search company by name or email..."
                      className="w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 py-1.5 text-xs text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                    />
                  </div>
                  <div className="max-h-40 overflow-y-auto rounded-lg border border-slate-200 bg-white dark:border-navy-700 dark:bg-navy-900 divide-y divide-slate-50 dark:divide-navy-800">
                    {dbCompanies
                      .filter(c => !companySearchQuery || (c.name || '').toLowerCase().includes(companySearchQuery.toLowerCase()))
                      .map((c) => {
                        const key = c.uei || c.name;
                        const hasEmail = !!c.email;
                        const isResearching = c.isResearching;
                        return (
                          <label key={key} className="flex items-center justify-between p-2.5 hover:bg-slate-50 dark:hover:bg-navy-800 cursor-pointer">
                            <div>
                              <p className="text-xs font-bold text-navy-900 dark:text-white">{c.name}</p>
                              <p className="text-[11px] text-slate-400">
                                {c.email || (isResearching ? '⏳ Research in progress...' : '❌ No email (requires research)')}
                              </p>
                            </div>
                            {hasEmail ? (
                              <input
                                type="checkbox"
                                checked={!!selectedBroadcastCompanyIds[key]}
                                onChange={(e) => setSelectedBroadcastCompanyIds({ ...selectedBroadcastCompanyIds, [key]: e.target.checked })}
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
                      })}
                  </div>
                  <div className="flex items-center justify-between pt-1 text-xs">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        disabled={companyPage <= 1}
                        onClick={() => fetchDbCompanies(companySearchQuery, companyPage - 1)}
                        className="rounded-lg border border-slate-200 px-2.5 py-1 font-semibold text-slate-600 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-300 dark:hover:bg-navy-800 disabled:opacity-40 text-[11px]"
                      >
                        Prev
                      </button>
                      <span className="text-[11px] text-slate-500">
                        Pg {companyPage}/{Math.max(1, Math.ceil(companyTotalCount / 20))} ({companyTotalCount.toLocaleString()} total)
                      </span>
                      <button
                        type="button"
                        disabled={companyPage >= Math.ceil(companyTotalCount / 20)}
                        onClick={() => fetchDbCompanies(companySearchQuery, companyPage + 1)}
                        className="rounded-lg border border-slate-200 px-2.5 py-1 font-semibold text-slate-600 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-300 dark:hover:bg-navy-800 disabled:opacity-40 text-[11px]"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {!editingEditionId && recipientTargetMode === 'manual' && (
                <div className="rounded-xl border border-slate-100 bg-slate-50/50 p-3 dark:border-navy-700 dark:bg-navy-900/50">
                  <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1">Enter Email Addresses (Comma Separated)</label>
                  <input
                    type="text"
                    value={manualRecipientEmails}
                    onChange={(e) => setManualRecipientEmails(e.target.value)}
                    placeholder="e.g. executive@client.com, director@orbit.com"
                    className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none focus:border-brand-500 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1">Email Subject *</label>
                <input
                  required
                  value={editionForm.subject}
                  onChange={(e) => setEditionForm({ ...editionForm, subject: e.target.value })}
                  placeholder="e.g. September Edition: Federal AI & Cloud Contracting Opportunities"
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none focus:border-brand-500 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1">Header Banner Image (Optional)</label>
                <div className="flex items-center gap-3">
                  <input
                    type="file"
                    accept="image/*"
                    id="newsletter-image-upload"
                    onChange={handleNewsletterImageUpload}
                    className="hidden"
                  />
                  <label
                    htmlFor="newsletter-image-upload"
                    className="flex cursor-pointer items-center gap-1.5 rounded-xl border border-slate-200 dark:border-navy-700 px-4 py-2.5 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-navy-700 transition-all"
                  >
                    {uploadingImage ? (
                      <Loader2 className="animate-spin text-brand-500" size={14} />
                    ) : (
                      <Image size={14} className="text-slate-400" />
                    )}
                    Upload Image
                  </label>
                  {editionForm.imageUrl && (
                    <div className="flex items-center gap-2 text-xs text-brand-600 font-semibold bg-brand-50 dark:bg-brand-500/10 px-3 py-1.5 rounded-xl">
                      <span>✓ Banner Attached</span>
                      <button
                        type="button"
                        onClick={() => setEditionForm(prev => ({ ...prev, imageUrl: '' }))}
                        className="text-slate-400 hover:text-red-500"
                        title="Remove banner"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  )}
                </div>
                {editionForm.imageUrl && (
                  <div className="mt-2 rounded-xl overflow-hidden border border-slate-100 dark:border-navy-700 max-h-24 flex items-center bg-slate-50/50 dark:bg-navy-900/30 p-2">
                    <img
                      src={`${BASE_URL}/api/newsletters/images/${editionForm.imageUrl}`}
                      alt="Banner Preview"
                      className="max-h-20 w-auto rounded object-contain"
                    />
                  </div>
                )}
              </div>
              <div>
                <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1">Newsletter Content *</label>
                <textarea
                  required
                  rows={6}
                  value={editionForm.body}
                  onChange={(e) => setEditionForm({ ...editionForm, body: e.target.value })}
                  placeholder="Write your newsletter edition broadcast text here..."
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs font-mono outline-none focus:border-brand-500 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>
              <div className="flex justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => setShowComposeModal(false)}
                  className="rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-300 dark:hover:bg-navy-900 px-4 py-2 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="flex items-center gap-1.5 rounded-xl bg-brand-500 px-5 py-2 text-xs font-bold text-white shadow-soft hover:bg-brand-600 disabled:opacity-60"
                >
                  {submitting ? (
                    <Loader2 className="animate-spin" size={14} />
                  ) : editingEditionId ? (
                    <Edit2 size={14} />
                  ) : (
                    <Send size={14} />
                  )}
                  {editingEditionId ? 'Update Broadcast' : 'Send Broadcast'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Subscribe Contact / Company */}
      {showSelfSubscribeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-900/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl dark:bg-navy-800">
            <h3 className="text-base font-bold text-navy-900 dark:text-white">Add Contact to {selectedNewsletter?.name}</h3>
            <p className="mt-1 text-xs text-slate-400">Subscribe an external client contact or enterprise email to receive all broadcast issues.</p>
            <form onSubmit={handleSelfSubscribe} className="mt-4 space-y-4">
              <div>
                <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1">Subscriber Email Address *</label>
                <input
                  type="email"
                  required
                  value={userEmailInput}
                  onChange={(e) => setUserEmailInput(e.target.value)}
                  placeholder="contact@clientcompany.com"
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs outline-none focus:border-brand-500 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowSelfSubscribeModal(false)}
                  className="rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-300 dark:hover:bg-navy-900 px-4 py-2 text-xs font-semibold"
                >
                  Cancel
                </button>
                <button type="submit" disabled={subscribingUser} className="flex items-center gap-1.5 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-soft hover:bg-emerald-700">
                  {subscribingUser ? <Loader2 className="animate-spin" size={14} /> : <Check size={14} />} Subscribe Contact
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Import from Companies */}
      {showCompanyImport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-900/60 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-navy-800 max-h-[80vh] flex flex-col">
            <h3 className="text-base font-bold text-navy-900 dark:text-white">Import Companies to Newsletter List</h3>
            <p className="mt-1 text-xs text-slate-500">Search and select registered prospect companies to add to {selectedNewsletter?.name}:</p>
            
            <div className="relative mt-3">
              <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={companySearchQuery}
                onChange={(e) => setCompanySearchQuery(e.target.value)}
                placeholder="Search registered companies by name or email..."
                className="w-full rounded-xl border border-slate-200 pl-9 pr-3 py-2 text-xs outline-none focus:border-brand-500 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
              />
            </div>

            <div className="mt-3 flex-1 overflow-y-auto divide-y divide-slate-100 dark:divide-navy-700 pr-2">
              {dbCompanies.map((c) => {
                const key = c.uei || c.name;
                const hasEmail = !!c.email;
                const isResearching = c.isResearching;
                return (
                  <label key={key} className="flex items-center justify-between p-3 hover:bg-slate-50 dark:hover:bg-navy-700/50 cursor-pointer">
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-xs font-bold text-navy-900 dark:text-white">{c.name}</p>
                        {(c.hasResearchedProfile || c.is_researched) && (
                          <span className="inline-flex items-center rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 px-1.5 py-0.2 text-[9px] font-extrabold">
                            Researched
                          </span>
                        )}
                      </div>
                      <p className="text-[11px] text-slate-400">
                        {c.email || (isResearching ? '⏳ Research in progress...' : '❌ No email (requires research)')}
                      </p>
                    </div>
                    {hasEmail ? (
                      <input
                        type="checkbox"
                        checked={!!selectedCompanyIds[key]}
                        onChange={(e) => setSelectedCompanyIds({ ...selectedCompanyIds, [key]: e.target.checked })}
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
              })}
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-slate-100 dark:border-navy-700 text-xs">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={companyPage <= 1}
                  onClick={() => fetchDbCompanies(companySearchQuery, companyPage - 1)}
                  className="rounded-lg border border-slate-200 px-2.5 py-1 font-semibold text-slate-600 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-300 dark:hover:bg-navy-800 disabled:opacity-40 text-[11px]"
                >
                  Prev
                </button>
                <span className="text-[11px] text-slate-500 font-medium">
                  Page {companyPage} of {Math.max(1, Math.ceil(companyTotalCount / 20))} ({companyTotalCount.toLocaleString()} total)
                </span>
                <button
                  type="button"
                  disabled={companyPage >= Math.ceil(companyTotalCount / 20)}
                  onClick={() => fetchDbCompanies(companySearchQuery, companyPage + 1)}
                  className="rounded-lg border border-slate-200 px-2.5 py-1 font-semibold text-slate-600 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-300 dark:hover:bg-navy-800 disabled:opacity-40 text-[11px]"
                >
                  Next
                </button>
              </div>
              <span className="font-bold text-brand-600 dark:text-brand-400">
                {Object.values(selectedCompanyIds).filter(Boolean).length} Selected
              </span>
            </div>

            <div className="flex justify-end gap-3 pt-3">
              <button
                type="button"
                onClick={() => setShowCompanyImport(false)}
                className="rounded-xl border border-slate-200 text-slate-700 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-300 dark:hover:bg-navy-900 px-4 py-2 text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleImportSelectedCompanies}
                disabled={importingCompanies}
                className="rounded-xl bg-brand-500 px-5 py-2 text-xs font-bold text-white shadow-soft hover:bg-brand-600 disabled:opacity-60"
              >
                {importingCompanies ? <Loader2 className="animate-spin" size={14} /> : 'Import Selected'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
