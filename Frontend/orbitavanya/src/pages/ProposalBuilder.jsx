import { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { Plus, Sparkles, FileDown, LayoutTemplate, Loader2, Database, AlertCircle, RefreshCw, Play, Eye, X, Building2, Trophy } from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';
import PreGenerationWizard from '../components/PreGenerationWizard.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';
export default function ProposalBuilder() {
  const { createAlert } = useNotifications();
  const notify = (title, message, link) => createAlert(title, message, link).catch(() => {});
  const [tab, setTab] = useState('all');

  // ----- Data States -----
  const [reports, setReports] = useState([]);
  const [draftRequests, setDraftRequests] = useState([]);
  const [activeTasks, setActiveTasks] = useState({});
  const [loading, setLoading] = useState(true);
  const [backendOffline, setBackendOffline] = useState(false);
  const [previewing, setPreviewing] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);

  // Company inventory states
  const [companyProfile, setCompanyProfile] = useState(null);
  const [companyLoading, setCompanyLoading] = useState(false);
  const [proposalTypeFilter, setProposalTypeFilter] = useState('all');

  // ----- Track individual triggering states -----
  const [triggeringId, setTriggeringId] = useState(null);
  const [activeWizardItem, setActiveWizardItem] = useState(null);
  const [showEditCompanyModal, setShowEditCompanyModal] = useState(false);
  const [editForm, setEditForm] = useState({});

  const [showAddInventoryModal, setShowAddInventoryModal] = useState(false);
  const [inventoryMode, setInventoryMode] = useState('document');
  const [inventoryForm, setInventoryForm] = useState({});

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

  useEffect(() => {
    if (previewing && previewing.filename && !backendOffline) {
      api.viewReportBlob(previewing.filename)
        .then((blob) => {
          const url = URL.createObjectURL(blob);
          setPreviewUrl(url);
        })
        .catch((err) => {
          console.error("Error creating preview URL:", err);
          setPreviewUrl(null);
        });
    } else {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        setPreviewUrl(null);
      }
    }
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewing, backendOffline]);

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

  // Fetch own company inventory (OrbitAvanya)
  const fetchOwnCompany = useCallback(() => {
    setCompanyLoading(true);
    api.getOwnCompanyProfile()
      .then(data => {
        setCompanyProfile(data || null);
        setCompanyLoading(false);
      })
      .catch(() => {
        setCompanyLoading(false);
      });
  }, []);

  useEffect(() => {
    fetchOwnCompany();
  }, [fetchOwnCompany]);

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
  const handleOpenWizard = (d, idKey) => {
    setActiveWizardItem({
      ...d,
      idKey: idKey,
      solicitation: d.solicitation_number || d.notice_id,
      title: d.tender_title || 'Tender Proposal',
      mode: d.mode,
      winner: d.target_company || d.award_awardee || ''
    });
  };

  const startProposalGeneration = (item, wizardData) => {
    setTriggeringId(item.idKey);

    api.generateProposal({
      mode: item.mode,
      solicitation: item.solicitation,
      winner: item.winner,
      tender_title: item.title,
      wizard_data: wizardData
    })
      .then(() => {
        setTriggeringId(null);
        fetchData();
        notify('Proposal build started', `Generating a draft for "${item.title || item.solicitation || 'this opportunity'}".`, '/proposal-builder');
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

  // Separate items into Drafts (Section 2) and History (Section 3)
  let draftItems = renderedItems.filter(item => item.status === 'Pending' || item.status === 'Processing' || item.type === 'task');
  let historyItems = renderedItems.filter(item => item.status === 'Completed' || item.type === 'report');

  if (proposalTypeFilter !== 'all') {
    draftItems = draftItems.filter(item => item.mode === proposalTypeFilter);
    historyItems = historyItems.filter(item => item.mode === proposalTypeFilter);
  }

  // Get CSS classes for the role badge
  const getModeBadge = (mode) => {
    if (mode === 'subcontract') {
      return { label: 'Subcontract Teaming', style: 'bg-violet-50 text-violet-700 dark:bg-violet-950/20 dark:text-violet-400 border border-violet-100 dark:border-violet-900/30' };
    }
    if (mode === 'other') {
      return { label: 'Product Match & Pitch', style: 'bg-amber-50 text-amber-700 dark:bg-amber-950/20 dark:text-amber-400 border border-amber-100 dark:border-amber-900/30' };
    }
    return { label: 'Prime Responder', style: 'bg-blue-50 text-blue-700 dark:bg-blue-950/20 dark:text-blue-400 border border-blue-100 dark:border-blue-900/30' };
  };

  return (
    <div className="pb-10">
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

      <div className="flex flex-col gap-8">
        {/* SECTION 1: Our Company Profile & Inventory */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-bold text-navy-900 dark:text-white flex items-center gap-2">
              <Building2 className="text-brand-500" size={20} />
              Our Company Profile & Inventory
            </h2>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setEditForm({
                    name: companyProfile?.name || 'OrbitAvanya Tech LLP',
                    uei: companyProfile?.uei || 'ORBIT1234567',
                    cage_code: companyProfile?.cage_code || '8A9B0',
                    primary_naics: companyProfile?.primary_naics || '541512',
                    primary_naics_desc: companyProfile?.primary_naics_desc || 'Computer Systems Design',
                    city: companyProfile?.city || 'Dallas',
                    state: companyProfile?.state || 'TX',
                    country: companyProfile?.country || 'USA',
                    email: companyProfile?.email || 'prasannadhamal982005@gmail.com',
                    phone: companyProfile?.phone || '+1-214-555-0199',
                    size: companyProfile?.size || 'Small',
                    certifications: companyProfile?.certifications?.join(', ') || 'SBA 8(a), WOSB, HUBZone',
                  });
                  setShowEditCompanyModal(true);
                }}
                className="flex items-center gap-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 px-4 py-2 text-xs font-bold text-slate-700 dark:bg-navy-800 dark:hover:bg-navy-700 dark:text-slate-300 transition-colors"
              >
                Edit / Update Profile
              </button>
              <button
                onClick={() => {
                  setInventoryForm({
                    name: '',
                    uei: '',
                    cage_code: '',
                    primary_naics: '',
                  });
                  setShowAddInventoryModal(true);
                }}
                className="flex items-center gap-1.5 rounded-xl bg-brand-50 hover:bg-brand-100 px-4 py-2 text-xs font-bold text-brand-700 dark:bg-brand-950/40 dark:text-brand-400 transition-colors"
              >
                <Database size={14} /> Add Inventory / Document Data
              </button>
            </div>
          </div>
          
          <Card className="!p-0 overflow-hidden">
            {companyProfile ? (
              <div className="p-6">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1">Company Name</p>
                    <p className="text-sm font-bold text-navy-900 dark:text-white">{companyProfile.name || companyProfile.company_name || 'OrbitAvanya Tech LLP'}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1">UEI</p>
                    <p className="text-sm font-bold text-navy-900 dark:text-white">{companyProfile.uei || 'N/A'}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1">CAGE Code</p>
                    <p className="text-sm font-bold text-navy-900 dark:text-white">{companyProfile.cage_code || 'N/A'}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1">Primary NAICS</p>
                    <p className="text-sm font-bold text-navy-900 dark:text-white">{companyProfile.primary_naics || 'N/A'}</p>
                    <p className="text-xs text-slate-500 mt-0.5">{companyProfile.primary_naics_desc}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1">State / Location</p>
                    <p className="text-sm font-bold text-navy-900 dark:text-white">{companyProfile.state || 'TX'}, {companyProfile.country || 'USA'}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1">Size</p>
                    <p className="text-sm font-bold text-navy-900 dark:text-white">{companyProfile.size || 'Small'}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1">Contact Email</p>
                    <p className="text-sm font-bold text-navy-900 dark:text-white">{companyProfile.email || 'N/A'}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-1">Contact Phone</p>
                    <p className="text-sm font-bold text-navy-900 dark:text-white">{companyProfile.phone || 'N/A'}</p>
                  </div>
                </div>

                <div className="mt-6 flex flex-wrap gap-x-8 gap-y-4 pt-6 border-t border-slate-100 dark:border-navy-800">
                  {companyProfile.certifications?.length > 0 && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-2">Certifications</p>
                      <div className="flex flex-wrap gap-2">
                        {companyProfile.certifications.map(cert => (
                          <span key={cert} className="inline-flex items-center rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 px-3 py-1 text-xs font-semibold">
                            {cert}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {companyProfile.past_performance_count !== undefined && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold mb-2">Experience</p>
                      <div className="flex items-center gap-2">
                        <Trophy className="text-amber-500" size={18} />
                        <p className="text-sm font-bold text-navy-900 dark:text-white">
                          {companyProfile.past_performance_count} Past Performance Records
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center px-6">
                <Building2 className="text-slate-300 dark:text-slate-600 mb-3" size={48} />
                <p className="text-base font-semibold text-slate-500 dark:text-slate-400">
                  {companyLoading ? 'Loading company data...' : 'Company profile not found'}
                </p>
                <p className="text-sm text-slate-400 dark:text-slate-500 mt-2 max-w-md">
                  Add your company details to use them automatically in generated proposals.
                </p>
              </div>
            )}
          </Card>
        </section>

        {/* SECTION 2: RFP & Proposal Drafts */}
        <section>
          <div className="mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <h2 className="text-lg font-bold text-navy-900 dark:text-white flex items-center gap-2">
              <LayoutTemplate className="text-brand-500" size={20} />
              RFP & Proposal Drafts
            </h2>
            
            <div className="flex bg-slate-100 p-1 rounded-xl dark:bg-navy-800 self-start">
              {[
                { value: 'all', label: 'All Proposals' },
                { value: 'prime', label: 'Prime RFP Response' },
                { value: 'subcontract', label: 'Subcontract Response' },
                { value: 'other', label: 'Product Match & Pitch' },
              ].map(opt => (
                <button
                  key={opt.value}
                  onClick={() => setProposalTypeFilter(opt.value)}
                  className={`px-4 py-1.5 text-xs font-bold rounded-lg transition-all ${
                    proposalTypeFilter === opt.value
                      ? 'bg-white text-brand-600 shadow-sm dark:bg-navy-700 dark:text-brand-400'
                      : 'text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {loading ? (
            <Card className="flex flex-col items-center justify-center py-20">
              <Loader2 className="animate-spin text-brand-500" size={32} />
              <p className="mt-4 text-sm text-slate-500 font-medium">Loading projects database...</p>
            </Card>
          ) : draftItems.length > 0 ? (
            <div className="flex flex-col gap-4">
              {draftItems.map((p) => {
                const badge = getModeBadge(p.mode);
                return (
                  <Card key={p.id}>
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2 mb-2">
                          <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${badge.style}`}>
                            {badge.label}
                          </span>
                          {p.solicitation && (
                            <span className="rounded-full bg-slate-100 dark:bg-navy-900 border border-slate-200 dark:border-navy-800 px-2.5 py-1 text-[10px] font-mono text-slate-600 dark:text-slate-400">
                              RFP: {p.solicitation}
                            </span>
                          )}
                          <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-bold ${
                            p.status === 'Processing' ? 'bg-brand-50 text-brand-700 dark:bg-brand-950/20 dark:text-brand-400 animate-pulse' :
                            'bg-amber-50 text-amber-700 dark:bg-amber-950/20 dark:text-amber-400'
                          }`}>
                            {p.status}
                          </span>
                        </div>
                        <h3 className="text-base font-bold text-navy-900 dark:text-white truncate" title={p.title}>
                          {p.title}
                        </h3>
                        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                          Target Entity: {p.company} • Requested: {p.updated}
                        </p>
                      </div>

                      <div className="flex-shrink-0 w-full md:w-64">
                        <div className="flex items-center justify-between gap-2 mb-1.5">
                          <span className="text-xs text-slate-500 font-medium truncate">
                            {p.status === 'Processing' ? (p.message || 'Building proposal...') : 'Ready to Build'}
                          </span>
                          <span className="text-xs font-bold text-navy-900 dark:text-white">{p.progress}%</span>
                        </div>
                        <div className="w-full h-2.5 bg-slate-100 dark:bg-navy-900 rounded-full overflow-hidden mb-3">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${
                              p.status === 'Processing' ? 'bg-brand-500 animate-pulse' : 'bg-slate-300 dark:bg-slate-600'
                            }`}
                            style={{ width: `${p.progress}%` }}
                          />
                        </div>
                        <div className="flex justify-end">
                          <button
                            onClick={() => handleOpenWizard(p.rawDraft, p.id)}
                            disabled={p.isReallyRunning || triggeringId !== null}
                            className="w-full md:w-auto flex items-center justify-center gap-1.5 rounded-xl bg-brand-500 px-4 py-2 text-sm font-bold text-white shadow-soft hover:bg-brand-600 disabled:opacity-50 transition-colors"
                          >
                            {p.isReallyRunning || triggeringId === p.id ? (
                              <>
                                <Loader2 size={14} className="animate-spin" />
                                <span>Building...</span>
                              </>
                            ) : (
                              <>
                                <Play size={14} />
                                <span>{p.status === 'Pending' ? 'Build Proposal' : 'Rebuild Proposal'}</span>
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          ) : (
             <div className="flex flex-col items-center justify-center py-12 text-center text-slate-400 dark:text-slate-500 border-2 border-dashed border-slate-200 dark:border-navy-800 rounded-2xl">
               <Database size={32} className="mb-3 text-slate-300" />
               <p className="text-sm font-medium">No pending drafts or active tasks.</p>
               <p className="text-xs mt-1">Start a new proposal from the Tenders page.</p>
             </div>
          )}
        </section>

        {/* SECTION 3: Generated Reports & Proposals History */}
        <section>
          <div className="mb-4 flex items-center gap-2">
            <h2 className="text-lg font-bold text-navy-900 dark:text-white flex items-center gap-2">
              <FileDown className="text-brand-500" size={20} />
              Generated Reports & Proposals History
            </h2>
          </div>

          <Card className="!p-0 overflow-hidden">
            {historyItems.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-navy-900/50 dark:text-slate-400">
                    <tr>
                      <th className="px-6 py-4 font-bold">Proposal Title</th>
                      <th className="px-6 py-4 font-bold">Solicitation</th>
                      <th className="px-6 py-4 font-bold">Type</th>
                      <th className="px-6 py-4 font-bold">Date Completed</th>
                      <th className="px-6 py-4 font-bold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-navy-800">
                    {historyItems.map((p) => {
                      const badge = getModeBadge(p.mode);
                      return (
                        <tr key={p.id} className="hover:bg-slate-50/50 dark:hover:bg-navy-800/50 transition-colors">
                          <td className="px-6 py-4">
                            <p className="font-bold text-navy-900 dark:text-white max-w-md truncate" title={p.title}>
                              {p.title}
                            </p>
                            <p className="text-xs text-slate-500 mt-0.5">Entity: {p.company}</p>
                          </td>
                          <td className="px-6 py-4 font-mono text-xs text-slate-600 dark:text-slate-400">
                            {p.solicitation || 'N/A'}
                          </td>
                          <td className="px-6 py-4">
                            <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${badge.style}`}>
                              {badge.label}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-xs text-slate-500">
                            {p.updated}
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center justify-end gap-2">
                              {p.filename && (
                                <>
                                  <button
                                    onClick={() => setPreviewing(p)}
                                    className="flex items-center gap-1.5 rounded-xl bg-violet-50 hover:bg-violet-100 px-3 py-1.5 text-xs font-bold text-violet-700 dark:bg-violet-950/40 dark:text-violet-400 transition-colors"
                                  >
                                    <Eye size={14} /> View
                                  </button>
                                  <button
                                    onClick={(e) => handleDownload(e, p.filename)}
                                    className="flex items-center gap-1.5 rounded-xl bg-brand-50 hover:bg-brand-100 px-3 py-1.5 text-xs font-bold text-brand-700 dark:bg-brand-950/40 dark:text-brand-400 transition-colors"
                                  >
                                    <FileDown size={14} /> Download
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center text-slate-400 dark:text-slate-500">
                <FileDown size={32} className="mb-3 text-slate-300" />
                <p className="text-sm font-medium">No completed proposals yet.</p>
              </div>
            )}
          </Card>
        </section>
      </div>

      {/* Inline Document Preview Modal */}
      {previewing && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/70 p-4 backdrop-blur-xs"
          onClick={() => setPreviewing(null)}
        >
          <div
            className="flex h-[90vh] w-full max-w-5xl flex-col rounded-2xl bg-white shadow-soft dark:bg-navy-800 border border-slate-100 dark:border-navy-700 overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-navy-700">
              <div className="min-w-0 pr-4">
                <h3 className="text-sm font-bold text-navy-900 dark:text-white truncate">
                  {previewing.title || previewing.filename}
                </h3>
                <p className="text-xs text-slate-400 font-mono mt-0.5">{previewing.filename}</p>
              </div>

              <div className="flex items-center gap-2">
                {previewing.filename && (
                  <button
                    onClick={(e) => handleDownload(e, previewing.filename)}
                    className="flex items-center gap-1.5 rounded-xl bg-brand-500 px-3 py-1.5 text-xs font-bold text-white shadow-soft hover:bg-brand-600"
                  >
                    <FileDown size={14} /> Download
                  </button>
                )}
                <button
                  onClick={() => setPreviewing(null)}
                  className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-100 hover:text-navy-900 dark:hover:bg-navy-700 dark:hover:text-white"
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            <div className="flex-1 bg-slate-100 dark:bg-navy-900 p-2">
              {previewUrl ? (
                <iframe
                  src={previewUrl}
                  title="Document Preview"
                  className="h-full w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white"
                />
              ) : (
                <div className="flex h-full flex-col items-center justify-center text-slate-400">
                  <Loader2 size={32} className="animate-spin text-brand-500 mb-2" />
                  <p className="text-xs font-medium">Loading document viewer...</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Pre-Generation Wizard Modal */}
      {activeWizardItem && (
        <PreGenerationWizard
          solicitationNumber={activeWizardItem.solicitation || activeWizardItem.title}
          proposalType={activeWizardItem.mode || 'prime'}
          onCancel={() => setActiveWizardItem(null)}
          onConfirmGenerate={(wizardData) => {
            const item = activeWizardItem;
            setActiveWizardItem(null);
            startProposalGeneration(item, wizardData);
          }}
        />
      )}

      {/* Edit Company Profile Modal */}
      {showEditCompanyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/70 p-4 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-2xl bg-white shadow-soft dark:bg-navy-800 border border-slate-100 dark:border-navy-700 overflow-hidden">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-navy-700">
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">Edit Company Profile</h3>
              <button
                onClick={() => setShowEditCompanyModal(false)}
                className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-100 hover:text-navy-900 dark:hover:bg-navy-700 dark:hover:text-white"
              >
                <X size={18} />
              </button>
            </div>
            <div className="p-5">
              <div className="grid grid-cols-2 gap-4">
                {['name', 'uei', 'cage_code', 'primary_naics', 'state', 'email', 'phone', 'size', 'certifications'].map(field => (
                  <div key={field} className={field === 'certifications' || field === 'name' ? 'col-span-2' : ''}>
                    <label className="mb-1 block text-[10px] uppercase tracking-wide text-slate-500 font-semibold">{field.replace('_', ' ')} {['name', 'uei'].includes(field) ? <span className="text-rose-500 font-extrabold ml-0.5">*</span> : <span className="text-[10px] text-slate-400 font-normal ml-1 flex-inline normal-case tracking-normal">(Optional)</span>}</label>
                    <input
                      className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                      value={editForm[field] || ''}
                      onChange={e => setEditForm({ ...editForm, [field]: e.target.value })}
                    />
                  </div>
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-3 border-t border-slate-100 px-5 py-4 dark:border-navy-700 bg-slate-50 dark:bg-navy-900/50">
              <button
                onClick={() => setShowEditCompanyModal(false)}
                className="rounded-xl px-4 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  try {
                    await api.updateOwnCompanyProfile({
                      ...editForm,
                      certifications: typeof editForm.certifications === 'string' 
                        ? editForm.certifications.split(',').map(s => s.trim()).filter(Boolean)
                        : editForm.certifications
                    });
                    fetchOwnCompany();
                    setShowEditCompanyModal(false);
                  } catch (err) {
                    alert('Failed to update: ' + err.message);
                  }
                }}
                className="rounded-xl bg-brand-500 px-4 py-2 text-xs font-bold text-white hover:bg-brand-600"
              >
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add Inventory Modal */}
      {showAddInventoryModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/70 p-4 backdrop-blur-xs">
          <div className="w-full max-w-2xl rounded-2xl bg-white shadow-soft dark:bg-navy-800 border border-slate-100 dark:border-navy-700 overflow-hidden flex flex-col max-h-[90vh]">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-navy-700">
              <h3 className="text-sm font-bold text-navy-900 dark:text-white flex items-center gap-2">
                <Database size={16} className="text-brand-500" />
                Add Inventory / Document Data
              </h3>
              <button
                onClick={() => setShowAddInventoryModal(false)}
                className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-100 hover:text-navy-900 dark:hover:bg-navy-700 dark:hover:text-white"
              >
                <X size={18} />
              </button>
            </div>
            
            <div className="flex bg-slate-50 border-b border-slate-100 dark:bg-navy-900/50 dark:border-navy-700 px-5 pt-3">
              {[
                { id: 'document', label: 'MongoDB JSON Document' },
                { id: 'manual', label: 'Manual Entry' },
                { id: 'upload', label: 'File Upload (.json / .csv)' }
              ].map(mode => (
                <button
                  key={mode.id}
                  onClick={() => setInventoryMode(mode.id)}
                  className={`px-4 py-2 text-xs font-bold border-b-2 transition-colors ${
                    inventoryMode === mode.id
                      ? 'border-brand-500 text-brand-600 dark:text-brand-400'
                      : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400'
                  }`}
                >
                  {mode.label}
                </button>
              ))}
            </div>

            <div className="p-5 overflow-y-auto flex-1">
              {inventoryMode === 'manual' && (
                <div className="grid grid-cols-2 gap-4">
                  {['name', 'uei', 'cage_code', 'primary_naics', 'state', 'email', 'phone', 'size'].map(field => (
                    <div key={field}>
                      <label className="mb-1 block text-[10px] uppercase tracking-wide text-slate-500 font-semibold">{field.replace('_', ' ')} {['name', 'uei'].includes(field) ? <span className="text-rose-500 font-extrabold ml-0.5">*</span> : <span className="text-[10px] text-slate-400 font-normal ml-1 flex-inline normal-case tracking-normal">(Optional)</span>}</label>
                      <input
                        className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white"
                        value={inventoryForm[field] || ''}
                        onChange={e => setInventoryForm({ ...inventoryForm, [field]: e.target.value })}
                        placeholder={`Enter ${field.replace('_', ' ')}`}
                      />
                    </div>
                  ))}
                  <div className="col-span-2">
                    <label className="mb-1 block text-[10px] uppercase tracking-wide text-slate-500 font-semibold">Additional Inventory Details <span className="text-[10px] text-slate-400 font-normal ml-1 flex-inline normal-case tracking-normal">(Optional)</span></label>
                    <textarea 
                      className="w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-900 dark:text-white h-24"
                      placeholder="Paste any additional products, services, or descriptions here..."
                    />
                  </div>
                </div>
              )}

              {inventoryMode === 'upload' && (
                <div className="flex flex-col items-center justify-center py-16 px-6 border-2 border-dashed border-slate-200 dark:border-navy-700 rounded-xl bg-slate-50/50 dark:bg-navy-900/20">
                  <FileDown size={40} className="text-brand-400 mb-4" />
                  <p className="text-sm font-bold text-navy-900 dark:text-white mb-1">Drag and drop your files here</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mb-4 text-center">
                    Support for .json, .csv files containing company profile, NAICS lists, past performances, or product inventory.
                  </p>
                  <button className="rounded-xl bg-white border border-slate-200 px-4 py-2 text-xs font-bold text-slate-700 shadow-sm dark:bg-navy-800 dark:border-navy-600 dark:text-slate-300">
                    Browse Files
                  </button>
                </div>
              )}

              {inventoryMode === 'document' && (
                <div className="rounded-xl border border-slate-200 dark:border-navy-700 bg-slate-50 dark:bg-navy-900 p-4 font-mono text-xs shadow-sm overflow-x-auto space-y-2">
                  <div className="text-slate-400 dark:text-slate-500 font-bold">{"{"}</div>
                  <div className="pl-3 space-y-2.5">
                    {[
                      { key: 'name', type: 'string', required: true, placeholder: '"OrbitAvanya Tech LLP"' },
                      { key: 'uei', type: 'string', required: true, placeholder: '"ORBIT1234567"' },
                      { key: 'cage_code', type: 'string', required: false, placeholder: '"8A9B0"' },
                      { key: 'primary_naics', type: 'string/int', required: false, placeholder: '"541512"' },
                      { key: 'primary_naics_desc', type: 'string', required: false, placeholder: '"Computer Systems Design Services"' },
                      { key: 'city', type: 'string', required: false, placeholder: '"Dallas"' },
                      { key: 'state', type: 'string', required: false, placeholder: '"TX"' },
                      { key: 'email', type: 'string', required: false, placeholder: '"contact@orbitavanya.com"' },
                      { key: 'phone', type: 'string', required: false, placeholder: '"+1-214-555-0199"' },
                    ].map(f => (
                      <div key={f.key} className="flex flex-wrap items-center gap-2">
                        <div className="w-36 shrink-0 flex items-center">
                          <span className="text-brand-600 dark:text-brand-400 font-bold">"{f.key}"</span>
                          {f.required ? (
                            <span className="text-rose-500 font-extrabold ml-0.5" title="Required field">*</span>
                          ) : (
                            <span className="text-[10px] text-slate-400 font-normal ml-1">(Optional)</span>
                          )}
                        </div>
                        <span className="text-slate-400 font-bold">:</span>
                        <span className="rounded bg-brand-50 dark:bg-navy-800 text-brand-700 dark:text-brand-300 border border-brand-200/60 dark:border-navy-700 px-1.5 py-0.5 text-[10px] font-semibold w-20 text-center shrink-0">
                          [{f.type}]
                        </span>
                        <input 
                          value={inventoryForm[f.key] || ''} 
                          onChange={e => setInventoryForm({...inventoryForm, [f.key]: e.target.value})} 
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
                        value={inventoryForm.size || 'Small'} 
                        onChange={e => setInventoryForm({...inventoryForm, size: e.target.value})} 
                        className="flex-1 min-w-[160px] rounded-lg border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-800 px-3 py-1.5 text-xs font-semibold text-navy-900 dark:text-white focus:ring-2 focus:ring-brand-400 outline-none cursor-pointer"
                      >
                        <option value="Small">"Small"</option>
                        <option value="Large">"Large"</option>
                      </select>
                    </div>
                  </div>
                  <div className="text-slate-400 dark:text-slate-500 font-bold">{"}"}</div>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 border-t border-slate-100 px-5 py-4 dark:border-navy-700 bg-slate-50 dark:bg-navy-900/50 mt-auto">
              <button
                onClick={() => setShowAddInventoryModal(false)}
                className="rounded-xl px-4 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-navy-800"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  try {
                    await api.updateOwnCompanyProfile({
                      ...inventoryForm
                    });
                    fetchOwnCompany();
                    setShowAddInventoryModal(false);
                    notify('Inventory Updated', 'Company profile and inventory data successfully added.');
                  } catch (err) {
                    alert('Failed to save data: ' + err.message);
                  }
                }}
                className="rounded-xl bg-brand-500 px-4 py-2 text-xs font-bold text-white hover:bg-brand-600 flex items-center gap-1.5"
              >
                <Database size={14} /> Add Document
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

