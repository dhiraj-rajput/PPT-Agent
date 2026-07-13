import { Plus, MoreHorizontal } from 'lucide-react';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { teamUsers as users } from '../data/misc.js';

export default function UsersRoles() {
  return (
    <div>
      <PageHeader
        title="Users & Roles"
        subtitle="Manage team members and permission levels"
        action={
          <button className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft">
            <Plus size={16} /> Invite User
          </button>
        }
      />

      <Card className="!p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-400">
              <th className="px-5 py-3 font-semibold">User</th>
              <th className="px-5 py-3 font-semibold">Role</th>
              <th className="px-5 py-3 font-semibold">Status</th>
              <th className="px-5 py-3 font-semibold text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.email} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60">
                <td className="px-5 py-3.5">
                  <div className="flex items-center gap-3">
                    <img src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${u.seed}`} className="h-9 w-9 rounded-full" alt={u.name} />
                    <div>
                      <p className="font-semibold text-navy-900">{u.name}</p>
                      <p className="text-xs text-slate-400">{u.email}</p>
                    </div>
                  </div>
                </td>
                <td className="px-5 py-3.5 text-slate-500">{u.role}</td>
                <td className="px-5 py-3.5"><StatusBadge status={u.status} /></td>
                <td className="px-5 py-3.5 text-right">
                  <button className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100"><MoreHorizontal size={15} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
