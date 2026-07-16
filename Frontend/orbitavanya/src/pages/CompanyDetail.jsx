import { useParams, Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import {
  ArrowLeft, Mail, Phone, MapPin, Building2, Sparkles,
  FileText, Calendar, Loader2, Check, Download, AlertTriangle,
  Eye, X, ShieldAlert, Cpu, RefreshCw, ExternalLink
} from 'lucide-react';
import { Card, MatchBadge, StatusBadge, ProgressBar } from '../components/ui/Common.jsx';
import { tenders } from '../data/tenders.jsx';

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

export default function CompanyDetail() {
  const { id: uei } = useParams();

  // Data States
  const [company, setCompany] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // AI Research Profile State
  const [aiProfile, setAiProfile] = useState(null);
  const [aiProfileLoading, setAiProfileLoading] = useState(false);

  // Inline Research Triggering (from CompanyDetail)
  const [isResearchingHere, setIsResearchingHere] = useState(false);
  const [researchProgress, setResearchProgress] = useState(0);
  const [researchMessage, setResearchMessage] = useState('');
  const [researchTaskKey, setResearchTaskKey] = useState(null);

  // Proposal Generation States
  const [isGenerating, setIsGenerating] = useState(false);
  const [recentProposals, setRecentProposals] = useState([]);
  const [generationProgress, setGenerationProgress] = useState(0);
  const [generationMessage, setGenerationMessage] = useState('');
  const [generationStatus, setGenerationStatus] = useState('idle');
  const [previewingReport, setPreviewingReport] = useState(null);
  const [generationError, setGenerationError] = useState(null);

  // Fetch company details on mount
  const fetchCompanyDetails = () => {
    setLoading(true);
    fetch(`http://localhost:8000/api/companies/${uei}`)
      .then((res) => {
        if (!res.ok) throw new Error('Company not found in database');
        return res.json();
      })
      .then((data) => {
        setCompany(data);
        setLoading(false);
        fetchRecentProposals(data.name);
        fetchAiProfile(data.name);
      })
      .catch((err) => {
        console.error('Error fetching company:', err);
        setError(err.message);
        setLoading(false);
      });
  };

  // Fetch recently generated documents for this company
  const fetchRecentProposals = (companyName) => {
    fetch(`http://localhost:8000/api/proposals/recent?company_name=${encodeURIComponent(companyName)}`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch recent proposals');
        return res.json();
      })
      .then((data) => {
        setRecentProposals(data || []);
      })
      .catch((err) => {
        console.warn('Error fetching recent proposals:', err);
      });
  };

  // Fetch AI research profile from MongoDB
  const fetchAiProfile = async (name) => {
    if (!name) return;
    setAiProfileLoading(true);
    try {
      const res = await fetch(
        `http://localhost:8000/api/companies/profiles/search?q=${encodeURIComponent(name)}`
      );
      if (res.ok) {
        const data = await res.json();
        setAiProfile(data);
      } else {
        setAiProfile(null);
      }
    } catch {
      setAiProfile(null);
    } finally {
      setAiProfileLoading(false);
    }
  };

  // Trigger inline AI research from CompanyDetail page
  const handleDeployResearch = async () => {
    if (!company) return;
    setIsResearchingHere(true);
    setResearchProgress(5);
    setResearchMessage('Initializing research agents...');
    setResearchTaskKey(company.name);
    try {
      await fetch('http://localhost:8000/api/companies/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company: company.name, force: true }),
      });
    } catch (err) {
      setIsResearchingHere(false);
      setResearchMessage('Failed to start research.');
    }
  };

  // Poll research progress when triggered from this page
  useEffect(() => {
    let timer;
    if (isResearchingHere && researchTaskKey) {
      timer = setInterval(async () => {
        try {
          const res = await fetch('http://localhost:8000/api/companies/research/status');
          const tasks = await res.json();
          const task = tasks[researchTaskKey];
          if (task) {
            setResearchProgress(task.progress || 0);
            setResearchMessage(task.message || 'Running...');
            if (task.status === 'completed') {
              clearInterval(timer);
              setIsResearchingHere(false);
              setResearchTaskKey(null);
              await fetchAiProfile(company.name);
            } else if (task.status === 'failed') {
              clearInterval(timer);
              setIsResearchingHere(false);
              setResearchMessage(task.message || 'Research failed.');
            }
          }
        } catch {}
      }, 2000);
    }
    return () => clearInterval(timer);
  }, [isResearchingHere, researchTaskKey, company]);

  useEffect(() => {
    fetchCompanyDetails();
  }, [uei]);

  // ── On company load: reconnect to any already-running research task ──
  // This fires after company data is fetched. If the user started research,
  // navigated away, and came back — we pick up right where we left off.
  useEffect(() => {
    if (!company) return;
    // Don't override an already-active poll loop
    if (isResearchingHere) return;

    const checkForActiveTask = async () => {
      try {
        const res = await fetch('http://localhost:8000/api/companies/research/status');
        if (!res.ok) return;
        const tasks = await res.json();
        // Find any task key that fuzzy-matches this company's name
        const companyNameLower = company.name.toLowerCase();
        const matchingKey = Object.keys(tasks).find(key => {
          const task = tasks[key];
          if (task.status !== 'processing') return false;
          return key.toLowerCase().includes(companyNameLower.split(' ')[0]) ||
                 companyNameLower.includes(key.toLowerCase().split(' ')[0]);
        });
        if (matchingKey) {
          const task = tasks[matchingKey];
          setResearchTaskKey(matchingKey);
          setResearchProgress(task.progress || 10);
          setResearchMessage(task.message || 'Research in progress...');
          setIsResearchingHere(true);
        }
      } catch {}
    };

    checkForActiveTask();
  }, [company]); // runs once when company data arrives

  // Run partnership proposal generation pipeline with progress polling
  const handleGenerateProposal = () => {
    if (!company) return;
    setIsGenerating(true);
    setGenerationError(null);
    setGenerationProgress(5);
    setGenerationMessage('Initializing pipeline...');
    setGenerationStatus('processing');

    fetch('http://localhost:8000/api/proposals/generate-partnership', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ winner: company.name })
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to start generation task');
        return data;
      })
      .then(() => {
        // Start polling status
        const pollInterval = setInterval(() => {
          fetch(`http://localhost:8000/api/proposals/status?company_name=${encodeURIComponent(company.name)}`)
            .then((res) => {
              if (!res.ok) throw new Error('Task status unreachable');
              return res.json();
            })
            .then((statusData) => {
              setGenerationProgress(statusData.progress || 0);
              setGenerationMessage(statusData.message || 'Running pipeline...');
              setGenerationStatus(statusData.status || 'processing');

              if (statusData.status === 'completed') {
                clearInterval(pollInterval);
                setIsGenerating(false);
                fetchRecentProposals(company.name);
                // Open preview modal automatically
                setPreviewingReport({
                  filename: statusData.filename,
                  title: 'Strategic Partnership Proposal',
                  company_name: company.name,
                  solicitation_number: company.uei,
                  size: 'Calculated'
                });
              } else if (statusData.status === 'failed') {
                clearInterval(pollInterval);
                setIsGenerating(false);
                setGenerationError(statusData.message);
              }
            })
            .catch((err) => {
              console.error('Error polling status:', err);
            });
        }, 1500);
      })
      .catch((err) => {
        setIsGenerating(false);
        setGenerationStatus('failed');
        setGenerationError(err.message);
      });
  };

  if (loading) {
    return (
      <Card className="flex flex-col items-center justify-center py-40">
        <Loader2 className="animate-spin text-brand-500" size={32} />
        <p className="mt-4 text-sm text-slate-500 dark:text-slate-400 font-medium">Fetching details from SAM database...</p>
      </Card>
    );
  }

  if (error || !company) {
    return (
      <Card className="flex flex-col items-center justify-center py-20 text-center">
        <AlertTriangle className="text-rose-500 mb-3" size={36} />
        <h3 className="text-base font-bold text-navy-900 dark:text-white">Error Loading Details</h3>
        <p className="mt-1.5 text-xs text-slate-400 max-w-sm">{error || 'Company profile could not be found.'}</p>
        <Link to="/companies" className="mt-4 text-xs font-bold text-brand-500 hover:underline">
          Return to Companies List
        </Link>
      </Card>
    );
  }

  // Derive business size/status badges
  const isSmall = ['Y', 'YES', 'TRUE'].includes(String(company.is_small_business || '').trim().toUpperCase());
  const isNonProfit = ['Y', 'YES', 'TRUE'].includes(String(company.is_non_profit || '').trim().toUpperCase());
  const isWomenOwned = ['Y', 'YES', 'TRUE'].includes(String(company.is_women_owned || '').trim().toUpperCase());
  const isVeteranOwned = ['Y', 'YES', 'TRUE'].includes(String(company.is_veteran_owned || '').trim().toUpperCase());
  const isSdvoseb = ['Y', 'YES', 'TRUE'].includes(String(company.is_sdvosb || '').trim().toUpperCase());
  const hasExclusions = ['Y', 'YES', 'TRUE'].includes(String(company.exclusions || '').trim().toUpperCase());

  return (
    <div>
      <Link to="/companies" className="mb-4 flex w-fit items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-navy-900 dark:text-slate-400 dark:hover:text-white">
        <ArrowLeft size={15} /> Back to Companies
      </Link>

      {/* Header Info */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-lg font-bold text-brand-600 dark:bg-navy-800 dark:text-brand-400 aspect-square shrink-0">
            {company.name.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-navy-900 dark:text-white leading-tight">{company.name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm text-slate-500 dark:text-slate-400">
              <span className="font-semibold text-slate-600 dark:text-slate-300">{company.industry}</span>
              <span>·</span>
              <span>{company.location}</span>
              <span>·</span>
              <StatusBadge status={company.status} />
            </div>
          </div>
        </div>
        
        {/* Call to Actions */}
        <div className="flex items-center gap-2">
          {company.email && (
            <a 
              href={`mailto:${company.email}`}
              className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700 transition-colors"
            >
              <Mail size={15} /> Email Contact
            </a>
          )}
          <button 
            onClick={handleGenerateProposal}
            disabled={isGenerating}
            className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft hover:bg-brand-600 transition-colors disabled:opacity-70 shrink-0"
          >
            {isGenerating ? <Loader2 className="animate-spin" size={15} /> : <Sparkles size={15} />}
            {isGenerating ? 'Generating Proposal...' : 'Generate Partnership Proposal'}
          </button>
        </div>
      </div>

      {generationError && (
        <div className="mt-4 rounded-xl bg-rose-50 border border-rose-100 p-4 text-sm text-rose-600 dark:bg-rose-950/20 dark:border-rose-900/30 dark:text-rose-400">
          <p className="font-bold">Generation Failed</p>
          <p className="text-xs mt-0.5">{generationError}</p>
        </div>
      )}

      {generationStatus !== 'idle' && (
        <div className="mt-4">
          <ProgressBar progress={generationProgress} message={generationMessage} status={generationStatus} />
        </div>
      )}

      {/* Main Layout Grid */}
      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="flex flex-col gap-5 lg:col-span-2">
          {/* Company Details Registry */}
          <Card>
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">SAM Registry Overview</h3>
            <div className="mt-4 grid grid-cols-1 gap-y-4 gap-x-6 text-sm sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">Unique Entity ID (UEI)</p>
                <p className="font-semibold text-navy-900 dark:text-white font-mono">{company.uei}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">CAGE Code</p>
                <p className="font-semibold text-navy-900 dark:text-white font-mono">{company.cage_code || 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">Entity Structure</p>
                <p className="font-semibold text-navy-900 dark:text-white">{company.entity_structure || 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">Exclusions Status</p>
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                  hasExclusions 
                    ? 'bg-rose-100 text-rose-800 dark:bg-rose-950/25 dark:text-rose-400' 
                    : 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/25 dark:text-emerald-400'
                }`}>
                  {hasExclusions ? 'Active Exclusions Found' : 'No Exclusions'}
                </span>
              </div>
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">Expiration Date</p>
                <p className="font-semibold text-navy-900 dark:text-white">{company.expiration_date || 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">Revenue (Exec Comp)</p>
                <p className="font-semibold text-navy-900 dark:text-white">{company.revenue || 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">Primary NAICS Code</p>
                <p className="font-semibold text-navy-900 dark:text-white font-mono">{company.primary_naics || 'N/A'}</p>
              </div>
              <div className="sm:col-span-2">
                <p className="text-xs text-slate-400 dark:text-slate-500">Primary NAICS Sector</p>
                <p className="font-semibold text-navy-900 dark:text-white text-xs truncate" title={company.primary_naics_desc}>{company.primary_naics_desc || 'N/A'}</p>
              </div>
            </div>

            {/* Certifications & Badges */}
            <div className="mt-5 pt-4 border-t border-slate-100 dark:border-navy-700 flex flex-wrap gap-2">
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${isSmall ? 'bg-sky-50 text-sky-700 dark:bg-navy-900 dark:text-sky-400' : 'bg-slate-50 text-slate-400'}`}>
                Small Business
              </span>
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${isNonProfit ? 'bg-indigo-50 text-indigo-700 dark:bg-navy-900 dark:text-indigo-400' : 'bg-slate-50 text-slate-400'}`}>
                Non-Profit
              </span>
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${isWomenOwned ? 'bg-fuchsia-50 text-fuchsia-700 dark:bg-navy-900 dark:text-fuchsia-400' : 'bg-slate-50 text-slate-400'}`}>
                Women Owned
              </span>
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${isVeteranOwned ? 'bg-teal-50 text-teal-700 dark:bg-navy-900 dark:text-teal-400' : 'bg-slate-50 text-slate-400'}`}>
                Veteran Owned
              </span>
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${isSdvoseb ? 'bg-amber-50 text-amber-700 dark:bg-navy-900 dark:text-amber-400' : 'bg-slate-50 text-slate-400'}`}>
                SDVOSB
              </span>
            </div>
          </Card>

          {/* AI Research Intelligence Panel */}
          <Card>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles size={16} className="text-brand-500" />
                <h3 className="text-sm font-bold text-navy-900 dark:text-white">AI Research Intelligence</h3>
              </div>
              {aiProfile && (
                <Link
                  to={`/ai-research?q=${encodeURIComponent(company.name)}`}
                  className="text-[10px] font-bold text-brand-500 hover:underline"
                >
                  Full Profile →
                </Link>
              )}
            </div>

            {aiProfileLoading ? (
              <div className="mt-4 flex items-center gap-2 text-xs text-slate-400">
                <Loader2 size={14} className="animate-spin" /> Loading research profile...
              </div>
            ) : aiProfile ? (
              <div className="mt-4 space-y-4">
                {/* Short description */}
                <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-300 line-clamp-4">
                  {cleanDescriptionText(aiProfile.description) || 'No description available.'}
                </p>

                {/* Key data pills */}
                <div className="flex flex-wrap gap-2">
                  {aiProfile.headquarters && (
                    <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600 dark:bg-navy-800 dark:border-navy-700 dark:text-slate-300">
                      📍 {aiProfile.headquarters}
                    </span>
                  )}
                  {aiProfile.employee_count && (
                    <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-600 dark:bg-navy-800 dark:border-navy-700 dark:text-slate-300">
                      👥 {aiProfile.employee_count}
                    </span>
                  )}
                  {aiProfile.website && (
                    <a href={aiProfile.website} target="_blank" rel="noreferrer"
                      className="rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-600 hover:bg-brand-100 flex items-center gap-1"
                    >
                      🌐 Website <ExternalLink size={10} />
                    </a>
                  )}
                </div>

                {/* Strengths preview */}
                {aiProfile.rfp_strengths && aiProfile.rfp_strengths.length > 0 && (
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Key Strengths</p>
                    <ul className="space-y-1">
                      {aiProfile.rfp_strengths.slice(0, 3).map((s, i) => (
                        <li key={i} className="flex items-start gap-1.5 text-xs text-emerald-700 dark:text-emerald-400">
                          <Check size={11} className="mt-0.5 shrink-0" /> {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Tech stack preview */}
                {aiProfile.technology_stack && aiProfile.technology_stack.length > 0 && (
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Tech Stack</p>
                    <div className="flex flex-wrap gap-1.5">
                      {aiProfile.technology_stack.slice(0, 6).map((t, i) => (
                        <span key={i} className="rounded-lg bg-blue-50 border border-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-700 dark:bg-navy-800 dark:border-navy-700 dark:text-blue-300">
                          {t}
                        </span>
                      ))}
                      {aiProfile.technology_stack.length > 6 && (
                        <span className="rounded-lg bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">
                          +{aiProfile.technology_stack.length - 6} more
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              /* Not generated yet */
              <div className="mt-4 space-y-3">
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  No AI research profile has been generated for <strong>{company?.name}</strong> yet.
                </p>
                {isResearchingHere ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs font-semibold text-blue-700 dark:text-blue-300">
                      <span>{researchMessage}</span>
                      <span>{researchProgress}%</span>
                    </div>
                    <div className="h-1.5 w-full rounded-full bg-blue-100 dark:bg-navy-700">
                      <div
                        className="h-full rounded-full bg-blue-500 transition-all duration-500"
                        style={{ width: `${researchProgress}%` }}
                      />
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={handleDeployResearch}
                    className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2 text-xs font-bold text-white hover:bg-brand-600 shadow-md"
                  >
                    <Cpu size={13} /> Deploy AI Research Agents
                  </button>
                )}
              </div>
            )}
          </Card>

          {/* Recently Generated Documents */}
          <Card>
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Recently Generated Proposals</h3>
            <div className="mt-3 flex flex-col gap-3">
              {recentProposals.map((doc) => (
                <div key={doc.filename} className="flex items-center justify-between rounded-xl border border-slate-100 p-3 hover:border-brand-200 dark:border-navy-800 dark:hover:border-brand-500/50">
                  <div>
                    <p className="text-sm font-semibold text-navy-900 dark:text-white">{doc.title}</p>
                    <p className="text-xs text-slate-400 dark:text-slate-500 font-mono mt-0.5">{doc.filename} · {doc.size} · Generated {doc.date}</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setPreviewingReport(doc)}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-brand-50 hover:bg-brand-100 text-brand-600 dark:bg-navy-900 dark:text-brand-400 px-3 py-1.5 text-xs font-semibold transition-colors"
                    >
                      <Eye size={13} /> View
                    </button>
                    <a
                      href={`http://localhost:8000/api/reports/download/${doc.filename}`}
                      download
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700 transition-colors"
                    >
                      <Download size={13} /> Download
                    </a>
                  </div>
                </div>
              ))}
              {recentProposals.length === 0 && (
                <p className="text-xs text-slate-400 py-4 text-center">No proposals generated for this company yet. Click the generate button above to start one.</p>
              )}
            </div>
          </Card>
        </div>

        {/* Sidebar Info (Registry Contacts) */}
        <div className="flex flex-col gap-5">
          {/* Government Contact Details */}
          <Card>
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Government Registry Contact</h3>
            <div className="mt-3 flex flex-col gap-3.5 text-sm">
              <div>
                <p className="text-xs text-slate-400 mb-0.5">Contact Name</p>
                <p className="font-semibold text-navy-900 dark:text-slate-200">{company.contact}</p>
              </div>
              {company.email && (
                <div>
                  <p className="text-xs text-slate-400 mb-0.5 flex items-center gap-1"><Mail size={11} /> Email</p>
                  <a href={`mailto:${company.email}`} className="font-semibold text-brand-500 hover:underline break-all">{company.email}</a>
                </div>
              )}
              {company.phone && company.phone !== 'N/A' && (
                <div>
                  <p className="text-xs text-slate-400 mb-0.5 flex items-center gap-1"><Phone size={11} /> Phone</p>
                  <p className="font-semibold text-navy-900 dark:text-slate-200">{company.phone}</p>
                </div>
              )}
              <div>
                <p className="text-xs text-slate-400 mb-0.5 flex items-center gap-1"><MapPin size={11} /> Address</p>
                <p className="font-semibold text-navy-900 dark:text-slate-200 text-xs leading-relaxed">{company.address || company.location}</p>
              </div>
            </div>
          </Card>

          {/* Electronic Business Contact Details */}
          {company.ebiz_contact && (
            <Card>
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">EBiz Contact</h3>
              <div className="mt-3 flex flex-col gap-3 text-sm">
                <div>
                  <p className="text-xs text-slate-400 mb-0.5">Contact Name</p>
                  <p className="font-semibold text-navy-900 dark:text-slate-200">{company.ebiz_contact}</p>
                </div>
                {company.ebiz_email && (
                  <div>
                    <p className="text-xs text-slate-400 mb-0.5"><Mail size={11} className="inline mr-1" /> Email</p>
                    <a href={`mailto:${company.ebiz_email}`} className="font-semibold text-brand-500 hover:underline break-all">{company.ebiz_email}</a>
                  </div>
                )}
                {company.ebiz_phone && (
                  <div>
                    <p className="text-xs text-slate-400 mb-0.5"><Phone size={11} className="inline mr-1" /> Phone</p>
                    <p className="font-semibold text-navy-900 dark:text-slate-200">{company.ebiz_phone}</p>
                  </div>
                )}
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* PDF View Modal Overlay */}
      {previewingReport && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4 md:p-6 backdrop-blur-md" onClick={() => setPreviewingReport(null)}>
          <div className="w-[94vw] md:w-[90vw] lg:w-[85vw] max-w-7xl h-[92vh] flex flex-col rounded-2xl bg-white dark:bg-navy-800 shadow-2xl overflow-hidden border border-slate-100 dark:border-navy-700" onClick={(e) => e.stopPropagation()}>
            
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-navy-700 p-5 shrink-0 bg-white dark:bg-navy-800">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-50 text-brand-600 dark:bg-navy-900 dark:text-brand-400">
                  <FileText size={20} />
                </div>
                <div>
                  <h3 className="text-base font-extrabold text-navy-900 dark:text-white leading-tight">{previewingReport.company_name}</h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className="font-semibold text-brand-600 dark:text-brand-400">{previewingReport.proposal_type || 'Strategic Partnership Proposal'}</span>
                    <span>•</span>
                    <span className="font-mono bg-slate-100 dark:bg-navy-900 px-1.5 py-0.5 rounded text-[10px]">{previewingReport.solicitation_number || uei}</span>
                    <span>•</span>
                    <span>{previewingReport.size}</span>
                  </p>
                </div>
              </div>
              <button onClick={() => setPreviewingReport(null)} className="rounded-lg p-2 text-slate-400 hover:text-navy-950 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-navy-900 transition-colors">
                <X size={20} />
              </button>
            </div>
            
            {/* Modal Body: Embedded PDF Viewer */}
            <div className="flex-1 bg-slate-100 dark:bg-navy-900 p-4 md:p-6 flex flex-col overflow-hidden">
              <iframe
                src={`http://localhost:8000/api/reports/view/${previewingReport.filename}`}
                className="w-full h-full border-0 rounded-xl bg-white shadow-lg"
                title={previewingReport.title}
              />
            </div>

            {/* Modal Footer */}
            <div className="flex justify-end gap-3 border-t border-slate-100 dark:border-navy-700 p-5 shrink-0 bg-white dark:bg-navy-800">
              <button onClick={() => setPreviewingReport(null)} className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700 transition-colors">
                Close
              </button>
              <a
                href={`http://localhost:8000/api/reports/download/${previewingReport.filename}`}
                download
                className="flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white shadow-soft hover:bg-brand-600 transition-colors"
              >
                <Download size={14} /> Download PDF
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
