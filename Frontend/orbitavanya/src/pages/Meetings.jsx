import { useState } from 'react';
import { Plus, Calendar, Clock, Video, MapPin, X, Mail } from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { meetings as initialMeetings } from '../data/misc.js';

const providers = [
  { id: 'google', label: 'Google Calendar / Gmail' },
  { id: 'outlook', label: 'Outlook' },
  { id: 'apple', label: 'Apple Calendar' },
  { id: 'other', label: 'Other / Manual Invite' },
];

const providerLabel = (id) => providers.find((p) => p.id === id)?.label;

export default function Meetings() {
  const [meetings, setMeetings] = useState(initialMeetings);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: '', with: '', date: '', time: '', type: 'Video Call', provider: 'google' });

  const submit = (e) => {
    e.preventDefault();
    if (!form.title || !form.with || !form.date || !form.time) return;
    setMeetings((prev) => [...prev, { id: prev.length + 1, ...form }]);
    setForm({ title: '', with: '', date: '', time: '', type: 'Video Call', provider: 'google' });
    setOpen(false);
  };

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

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {meetings.map((m) => (
          <Card key={m.id}>
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                <Calendar size={18} />
              </div>
              <div className="flex-1">
                <p className="text-sm font-bold text-navy-900">{m.title}</p>
                <p className="mt-0.5 text-xs text-slate-400">with {m.with}</p>
                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                  <span className="flex items-center gap-1"><Calendar size={12} /> {m.date}</span>
                  <span className="flex items-center gap-1"><Clock size={12} /> {m.time}</span>
                  <span className="flex items-center gap-1">
                    {m.type === 'Video Call' ? <Video size={12} /> : <MapPin size={12} />} {m.type}
                  </span>
                  {m.provider && (
                    <span className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-500">
                      <Mail size={11} /> {providerLabel(m.provider)}
                    </span>
                  )}
                </div>
              </div>
              <button className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-navy-900">Join</button>
            </div>
          </Card>
        ))}
      </div>

      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/50 p-4" onClick={() => setOpen(false)}>
          <form onSubmit={submit} className="w-full max-w-md rounded-2xl bg-white p-6 shadow-soft" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-navy-900">Schedule Meeting</h3>
              <button type="button" onClick={() => setOpen(false)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100">
                <X size={16} />
              </button>
            </div>

            <div className="mt-4 flex flex-col gap-3">
              <div>
                <label className="text-xs font-semibold text-slate-500">Meeting Title</label>
                <input
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none focus:border-brand-500"
                  placeholder="Kickoff Call - ABC Corporation"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500">With</label>
                <input
                  value={form.with}
                  onChange={(e) => setForm((f) => ({ ...f, with: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none focus:border-brand-500"
                  placeholder="Contact name"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-500">Date</label>
                  <input
                    type="date"
                    value={form.date}
                    onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))}
                    className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none focus:border-brand-500"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-500">Time</label>
                  <input
                    type="time"
                    value={form.time}
                    onChange={(e) => setForm((f) => ({ ...f, time: e.target.value }))}
                    className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none focus:border-brand-500"
                  />
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500">Meeting Type</label>
                <select
                  value={form.type}
                  onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none focus:border-brand-500"
                >
                  <option>Video Call</option>
                  <option>In Person</option>
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500">Calendar / Invite via</label>
                <div className="mt-1 grid grid-cols-2 gap-2">
                  {providers.map((p) => (
                    <button
                      type="button"
                      key={p.id}
                      onClick={() => setForm((f) => ({ ...f, provider: p.id }))}
                      className={`rounded-xl border px-3 py-2 text-left text-xs font-semibold ${
                        form.provider === p.id
                          ? 'border-brand-500 bg-brand-50 text-brand-700'
                          : 'border-slate-200 text-slate-500 hover:bg-slate-50'
                      }`}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={() => setOpen(false)} className="rounded-lg border border-slate-200 px-3.5 py-2 text-xs font-semibold text-navy-900 hover:bg-slate-50">
                Cancel
              </button>
              <button type="submit" className="rounded-lg bg-brand-500 px-3.5 py-2 text-xs font-bold text-white">
                Schedule Meeting
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
