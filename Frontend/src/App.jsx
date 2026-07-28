import { lazy, Suspense } from 'react';
import { Routes, Route } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout.jsx';
import ProtectedRoute from './components/ProtectedRoute.jsx';
import AdminRoute from './components/AdminRoute.jsx';

// ---------------------------------------------------------------------------
// Lazy-loaded pages — Vite splits each into its own chunk automatically.
// Only the page the user visits gets downloaded, keeping initial load fast.
// ---------------------------------------------------------------------------

// Auth / utility pages
const Login               = lazy(() => import('./pages/Login.jsx'));
const Register            = lazy(() => import('./pages/Register.jsx'));
const VerifyOtp           = lazy(() => import('./pages/VerifyOtp.jsx'));
const ForgotPassword      = lazy(() => import('./pages/ForgotPassword.jsx'));
const ForceChangePassword = lazy(() => import('./pages/ForceChangePassword.jsx'));
const NotFound            = lazy(() => import('./pages/NotFound.jsx'));
const DocumentViewer      = lazy(() => import('./pages/DocumentViewer.jsx'));

// Core app pages
const Dashboard           = lazy(() => import('./pages/Dashboard.jsx'));
const Companies           = lazy(() => import('./pages/Companies.jsx'));
const CompanyDetail       = lazy(() => import('./pages/CompanyDetail.jsx'));
const Tenders             = lazy(() => import('./pages/Tenders.jsx'));
const TenderDetail        = lazy(() => import('./pages/TenderDetail.jsx'));
const NaicsMuster         = lazy(() => import('./pages/NaicsMuster.jsx'));

// AI / Research pages (heaviest — benefit most from splitting)
const AIResearch          = lazy(() => import('./pages/AIResearch.jsx'));
const ProposalBuilder     = lazy(() => import('./pages/ProposalBuilder.jsx'));
const RFPAutoRespond      = lazy(() => import('./pages/RFPAutoRespond.jsx'));

// Campaign / outreach pages
const EmailCampaign       = lazy(() => import('./pages/EmailCampaign.jsx'));
const Newsletter          = lazy(() => import('./pages/Newsletter.jsx'));

// CRM / productivity pages
const CRMPipeline         = lazy(() => import('./pages/CRMPipeline.jsx'));
const Meetings            = lazy(() => import('./pages/Meetings.jsx'));
const Tasks               = lazy(() => import('./pages/Tasks.jsx'));
const Analytics           = lazy(() => import('./pages/Analytics.jsx'));
const Reports             = lazy(() => import('./pages/Reports.jsx'));

// Settings pages
const Settings            = lazy(() => import('./pages/Settings.jsx'));
const UsersRoles          = lazy(() => import('./pages/UsersRoles.jsx'));
const Integrations        = lazy(() => import('./pages/Integrations.jsx'));
const ServerLogs          = lazy(() => import('./pages/ServerLogs.jsx'));

// ---------------------------------------------------------------------------
// Minimal page-transition loading spinner (no external deps)
// ---------------------------------------------------------------------------
function PageLoader() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      height: '100vh', width: '100%',
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: '50%',
        border: '3px solid #e2e8f0',
        borderTopColor: '#6366f1',
        animation: 'spin 0.7s linear infinite',
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/verify-otp" element={<VerifyOtp />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/document-viewer" element={<DocumentViewer />} />

        <Route element={<ProtectedRoute />}>
          <Route path="/force-change-password" element={<ForceChangePassword />} />
          <Route element={<DashboardLayout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/companies" element={<Companies />} />
            <Route path="/companies/:id" element={<CompanyDetail />} />
            <Route path="/tenders" element={<Tenders />} />
            <Route path="/tenders/:id" element={<TenderDetail />} />
            <Route path="/naics" element={<NaicsMuster />} />
            <Route path="/ai-research" element={<AIResearch />} />
            <Route path="/proposal-builder" element={<ProposalBuilder />} />
            <Route path="/email-campaign" element={<EmailCampaign />} />
            <Route path="/newsletter" element={<Newsletter />} />
            <Route path="/crm-pipeline" element={<CRMPipeline />} />
            <Route path="/meetings" element={<Meetings />} />
            <Route path="/tasks" element={<Tasks />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/settings/users" element={<UsersRoles />} />
            <Route path="/settings/integrations" element={<Integrations />} />
            <Route element={<AdminRoute />}>
              <Route path="/settings/server-logs" element={<ServerLogs />} />
            </Route>
            <Route path="/rfp-auto-respond" element={<RFPAutoRespond />} />
          </Route>
        </Route>

        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
