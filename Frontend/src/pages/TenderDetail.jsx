import { useParams, Link } from 'react-router-dom';
import { useState, useEffect, useCallback } from 'react';
import {
  ArrowLeft, Building2, DollarSign, Calendar, Sparkles, FileEdit,
  Users, ExternalLink, Send, Check, Loader2, AlertTriangle, RefreshCw,
  Trophy, Clock, AlertOctagon, Mail, Phone, MapPin, Handshake,
  ShieldCheck, BookTemplate, ChevronDown, ChevronUp, FileText, FileDown
} from 'lucide-react';
import { Card, MatchBadge, StatusBadge, renderSafeText } from '../components/ui/Common.jsx';
import { tenders as staticTenders, daysUntilClosing } from '../data/tenders.jsx';
import { companies as staticCompanies } from '../data/companies.jsx';
import { api } from '../lib/api.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';

// ---------------------------------------------------------------------------
// Mode config — drives button appearance + backend payload for every status
// ---------------------------------------------------------------------------
const MODE_CONFIG = {
  prime: {
    label: 'Respond as Prime Contractor',
    sublabel: 'Build technical and pricing volumes to bid directly',
    icon: ShieldCheck,
    color: 'bg-brand-500 hover:bg-brand-600 text-white',
    doneColor: 'bg-brand-100 text-brand-700 dark:bg-brand-950/40 dark:text-brand-400',
    description:
      'Your organisation responds to this solicitation directly as the prime contractor. ' +
      'A full technical and price proposal response draft will be initialized in the Proposal Builder.',
  },
  subcontract: {
    label: 'Seek Subcontract from Prime',
    sublabel: 'Pitch your capabilities to the winning prime contractor',
    icon: Handshake,
    color: 'bg-violet-500 hover:bg-violet-600 text-white',
    doneColor: 'bg-violet-100 text-violet-700 dark:bg-violet-950/40 dark:text-violet-400',
    description:
      'The contract is awarded. You can reach out to the winning prime contractor ' +
      'and offer your capabilities as a subcontractor. A partnership proposal will be generated.',
  },
};

// Which modes are offered for each tender status
// Open & Closing Soon: prime only (no winner is there yet, so subcontract cannot be sought)
// Expired, Won, Closed: subcontract only (the solicitation period has closed, so teaming/subcontracting is the only route)
const MODES_FOR_STATUS = {
  'Open':         ['prime'],
  'Closing Soon': ['prime'],
  'Expired':      ['subcontract'],
  'Won':          ['subcontract'],
  'Closed':       ['subcontract'],
};

export default function TenderDetail() {
  const { id } = useParams();
  const { createAlert } = useNotifications();
  const notify = (title, message, link) => createAlert(title, message, link).catch(() => {});
  const [tender, setTender] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [backendOffline, setBackendOffline] = useState(false);

  // Draft Requests and Mode States
  const [draftRequests, setDraftRequests] = useState([]);
  const [modeStates, setModeStates] = useState({ prime: 'idle', subcontract: 'idle' });

  const handleDownload = async (e, filename) => {
    e.preventDefault();
    try {
      const blob = await api.downloadReport(filename);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Download failed:", err);
    }
  };
  const [modeMessages, setModeMessages] = useState({});
  const [expandedMode, setExpandedMode] = useState(null); // which mode's description is open
  const [manualWinner, setManualWinner] = useState(''); // manually entered winning company name for subcontract mode

  // Fetch draft requests status from database helper
  const fetchDraftRequests = useCallback(() => {
    api.getTenderDraftRequest(id)
      .then(draftData => {
        if (draftData?.requests?.length) {
          setDraftRequests(draftData.requests);
          const newStates = { prime: 'idle', subcontract: 'idle' };
          draftData.requests.forEach(r => {
            newStates[r.mode] = r.draft_status === 'completed' ? 'completed' : 'already';
          });
          setModeStates(newStates);
        }
      })
      .catch(() => {});
  }, [id]);

  // Fetch tender
  useEffect(() => {
    setLoading(true);
    setError(null);
    api.getTender(id)
      .then(data => {
        setTender(data);
        setBackendOffline(false);
        setLoading(false);
        // Also fetch existing draft request state
        fetchDraftRequests();
      })
      .catch(err => {
        if (err.message.includes('404') || err.message === 'not_found') {
          const found = staticTenders.find(t => String(t.id) === id);
          if (found) { setTender(found); setBackendOffline(false); }
          else setError('Tender not found. It may not be cached yet — try syncing from SAM.gov on the Tenders page.');
        } else {
          setBackendOffline(true);
          setTender(staticTenders.find(t => String(t.id) === id) || staticTenders[0]);
        }
        setLoading(false);
      });
  }, [id, fetchDraftRequests]);

  // Real-time updates when compile completes
  useEffect(() => {
    let isMounted = true;
    let ws = null;
    let reconnectTimeout = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 3;

    function connect() {
      if (!isMounted) return;
      const token = localStorage.getItem('orbitavanya_token');
      const wsUrl = api.getWebSocketUrl(`/api/proposals/ws${token ? `?token=${encodeURIComponent(token)}` : ''}`);
      try {
        ws = new WebSocket(wsUrl);
        ws.onopen = () => {
          reconnectAttempts = 0;
        };
        ws.onmessage = () => {
          if (isMounted) fetchDraftRequests();
        };
        ws.onclose = () => {
          if (isMounted) {
            reconnectAttempts++;
            if (reconnectAttempts <= MAX_RECONNECT_ATTEMPTS) {
              reconnectTimeout = setTimeout(connect, 5000);
            } else {
              console.warn("WebSocket reconnect limit reached. Falling back to slow HTTP polling.");
              reconnectTimeout = setTimeout(function poll() {
                if (isMounted) {
                  fetchDraftRequests();
                  reconnectTimeout = setTimeout(poll, 30000);
                }
              }, 30000);
            }
          }
        };
        ws.onerror = () => {};
      } catch (e) {}
    }

    connect();

    return () => {
      isMounted = false;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) {
        ws.onclose = null;
        ws.onerror = null;
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
          ws.close();
        }
      }
    };
  }, [fetchDraftRequests]);

  // Submit a specific mode
  const handleModeAction = (mode) => {
    if (backendOffline) {
      setModeStates(s => ({ ...s, [mode]: 'success' }));
      setModeMessages(m => ({ ...m, [mode]: `${MODE_CONFIG[mode].label} request submitted (demo mode).` }));
      return;
    }

    const winningCompany = mode === 'subcontract' 
      ? (tender?.award_awardee || manualWinner || '').trim() 
      : '';

    if (mode === 'subcontract' && !winningCompany) {
      alert('Please specify the winning company name to pitch subcontracting.');
      return;
    }

    setModeStates(s => ({ ...s, [mode]: 'submitting' }));
    api.requestTenderDraft(id, {
      mode,
      target_company: winningCompany,
      tender_title: tender?.title || 'Tender Proposal'
    })
      .then(data => {
        setModeStates(s => ({ ...s, [mode]: data.status === 'already_requested' ? 'already' : 'success' }));
        setModeMessages(m => ({ ...m, [mode]: data.message }));
        // Refresh drafts state to get latest IDs and completed filenames
        fetchDraftRequests();
        if (data.status !== 'already_requested') {
          notify(
            `${MODE_CONFIG[mode].label} requested`,
            `Draft generation started for "${tender?.title || 'this tender'}".`,
            `/tenders/${id}`
          );
        }
      })
      .catch(err => {
        setModeStates(s => ({ ...s, [mode]: 'error' }));
        setModeMessages(m => ({ ...m, [mode]: err.message }));
      });
  };

  // Loading / error guards
  if (loading) {
    return (
      <Card className="flex flex-col items-center justify-center py-40">
        <Loader2 className="animate-spin text-brand-500" size={32} />
        <p className="mt-4 text-sm text-slate-500 dark:text-slate-400 font-medium">Loading tender details...</p>
      </Card>
    );
  }
  if (error) {
    return (
      <Card className="flex flex-col items-center justify-center py-20 text-center">
        <AlertTriangle className="text-rose-500 mb-3" size={36} />
        <h3 className="text-base font-bold text-navy-900 dark:text-white">Tender Not Found</h3>
        <p className="mt-1.5 text-xs text-slate-400 max-w-sm">{error}</p>
        <Link to="/tenders" className="mt-4 flex items-center gap-1.5 text-xs font-bold text-brand-500 hover:underline">
          <ArrowLeft size={13} /> Back to Tenders
        </Link>
      </Card>
    );
  }
  if (!tender) return null;

  // Normalise fields (snake_case from backend, camelCase from static)
  const title          = tender.title;
  const agency         = tender.agency || tender.agency_name;
  const value          = tender.value;
  const category       = tender.category || tender.type || 'Solicitation';
  const postedDate     = tender.posted_date  || tender.postedDate;
  const closingDate    = tender.closing_date || tender.closingDate;
  const status         = tender.status;
  const rfpUrl         = tender.rfp_url      || tender.rfpUrl;
  const description    = tender.description;
  const matchScore     = tender.match || tender.matchScore || tender.match_score;
  const setAside       = tender.set_aside;
  const solicitationNumber = tender.solicitation_number;
  const office         = tender.office || 'Federal Office';
  const naicsCode      = tender.naics_code || tender.naicsCode || '541511';
  const pscCode        = tender.psc_code || tender.pscCode || 'D399';
  const pocName        = tender.poc_name || 'Government POC';
  const pocEmail       = tender.poc_email;
  const awardAwardee   = tender.award_awardee;
  const awardDate      = tender.award_date;
  const awardValue     = tender.award_value;

  // Available modes based on status
  const availableModes = MODES_FOR_STATUS[status] || [];

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Link to="/tenders" className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-500 hover:text-brand-500 transition-colors">
        <ArrowLeft size={14} /> Back to Tenders
      </Link>

      {/* Hero Header Card */}
      <Card className="relative overflow-hidden">
        {/* Glow decoration */}
        <div className="absolute -right-16 -top-16 h-48 w-48 rounded-full bg-brand-500/10 blur-3xl pointer-events-none" />

        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div className="space-y-2.5 max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-brand-50 dark:bg-brand-950/20 border border-brand-100 dark:border-brand-900/30 px-3 py-1 text-xs font-bold text-brand-700 dark:text-brand-400">
                {category}
              </span>
              <span className={`rounded-full px-3 py-1 text-xs font-bold ${
                (tender.source || '').toLowerCase().includes('companies') || (tender.source || '').toLowerCase().includes('uk')
                  ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400 border border-emerald-200/60'
                  : 'bg-blue-50 text-blue-700 dark:bg-blue-950/20 dark:text-blue-400 border border-blue-200/60'
              }`}>
                {tender.source || 'SAM.gov'}
              </span>
              <StatusBadge status={status} />
              {setAside && (
                <span className="rounded-full bg-slate-100 dark:bg-navy-800 border border-slate-200 dark:border-navy-700 px-3 py-1 text-xs font-semibold text-slate-600 dark:text-slate-400">
                  {setAside}
                </span>
              )}
            </div>
            <h1 className="text-xl md:text-2xl font-extrabold text-navy-900 dark:text-white leading-tight">
              {title}
            </h1>
            <p className="text-sm font-semibold text-slate-500 dark:text-slate-400">
              {agency} {office && `· ${office}`}
            </p>
          </div>

          <div className="flex flex-col items-start md:items-end gap-3 shrink-0">
            {matchScore && <MatchBadge score={matchScore} />}
            <a
              href={
                rfpUrl ||
                ((tender.source || '').toLowerCase().includes('companies') || (tender.source || '').toLowerCase().includes('uk')
                  ? `https://www.find-tender.service.gov.uk/Search/Results?Keywords=${encodeURIComponent(title || '')}`
                  : `https://sam.gov/search/?index=opp&q=${encodeURIComponent(solicitationNumber || title || '')}`)
              }
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700 transition-colors shadow-soft"
            >
              <ExternalLink size={14} />
              View on {(tender.source || '').toLowerCase().includes('companies') ? 'Find a Tender (UK)' : 'SAM.gov'}
            </a>
            {value && (
              <div className="text-right mt-1">
                <p className="text-[10px] uppercase font-bold tracking-wider text-slate-400">Estimated Value</p>
                <p className="text-base font-extrabold text-navy-900 dark:text-white mt-0.5">{value}</p>
              </div>
            )}
          </div>
        </div>

        {/* Quick details strip */}
        <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-4 border-t border-slate-100 dark:border-navy-800/80 pt-5">
          <div>
            <p className="text-[10px] uppercase font-bold text-slate-400">Solicitation #</p>
            <p className="mt-1 text-xs font-mono font-bold text-navy-900 dark:text-slate-200">{solicitationNumber || '—'}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase font-bold text-slate-400">Primary NAICS</p>
            <p className="mt-1 text-xs font-mono font-bold text-navy-900 dark:text-slate-200">{naicsCode}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase font-bold text-slate-400">Posted Date</p>
            <p className="mt-1 text-xs font-semibold text-navy-900 dark:text-slate-200">{postedDate || '—'}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase font-bold text-slate-400">Closing Date</p>
            <p className="mt-1 text-xs font-semibold text-navy-900 dark:text-slate-200">{closingDate || '—'}</p>
          </div>
        </div>
      </Card>

      {/* Main Content Split */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left: Description & Details */}
        <div className="space-y-6 lg:col-span-2">
          {/* Description */}
          <Card>
            <h3 className="text-sm font-extrabold text-navy-900 dark:text-white uppercase tracking-wider mb-3">
              Description
            </h3>
            <div className="text-xs leading-relaxed text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
              {description || 'No description summary available.'}
            </div>
            {rfpUrl && (
              <a
                href={rfpUrl}
                target="_blank"
                rel="noreferrer"
                className="mt-4 inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700 transition-all shadow-soft"
              >
                View original SAM.gov posting <ExternalLink size={13} />
              </a>
            )}
          </Card>

          {/* Award Info (if won) */}
          {awardAwardee && (
            <Card className="border-l-4 border-emerald-500 bg-emerald-50/10 dark:bg-emerald-950/5">
              <div className="flex items-center gap-2 mb-3">
                <Trophy size={16} className="text-emerald-500" />
                <h3 className="text-sm font-extrabold text-navy-900 dark:text-white uppercase tracking-wider">
                  Award Details
                </h3>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                <div>
                  <p className="font-semibold text-slate-400">Awardee</p>
                  <p className="mt-1 font-bold text-navy-900 dark:text-slate-200">{awardAwardee}</p>
                </div>
                {awardValue && (
                  <div>
                    <p className="font-semibold text-slate-400">Award Amount</p>
                    <p className="mt-1 font-bold text-navy-900 dark:text-slate-200">{awardValue}</p>
                  </div>
                )}
                {awardDate && (
                  <div>
                    <p className="font-semibold text-slate-400">Award Date</p>
                    <p className="mt-1 font-semibold text-navy-900 dark:text-slate-200">{awardDate}</p>
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* Contextual Teaming / Bid Competitors profiles block */}
          <Card>
            <div className="flex items-center gap-2 mb-3">
              <Users size={16} className="text-slate-400" />
              <h3 className="text-sm font-extrabold text-navy-900 dark:text-white uppercase tracking-wider">
                {status === 'Open' || status === 'Closing Soon' ? 'Potential Teaming Partners' : 'Target Bid Competitors'}
              </h3>
            </div>
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-4 leading-relaxed">
              {status === 'Open' || status === 'Closing Soon'
                ? `The following local small businesses match the solicitation's NAICS code (${naicsCode}) and could act as joint venture or subcontracting partners for your active prime response:`
                : `The following companies have historically won or competed for similar opportunities under NAICS ${naicsCode} and represent target prime competitors to pitch subcontracting services to:`}
            </p>
            <div className="divide-y divide-slate-100 dark:divide-navy-800/80">
              {staticCompanies.slice(0, 3).map((comp) => (
                <div key={comp.uei} className="flex items-center justify-between py-3 first:pt-0 last:pb-0">
                  <div className="min-w-0">
                    <p className="font-bold text-xs text-navy-900 dark:text-slate-200 truncate">{comp.name}</p>
                    <p className="text-[10px] text-slate-400 mt-0.5">{renderSafeText(comp.industry)} · {renderSafeText(comp.city)}, {renderSafeText(comp.state)}</p>
                  </div>
                  <span className="rounded-full bg-slate-100 dark:bg-navy-900 px-2.5 py-0.5 text-[10px] font-semibold text-slate-500 dark:text-slate-400 font-mono">
                    Score: {comp.match}%
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Right Column: Actions Panel */}
        <div className="space-y-6">
          <Card className="!p-0 overflow-hidden border-t-4 border-t-brand-500">
            {/* Panel header */}
            <div className="bg-slate-50/50 dark:bg-navy-900 px-5 py-4 border-b border-slate-100 dark:border-navy-700">
              <h3 className="text-sm font-extrabold text-navy-900 dark:text-white">Actions Panel</h3>
              <p className="text-xs text-slate-400 mt-1">
                {status === 'Won' || status === 'Expired' || status === 'Closed'
                  ? 'The prime contract is awarded — subcontracting is the only route.'
                  : status === 'Expired'
                  ? 'This RFP is closed — save a reference or seek a subcontract with the contractor who won.'
                  : 'Choose your role: respond as prime contractor directly.'}
              </p>
            </div>

            {/* Mode buttons */}
            <div className="divide-y divide-slate-100 dark:divide-navy-800">
              {availableModes.map((mode) => {
                const cfg = MODE_CONFIG[mode];
                const Icon = cfg.icon;
                const modeState = modeStates[mode];
                const isDone = modeState === 'success' || modeState === 'already' || modeState === 'completed';
                const isSubmitting = modeState === 'submitting';
                const isExpanded = expandedMode === mode;

                // For subcontract, show awardee name in label if available
                const dynamicLabel = mode === 'subcontract' && awardAwardee
                  ? `Pitch to ${awardAwardee} for Subcontract`
                  : cfg.label;
                const dynamicSublabel = mode === 'subcontract' && awardAwardee
                  ? `Contact the prime contractor (${awardAwardee}) and offer your capabilities`
                  : cfg.sublabel;

                return (
                  <div key={mode} className="bg-white dark:bg-navy-800">
                    <div className="flex items-center gap-4 px-5 py-4">
                      {/* Icon */}
                      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                        isDone ? 'bg-emerald-50 dark:bg-emerald-950/30' :
                        mode === 'prime' ? 'bg-brand-50 dark:bg-navy-700' :
                        mode === 'subcontract' ? 'bg-violet-50 dark:bg-navy-700' :
                        'bg-slate-100 dark:bg-navy-700'
                      }`}>
                        {isDone
                          ? <Check size={18} className="text-emerald-500" />
                          : <Icon size={18} className={
                              mode === 'prime' ? 'text-brand-500' :
                              mode === 'subcontract' ? 'text-violet-500' :
                              'text-slate-500'
                            } />
                        }
                      </div>

                      {/* Text */}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-bold text-navy-900 dark:text-white">{dynamicLabel}</p>
                        <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">{dynamicSublabel}</p>
                        {/* Success / already / error message */}
                        {modeMessages[mode] && (
                          <p className={`text-xs mt-1.5 font-medium ${
                            modeState === 'error' ? 'text-rose-500' :
                            modeState === 'already' ? 'text-sky-600 dark:text-sky-400' :
                            'text-emerald-600 dark:text-emerald-400'
                          }`}>
                            {modeState === 'already' && '✓ Already requested — '}
                            {modeMessages[mode]}
                          </p>
                        )}
                      </div>

                      {/* Right actions */}
                      <div className="flex items-center gap-2 shrink-0">
                        {/* Info toggle */}
                        <button
                          onClick={() => setExpandedMode(isExpanded ? null : mode)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-navy-700 transition-colors"
                          title="Learn more"
                        >
                          {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                        </button>

                        {/* Action button */}
                        {modeState === 'completed' ? (
                          (() => {
                            const draft = draftRequests.find(r => r.mode === mode);
                            return (
                              <button
                                onClick={(e) => handleDownload(e, draft?.completed_filename)}
                                className="flex items-center gap-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white px-4 py-2 text-xs font-bold transition-all shadow-soft"
                              >
                                <FileDown size={13} />
                                Download PDF
                              </button>
                            );
                          })()
                        ) : (
                          <button
                            onClick={() => handleModeAction(mode)}
                            disabled={isDone || isSubmitting}
                            className={`flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition-all disabled:opacity-60 ${
                              isDone ? cfg.doneColor :
                              cfg.color
                            }`}
                          >
                            {isSubmitting && <Loader2 size={13} className="animate-spin" />}
                            {isDone && !isSubmitting && <Check size={13} />}
                            {!isDone && !isSubmitting && <Send size={13} />}
                            {isSubmitting ? 'Submitting…'
                              : isDone ? 'Requested'
                              : mode === 'prime' ? 'Start RFP Draft'
                              : 'Start Pitch'}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Expandable description */}
                    {isExpanded && (
                      <div className="px-5 pb-4 pt-0">
                        <div className={`rounded-xl px-4 py-3 text-xs leading-relaxed ${
                          mode === 'prime' ? 'bg-brand-50 text-brand-700 dark:bg-brand-950/20 dark:text-brand-300' :
                          mode === 'subcontract' ? 'bg-violet-50 text-violet-700 dark:bg-violet-950/20 dark:text-brand-300' :
                          'bg-slate-50 text-slate-600 dark:bg-navy-900 dark:text-slate-400'
                        }`}>
                          <p className="font-semibold mb-1">What happens when you click:</p>
                          <p>{cfg.description}</p>

                          {/* Manual winner input if none listed for subcontract */}
                          {mode === 'subcontract' && (
                            <div className="mt-3 border-t border-slate-200/50 dark:border-navy-700/50 pt-3">
                              {awardAwardee ? (
                                <p className="font-semibold">
                                  Target company: <span className="font-normal">{awardAwardee}</span>
                                  {pocEmail && <> · <a href={`mailto:${pocEmail}`} className="underline">{pocEmail}</a></>}
                                </p>
                              ) : (
                                <div className="space-y-1.5 max-w-sm">
                                  <label className="block font-semibold text-navy-900 dark:text-slate-300">
                                    Specify Winning Company Name:
                                  </label>
                                  <input
                                    type="text"
                                    value={manualWinner}
                                    onChange={(e) => setManualWinner(e.target.value)}
                                    placeholder="Enter name of the winning contractor..."
                                    className="w-full text-xs rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 outline-none focus:border-brand-400 dark:border-navy-700 dark:bg-navy-800 dark:text-white"
                                  />
                                </div>
                              )}
                            </div>
                          )}
                          
                          {mode === 'prime' && (
                            <p className="mt-2">
                              The Proposal Builder will open pre-filled with this solicitation's NAICS code ({naicsCode}),
                              agency ({agency}), and closing date ({closingDate}).
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Panel footer — link to Proposal Builder */}
            <div className="bg-slate-50 dark:bg-navy-900 px-5 py-3 border-t border-slate-200 dark:border-navy-700 flex items-center justify-between">
              <p className="text-xs text-slate-400">All drafts are saved in the Proposal Builder</p>
              <Link to="/proposal-builder" className="flex items-center gap-1.5 text-xs font-bold text-brand-500 hover:underline">
                <FileEdit size={13} /> Open Proposal Builder
              </Link>
            </div>
          </Card>

          {/* Quick details info card */}
          <Card className="text-xs space-y-3">
            <h4 className="font-extrabold text-navy-900 dark:text-white uppercase tracking-wider">
              Solicitation Context
            </h4>
            <div className="space-y-2">
              <div className="flex justify-between border-b border-slate-50 dark:border-navy-900/50 pb-1.5">
                <span className="text-slate-400">PSC Code</span>
                <span className="font-mono font-semibold text-navy-900 dark:text-slate-200">{pscCode}</span>
              </div>
              <div className="flex justify-between border-b border-slate-50 dark:border-navy-900/50 pb-1.5">
                <span className="text-slate-400">Point of Contact</span>
                <span className="font-semibold text-navy-900 dark:text-slate-200">{pocName}</span>
              </div>
              {pocEmail && (
                <div className="flex justify-between border-b border-slate-50 dark:border-navy-900/50 pb-1.5">
                  <span className="text-slate-400">POC Email</span>
                  <a href={`mailto:${pocEmail}`} className="font-mono text-brand-500 hover:underline">
                    {pocEmail}
                  </a>
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
