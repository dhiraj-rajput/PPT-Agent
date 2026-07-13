import { Routes, Route } from 'react-router-dom';
import DashboardLayout from './layouts/DashboardLayout.jsx';

import Login from './pages/Login.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Companies from './pages/Companies.jsx';
import CompanyDetail from './pages/CompanyDetail.jsx';
import Tenders from './pages/Tenders.jsx';
import TenderDetail from './pages/TenderDetail.jsx';
import AIResearch from './pages/AIResearch.jsx';
import ProposalBuilder from './pages/ProposalBuilder.jsx';
import EmailCampaign from './pages/EmailCampaign.jsx';
import CRMPipeline from './pages/CRMPipeline.jsx';
import Meetings from './pages/Meetings.jsx';
import Tasks from './pages/Tasks.jsx';
import Analytics from './pages/Analytics.jsx';
import Reports from './pages/Reports.jsx';
import Settings from './pages/Settings.jsx';
import UsersRoles from './pages/UsersRoles.jsx';
import Integrations from './pages/Integrations.jsx';
import NotFound from './pages/NotFound.jsx';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route element={<DashboardLayout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/companies" element={<Companies />} />
        <Route path="/companies/:id" element={<CompanyDetail />} />
        <Route path="/tenders" element={<Tenders />} />
        <Route path="/tenders/:id" element={<TenderDetail />} />
        <Route path="/ai-research" element={<AIResearch />} />
        <Route path="/proposal-builder" element={<ProposalBuilder />} />
        <Route path="/email-campaign" element={<EmailCampaign />} />
        <Route path="/crm-pipeline" element={<CRMPipeline />} />
        <Route path="/meetings" element={<Meetings />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/settings/users" element={<UsersRoles />} />
        <Route path="/settings/integrations" element={<Integrations />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
