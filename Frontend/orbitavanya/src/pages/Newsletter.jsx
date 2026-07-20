import { useState, useEffect } from 'react';
import { Mail, Plus, Users, Send, Check, Loader2, Sparkles, Building2, Search, AlertCircle } from 'lucide-react';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';

export default function Newsletter() {
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
  const [editionForm, setEditionForm] = useState({ subject: '', body: '', sendNow: true });

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
      })
      .catch((err) => {
        setSubmitting(false);
        setMessage(err.message || 'Failed to create newsletter');
      });
  };

  const handleSendEdition = (e) => {
    e.preventDefault();
    if (!selectedNewsletter) return;
    setSubmitting(true);
    api.createNewsletterEdition(selectedNewsletter.id, editionForm)
      .then(() => {
        setSubmitting(false);
        setShowComposeModal(false);
        setEditionForm({ subject: '', body: '', sendNow: true });
        fetchNewsletterDetails(selectedNewsletter);
      })
      .catch((err) => {
        setSubmitting(false);
        setMessage(err.message || 'Failed to send edition');
      });
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

  return (
    <div className="space-y-6">
      <PageHeader
        title="Newsletter Publications"
        subtitle="Manage recurring publications, subscribers, and broadcast issue distributions"
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
                onClick={() => setShowComposeModal(true)}
                className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-xs font-bold text-white shadow-soft hover:bg-brand-600 transition-colors"
              >
                <Send size={15} /> Send Broadcast Edition
              </button>
            )}
          </div>
        }
      />

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
                    <h4 className="text-sm font-bold text-navy-900 dark:text-white">{nl.name}</h4>
                    <span className="rounded-full bg-brand-100 px-2 py-0.5 text-[10px] font-bold text-brand-700 dark:bg-navy-700 dark:text-brand-300">
                      {nl.stats?.totalSubscribers || 0} subs
                    </span>
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
                            <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-bold text-emerald-600 dark:bg-emerald-950/30 dark:text-emerald-400">
                              {e.stats?.sent || 0} Delivered
                            </span>
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
          <div className="w-full max-w-xl rounded-2xl bg-white p-6 shadow-2xl dark:bg-navy-800">
            <h3 className="text-base font-bold text-navy-900 dark:text-white">Broadcast Newsletter Issue</h3>
            <form onSubmit={handleSendEdition} className="mt-4 space-y-4">
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
                <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1">Newsletter Content *</label>
                <textarea
                  required
                  rows={8}
                  value={editionForm.body}
                  onChange={(e) => setEditionForm({ ...editionForm, body: e.target.value })}
                  placeholder="Write your newsletter edition broadcast text here..."
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-xs font-mono outline-none focus:border-brand-500 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                />
              </div>
              <div className="flex justify-end gap-3 pt-3">
                <button type="button" onClick={() => setShowComposeModal(false)} className="rounded-xl border px-4 py-2 text-xs font-semibold">Cancel</button>
                <button type="submit" disabled={submitting} className="flex items-center gap-1.5 rounded-xl bg-brand-500 px-5 py-2 text-xs font-bold text-white">{submitting ? <Loader2 className="animate-spin" size={14} /> : <Send size={14} />} Send Broadcast</button>
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
            <p className="mt-1 text-xs text-slate-500">Select companies from your SAM.gov directory to add to {selectedNewsletter?.name}:</p>
            <div className="mt-4 flex-1 overflow-y-auto divide-y divide-slate-100 dark:divide-navy-700 pr-2">
              {companies.map((c) => (
                <label key={c.id || c.uei} className="flex items-center justify-between p-3 hover:bg-slate-50 dark:hover:bg-navy-700/50 cursor-pointer">
                  <div>
                    <p className="text-xs font-bold text-navy-900 dark:text-white">{c.name}</p>
                    <p className="text-[11px] text-slate-400">{c.email || 'No email registered'}</p>
                  </div>
                  <input
                    type="checkbox"
                    disabled={!c.email}
                    checked={!!selectedCompanyIds[c.id]}
                    onChange={(e) => setSelectedCompanyIds({ ...selectedCompanyIds, [c.id]: e.target.checked })}
                    className="rounded border-slate-300 text-brand-500 focus:ring-brand-500"
                  />
                </label>
              ))}
            </div>
            <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-navy-700 mt-4">
              <button type="button" onClick={() => setShowCompanyImport(false)} className="rounded-xl border px-4 py-2 text-xs font-semibold">Cancel</button>
              <button type="button" onClick={handleImportSelectedCompanies} disabled={importingCompanies} className="rounded-xl bg-brand-500 px-5 py-2 text-xs font-bold text-white">{importingCompanies ? <Loader2 className="animate-spin" size={14} /> : 'Import Selected'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
