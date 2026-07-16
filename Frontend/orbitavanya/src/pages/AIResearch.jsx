import { useState, useEffect, useCallback } from 'react';
import {
  Sparkles, Search, Building2, TrendingUp, ShieldCheck, Target,
  RefreshCw, Cpu, Award, Zap, AlertTriangle, AlertCircle,
  Mail, Phone, ExternalLink, ChevronLeft, ChevronRight
} from 'lucide-react';
import { PageHeader, Card, MatchBadge } from '../components/ui/Common.jsx';

const PAGE_SIZE = 10; // companies shown per "page" in the left panel

const cleanDescriptionText = (text) => {
  if (!text) return '';
  return text
    .replace(/(?:sign in|welcome back|forgot password|join now|cookie policy|user agreement|privacy policy|linkedin member|view all employees|report this post|followers|followers count|get directions|by clicking continue|continue to join|show password|email or phone password|see all employees locations|locations primary|updates kano|updates hope)/gi, '')
    .replace(/we were honoured to welcome.*/gi, '')
    .replace(/together, we continue to.*/gi, '')
    .replace(/we appreciate the interest shown by.*/gi, '')
    .replace(/looking forward to fostering.*/gi, '')
    .replace(/\s+/g, ' ')
    .trim();
};

export default function AIResearch() {
  const [companiesList, setCompaniesList] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [selectedCompany, setSelectedCompany] = useState(null);
  const [selectedProfile, setSelectedProfile] = useState(null);
  const [searchInput, setSearchInput] = useState('');
  const [newCompanyInput, setNewCompanyInput] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [isResearching, setIsResearching] = useState(false);
  const [researchTaskKey, setResearchTaskKey] = useState(null);
  const [researchProgress, setResearchProgress] = useState(0);
  const [researchMessage, setResearchMessage] = useState('');
  const [activeTab, setActiveTab] = useState('overview');
  // Pagination state for the company list
  const [currentPage, setCurrentPage] = useState(1);

  // ─── Fetch helpers ───────────────────────────────────────────────────────────

  const fetchCompanies = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/companies?limit=1000');
      if (res.ok) {
        const data = await res.json();
        const list = data.companies || [];
        setCompaniesList(list);

        // Check if there is a query parameter "q" in the URL
        const params = new URLSearchParams(window.location.search);
        const qParam = params.get('q');
        let initialSelection = null;

        if (qParam) {
          const qLower = qParam.toLowerCase();
          initialSelection = list.find(c =>
            c.name.toLowerCase().includes(qLower) ||
            qLower.includes(c.name.toLowerCase())
          );
        }

        if (initialSelection) {
          setSelectedCompany(initialSelection);
        } else {
          // Default selection — only if no research is already active
          if (list.length > 0 && !selectedCompany) {
            setSelectedCompany(list[0]);
          }
          // If we reconnected to an active task, upgrade the placeholder
          // selectedCompany to the real entry from the list
          setSelectedCompany(prev => {
            if (!prev) return list[0] || null;
            // If the current selection looks like a placeholder (no uei/industry properly set)
            const isPlaceholder = !prev.uei;
            if (!isPlaceholder) return prev; // already a real entry
            const match = list.find(c =>
              c.name.toLowerCase().includes((prev.name || '').toLowerCase().split(' ')[0]) ||
              (prev.name || '').toLowerCase().includes(c.name.toLowerCase().split(' ')[0])
            );
            return match || prev;
          });
        }
      }
    } catch (err) {
      console.error('Error fetching companies:', err);
    }
  };

  const fetchProfiles = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/companies/profiles');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          setProfiles(data);
          return data;
        }
      }
      setProfiles([]);
      return [];
    } catch (err) {
      console.error('Error fetching profiles:', err);
      setProfiles([]);
      return [];
    }
  };

  useEffect(() => {
    fetchCompanies();
    fetchProfiles();
    reconnectActiveTask();
  }, []);

  /**
   * On mount: check if any research task is currently in-progress on the backend.
   * If found, restore the isResearching state so the progress bar shows immediately
   * — even if the user navigated away and came back mid-run.
   */
  const reconnectActiveTask = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/companies/research/status');
      if (!res.ok) return;
      const tasks = await res.json();
      // Find the first task that is still processing
      const activeEntry = Object.entries(tasks).find(
        ([, v]) => v.status === 'processing'
      );
      if (activeEntry) {
        const [taskKey, taskData] = activeEntry;
        setResearchTaskKey(taskKey);
        setResearchProgress(taskData.progress || 10);
        setResearchMessage(taskData.message || 'Research in progress...');
        setIsResearching(true);
        // Pre-fill the input box so the user can see what's running
        setNewCompanyInput(taskKey);
        // Pre-select company in the sidebar if we can match it
        // (will be refined once companiesList loads via fetchCompanies)
        setSelectedCompany({ name: taskKey, industry: 'Research in progress...' });
      }
    } catch {
      // Silently ignore — status endpoint may not be up yet
    }
  };

  // ─── Profile matching ─────────────────────────────────────────────────────────

  /**
   * Robust multi-signal company ↔ profile matcher.
   * Checks: exact slug, name slug, website substring, token overlap.
   */
  const matchProfile = useCallback((company, profileList) => {
    if (!company || !profileList?.length) return null;

    const companyName = (company.name || '').toLowerCase().trim();

    // Helper: slug from a string
    const toSlug = (str) =>
      (str || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

    const companySlug = toSlug(companyName);

    // Strip URL scheme/trailing slashes so URLs become a bare domain
    const stripUrl = (str) =>
      (str || '').replace(/^https?:\/\//, '').replace(/\/$/, '').split('/')[0].toLowerCase();

    const companyDomain = stripUrl(companyName); // in case name is a URL

    // Token match — min 2 chars, ignore very common words
    const STOP = new Set(['inc', 'llc', 'ltd', 'corp', 'co', 'and', 'the', 'for',
      'solutions', 'systems', 'services', 'technologies', 'group', 'global']);
    const tokenize = (str) =>
      (str || '').toLowerCase().replace(/[^a-z0-9\s]+/g, '').split(/\s+/)
        .filter(t => t.length >= 2 && !STOP.has(t));

    const companyTokens = tokenize(companyName);

    return profileList.find(p => {
      const pName = (p.company_name || '').toLowerCase();
      const pSlug = (p.company_slug || '').toLowerCase();
      const pNameSlug = (p.company_name_slug || toSlug(pName));
      const pWebsite = stripUrl(p.website || '');

      // 1. Exact slug match (both directions)
      if (pSlug === companySlug || pNameSlug === companySlug) return true;

      // 2. Website domain substring match (handles "infosys.com" input)
      if (companyDomain && pWebsite && (pWebsite.includes(companyDomain) || companyDomain.includes(pWebsite))) return true;

      // 3. Token overlap: at least 1 meaningful shared token
      if (companyTokens.length > 0) {
        const pTokens = tokenize(pName);
        if (pTokens.length > 0 && companyTokens.some(t => pTokens.includes(t))) return true;
        // First token exact match is strong signal
        if (companyTokens[0] && pTokens[0] && companyTokens[0] === pTokens[0]) return true;
      }

      return false;
    }) || null;
  }, []);

  // Update selectedProfile whenever selectedCompany or profiles changes
  useEffect(() => {
    if (selectedCompany && profiles.length > 0) {
      setSelectedProfile(matchProfile(selectedCompany, profiles));
    } else {
      setSelectedProfile(null);
    }
  }, [selectedCompany, profiles, matchProfile]);

  // ─── Research polling ─────────────────────────────────────────────────────────

  useEffect(() => {
    let timer;
    if (isResearching && researchTaskKey) {
      timer = setInterval(async () => {
        try {
          const res = await fetch('http://localhost:8000/api/companies/research/status');
          const tasks = await res.json();
          const task = tasks[researchTaskKey];
          if (task) {
            setResearchProgress(task.progress || 0);
            setResearchMessage(task.message || 'Running research agent pipeline...');

            if (task.status === 'completed') {
              setIsResearching(false);
              setResearchTaskKey(null);

              // ── Reliable post-research profile fetch ──
              // Use the new /profiles/search endpoint which matches on name, website, AND slug
              try {
                const searchRes = await fetch(
                  `http://localhost:8000/api/companies/profiles/search?q=${encodeURIComponent(researchTaskKey)}`
                );
                if (searchRes.ok) {
                  const foundProfile = await searchRes.json();
                  // Re-fetch all profiles to update the list state
                  const allProfiles = await fetchProfiles();
                  setSelectedProfile(foundProfile);
                  // Also sync selectedCompany name display
                  const matchInList = companiesList.find(c =>
                    matchProfile(c, [foundProfile])
                  );
                  if (matchInList) {
                    setSelectedCompany(matchInList);
                  } else {
                    setSelectedCompany({ name: foundProfile.company_name || researchTaskKey });
                  }
                } else {
                  // Fallback: refresh all profiles and re-run matcher
                  const allProfiles = await fetchProfiles();
                  const found = allProfiles.find(p => matchProfile({ name: researchTaskKey }, [p]));
                  if (found) setSelectedProfile(found);
                }
              } catch {
                await fetchProfiles();
              }

            } else if (task.status === 'failed') {
              setIsResearching(false);
              setResearchMessage(task.message || 'Research pipeline failed.');
            }
          }
        } catch (err) {
          console.error('Error polling status:', err);
        }
      }, 2000);
    }
    return () => clearInterval(timer);
  }, [isResearching, researchTaskKey, companiesList, matchProfile]);

  // ─── Action handlers ──────────────────────────────────────────────────────────

  const handleStartResearch = async (e) => {
    e.preventDefault();
    if (!newCompanyInput.trim()) return;
    const inputVal = newCompanyInput.trim();
    setIsResearching(true);
    setResearchProgress(5);
    setResearchMessage('Initializing research task...');
    setResearchTaskKey(inputVal);

    // Optimistic sidebar selection
    const matchInList = companiesList.find(c => matchProfile(c, [{ company_name: inputVal, website: inputVal }]));
    if (matchInList) {
      setSelectedCompany(matchInList);
    } else {
      setSelectedCompany({ name: inputVal, industry: 'Researching...' });
    }
    setSelectedProfile(null);

    try {
      const res = await fetch('http://localhost:8000/api/companies/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company: inputVal, force: true }),
      });
      const data = await res.json();
      if (data && data.task_key) {
        setResearchTaskKey(data.task_key);
      }
    } catch (err) {
      console.error('Failed to trigger research:', err);
      setIsResearching(false);
      setResearchMessage('Failed to trigger research pipeline.');
    }
  };

  const handleRegenerate = async (companyName) => {
    if (!companyName) return;
    setIsResearching(true);
    setResearchProgress(5);
    setResearchMessage('Re-initializing research task...');
    setResearchTaskKey(companyName.trim());

    try {
      const res = await fetch('http://localhost:8000/api/companies/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company: companyName, force: true }),
      });
      const data = await res.json();
      if (data && data.task_key) {
        setResearchTaskKey(data.task_key);
      }
    } catch (err) {
      console.error('Failed to trigger research:', err);
      setIsResearching(false);
      setResearchMessage('Failed to trigger research pipeline.');
    }
  };

  // ─── Derived state ────────────────────────────────────────────────────────────

  const filteredCompanies = companiesList.filter(c =>
    c.name.toLowerCase().includes(searchInput.toLowerCase()) ||
    (c.industry && c.industry.toLowerCase().includes(searchInput.toLowerCase()))
  );

  const totalPages = Math.ceil(filteredCompanies.length / PAGE_SIZE);
  const safePage = Math.min(currentPage, totalPages || 1);
  const pagedCompanies = filteredCompanies.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  // Reset to page 1 when search changes
  useEffect(() => { setCurrentPage(1); }, [searchInput]);

  const autocompleteSuggestions = newCompanyInput.trim().length > 1
    ? companiesList.filter(c => c.name.toLowerCase().includes(newCompanyInput.toLowerCase())).slice(0, 5)
    : [];

  const hasProfileForCompany = (c) => !!matchProfile(c, profiles);

  // ─── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Company Research & Compaction"
        subtitle="Perform deep, automated visual agent crawls & compaction on potential partners or competitors."
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* ── Left Sidebar ── */}
        <div className="space-y-6 lg:col-span-1">
          {/* Start New Research */}
          <Card className="p-5 border-brand-100 bg-brand-50/10">
            <h3 className="flex items-center gap-2 text-sm font-bold text-navy-900 dark:text-white">
              <Sparkles size={16} className="text-brand-500" />
              Start New AI Agent Research
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              Provide a company name, website homepage URL, or LinkedIn corporate page URL.
            </p>
            <form onSubmit={handleStartResearch} className="mt-4 space-y-3">
              <div className="relative">
                <input
                  type="text"
                  placeholder="e.g. guidehouse.com or Guidehouse"
                  value={newCompanyInput}
                  onChange={(e) => { setNewCompanyInput(e.target.value); setShowSuggestions(true); }}
                  onFocus={() => setShowSuggestions(true)}
                  onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
                  disabled={isResearching}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm outline-none placeholder:text-slate-400 focus:border-brand-500 dark:border-navy-700 dark:bg-navy-800"
                />
                {showSuggestions && autocompleteSuggestions.length > 0 && (
                  <div className="absolute left-0 right-0 z-30 mt-1 max-h-48 overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-lg dark:border-navy-800 dark:bg-navy-900">
                    {autocompleteSuggestions.map(s => (
                      <button
                        key={s.uei || s.name}
                        type="button"
                        onMouseDown={() => {
                          setNewCompanyInput(s.name);
                          setSelectedCompany(s);
                          setShowSuggestions(false);
                        }}
                        className="w-full px-3.5 py-2.5 text-left text-xs font-semibold text-navy-800 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-navy-800 border-b border-slate-100 dark:border-navy-800 last:border-0"
                      >
                        {s.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <button
                type="submit"
                disabled={isResearching || !newCompanyInput.trim()}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-brand-500 py-2.5 text-xs font-bold text-white shadow-md hover:bg-brand-600 disabled:opacity-50"
              >
                {isResearching ? (
                  <><RefreshCw size={14} className="animate-spin" /> Running Agents ({researchProgress}%)</>
                ) : (
                  <><Cpu size={14} /> Deploy Research Agents</>
                )}
              </button>
            </form>

            {isResearching && (
              <div className="mt-4 rounded-xl border border-blue-100 bg-blue-50/50 p-3.5 dark:border-navy-800 dark:bg-navy-900">
                <div className="flex items-center justify-between text-xs font-semibold text-blue-800 dark:text-blue-300">
                  <span>{researchMessage}</span>
                  <span>{researchProgress}%</span>
                </div>
                <div className="mt-2 h-1.5 w-full rounded-full bg-blue-100 dark:bg-navy-700">
                  <div
                    className="h-full rounded-full bg-blue-500 transition-all duration-500"
                    style={{ width: `${researchProgress}%` }}
                  />
                </div>
              </div>
            )}
          </Card>

          {/* Company List with Prev/Next Pagination */}
          <Card className="p-4">
            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 dark:border-navy-700 dark:bg-navy-800">
              <Search size={16} className="text-slate-400 shrink-0" />
              <input
                placeholder="Search companies..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400 dark:text-white"
              />
            </div>

            {/* Company Entries */}
            <div className="mt-4 space-y-2">
              {pagedCompanies.length === 0 ? (
                <p className="py-4 text-center text-xs text-slate-400">No companies found.</p>
              ) : (
                pagedCompanies.map((c) => {
                  const hasProfile = hasProfileForCompany(c);
                  return (
                    <button
                      key={c.uei || c.name}
                      onClick={() => setSelectedCompany(c)}
                      className={`flex w-full items-center justify-between rounded-xl border p-3.5 text-left transition-all ${
                        selectedCompany?.name === c.name
                          ? 'border-brand-300 bg-brand-50/50 dark:border-brand-700 dark:bg-brand-950/20'
                          : 'border-slate-100 hover:border-slate-200 dark:border-navy-800 dark:hover:border-navy-700'
                      }`}
                    >
                      <div className="space-y-0.5 max-w-[70%]">
                        <p className="truncate text-xs font-bold text-navy-900 dark:text-white">{c.name}</p>
                        <p className="truncate text-[10px] text-slate-400">{c.industry || 'General Industry'}</p>
                      </div>
                      <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold ${
                        hasProfile
                          ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400'
                          : 'bg-slate-100 text-slate-500 dark:bg-navy-800 dark:text-slate-400'
                      }`}>
                        {hasProfile ? 'Researched' : 'No Data'}
                      </span>
                    </button>
                  );
                })
              )}
            </div>

            {/* Prev / Next Pagination */}
            {totalPages > 1 && (
              <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3 dark:border-navy-800">
                <button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={safePage <= 1}
                  className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-navy-700 hover:bg-slate-50 disabled:opacity-40 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors"
                >
                  <ChevronLeft size={13} /> Prev
                </button>
                <span className="text-[10px] font-semibold text-slate-400">
                  Page {safePage} of {totalPages}
                  <span className="ml-1.5 text-slate-300 dark:text-navy-600">({filteredCompanies.length} total)</span>
                </span>
                <button
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={safePage >= totalPages}
                  className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-navy-700 hover:bg-slate-50 disabled:opacity-40 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 transition-colors"
                >
                  Next <ChevronRight size={13} />
                </button>
              </div>
            )}
          </Card>
        </div>

        {/* ── Right Pane: Profile Display ── */}
        <div className="lg:col-span-2">
          {selectedCompany ? (
            selectedProfile ? (
              <div className="space-y-6">
                {/* Header */}
                <Card className="p-6">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-3">
                        <div className="flex items-center gap-2">
                          <Building2 size={20} className="text-brand-500" />
                          <h2 className="text-lg font-bold text-navy-900 dark:text-white">{selectedProfile.company_name}</h2>
                        </div>
                        <button
                          onClick={() => handleRegenerate(selectedProfile.company_name)}
                          disabled={isResearching}
                          className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-50 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300 dark:hover:bg-navy-700 shadow-sm"
                          title="Force re-run AI agents and compaction for this company"
                        >
                          <RefreshCw size={10} className={isResearching ? 'animate-spin' : ''} />
                          Regenerate
                        </button>
                      </div>
                      <p className="text-xs text-slate-500">
                        {selectedProfile.website && (
                          <a href={selectedProfile.website} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-brand-600 hover:underline">
                            {selectedProfile.website} <ExternalLink size={10} />
                          </a>
                        )}
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-2 text-right">
                      <span className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-600 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300">
                        HQ: {selectedProfile.headquarters || 'N/A'}
                      </span>
                      <span className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-600 dark:border-navy-700 dark:bg-navy-800 dark:text-slate-300">
                        Size: {selectedProfile.employee_count || 'N/A'}
                      </span>
                    </div>
                  </div>

                  {/* Tabs */}
                  <div className="mt-6 flex border-b border-slate-200 dark:border-navy-800">
                    {['overview', 'swot', 'financials', 'techstack'].map((tab) => (
                      <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`border-b-2 px-4 py-2.5 text-xs font-bold capitalize transition-all ${
                          activeTab === tab
                            ? 'border-brand-500 text-brand-600 dark:text-white'
                            : 'border-transparent text-slate-400 hover:text-slate-600'
                        }`}
                      >
                        {tab}
                      </button>
                    ))}
                  </div>

                  {/* Overview Tab */}
                  {activeTab === 'overview' && (
                    <div className="mt-6 space-y-5 text-sm">
                      <div className="space-y-1.5">
                        <h4 className="font-bold text-navy-900 dark:text-white">Company Summary</h4>
                        <p className="text-slate-600 leading-relaxed dark:text-slate-300">{cleanDescriptionText(selectedProfile.description)}</p>
                      </div>

                      <div className="space-y-1.5">
                        <h4 className="font-bold text-navy-900 dark:text-white">Value Proposition</h4>
                        <p className="text-slate-600 leading-relaxed dark:text-slate-300">
                          {selectedProfile.value_proposition || 'Scalable consulting and custom product deployment matching the RFP context.'}
                        </p>
                      </div>

                      <div className="space-y-1.5">
                        <h4 className="font-bold text-navy-900 dark:text-white">Business & Pricing Model</h4>
                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                          <div className="rounded-xl border border-slate-100 p-3.5 dark:border-navy-800">
                            <p className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Business Model</p>
                            <p className="mt-1 text-xs font-semibold text-navy-800 dark:text-slate-200">{selectedProfile.business_model || 'Enterprise Services'}</p>
                          </div>
                          <div className="rounded-xl border border-slate-100 p-3.5 dark:border-navy-800">
                            <p className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">Pricing Strategy</p>
                            <p className="mt-1 text-xs font-semibold text-navy-800 dark:text-slate-200">{selectedProfile.pricing_model || 'Quote-based pricing'}</p>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* SWOT Tab */}
                  {activeTab === 'swot' && (
                    <div className="mt-6 space-y-5">
                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        <div className="rounded-xl border border-emerald-100 bg-emerald-50/20 p-4 dark:border-emerald-950/20">
                          <h4 className="flex items-center gap-1.5 text-xs font-bold text-emerald-800 dark:text-emerald-300">
                            <Award size={14} /> Strengths
                          </h4>
                          <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-emerald-900 dark:text-slate-300">
                            {(selectedProfile.rfp_strengths || []).length > 0
                              ? (selectedProfile.rfp_strengths || []).map((s, idx) => <li key={idx}>{s}</li>)
                              : <li className="list-none text-slate-400 italic">No strengths data available.</li>
                            }
                          </ul>
                        </div>

                        <div className="rounded-xl border border-rose-100 bg-rose-50/20 p-4 dark:border-rose-950/20">
                          <h4 className="flex items-center gap-1.5 text-xs font-bold text-rose-800 dark:text-rose-300">
                            <AlertTriangle size={14} /> Weaknesses
                          </h4>
                          <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-rose-900 dark:text-slate-300">
                            {(selectedProfile.rfp_weaknesses || []).length > 0
                              ? (selectedProfile.rfp_weaknesses || []).map((w, idx) => <li key={idx}>{w}</li>)
                              : <li className="list-none text-slate-400 italic">No weaknesses data available.</li>
                            }
                          </ul>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        <div className="rounded-xl border border-blue-100 bg-blue-50/20 p-4 dark:border-blue-950/20">
                          <h4 className="flex items-center gap-1.5 text-xs font-bold text-blue-800 dark:text-blue-300">
                            <Zap size={14} /> Opportunities
                          </h4>
                          <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-blue-900 dark:text-slate-300">
                            {(selectedProfile.opportunities || []).length > 0
                              ? (selectedProfile.opportunities || []).map((o, idx) => <li key={idx}>{o}</li>)
                              : <li className="list-none text-slate-400 italic">No opportunities data available.</li>
                            }
                          </ul>
                        </div>

                        <div className="rounded-xl border border-amber-100 bg-amber-50/20 p-4 dark:border-amber-950/20">
                          <h4 className="flex items-center gap-1.5 text-xs font-bold text-amber-800 dark:text-amber-300">
                            <AlertCircle size={14} /> Challenges / Threats
                          </h4>
                          <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-amber-900 dark:text-slate-300">
                            {(selectedProfile.challenges || []).length > 0
                              ? (selectedProfile.challenges || []).map((c, idx) => <li key={idx}>{c}</li>)
                              : <li className="list-none text-slate-400 italic">No challenges data available.</li>
                            }
                          </ul>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Financials Tab */}
                  {activeTab === 'financials' && (
                    <div className="mt-6 space-y-5">
                      <div className="space-y-2">
                        <h4 className="text-xs font-bold text-navy-900 dark:text-white">Financial Highlights</h4>
                        {(selectedProfile.financial_highlights || []).length > 0 ? (
                          <ul className="list-inside list-disc space-y-1.5 text-xs text-slate-600 dark:text-slate-300">
                            {(selectedProfile.financial_highlights || []).map((f, idx) => <li key={idx}>{f}</li>)}
                          </ul>
                        ) : (
                          <p className="text-xs text-slate-400 italic">No financial data found in public sources.</p>
                        )}
                      </div>

                      <div className="space-y-2 border-t border-slate-100 pt-4 dark:border-navy-800">
                        <h4 className="text-xs font-bold text-navy-900 dark:text-white">Identified Competitors</h4>
                        {(selectedProfile.competitors || []).length > 0 ? (
                          <div className="flex flex-wrap gap-2">
                            {(selectedProfile.competitors || []).map((c, idx) => (
                              <span key={idx} className="rounded-xl bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600 dark:bg-navy-800 dark:text-slate-300">
                                {c}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-slate-400 italic">No competitor data identified.</p>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Tech Stack Tab */}
                  {activeTab === 'techstack' && (
                    <div className="mt-6 space-y-5">
                      <div className="space-y-2">
                        <h4 className="text-xs font-bold text-navy-900 dark:text-white">Technology Stack</h4>
                        {(selectedProfile.technology_stack || []).length > 0 ? (
                          <div className="flex flex-wrap gap-2">
                            {(selectedProfile.technology_stack || []).map((t, idx) => (
                              <span key={idx} className="rounded-xl bg-blue-50/50 border border-blue-100 px-3 py-1.5 text-xs font-semibold text-blue-700 dark:bg-navy-800 dark:border-navy-700 dark:text-blue-300">
                                {t}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-slate-400 italic">No technology stack data identified.</p>
                        )}
                      </div>

                      {selectedProfile.specialties && selectedProfile.specialties.length > 0 && (
                        <div className="space-y-2 border-t border-slate-100 pt-4 dark:border-navy-800">
                          <h4 className="text-xs font-bold text-navy-900 dark:text-white">Specialties</h4>
                          <div className="flex flex-wrap gap-2">
                            {selectedProfile.specialties.map((s, idx) => (
                              <span key={idx} className="rounded-xl bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600 dark:bg-navy-800 dark:text-slate-300">
                                {s}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </Card>

                {/* Contact Info & News */}
                <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                  <Card className="p-5 space-y-4">
                    <h3 className="text-sm font-bold text-navy-900 dark:text-white">Contact Information</h3>
                    <div className="space-y-3 text-xs">
                      {selectedProfile.emails && selectedProfile.emails.length > 0 ? (
                        <div className="flex items-start gap-2.5">
                          <Mail size={14} className="text-slate-400 mt-0.5" />
                          <div>
                            <p className="font-semibold text-slate-400">Emails</p>
                            {selectedProfile.emails.map((email, idx) => (
                              <p key={idx} className="text-navy-900 dark:text-slate-200">{email}</p>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <p className="text-slate-400 italic">No email addresses found.</p>
                      )}

                      {selectedProfile.phone_numbers && selectedProfile.phone_numbers.length > 0 && (
                        <div className="flex items-start gap-2.5">
                          <Phone size={14} className="text-slate-400 mt-0.5" />
                          <div>
                            <p className="font-semibold text-slate-400">Phone Numbers</p>
                            {selectedProfile.phone_numbers.map((phone, idx) => (
                              <p key={idx} className="text-navy-900 dark:text-slate-200">{phone}</p>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </Card>

                  <Card className="p-5 space-y-4">
                    <h3 className="text-sm font-bold text-navy-900 dark:text-white">Recent News / Search Insights</h3>
                    <div className="space-y-3 max-h-[200px] overflow-y-auto pr-1">
                      {(selectedProfile.recent_news || []).length === 0 ? (
                        <p className="text-xs text-slate-400 italic">No recent news or search insights found.</p>
                      ) : (
                        (selectedProfile.recent_news || []).map((news, idx) => (
                          <div key={idx} className="border-l-2 border-brand-200 pl-2.5 py-0.5">
                            <p className="text-[11px] leading-relaxed text-slate-600 dark:text-slate-300">{news}</p>
                          </div>
                        ))
                      )}
                    </div>
                  </Card>
                </div>
              </div>
            ) : (
              /* No profile yet for selected company */
              <div className="flex h-[400px] flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-white p-6 dark:border-navy-800 dark:bg-navy-900">
                <Sparkles size={48} className="text-brand-500 animate-pulse" />
                <h3 className="mt-4 text-base font-bold text-navy-900 dark:text-white">No AI Research Profile Exists</h3>
                <p className="mt-1 text-center text-xs text-slate-400 max-w-sm">
                  No business intelligence profile has been generated for <strong>{selectedCompany.name}</strong> yet.
                </p>
                <button
                  onClick={() => handleRegenerate(selectedCompany.name)}
                  disabled={isResearching}
                  className="mt-6 flex items-center gap-2 rounded-xl bg-brand-500 px-6 py-2.5 text-xs font-bold text-white shadow-md hover:bg-brand-600 disabled:opacity-50"
                >
                  {isResearching ? (
                    <><RefreshCw size={14} className="animate-spin" /> Researching ({researchProgress}%)</>
                  ) : (
                    <><Cpu size={14} /> Deploy AI Research Agents</>
                  )}
                </button>
              </div>
            )
          ) : (
            /* No company selected */
            <div className="flex h-[400px] flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 bg-white dark:border-navy-800 dark:bg-navy-900">
              <Sparkles size={48} className="text-slate-300 animate-pulse" />
              <h3 className="mt-4 text-base font-bold text-navy-900 dark:text-white">No Company Selected</h3>
              <p className="mt-1 text-xs text-slate-400">
                Select a company on the left or enter a new target domain to deploy AI research.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
