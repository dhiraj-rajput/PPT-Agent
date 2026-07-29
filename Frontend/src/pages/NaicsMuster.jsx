import { useState, useEffect } from 'react';
import { Search, Filter, Hash, BookOpen, Copy, Check, ChevronLeft, ChevronRight, RefreshCw, Plus, X, Upload } from 'lucide-react';
import { api } from '../lib/api.jsx';

const NAICS_SECTORS = [
  { value: '', label: 'All Sectors' },
  { value: '11', label: '11 - Agriculture, Forestry, Fishing & Hunting' },
  { value: '21', label: '21 - Mining, Quarrying, & Oil/Gas Extraction' },
  { value: '22', label: '22 - Utilities' },
  { value: '23', label: '23 - Construction' },
  { value: '31-33', label: '31-33 - Manufacturing' },
  { value: '42', label: '42 - Wholesale Trade' },
  { value: '44-45', label: '44-45 - Retail Trade' },
  { value: '48-49', label: '48-49 - Transportation & Warehousing' },
  { value: '51', label: '51 - Information' },
  { value: '52', label: '52 - Finance & Insurance' },
  { value: '53', label: '53 - Real Estate & Rental/Leasing' },
  { value: '54', label: '54 - Professional, Scientific, & Technical' },
  { value: '55', label: '55 - Management of Companies' },
  { value: '56', label: '56 - Administrative & Support & Waste' },
  { value: '61', label: '61 - Educational Services' },
  { value: '62', label: '62 - Health Care & Social Assistance' },
  { value: '71', label: '71 - Arts, Entertainment, & Recreation' },
  { value: '72', label: '72 - Accommodation & Food Services' },
  { value: '81', label: '81 - Other Services (except Public Admin)' },
  { value: '92', label: '92 - Public Administration' },
];

export default function NaicsMuster() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(25);
  const [search, setSearch] = useState('');
  const [sector, setSector] = useState('');
  const [loading, setLoading] = useState(false);
  const [copiedCode, setCopiedCode] = useState(null);
  const [expandedCodes, setExpandedCodes] = useState({});

  // Own company description matching states
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

  // Modal States
  const [showModal, setShowModal] = useState(false);
  const [modalTab, setModalTab] = useState('manual'); // 'manual' | 'upload'
  const [manualCode, setManualCode] = useState('');
  const [manualTitle, setManualTitle] = useState('');
  const [manualDesc, setManualDesc] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [modalLoading, setModalLoading] = useState(false);
  const [modalError, setModalError] = useState('');
  const [modalSuccess, setModalSuccess] = useState('');
  const [naicsImportMode, setNaicsImportMode] = useState('document'); // 'document' | 'file'
  const [naicsDocEditor, setNaicsDocEditor] = useState({
    code: '',
    title: '',
    description: ''
  });
  const fetchNaics = useCallback(async (targetPage = page, targetSearch = search, targetSector = sector, targetMatch = matchCompanyDescription) => {
    setLoading(true);
    try {
      const res = await api.getNaicsCodes({
        search: targetSearch,
        sector: targetSector,
        match_company_description: targetMatch && !targetSearch,
        page: targetPage,
        limit,
      });
      setItems(res.items || []);
      setTotal(res.total || 0);
    } catch (err) {
      console.error('Error fetching NAICS codes:', err);
    } finally {
      setLoading(false);
    }
  }, [limit]);

  // Debounced search and direct filter refetch
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchNaics(page, search, sector, matchCompanyDescription);
    }, 200);
    return () => clearTimeout(timer);
  }, [page, search, sector, matchCompanyDescription, fetchNaics]);

  // Reset page to 1 on filter or search changes
  useEffect(() => {
    setPage(1);
  }, [search, sector, matchCompanyDescription]);


  // Copy code to clipboard
  function handleCopy(code) {
    navigator.clipboard.writeText(code);
    setCopiedCode(code);
    setTimeout(() => setCopiedCode(null), 2000);
  }

  // Toggle expanded description
  function toggleExpand(code) {
    setExpandedCodes((prev) => ({
      ...prev,
      [code]: !prev[code],
    }));
  }

  // Reset and close modal
  function closeModal() {
    setShowModal(false);
    setManualCode('');
    setManualTitle('');
    setManualDesc('');
    setSelectedFile(null);
    setModalError('');
    setModalSuccess('');
    setModalLoading(false);
  }

  // Manual code submission
  async function handleManualSubmit(e) {
    e.preventDefault();
    setModalError('');
    setModalSuccess('');
    setModalLoading(true);

    try {
      await api.addNaicsCode({
        code: manualCode,
        title: manualTitle,
        description: manualDesc,
      });
      setModalSuccess('NAICS Code successfully saved!');
      setTimeout(() => {
        closeModal();
        fetchNaics();
      }, 1500);
    } catch (err) {
      setModalError(err.message || 'Failed to save NAICS code.');
    } finally {
      setModalLoading(false);
    }
  }

  // File upload change
  function handleFileChange(e) {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
    }
  }

  // File upload submission
  async function handleUploadSubmit(e) {
    e.preventDefault();
    setModalError('');
    setModalSuccess('');
    setModalLoading(true);

    if (naicsImportMode === 'document') {
      try {
        if (!naicsDocEditor.code || !naicsDocEditor.title) {
            throw new Error("Code and Title are required");
        }
        const parsed = [naicsDocEditor];
        await api.importNaicsCodes({ items: parsed, format: 'json' });
        setModalSuccess(`Successfully imported NAICS code.`);
        setNaicsDocEditor({ code: '', title: '', description: '' });
        setTimeout(() => {
          closeModal();
          fetchNaics();
        }, 1500);
      } catch (err) {
        setModalError('Invalid Input: ' + err.message);
      } finally {
        setModalLoading(false);
      }
    } else {
      if (!selectedFile) {
        setModalError('Please select a file to upload');
        setModalLoading(false);
        return;
      }
      try {
        const res = await api.importNaicsFile(selectedFile);
        setModalSuccess(res.message || 'File successfully imported!');
        setTimeout(() => {
          closeModal();
          fetchNaics();
        }, 1500);
      } catch (err) {
        setModalError(err.message || 'Failed to import file.');
      } finally {
        setModalLoading(false);
      }
    }
  }

  const totalPages = Math.ceil(total / limit) || 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-navy-900 dark:text-white sm:text-3xl">
            NAICS Code Muster
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Search, filter, and reference standard North American Industry Classification System (NAICS) codes.
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center justify-center gap-2 rounded-xl bg-brand-500 hover:bg-brand-600 px-5 py-3 text-sm font-bold text-white shadow-soft transition-all"
        >
          <Plus size={16} />
          Add NAICS Data
        </button>
      </div>

      {/* Filter / Search Bar Card */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft dark:border-navy-800 dark:bg-navy-900 space-y-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          {/* Unified search box — matches NAICS code, title, and description
              keywords from a single input, no separate "capabilities" field needed */}
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
            <input
              type="text"
              placeholder="Search by NAICS code, title, or description keywords (e.g. Software, cloud security)..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                if (matchCompanyDescription) setMatchCompanyDescription(false);
              }}
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 py-3 pl-11 pr-10 text-sm font-medium outline-none transition-all focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/20 dark:border-navy-800 dark:bg-navy-950 dark:focus:border-brand-500 dark:focus:bg-navy-900"
            />
            {search && (
              <button
                onClick={() => { setSearch(''); setMatchCompanyDescription(false); }}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-white transition-all"
                title="Clear search"
              >
                <X size={16} />
              </button>
            )}
          </div>

          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            {/* Sector select filter */}
            <div className="relative min-w-[280px]">
              <Filter className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
              <select
                value={sector}
                onChange={(e) => setSector(e.target.value)}
                className="w-full appearance-none rounded-xl border border-slate-200 bg-slate-50/50 py-3 pl-10 pr-10 text-sm font-semibold outline-none transition-all focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/20 dark:border-navy-800 dark:bg-navy-950 dark:focus:border-brand-500 dark:focus:bg-navy-900"
              >
                {NAICS_SECTORS.map((sec) => (
                  <option key={sec.value} value={sec.value}>
                    {sec.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Entity selector: choose whether to match against the parent/main company or a subsidiary */}
            {entityOptions.length > 1 && (
              <select
                value={matchEntityId}
                onChange={(e) => {
                  setMatchEntityId(e.target.value);
                  if (matchCompanyDescription) {
                    const ent = entityOptions.find((opt) => opt.id === e.target.value);
                    setSearch(ent?.description || '');
                  }
                }}
                className="rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm font-semibold text-slate-600 outline-none transition-all focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 dark:border-navy-800 dark:bg-navy-900 dark:text-slate-300"
                title="Choose which company entity's description to match"
              >
                {entityOptions.map((ent) => (
                  <option key={ent.id} value={ent.id}>
                    {ent.name} {ent.isParent ? '(Main Company)' : '(Subsidiary)'}
                  </option>
                ))}
              </select>
            )}

            {/* Company Description Toggle — auto-fills the search bar above with
                your own company's description so results match it */}
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
                setSearch(nextVal ? entity.description : '');
              }}
              className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-bold border transition-all ${
                matchCompanyDescription
                  ? 'bg-brand-500 text-white border-brand-500 shadow-md shadow-brand-500/20'
                  : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 dark:bg-navy-900 dark:text-slate-400 dark:border-navy-800 dark:hover:bg-navy-800'
              }`}
              title="Automatically matches NAICS codes related to the selected entity's profile description"
            >
              <BookOpen size={16} />
              Match {entityOptions.length > 1 ? getSelectedEntity()?.name || 'Company' : 'Company'} Description
            </button>

            {/* Top Pagination Control next to sector filter */}
            {total > 0 && (
              <div className="flex items-center gap-3 bg-slate-50/70 px-4 py-2 rounded-xl border border-slate-200 dark:border-navy-800 dark:bg-navy-950/40">
                <button
                  onClick={() => {
                    const prevP = Math.max(1, page - 1);
                    setPage(prevP);
                    fetchNaics(prevP, search, sector, matchCompanyDescription);
                  }}
                  disabled={page === 1}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-all hover:bg-slate-50 disabled:opacity-50 disabled:hover:bg-white dark:border-navy-700 dark:bg-navy-800 dark:text-slate-400 dark:hover:bg-navy-750"
                  title="Previous Page"
                >
                  <ChevronLeft size={18} />
                </button>
                <span className="text-xs font-bold text-slate-600 dark:text-slate-400 whitespace-nowrap min-w-[48px] text-center">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => {
                    const nextP = Math.min(totalPages, page + 1);
                    setPage(nextP);
                    fetchNaics(nextP, search, sector, matchCompanyDescription);
                  }}
                  disabled={page === totalPages}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-all hover:bg-slate-50 disabled:opacity-50 disabled:hover:bg-white dark:border-navy-700 dark:bg-navy-800 dark:text-slate-400 dark:hover:bg-navy-750"
                  title="Next Page"
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Results table */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft dark:border-navy-800 dark:bg-navy-900">
        {loading && items.length === 0 ? (
          <div className="flex h-64 items-center justify-center gap-2 text-slate-500">
            <RefreshCw className="h-5 w-5 animate-spin" />
            <span className="text-sm font-medium">Loading NAICS descriptions...</span>
          </div>
        ) : items.length === 0 ? (
          <div className="flex h-64 flex-col items-center justify-center text-slate-500">
            <BookOpen className="mb-2 h-10 w-10 text-slate-300 dark:text-slate-700" />
            <p className="text-sm font-semibold">No NAICS codes found matching your criteria.</p>
            <p className="text-xs text-slate-400">Try adjusting your search terms or selecting a different sector.</p>
          </div>
        ) : (
          <>
            {/* Desktop Table View */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50/70 text-xs font-bold uppercase tracking-wider text-slate-500 dark:border-navy-800 dark:bg-navy-950 dark:text-slate-400">
                    <th className="px-6 py-4 w-32">Code</th>
                    <th className="px-6 py-4 w-64">Title</th>
                    <th className="px-6 py-4">Description</th>
                    <th className="px-6 py-4 text-center w-24">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-navy-800">
                  {items.map((item) => {
                    const isExpanded = expandedCodes[item.code];
                    const hasLongDesc = item.description && item.description.length > 200;
                    const displayDesc = hasLongDesc && !isExpanded
                      ? `${item.description.slice(0, 200)}...`
                      : item.description;

                    return (
                      <tr key={item.code} className="hover:bg-slate-50/50 dark:hover:bg-navy-950/20">
                        {/* Code Badge */}
                        <td className="whitespace-nowrap px-6 py-4">
                          <span className="inline-flex items-center rounded-lg bg-brand-50 px-2.5 py-1 text-xs font-bold text-brand-600 dark:bg-brand-500/10 dark:text-brand-400">
                            {item.code}
                          </span>
                        </td>

                        {/* Title */}
                        <td className="px-6 py-4 font-bold text-navy-900 dark:text-white">
                          {item.title}
                        </td>

                        {/* Description */}
                        <td className="px-6 py-4 text-slate-600 dark:text-slate-300 max-w-md">
                          <p className="text-xs leading-relaxed">
                            {displayDesc || <span className="italic text-slate-400">No description available</span>}
                          </p>
                          {hasLongDesc && (
                            <button
                              onClick={() => toggleExpand(item.code)}
                              className="mt-1 text-[11px] font-bold text-brand-500 hover:text-brand-600 outline-none"
                            >
                              {isExpanded ? 'Show less' : 'Read more'}
                            </button>
                          )}
                        </td>

                        {/* Action buttons */}
                        <td className="whitespace-nowrap px-6 py-4 text-center">
                          <button
                            onClick={() => handleCopy(item.code)}
                            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border transition-all ${
                              copiedCode === item.code
                                ? 'border-green-200 bg-green-50 text-green-600 dark:border-green-500/20 dark:bg-green-500/10 dark:text-green-400'
                                : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:text-slate-700 dark:border-navy-700 dark:bg-navy-800 dark:hover:border-navy-600 dark:hover:text-white'
                            }`}
                            title="Copy NAICS Code"
                          >
                            {copiedCode === item.code ? (
                              <>
                                <Check size={13} />
                                <span>Copied!</span>
                              </>
                            ) : (
                              <>
                                <Copy size={13} />
                                <span>Copy</span>
                              </>
                            )}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile Card List View */}
            <div className="block md:hidden divide-y divide-slate-100 dark:divide-navy-800">
              {items.map((item) => {
                const isExpanded = expandedCodes[item.code];
                const hasLongDesc = item.description && item.description.length > 200;
                const displayDesc = hasLongDesc && !isExpanded
                  ? `${item.description.slice(0, 200)}...`
                  : item.description;

                return (
                  <div key={item.code} className="p-4 space-y-3 hover:bg-slate-50/40 dark:hover:bg-navy-800/40 transition-colors">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <span className="inline-flex items-center rounded-lg bg-brand-50 px-2.5 py-1 text-xs font-bold text-brand-600 dark:bg-brand-500/10 dark:text-brand-400 mb-2">
                          {item.code}
                        </span>
                        <h4 className="font-bold text-navy-900 dark:text-white text-sm leading-snug">
                          {item.title}
                        </h4>
                      </div>
                      
                      <button
                        onClick={() => handleCopy(item.code)}
                        className={`shrink-0 inline-flex items-center gap-1 px-2.5 py-1 text-xs font-bold rounded-lg border transition-all ${
                          copiedCode === item.code
                            ? 'border-green-200 bg-green-50 text-green-600 dark:border-green-500/20 dark:bg-green-500/10 dark:text-green-400'
                            : 'border-slate-200 bg-white text-slate-500 hover:border-slate-350 hover:text-slate-700 dark:border-navy-700 dark:bg-navy-800 dark:hover:border-navy-600 dark:hover:text-white'
                        }`}
                      >
                        {copiedCode === item.code ? <Check size={12} /> : <Copy size={12} />}
                        <span>{copiedCode === item.code ? 'Copied' : 'Copy'}</span>
                      </button>
                    </div>

                    {item.description && (
                      <div className="text-xs text-slate-600 dark:text-slate-350 leading-relaxed bg-slate-50/80 dark:bg-navy-950 p-2.5 rounded-xl border border-slate-100/40 dark:border-navy-800/30">
                        <p>{displayDesc}</p>
                        {hasLongDesc && (
                          <button
                            onClick={() => toggleExpand(item.code)}
                            className="mt-1.5 text-[11px] font-bold text-brand-500 hover:text-brand-600 outline-none"
                          >
                            {isExpanded ? 'Show less' : 'Read more'}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )
}

        {/* Pagination bar */}
        {total > 0 && (
          <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/50 px-6 py-4 dark:border-navy-800 dark:bg-navy-950">
            <div className="text-xs font-semibold text-slate-500">
              Showing <span className="text-navy-900 dark:text-white">{Math.min(total, (page - 1) * limit + 1)}</span> to{' '}
              <span className="text-navy-900 dark:text-white">{Math.min(total, page * limit)}</span> of{' '}
              <span className="text-navy-900 dark:text-white">{total}</span> codes
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  const prevP = Math.max(1, page - 1);
                  setPage(prevP);
                  fetchNaics(prevP, search, sector, matchCompanyDescription);
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                disabled={page === 1}
                className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-all hover:bg-slate-55 disabled:opacity-50 disabled:hover:bg-white dark:border-navy-700 dark:bg-navy-800 dark:text-slate-400 dark:hover:bg-navy-750"
              >
                <ChevronLeft size={18} />
              </button>

              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">
                Page {page} of {totalPages}
              </div>

              <button
                onClick={() => {
                  const nextP = Math.min(totalPages, page + 1);
                  setPage(nextP);
                  fetchNaics(nextP, search, sector, matchCompanyDescription);
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                disabled={page === totalPages}
                className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-all hover:bg-slate-55 disabled:opacity-50 disabled:hover:bg-white dark:border-navy-700 dark:bg-navy-800 dark:text-slate-400 dark:hover:bg-navy-750"
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/60 backdrop-blur-sm">
          <div className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 shadow-xl dark:border-navy-800 dark:bg-navy-900 animate-in fade-in zoom-in-95 duration-150">
            {/* Close Button */}
            <button
              onClick={closeModal}
              className="absolute right-4 top-4 rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:text-slate-500 dark:hover:bg-navy-800 dark:hover:text-white"
            >
              <X size={20} />
            </button>

            <h3 className="text-lg font-bold text-navy-900 dark:text-white">Add NAICS Code Data</h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Add new codes to the database manually or import bulk data files.
            </p>

            {/* Tabs */}
            <div className="mt-4 flex gap-1 overflow-x-auto border-b border-slate-100 dark:border-navy-800">
              <button
                onClick={() => setModalTab('manual')}
                className={`shrink-0 whitespace-nowrap pb-2.5 text-xs font-bold transition-all border-b-2 px-4 ${
                  modalTab === 'manual'
                    ? 'border-brand-500 text-brand-600 dark:text-brand-400'
                    : 'border-transparent text-slate-400 hover:text-slate-600'
                }`}
              >
                Manual Input
              </button>
              <button
                onClick={() => setModalTab('upload')}
                className={`shrink-0 whitespace-nowrap pb-2.5 text-xs font-bold transition-all border-b-2 px-4 ${
                  modalTab === 'upload'
                    ? 'border-brand-500 text-brand-600 dark:text-brand-400'
                    : 'border-transparent text-slate-400 hover:text-slate-600'
                }`}
              >
                Upload File (CSV/JSON)
              </button>
            </div>

            {/* Error Message */}
            {modalError && (
              <div className="mt-4 rounded-xl bg-rose-50 p-3 text-xs font-semibold text-rose-600 dark:bg-rose-500/10 dark:text-rose-400">
                {modalError}
              </div>
            )}
            {/* Success Message */}
            {modalSuccess && (
              <div className="mt-4 rounded-xl bg-green-50 p-3 text-xs font-semibold text-green-600 dark:bg-green-500/10 dark:text-green-400">
                {modalSuccess}
              </div>
            )}

            {modalTab === 'manual' ? (
              <form onSubmit={handleManualSubmit} className="mt-4 space-y-4">
                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide dark:text-slate-400">
                    NAICS Code <span className="text-rose-500 font-extrabold ml-0.5">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. 541511"
                    value={manualCode}
                    onChange={(e) => setManualCode(e.target.value)}
                    className="mt-1.5 w-full rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-2.5 text-sm font-medium outline-none transition-all focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/20 dark:border-navy-800 dark:bg-navy-950 dark:focus:border-brand-500 dark:focus:bg-navy-900"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide dark:text-slate-400">
                    Title <span className="text-rose-500 font-extrabold ml-0.5">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Custom Computer Programming Services"
                    value={manualTitle}
                    onChange={(e) => setManualTitle(e.target.value)}
                    className="mt-1.5 w-full rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-2.5 text-sm font-medium outline-none transition-all focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/20 dark:border-navy-800 dark:bg-navy-950 dark:focus:border-brand-500 dark:focus:bg-navy-900"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-500 uppercase tracking-wide dark:text-slate-400">
                    Description <span className="text-[10px] text-slate-400 font-normal ml-1 flex-inline normal-case tracking-normal">(Optional)</span>
                  </label>
                  <textarea
                    rows={3}
                    placeholder="Write detailed industry descriptions..."
                    value={manualDesc}
                    onChange={(e) => setManualDesc(e.target.value)}
                    className="mt-1.5 w-full rounded-xl border border-slate-200 bg-slate-50/50 px-4 py-2.5 text-sm font-medium outline-none transition-all focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/20 dark:border-navy-800 dark:bg-navy-950 dark:focus:border-brand-500 dark:focus:bg-navy-900 resize-none"
                  />
                </div>

                <div className="mt-6 flex justify-end gap-3">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="rounded-xl border border-slate-200 px-5 py-2.5 text-sm font-bold text-slate-500 hover:bg-slate-50 dark:border-navy-800 dark:text-slate-400 dark:hover:bg-navy-950"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={modalLoading}
                    className="flex items-center justify-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-bold text-white shadow-soft transition-all hover:bg-brand-600 hover:shadow-none disabled:opacity-50"
                  >
                    {modalLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : 'Save Code'}
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleUploadSubmit} className="mt-4 space-y-4">
                <div className="space-y-3">
                  {/* Import method selection */}
                  <div className="flex items-center gap-2 mb-3">
                    <button
                      type="button"
                      onClick={() => setNaicsImportMode('document')}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                        naicsImportMode === 'document'
                          ? 'bg-brand-500 text-white'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300'
                      }`}
                    >
                      Document Editor
                    </button>
                    <button
                      type="button"
                      onClick={() => setNaicsImportMode('file')}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                        naicsImportMode === 'file'
                          ? 'bg-brand-500 text-white'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-navy-800 dark:text-slate-300'
                      }`}
                    >
                      Upload File
                    </button>
                  </div>

                  {naicsImportMode === 'document' ? (
                      <div className="rounded-xl border border-slate-200 dark:border-navy-700 bg-slate-50 dark:bg-navy-900 p-4 font-mono text-xs shadow-sm overflow-x-auto space-y-2 mb-2">
                        <div className="text-slate-400 dark:text-slate-500 font-bold">{"{"}</div>
                        <div className="pl-3 space-y-2.5">
                          {/* Code */}
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="w-32 shrink-0 flex items-center">
                              <span className="text-brand-600 dark:text-brand-400 font-bold">"code"</span>
                              <span className="text-rose-500 font-extrabold ml-0.5" title="Required field">*</span>
                            </div>
                            <span className="text-slate-400 font-bold">:</span>
                            <span className="rounded bg-brand-50 dark:bg-navy-800 text-brand-700 dark:text-brand-300 border border-brand-200/60 dark:border-navy-700 px-1.5 py-0.5 text-[10px] font-semibold w-24 text-center shrink-0">
                              [string/int]
                            </span>
                            <input 
                              value={naicsDocEditor.code} 
                              onChange={e => setNaicsDocEditor({...naicsDocEditor, code: e.target.value})} 
                              className="flex-1 min-w-[160px] rounded-lg border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-800 px-3 py-1.5 text-xs text-navy-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-brand-400 outline-none" 
                              placeholder='"541512"' 
                            />
                          </div>

                          {/* Title */}
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="w-32 shrink-0 flex items-center">
                              <span className="text-brand-600 dark:text-brand-400 font-bold">"title"</span>
                              <span className="text-rose-500 font-extrabold ml-0.5" title="Required field">*</span>
                            </div>
                            <span className="text-slate-400 font-bold">:</span>
                            <span className="rounded bg-brand-50 dark:bg-navy-800 text-brand-700 dark:text-brand-300 border border-brand-200/60 dark:border-navy-700 px-1.5 py-0.5 text-[10px] font-semibold w-24 text-center shrink-0">
                              [string]
                            </span>
                            <input 
                              value={naicsDocEditor.title} 
                              onChange={e => setNaicsDocEditor({...naicsDocEditor, title: e.target.value})} 
                              className="flex-1 min-w-[160px] rounded-lg border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-800 px-3 py-1.5 text-xs text-navy-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-brand-400 outline-none" 
                              placeholder='"Computer Systems Design Services"' 
                            />
                          </div>

                          {/* Description */}
                          <div className="flex flex-wrap items-start gap-2">
                            <div className="w-32 shrink-0 flex items-center pt-1.5">
                              <span className="text-brand-600 dark:text-brand-400 font-bold">"description"</span>
                              <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span>
                            </div>
                            <span className="text-slate-400 font-bold pt-1.5">:</span>
                            <span className="rounded bg-brand-50 dark:bg-navy-800 text-brand-700 dark:text-brand-300 border border-brand-200/60 dark:border-navy-700 px-1.5 py-0.5 text-[10px] font-semibold w-24 text-center shrink-0 mt-1">
                              [string]
                            </span>
                            <textarea 
                              rows={3}
                              value={naicsDocEditor.description} 
                              onChange={e => setNaicsDocEditor({...naicsDocEditor, description: e.target.value})} 
                              className="flex-1 min-w-[160px] rounded-lg border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-800 px-3 py-1.5 text-xs text-navy-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-brand-400 outline-none resize-y" 
                              placeholder='"Establishments primarily engaged in planning and designing computer systems..."' 
                            />
                          </div>
                        </div>
                        <div className="text-slate-400 dark:text-slate-500 font-bold">{"}"}</div>
                      </div>
                  ) : (
                    <div
                      className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 dark:border-navy-600 p-8 text-center cursor-pointer hover:border-brand-400 transition-colors"
                      onClick={() => document.getElementById('naics-file-input').click()}
                    >
                      <Upload className="text-slate-300 dark:text-slate-600 mb-2" size={32} />
                      <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">
                        {selectedFile ? selectedFile.name : 'Click to upload CSV or JSON file'}
                      </p>
                      <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">Supports .csv, .json</p>
                      <input
                        id="naics-file-input"
                        type="file"
                        accept=".csv,.json"
                        className="hidden"
                        onChange={handleFileChange}
                      />
                    </div>
                  )}
                </div>

                <div className="mt-6 flex justify-end gap-3">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="rounded-xl border border-slate-200 px-5 py-2.5 text-sm font-bold text-slate-500 hover:bg-slate-50 dark:border-navy-800 dark:text-slate-400 dark:hover:bg-navy-950"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={
                      modalLoading || 
                      (naicsImportMode === 'file' && !selectedFile) || 
                      (naicsImportMode === 'document' && (!naicsDocEditor.code || !naicsDocEditor.title))
                    }
                    className="flex items-center justify-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-bold text-white shadow-soft transition-all hover:bg-brand-600 hover:shadow-none disabled:opacity-50"
                  >
                    {modalLoading ? <RefreshCw className="h-4 w-4 animate-spin" /> : 'Import Data'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
