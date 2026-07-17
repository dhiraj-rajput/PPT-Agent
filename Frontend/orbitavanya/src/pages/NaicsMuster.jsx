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

  async function fetchNaics() {
    setLoading(true);
    try {
      const res = await api.getNaicsCodes({
        search,
        sector,
        page,
        limit,
      });
      setItems(res.items || []);
      setTotal(res.total || 0);
    } catch (err) {
      console.error('Error fetching NAICS codes:', err);
    } finally {
      setLoading(false);
    }
  }

  // Refetch when page or filters change
  useEffect(() => {
    fetchNaics();
  }, [page, sector]);

  // Reset page to 1 and fetch on search submit
  function handleSearchSubmit(e) {
    e.preventDefault();
    setPage(1);
    fetchNaics();
  }

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
    if (!selectedFile) return;

    setModalError('');
    setModalSuccess('');
    setModalLoading(true);

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
          className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-brand-500 to-accent-orange px-5 py-3 text-sm font-bold text-white shadow-soft transition-all hover:opacity-90"
        >
          <Plus size={16} />
          Add NAICS Data
        </button>
      </div>

      {/* Filter / Search Bar Card */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft dark:border-navy-800 dark:bg-navy-900">
        <form onSubmit={handleSearchSubmit} className="flex flex-col gap-4 md:flex-row md:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
            <input
              type="text"
              placeholder="Search by NAICS code (e.g. 5415) or keywords (e.g. Software, Construction)..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-slate-50/50 py-3 pl-11 pr-4 text-sm font-medium outline-none transition-all focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/20 dark:border-navy-800 dark:bg-navy-950 dark:focus:border-brand-500 dark:focus:bg-navy-900"
            />
          </div>

          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <div className="relative min-w-[240px]">
              <Filter className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500" />
              <select
                value={sector}
                onChange={(e) => {
                  setSector(e.target.value);
                  setPage(1);
                }}
                className="w-full appearance-none rounded-xl border border-slate-200 bg-slate-50/50 py-3 pl-10 pr-10 text-sm font-semibold outline-none transition-all focus:border-brand-500 focus:bg-white focus:ring-2 focus:ring-brand-500/20 dark:border-navy-800 dark:bg-navy-950 dark:focus:border-brand-500 dark:focus:bg-navy-900"
              >
                {NAICS_SECTORS.map((sec) => (
                  <option key={sec.value} value={sec.value}>
                    {sec.label}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="submit"
              className="flex items-center justify-center gap-2 rounded-xl bg-brand-500 px-6 py-3 text-sm font-bold text-white shadow-soft transition-all hover:bg-brand-600 hover:shadow-none"
            >
              Search
            </button>
          </div>
        </form>
      </div>

      {/* Results table */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-soft dark:border-navy-800 dark:bg-navy-900">
        {loading ? (
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
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/70 text-xs font-bold uppercase tracking-wider text-slate-500 dark:border-navy-800 dark:bg-navy-950 dark:text-slate-400">
                  <th className="px-6 py-4">Code</th>
                  <th className="px-6 py-4">Title</th>
                  <th className="px-6 py-4">Description</th>
                  <th className="px-6 py-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-navy-800">
                {items.map((item) => {
                  const isExpanded = expandedCodes[item.code];
                  const hasLongDesc = item.description && item.description.length > 180;
                  const displayDesc = hasLongDesc && !isExpanded
                    ? `${item.description.slice(0, 180)}...`
                    : item.description;

                  return (
                    <tr key={item.code} className="hover:bg-slate-50/50 dark:hover:bg-navy-950/20">
                      {/* Code Badge */}
                      <td className="whitespace-nowrap px-6 py-4">
                        <span className="inline-flex items-center gap-1 rounded-lg bg-brand-50/80 px-2.5 py-1 text-xs font-bold text-brand-600 dark:bg-brand-500/10 dark:text-brand-400">
                          <Hash size={12} />
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
                      <td className="whitespace-nowrap px-6 py-4 text-right">
                        <button
                          onClick={() => handleCopy(item.code)}
                          className={`inline-flex h-8 w-8 items-center justify-center rounded-lg border transition-all ${
                            copiedCode === item.code
                              ? 'border-green-200 bg-green-50 text-green-600 dark:border-green-500/20 dark:bg-green-500/10 dark:text-green-400'
                              : 'border-slate-200 bg-white text-slate-400 hover:border-slate-300 hover:text-slate-600 dark:border-navy-700 dark:bg-navy-800 dark:hover:border-navy-600 dark:hover:text-white'
                          }`}
                          title="Copy NAICS Code"
                        >
                          {copiedCode === item.code ? <Check size={14} /> : <Copy size={14} />}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

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
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-all hover:bg-slate-50 disabled:opacity-50 disabled:hover:bg-white dark:border-navy-700 dark:bg-navy-800 dark:hover:bg-navy-700"
              >
                <ChevronLeft size={16} />
              </button>

              <div className="text-xs font-bold text-slate-600 dark:text-slate-400">
                Page {page} of {totalPages}
              </div>

              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-all hover:bg-slate-50 disabled:opacity-50 disabled:hover:bg-white dark:border-navy-700 dark:bg-navy-800 dark:hover:bg-navy-700"
              >
                <ChevronRight size={16} />
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
            <div className="mt-4 flex border-b border-slate-100 dark:border-navy-800">
              <button
                onClick={() => setModalTab('manual')}
                className={`pb-2.5 text-xs font-bold transition-all border-b-2 px-4 ${
                  modalTab === 'manual'
                    ? 'border-brand-500 text-brand-600 dark:text-brand-400'
                    : 'border-transparent text-slate-400 hover:text-slate-600'
                }`}
              >
                Manual Input
              </button>
              <button
                onClick={() => setModalTab('upload')}
                className={`pb-2.5 text-xs font-bold transition-all border-b-2 px-4 ${
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
                    NAICS Code
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
                    Title
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
                    Description
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
                <div className="rounded-xl border-2 border-dashed border-slate-200 p-6 text-center dark:border-navy-800">
                  <input
                    type="file"
                    id="naics-file-input"
                    accept=".csv,.json"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  <label htmlFor="naics-file-input" className="cursor-pointer space-y-2 block">
                    <Upload className="mx-auto h-8 w-8 text-slate-400 dark:text-slate-500" />
                    <p className="text-sm font-semibold text-navy-900 dark:text-white">
                      {selectedFile ? selectedFile.name : 'Select CSV or JSON file'}
                    </p>
                    <p className="text-xs text-slate-400">
                      Files must match NAICS format containing Code, Title, Description
                    </p>
                  </label>
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
                    disabled={modalLoading || !selectedFile}
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
