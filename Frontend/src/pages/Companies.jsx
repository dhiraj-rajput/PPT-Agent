import { useState, useMemo, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Search, Plus, SlidersHorizontal, Eye, FileText, X, Upload, Check, Loader2, AlertOctagon, Calendar } from 'lucide-react';
import { PageHeader, Card, MatchBadge, StatusBadge } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';

export default function Companies() {
  const { createAlert } = useNotifications();
  const notify = (title, message, link) => createAlert(title, message, link).catch(() => {});

  // Query & Filters States
  const [query, setQuery] = useState('');
  const [sizeFilter, setSizeFilter] = useState('All');
  const [naicsFilter, setNaicsFilter] = useState('All');
  const [researchedFilter, setResearchedFilter] = useState('All');
  const [naicsCodes, setNaicsCodes] = useState([]);

  // Description filters states
  const [matchCompanyDescription, setMatchCompanyDescription] = useState(false);
  const [ownCompanyProfile, setOwnCompanyProfile] = useState(null);
  // Which entity (parent company or a subsidiary) to pull the description from
  const [matchEntityId, setMatchEntityId] = useState('parent');

  useEffect(() => {
    api.getOwnCompanyProfile()
      .then(data => setOwnCompanyProfile(data))
      .catch(err => console.error("Error loading own company profile:", err));
  }, []);

  // Build the list of selectable entities: the parent/main company plus any registered subsidiaries
  const entityOptions = ownCompanyProfile
    ? [
        { id: 'parent', name: ownCompanyProfile.name || 'Main Company', description: ownCompanyProfile.description, isParent: true },
        ...(ownCompanyProfile.sub_companies || []).map((sub, idx) => ({
          id: String(idx),
          name: sub.name,
          description: sub.description,
          isParent: false,
        })),
      ]
    : [];

  function getSelectedEntity() {
    return entityOptions.find((ent) => ent.id === matchEntityId) || entityOptions[0];
  }
  
  // Data States
  const [allCompanies, setAllCompanies] = useState([]);
  const [totalCompanies, setTotalCompanies] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const itemsPerPage = 20;

  // Add/Import Modal States
  const [showAddModal, setShowAddModal] = useState(false);
  const [activeTab, setActiveTab] = useState('manual'); // 'manual' | 'import'
  const [manualForm, setManualForm] = useState({
    name: '',
    uei: '',
    cage_code: '',
    primary_naics: '',
    primary_naics_desc: '',
    city: '',
    state: '',
    country: 'USA',
    contact: '',
    contact_role: 'Procurement Manager',
    email: '',
    phone: '',
    size: 'Small',
    status: 'Active'
  });
  const [importMode, setImportMode] = useState('document'); // 'document' | 'file'
  const [selectedFile, setSelectedFile] = useState(null);
  const [docEditor, setDocEditor] = useState({
    name: '',
    uei: '',
    cage_code: '',
    primary_naics: '',
    primary_naics_desc: '',
    city: '',
    state: '',
    country: 'USA',
    contact: '',
    contact_role: 'Procurement Manager',
    email: '',
    phone: '',
    size: 'Small',
    status: 'Active'
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  // Fetch companies dynamically from FastAPI backend
  const fetchCompanies = () => {
    setLoading(true);
    const params = {
      page: currentPage.toString(),
      limit: itemsPerPage.toString(),
    };
    if (query) params.query = query;
    if (sizeFilter !== 'All') params.size = sizeFilter;
    if (naicsFilter !== 'All') params.naics = naicsFilter;
    if (researchedFilter !== 'All') {
      params.researched = researchedFilter === 'Researched' ? 'true' : 'false';
    }
    if (matchCompanyDescription && !query) params.match_company_description = 'true';

    api.getCompanies(params)
      .then((data) => {
        setAllCompanies(data.companies || []);
        setTotalCompanies(data.total || 0);
        if (data.naics_codes && naicsCodes.length === 0) {
          setNaicsCodes(data.naics_codes);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error fetching companies:', err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchCompanies();
  }, [currentPage, query, sizeFilter, naicsFilter, researchedFilter, matchCompanyDescription]);

  // Reset page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [query, sizeFilter, naicsFilter, researchedFilter, matchCompanyDescription]);

  const pageCount = Math.ceil(totalCompanies / itemsPerPage);

  // Handle manual company add submission
  const handleManualSubmit = (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitError(null);

    api.addCompany(manualForm)
      .then(() => {
        setIsSubmitting(false);
        setShowAddModal(false);
        // Reset form
        setManualForm({
          name: '',
          uei: '',
          cage_code: '',
          primary_naics: '',
          primary_naics_desc: '',
          city: '',
          state: '',
          country: 'USA',
          contact: '',
          email: '',
          phone: '',
          size: 'Small',
          status: 'Active'
        });
        fetchCompanies();
        notify('Company added', `${manualForm.name || 'A new company'} was added to your directory.`, '/companies');
      })
      .catch((err) => {
        setIsSubmitting(false);
        setSubmitError(err.message);
      });
  };

  // Handle bulk import submission
  const handleImportSubmit = async (e) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      if (importMode === 'document') {
        const importData = JSON.stringify([docEditor]);
        await api.importCompanies({ data: importData, format: 'json' });
      } else {
        if (!selectedFile) throw new Error("Please select a file to upload");
        const format = selectedFile.name.toLowerCase().endsWith('.json') ? 'json' : 'csv';
        const text = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = e => resolve(e.target.result);
          reader.onerror = e => reject(new Error("Failed to read file"));
          reader.readAsText(selectedFile);
        });
        await api.importCompanies({ data: text, format });
      }
      setIsSubmitting(false);
      setShowAddModal(false);
      setSelectedFile(null);
      fetchCompanies();
    } catch (err) {
      setIsSubmitting(false);
      setSubmitError(err.message || 'Import failed');
    }
  };

  return (
    <div>
      <PageHeader
        title="Companies"
        subtitle={`${totalCompanies.toLocaleString()} companies loaded from SAM database`}
        action={
          <button 
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft hover:bg-brand-600 transition-colors"
          >
            <Plus size={16} /> Add Company
          </button>
        }
      />

      {/* Filters Bar */}
      <Card className="!p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          {/* Unified Search Bar — matches company key fields (name, UEI, contact, email)
              AND description/NAICS keywords from a single input, no field selector needed */}
          <div className="flex flex-1 min-w-[280px] items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 dark:border-navy-700 dark:bg-navy-800">
            <Search size={16} className="text-slate-400 dark:text-slate-500" />
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                if (matchCompanyDescription) setMatchCompanyDescription(false);
              }}
              placeholder="Search by name, UEI, contact, or description keywords (e.g. cloud security)..."
              className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500 dark:text-white"
            />
            {query && (
              <button
                onClick={() => { setQuery(''); setMatchCompanyDescription(false); }}
                className="rounded-full p-0.5 text-slate-400 hover:text-rose-500"
                title="Clear search"
              >
                <X size={14} />
              </button>
            )}
          </div>

          {/* Size Filter */}
          <select
            value={sizeFilter}
            onChange={(e) => setSizeFilter(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white cursor-pointer"
          >
            <option value="All">All Company Sizes</option>
            <option value="Small">Small Business</option>
            <option value="Large">Large Business</option>
          </select>

          {/* NAICS Sector Filter */}
          <select
            value={naicsFilter}
            onChange={(e) => setNaicsFilter(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white max-w-xs cursor-pointer truncate"
          >
            <option value="All">All NAICS Sectors</option>
            {naicsCodes.map((code) => (
              <option key={code} value={code}>{code}</option>
            ))}
          </select>

          {/* Research Status Filter */}
          <select
            value={researchedFilter}
            onChange={(e) => setResearchedFilter(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white cursor-pointer"
          >
            <option value="All">All Research Status</option>
            <option value="Researched">Researched (AI Ready)</option>
            <option value="Not Researched">Not Researched</option>
          </select>
        </div>

        {/* Match My Company Description — auto-fills the search bar above with
            your own company's description so results match it (no separate field) */}
        <div className="flex flex-wrap items-center gap-3 pt-3 border-t border-slate-100 dark:border-navy-800">
          {/* Entity selector: choose whether to match against the parent/main company or a subsidiary */}
          {entityOptions.length > 1 && (
            <select
              value={matchEntityId}
              onChange={(e) => {
                setMatchEntityId(e.target.value);
                // If matching is currently active, refresh the search text to the newly selected entity
                if (matchCompanyDescription) {
                  const ent = entityOptions.find((opt) => opt.id === e.target.value);
                  setQuery(ent?.description || '');
                }
              }}
              className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-semibold text-slate-600 outline-none focus:border-brand-500 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300 cursor-pointer"
              title="Choose which company entity's description to match"
            >
              {entityOptions.map((ent) => (
                <option key={ent.id} value={ent.id}>
                  {ent.name} {ent.isParent ? '(Main Company)' : '(Subsidiary)'}
                </option>
              ))}
            </select>
          )}

          <button
            onClick={() => {
              const entity = getSelectedEntity();
              if (!entity?.description) {
                alert(
                  entity && !entity.isParent
                    ? `No description registered for ${entity.name}. Go to the Proposal Builder page and add a description for this subsidiary first!`
                    : "No company description registered. Go to the Proposal Builder page and register a description of what your company does first!"
                );
                return;
              }
              const nextVal = !matchCompanyDescription;
              setMatchCompanyDescription(nextVal);
              setQuery(nextVal ? entity.description : '');
            }}
            className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold border transition-all ${
              matchCompanyDescription
                ? 'bg-brand-500 text-white border-brand-500 shadow-md shadow-brand-500/20'
                : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 dark:bg-navy-900 dark:text-slate-400 dark:border-navy-800 dark:hover:bg-navy-800'
            }`}
            title="Automatically matches companies related to the selected entity's profile description"
          >
            <SlidersHorizontal size={14} />
            Match {entityOptions.length > 1 ? getSelectedEntity()?.name || 'My Company' : 'My Company'} Description
          </button>
        </div>
      </Card>

      {/* Main Table */}
      {loading ? (
        <Card className="flex flex-col items-center justify-center py-20 mt-5">
          <Loader2 className="animate-spin text-brand-500" size={32} />
          <p className="mt-4 text-sm text-slate-500 dark:text-slate-400 font-medium">Loading companies from database...</p>
        </Card>
      ) : (
        <Card className="mt-5 !p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-400 dark:border-navy-800 dark:text-slate-400">
                  <th className="px-5 py-3 font-semibold w-[26%] min-w-[240px]">Company</th>
                  <th className="px-5 py-3 font-semibold">UEI / CAGE</th>
                  <th className="px-5 py-3 font-semibold w-[15%] max-w-[150px]">NAICS Sector</th>
                  <th className="px-5 py-3 font-semibold">Location</th>
                  <th className="px-5 py-3 font-semibold">Size</th>
                  <th className="px-5 py-3 font-semibold">Match Score</th>
                  <th className="px-5 py-3 font-semibold">Research Status</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {allCompanies.map((c) => (
                  <tr key={c.uei} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60 dark:border-navy-800/40 dark:hover:bg-navy-800/40">
                    {/* Company Column */}
                    <td className="px-5 py-3.5 w-[26%] min-w-[240px]">
                      <Link to={`/companies/${c.uei}`} className="flex items-center gap-3">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-xs font-bold text-brand-600 dark:bg-navy-900 dark:text-brand-400 aspect-square">
                          {(c.name || '??').slice(0, 2).toUpperCase()}
                        </div>
                        <div>
                          <p className="font-bold text-navy-900 hover:text-brand-600 dark:text-white dark:hover:text-brand-400 leading-tight text-sm">
                            {c.name || 'Unnamed Company'}
                          </p>
                          <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">{c.contact || c.ebiz_contact || '—'}</p>
                        </div>
                      </Link>
                    </td>
                    {/* UEI/CAGE Column */}
                    <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400 font-mono text-xs">
                      <p>{c.uei || '—'}</p>
                      {c.cage_code && <p className="text-[10px] text-slate-400 mt-0.5">CAGE: {c.cage_code}</p>}
                    </td>
                    {/* NAICS Sector Column */}
                    <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400 text-xs w-[15%] max-w-[150px]">
                      <p className="font-semibold text-navy-900 dark:text-slate-300">{c.primary_naics || '—'}</p>
                      <p className="mt-0.5 text-slate-400 dark:text-slate-500 truncate" title={c.primary_naics_desc}>{c.primary_naics_desc || ''}</p>
                    </td>
                    {/* Location Column */}
                    <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400 text-xs">
                      {c.location || (c.city && c.state ? `${c.city}, ${c.state}` : c.city || c.state || '—')}
                    </td>
                    {/* Size Column */}
                    <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-semibold whitespace-nowrap ${
                        c.size === 'Small' 
                          ? 'bg-sky-50 text-sky-700 dark:bg-sky-950/20 dark:text-sky-400' 
                          : 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/20 dark:text-indigo-400'
                      }`}>
                        {c.size || 'Unknown'} Business
                      </span>
                    </td>
                    {/* Match Score Column */}
                    <td className="px-5 py-3.5"><MatchBadge score={c.matchScore ?? c.match_score} /></td>
                    {/* Research Status Column */}
                    <td className="px-5 py-3.5 text-xs">
                      {c.is_researched || c.hasResearchedProfile ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[10px] font-bold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                          <Check size={11} /> Researched
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] font-semibold text-slate-500 dark:bg-navy-800 dark:text-slate-400">
                          Not Researched
                        </span>
                      )}
                    </td>
                    {/* Status Column */}
                    <td className="px-5 py-3.5">
                      <div className="flex flex-col gap-1">
                        <StatusBadge status={c.status} />
                        {c.exclusions === 'Y' && (
                          <span className="flex items-center gap-0.5 text-[10px] font-bold text-rose-500">
                            <AlertOctagon size={10} /> Excluded
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {allCompanies.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-5 py-10 text-center text-slate-400 dark:text-slate-500">
                      No companies match your search and filter criteria.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {pageCount > 1 && (
            <div className="flex items-center justify-between border-t border-slate-100 p-4 dark:border-navy-800">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Showing <span className="font-semibold text-navy-900 dark:text-white">{(currentPage - 1) * itemsPerPage + 1}</span> to{' '}
                <span className="font-semibold text-navy-900 dark:text-white">
                  {Math.min(currentPage * itemsPerPage, totalCompanies)}
                </span>{' '}
                of <span className="font-semibold text-navy-900 dark:text-white">{totalCompanies.toLocaleString()}</span> companies
              </p>
              <div className="flex gap-2">
                <button
                  disabled={currentPage === 1}
                  onClick={() => setCurrentPage((p) => p - 1)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 disabled:opacity-50 dark:border-navy-700 dark:text-white dark:hover:bg-navy-800 transition-colors"
                >
                  Previous
                </button>
                <button
                  disabled={currentPage === pageCount}
                  onClick={() => setCurrentPage((p) => p + 1)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 disabled:opacity-50 dark:border-navy-700 dark:text-white dark:hover:bg-navy-800 transition-colors"
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
            className="w-full max-w-2xl rounded-2xl bg-white dark:bg-navy-800 shadow-2xl overflow-hidden border border-slate-100 dark:border-navy-700 flex flex-col max-h-[90vh]" 
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 p-5 shrink-0 bg-white dark:bg-navy-800">
              <div>
                <h3 className="text-base font-extrabold text-navy-900 dark:text-white">Add New Company</h3>
                <p className="text-xs text-slate-400 mt-1">Add a single company or import datasets into the collection</p>
              </div>
              <button onClick={() => setShowAddModal(false)} className="rounded-lg p-2 text-slate-400 hover:text-navy-950 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-navy-900 transition-colors">
                <X size={18} />
              </button>
            </div>

            {/* Modal Tabs */}
            <div className="flex border-b border-slate-100 dark:border-navy-700 bg-slate-50 dark:bg-navy-900 shrink-0">
              <button 
                onClick={() => setActiveTab('manual')}
                className={`flex-1 py-3 text-xs font-bold border-b-2 transition-colors ${
                  activeTab === 'manual' 
                    ? 'border-brand-500 text-brand-600 dark:text-brand-400 bg-white dark:bg-navy-800' 
                    : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-300'
                }`}
              >
                Manually Enter Details
              </button>
              <button 
                onClick={() => setActiveTab('import')}
                className={`flex-1 py-3 text-xs font-bold border-b-2 transition-colors ${
                  activeTab === 'import' 
                    ? 'border-brand-500 text-brand-600 dark:text-brand-400 bg-white dark:bg-navy-800' 
                    : 'border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-300'
                }`}
              >
                Import CSV / JSON
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-5">
              {submitError && (
                <div className="mb-4 rounded-xl bg-rose-50 border border-rose-100 p-3 text-xs font-semibold text-rose-600 dark:bg-rose-950/20 dark:border-rose-900/30 dark:text-rose-400">
                  Error: {submitError}
                </div>
              )}

              {activeTab === 'manual' ? (
                <form onSubmit={handleManualSubmit} className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Name */}
                    <div>
                      <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">Legal Business Name *</label>
                      <input 
                        required
                        value={manualForm.name}
                        onChange={(e) => setManualForm({...manualForm, name: e.target.value})}
                        placeholder="Company Name"
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                      />
                    </div>
                    {/* UEI */}
                    <div>
                      <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">Unique Entity ID (UEI) *</label>
                      <input 
                        required
                        value={manualForm.uei}
                        onChange={(e) => setManualForm({...manualForm, uei: e.target.value})}
                        placeholder="12-character ID"
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white font-mono"
                      />
                    </div>
                    {/* CAGE Code */}
                    <div>
                      <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">CAGE Code <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input 
                        value={manualForm.cage_code}
                        onChange={(e) => setManualForm({...manualForm, cage_code: e.target.value})}
                        placeholder="5-character CAGE"
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white font-mono"
                      />
                    </div>
                    {/* Size */}
                    <div>
                      <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">Business Size <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <select 
                        value={manualForm.size}
                        onChange={(e) => setManualForm({...manualForm, size: e.target.value})}
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white cursor-pointer"
                      >
                        <option value="Small">Small Business</option>
                        <option value="Large">Large Business</option>
                      </select>
                    </div>
                  </div>

                  <div className="border-t border-slate-100 dark:border-navy-700 pt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Primary NAICS */}
                    <div>
                      <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">Primary NAICS Code <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input 
                        value={manualForm.primary_naics}
                        onChange={(e) => setManualForm({...manualForm, primary_naics: e.target.value})}
                        placeholder="e.g. 541511"
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white font-mono"
                      />
                    </div>
                    {/* NAICS Desc */}
                    <div>
                      <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">NAICS Description <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input 
                        value={manualForm.primary_naics_desc}
                        onChange={(e) => setManualForm({...manualForm, primary_naics_desc: e.target.value})}
                        placeholder="e.g. Custom Computer Programming Services"
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                      />
                    </div>
                  </div>

                  <div className="border-t border-slate-100 dark:border-navy-700 pt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* City */}
                    <div>
                      <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">City <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input 
                        value={manualForm.city}
                        onChange={(e) => setManualForm({...manualForm, city: e.target.value})}
                        placeholder="City"
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                      />
                    </div>
                    {/* State */}
                    <div>
                      <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">State / Province <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input 
                        value={manualForm.state}
                        onChange={(e) => setManualForm({...manualForm, state: e.target.value})}
                        placeholder="State"
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                      />
                    </div>
                    {/* Country */}
                    <div>
                      <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">Country <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input 
                        value={manualForm.country}
                        onChange={(e) => setManualForm({...manualForm, country: e.target.value})}
                        placeholder="Country"
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                      />
                    </div>
                  </div>

                  <div className="border-t border-slate-100 dark:border-navy-700 pt-4 grid grid-cols-1 md:grid-cols-4 gap-4">
                    {/* Contact Name */}
                    <div>
                      <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">Contact Name <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input 
                        value={manualForm.contact}
                        onChange={(e) => setManualForm({...manualForm, contact: e.target.value})}
                        placeholder="Contact Person"
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                      />
                    </div>
                    {/* Contact Post / Role */}
                    <div>
                      <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">Post / Role <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <select
                        value={['Procurement Officer', 'Chief Technology Officer (CTO)', 'Director of Procurement', 'EBiz Contact', 'Managing Partner', 'Executive VP'].includes(manualForm.contact_role) ? manualForm.contact_role : 'Custom'}
                        onChange={(e) => {
                          if (e.target.value !== 'Custom') {
                            setManualForm({ ...manualForm, contact_role: e.target.value });
                          }
                        }}
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none mb-1.5 focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white cursor-pointer"
                      >
                        <option value="Procurement Officer">Procurement Officer</option>
                        <option value="Chief Technology Officer (CTO)">CTO</option>
                        <option value="Director of Procurement">Director of Procurement</option>
                        <option value="EBiz Contact">EBiz Contact</option>
                        <option value="Managing Partner">Managing Partner</option>
                        <option value="Executive VP">Executive VP</option>
                        <option value="Custom">Custom Role...</option>
                      </select>
                      <input 
                        value={manualForm.contact_role}
                        onChange={(e) => setManualForm({...manualForm, contact_role: e.target.value})}
                        placeholder="Or type custom role..."
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                      />
                    </div>
                    {/* Email */}
                    <div>
                      <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">Contact Email <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input 
                        type="email"
                        value={manualForm.email}
                        onChange={(e) => setManualForm({...manualForm, email: e.target.value})}
                        placeholder="Email Address"
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                      />
                    </div>
                    {/* Phone */}
                    <div>
                      <label className="block text-xs font-bold text-navy-900 dark:text-white mb-1.5">Contact Phone <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span></label>
                      <input 
                        value={manualForm.phone}
                        onChange={(e) => setManualForm({...manualForm, phone: e.target.value})}
                        placeholder="Phone Number"
                        className="w-full text-xs rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 outline-none focus:border-brand-400 focus:bg-white dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                      />
                    </div>
                  </div>

                  {/* Manual Footer */}
                  <div className="flex justify-end gap-3 border-t border-slate-100 dark:border-navy-700 pt-5 mt-5">
                    <button 
                      type="button"
                      onClick={() => setShowAddModal(false)}
                      className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700 transition-colors"
                    >
                      Cancel
                    </button>
                    <button 
                      type="submit"
                      disabled={isSubmitting}
                      className="flex items-center justify-center gap-1.5 rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white shadow-soft hover:bg-brand-600 transition-colors disabled:opacity-75"
                    >
                      {isSubmitting ? <Loader2 className="animate-spin" size={14} /> : <Check size={14} />}
                      Save Details
                    </button>
                  </div>
                </form>
              ) : (
                <form onSubmit={handleImportSubmit} className="space-y-4">
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 mb-2">
                      <button
                        type="button"
                        onClick={() => setImportMode('document')}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                          importMode === 'document'
                            ? 'bg-brand-500 text-white'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300'
                        }`}
                      >
                        Document Editor
                      </button>
                      <button
                        type="button"
                        onClick={() => setImportMode('file')}
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                          importMode === 'file'
                            ? 'bg-brand-500 text-white'
                            : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300'
                        }`}
                      >
                        Upload File
                      </button>
                    </div>

                    {importMode === 'document' ? (
                      <div className="rounded-xl border border-slate-200 dark:border-navy-700 bg-slate-50 dark:bg-navy-900 p-4 font-mono text-xs shadow-sm overflow-x-auto space-y-2">
                        <div className="text-slate-400 dark:text-slate-500 font-bold">{"{"}</div>
                        <div className="pl-3 space-y-2.5">
                          {[
                            { key: 'name', type: 'string', required: true, placeholder: '"Acme Corp"' },
                            { key: 'uei', type: 'string', required: true, placeholder: '"ABC123456789"' },
                            { key: 'cage_code', type: 'string', required: false, placeholder: '"1A2B3"' },
                            { key: 'primary_naics', type: 'string/int', required: false, placeholder: '"541512"' },
                            { key: 'primary_naics_desc', type: 'string', required: false, placeholder: '"Computer Systems Design"' },
                            { key: 'city', type: 'string', required: false, placeholder: '"Dallas"' },
                            { key: 'state', type: 'string', required: false, placeholder: '"TX"' },
                            { key: 'country', type: 'string', required: false, placeholder: '"USA"' },
                            { key: 'contact', type: 'string', required: false, placeholder: '"John Doe"' },
                            { key: 'contact_role', type: 'string', required: false, placeholder: '"Procurement Manager"' },
                            { key: 'email', type: 'string', required: false, placeholder: '"contact@acme.com"' },
                            { key: 'phone', type: 'string', required: false, placeholder: '"+1-214-555-0100"' },
                          ].map(f => (
                            <div key={f.key} className="flex flex-wrap items-center gap-2">
                              <div className="w-36 shrink-0 flex items-center">
                                <span className="text-brand-600 dark:text-brand-400 font-bold">"{f.key}"</span>
                                {f.required && <span className="text-rose-500 font-extrabold ml-0.5" title="Required field">*</span>}
                                {!f.required && <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span>}
                              </div>
                              <span className="text-slate-400 font-bold">:</span>
                              <span className="rounded bg-brand-50 dark:bg-navy-800 text-brand-700 dark:text-brand-300 border border-brand-200/60 dark:border-navy-700 px-1.5 py-0.5 text-[10px] font-semibold w-20 text-center shrink-0">
                                [{f.type}]
                              </span>
                              <input 
                                value={docEditor[f.key] || ''} 
                                onChange={e => setDocEditor({...docEditor, [f.key]: e.target.value})} 
                                className="flex-1 min-w-[160px] rounded-lg border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-800 px-3 py-1.5 text-xs text-navy-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-brand-400 outline-none transition-colors" 
                                placeholder={f.placeholder} 
                              />
                            </div>
                          ))}
                          
                          {/* Size Enum */}
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="w-36 shrink-0 flex items-center">
                              <span className="text-brand-600 dark:text-brand-400 font-bold">"size"</span>
                              <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span>
                            </div>
                            <span className="text-slate-400 font-bold">:</span>
                            <span className="rounded bg-purple-50 dark:bg-navy-800 text-purple-700 dark:text-purple-300 border border-purple-200/60 dark:border-navy-700 px-1.5 py-0.5 text-[10px] font-semibold w-20 text-center shrink-0">
                              [enum]
                            </span>
                            <select 
                              value={docEditor.size || 'Small'} 
                              onChange={e => setDocEditor({...docEditor, size: e.target.value})} 
                              className="flex-1 min-w-[160px] rounded-lg border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-800 px-3 py-1.5 text-xs font-semibold text-navy-900 dark:text-white focus:ring-2 focus:ring-brand-400 outline-none cursor-pointer"
                            >
                              <option value="Small">"Small"</option>
                              <option value="Large">"Large"</option>
                            </select>
                          </div>

                          {/* Status Enum */}
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="w-36 shrink-0 flex items-center">
                              <span className="text-brand-600 dark:text-brand-400 font-bold">"status"</span>
                              <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span>
                            </div>
                            <span className="text-slate-400 font-bold">:</span>
                            <span className="rounded bg-emerald-50 dark:bg-navy-800 text-emerald-700 dark:text-emerald-300 border border-emerald-200/60 dark:border-navy-700 px-1.5 py-0.5 text-[10px] font-semibold w-20 text-center shrink-0">
                              [enum]
                            </span>
                            <select 
                              value={docEditor.status || 'Active'} 
                              onChange={e => setDocEditor({...docEditor, status: e.target.value})} 
                              className="flex-1 min-w-[160px] rounded-lg border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-800 px-3 py-1.5 text-xs font-semibold text-navy-900 dark:text-white focus:ring-2 focus:ring-brand-400 outline-none cursor-pointer"
                            >
                              <option value="Active">"Active"</option>
                              <option value="Inactive">"Inactive"</option>
                            </select>
                          </div>
                        </div>
                        <div className="text-slate-400 dark:text-slate-500 font-bold">{"}"}</div>
                      </div>
                    ) : (
                      <div
                        className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 dark:border-navy-600 p-8 text-center cursor-pointer hover:border-brand-400 transition-colors"
                        onClick={() => document.getElementById('company-file-input').click()}
                      >
                        <Upload className="text-slate-300 dark:text-slate-600 mb-2" size={32} />
                        <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">
                          {selectedFile ? selectedFile.name : 'Click to upload CSV or JSON file'}
                        </p>
                        <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Supports .csv, .json</p>
                        <input
                          id="company-file-input"
                          type="file"
                          accept=".csv,.json"
                          className="hidden"
                          onChange={(e) => {
                            if (e.target.files && e.target.files[0]) {
                              setSelectedFile(e.target.files[0]);
                            }
                          }}
                        />
                      </div>
                    )}

                    {submitError && (
                      <div className="rounded-lg bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/30 p-3 text-xs text-red-600 dark:text-red-400">
                        {submitError}
                      </div>
                    )}
                  </div>

                  {/* Import Footer */}
                  <div className="flex justify-end gap-3 border-t border-slate-100 dark:border-navy-700 pt-5 mt-5">
                    <button 
                      type="button"
                      onClick={() => setShowAddModal(false)}
                      className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700 transition-colors"
                    >
                      Cancel
                    </button>
                    <button 
                      type="submit"
                      disabled={isSubmitting}
                      className="flex items-center justify-center gap-1.5 rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white shadow-soft hover:bg-brand-600 transition-colors disabled:opacity-75"
                    >
                      {isSubmitting ? <Loader2 className="animate-spin" size={14} /> : <Upload size={14} />}
                      Bulk Import
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
