/**
 * src/lib/api.jsx
 * ---------------
 * Unified API client for OrbitAvanya.
 *
 * ALL routes — including auth, tasks, meetings, notifications, and every
 * existing feature (companies, tenders, proposals, reports) — point to the
 * single FastAPI backend on http://localhost:5050.
 *
 * Bearer token is automatically injected from localStorage.
 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5050';
const TOKEN_KEY = 'orbitavanya_token';

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

async function _request(method, path, body, opts = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...opts.headers,
  };

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    ...opts,
  });

  if (!res.ok) {
    let errorMsg = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      errorMsg = data.detail || data.error || data.message || errorMsg;
    } catch {}
    throw new Error(errorMsg);
  }

  // 204 No Content
  if (res.status === 204) return null;
  return res.json();
}

const get = (path, opts) => _request('GET', path, undefined, opts);
const post = (path, body, opts) => _request('POST', path, body, opts);
const patch = (path, body, opts) => _request('PATCH', path, body, opts);
const del = (path, opts) => _request('DELETE', path, undefined, opts);

// ---------------------------------------------------------------------------
// Multipart upload helper (for RFP Auto-Respond)
// ---------------------------------------------------------------------------

async function _upload(path, formData) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers,
    body: formData,
  });
  if (!res.ok) {
    let errorMsg = `Upload failed (${res.status})`;
    try {
      const data = await res.json();
      errorMsg = data.detail || data.error || errorMsg;
    } catch {}
    throw new Error(errorMsg);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export const api = {
  // ---------- Auth ----------
  async login(email, password) {
    return post('/api/auth/login', { email, password });
  },
  async register(name, email, phone, password, confirmPassword) {
    return post('/api/auth/register', { name, email, phone, password, confirmPassword });
  },
  async verifyOtp(email, otp, purpose) {
    return post('/api/auth/verify-otp', { email, otp, purpose });
  },
  async verifyRegistration(email, otp) {
    return this.verifyOtp(email, otp, 'register');
  },
  async verifyLogin(email, otp) {
    return this.verifyOtp(email, otp, 'login');
  },
  async forgotPassword(email) {
    return post('/api/auth/forgot-password', { email });
  },
  async resetPassword(actionToken, newPassword, confirmPassword) {
    return post('/api/auth/reset-password', { actionToken, newPassword, confirmPassword });
  },
  async changePassword(currentPassword, newPassword, confirmPassword) {
    return patch('/api/auth/change-password', { currentPassword, newPassword, confirmPassword });
  },
  async me() {
    return get('/api/auth/me');
  },
  async logout() {
    return post('/api/auth/logout', {});
  },

  // ---------- Users ----------
  async getUsers() {
    return get('/api/users');
  },
  async inviteUser(name, email, role) {
    return post('/api/users/invite', { name, email, role });
  },
  async updateUserRole(userId, role) {
    return patch(`/api/users/${userId}/role`, { role });
  },

  // ---------- Tasks ----------
  async getTasks() {
    return get('/api/tasks');
  },
  async createTask(title, due, priority, assigneeId) {
    return post('/api/tasks', { title, due, priority, assigneeId });
  },
  async toggleTask(taskId) {
    return patch(`/api/tasks/${taskId}/toggle`, {});
  },
  async reassignTask(taskId, assigneeId) {
    return patch(`/api/tasks/${taskId}/assignee`, { assigneeId });
  },

  // ---------- Meetings ----------
  async getMeetings() {
    return get('/api/meetings');
  },
  async createMeeting(data) {
    return post('/api/meetings', data);
  },
  async cancelMeeting(meetingId) {
    return post(`/api/meetings/${meetingId}/cancel`, {});
  },

  // ---------- Notifications ----------
  async getNotifications() {
    return get('/api/notifications');
  },
  async markNotificationRead(notifId) {
    return patch(`/api/notifications/${notifId}/read`, {});
  },
  async markAllNotificationsRead() {
    return patch('/api/notifications/read-all', {});
  },
  async deleteNotification(notifId) {
    return del(`/api/notifications/${notifId}`);
  },
  async createNotification(title, message, link, userId) {
    return post('/api/notifications', { title, message, link, userId });
  },

  // ---------- Integrations ----------
  async getGoogleStatus() {
    return get('/api/integrations/google/status');
  },
  async getGoogleAuthUrl() {
    return get('/api/integrations/google/auth-url');
  },
  async googleIntegrationStatus() {
    return this.getGoogleStatus();
  },
  async googleIntegrationAuthUrl() {
    return this.getGoogleAuthUrl();
  },

  // ---------- Companies ----------
  async getCompanies(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return get(`/api/companies${qs ? `?${qs}` : ''}`);
  },
  async getCompany(id) {
    return get(`/api/companies/${id}`);
  },
  async triggerResearch(companyInput, force = false) {
    return post('/api/companies/research', { company: companyInput, force });
  },
  async addCompany(companyData) {
    return post('/api/companies', companyData);
  },
  async importCompanies(format, data) {
    return post('/api/companies/import', { format, data });
  },
  async getCompactedProfiles() {
    return get('/api/companies/profiles');
  },
  async getCompanyResearchStatus() {
    return get('/api/companies/research/status');
  },
  async getProfileDetail(slug) {
    return get(`/api/companies/profiles/detail/${slug}`);
  },
  async searchProfile(q) {
    return get(`/api/companies/profiles/search?q=${encodeURIComponent(q)}`);
  },
  async getAiMode() {
    return get('/api/companies/settings/ai-mode');
  },
  async setAiMode(mode) {
    return post('/api/companies/settings/ai-mode', { mode });
  },

  // ---------- Tenders ----------
  async getTenders(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return get(`/api/tenders${qs ? `?${qs}` : ''}`);
  },
  async getTender(id) {
    return get(`/api/tenders/${id}`);
  },
  async syncTenders(body = {}) {
    return post('/api/tenders/sync', body);
  },
  async getTendersMeta() {
    return get('/api/tenders/meta');
  },
  async getTenderDraftRequest(noticeId) {
    return get(`/api/tenders/${noticeId}/request-draft`);
  },
  async requestTenderDraft(noticeId, data) {
    return post(`/api/tenders/${noticeId}/request-draft`, data);
  },
  async getAllDraftRequests() {
    return get('/api/tenders/draft-requests/all');
  },

  // ---------- Proposals ----------
  async getProposals() {
    return get('/api/proposals');
  },
  async createProposal(data) {
    return post('/api/proposals', data);
  },
  async getProposalStatus(taskId) {
    return get(`/api/proposals/status/${taskId}`);
  },
  async downloadProposal(filename) {
    return `${BASE_URL}/api/proposals/download/${filename}`;
  },
  async getRecentProposals(companyName) {
    return get(`/api/proposals/recent?company_name=${encodeURIComponent(companyName)}`);
  },
  async generatePartnership(winner) {
    return post('/api/proposals/generate-partnership', { winner });
  },
  async getProposalStatusByCompany(companyName) {
    return get(`/api/proposals/status?company_name=${encodeURIComponent(companyName)}`);
  },

  // ---------- Reports ----------
  async getReports() {
    return get('/api/reports');
  },
  async downloadReport(filename) {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch(`${BASE_URL}/api/reports/download/${filename}`, { headers });
    if (!res.ok) throw new Error('Download failed');
    return res.blob();
  },
  async viewReportBlob(filename) {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch(`${BASE_URL}/api/reports/view/${filename}`, { headers });
    if (!res.ok) throw new Error('Failed to fetch preview');
    return res.blob();
  },

  // ---------- RFP Auto-Respond ----------
  async uploadRfp(rfpFiles, templateFile = null) {
    const formData = new FormData();
    if (Array.isArray(rfpFiles)) {
      rfpFiles.forEach(file => {
        formData.append('rfp_files', file);
      });
    } else {
      formData.append('rfp_files', rfpFiles);
    }
    if (templateFile) formData.append('template_file', templateFile);
    return _upload('/api/rfp-respond/upload', formData);
  },
  async getRfpRespondStatus(taskId) {
    return get(`/api/rfp-respond/status/${taskId}`);
  },
  getRfpRespondDownloadUrl(filename) {
    return `${BASE_URL}/api/rfp-respond/download/${filename}`;
  },
  async downloadRfpRespond(filename) {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch(`${BASE_URL}/api/rfp-respond/download/${filename}`, { headers });
    if (!res.ok) throw new Error('Download failed');
    return res.blob();
  },

  // ---------- Email Campaigns ----------
  async listCampaigns() {
    return get('/api/campaigns');
  },
  async createCampaign(form) {
    return post('/api/campaigns', form);
  },
  async getCampaign(id) {
    return get(`/api/campaigns/${id}`);
  },
  async updateCampaign(id, form) {
    return patch(`/api/campaigns/${id}`, form);
  },
  async deleteCampaign(id) {
    return del(`/api/campaigns/${id}`);
  },
  async duplicateCampaign(id) {
    return post(`/api/campaigns/${id}/duplicate`);
  },
  async pauseCampaign(id) {
    return post(`/api/campaigns/${id}/pause`);
  },
  async resumeCampaign(id) {
    return post(`/api/campaigns/${id}/resume`);
  },
  async launchCampaign(id) {
    return post(`/api/campaigns/${id}/launch`);
  },

  // ---------- Leads ----------
  async listLeads(campaignId, status = '') {
    const query = status ? `?campaignId=${campaignId}&status=${status}` : `?campaignId=${campaignId}`;
    return get(`/api/leads${query}`);
  },
  async createLead(leadData) {
    return post('/api/leads', leadData);
  },
  async importLeadsCsv(campaignId, file) {
    const formData = new FormData();
    formData.append('campaignId', campaignId);
    formData.append('file', file);
    return _upload('/api/leads/import/csv', formData);
  },
  async importLeadsApi(campaignId, leads) {
    return post('/api/leads/import/api', { campaignId, leads });
  },
  async deleteLead(id) {
    return del(`/api/leads/${id}`);
  },

  // ---------- Analytics ----------
  async getAnalyticsOverview() {
    return get('/api/analytics/overview');
  },
  async getCampaignAnalytics(id) {
    return get(`/api/analytics/campaign/${id}`);
  },
  async getAnalyticsTrends() {
    return get('/api/analytics/trends');
  },
  async getWebsiteEngagement() {
    return get('/api/analytics/website-engagement');
  },

  // ---------- Health check ----------
  async health() {
    return get('/api/health');
  },

  // ---------- WebSocket Helper ----------
  getWebSocketUrl(path) {
    const url = new URL(path, BASE_URL);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    return url.toString();
  },

  // ---------------------------------------------------------------------------
  // Aliases — exact method names used by the merged Frontend2.0 pages
  // ---------------------------------------------------------------------------
  async listTasks() { return this.getTasks(); },
  async listUsers() { return this.getUsers(); },
  async listMeetings() { return this.getMeetings(); },
  async listNotifications() { return this.getNotifications(); },

  // Settings page — profile update
  async updateProfile(data) {
    return patch('/api/auth/me/profile', data);
  },

  // Settings page — change password via OTP flow (same as change-password route)
  async requestChangePasswordOtp() {
    // The settings page re-uses the /forgot-password flow seeded with the current user's email.
    // We get the current user first, then request a reset OTP.
    const { user } = await this.me();
    return post('/api/auth/forgot-password', { email: user.email });
  },
  async verifyChangePasswordOtp(otp) {
    const { user } = await this.me();
    // Use reset-password purpose to get an action token
    const result = await post('/api/auth/verify-otp', { email: user.email, otp, purpose: 'reset-password' });
    return { changeToken: result.actionToken };
  },
  async confirmChangePassword(actionToken, newPassword, confirmPassword) {
    return post('/api/auth/reset-password', { actionToken, newPassword, confirmPassword });
  },
  async getDashboardData() {
    return get('/api/analytics/dashboard');
  },
  async getCampaignWorkerStatus() {
    return get('/api/campaigns/worker-status');
  },
  async getAvailableAttachments() {
    return get('/api/companies/attachments');
  },
  async sendCompanyEmail(body) {
    return post('/api/companies/send-email', body);
  },
};

export default api;
