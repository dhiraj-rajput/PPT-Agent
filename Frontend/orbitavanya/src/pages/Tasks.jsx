import { useEffect, useState } from 'react';
import { Plus, X, Loader2 } from 'lucide-react';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { api } from '../lib/api.js';

export default function Tasks() {
  const [tasks, setTasks] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: '', due: '', priority: 'Medium', assigneeId: '' });
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');
  const [createNotice, setCreateNotice] = useState('');

  async function loadAll() {
    setLoading(true);
    setLoadError('');
    try {
      const [{ tasks }, { users }] = await Promise.all([api.listTasks(), api.listUsers()]);
      setTasks(tasks);
      setUsers(users);
      setForm((f) => ({ ...f, assigneeId: f.assigneeId || users[0]?.id || '' }));
    } catch (err) {
      setLoadError(err.message || 'Could not load tasks.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  const toggle = async (id) => {
    const prev = tasks;
    setTasks((p) => p.map((t) => (t.id === id ? { ...t, done: !t.done } : t)));
    try {
      await api.toggleTask(id);
    } catch (err) {
      setTasks(prev);
      setLoadError(err.message || 'Could not update task.');
    }
  };

  const reassign = async (id, assigneeId) => {
    const prev = tasks;
    const assignee = users.find((u) => u.id === assigneeId);
    setTasks((p) => p.map((t) => (t.id === id ? { ...t, assigneeId, assignee } : t)));
    try {
      // The backend performs the real DB relation update and emails the new assignee.
      await api.reassignTask(id, assigneeId);
    } catch (err) {
      setTasks(prev);
      setLoadError(err.message || 'Could not reassign task.');
    }
  };

  async function submitCreate(e) {
    e.preventDefault();
    setCreateError('');
    setCreateNotice('');
    if (!form.title) {
      setCreateError('Title is required.');
      return;
    }
    setCreating(true);
    try {
      const { task } = await api.createTask(form.title, form.due, form.priority, form.assigneeId || null);
      setTasks((prev) => [task, ...prev]);
      setCreateNotice(task.assignee ? `Task created and ${task.assignee.name} was emailed.` : 'Task created.');
      setForm({ title: '', due: '', priority: 'Medium', assigneeId: users[0]?.id || '' });
      setTimeout(() => {
        setOpen(false);
        setCreateNotice('');
      }, 1400);
    } catch (err) {
      setCreateError(err.message || 'Could not create task.');
    } finally {
      setCreating(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Tasks"
        subtitle={loading ? 'Loading…' : `${tasks.filter((t) => !t.done).length} open tasks`}
        action={
          <button
            onClick={() => setOpen(true)}
            className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft"
          >
            <Plus size={16} /> New Task
          </button>
        }
      />

      {loadError && (
        <div className="mb-4 rounded-lg bg-tomato-50 px-3.5 py-2.5 text-sm text-tomato-700">{loadError}</div>
      )}

      <Card className="!p-0">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-400">
            <Loader2 size={16} className="animate-spin" /> Loading tasks…
          </div>
        ) : tasks.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-400">No tasks yet. Create the first one.</div>
        ) : (
          tasks.map((t) => (
            <div key={t.id} className="flex items-center gap-4 border-b border-slate-50 px-5 py-4 last:border-0">
              <input
                type="checkbox"
                checked={t.done}
                onChange={() => toggle(t.id)}
                className="h-4 w-4 rounded border-slate-300 text-brand-600"
              />
              <div className="flex-1">
                <p className={`text-sm font-semibold ${t.done ? 'text-slate-400 line-through' : 'text-navy-900'}`}>{t.title}</p>
                <p className="text-xs text-slate-400">Due {t.due || 'Not set'}</p>
              </div>
              <div className="flex items-center gap-2">
                {t.assignee && (
                  <img
                    src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(t.assignee.seed || t.assignee.email)}`}
                    className="h-6 w-6 rounded-full"
                    alt={t.assignee.name}
                    title={t.assignee.name}
                  />
                )}
                <select
                  value={t.assigneeId ?? ''}
                  onChange={(e) => reassign(t.id, e.target.value)}
                  className="rounded-lg border border-slate-200 px-2 py-1.5 text-xs font-medium text-navy-900 outline-none focus:border-brand-500"
                >
                  <option value="">Unassigned</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>{u.name}</option>
                  ))}
                </select>
              </div>
              <StatusBadge status={t.priority} />
            </div>
          ))
        )}
      </Card>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/50 p-4"
          onClick={() => setOpen(false)}
        >
          <form
            onSubmit={submitCreate}
            className="w-full max-w-md rounded-2xl bg-white p-6 shadow-soft"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-navy-900">New Task</h3>
              <button type="button" onClick={() => setOpen(false)} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100">
                <X size={16} />
              </button>
            </div>

            <p className="mt-1 text-xs text-slate-400">
              Assigning to a teammate updates the database and emails them right away.
            </p>

            <div className="mt-4 flex flex-col gap-3">
              <div>
                <label className="text-xs font-semibold text-slate-500">Title</label>
                <input
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none focus:border-brand-500"
                  placeholder="Draft technical approach section"
                  required
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-500">Due</label>
                  <input
                    value={form.due}
                    onChange={(e) => setForm((f) => ({ ...f, due: e.target.value }))}
                    className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none focus:border-brand-500"
                    placeholder="Tomorrow"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-500">Priority</label>
                  <select
                    value={form.priority}
                    onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}
                    className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none focus:border-brand-500"
                  >
                    <option>High</option>
                    <option>Medium</option>
                    <option>Low</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500">Assign to</label>
                <select
                  value={form.assigneeId}
                  onChange={(e) => setForm((f) => ({ ...f, assigneeId: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm outline-none focus:border-brand-500"
                >
                  <option value="">Unassigned</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>{u.name}</option>
                  ))}
                </select>
              </div>
            </div>

            {createError && (
              <div className="mt-3 rounded-lg bg-tomato-50 px-3.5 py-2.5 text-sm text-tomato-700">{createError}</div>
            )}
            {createNotice && (
              <div className="mt-3 rounded-lg bg-emerald-50 px-3.5 py-2.5 text-sm text-emerald-700">{createNotice}</div>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-lg border border-slate-200 px-3.5 py-2 text-xs font-semibold text-navy-900 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={creating}
                className="flex items-center gap-1.5 rounded-lg bg-brand-500 px-3.5 py-2 text-xs font-bold text-white disabled:opacity-60"
              >
                {creating && <Loader2 size={13} className="animate-spin" />}
                Create Task
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
