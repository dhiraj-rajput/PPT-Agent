import { useState } from 'react';
import { Plus } from 'lucide-react';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { tasks as initialTasks, teamUsers } from '../data/misc.js';

const userById = (id) => teamUsers.find((u) => u.id === id);

export default function Tasks() {
  const [tasks, setTasks] = useState(initialTasks);

  const toggle = (id) => {
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, done: !t.done } : t)));
  };

  const reassign = (id, assigneeId) => {
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, assigneeId: Number(assigneeId) } : t)));
  };

  return (
    <div>
      <PageHeader
        title="Tasks"
        subtitle={`${tasks.filter((t) => !t.done).length} open tasks`}
        action={
          <button className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft">
            <Plus size={16} /> New Task
          </button>
        }
      />

      <Card className="!p-0">
        {tasks.map((t) => {
          const assignee = userById(t.assigneeId);
          return (
            <div key={t.id} className="flex items-center gap-4 border-b border-slate-50 px-5 py-4 last:border-0">
              <input
                type="checkbox"
                checked={t.done}
                onChange={() => toggle(t.id)}
                className="h-4 w-4 rounded border-slate-300 text-brand-600"
              />
              <div className="flex-1">
                <p className={`text-sm font-semibold ${t.done ? 'text-slate-400 line-through' : 'text-navy-900'}`}>{t.title}</p>
                <p className="text-xs text-slate-400">Due {t.due}</p>
              </div>
              <div className="flex items-center gap-2">
                {assignee && (
                  <img
                    src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${assignee.seed}`}
                    className="h-6 w-6 rounded-full"
                    alt={assignee.name}
                    title={assignee.name}
                  />
                )}
                <select
                  value={t.assigneeId ?? ''}
                  onChange={(e) => reassign(t.id, e.target.value)}
                  className="rounded-lg border border-slate-200 px-2 py-1.5 text-xs font-medium text-navy-900 outline-none focus:border-brand-500"
                >
                  {teamUsers.map((u) => (
                    <option key={u.id} value={u.id}>{u.name}</option>
                  ))}
                </select>
              </div>
              <StatusBadge status={t.priority} />
            </div>
          );
        })}
      </Card>
    </div>
  );
}
