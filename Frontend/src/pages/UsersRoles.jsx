import { useEffect, useState } from 'react';
import { Plus, MoreHorizontal, X, Loader2, Trash2, RefreshCw } from 'lucide-react';
import { PageHeader, Card, StatusBadge } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';

const ROLES = ['Admin', 'Team Member', 'Proposal Writer', 'Contract Specialist', 'Business Development', 'Viewer'];

export default function UsersRoles() {
  const { createAlert } = useNotifications();
  const notify = (title, message, link) => createAlert(title, message, link).catch(() => {});
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', role: 'Team Member' });
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState('');
  const [inviteSuccess, setInviteSuccess] = useState('');
  const [menuOpenId, setMenuOpenId] = useState(null);

  async function loadUsers() {
    setLoading(true);
    setLoadError('');
    try {
      const { users } = await api.listUsers();
      setUsers(users);
    } catch (err) {
      setLoadError(typeof err?.message === 'string' ? err.message : String(err || 'Could not load users.'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUsers();
  }, []);

  async function submitInvite(e) {
    e.preventDefault();
    setInviteError('');
    setInviteSuccess('');
    if (!form.email) {
      setInviteError('Email is required.');
      return;
    }
    setInviting(true);
    try {
      const { user, warning } = await api.inviteUser(form.name, form.email, form.role);
      setUsers((prev) => [user, ...prev]);
      setInviteSuccess(warning || `Invite sent to ${user.email}.`);
      setForm({ name: '', email: '', role: 'Team Member' });
      setTimeout(() => {
        setOpen(false);
        setInviteSuccess('');
      }, 1600);
      notify('Teammate invited', `${user.name || user.email} was invited as ${user.role}.`, '/settings/users');
    } catch (err) {
      const msg = typeof err?.message === 'string' ? err.message : String(err || 'Could not invite user.');
      setInviteError(msg);
    } finally {
      setInviting(false);
    }
  }

  async function changeRole(id, role) {
    setMenuOpenId(null);
    const prev = users;
    setUsers((p) => p.map((u) => (u.id === id ? { ...u, role } : u)));
    try {
      await api.updateUserRole(id, role);
      const target = users.find((u) => u.id === id);
      notify('Role updated', `${target?.name || target?.email || 'A teammate'} is now ${role}.`, '/settings/users');
    } catch (err) {
      setUsers(prev);
      const msg = typeof err?.message === 'string' ? err.message : String(err || 'Could not update role.');
      setLoadError(msg);
    }
  }

  async function handleDeleteUser(user) {
    setMenuOpenId(null);
    if (!window.confirm(`Are you sure you want to remove user "${user.name || user.email}"?`)) return;
    const prev = users;
    setUsers((p) => p.filter((u) => u.id !== user.id));
    try {
      await api.deleteUser(user.id);
      notify('User removed', `${user.name || user.email} was removed from the team.`, '/settings/users');
    } catch (err) {
      setUsers(prev);
      const msg = typeof err?.message === 'string' ? err.message : String(err || 'Could not delete user.');
      setLoadError(msg);
    }
  }

  async function handleResendInvite(user) {
    setMenuOpenId(null);
    try {
      const res = await api.resendUserInvite(user.id);
      const msg = res.warning || `New temporary password generated for ${user.email}.`;
      alert(`${msg}\n\nTemp Password: ${res.tempPassword || '(Sent via email)'}`);
      notify('Invite Resent', `New temporary password sent to ${user.email}.`, '/settings/users');
    } catch (err) {
      const msg = typeof err?.message === 'string' ? err.message : String(err || 'Could not resend invite.');
      setLoadError(msg);
    }
  }

  return (
    <div>
      <PageHeader
        title="Users & Roles"
        subtitle="Manage team members and permission levels"
        action={
          <button
            onClick={() => setOpen(true)}
            className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft"
          >
            <Plus size={16} /> Invite User
          </button>
        }
      />

      {loadError && (
        <div className="mb-4 rounded-lg bg-tomato-50 px-3.5 py-2.5 text-sm text-tomato-700">{loadError}</div>
      )}

      <Card className="!p-0">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-slate-400 dark:text-slate-500">
            <Loader2 size={16} className="animate-spin" /> Loading users…
          </div>
        ) : users.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-400 dark:text-slate-500">No users yet. Invite your first teammate.</div>
        ) : (
          <>
          <div className="hidden overflow-x-auto sm:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 dark:border-navy-800 text-left text-[11px] uppercase tracking-wide text-slate-400 dark:text-slate-500">
                  <th className="px-5 py-3 font-semibold">User</th>
                  <th className="px-5 py-3 font-semibold">Role</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60 dark:border-navy-800/40 dark:hover:bg-navy-800/40">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <img
                          src={api.getInitialsAvatar(u.name || u.email || 'User')}
                          className="h-9 w-9 rounded-full"
                          alt={u.name}
                        />
                        <div>
                          <p className="font-semibold text-navy-900 dark:text-white">{u.name}</p>
                          <p className="text-xs text-slate-400 dark:text-slate-500">{u.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{u.role}</td>
                    <td className="px-5 py-3.5">
                      <StatusBadge status={u.status} />
                    </td>
                    <td className="relative px-5 py-3.5 text-right">
                      <button
                        onClick={() => setMenuOpenId(menuOpenId === u.id ? null : u.id)}
                        className="rounded-lg p-1.5 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-navy-700"
                      >
                        <MoreHorizontal size={15} />
                      </button>
                      {menuOpenId === u.id && (
                        <div className="absolute right-5 z-10 mt-1 w-52 rounded-xl border border-slate-100 dark:border-navy-800 bg-white dark:bg-navy-900 p-1.5 text-left shadow-card">
                          <p className="px-2.5 py-1.5 text-[11px] font-semibold uppercase text-slate-400 dark:text-slate-500">Change role</p>
                          {ROLES.map((r) => (
                            <button
                              key={r}
                              onClick={() => changeRole(u.id, r)}
                              className={`block w-full rounded-lg px-2.5 py-1.5 text-left text-xs font-medium hover:bg-slate-50 dark:hover:bg-navy-800 ${
                                r === u.role ? 'text-brand-600 font-bold' : 'text-navy-900 dark:text-slate-200'
                              }`}
                            >
                              {r}
                            </button>
                          ))}
                          <div className="my-1.5 border-t border-slate-100 dark:border-navy-800" />
                          <button
                            onClick={() => handleResendInvite(u)}
                            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950/30"
                          >
                            <RefreshCw size={13} /> Reset Temp Password
                          </button>
                          <button
                            onClick={() => handleDeleteUser(u)}
                            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30"
                          >
                            <Trash2 size={13} /> Delete User
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="divide-y divide-slate-50 dark:divide-navy-800/40 sm:hidden">
            {users.map((u) => (
              <div key={u.id} className="relative p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-3">
                    <img
                      src={api.getInitialsAvatar(u.name || u.email || 'User')}
                      className="h-9 w-9 shrink-0 rounded-full"
                      alt={u.name}
                    />
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-navy-900 dark:text-white">{u.name}</p>
                      <p className="truncate text-xs text-slate-400 dark:text-slate-500">{u.email}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setMenuOpenId(menuOpenId === u.id ? null : u.id)}
                    className="shrink-0 rounded-lg p-1.5 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-navy-700"
                  >
                    <MoreHorizontal size={15} />
                  </button>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-navy-800 dark:text-slate-300">{u.role}</span>
                  <StatusBadge status={u.status} />
                </div>
                {menuOpenId === u.id && (
                  <div className="absolute right-4 top-12 z-10 w-48 rounded-xl border border-slate-100 dark:border-navy-800 bg-white dark:bg-navy-900 p-1.5 text-left shadow-card">
                    <p className="px-2.5 py-1.5 text-[11px] font-semibold uppercase text-slate-400 dark:text-slate-500">Change role</p>
                    {ROLES.map((r) => (
                      <button
                        key={r}
                        onClick={() => changeRole(u.id, r)}
                        className={`block w-full rounded-lg px-2.5 py-1.5 text-left text-xs font-medium hover:bg-slate-50 dark:hover:bg-navy-800 ${
                          r === u.role ? 'text-brand-600 font-bold' : 'text-navy-900 dark:text-slate-200'
                        }`}
                      >
                        {r}
                      </button>
                    ))}
                    <div className="my-1.5 border-t border-slate-100 dark:border-navy-800" />
                    <button
                      onClick={() => handleResendInvite(u)}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950/30"
                    >
                      <RefreshCw size={13} /> Reset Temp Password
                    </button>
                    <button
                      onClick={() => handleDeleteUser(u)}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs font-medium text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30"
                    >
                      <Trash2 size={13} /> Delete User
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
          </>
        )}
      </Card>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/50 p-4"
          onClick={() => setOpen(false)}
        >
          <form
            onSubmit={submitInvite}
            className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl bg-white dark:bg-navy-900 p-5 shadow-soft sm:p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">Invite User</h3>
              <button type="button" onClick={() => setOpen(false)} className="rounded-lg p-1.5 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-navy-700">
                <X size={16} />
              </button>
            </div>

            <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
              We'll create their account and email them a sign-in link with a temporary password.
            </p>

            <div className="mt-4 flex flex-col gap-3">
              <div>
                <label className="text-xs font-semibold text-slate-500 dark:text-slate-400">Name</label>
                <input
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
                  placeholder="Jane Smith"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 dark:text-slate-400">Email</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
                  placeholder="jane@company.com"
                  required
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 dark:text-slate-400">Role</label>
                <select
                  value={form.role}
                  onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
                  className="mt-1 w-full rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3.5 py-2.5 text-sm text-navy-900 dark:text-white outline-none focus:border-brand-500"
                >
                  {ROLES.map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </select>
              </div>
            </div>

            {inviteError && (
              <div className="mt-3 rounded-lg bg-tomato-50 px-3.5 py-2.5 text-sm text-tomato-700">{inviteError}</div>
            )}
            {inviteSuccess && (
              <div className="mt-3 rounded-lg bg-emerald-50 px-3.5 py-2.5 text-sm text-emerald-700">{inviteSuccess}</div>
            )}

            <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="w-full rounded-lg border border-slate-200 dark:border-navy-700 px-3.5 py-2.5 text-xs font-semibold text-navy-900 dark:text-white hover:bg-slate-50 dark:hover:bg-navy-800 sm:w-auto sm:py-2"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={inviting}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-brand-500 px-3.5 py-2.5 text-xs font-bold text-white disabled:opacity-60 sm:w-auto sm:py-2"
              >
                {inviting && <Loader2 size={13} className="animate-spin" />}
                Send Invite
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
