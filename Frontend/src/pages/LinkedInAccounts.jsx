import { useState, useEffect, useRef } from 'react';
import { 
  Play, Pause, Trash2, RefreshCw, Plus, Globe, Shield, Activity, 
  ChevronRight, X, AlertCircle, CheckCircle2, Loader2, Keyboard, MousePointer
} from 'lucide-react';
import { api, BASE_URL } from '../lib/api.jsx';

export default function LinkedInAccounts() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  
  // Connection Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [connectLabel, setConnectLabel] = useState('');
  const [connectRegion, setConnectRegion] = useState('usa');
  const [connectStep, setConnectStep] = useState(1); // 1 = setup, 2 = websocket stream
  
  // WebSocket stream state
  const [wsStatus, setWsStatus] = useState('idle');
  const [wsMessage, setWsMessage] = useState('');
  const [screenImage, setScreenImage] = useState(null);
  const [manualText, setManualText] = useState('');
  
  const wsRef = useRef(null);
  const imageRef = useRef(null);

  const fetchAccounts = async () => {
    setLoading(true);
    try {
      const data = await api.getLinkedInAccounts();
      setAccounts(data || []);
      setError('');
    } catch (err) {
      setError(err.message || 'Failed to fetch accounts.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, []);

  const handlePause = async (id) => {
    try {
      await api.pauseLinkedInAccount(id);
      fetchAccounts();
    } catch (err) {
      alert(err.message || 'Failed to pause account.');
    }
  };

  const handleResume = async (id) => {
    try {
      await api.resumeLinkedInAccount(id);
      fetchAccounts();
    } catch (err) {
      alert(err.message || 'Failed to resume account.');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Are you sure you want to disconnect this LinkedIn account?')) return;
    try {
      await api.deleteLinkedInAccount(id);
      fetchAccounts();
    } catch (err) {
      alert(err.message || 'Failed to delete account.');
    }
  };

  const startGuidedLogin = () => {
    if (!connectLabel.trim()) {
      alert('Please enter an account label.');
      return;
    }
    setConnectStep(2);
    setWsStatus('connecting');
    setWsMessage('Initializing remote browser context...');
    
    // Connect to WebSocket
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsBase = BASE_URL.replace(/^http/, 'ws');
    const token = localStorage.getItem('orbitavanya_token');
    const wsUrl = `${wsBase}/api/linkedin/accounts/connect/ws?region=${connectRegion}&label=${encodeURIComponent(connectLabel)}&token=${token}`;
    
    const socket = new WebSocket(wsUrl);
    wsRef.current = socket;

    socket.onopen = () => {
      logger('WebSocket opened successfully.');
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'status') {
          setWsStatus(data.status);
          setWsMessage(data.message);
          if (data.status === 'authenticated') {
            setTimeout(() => {
              closeConnectModal();
              fetchAccounts();
            }, 3000);
          }
        } else if (data.type === 'screen') {
          setScreenImage(data.image);
        }
      } catch (e) {
        console.error('Error parsing WS message:', e);
      }
    };

    socket.onclose = (event) => {
      logger('WebSocket closed.');
      setWsStatus('closed');
      setWsMessage(event.reason || 'Browser session disconnected.');
    };

    socket.onerror = (err) => {
      console.error('WebSocket error:', err);
      setWsStatus('error');
      setWsMessage('WebSocket connection failed.');
    };
  };

  const handleImageClick = (e) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    if (!imageRef.current) return;

    const rect = imageRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    // Scale to the browser viewport size (1280x800)
    const scaleX = 1280 / rect.width;
    const scaleY = 800 / rect.height;
    const x = Math.round(clickX * scaleX);
    const y = Math.round(clickY * scaleY);

    wsRef.current.send(JSON.stringify({ type: 'click', x, y }));
  };

  const handleKeyDown = (e) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    
    // Prevent normal browser navigation/scrolling keys when focused
    const preventKeys = ['ArrowUp', 'ArrowDown', 'Space', 'Tab', 'Backspace', 'Enter'];
    if (preventKeys.includes(e.key)) {
      e.preventDefault();
    }

    if (e.key.length === 1) {
      wsRef.current.send(JSON.stringify({ type: 'type', text: e.key }));
    } else {
      wsRef.current.send(JSON.stringify({ type: 'press', key: e.key }));
    }
  };

  const sendManualText = () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    if (!manualText) return;
    wsRef.current.send(JSON.stringify({ type: 'type', text: manualText }));
    setManualText('');
  };

  const sendSpecialKey = (key) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: 'press', key }));
  };

  const closeConnectModal = () => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    wsRef.current = null;
    setScreenImage(null);
    setConnectLabel('');
    setConnectStep(1);
    setWsStatus('idle');
    setIsModalOpen(false);
  };

  const logger = (msg) => {
    console.log(`[LinkedIn guided login] ${msg}`);
  };

  return (
    <div className="mx-auto max-w-7xl">
      {/* Header */}
      <div className="mb-6 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-navy-900 dark:text-white">
            LinkedIn Outreach Accounts
          </h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Connect and manage multiple LinkedIn accounts by region for personalized messaging.
          </p>
        </div>
        <button
          onClick={() => setIsModalOpen(true)}
          className="inline-flex items-center gap-2 rounded-xl bg-brand-500 hover:bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-soft transition-colors"
        >
          <Plus size={18} />
          Connect Account
        </button>
      </div>

      {error && (
        <div className="mb-6 rounded-xl border border-rose-200 bg-rose-50 p-4 dark:border-rose-900/40 dark:bg-rose-950/20 text-rose-700 dark:text-rose-400">
          <div className="flex items-center gap-2 font-semibold">
            <AlertCircle size={18} />
            Error Loading Accounts
          </div>
          <p className="mt-1 text-sm">{error}</p>
        </div>
      )}

      {/* Overview Cards */}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-100 bg-white p-5 shadow-soft dark:border-navy-800 dark:bg-navy-900">
          <div className="flex items-center justify-between text-slate-400 dark:text-slate-500">
            <span className="text-xs font-semibold uppercase tracking-wider">Total Accounts</span>
            <Globe size={18} className="text-brand-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-navy-900 dark:text-white">{accounts.length}</p>
        </div>
        
        <div className="rounded-xl border border-slate-100 bg-white p-5 shadow-soft dark:border-navy-800 dark:bg-navy-900">
          <div className="flex items-center justify-between text-slate-400 dark:text-slate-500">
            <span className="text-xs font-semibold uppercase tracking-wider">Active Sessions</span>
            <CheckCircle2 size={18} className="text-emerald-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-navy-900 dark:text-white">
            {accounts.filter(a => ['active', 'warming_up'].includes(a.status)).length}
          </p>
        </div>

        <div className="rounded-xl border border-slate-100 bg-white p-5 shadow-soft dark:border-navy-800 dark:bg-navy-900">
          <div className="flex items-center justify-between text-slate-400 dark:text-slate-500">
            <span className="text-xs font-semibold uppercase tracking-wider">Attention Required</span>
            <AlertCircle size={18} className="text-amber-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-navy-900 dark:text-white">
            {accounts.filter(a => ['expired', 'flagged', 'banned'].includes(a.status)).length}
          </p>
        </div>

        <div className="rounded-xl border border-slate-100 bg-white p-5 shadow-soft dark:border-navy-800 dark:bg-navy-900">
          <div className="flex items-center justify-between text-slate-400 dark:text-slate-500">
            <span className="text-xs font-semibold uppercase tracking-wider">Warmup Stage Range</span>
            <Activity size={18} className="text-purple-500" />
          </div>
          <p className="mt-2 text-2xl font-bold text-navy-900 dark:text-white">
            {accounts.length > 0 
              ? `Stage ${Math.min(...accounts.map(a => a.warmup_stage))} - ${Math.max(...accounts.map(a => a.warmup_stage))}`
              : 'N/A'
            }
          </p>
        </div>
      </div>

      {/* Account Table */}
      <div className="overflow-hidden rounded-xl border border-slate-100 bg-white shadow-soft dark:border-navy-800 dark:bg-navy-900">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-slate-500">
            <Loader2 className="animate-spin text-brand-500" size={32} />
            <span className="text-sm">Loading LinkedIn accounts...</span>
          </div>
        ) : accounts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <Globe className="text-slate-300 dark:text-navy-700" size={60} />
            <h3 className="mt-4 text-base font-bold text-navy-900 dark:text-white">No Accounts Connected</h3>
            <p className="mt-1 max-w-sm text-sm text-slate-500 dark:text-slate-400">
              Get started by connecting a LinkedIn account with guided browser login.
            </p>
            <button
              onClick={() => setIsModalOpen(true)}
              className="mt-6 inline-flex items-center gap-2 rounded-xl bg-brand-500 hover:bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-soft transition-colors"
            >
              <Plus size={16} />
              Connect Your First Account
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/50 text-xs font-bold uppercase tracking-wider text-slate-400 dark:border-navy-800 dark:bg-navy-950/20 dark:text-slate-500">
                  <th className="p-4">Account Label</th>
                  <th className="p-4">Region</th>
                  <th className="p-4">Status</th>
                  <th className="p-4">Health</th>
                  <th className="p-4">Daily Caps (Conn / Msg)</th>
                  <th className="p-4">Warmup Stage</th>
                  <th className="p-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-navy-800 text-sm">
                {accounts.map((acc) => (
                  <tr key={acc.id} className="hover:bg-slate-50/30 dark:hover:bg-navy-950/10">
                    <td className="p-4 font-bold text-navy-900 dark:text-white">
                      {acc.label}
                    </td>
                    <td className="p-4">
                      <span className="inline-flex items-center rounded-lg bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-navy-800 dark:text-slate-400 uppercase">
                        {acc.region}
                      </span>
                    </td>
                    <td className="p-4">
                      <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold border ${
                        ['active', 'warming_up'].includes(acc.status)
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-950'
                          : acc.status === 'cooldown'
                          ? 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-500/10 dark:text-blue-400 dark:border-blue-950'
                          : 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-500/10 dark:text-rose-400 dark:border-rose-950'
                      }`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${
                          ['active', 'warming_up'].includes(acc.status)
                            ? 'bg-emerald-500'
                            : acc.status === 'cooldown'
                            ? 'bg-blue-500'
                            : 'bg-rose-500'
                        }`} />
                        {acc.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        <span className={`text-xs font-bold ${
                          acc.health_score > 75 ? 'text-emerald-500' : acc.health_score > 40 ? 'text-amber-500' : 'text-rose-500'
                        }`}>
                          {acc.health_score}%
                        </span>
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100 dark:bg-navy-800">
                          <div 
                            className={`h-full rounded-full ${
                              acc.health_score > 75 ? 'bg-emerald-500' : acc.health_score > 40 ? 'bg-amber-500' : 'bg-rose-500'
                            }`}
                            style={{ width: `${acc.health_score}%` }}
                          />
                        </div>
                      </div>
                    </td>
                    <td className="p-4 font-medium text-slate-500 dark:text-slate-400">
                      {acc.daily_connection_cap} / {acc.daily_message_cap}
                    </td>
                    <td className="p-4 font-semibold text-purple-600 dark:text-purple-400">
                      Stage {acc.warmup_stage}
                    </td>
                    <td className="p-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {['active', 'warming_up'].includes(acc.status) ? (
                          <button
                            onClick={() => handlePause(acc.id)}
                            title="Pause outreach"
                            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-navy-800 dark:hover:text-white"
                          >
                            <Pause size={16} />
                          </button>
                        ) : acc.status === 'cooldown' ? (
                          <button
                            onClick={() => handleResume(acc.id)}
                            title="Resume outreach"
                            className="rounded-lg p-2 text-emerald-500 hover:bg-emerald-50/50 dark:hover:bg-emerald-500/10"
                          >
                            <Play size={16} />
                          </button>
                        ) : (
                          <button
                            onClick={() => {
                              setConnectLabel(acc.label);
                              setConnectRegion(acc.region);
                              setIsModalOpen(true);
                              startGuidedLogin();
                            }}
                            title="Reconnect expired cookie"
                            className="rounded-lg p-2 text-amber-500 hover:bg-amber-50/50 dark:hover:bg-amber-500/10"
                          >
                            <RefreshCw size={16} />
                          </button>
                        )}
                        <button
                          onClick={() => handleDelete(acc.id)}
                          title="Disconnect account"
                          className="rounded-lg p-2 text-rose-500 hover:bg-rose-50/50 dark:hover:bg-rose-500/10"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Guided Login Connect Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm">
          <div className="relative w-full max-w-4xl rounded-2xl border border-slate-100 bg-white p-6 shadow-2xl dark:border-navy-800 dark:bg-navy-900 max-h-[90vh] overflow-y-auto flex flex-col">
            {/* Modal Header */}
            <div className="flex items-center justify-between pb-4 border-b border-slate-100 dark:border-navy-800 mb-4">
              <div>
                <h3 className="text-lg font-bold text-navy-900 dark:text-white">
                  Connect LinkedIn Account
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Secure guided authentication.
                </p>
              </div>
              <button 
                onClick={closeConnectModal}
                className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-navy-800 dark:hover:text-white"
              >
                <X size={18} />
              </button>
            </div>

            {/* Step 1: Configuration Form */}
            {connectStep === 1 && (
              <div className="space-y-4 py-4 flex-1">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                    Account Label (Identify easily)
                  </label>
                  <input
                    type="text"
                    value={connectLabel}
                    onChange={(e) => setConnectLabel(e.target.value)}
                    placeholder="e.g. Sales Director USA"
                    className="w-full rounded-xl border border-slate-200 bg-transparent px-4 py-2.5 text-sm outline-none focus:border-brand-500 dark:border-navy-700"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                    Geographic Region
                  </label>
                  <select
                    value={connectRegion}
                    onChange={(e) => setConnectRegion(e.target.value)}
                    className="w-full rounded-xl border border-slate-200 bg-transparent px-4 py-2.5 text-sm outline-none focus:border-brand-500 dark:border-navy-700 dark:bg-navy-900"
                  >
                    <option value="usa">USA</option>
                    <option value="eu">Europe (EU)</option>
                    <option value="asia">Asia Pacific (APAC)</option>
                    <option value="mea">Middle East (MEA)</option>
                    <option value="other">Other / General</option>
                  </select>
                  <p className="mt-1.5 text-[11px] text-slate-400">
                    Choosing a region allocates a dedicated sticky proxy located in that geography.
                  </p>
                </div>

                <div className="rounded-xl border border-brand-100 bg-brand-50/50 p-4 dark:border-brand-900/20 dark:bg-brand-950/10 text-xs leading-relaxed text-brand-700 dark:text-brand-400 flex gap-2">
                  <Shield className="shrink-0 mt-0.5" size={16} />
                  <div>
                    <span className="font-bold">No credentials stored:</span> You will log in directly on LinkedIn's official website loaded in our secure, remote browser session. Your password is never sent to or saved by our platform. Only the session authentication cookies are safely stored in encrypted format.
                  </div>
                </div>

                <div className="flex justify-end gap-3 pt-4 border-t border-slate-100 dark:border-navy-800">
                  <button
                    onClick={closeConnectModal}
                    className="rounded-xl border border-slate-200 px-5 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-800"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={startGuidedLogin}
                    className="rounded-xl bg-brand-500 hover:bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-soft transition-colors"
                  >
                    Start Guided Connection
                  </button>
                </div>
              </div>
            )}

            {/* Step 2: Live Browser Canvas Stream */}
            {connectStep === 2 && (
              <div className="flex flex-col gap-4 py-2 flex-1">
                {/* Live Info Banner */}
                <div className={`rounded-xl border p-3 text-xs flex items-center justify-between ${
                  wsStatus === 'authenticated'
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/20 dark:text-emerald-400 dark:border-emerald-900/40'
                    : wsStatus === 'error' || wsStatus === 'closed'
                    ? 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/20 dark:text-rose-400 dark:border-rose-900/40'
                    : 'bg-slate-50 text-slate-600 border-slate-200 dark:bg-navy-800 dark:text-slate-300 dark:border-navy-700'
                }`}>
                  <div className="flex items-center gap-2">
                    {['connecting', 'idle'].includes(wsStatus) && (
                      <Loader2 className="animate-spin text-brand-500" size={16} />
                    )}
                    {wsStatus === 'authenticated' && <CheckCircle2 size={16} className="text-emerald-500" />}
                    <span className="font-semibold">{wsMessage}</span>
                  </div>
                  <span className="text-[10px] uppercase font-bold tracking-wider opacity-60">
                    Status: {wsStatus}
                  </span>
                </div>

                {/* Interaction Instruction */}
                {wsStatus === 'ready' && (
                  <div className="text-xs text-slate-500 dark:text-slate-400 flex items-center gap-4 bg-slate-50/50 p-2 rounded-lg border border-slate-100 dark:bg-navy-800/30 dark:border-navy-800">
                    <div className="flex items-center gap-1.5"><MousePointer size={14} /> Click to focus fields</div>
                    <div className="flex items-center gap-1.5"><Keyboard size={14} /> Type on your keyboard to enter credentials</div>
                  </div>
                )}

                {/* Canvas Container */}
                <div className="flex items-center justify-center bg-slate-950 rounded-xl overflow-hidden min-h-[400px] max-h-[500px] border border-slate-800 relative">
                  {screenImage ? (
                    <img
                      ref={imageRef}
                      src={`data:image/jpeg;base64,${screenImage}`}
                      alt="Live Browser Session"
                      onMouseDown={handleImageClick}
                      onKeyDown={handleKeyDown}
                      tabIndex={0}
                      className="max-w-full max-h-[500px] object-contain cursor-crosshair focus:outline-none focus:ring-2 focus:ring-brand-500"
                    />
                  ) : (
                    <div className="flex flex-col items-center gap-3 text-slate-500">
                      <Loader2 className="animate-spin text-brand-500" size={36} />
                      <span className="text-sm">Setting up secure sandboxed sandbox...</span>
                    </div>
                  )}
                </div>

                {/* Keyboard / Input Helper Panel */}
                {wsStatus === 'ready' && screenImage && (
                  <div className="grid gap-3 sm:grid-cols-12 border-t border-slate-100 pt-3 dark:border-navy-800">
                    <div className="sm:col-span-8 flex gap-2">
                      <input
                        type="text"
                        placeholder="Type text here and click Send..."
                        value={manualText}
                        onChange={(e) => setManualText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') sendManualText();
                        }}
                        className="flex-1 rounded-xl border border-slate-200 bg-transparent px-3 py-1.5 text-xs outline-none focus:border-brand-500 dark:border-navy-700"
                      />
                      <button
                        onClick={sendManualText}
                        className="rounded-xl bg-slate-100 hover:bg-slate-200 dark:bg-navy-800 dark:text-white px-4 text-xs font-bold transition-colors"
                      >
                        Send Text
                      </button>
                    </div>
                    <div className="sm:col-span-4 flex justify-end gap-2">
                      <button
                        onClick={() => sendSpecialKey('Tab')}
                        className="rounded-lg border border-slate-200 dark:border-navy-700 px-3 py-1 text-xs font-semibold hover:bg-slate-50 dark:hover:bg-navy-800"
                        title="Press Tab"
                      >
                        Tab
                      </button>
                      <button
                        onClick={() => sendSpecialKey('Enter')}
                        className="rounded-lg border border-slate-200 dark:border-navy-700 px-3 py-1 text-xs font-semibold hover:bg-slate-50 dark:hover:bg-navy-800"
                        title="Press Enter"
                      >
                        Enter
                      </button>
                      <button
                        onClick={() => sendSpecialKey('Backspace')}
                        className="rounded-lg border border-slate-200 dark:border-navy-700 px-3 py-1 text-xs font-semibold hover:bg-slate-50 dark:hover:bg-navy-800 text-rose-500"
                        title="Press Backspace"
                      >
                        Backspace
                      </button>
                    </div>
                  </div>
                )}

                {/* Close Button / Cancel */}
                <div className="flex justify-between items-center pt-2 mt-auto">
                  <div className="text-[11px] text-slate-400">
                    Session terminates automatically on login or close.
                  </div>
                  <button
                    onClick={closeConnectModal}
                    className="rounded-xl border border-slate-200 px-5 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:border-navy-700 dark:text-slate-400 dark:hover:bg-navy-800"
                  >
                    Close & Terminate Session
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
