import { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Sparkles, FileDown, LayoutTemplate, Loader2, Database, AlertCircle, RefreshCw, Play } from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';

export default function ProposalBuilder() {
  const [tab, setTab] = useState('all');

  // ----- Data States -----
  const [reports, setReports] = useState([]);
  const [draftRequests, setDraftRequests] = useState([]);
  const [activeTasks, setActiveTasks] = useState({});
  const [loading, setLoading] = useState(true);
  const [backendOffline, setBackendOffline] = useState(false);

  // ----- Track individual triggering states -----
  const [triggeringId, setTriggeringId] = useState(null);

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

  // Ref to hold the latest active tasks to prevent stable interval resets
  const activeTasksRef = useRef({});
  useEffect(() => {
    activeTasksRef.current = activeTasks;
  }, [activeTasks]);

  // ----- Fetch reports, draft requests and task status -----
  const fetchData = useCallback(() => {
    setLoading(true);
    // Fetch generated reports
    const p1 = api.getReports()
      .catch(() => null);

    // Fetch active draft requests
    const p2 = api.getAllDraftRequests()
      .catch(() => null);

    // Fetch active background tasks
    const p3 = api.getProposals()
      .catch(() => null);

    Promise.all([p1, p2, p3]).then(([reportsData, draftsData, tasksData]) => {
      if (reportsData === null && draftsData === null) {
        setBackendOffline(true);
        setReports([]);
        setDraftRequests([]);
      } else {
        setBackendOffline(false);
        setReports(reportsData || []);
        setDraftRequests(draftsData || []);
        setActiveTasks(tasksData || {});
      }
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // ----- WebSocket Realtime Tracking -----
  useEffect(() => {
    let ws;
    let reconnectTimeout;
    
    function connect() {
      const token = localStorage.getItem('orbitavanya_token');
      const wsUrl = api.getWebSocketUrl(`/api/proposals/ws${token ? `?token=${encodeURIComponent(token)}` : ''}`);
      ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Check if any active task finished (status changed from processing to something else)
          let anyStatusChanged = false;
          Object.keys(data).forEach(k => {
            const prevStatus = activeTasksRef.current[k]?.status;
            const currentStatus = data[k]?.status;
            if (prevStatus === 'processing' && currentStatus !== 'processing') {
              anyStatusChanged = true;
            }
          });

          // Update tasks state
          setActiveTasks(data || {});

          if (anyStatusChanged) {
            // Refetch completed proposals and draft requests from DB
            fetchData();
          }
        } catch (err) {
          console.error("WebSocket message parsing error:", err);
        }
      };

      ws.onclose = () => {
        // Retry connection in 5 seconds if disconnected
        reconnectTimeout = setTimeout(connect, 5000);
      };

      ws.onerror = (err) => {
        console.warn("WebSocket connection error:", err);
      };
    }

    connect();

    return () => {
      if (ws) {
        ws.onclose = null;
        ws.close();
      }
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, [fetchData]);

  // ----- Start building a pending draft manually -----
  const handleBuildDraft = (d, idKey) => {
    setTriggeringId(idKey);
    const solicitation = d.solicitation_number || d.notice_id;
    const winner = d.target_company || d.award_awardee || '';

    api.createProposal({
      mode: d.mode,
      solicitation: solicitation,
      winner: winner,
      tender_title: d.tender_title
    })
      .then(() => {
        setTriggeringId(null);
        fetchData();
      })
      .catch(err => {
        setTriggeringId(null);
        alert(err.message);
      });
  };

  // ----- Render lists combined -----
  const renderedItems = [];
  const mergedTaskKeys = new Set();

  // 1. Add draft requests (pending / completed / processing)
  draftRequests.forEach((d, idx) => {
    const solicitation = d.solicitation_number || d.notice_id;
    const targetComp = d.target_company || '';
    
    // Compute task key lookup in in-memory dict
    let matchingTaskKey = '';
    if (d.mode === 'prime') {
      matchingTaskKey = `prime-${solicitation}`;
    } else if (d.mode === 'subcontract') {
      matchingTaskKey = `subcontract-${solicitation}-${targetComp}`;
    }

    const activeTask = activeTasks[matchingTaskKey];
    const isReallyRunning = activeTask && activeTask.status === 'processing';
    const isProcessing = d.draft_status === 'processing' || isReallyRunning;
    
    if (isReallyRunning) {
      mergedTaskKeys.add(matchingTaskKey);
    }

    // Determine status badge based on draft request DB record
    const statusLabel = d.draft_status === 'completed' ? 'Completed' :
                        isProcessing ? 'Processing' : 'Pending';

    renderedItems.push({
      id: `draft-${solicitation}-${d.mode}`,
      type: 'draft_request',
      rawDraft: d,
      title: d.tender_title || `Tender Draft Request`,
      subtitle: `${d.agency || 'Federal Agency'} · NAICS ${d.naics_code || 'General'}`,
      status: statusLabel,
      progress: d.draft_status === 'completed' ? 100 : (activeTask?.progress || 0),
      message: activeTask?.message || null,
      updated: d.requested_at ? d.requested_at.replace('T', ' ').replace('Z', ' UTC') : 'Recently requested',
      company: d.target_company || d.award_awardee || 'OrbitAvanya Tech',
      solicitation: solicitation || 'N/A',
      mode: d.mode,
      filename: d.completed_filename || null,
      isReallyRunning: isReallyRunning
    });
  });

  // 2. Add active background tasks (running and not merged yet)
  Object.keys(activeTasks).forEach(k => {
    if (mergedTaskKeys.has(k)) return;
    const task = activeTasks[k];
    if (task.status === 'processing') {
      renderedItems.push({
        id: `task-${k}`,
        type: 'task',
        title: task.tender_title || (task.mode === 'subcontract'
          ? `Subcontract Pitch: ${task.winner}`
          : `Prime RFP Response`),
        subtitle: task.message || 'Scraping company profiles...',
        status: 'Processing',
        progress: task.progress || 10,
        updated: 'Running...',
        company: task.winner || 'OrbitAvanya Tech',
        solicitation: task.solicitation || 'N/A',
        mode: task.mode || 'prime'
      });
    }
  });

  // 3. Add generated PDF reports (skip if already handled by draft request cards)
  reports.forEach((r) => {
    const solicitation = r.solicitation_number;
    const pType = r.proposal_type || '';
    
    let resolvedMode = 'prime';
    if (pType.toLowerCase().includes('subcontract') || pType.toLowerCase().includes('pitch')) {
      resolvedMode = 'subcontract';
    }

    // Check duplicate
    const isDuplicate = draftRequests.some(d => 
      (d.solicitation_number === solicitation || d.notice_id === solicitation) && d.mode === resolvedMode
    );
    if (isDuplicate) return;

    renderedItems.push({
      id: `report-${r.filename}`,
      type: 'report',
      title: r.title,
      subtitle: `${r.proposal_type} · Ref ${r.ref}`,
      status: 'Completed',
      progress: 100,
      updated: r.date,
      company: r.company_name,
      filename: r.filename,
      size: r.size,
      solicitation: solicitation !== 'N/A' ? solicitation : '',
      mode: resolvedMode
    });
  });

  // Filter items based on selected tab
  const filteredItems = renderedItems.filter(item => {
    if (tab === 'all') return true;
    if (tab === 'Completed') return item.status === 'Completed' || item.type === 'report';
    if (tab === 'Draft') return item.status === 'Pending' || item.status === 'Processing' || item.type === 'task';
    return true;
  });

  // Get CSS classes for the role badge
  const getModeBadge = (mode) => {
    if (mode === 'subcontract') {
      return { label: 'Subcontract Teaming', style: 'bg-violet-50 text-violet-700 dark:bg-violet-950/20 dark:text-violet-400 border border-violet-100 dark:border-violet-900/30' };
    }
    return { label: 'Prime Responder', style: 'bg-blue-50 text-blue-700 dark:bg-blue-950/20 dark:text-blue-400 border border-blue-100 dark:border-blue-900/30' };
  };

  return (
    <div>
      <PageHeader
        title="Proposal Builder"
        subtitle="Manage and build your direct RFP responses and subcontract pitches"
        action={
          <Link
            to="/tenders"
            className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft hover:bg-brand-600 transition-colors"
          >
            <Plus size={16} /> Find RFP on Tenders Page
          </Link>
        }
      />

      {backendOffline && (
        <div className="mb-4 flex items-center gap-2 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-xs text-amber-700 dark:bg-amber-950/30 dark:border-amber-900/30 dark:text-amber-400">
          <AlertCircle size={13} />
          Showing offline templates. Start the backend server to build draft proposals.
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* Left column: Action guidance */}
        <Card className="lg:col-span-1">
          <div className="flex items-center gap-2">
            <LayoutTemplate size={16} className="text-slate-400" />
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Build Flow Guide</h3>
          </div>
          
          <div className="mt-4 space-y-4 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            <div>
              <p className="font-bold text-navy-900 dark:text-slate-300">1. Select RFP</p>
              <p>Go to the Tenders tab to find active opportunities cached from SAM.gov.</p>
            </div>
            <div>
              <p className="font-bold text-navy-900 dark:text-slate-300">2. Request Proposal Mode</p>
              <p>Click "Respond as Prime" for open RFPs, or "Seek Subcontract" if a contractor won it.</p>
            </div>
            <div>
              <p className="font-bold text-navy-900 dark:text-slate-300">3. Run Compilation Pipeline</p>
              <p>Wired drafts appear in the list. Click "Build Proposal" to start background document compiles.</p>
            </div>
          </div>

          <div className="mt-6 rounded-xl bg-brand-50 p-4 dark:bg-navy-900">
            <div className="flex items-center gap-2">
              <Sparkles size={15} className="text-brand-600" />
              <p className="text-sm font-bold text-brand-700">Need new projects?</p>
            </div>
            <p className="mt-2 text-xs text-brand-700/80 dark:text-slate-400">
              Search live opportunities matching your company NAICS codes.
            </p>
            <Link
              to="/tenders"
              className="mt-3 block w-full text-center rounded-lg bg-brand-500 py-2 text-xs font-bold text-white hover:bg-brand-600"
            >
              Go to Tenders Page
            </Link>
          </div>
        </Card>

        {/* Right column: list of active / completed proposals */}
        <div className="flex flex-col gap-5 lg:col-span-2">
          {/* Tabs bar */}
          <div className="flex gap-2">
            {[
              { key: 'all', label: 'All Projects' },
              { key: 'Draft', label: 'Drafts & Tasks' },
              { key: 'Completed', label: 'Completed Reports' }
            ].map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`rounded-lg px-3.5 py-2 text-xs font-semibold transition-colors ${
                  tab === t.key
                    ? 'bg-brand-500 text-white'
                    : 'bg-white text-slate-500 border border-slate-200 dark:bg-navy-800 dark:border-navy-700 dark:text-slate-400'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Loading spinner */}
          {loading ? (
            <Card className="flex flex-col items-center justify-center py-20">
              <Loader2 className="animate-spin text-brand-500" size={32} />
              <p className="mt-4 text-sm text-slate-500 font-medium">Loading projects database...</p>
            </Card>
          ) : (
            <div className="flex flex-col gap-3">
              {filteredItems.map((p) => {
                const badge = getModeBadge(p.mode);
                return (
                  <Card key={p.id}>
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        {/* Role Badge and Solicitation badge */}
                        <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
                          <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase ${badge.style}`}>
                            {badge.label}
                          </span>
                          {p.solicitation && (
                            <span className="rounded-full bg-slate-100 dark:bg-navy-900 border border-slate-200 dark:border-navy-800 px-2 py-0.5 text-[9px] font-mono text-slate-500 dark:text-slate-400">
                              RFP: {p.solicitation}
                            </span>
                          )}
                        </div>
                        <p className="text-sm font-bold text-navy-900 dark:text-white truncate" title={p.title}>
                          {p.title}
                        </p>
                        <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                          Target Entity: {p.company}
                        </p>
                      </div>
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold ${
                        p.status === 'Completed' ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-400' :
                        p.status === 'Processing' ? 'bg-brand-50 text-brand-700 dark:bg-brand-950/20 dark:text-brand-400 animate-pulse' :
                        'bg-slate-100 text-slate-500 dark:bg-navy-900 dark:text-slate-500'
                      }`}>
                        {p.status}
                      </span>
                    </div>

                    {/* Progress bar section */}
                    <div className="mt-3">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-[11px] text-slate-400 font-medium truncate max-w-[280px]">
                          {p.status === 'Processing' ? (p.message || 'Building proposal...') : 'Progress'}
                        </span>
                        <span className="text-xs font-bold text-navy-900 dark:text-white">{p.progress}%</span>
                      </div>
                      <div className="w-full h-2 bg-slate-100 dark:bg-navy-900 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            p.status === 'Completed' ? 'bg-emerald-500' :
                            p.status === 'Processing' ? 'bg-brand-500 animate-pulse' :
                            'bg-slate-400'
                          }`}
                          style={{ width: `${p.progress}%` }}
                        />
                      </div>
                    </div>

                    <div className="mt-4 flex items-center justify-between border-t border-slate-50 dark:border-navy-900/50 pt-2.5">
                      <p className="text-[11px] text-slate-400">{p.type === 'report' ? 'Generated' : 'Requested'} {p.updated}</p>
                      
                      <div className="flex items-center gap-1.5">
                        {/* Show build or rebuild button for non-completed draft requests */}
                        {p.type === 'draft_request' && p.status !== 'Completed' && (
                          <button
                            onClick={() => handleBuildDraft(p.rawDraft, p.id)}
                            disabled={p.isReallyRunning || triggeringId !== null}
                            className="flex items-center gap-1 rounded-xl bg-brand-500 px-3.5 py-1.5 text-xs font-bold text-white shadow-soft hover:bg-brand-600 disabled:opacity-50 transition-colors"
                          >
                            {p.isReallyRunning || triggeringId === p.id ? (
                              <>
                                <Loader2 size={12} className="animate-spin" />
                                <span>Building...</span>
                              </>
                            ) : (
                              <>
                                <Play size={12} />
                                <span>{p.status === 'Pending' ? 'Build Proposal' : 'Rebuild Proposal'}</span>
                              </>
                            )}
                          </button>
                        )}

                        {/* View in Reports button for Completed drafts/reports */}
                        {p.status === 'Completed' && (
                          <Link
                            to="/reports"
                            className="flex items-center gap-1 rounded-xl bg-violet-100 hover:bg-violet-200 px-3.5 py-1.5 text-xs font-bold text-violet-700 dark:bg-violet-950/40 dark:text-violet-400 transition-colors"
                          >
                            View in Reports
                          </Link>
                        )}

                        {/* Download button for completed drafts */}
                        {p.filename && (
                           <button
                             onClick={(e) => handleDownload(e, p.filename)}
                             className="flex items-center gap-1 rounded-xl bg-brand-50 hover:bg-brand-100 px-3.5 py-1.5 text-xs font-bold text-brand-700 dark:bg-brand-950/40 dark:text-brand-400 transition-colors"
                             title="Download PDF"
                           >
                             <FileDown size={12} />
                             Download PDF
                           </button>
                        )}
                      </div>
                    </div>
                  </Card>
                );
              })}

              {filteredItems.length === 0 && (
                <div className="flex flex-col items-center justify-center py-10 text-center text-slate-400 dark:text-slate-500">
                  <Database size={28} className="mb-2 text-slate-300" />
                  No proposals found for this category.
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
