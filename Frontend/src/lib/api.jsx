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

export const BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:5050';
const TOKEN_KEY = 'orbitavanya_token';

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------

function _buildUrl(path) {
  const cleanBase = BASE_URL.replace(/\/+$/, '');
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  if (cleanBase.endsWith('/api') && cleanPath.startsWith('/api/')) {
    return `${cleanBase}${cleanPath.slice(4)}`;
  }
  if (cleanBase.endsWith('/api') && cleanPath === '/api') {
    return cleanBase;
  }
  return `${cleanBase}${cleanPath}`;
}

async function _request(method, path, body, opts = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...opts.headers,
  };

  const res = await fetch(_buildUrl(path), {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    ...opts,
  });

  if (!res.ok) {
    if (res.status === 401 && path !== '/api/auth/login') {
      localStorage.removeItem(TOKEN_KEY);
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('auth:unauthorized'));
      }
    }
    let errorMsg = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      let rawDetail = data.detail || data.error || data.message;
      if (Array.isArray(rawDetail)) {
        errorMsg = rawDetail.map(err => (typeof err === 'object' ? err?.msg || err?.message || JSON.stringify(err) : String(err))).join(', ');
      } else if (typeof rawDetail === 'object' && rawDetail !== null) {
        errorMsg = rawDetail?.msg || rawDetail?.message || JSON.stringify(rawDetail);
      } else if (rawDetail) {
        errorMsg = String(rawDetail);
      }
    } catch {}
    throw new Error(errorMsg);
  }

  // 204 No Content
  if (res.status === 204) return null;
  const contentType = res.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    const text = await res.text();
    if (text.trim().startsWith('<!') || text.includes('<html')) {
      throw new Error('Backend server is starting up or offline. Please run the Uvicorn start command in cPanel terminal.');
    }
    try {
      return JSON.parse(text);
    } catch {
      throw new Error(`Server returned unexpected response: ${text.slice(0, 100)}`);
    }
  }
  return res.json();
}

const get = (path, opts) => _request('GET', path, undefined, opts);
const post = (path, body, opts) => _request('POST', path, body, opts);
const patch = (path, body, opts) => _request('PATCH', path, body, opts);
const put = (path, body, opts) => _request('PUT', path, body, opts);
const del = (path, opts) => _request('DELETE', path, undefined, opts);

// ---------------------------------------------------------------------------
// Multipart upload helper (for RFP Auto-Respond)
// ---------------------------------------------------------------------------

async function _upload(path, formData) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const res = await fetch(_buildUrl(path), {
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
  async resendOtp(email) {
    return post('/api/auth/forgot-password', { email });
  },
  async verifyResetOtp(email, otp) {
    return this.verifyOtp(email, otp, 'reset-password');
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
  async deleteUser(userId) {
    return _request('DELETE', `/api/users/${userId}`);
  },
  async resendUserInvite(userId) {
    return post(`/api/users/${userId}/resend-invite`, {});
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
  async clearAllNotifications() {
    return del('/api/notifications');
  },
  async createNotification(title, message, link, userId) {
    return post('/api/notifications', { title, message, link, userId });
  },

  // ---------- Server Logs (admin) ----------
  async getSystemLogs(params = {}) {
    const q = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''))
    ).toString();
    return get(`/api/system-logs${q ? `?${q}` : ''}`);
  },
  async getSystemLogsSummary() {
    return get('/api/system-logs/summary');
  },
  async pollSystemLogs(since) {
    const q = since ? `?since=${encodeURIComponent(since)}` : '';
    return get(`/api/system-logs/poll${q}`);
  },
  async resolveSystemLog(id) {
    return patch(`/api/system-logs/${id}/resolve`, {});
  },
  async unresolveSystemLog(id) {
    return patch(`/api/system-logs/${id}/unresolve`, {});
  },
  async deleteSystemLog(id) {
    return del(`/api/system-logs/${id}`);
  },
  async clearSystemLogs(scope = 'resolved') {
    return del(`/api/system-logs?scope=${scope}`);
  },
  async triggerTestSystemLog() {
    return post('/api/system-logs/test', {});
  },

  // ---------- Integrations ----------
  async getGoogleStatus() {
    return get('/api/integrations/google/status');
  },
  async getGoogleAuthUrl() {
    return get('/api/integrations/google/auth-url');
  },
  async googleDisconnect() {
    return del('/api/integrations/google');
  },
  async googleIntegrationStatus() {
    return this.getGoogleStatus();
  },
  async googleIntegrationAuthUrl() {
    return this.getGoogleAuthUrl();
  },
  async getSamStatus() {
    return get('/api/integrations/sam/status');
  },
  async connectSam(apiKey) {
    return post('/api/integrations/sam/connect', { api_key: apiKey });
  },
  async disconnectSam() {
    return del('/api/integrations/sam');
  },
  async getEnvKeys() {
    return get('/api/integrations/env-keys');
  },
  async saveEnvKeys(keys) {
    return post('/api/integrations/env-keys', keys);
  },
  async getLinkedinStatus() {
    return get('/api/integrations/linkedin/status');
  },
  async saveIntegrationConfig(name, data) {
    return post('/api/integrations/env-keys', data);
  },

  // ---------- NAICS Codes ----------
  async getNaicsCodes(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return get(`/api/naics${qs ? `?${qs}` : ''}`);
  },
  async addNaicsCode(data) {
    return post('/api/naics', data);
  },
  async importNaicsFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    return _upload('/api/naics/import', formData);
  },

  // ---------- Companies ----------
  getOwnCompanyProfile: () => get('/api/companies/own-profile'),
  updateOwnCompanyProfile: (data) => post('/api/companies/own-profile', data),
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
  async importCompanies({ format, data }) {
    // If 'data' is a File object (CSV file upload), use the streaming file endpoint
    // to avoid sending the entire CSV as a JSON string (which causes 500 on large files).
    if (format === 'csv' && data instanceof File) {
      const formData = new FormData();
      formData.append('file', data);
      return _upload('/api/companies/import/file', formData);
    }
    // For JSON arrays or small inline CSV strings, use the JSON body endpoint
    return post('/api/companies/import', { format, data });
  },
  async importCompaniesFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    return _upload('/api/companies/import/file', formData);
  },
  async getCRMPipeline() {
    return get('/api/companies/pipeline');
  },
  async getCompactedProfiles() {
    return get('/api/companies/profiles');
  },
  async getCompanyResearchStatus() {
    return get('/api/companies/research/status');
  },
  async getProfileDetail(slug) {
    if (!slug || String(slug).trim() === '' || String(slug).toLowerCase() === 'none' || String(slug).toLowerCase() === 'undefined' || String(slug).toLowerCase() === 'null') {
      return null;
    }
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

  // ---------- People ----------
  async getPeople(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return get(`/api/people${qs ? `?${qs}` : ''}`);
  },
  async getPerson(id) {
    return get(`/api/people/${id}`);
  },
  async addPerson(personData) {
    return post('/api/people', personData);
  },
  async importPeople({ format, data }) {
    // If 'data' is a File object (CSV/Excel upload), use the streaming file
    // endpoint so large files don't get sent as one giant JSON string.
    if (data instanceof File) {
      const formData = new FormData();
      formData.append('file', data);
      return _upload('/api/people/import/file', formData);
    }
    // JSON array (single record or bulk manual entry grid)
    return post('/api/people/import', { format, data });
  },
  async importPeopleFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    return _upload('/api/people/import/file', formData);
  },
  /** Send client-parsed & reviewed rows directly as JSON (after CSV preview table edits). */
  async importPeopleJSON(rows) {
    return post('/api/people/import/json', { rows });
  },
  /** Update an existing person record by ID. */
  async updatePerson(id, data) {
    return patch(`/api/people/${id}`, data);
  },
  /** Permanently delete a person record by ID. */
  async deletePerson(id) {
    return del(`/api/people/${id}`);
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

  // List downloaded documents for a tender
  getTenderDocuments: (noticeId) => get(`/api/tenders/${encodeURIComponent(noticeId)}/documents`),

  // Serve/stream a specific tender document  
  getTenderDocumentUrl: (noticeId, filename) =>
    _buildUrl(`/api/tenders/${encodeURIComponent(noticeId)}/documents/${encodeURIComponent(filename)}`),

  // Download a tender document as blob
  downloadTenderDocument: async (noticeId, filename) => {
    const token = localStorage.getItem('orbitavanya_token');
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch(
      _buildUrl(`/api/tenders/${encodeURIComponent(noticeId)}/documents/${encodeURIComponent(filename)}`),
      { headers }
    );
    if (!res.ok) throw new Error(`Download failed (${res.status})`);
    return res.blob();
  },

  // ---------- Proposals ----------
  async getProposals() {
    return get('/api/proposals');
  },
  async createProposal(data) {
    return post('/api/proposals', data);
  },
  async generateProposal(data) {
    return post('/api/proposals/generate', data);
  },
  async getProposalStatus(taskId) {
    return get(`/api/proposals/status/${taskId}`);
  },
  async downloadProposal(filename) {
    return _buildUrl(`/api/proposals/download/${filename}`);
  },
  async getRecentProposals(companyName) {
    return get(`/api/proposals/recent?company_name=${encodeURIComponent(companyName)}`);
  },
  async generatePartnership(winner, wizardData = null) {
    return post('/api/proposals/generate-partnership', { 
      winner, 
      ...(wizardData ? { wizard_data: wizardData } : {}) 
    });
  },
  async getProposalStatusByCompany(companyName) {
    return get(`/api/proposals/status?company_name=${encodeURIComponent(companyName)}`);
  },

  // ---------- Reports ----------
  async getReports() {
    return get('/api/reports');
  },
  async updateReportStatus(filename, status) {
    return patch(`/api/reports/${encodeURIComponent(filename)}/status`, { status });
  },
  async sendReportEmail(payload) {
    return post('/api/reports/send-email', payload);
  },
  async downloadReport(filename) {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch(_buildUrl(`/api/reports/download/${filename}`), { headers });
    if (!res.ok) throw new Error('Download failed');
    return res.blob();
  },
  async viewReportBlob(filename) {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch(_buildUrl(`/api/reports/view/${filename}`), { headers });
    if (!res.ok) throw new Error('Failed to fetch preview');
    return res.blob();
  },

  // ---------- RFP Auto-Respond ----------
  async uploadRfp(rfpFiles, templateFile = null, wizardConfig = null) {
    const formData = new FormData();
    if (Array.isArray(rfpFiles)) {
      rfpFiles.forEach(file => {
        formData.append('rfp_files', file);
      });
    } else {
      formData.append('rfp_files', rfpFiles);
    }
    if (templateFile) formData.append('template_file', templateFile);
    if (wizardConfig) formData.append('wizard_config', JSON.stringify(wizardConfig));
    return _upload('/api/rfp-respond/upload', formData);
  },
  async getRfpRespondStatus(taskId) {
    return get(`/api/rfp-respond/status/${taskId}`);
  },
  getRfpRespondDownloadUrl(filename) {
    return _buildUrl(`/api/rfp-respond/download/${filename}`);
  },
  async downloadRfpRespond(filename) {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch(_buildUrl(`/api/rfp-respond/download/${filename}`), { headers });
    if (!res.ok) throw new Error('Download failed');
    return res.blob();
  },
  async viewRfpRespondBlob(filename) {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch(_buildUrl(`/api/rfp-respond/view/${filename}`), { headers });
    if (!res.ok) throw new Error('Failed to fetch preview');
    return res.blob();
  },
  async viewUploadedSourceBlob(taskId, filename) {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch(_buildUrl(`/api/rfp-respond/view-upload/${taskId}/${filename}`), { headers });
    if (!res.ok) throw new Error('Failed to fetch preview');
    return res.blob();
  },

  // ---------- Default Proposal Template (shared across Proposal Builder / RFP pages) ----------
  async getDefaultTemplate() {
    return get('/api/templates/default');
  },
  async uploadDefaultTemplate(templateFile) {
    const formData = new FormData();
    formData.append('template_file', templateFile);
    return _upload('/api/templates/default', formData);
  },
  async deleteDefaultTemplate() {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch(_buildUrl('/api/templates/default'), { method: 'DELETE', headers });
    if (!res.ok) throw new Error('Failed to remove default template');
    return res.json();
  },
  async viewDefaultTemplateBlob() {
    const token = localStorage.getItem(TOKEN_KEY);
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch(_buildUrl('/api/templates/default/view'), { headers });
    if (!res.ok) throw new Error('Failed to fetch template preview');
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
  async uploadCampaignAttachment(file) {
    const formData = new FormData();
    formData.append('file', file);
    return _upload('/api/campaigns/upload-attachment', formData);
  },
  async importLeadsApi(campaignId, leads) {
    return post('/api/leads/import/api', { campaignId, leads });
  },
  async addCompaniesToCampaign(campaignId, companies) {
    return post('/api/leads/import/companies', { campaignId, companies });
  },
  async getCompaniesInUse() {
    return get('/api/leads/companies-in-use');
  },
  async resendLead(id) {
    return post(`/api/leads/${id}/resend`);
  },
  async deleteLead(id) {
    return del(`/api/leads/${id}`);
  },

  // ---------- Newsletter ----------
  async getNewsletters() {
    return get('/api/newsletters');
  },
  async createNewsletter(data) {
    return post('/api/newsletters', data);
  },
  async deleteNewsletter(id) {
    return del(`/api/newsletters/${id}`);
  },
  async getNewsletterSubscribers(id, params = {}) {
    const q = new URLSearchParams(params).toString();
    return get(`/api/newsletters/${id}/subscribers${q ? `?${q}` : ''}`);
  },
  async addNewsletterSubscriber(id, data) {
    return post(`/api/newsletters/${id}/subscribers`, data);
  },
  async addNewsletterSubscribersFromCompanies(id, companyIds = [], manualEmail = '') {
    return post(`/api/newsletters/${id}/subscribers/companies`, { companyIds, manualEmail });
  },
  async addNewsletterSubscribersFromPeople(id, peopleIds = [], manualEmail = '') {
    return post(`/api/newsletters/${id}/subscribers/people`, { peopleIds, manualEmail });
  },
  async createNewsletterEdition(id, data) {
    return post(`/api/newsletters/${id}/editions`, data);
  },
  async getNewsletterEditions(id) {
    return get(`/api/newsletters/${id}/editions`);
  },
  async updateNewsletterEdition(editionId, data) {
    return put(`/api/newsletters/editions/${editionId}`, data);
  },
  async deleteNewsletterEdition(editionId) {
    return del(`/api/newsletters/editions/${editionId}`);
  },
  async uploadNewsletterImage(file) {
    const formData = new FormData();
    formData.append('file', file);
    return _upload('/api/newsletters/upload-image', formData);
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

  // ---------- Generic request helper ----------
  async request(path, opts = {}) {
    const method = opts.method || 'GET';
    let body = opts.body;
    if (body && typeof body === 'string') {
      try { body = JSON.parse(body); } catch {}
    }
    return _request(method, path, body, opts);
  },

  // ---------- Preview / Wizard endpoints ----------
  async getPreviewQuestions(params = {}) {
    const q = new URLSearchParams(params).toString();
    return get(`/api/preview/questions${q ? `?${q}` : ''}`);
  },
  async getPreviewOutline(payload) {
    return post('/api/preview/outline', payload);
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

  // Settings page — upload/assign a profile photo
  async uploadAvatar(file) {
    const formData = new FormData();
    formData.append('file', file);
    return _upload('/api/auth/me/avatar', formData);
  },
  getAvatarUrl(filename) {
    if (!filename) return '';
    return _buildUrl(`/api/auth/avatar/${filename}`);
  },

  // Settings page — change password via OTP flow (same as change-password route)
  async requestChangePasswordOtp() {
    const { user } = await this.me();
    return post('/api/auth/forgot-password', { email: user.email });
  },
  async verifyChangePasswordOtp(otp) {
    const { user } = await this.me();
    const result = await post('/api/auth/verify-otp', { email: user.email, otp, purpose: 'reset-password' });
    return { changeToken: result.actionToken };
  },
  async forceChangePassword(newPassword, confirmPassword) {
    return post('/api/auth/force-change-password', { newPassword, confirmPassword });
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
  getInitialsAvatar(name) {
    const cleanName = (name || 'User').trim();
    const initials = cleanName.split(/\s+/).map(n => n[0]).slice(0, 2).join('').toUpperCase();
    const escapeXml = (s) => String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
    const colors = [
      '#3b82f6',
      '#10b981',
      '#f59e0b',
      '#ef4444',
      '#8b5cf6',
      '#ec4899',
      '#06b6d4',
    ];
    let hash = 0;
    for (let i = 0; i < cleanName.length; i++) {
      hash = cleanName.charCodeAt(i) + ((hash << 5) - hash);
    }
    const color = colors[Math.abs(hash) % colors.length];
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%"><rect width="100" height="100" fill="${encodeURIComponent(color)}"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="40" font-weight="bold" fill="%23ffffff" dy=".3em">${escapeXml(initials)}</text></svg>`;
    return `data:image/svg+xml;utf8,${svg}`;
  },
  getBaseUrl() {
    let cleanBase = BASE_URL.replace(/\/+$/, '');
    if (cleanBase.endsWith('/api')) {
      cleanBase = cleanBase.slice(0, -4);
    }
    return cleanBase;
  },

  // ── AI Email Beautifier ─────────────────────────────────────────────────
  beautifyEmail({ subject = '', body, style = 'professional' }) {
    return _request('POST', '/api/campaigns/beautify-email', { subject, body, style });
  },

  async uploadEmailImage(file) {
    const token = localStorage.getItem(TOKEN_KEY);
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(_buildUrl('/api/campaigns/upload-image'), {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    });
    if (!res.ok) throw new Error(`Image upload failed (${res.status})`);
    return res.json();
  },

  // ── People Leads ────────────────────────────────────────────────────────
  importPeopleToLeads({ campaignId, peopleIds, segmentTag = '' }) {
    return _request('POST', '/api/leads/import/people', { campaignId, peopleIds, segmentTag });
  },

  getPeopleFilters() {
    return _request('GET', '/api/leads/people-filters');
  },

  // ── Database Analytics ──────────────────────────────────────────────────
  getCompaniesSummary() {
    return _request('GET', '/api/analytics/companies-summary');
  },

  getPeopleSummary() {
    return _request('GET', '/api/analytics/people-summary');
  },

  // ── LinkedIn Campaigns ──────────────────────────────────────────────────
  async listLinkedInCampaigns() {
    return get('/api/linkedin/campaigns');
  },
  async createLinkedInCampaign(form) {
    return post('/api/linkedin/campaigns', form);
  },
  async getLinkedInCampaign(id) {
    return get(`/api/linkedin/campaigns/${id}`);
  },
  async updateLinkedInCampaign(id, form) {
    return patch(`/api/linkedin/campaigns/${id}`, form);
  },
  async deleteLinkedInCampaign(id) {
    return del(`/api/linkedin/campaigns/${id}`);
  },
  async importLinkedInTargets(id, { personIds, file }) {
    const fd = new FormData();
    if (personIds) fd.append('person_ids', personIds.join(','));
    if (file) fd.append('file', file);
    
    const token = localStorage.getItem(TOKEN_KEY);
    const res = await fetch(_buildUrl(`/api/linkedin/campaigns/${id}/import-targets`), {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    });
    if (!res.ok) throw new Error(`Target import failed (${res.status})`);
    return res.json();
  },
  async getLinkedInTargets(id, scrapeStatus = '') {
    const query = scrapeStatus ? `?scrape_status=${scrapeStatus}` : '';
    return get(`/api/linkedin/campaigns/${id}/targets${query}`);
  },
  async deleteLinkedInTarget(campaignId, targetId) {
    return del(`/api/linkedin/campaigns/${campaignId}/targets/${targetId}`);
  },
  async getLinkedInQueue(id) {
    return get(`/api/linkedin/campaigns/${id}/queue`);
  },
  async getLinkedInTargetMessages(campaignId, targetId) {
    return get(`/api/linkedin/campaigns/${campaignId}/targets/${targetId}/messages`);
  },
  async reviewLinkedInMessage(messageId, { content, action }) {
    return post(`/api/linkedin/campaigns/messages/${messageId}/review`, { content, action });
  },
  async resendLinkedInMessage(messageId) {
    return post(`/api/linkedin/campaigns/messages/${messageId}/resend`, {});
  },

  // ── LinkedIn Unified Inbox ──────────────────────────────────────────────
  async getLinkedInInbox() {
    return get('/api/linkedin/inbox');
  },
  async sendLinkedInReply(targetId, content) {
    return post('/api/linkedin/inbox/reply', { target_id: targetId, content });
  },

  // ── LinkedIn Accounts ───────────────────────────────────────────────────
  getLinkedInAccounts() {
    return _request('GET', '/api/linkedin/accounts');
  },
  createLinkedInAccount(payload) {
    return _request('POST', '/api/linkedin/accounts', payload);
  },
  pauseLinkedInAccount(id) {
    return _request('POST', `/api/linkedin/accounts/${id}/pause`);
  },
  resumeLinkedInAccount(id) {
    return _request('POST', `/api/linkedin/accounts/${id}/resume`);
  },
  deleteLinkedInAccount(id) {
    return _request('DELETE', `/api/linkedin/accounts/${id}`);
  },
};

export default api;
