import { useEffect, useState } from 'react';
import { MessageSquare, RefreshCw, Send, User, ChevronRight, Inbox, HelpCircle, Check, AlertCircle, Smile } from 'lucide-react';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';

export default function LinkedInInbox() {
  const { createAlert } = useNotifications();
  const notify = (title, message) => createAlert(title, message).catch(() => {});

  const [inboxItems, setInboxItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedConversation, setSelectedConversation] = useState(null);
  
  // Reply composition
  const [replyText, setReplyText] = useState('');
  const [sendingReply, setSendingReply] = useState(false);

  // Fetch inbox items
  const fetchInbox = async () => {
    try {
      setLoading(true);
      const res = await api.getLinkedInInbox();
      setInboxItems(res.inbox || []);
      
      // Auto-select first conversation if not already selected
      if (res.inbox && res.inbox.length > 0 && !selectedConversation) {
        setSelectedConversation(res.inbox[0]);
      }
    } catch (err) {
      notify('Error', `Failed to load LinkedIn inbox: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInbox();
  }, []);

  // Send Reply
  const handleSendReply = async (e) => {
    e.preventDefault();
    if (!replyText.trim() || !selectedConversation) return;

    setSendingReply(true);
    try {
      await api.sendLinkedInReply(selectedConversation.target_id, replyText);
      notify('Success', 'Manual reply queued for sending.');
      setReplyText('');
      fetchInbox();
    } catch (err) {
      notify('Error', `Failed to send reply: ${err.message}`);
    } finally {
      setSendingReply(false);
    }
  };

  // Maps intent string to status style classes
  const getIntentBadge = (intent) => {
    const styles = {
      interested: 'bg-emerald-100 text-emerald-700',
      meeting_request: 'bg-indigo-100 text-indigo-700',
      objection: 'bg-amber-100 text-amber-700',
      not_interested: 'bg-rose-100 text-rose-700',
      out_of_office: 'bg-slate-100 text-slate-600',
      unclear: 'bg-slate-100 text-slate-500'
    };
    return (
      <span className={`rounded-md px-2 py-0.5 text-[10px] font-bold ${styles[intent] || 'bg-slate-100 text-slate-500'}`}>
        {intent ? intent.replace('_', ' ').toUpperCase() : 'UNCLEAR'}
      </span>
    );
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <PageHeader 
        title="LinkedIn Unified Inbox" 
        subtitle="View incoming messages across all campaigns and accounts. Review LLM classifications and compose manual replies."
        action={
          <button
            onClick={fetchInbox}
            className="flex items-center gap-1 rounded-xl border border-slate-200 bg-white p-2 text-sm text-slate-600 hover:bg-slate-50 dark:border-navy-800 dark:bg-navy-950 dark:text-slate-400"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
          </button>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left Column: Conversations List */}
        <div className="lg:col-span-1 space-y-4">
          <Card className="h-[600px] flex flex-col">
            <h2 className="mb-4 text-base font-bold text-navy-900 dark:text-white flex items-center gap-2">
              <Inbox size={18} className="text-brand-500" /> Conversations
            </h2>
            
            {loading ? (
              <div className="flex flex-1 items-center justify-center">
                <RefreshCw size={24} className="animate-spin text-slate-400" />
              </div>
            ) : inboxItems.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center text-slate-400 dark:text-slate-600 py-12">
                <MessageSquare size={32} className="mb-2" />
                <p className="text-xs">Your inbox is currently empty.</p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                {inboxItems.map((item) => (
                  <div
                    key={item.id}
                    onClick={() => setSelectedConversation(item)}
                    className={`p-3 rounded-xl cursor-pointer border transition-all text-xs ${
                      selectedConversation?.id === item.id
                        ? 'bg-brand-50/50 border-brand-200 dark:bg-navy-800/40 dark:border-navy-700'
                        : 'border-transparent hover:bg-slate-50 dark:hover:bg-navy-800/10'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold text-navy-900 dark:text-white truncate">
                        {item.target?.person?.full_name || 'Prospect'}
                      </span>
                      {getIntentBadge(item.classification?.intent)}
                    </div>
                    <div className="mt-1 text-[11px] text-slate-500 truncate">
                      {item.target?.person?.title || 'Unknown'} at {item.target?.person?.organization_name || 'Unknown'}
                    </div>
                    <p className="mt-2 text-slate-600 dark:text-slate-400 line-clamp-2">
                      {item.content}
                    </p>
                    <div className="mt-2 flex items-center justify-between text-[10px] text-slate-400">
                      <span>{new Date(item.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        {/* Right Column: Chat details & Reply editor */}
        <div className="lg:col-span-2 space-y-6">
          {selectedConversation ? (
            <Card className="h-[600px] flex flex-col">
              {/* Header */}
              <div className="border-b border-slate-100 pb-4 dark:border-navy-800 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-base text-navy-900 dark:text-white">
                      {selectedConversation.target?.person?.full_name}
                    </h3>
                    {selectedConversation.target?.person?.linkedin_url && (
                      <a
                        href={selectedConversation.target.person.linkedin_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-brand-500 hover:underline"
                      >
                        LinkedIn Profile
                      </a>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {selectedConversation.target?.person?.title} at {selectedConversation.target?.person?.organization_name}
                  </p>
                </div>
                
                {selectedConversation.classification && (
                  <div className="text-right">
                    <div className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">LLM Classification</div>
                    <div className="mt-1 flex items-center gap-2 justify-end">
                      {getIntentBadge(selectedConversation.classification.intent)}
                      <span className="text-xs font-bold text-slate-600 dark:text-slate-400">
                        {Math.round(selectedConversation.classification.confidence * 100)}% Match
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Classification alert */}
              {selectedConversation.classification?.suggested_next_action && (
                <div className="mt-3 rounded-lg bg-brand-50/40 p-3 text-xs border border-brand-100 dark:bg-navy-800/10 dark:border-navy-800 flex items-start gap-2">
                  <Smile size={16} className="text-brand-500 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold text-brand-600">Suggested Action: </span>
                    <span className="text-slate-600 dark:text-slate-300">
                      {selectedConversation.classification.suggested_next_action}
                    </span>
                  </div>
                </div>
              )}

              {/* Chat messages stream */}
              <div className="flex-1 overflow-y-auto py-4 space-y-4">
                {/* Outgoing initial (simulated context) */}
                <div className="flex justify-end">
                  <div className="max-w-[75%] rounded-2xl rounded-tr-none bg-brand-500 p-3 text-xs text-white shadow-sm">
                    <p className="leading-relaxed">
                      Hello! I noticed you work as {selectedConversation.target?.person?.title || 'Professional'} and wanted to connect.
                    </p>
                  </div>
                </div>

                {/* Incoming reply */}
                <div className="flex justify-start">
                  <div className="max-w-[75%] rounded-2xl rounded-tl-none bg-slate-50 border border-slate-100 p-3 text-xs text-slate-800 dark:bg-navy-950 dark:border-navy-800 dark:text-slate-300 shadow-sm">
                    <p className="whitespace-pre-line leading-relaxed">
                      {selectedConversation.content}
                    </p>
                    <div className="mt-1 text-right text-[10px] text-slate-400">
                      {new Date(selectedConversation.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </div>
                </div>
              </div>

              {/* Reply box */}
              <form onSubmit={handleSendReply} className="border-t border-slate-100 pt-4 dark:border-navy-800">
                <div className="flex gap-2">
                  <textarea
                    placeholder="Type your manual reply here (queued & scheduled to send safely)..."
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    rows={2}
                    required
                    className="flex-1 rounded-xl border border-slate-200 p-3 text-xs focus:border-brand-500 focus:outline-none dark:border-navy-800 dark:bg-navy-950 dark:text-white"
                  />
                  <button
                    type="submit"
                    disabled={sendingReply || !replyText.trim()}
                    className="flex items-center justify-center rounded-xl bg-brand-500 px-4 text-white hover:bg-brand-600 disabled:bg-slate-200 disabled:text-slate-400 shrink-0"
                  >
                    {sendingReply ? (
                      <RefreshCw size={16} className="animate-spin" />
                    ) : (
                      <Send size={16} />
                    )}
                  </button>
                </div>
              </form>
            </Card>
          ) : (
            <div className="flex h-[600px] flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 dark:border-navy-800 p-8 text-center bg-white dark:bg-navy-900">
              <MessageSquare size={48} className="text-slate-300 dark:text-slate-700 mb-3" />
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">Select a Conversation</h3>
              <p className="mt-1 text-xs text-slate-500 max-w-sm">
                Choose an incoming LinkedIn reply from the left panel to review intent categorization, read message history, and compose your manual responses.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
