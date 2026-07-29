import { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from '../components/layout/Sidebar.jsx';
import Topbar from '../components/layout/Topbar.jsx';

export default function DashboardLayout() {
  // Desktop-only: collapses the sidebar to icon-width (lg breakpoint and up).
  const [collapsed, setCollapsed] = useState(false);
  // Mobile-only: shows/hides the sidebar as a slide-in drawer (below lg breakpoint).
  const [mobileOpen, setMobileOpen] = useState(false);

  // Keep the background from scrolling behind the drawer while it's open,
  // and make sure the drawer never gets stuck open if the viewport is
  // resized past the lg breakpoint (e.g. rotating a tablet).
  useEffect(() => {
    document.body.style.overflow = mobileOpen ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [mobileOpen]);

  useEffect(() => {
    const mql = window.matchMedia('(min-width: 1024px)');
    const handle = (e) => {
      if (e.matches) setMobileOpen(false);
    };
    mql.addEventListener('change', handle);
    return () => mql.removeEventListener('change', handle);
  }, []);

  return (
    <div className="min-h-screen bg-[#F6F7FB] dark:bg-navy-950 text-navy-900 dark:text-white transition-colors duration-200">
      <Sidebar
        collapsed={collapsed}
        onToggle={() => setCollapsed((c) => !c)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      <div
        className={`flex min-h-screen flex-col transition-[padding] duration-200 ${collapsed ? 'lg:pl-[76px]' : 'lg:pl-[260px]'}`}
      >
        <div className="sticky top-0 z-20">
          <Topbar onMenuClick={() => setMobileOpen((o) => !o)} />
        </div>

        <div className="flex flex-1">
          <main className="flex-1 overflow-x-hidden p-3.5 sm:p-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
