import { useState, useEffect } from 'react';
import { useLocation, Outlet } from 'react-router-dom';
import Sidebar from '../components/layout/Sidebar.jsx';
import Topbar from '../components/layout/Topbar.jsx';

export default function DashboardLayout() {
  // Desktop: collapses the sidebar to a narrow icon rail (lg and up).
  const [collapsed, setCollapsed] = useState(false);
  // Mobile/tablet: sidebar is off-canvas by default and opens as a drawer.
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  // Close the mobile drawer automatically whenever the route changes.
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-[#F6F7FB] dark:bg-navy-950 text-navy-900 dark:text-white transition-colors duration-200">
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed((c) => !c)}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />

      <div
        className={`flex min-h-screen flex-col transition-all duration-200 ${collapsed ? 'lg:pl-[76px]' : 'lg:pl-[260px]'}`}
      >
        <div className="sticky top-0 z-20">
          <Topbar onMenuClick={() => setMobileOpen((o) => !o)} />
        </div>

        <div className="flex flex-1">
          <main className="flex-1 overflow-x-hidden p-4 sm:p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
