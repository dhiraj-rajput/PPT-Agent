import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Search, Plus, Eye, X, Upload, Check, Loader2, Trash2, PlusCircle, AlertTriangle, FileText, Pencil } from 'lucide-react';
import { PageHeader, Card, StatusBadge, renderSafeText } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';

// Exact DB columns — order matters for table display
const REQUIRED_COLS = [
  'source', 'status', 'organization_name',
  'first_name', 'last_name', 'full_name',
  'title', 'function_name', 'seniority',
  'email', 'email_status', 'email_confidence',
  'phone', 'linkedin_url',
  'city', 'state', 'country',
  'job_start_date',
];

const REQUIRED_COLS_SET = new Set(REQUIRED_COLS);

const EMPTY_PERSON = Object.fromEntries(REQUIRED_COLS.map(c => [c, c === 'source' ? 'Manual Entry' : c === 'status' ? 'Pending' : '']));

const SOURCE_CHOICES = ['Apollo', 'LinkedIn', 'CSV Import', 'Excel Import', 'Manual Entry'];
const STATUS_CHOICES = ['Pending', 'Processing', 'Completed', 'Failed', 'Duplicate'];

// Friendly short labels for table column headers
const COL_LABELS = {
  source: 'Source', status: 'Status', organization_name: 'Organization',
  first_name: 'First', last_name: 'Last', full_name: 'Full Name',
  title: 'Title', function_name: 'Function', seniority: 'Seniority',
  email: 'Email', email_status: 'Email Status', email_confidence: 'Confidence',
  phone: 'Phone', linkedin_url: 'LinkedIn', city: 'City',
  state: 'State', country: 'Country', job_start_date: 'Start Date',
};

/** Robust client-side CSV parser — handles quoted fields and embedded commas/newlines */
function parseCSVText(text) {
  const rows = [];
  let field = '', row = [], inQ = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') {
      if (inQ && text[i + 1] === '"') { field += '"'; i++; }
      else inQ = !inQ;
    } else if (ch === ',' && !inQ) {
      row.push(field); field = '';
    } else if ((ch === '\n' || (ch === '\r' && text[i + 1] === '\n')) && !inQ) {
      if (ch === '\r') i++;
      row.push(field); rows.push(row); row = []; field = '';
    } else if (ch === '\r' && !inQ) {
      row.push(field); rows.push(row); row = []; field = '';
    } else {
      field += ch;
    }
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  // Drop trailing empty rows
  while (rows.length && rows[rows.length - 1].every(f => !f.trim())) rows.pop();
  return rows;
}

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

  const [showAddModal, setShowAddModal] = useState(false);
  const [activeTab, setActiveTab] = useState('manual'); // 'manual' | 'import'
  const [manualForm, setManualForm] = useState({ ...EMPTY_PERSON });
  const [selectedFile, setSelectedFile] = useState(null);
  const [parsedRows, setParsedRows] = useState([]);      // CSV preview rows
  const [parseError, setParseError] = useState(null);   // column mismatch / parse error
  const [editingCell, setEditingCell] = useState(null);  // {row, col} for CSV table
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  // Edit / Delete CRUD States
  const [editPerson, setEditPerson] = useState(null);      // person obj being edited
  const [editForm, setEditForm] = useState({});             // edit form values
  const [isEditSubmitting, setIsEditSubmitting] = useState(false);
  const [editError, setEditError] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);  // {id, name}
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

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

  // ---------------- Open edit modal ----------------
  const openEdit = (person) => {
    setEditPerson(person);
    setEditForm({
      source: person.source || 'Manual Entry',
      status: person.status || 'Pending',
      organization_name: person.organization_name || '',
      first_name: person.first_name || '',
      last_name: person.last_name || '',
      full_name: person.full_name || '',
      title: person.title || '',
      function_name: person.function_name || '',
      seniority: person.seniority || '',
      email: person.email || '',
      email_status: person.email_status || '',
      email_confidence: person.email_confidence ?? '',
      phone: person.phone || '',
      linkedin_url: person.linkedin_url || '',
      city: person.city || '',
      state: person.state || '',
      country: person.country || '',
      job_start_date: person.job_start_date ? person.job_start_date.slice(0, 10) : '',
    });
    setEditError(null);
  };

  // ---------------- Submit edit ----------------
  const handleEditSubmit = (e) => {
    e.preventDefault();
    setIsEditSubmitting(true);
    setEditError(null);
    api.updatePerson(editPerson.id, editForm)
      .then(() => {
        setIsEditSubmitting(false);
        setEditPerson(null);
        fetchPeople();
        notify('Contact updated', `${editForm.full_name || editForm.first_name || 'Contact'} was updated.`, '/people');
      })
      .catch((err) => {
        setIsEditSubmitting(false);
        setEditError(err.message);
      });
  };

  // ---------------- Delete confirm ----------------
  const handleDeleteConfirm = () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    setDeleteError(null);
    api.deletePerson(deleteTarget.id)
      .then(() => {
        setIsDeleting(false);
        setDeleteTarget(null);
        fetchPeople();
        notify('Contact deleted', `${deleteTarget.name} was removed.`, '/people');
      })
      .catch((err) => {
        setIsDeleting(false);
        setDeleteError(err.message);
      });
  };


  // ---------------- Parse CSV on file select ----------------
  const handleFileSelect = (file) => {
    if (!file) return;
    setSelectedFile(file);
    setParsedRows([]);
    setParseError(null);
    setSubmitError(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const text = e.target.result;
        const allRows = parseCSVText(text);
        if (allRows.length < 2) { setParseError('CSV has no data rows.'); return; }
        const header = allRows[0].map(h => h.trim());
        const csvSet = new Set(header);
        const missing = REQUIRED_COLS.filter(c => !csvSet.has(c));
        const extra = header.filter(c => !REQUIRED_COLS_SET.has(c));
        if (missing.length || extra.length) {
          const parts = [];
          if (missing.length) parts.push(`Missing: ${missing.join(', ')}`);
          if (extra.length) parts.push(`Not allowed: ${extra.join(', ')}`);
          setParseError(parts.join(' | '));
          return;
        }
        const data = allRows.slice(1).map(vals => {
          const obj = {};
          header.forEach((h, i) => { obj[h] = (vals[i] ?? '').trim(); });
          return obj;
        }).filter(r => REQUIRED_COLS.some(c => r[c]));
        setParsedRows(data);
      } catch {
        setParseError('Failed to parse the CSV file.');
      }
    };
    reader.readAsText(file);
  };

  // Cell editing helpers
  const updateCell = (rowIdx, col, val) => {
    setParsedRows(rows => rows.map((r, i) => i === rowIdx ? { ...r, [col]: val } : r));
  };
  const deleteRow = (rowIdx) => setParsedRows(rows => rows.filter((_, i) => i !== rowIdx));
  const addRow = () => setParsedRows(rows => [...rows, { ...EMPTY_PERSON, source: 'CSV Import' }]);

  // ---------------- CSV import submit (send parsed rows as JSON) ----------------
  const handleImportSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      if (!parsedRows.length) throw new Error('No rows to import. Please select and verify a CSV file first.');
      const res = await api.importPeopleJSON(parsedRows);
      setIsSubmitting(false);
      setShowAddModal(false);
      setSelectedFile(null);
      setParsedRows([]);
      setParseError(null);
      fetchPeople();
      notify('Contacts imported', `${res.count ?? parsedRows.length} contacts imported successfully.`, '/people');
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
                      <div className="flex items-center gap-2">
                        <Link to={`/people/${p.id}`} className="text-slate-400 hover:text-brand-600 dark:hover:text-brand-400 transition-colors" title="View">
                          <Eye size={15} />
                        </Link>
                        <button onClick={() => openEdit(p)} className="text-slate-400 hover:text-amber-500 dark:hover:text-amber-400 transition-colors" title="Edit">
                          <Pencil size={15} />
                        </button>
                        <button onClick={() => { setDeleteTarget({ id: p.id, name: p.full_name || 'this contact' }); setDeleteError(null); }} className="text-slate-400 hover:text-rose-500 dark:hover:text-rose-400 transition-colors" title="Delete">
                          <Trash2 size={15} />
                        </button>
                      </div>
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
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[9px] font-semibold text-slate-500 dark:bg-navy-800 dark:text-slate-400">
                      {p.source || '—'}
                    </span>
                    <Link to={`/people/${p.id}`} className="rounded-lg p-1.5 text-slate-400 hover:text-brand-600 hover:bg-brand-50 dark:hover:bg-navy-700 transition-colors" title="View">
                      <Eye size={13} />
                    </Link>
                    <button onClick={() => openEdit(p)} className="rounded-lg p-1.5 text-slate-400 hover:text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-950/30 transition-colors" title="Edit">
                      <Pencil size={13} />
                    </button>
                    <button onClick={() => { setDeleteTarget({ id: p.id, name: p.full_name || 'this contact' }); setDeleteError(null); }} className="rounded-lg p-1.5 text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors" title="Delete">
                      <Trash2 size={13} />
                    </button>
                  </div>
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

                  {/* Drop zone */}
                  <div
                    className={`flex items-center gap-4 rounded-xl border-2 border-dashed px-5 py-4 cursor-pointer transition-colors ${
                      selectedFile && !parseError
                        ? 'border-emerald-400 bg-emerald-50 dark:bg-emerald-950/20'
                        : parseError
                        ? 'border-rose-400 bg-rose-50 dark:bg-rose-950/20'
                        : 'border-slate-300 dark:border-navy-600 hover:border-brand-400'
                    }`}
                    onClick={() => document.getElementById('people-file-input').click()}
                  >
                    <FileText size={28} className={parseError ? 'text-rose-400' : selectedFile ? 'text-emerald-500' : 'text-slate-300 dark:text-slate-600'} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-700 dark:text-slate-300 truncate">
                        {selectedFile ? selectedFile.name : 'Click to upload a CSV file'}
                      </p>
                      <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
                        {parseError ? 'Column mismatch — see error below' : parsedRows.length > 0 ? `${parsedRows.length} rows ready to import` : 'Must contain exactly 18 DB columns'}
                      </p>
                    </div>
                    {selectedFile && (
                      <button type="button" onClick={(ev) => { ev.stopPropagation(); setSelectedFile(null); setParsedRows([]); setParseError(null); }}
                        className="shrink-0 rounded-lg p-1.5 text-slate-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors">
                        <X size={14} />
                      </button>
                    )}
                    <input id="people-file-input" type="file" accept=".csv" className="hidden"
                      onChange={(e) => { if (e.target.files?.[0]) handleFileSelect(e.target.files[0]); }} />
                  </div>

                  {/* Column mismatch error */}
                  {parseError && (
                    <div className="flex items-start gap-2.5 rounded-xl bg-rose-50 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-900/30 p-3">
                      <AlertTriangle size={15} className="text-rose-500 shrink-0 mt-0.5" />
                      <div className="text-xs">
                        <p className="font-bold text-rose-600 dark:text-rose-400 mb-1">CSV column mismatch</p>
                        <p className="text-rose-500 dark:text-rose-400">{parseError}</p>
                        <p className="mt-1.5 text-slate-500 dark:text-slate-400">
                          Required (exact): <span className="font-mono">{REQUIRED_COLS.join(', ')}</span>
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Editable preview table */}
                  {parsedRows.length > 0 && (
                    <div className="rounded-xl border border-slate-200 dark:border-navy-700 overflow-hidden">
                      {/* Table header */}
                      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-50 dark:bg-navy-900 border-b border-slate-200 dark:border-navy-700">
                        <span className="text-xs font-bold text-navy-900 dark:text-white">
                          Preview — {parsedRows.length} rows
                        </span>
                        <button type="button" onClick={addRow}
                          className="flex items-center gap-1.5 text-xs font-bold text-brand-600 dark:text-brand-400 hover:text-brand-700 transition-colors">
                          <PlusCircle size={13} /> Add row
                        </button>
                      </div>

                      {/* Scrollable table */}
                      <div className="overflow-auto max-h-[42vh]">
                        <table className="w-full text-[11px] border-collapse" style={{ minWidth: '1600px' }}>
                          <thead className="sticky top-0 z-10">
                            <tr className="bg-slate-100 dark:bg-navy-900">
                              <th className="px-2 py-2 text-left font-semibold text-slate-500 dark:text-slate-400 w-8 sticky left-0 bg-slate-100 dark:bg-navy-900">#</th>
                              {REQUIRED_COLS.map(col => (
                                <th key={col} className="px-2 py-2 text-left font-semibold text-slate-500 dark:text-slate-400 whitespace-nowrap">
                                  {COL_LABELS[col]}
                                </th>
                              ))}
                              <th className="px-2 py-2 sticky right-0 bg-slate-100 dark:bg-navy-900 w-8"></th>
                            </tr>
                          </thead>
                          <tbody>
                            {parsedRows.map((row, rIdx) => (
                              <tr key={rIdx} className="border-t border-slate-100 dark:border-navy-800 hover:bg-brand-50/40 dark:hover:bg-navy-800/40 group">
                                <td className="px-2 py-1 text-slate-400 sticky left-0 bg-white dark:bg-navy-850 group-hover:bg-brand-50/40 dark:group-hover:bg-navy-800/40 font-mono">{rIdx + 1}</td>
                                {REQUIRED_COLS.map(col => {
                                  const isEditing = editingCell?.row === rIdx && editingCell?.col === col;
                                  return (
                                    <td key={col} className="px-1 py-1 min-w-[90px] max-w-[160px]">
                                      {isEditing ? (
                                        <input
                                          autoFocus
                                          value={row[col] ?? ''}
                                          onChange={(e) => updateCell(rIdx, col, e.target.value)}
                                          onBlur={() => setEditingCell(null)}
                                          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === 'Escape') setEditingCell(null); }}
                                          className="w-full rounded border border-brand-400 bg-white dark:bg-navy-800 dark:text-white px-1.5 py-0.5 text-[11px] outline-none shadow-sm"
                                        />
                                      ) : (
                                        <div
                                          onClick={() => setEditingCell({ row: rIdx, col })}
                                          className="cursor-text px-1.5 py-0.5 rounded hover:bg-brand-100 dark:hover:bg-navy-700 truncate text-slate-700 dark:text-slate-300 min-h-[20px]"
                                          title={row[col] || '(empty — click to edit)'}
                                        >
                                          {row[col] || <span className="text-slate-300 dark:text-slate-600 italic">empty</span>}
                                        </div>
                                      )}
                                    </td>
                                  );
                                })}
                                <td className="px-1 py-1 sticky right-0 bg-white dark:bg-navy-850 group-hover:bg-brand-50/40 dark:group-hover:bg-navy-800/40">
                                  <button type="button" onClick={() => deleteRow(rIdx)}
                                    className="rounded p-1 text-slate-300 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors">
                                    <Trash2 size={12} />
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* No-file placeholder */}
                  {!selectedFile && (
                    <div className="rounded-xl border border-slate-200 dark:border-navy-700 bg-slate-50 dark:bg-navy-900 p-4">
                      <p className="text-xs font-bold text-navy-900 dark:text-white mb-2">Required columns (18 exact)</p>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-1 font-mono text-[10px] text-slate-500 dark:text-slate-400">
                        {REQUIRED_COLS.map(col => (
                          <span key={col} className="bg-white dark:bg-navy-800 border border-slate-200 dark:border-navy-700 rounded px-1.5 py-0.5">{col}</span>
                        ))}
                      </div>
                    </div>
                  )}

                  {submitError && (
                    <div className="flex items-start gap-2 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/30 p-3 text-xs text-red-600 dark:text-red-400">
                      <AlertTriangle size={13} className="shrink-0 mt-0.5" />
                      {submitError}
                    </div>
                  )}

                  <div className="flex justify-end gap-3 border-t border-slate-100 dark:border-navy-700 pt-5 mt-5">
                    <button type="button" onClick={() => setShowAddModal(false)} className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700 transition-colors">
                      Cancel
                    </button>
                    <button type="submit" disabled={isSubmitting || parsedRows.length === 0}
                      className="flex items-center justify-center gap-1.5 rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white shadow-soft hover:bg-brand-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                      {isSubmitting ? <Loader2 className="animate-spin" size={14} /> : <Check size={14} />}
                      Import {parsedRows.length > 0 ? `${parsedRows.length} rows` : 'CSV'}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ================================================================ */}
      {/* Edit Person Modal                                                  */}
      {/* ================================================================ */}
      {editPerson && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4 backdrop-blur-md" onClick={() => setEditPerson(null)}>
          <div className="w-full max-w-3xl rounded-2xl bg-white dark:bg-navy-800 shadow-2xl overflow-hidden border border-slate-100 dark:border-navy-700 flex flex-col max-h-[92vh]"
            onClick={(e) => e.stopPropagation()}>

            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 p-5 shrink-0">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-50 dark:bg-amber-950/30 text-amber-600 dark:text-amber-400">
                  <Pencil size={18} />
                </div>
                <div>
                  <h3 className="text-base font-extrabold text-navy-900 dark:text-white">Edit Contact</h3>
                  <p className="text-xs text-slate-400 mt-0.5">{editPerson.full_name || 'Unnamed Contact'}</p>
                </div>
              </div>
              <button onClick={() => setEditPerson(null)} className="rounded-lg p-2 text-slate-400 hover:text-navy-950 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-navy-900 transition-colors">
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <form onSubmit={handleEditSubmit} className="flex-1 overflow-y-auto">
              <div className="p-5 space-y-5">
                {editError && (
                  <div className="flex items-start gap-2 rounded-xl bg-rose-50 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-900/30 p-3 text-xs text-rose-600 dark:text-rose-400">
                    <AlertTriangle size={13} className="shrink-0 mt-0.5" /> {editError}
                  </div>
                )}

                {/* Name */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {['first_name', 'last_name', 'full_name'].map(f => (
                    <div key={f}>
                      <label className={labelClass}>{COL_LABELS[f]}</label>
                      <input value={editForm[f] || ''} onChange={e => setEditForm(p => ({ ...p, [f]: e.target.value }))} className={inputClass} placeholder={COL_LABELS[f]} />
                    </div>
                  ))}
                </div>

                {/* Role */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-t border-slate-100 dark:border-navy-700 pt-4">
                  {['title', 'function_name', 'seniority'].map(f => (
                    <div key={f}>
                      <label className={labelClass}>{COL_LABELS[f]}</label>
                      <input value={editForm[f] || ''} onChange={e => setEditForm(p => ({ ...p, [f]: e.target.value }))} className={inputClass} placeholder={COL_LABELS[f]} />
                    </div>
                  ))}
                </div>

                {/* Organization */}
                <div className="border-t border-slate-100 dark:border-navy-700 pt-4">
                  <label className={labelClass}>Organization</label>
                  <input value={editForm.organization_name || ''} onChange={e => setEditForm(p => ({ ...p, organization_name: e.target.value }))} className={inputClass} placeholder="Company / Organization" />
                </div>

                {/* Contact */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-slate-100 dark:border-navy-700 pt-4">
                  <div>
                    <label className={labelClass}>Email</label>
                    <input type="email" value={editForm.email || ''} onChange={e => setEditForm(p => ({ ...p, email: e.target.value }))} className={inputClass} placeholder="Email address" />
                  </div>
                  <div>
                    <label className={labelClass}>Email Status</label>
                    <input value={editForm.email_status || ''} onChange={e => setEditForm(p => ({ ...p, email_status: e.target.value }))} className={inputClass} placeholder="valid / invalid / unknown" />
                  </div>
                  <div>
                    <label className={labelClass}>Phone</label>
                    <input value={editForm.phone || ''} onChange={e => setEditForm(p => ({ ...p, phone: e.target.value }))} className={inputClass} placeholder="Phone number" />
                  </div>
                  <div>
                    <label className={labelClass}>LinkedIn URL</label>
                    <input value={editForm.linkedin_url || ''} onChange={e => setEditForm(p => ({ ...p, linkedin_url: e.target.value }))} className={inputClass} placeholder="https://linkedin.com/in/..." />
                  </div>
                </div>

                {/* Location */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-t border-slate-100 dark:border-navy-700 pt-4">
                  {['city', 'state', 'country'].map(f => (
                    <div key={f}>
                      <label className={labelClass}>{COL_LABELS[f]}</label>
                      <input value={editForm[f] || ''} onChange={e => setEditForm(p => ({ ...p, [f]: e.target.value }))} className={inputClass} placeholder={COL_LABELS[f]} />
                    </div>
                  ))}
                </div>

                {/* Meta */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 border-t border-slate-100 dark:border-navy-700 pt-4">
                  <div>
                    <label className={labelClass}>Source</label>
                    <select value={editForm.source || 'Manual Entry'} onChange={e => setEditForm(p => ({ ...p, source: e.target.value }))} className={`${inputClass} cursor-pointer`}>
                      {SOURCE_CHOICES.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={labelClass}>Status</label>
                    <select value={editForm.status || 'Pending'} onChange={e => setEditForm(p => ({ ...p, status: e.target.value }))} className={`${inputClass} cursor-pointer`}>
                      {STATUS_CHOICES.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className={labelClass}>Job Start Date</label>
                    <input type="date" value={editForm.job_start_date || ''} onChange={e => setEditForm(p => ({ ...p, job_start_date: e.target.value }))} className={inputClass} />
                  </div>
                </div>
              </div>

              {/* Footer */}
              <div className="flex justify-end gap-3 border-t border-slate-100 dark:border-navy-700 px-5 py-4 shrink-0 bg-white dark:bg-navy-800">
                <button type="button" onClick={() => setEditPerson(null)} className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700 transition-colors">
                  Cancel
                </button>
                <button type="submit" disabled={isEditSubmitting} className="flex items-center justify-center gap-1.5 rounded-xl bg-amber-500 px-5 py-2.5 text-xs font-bold text-white shadow-soft hover:bg-amber-600 transition-colors disabled:opacity-75">
                  {isEditSubmitting ? <Loader2 className="animate-spin" size={14} /> : <Check size={14} />}
                  Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ================================================================ */}
      {/* Delete Confirmation Modal                                         */}
      {/* ================================================================ */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4 backdrop-blur-md" onClick={() => !isDeleting && setDeleteTarget(null)}>
          <div className="w-full max-w-sm rounded-2xl bg-white dark:bg-navy-800 shadow-2xl border border-slate-100 dark:border-navy-700 overflow-hidden"
            onClick={(e) => e.stopPropagation()}>
            <div className="p-6">
              <div className="flex items-center gap-4 mb-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-rose-100 dark:bg-rose-950/30">
                  <Trash2 size={22} className="text-rose-500" />
                </div>
                <div>
                  <h3 className="text-base font-extrabold text-navy-900 dark:text-white">Delete Contact</h3>
                  <p className="text-xs text-slate-400 mt-0.5">This action cannot be undone</p>
                </div>
              </div>
              <p className="text-sm text-slate-600 dark:text-slate-300 mb-1">
                Are you sure you want to permanently delete
              </p>
              <p className="text-sm font-bold text-navy-900 dark:text-white mb-5">
                "{deleteTarget.name}"?
              </p>
              {deleteError && (
                <div className="flex items-start gap-2 rounded-xl bg-rose-50 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-900/30 p-3 text-xs text-rose-600 dark:text-rose-400 mb-4">
                  <AlertTriangle size={13} className="shrink-0 mt-0.5" /> {deleteError}
                </div>
              )}
              <div className="flex gap-3">
                <button onClick={() => setDeleteTarget(null)} disabled={isDeleting}
                  className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700 transition-colors disabled:opacity-50">
                  Cancel
                </button>
                <button onClick={handleDeleteConfirm} disabled={isDeleting}
                  className="flex-1 flex items-center justify-center gap-1.5 rounded-xl bg-rose-500 px-4 py-2.5 text-xs font-bold text-white hover:bg-rose-600 transition-colors disabled:opacity-75">
                  {isDeleting ? <Loader2 className="animate-spin" size={14} /> : <Trash2 size={14} />}
                  Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
