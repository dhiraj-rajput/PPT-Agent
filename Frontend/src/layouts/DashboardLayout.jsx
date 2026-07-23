import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from '../components/layout/Sidebar.jsx';
import Topbar from '../components/layout/Topbar.jsx';

export default function DashboardLayout() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="min-h-screen bg-[#F6F7FB] dark:bg-navy-950 text-navy-900 dark:text-white transition-colors duration-200">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />

      <div
        className={`flex min-h-screen flex-col transition-all duration-200 ${collapsed ? 'lg:pl-[76px]' : 'lg:pl-[260px]'}`}
      >
        <Topbar
          onMenuClick={() => setCollapsed((c) => !c)}
        />

        <div className="flex flex-1">
          <main className="flex-1 overflow-x-hidden p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
