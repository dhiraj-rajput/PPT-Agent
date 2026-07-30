import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Search, Plus, Eye, X, Upload, Check, Loader2 } from 'lucide-react';
import { PageHeader, Card, StatusBadge, renderSafeText } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';

const EMPTY_PERSON = {
  source: 'Manual Entry',
  status: 'Pending',
  organization_name: '',
  first_name: '',
  last_name: '',
  title: '',
  function_name: '',
  seniority: '',
  email: '',
  email_status: '',
  email_confidence: '',
  phone: '',
  linkedin_url: '',
  city: '',
  state: '',
  country: '',
  job_start_date: '',
};

const SOURCE_CHOICES = ['Apollo', 'LinkedIn', 'CSV Import', 'Excel Import', 'Manual Entry'];
const STATUS_CHOICES = ['Pending', 'Processing', 'Completed', 'Failed', 'Duplicate'];

export default function People() {
  const { createAlert } = useNotifications();
  const notify = (title, message, link) => createAlert(title, message, link).catch(() => {});

  // Query & Filter States
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('All');
  const [sourceFilter, setSourceFilter] = useState('All');
  const [countryFilter, setCountryFilter] = useState('All');
  const [sourceOptions, setSourceOptions] = useState([]);
  const [countryOptions, setCountryOptions] = useState([]);

  // Data States
  const [allPeople, setAllPeople] = useState([]);
  const [totalPeople, setTotalPeople] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const itemsPerPage = 20;

  // Add/Import Modal States
  const [showAddModal, setShowAddModal] = useState(false);
  const [activeTab, setActiveTab] = useState('manual'); // 'manual' | 'import'
  const [manualForm, setManualForm] = useState({ ...EMPTY_PERSON });
  const [selectedFile, setSelectedFile] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  const debounceRef = useRef(null);

  // Fetch people dynamically from FastAPI backend
  const fetchPeople = (searchQuery = query) => {
    setLoading(true);
    const params = {
      page: currentPage.toString(),
      limit: itemsPerPage.toString(),
    };
    if (searchQuery) params.query = searchQuery;
    if (statusFilter !== 'All') params.status = statusFilter;
    if (sourceFilter !== 'All') params.source = sourceFilter;
    if (countryFilter !== 'All') params.country = countryFilter;

    api.getPeople(params)
      .then((data) => {
        setAllPeople(data.people || []);
        setTotalPeople(data.total || 0);
        if (data.source_options) setSourceOptions(data.source_options);
        if (data.country_options) setCountryOptions(data.country_options);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error fetching people:', err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchPeople();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, statusFilter, sourceFilter, countryFilter]);

  useEffect(() => {
    setCurrentPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, statusFilter, sourceFilter, countryFilter]);

  const pageCount = Math.ceil(totalPeople / itemsPerPage);

  // ---------------- Manual single-record submit ----------------
  const handleManualSubmit = (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitError(null);

    api.addPerson(manualForm)
      .then(() => {
        setIsSubmitting(false);
        setShowAddModal(false);
        setManualForm({ ...EMPTY_PERSON });
        fetchPeople();
        notify('Contact added', `${manualForm.full_name || manualForm.first_name || 'A new contact'} was added.`, '/people');
      })
      .catch((err) => {
        setIsSubmitting(false);
        setSubmitError(err.message);
      });
  };



  // ---------------- CSV/Excel import submit ----------------
  const handleImportSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      if (!selectedFile) throw new Error('Please select a CSV or Excel file to upload');
      const res = await api.importPeople({ data: selectedFile });
      setIsSubmitting(false);
      setShowAddModal(false);
      setSelectedFile(null);
      fetchPeople();
      notify('Contacts imported', `${res.count ?? 0} contacts imported from file.`, '/people');
    } catch (err) {
      setIsSubmitting(false);
      setSubmitError(err.message || 'Import failed');
    }
  };

  const inputClass = "w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white";
  const labelClass = "block text-xs font-bold text-navy-900 dark:text-white mb-1.5";

  return (
    <div>
      <PageHeader
        title="People"
        subtitle={`${totalPeople.toLocaleString()} contacts in your directory`}
        action={
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft hover:bg-brand-600 transition-colors"
          >
            <Plus size={16} /> Add Person
          </button>
        }
      />

      {/* Filters Bar */}
      <Card className="!p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-1 min-w-[280px] items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 dark:border-navy-700 dark:bg-navy-800">
            <Search size={16} className="text-slate-400 dark:text-slate-500" />
            <input
              value={query}
              onChange={(e) => {
                const val = e.target.value;
                setQuery(val);
                if (debounceRef.current) clearTimeout(debounceRef.current);
                debounceRef.current = setTimeout(() => fetchPeople(val), 400);
              }}
              placeholder="Search by name, email, organization, title, or phone..."
              className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500 dark:text-white"
            />
            {query && (
              <button onClick={() => setQuery('')} className="rounded-full p-0.5 text-slate-400 hover:text-rose-500" title="Clear search">
                <X size={14} />
              </button>
            )}
          </div>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white cursor-pointer"
          >
            <option value="All">All Statuses</option>
            {STATUS_CHOICES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>

          {/* Source Filter */}
          <select
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white cursor-pointer"
          >
            <option value="All">All Sources</option>
            {(sourceOptions.length ? sourceOptions : SOURCE_CHOICES).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>

          {/* Country Filter */}
          <select
            value={countryFilter}
            onChange={(e) => setCountryFilter(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white max-w-xs cursor-pointer truncate"
          >
            <option value="All">All Countries</option>
            {countryOptions.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </Card>

      {/* Main Table & Card List */}
      {loading ? (
        <Card className="flex flex-col items-center justify-center py-20 mt-5">
          <Loader2 className="animate-spin text-brand-500" size={32} />
          <p className="mt-4 text-sm text-slate-500 dark:text-slate-400 font-medium">Loading people from database...</p>
        </Card>
      ) : (
        <Card className="mt-5 !p-0 overflow-hidden">
          {/* Desktop Table View */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-400 dark:border-navy-800 dark:text-slate-400">
                  <th className="px-5 py-3 font-semibold w-[24%] min-w-[220px]">Person</th>
                  <th className="px-5 py-3 font-semibold">Organization</th>
                  <th className="px-5 py-3 font-semibold">Contact</th>
                  <th className="px-5 py-3 font-semibold">Location</th>
                  <th className="px-5 py-3 font-semibold">Seniority</th>
                  <th className="px-5 py-3 font-semibold">Source</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold"></th>
                </tr>
              </thead>
              <tbody>
                {allPeople.map((p) => (
                  <tr key={p.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60 dark:border-navy-800/40 dark:hover:bg-navy-800/40">
                    <td className="px-5 py-3.5 w-[24%] min-w-[220px]">
                      <Link to={`/people/${p.id}`} className="flex items-center gap-3">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-xs font-bold text-brand-600 dark:bg-navy-900 dark:text-brand-400 aspect-square">
                          {(p.full_name || '??').slice(0, 2).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-bold text-navy-900 hover:text-brand-600 dark:text-white dark:hover:text-brand-400 leading-tight text-sm">
                            {p.full_name || 'Unnamed Contact'}
                          </p>
                          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">{p.title || '—'}</p>
                        </div>
                      </Link>
                    </td>
                    <td className="px-5 py-3.5 text-slate-600 dark:text-slate-300 text-xs">
                      {renderSafeText(p.organization_name)}
                    </td>
                    <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400 text-xs">
                      <p className="truncate max-w-[200px]" title={p.email}>{p.email || '—'}</p>
                      <p className="text-slate-400 mt-0.5">{p.phone || ''}</p>
                    </td>
                    <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400 text-xs">
                      {renderSafeText(p.city && p.country ? `${p.city}, ${p.country}` : p.city || p.country)}
                    </td>
                    <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400 text-xs">
                      {renderSafeText(p.seniority)}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] font-semibold text-slate-600 dark:bg-navy-800 dark:text-slate-300 whitespace-nowrap">
                        {p.source || '—'}
                      </span>
                    </td>
                    <td className="px-5 py-3.5"><StatusBadge status={p.status} /></td>
                    <td className="px-5 py-3.5">
                      <Link to={`/people/${p.id}`} className="text-slate-400 hover:text-brand-600 dark:hover:text-brand-400">
                        <Eye size={16} />
                      </Link>
                    </td>
                  </tr>
                ))}
                {allPeople.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-5 py-10 text-center text-slate-400 dark:text-slate-500">
                      No people match your search and filter criteria.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Mobile Card List View */}
          <div className="block md:hidden divide-y divide-slate-100 dark:divide-navy-800">
            {allPeople.map((p) => (
              <div key={p.id} className="p-4 space-y-3 hover:bg-slate-50/40 dark:hover:bg-navy-800/40 transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <Link to={`/people/${p.id}`} className="flex gap-2.5 min-w-0">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-xs font-bold text-brand-600 dark:bg-navy-850 dark:text-brand-400 aspect-square">
                      {(p.full_name || '??').slice(0, 2).toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <p className="font-bold text-navy-900 hover:text-brand-600 dark:text-white dark:hover:text-brand-400 leading-snug text-sm">
                        {p.full_name || 'Unnamed Contact'}
                      </p>
                      <p className="text-xs text-slate-400 mt-0.5 truncate">{p.title || 'No title listed'}</p>
                    </div>
                  </Link>
                  <StatusBadge status={p.status} />
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px] bg-slate-50 dark:bg-navy-950 p-2 rounded-xl border border-slate-100/50 dark:border-navy-800/40">
                  <div className="col-span-2">
                    <span className="text-slate-400 block">Organization</span>
                    <span className="font-semibold text-slate-700 dark:text-slate-300">{p.organization_name || '—'}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block">Email</span>
                    <span className="font-mono text-slate-700 dark:text-slate-300 truncate block">{p.email || '—'}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block">Phone</span>
                    <span className="font-mono text-slate-700 dark:text-slate-300">{p.phone || '—'}</span>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2.5 pt-1.5">
                  <span className="text-[11px] text-slate-400">
                    {renderSafeText(p.city && p.country ? `${p.city}, ${p.country}` : p.city || p.country)}
                  </span>
                  <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-semibold text-slate-500 dark:bg-navy-800 dark:text-slate-400">
                    {p.source || '—'}
                  </span>
                </div>
              </div>
            ))}
            {allPeople.length === 0 && (
              <div className="p-8 text-center text-slate-400 dark:text-slate-500">
                No people match your search and filter criteria.
              </div>
            )}
          </div>

          {/* Pagination */}
          {pageCount > 1 && (
            <div className="flex items-center justify-between border-t border-slate-100 p-4 dark:border-navy-800">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Showing <span className="font-semibold text-navy-900 dark:text-white">{totalPeople === 0 ? 0 : (currentPage - 1) * itemsPerPage + 1}</span> to{' '}
                <span className="font-semibold text-navy-900 dark:text-white">{Math.min(currentPage * itemsPerPage, totalPeople)}</span>{' '}
                of <span className="font-semibold text-navy-900 dark:text-white">{totalPeople.toLocaleString()}</span> people
              </p>
              <div className="flex gap-2 items-center">
                <button
                  disabled={currentPage === 1}
                  onClick={() => { setCurrentPage((p) => p - 1); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 disabled:opacity-50 dark:border-navy-700 dark:text-white dark:hover:bg-navy-750 transition-colors"
                >
                  Previous
                </button>
                <span className="text-xs font-bold text-slate-600 dark:text-slate-400 px-1">{currentPage} / {pageCount}</span>
                <button
                  disabled={currentPage === pageCount}
                  onClick={() => { setCurrentPage((p) => p + 1); window.scrollTo({ top: 0, behavior: 'smooth' }); }}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 disabled:opacity-50 dark:border-navy-700 dark:text-white dark:hover:bg-navy-750 transition-colors"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Add & Import Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4 backdrop-blur-md" onClick={() => setShowAddModal(false)}>
          <div
            className="w-full max-w-3xl rounded-2xl bg-white dark:bg-navy-800 shadow-2xl overflow-hidden border border-slate-100 dark:border-navy-700 flex flex-col max-h-[90vh]"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 p-5 shrink-0 bg-white dark:bg-navy-800">
              <div>
                <h3 className="text-base font-extrabold text-navy-900 dark:text-white">Add People</h3>
                <p className="text-xs text-slate-400 mt-1">Add a single contact manually or import a CSV file</p>
              </div>
              <button onClick={() => setShowAddModal(false)} className="rounded-lg p-2 text-slate-400 hover:text-navy-950 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-navy-900 transition-colors">
                <X size={18} />
              </button>
            </div>

            {/* Modal Tabs */}
            <div className="flex border-b border-slate-100 dark:border-navy-700 bg-slate-50 dark:bg-navy-900 shrink-0">
              {[
                { key: 'manual', label: 'Manual Entry' },
                { key: 'import', label: 'Import CSV' },
              ].map((t) => (
                <button
                  key={t.key}
                  onClick={() => setActiveTab(t.key)}
                  className={`flex-1 py-3 text-xs font-bold border-b-2 transition-colors ${
                    activeTab === t.key
                      ? 'border-brand-500 text-brand-600 dark:text-brand-400 bg-white dark:bg-navy-800'
                      : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-300'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-5">
              {submitError && (
                <div className="mb-4 rounded-xl bg-rose-50 border border-rose-100 p-3 text-xs font-semibold text-rose-600 dark:bg-rose-950/20 dark:border-rose-900/30 dark:text-rose-400">
                  Error: {submitError}
                </div>
              )}

              {/* ---------- Manual Entry ---------- */}
              {activeTab === 'manual' && (
                <form onSubmit={handleManualSubmit} className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className={labelClass}>First Name</label>
                      <input value={manualForm.first_name} onChange={(e) => setManualForm({ ...manualForm, first_name: e.target.value })} placeholder="First Name" className={inputClass} />
                    </div>
                    <div>
                      <label className={labelClass}>Last Name</label>
                      <input value={manualForm.last_name} onChange={(e) => setManualForm({ ...manualForm, last_name: e.target.value })} placeholder="Last Name" className={inputClass} />
                    </div>
                    <div>
                      <label className={labelClass}>Job Title <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input value={manualForm.title} onChange={(e) => setManualForm({ ...manualForm, title: e.target.value })} placeholder="e.g. Product Manager" className={inputClass} />
                    </div>
                    <div>
                      <label className={labelClass}>Organization <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input value={manualForm.organization_name} onChange={(e) => setManualForm({ ...manualForm, organization_name: e.target.value })} placeholder="Company / Organization Name" className={inputClass} />
                    </div>
                  </div>

                  <div className="border-t border-slate-100 dark:border-navy-700 pt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className={labelClass}>Email <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input type="email" value={manualForm.email} onChange={(e) => setManualForm({ ...manualForm, email: e.target.value })} placeholder="Email Address" className={inputClass} />
                    </div>
                    <div>
                      <label className={labelClass}>Phone <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input value={manualForm.phone} onChange={(e) => setManualForm({ ...manualForm, phone: e.target.value })} placeholder="Phone Number" className={inputClass} />
                    </div>
                    <div>
                      <label className={labelClass}>LinkedIn URL <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input value={manualForm.linkedin_url} onChange={(e) => setManualForm({ ...manualForm, linkedin_url: e.target.value })} placeholder="https://linkedin.com/in/..." className={inputClass} />
                    </div>
                    <div>
                      <label className={labelClass}>Seniority <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input value={manualForm.seniority} onChange={(e) => setManualForm({ ...manualForm, seniority: e.target.value })} placeholder="e.g. Senior, Manager, Executive" className={inputClass} />
                    </div>
                  </div>

                  <div className="border-t border-slate-100 dark:border-navy-700 pt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className={labelClass}>City <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input value={manualForm.city} onChange={(e) => setManualForm({ ...manualForm, city: e.target.value })} placeholder="City" className={inputClass} />
                    </div>
                    <div>
                      <label className={labelClass}>State / Province <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input value={manualForm.state} onChange={(e) => setManualForm({ ...manualForm, state: e.target.value })} placeholder="State" className={inputClass} />
                    </div>
                    <div>
                      <label className={labelClass}>Country <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input value={manualForm.country} onChange={(e) => setManualForm({ ...manualForm, country: e.target.value })} placeholder="Country" className={inputClass} />
                    </div>
                  </div>

                  <div className="border-t border-slate-100 dark:border-navy-700 pt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <label className={labelClass}>Source</label>
                      <select value={manualForm.source} onChange={(e) => setManualForm({ ...manualForm, source: e.target.value })} className={`${inputClass} cursor-pointer`}>
                        {SOURCE_CHOICES.map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className={labelClass}>Status</label>
                      <select value={manualForm.status} onChange={(e) => setManualForm({ ...manualForm, status: e.target.value })} className={`${inputClass} cursor-pointer`}>
                        {STATUS_CHOICES.map((s) => <option key={s} value={s}>{s}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className={labelClass}>Job Start Date <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input type="date" value={manualForm.job_start_date} onChange={(e) => setManualForm({ ...manualForm, job_start_date: e.target.value })} className={inputClass} />
                    </div>
                  </div>

                  <div className="flex justify-end gap-3 border-t border-slate-100 dark:border-navy-700 pt-5 mt-5">
                    <button type="button" onClick={() => setShowAddModal(false)} className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700 transition-colors">
                      Cancel
                    </button>
                    <button type="submit" disabled={isSubmitting} className="flex items-center justify-center gap-1.5 rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white shadow-soft hover:bg-brand-600 transition-colors disabled:opacity-75">
                      {isSubmitting ? <Loader2 className="animate-spin" size={14} /> : <Check size={14} />}
                      Save Contact
                    </button>
                  </div>
                </form>
              )}


              {/* ---------- Import CSV ---------- */}
              {activeTab === 'import' && (
                <form onSubmit={handleImportSubmit} className="space-y-4">
                  <div
                    className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 dark:border-navy-600 p-8 text-center cursor-pointer hover:border-brand-400 transition-colors"
                    onClick={() => document.getElementById('people-file-input').click()}
                  >
                    <Upload className="text-slate-300 dark:text-slate-600 mb-2" size={32} />
                    <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">
                      {selectedFile ? selectedFile.name : 'Click to upload a CSV file'}
                    </p>
                    <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Only .csv files are accepted — columns must match the database exactly</p>
                    <input
                      id="people-file-input"
                      type="file"
                      accept=".csv"
                      className="hidden"
                      onChange={(e) => {
                        if (e.target.files && e.target.files[0]) setSelectedFile(e.target.files[0]);
                      }}
                    />
                  </div>

                  <div className="rounded-xl border border-slate-200 dark:border-navy-700 bg-slate-50 dark:bg-navy-900 p-4 text-xs text-slate-500 dark:text-slate-400">
                    <p className="font-bold text-navy-900 dark:text-white mb-2">Required CSV columns (exact names, no extras allowed)</p>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-1 font-mono text-[10px] text-slate-600 dark:text-slate-400">
                      {['source','status','organization_name','first_name','last_name','full_name','title','function_name','seniority','email','email_status','email_confidence','phone','linkedin_url','city','state','country','job_start_date'].map(col => (
                        <span key={col} className="bg-white dark:bg-navy-800 border border-slate-200 dark:border-navy-600 rounded px-1.5 py-0.5">{col}</span>
                      ))}
                    </div>
                    <p className="mt-2 text-rose-500 dark:text-rose-400 font-semibold">⚠ The CSV must have all 18 columns above — no more, no fewer.</p>
                  </div>

                  {submitError && (
                    <div className="rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/30 p-3 text-xs text-red-600 dark:text-red-400">
                      {submitError}
                    </div>
                  )}

                  <div className="flex justify-end gap-3 border-t border-slate-100 dark:border-navy-700 pt-5 mt-5">
                    <button type="button" onClick={() => setShowAddModal(false)} className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700 transition-colors">
                      Cancel
                    </button>
                    <button type="submit" disabled={isSubmitting} className="flex items-center justify-center gap-1.5 rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white shadow-soft hover:bg-brand-600 transition-colors disabled:opacity-75">
                      {isSubmitting ? <Loader2 className="animate-spin" size={14} /> : <Upload size={14} />}
                      Import CSV
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
