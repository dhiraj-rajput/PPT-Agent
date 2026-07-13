import { PageHeader, Card } from '../components/ui/Common.jsx';

export default function Settings() {
  return (
    <div>
      <PageHeader title="Settings" subtitle="Manage your account and workspace preferences" />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <div className="flex flex-col items-center text-center">
            <img src="https://api.dicebear.com/7.x/avataaars/svg?seed=JohnDoe" className="h-20 w-20 rounded-full border border-slate-200" alt="John Doe" />
            <p className="mt-3 text-sm font-bold text-navy-900">John Doe</p>
            <p className="text-xs text-slate-400">Admin · john.doe@orbitavanya.com</p>
            <button className="mt-4 w-full rounded-lg border border-slate-200 py-2 text-xs font-semibold text-navy-900">Change Photo</button>
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <h3 className="text-sm font-bold text-navy-900">Profile Information</h3>
          <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {[
              ['Full Name', 'John Doe'],
              ['Email', 'john.doe@orbitavanya.com'],
              ['Phone', '+1 (555) 019-2833'],
              ['Role', 'Admin'],
              ['Company', 'OrbitAvanya Tech'],
              ['Timezone', 'America/Chicago'],
            ].map(([label, val]) => (
              <div key={label}>
                <label className="mb-1.5 block text-xs font-semibold text-slate-500">{label}</label>
                <input defaultValue={val} className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-navy-900" />
              </div>
            ))}
          </div>
          <button className="mt-5 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-bold text-white shadow-soft">Save Changes</button>
        </Card>

        <Card className="lg:col-span-3">
          <h3 className="text-sm font-bold text-navy-900">Notification Preferences</h3>
          <div className="mt-4 flex flex-col divide-y divide-slate-50">
            {[
              ['New high-match tenders', true],
              ['Weekly performance digest', true],
              ['Proposal deadline reminders', true],
              ['Product updates & tips', false],
            ].map(([label, checked]) => (
              <label key={label} className="flex items-center justify-between py-3 text-sm text-navy-900">
                {label}
                <input type="checkbox" defaultChecked={checked} className="h-4 w-4 rounded border-slate-300 text-brand-600" />
              </label>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
