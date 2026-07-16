import { useEffect, useMemo, useState } from 'react';
import { Plus, Calendar, Clock, Video, MapPin, X, Mail, Loader2, ExternalLink, Ban, Search, Check } from 'lucide-react';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { api } from '../lib/api.js';

const PROVIDERS = [
  { value: 'jitsi', label: 'Jitsi (instant, no account needed)' },
  { value: 'zoom', label: 'Zoom' },
  { value: 'google_meet', label: 'Google Meet' },
];

const EMPTY_FORM = {
  title: '',
  with: '',
  date: '',
  time: '',
  type: 'Video Call',
  provider: 'jitsi',
  location: '',
};

function isValidEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export default function Meetings() {
  const [meetings, setMeetings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const [users, setUsers] = useState([]);

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [selectedUserIds, setSelectedUserIds] = useState([]);
  const [userSearch, setUserSearch] = useState('');
  const [externalEmail, setExternalEmail] = useState('');
  const [externalAttendees, setExternalAttendees] = useState([]); // [{email}]

  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');
  const [createNotice, setCreateNotice] = useState('');

  const [cancellingId, setCancellingId] = useState(null);

  async function loadMeetings() {
    setLoading(true);
    setLoadError('');
    try {
      const { meetings } = await api.listMeetings();
      setMeetings(meetings);
    } catch (err) {
      setLoadError(err.message || 'Could not load meetings.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMeetings();
    api
      .listUsers()
      .then(({ users }) => setUsers(users))
      .catch(() => {}); // registered-user picker is a nice-to-have; failing silently is fine here
  }, []);

  const filteredUsers = useMemo(() => {
    const q = userSearch.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) => u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q));
  }, [users, userSearch]);

  function toggleUser(id) {
    setSelectedUserIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function addExternalEmail() {
    const email = externalEmail.trim().toLowerCase();
    if (!email) return;
    if (!isValidEmail(email)) {
      setCreateError('Enter a valid email address to add an attendee.');
      return;
    }
    if (externalAttendees.some((a) => a.email === email) || users.some((u) => selectedUserIds.includes(u.id) && u.email === email)) {
      setExternalEmail('');
      return;
    }
    setCreateError('');
    setExternalAttendees((prev) => [...prev, { email }]);
    setExternalEmail('');
  }

  function removeExternalEmail(email) {
    setExternalAttendees((prev) => prev.filter((a) => a.email !== email));
  }

  function resetForm() {
    setForm(EMPTY_FORM);
    setSelectedUserIds([]);
    setUserSearch('');
    setExternalEmail('');
    setExternalAttendees([]);
  }

  async function submit(e) {
    e.preventDefault();
    setCreateError('');
    setCreateNotice('');
    if (!form.title || !form.date || !form.time) {
      setCreateError('Title, date, and time are required.');
      return;
    }

    const attendees = [
      ...selectedUserIds.map((userId) => ({ userId })),
      ...externalAttendees.map((a) => ({ email: a.email })),
    ];

    setCreating(true);
    try {
      const { meeting, providerWarning } = await api.createMeeting({ ...form, attendees });
      setMeetings((prev) => [...prev, meeting]);
      const inviteCount = meeting.attendees.length;
      setCreateNotice(
        [
          inviteCount ? `Meeting scheduled — invite emailed to ${inviteCount} attendee${inviteCount > 1 ? 's' : ''}.` : 'Meeting scheduled.',
          providerWarning || '',
        ]
          .filter(Boolean)
          .join(' ')
      );
      resetForm();
      setTimeout(() => {
        setOpen(false);
        setCreateNotice('');
      }, 2000);
    } catch (err) {
      setCreateError(err.message || 'Could not schedule meeting.');
    } finally {
      setCreating(false);
    }
  }

  async function cancelMeeting(id) {
    setCancellingId(id);
    try {
      const { meeting } = await api.cancelMeeting(id);
      setMeetings((prev) => prev.map((m) => (m.id === meeting.id ? meeting : m)));
    } catch (err) {
      setLoadError(err.message || 'Could not cancel meeting.');
    } finally {
      setCancellingId(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Meetings"
        subtitle="Upcoming calls and in-person meetings"
        action={
          <button onClick={() => setOpen(true)} className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft">
            <Plus size={16} /> Schedule Meeting
          </button>
        }
      />

      {loadError && (
        <div className="mb-4 rounded-lg bg-tomato-50 px-3.5 py-2.5 text-sm text-tomato-700">{loadError}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-400 dark:text-slate-500">
          <Loader2 size={16} className="animate-spin" /> Loading meetings…
        </div>
      ) : meetings.length === 0 ? (
        <div className="py-12 text-center text-sm text-slate-400 dark:text-slate-500">No meetings scheduled yet.</div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {meetings.map((m) => {
            const cancelled = m.status === 'cancelled';
            return (
              <Card key={m.id} className={cancelled ? 'opacity-60' : ''}>
                <div className="flex items-start gap-4">
                  <div className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                    <Calendar size={18} />
                  </div>
                  <div className="flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-bold text-navy-900 dark:text-white">{m.title}</p>
                      {cancelled && <StatusBadge status="Cancelled" />}
                    </div>
                    {m.with && <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">with {m.with}</p>}
                    <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
                      <span className="flex items-center gap-1"><Calendar size={12} /> {m.date}</span>
                      <span className="flex items-center gap-1"><Clock size={12} /> {m.time}</span>
                      <span className="flex items-center gap-1">
                        {m.type === 'Video Call' ? <Video size={12} /> : <MapPin size={12} />} {m.type}
                        {m.type === 'Video Call' && m.provider && ` · ${m.provider === 'google_meet' ? 'Google Meet' : m.provider}`}
                      </span>
                    </div>
                    {m.attendees?.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {m.attendees.map((a) => (
                          <span
                            key={a.email}
                            className="flex items-center gap-1 rounded-full bg-slate-100 dark:bg-navy-800 px-2 py-0.5 text-xs font-medium text-slate-500 dark:text-slate-400"
                            title={a.email}
                          >
                            <Mail size={11} /> {a.name || a.email} {a.inviteSent ? '· sent' : ''}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    {!cancelled && m.type === 'Video Call' && m.meetingLink ? (
                      <a
                        href={m.meetingLink}
                        target="_blank"
                        rel="noreferrer"
                        className="flex items-center gap-1 rounded-lg border border-slate-200 dark:border-navy-700 px-3 py-1.5 text-xs font-semibold text-navy-900 dark:text-white hover:bg-slate-50 dark:hover:bg-navy-800"
                      >
                        Join <ExternalLink size={12} />
                      </a>
                    ) : !cancelled ? (
                      <button className="rounded-lg border border-slate-200 dark:border-navy-700 px-3 py-1.5 text-xs font-semibold text-navy-900 dark:text-white">
                        Details
                      </button>
                    ) : null}
                    {!cancelled && (
                      <button
                        onClick={() => cancelMeeting(m.id)}
                        disabled={cancellingId === m.id}
                        className="flex items-center gap-1 rounded-lg border border-tomato-200 px-3 py-1.5 text-xs font-semibold text-tomato-600 hover:bg-tomato-50 disabled:opacity-60"
                      >
                        {cancellingId === m.id ? <Loader2 size={12} className="animate-spin" /> : <Ban size={12} />}
                        Cancel
                      </button>
                    )}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/50 p-4" onClick={() => setOpen(false)}>
          <form
            onSubmit={submit}
            className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl bg-white dark:bg-navy-900 p-6 shadow-soft"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">Schedule Meeting</h3>
              <button type="button" onClick={() => setOpen(false)} className="rounded-lg p-1.5 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-navy-700">
                <X size={16} />
              </button>
            </div>

            <div className="mt-4 flex flex-col gap-3">
              <div>
                <label className="text-xs font-semibold text-slate-500 dark:text-slate-400">Meeting Title</label>
                <input
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
                  placeholder="Kickoff Call - ABC Corporation"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 dark:text-slate-400">With (optional label)</label>
                <input
                  value={form.with}
                  onChange={(e) => setForm((f) => ({ ...f, with: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
                  placeholder="Contact name or account"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-500 dark:text-slate-400">Date</label>
                  <input
                    type="date"
                    value={form.date}
                    onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))}
                    className="mt-1 w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-500 dark:text-slate-400">Time</label>
                  <input
                    type="time"
                    value={form.time}
                    onChange={(e) => setForm((f) => ({ ...f, time: e.target.value }))}
                    className="mt-1 w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-500 dark:text-slate-400">Meeting Type</label>
                <select
                  value={form.type}
                  onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
                >
                  <option>Video Call</option>
                  <option>In Person</option>
                </select>
              </div>

              {form.type === 'In Person' && (
                <div>
                  <label className="text-xs font-semibold text-slate-500 dark:text-slate-400">Location</label>
                  <input
                    value={form.location}
                    onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))}
                    className="mt-1 w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
                    placeholder="123 Main St, Suite 400"
                  />
                </div>
              )}

              {form.type === 'Video Call' && (
                <div>
                  <label className="text-xs font-semibold text-slate-500 dark:text-slate-400">Video Provider</label>
                  <select
                    value={form.provider}
                    onChange={(e) => setForm((f) => ({ ...f, provider: e.target.value }))}
                    className="mt-1 w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
                  >
                    {PROVIDERS.map((p) => (
                      <option key={p.value} value={p.value}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                  <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                    {form.provider === 'jitsi' && 'A Jitsi video room is created automatically — no calendar account needed.'}
                    {form.provider === 'zoom' && "A Zoom meeting is created on your organization's Zoom account."}
                    {form.provider === 'google_meet' && 'Requires Google to be connected once in Settings > Integrations. Falls back to Jitsi if not.'}
                  </p>
                </div>
              )}

              {/* ---- Attendees: registered users (multi-select) + external emails ---- */}
              <div>
                <label className="text-xs font-semibold text-slate-500 dark:text-slate-400">Invite registered users</label>
                <div className="mt-1 flex items-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3 py-2">
                  <Search size={14} className="text-slate-400 dark:text-slate-500" />
                  <input
                    value={userSearch}
                    onChange={(e) => setUserSearch(e.target.value)}
                    placeholder="Search by name or email…"
                    className="w-full border-0 bg-transparent text-sm outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500"
                  />
                </div>
                <div className="mt-1.5 max-h-32 overflow-y-auto rounded-xl border border-slate-100 dark:border-navy-800">
                  {filteredUsers.length === 0 ? (
                    <p className="px-3 py-2 text-xs text-slate-400 dark:text-slate-500">No matching users.</p>
                  ) : (
                    filteredUsers.map((u) => {
                      const selected = selectedUserIds.includes(u.id);
                      return (
                        <button
                          type="button"
                          key={u.id}
                          onClick={() => toggleUser(u.id)}
                          className={`flex w-full items-center justify-between px-3 py-2 text-left text-xs hover:bg-slate-50 ${
                            selected ? 'bg-brand-50' : ''
                          }`}
                        >
                          <span>
                            <span className="font-semibold text-navy-900 dark:text-white">{u.name}</span>{' '}
                            <span className="text-slate-400 dark:text-slate-500">{u.email}</span>
                          </span>
                          {selected && <Check size={14} className="text-brand-600" />}
                        </button>
                      );
                    })
                  )}
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-500 dark:text-slate-400">Invite by email (external attendees)</label>
                <div className="mt-1 flex gap-2">
                  <input
                    type="email"
                    value={externalEmail}
                    onChange={(e) => setExternalEmail(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addExternalEmail();
                      }
                    }}
                    className="w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
                    placeholder="contact@company.com"
                  />
                  <button
                    type="button"
                    onClick={addExternalEmail}
                    className="shrink-0 rounded-xl border border-slate-200 dark:border-navy-700 px-3.5 py-2.5 text-xs font-semibold text-navy-900 dark:text-white hover:bg-slate-50 dark:hover:bg-navy-800"
                  >
                    Add
                  </button>
                </div>
              </div>

              {(selectedUserIds.length > 0 || externalAttendees.length > 0) && (
                <div className="flex flex-wrap gap-1.5">
                  {selectedUserIds.map((id) => {
                    const u = users.find((x) => x.id === id);
                    if (!u) return null;
                    return (
                      <span key={id} className="flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700">
                        {u.name}
                        <button type="button" onClick={() => toggleUser(id)}>
                          <X size={12} />
                        </button>
                      </span>
                    );
                  })}
                  {externalAttendees.map((a) => (
                    <span key={a.email} className="flex items-center gap-1 rounded-full bg-slate-100 dark:bg-navy-800 px-2.5 py-1 text-xs font-medium text-slate-600 dark:text-slate-300">
                      {a.email}
                      <button type="button" onClick={() => removeExternalEmail(a.email)}>
                        <X size={12} />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {createError && (
              <div className="mt-3 rounded-lg bg-tomato-50 px-3.5 py-2.5 text-sm text-tomato-700">{createError}</div>
            )}
            {createNotice && (
              <div className="mt-3 rounded-lg bg-emerald-50 px-3.5 py-2.5 text-sm text-emerald-700">{createNotice}</div>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setOpen(false)} className="rounded-lg border border-slate-200 dark:border-navy-700 px-3.5 py-2 text-xs font-semibold text-navy-900 dark:text-white hover:bg-slate-50 dark:hover:bg-navy-800">
                Cancel
              </button>
              <button
                type="submit"
                disabled={creating}
                className="flex items-center gap-1.5 rounded-lg bg-brand-500 px-3.5 py-2 text-xs font-bold text-white disabled:opacity-60"
              >
                {creating && <Loader2 size={13} className="animate-spin" />}
                Schedule Meeting
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
