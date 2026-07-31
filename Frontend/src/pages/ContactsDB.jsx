import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  Building2, Users, Search, Plus, X, Upload, Check, Loader2,
  Trash2, PlusCircle, AlertTriangle, FileText, Pencil, Database,
  TrendingUp, Globe, BarChart2, Star, SlidersHorizontal, RefreshCw,
  Eye, ArrowUp, ArrowDown, ChevronDown
} from 'lucide-react';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, PieChart, Pie, Cell, AreaChart, Area
} from 'recharts';
import { api } from '../lib/api.jsx';
import { PageHeader, Card, MatchBadge, StatusBadge, renderSafeText } from '../components/ui/Common.jsx';
import { useNotifications } from '../context/NotificationContext.jsx';

// ─── Global Constants & Helpers for Contacts Table ──────────────────────────

const REQUIRED_COLS = [
  'source', 'status', 'organization_name',
  'first_name', 'last_name', 'full_name',
  'title', 'function_name', 'seniority',
  'email', 'email_status', 'email_confidence',
  'phone', 'linkedin_url',
  'city', 'state', 'country',
  'job_start_date',
];

const COL_ALIASES = {
  full_name:        ['full name', 'full_name', 'name'],
  first_name:       ['first name', 'first_name', 'firstname'],
  last_name:        ['last name', 'last_name', 'lastname', 'surname'],
  organization_name:['organization', 'organization name', 'organization_name', 'company', 'company name', 'company_name'],
  title:            ['title', 'job title', 'job_title', 'position'],
  function_name:    ['function', 'function_name', 'department'],
  seniority:        ['seniority', 'level'],
  email:            ['email', 'email address', 'email_address'],
  email_status:     ['email status', 'email_status'],
  email_confidence: ['email confidence', 'email_confidence', 'confidence'],
  phone:            ['phone', 'phone number', 'phone_number', 'mobile'],
  linkedin_url:     ['linkedin', 'linkedin url', 'linkedin_url'],
  city:             ['city'],
  state:            ['state', 'province'],
  country:          ['country'],
  job_start_date:   ['job start date', 'job_start_date', 'start date', 'start_date'],
  source:           ['source'],
  status:           ['status'],
};

const COL_LABELS = {
  source: 'Source', status: 'Status', organization_name: 'Organization',
  first_name: 'First', last_name: 'Last', full_name: 'Full Name',
  title: 'Title', function_name: 'Function', seniority: 'Seniority',
  email: 'Email', email_status: 'Email Status', email_confidence: 'Confidence',
  phone: 'Phone', linkedin_url: 'LinkedIn', city: 'City',
  state: 'State', country: 'Country', job_start_date: 'Start Date',
};

const EMPTY_PERSON = Object.fromEntries(REQUIRED_COLS.map(c => [c, c === 'source' ? 'Manual Entry' : c === 'status' ? 'Pending' : '']));

const SOURCE_CHOICES = ['Apollo', 'LinkedIn', 'CSV Import', 'Excel Import', 'Manual Entry'];
const STATUS_CHOICES = ['Pending', 'Processing', 'Completed', 'Failed', 'Duplicate'];

function buildHeaderMap(headers) {
  const map = {};
  headers.forEach(h => {
    const lower = h.trim().toLowerCase();
    for (const [field, aliases] of Object.entries(COL_ALIASES)) {
      if (aliases.includes(lower)) { map[h] = field; break; }
    }
  });
  return map;
}

function parseCSVText(text) {
  const rows = [];
  let field = '', row = [], inQ = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') {
      if (inQ && text[i + 1] === '"') { field += '"'; i++; }
      else inQ = !inQ;
    } else if (ch === ',' && !inQ) {
      row.push(field); field = '';
    } else if ((ch === '\n' || (ch === '\r' && text[i + 1] === '\n')) && !inQ) {
      if (ch === '\r') i++;
      row.push(field); rows.push(row); row = []; field = '';
    } else if (ch === '\r' && !inQ) {
      row.push(field); rows.push(row); row = []; field = '';
    } else {
      field += ch;
    }
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  while (rows.length && rows[rows.length - 1].every(f => !f.trim())) rows.pop();
  return rows;
}

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#3b82f6'];

// ─── Stat Card Component ─────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, sub, color = 'brand' }) {
  const colors = {
    brand:   'text-brand-600 bg-brand-50 dark:bg-brand-950/30',
    emerald: 'text-emerald-600 bg-emerald-50 dark:bg-emerald-950/30',
    violet:  'text-violet-600 bg-violet-50 dark:bg-violet-950/30',
    amber:   'text-amber-600 bg-amber-50 dark:bg-amber-950/30',
  };
  const cls = colors[color] || colors.brand;
  return (
    <div className="rounded-2xl border border-slate-100 dark:border-navy-800 bg-white dark:bg-navy-900 p-5 shadow-card hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl ${cls}`}>
          <Icon size={18} />
        </div>
      </div>
      <p className="mt-3 text-2xl font-extrabold text-navy-900 dark:text-white">{value ?? '—'}</p>
      <p className="text-xs font-semibold text-slate-500 dark:text-slate-400 mt-0.5">{label}</p>
      {sub && <p className="text-[11px] text-slate-400 mt-1 truncate" title={sub}>{sub}</p>}
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function ContactsDB() {
  const { createAlert } = useNotifications();
  const notify = (title, message, link) => createAlert(title, message, link).catch(() => {});

  const [tableView, setTableView] = useState('all'); // 'all' | 'companies' | 'people'
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // Summary Analytics Data States
  const [companiesSummary, setCompaniesSummary] = useState(null);
  const [peopleSummary, setPeopleSummary] = useState(null);
  const [loadingAnalytics, setLoadingAnalytics] = useState(true);

  // Global Add Record Modals States
  const [showAddChoiceModal, setShowAddChoiceModal] = useState(false);
  const [showAddCompanyModal, setShowAddCompanyModal] = useState(false);
  const [showAddPersonModal, setShowAddPersonModal] = useState(false);

  // ──────────────────────────────────────────────────────────────────────────
  // Companies Table States
  // ──────────────────────────────────────────────────────────────────────────
  const [compQuery, setCompQuery] = useState('');
  const [compSizeFilter, setCompSizeFilter] = useState('All');
  const [compNaicsFilter, setCompNaicsFilter] = useState('All');
  const [compResearchedFilter, setCompResearchedFilter] = useState('All');
  const [compNaicsCodes, setCompNaicsCodes] = useState([]);
  const [matchCompanyDesc, setMatchCompanyDesc] = useState(false);
  const [ownCompanyProfile, setOwnCompanyProfile] = useState(null);
  const [matchEntityId, setMatchEntityId] = useState('parent');

  const [companies, setCompanies] = useState([]);
  const [totalCompanies, setTotalCompanies] = useState(0);
  const [companiesPage, setCompaniesPage] = useState(1);
  const [loadingCompanies, setLoadingCompanies] = useState(true);

  // Add Company Forms States
  const [addCompanyTab, setAddCompanyTab] = useState('manual');
  const [companyImportMode, setCompanyImportMode] = useState('document');
  const [companySelectedFile, setCompanySelectedFile] = useState(null);
  const [submittingCompany, setSubmittingCompany] = useState(false);
  const [companySubmitError, setCompanySubmitError] = useState(null);
  const [companyManualForm, setCompanyManualForm] = useState({
    name: '', uei: '', cage_code: '', primary_naics: '', primary_naics_desc: '',
    city: '', state: '', country: 'USA', contact: '', contact_role: 'Procurement Manager',
    email: '', phone: '', size: 'Small', status: 'Active'
  });
  const [companyDocEditor, setCompanyDocEditor] = useState({
    name: '', uei: '', cage_code: '', primary_naics: '', primary_naics_desc: '',
    city: '', state: '', country: 'USA', contact: '', contact_role: 'Procurement Manager',
    email: '', phone: '', size: 'Small', status: 'Active'
  });

  // ──────────────────────────────────────────────────────────────────────────
  // People Table States
  // ──────────────────────────────────────────────────────────────────────────
  const [peopleQuery, setPeopleQuery] = useState('');
  const [peopleStatusFilter, setPeopleStatusFilter] = useState('All');
  const [peopleSourceFilter, setPeopleSourceFilter] = useState('All');
  const [peopleCountryFilter, setPeopleCountryFilter] = useState('All');
  const [peopleSourceOptions, setPeopleSourceOptions] = useState([]);
  const [peopleCountryOptions, setPeopleCountryOptions] = useState([]);

  const [people, setPeople] = useState([]);
  const [totalPeople, setTotalPeople] = useState(0);
  const [peoplePage, setPeoplePage] = useState(1);
  const [loadingPeople, setLoadingPeople] = useState(true);

  // Add Person Forms States
  const [addPersonTab, setAddPersonTab] = useState('manual');
  const [personManualForm, setPersonManualForm] = useState({ ...EMPTY_PERSON });
  const [personSelectedFile, setPersonSelectedFile] = useState(null);
  const [personParsedRows, setPersonParsedRows] = useState([]);
  const [personParseError, setPersonParseError] = useState(null);
  const [personEditingCell, setPersonEditingCell] = useState(null);
  const [submittingPerson, setSubmittingPerson] = useState(false);
  const [personSubmitError, setPersonSubmitError] = useState(null);

  // Person CRUD Action Modals
  const [editPerson, setEditPerson] = useState(null);
  const [editPersonForm, setEditPersonForm] = useState({});
  const [isEditSubmitting, setIsEditSubmitting] = useState(false);
  const [editPersonError, setEditPersonError] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  const debounceRef = useRef(null);
  const LIMIT = 20;

  // ──────────────────────────────────────────────────────────────────────────
  // Fetch Analytics & Core Data on mount
  // ──────────────────────────────────────────────────────────────────────────

  const loadAnalytics = useCallback(async () => {
    setLoadingAnalytics(true);
    try {
      const [cs, ps] = await Promise.all([
        api.getCompaniesSummary().catch(() => null),
        api.getPeopleSummary().catch(() => null)
      ]);
      setCompaniesSummary(cs);
      setPeopleSummary(ps);
    } catch (err) {
      console.error("Failed to load analytics summaries:", err);
    } finally {
      setLoadingAnalytics(false);
    }
  }, []);

  useEffect(() => {
    loadAnalytics();
    api.getOwnCompanyProfile()
      .then(data => setOwnCompanyProfile(data))
      .catch(() => {});
  }, [loadAnalytics]);

  const entityOptions = ownCompanyProfile
    ? [
        { id: 'parent', name: ownCompanyProfile.name || 'Main Company', description: ownCompanyProfile.description, isParent: true },
        ...(ownCompanyProfile.sub_companies || []).map((sub, idx) => ({
          id: String(idx), name: sub.name, description: sub.description, isParent: false
        })),
      ]
    : [];

  const getSelectedEntity = () => entityOptions.find(ent => ent.id === matchEntityId) || entityOptions[0];

  // ──────────────────────────────────────────────────────────────────────────
  // Data Loading Handlers
  // ──────────────────────────────────────────────────────────────────────────

  const loadCompaniesList = useCallback((q = compQuery, p = companiesPage) => {
    setLoadingCompanies(true);
    const params = { page: String(p), limit: String(LIMIT) };
    if (q) params.query = q;
    if (compSizeFilter !== 'All') params.size = compSizeFilter;
    if (compNaicsFilter !== 'All') params.naics = compNaicsFilter;
    if (compResearchedFilter !== 'All') {
      params.researched = compResearchedFilter === 'Researched' ? 'true' : 'false';
    }
    if (matchCompanyDesc && !q) params.match_company_description = 'true';

    api.getCompanies(params)
      .then(res => {
        setCompanies(res?.companies || []);
        setTotalCompanies(res?.total || 0);
        if (res?.naics_codes && compNaicsCodes.length === 0) {
          setCompNaicsCodes(res.naics_codes);
        }
      })
      .catch(() => {})
      .finally(() => setLoadingCompanies(false));
  }, [compQuery, companiesPage, compSizeFilter, compNaicsFilter, compResearchedFilter, matchCompanyDesc]);

  const loadPeopleList = useCallback((q = peopleQuery, p = peoplePage) => {
    setLoadingPeople(true);
    const params = { page: String(p), limit: String(LIMIT) };
    if (q) params.query = q;
    if (peopleStatusFilter !== 'All') params.status = peopleStatusFilter;
    if (peopleSourceFilter !== 'All') params.source = peopleSourceFilter;
    if (peopleCountryFilter !== 'All') params.country = peopleCountryFilter;

    api.getPeople(params)
      .then(res => {
        setPeople(res?.people || []);
        setTotalPeople(res?.total || 0);
        if (res?.source_options) setPeopleSourceOptions(res.source_options);
        if (res?.country_options) setPeopleCountryOptions(res.country_options);
      })
      .catch(() => {})
      .finally(() => setLoadingPeople(false));
  }, [peopleQuery, peoplePage, peopleStatusFilter, peopleSourceFilter, peopleCountryFilter]);

  // Loading triggers
  useEffect(() => {
    if (tableView === 'all' || tableView === 'companies') loadCompaniesList();
  }, [loadCompaniesList, tableView, companiesPage, compSizeFilter, compNaicsFilter, compResearchedFilter, matchCompanyDesc]);

  useEffect(() => {
    if (tableView === 'all' || tableView === 'people') loadPeopleList();
  }, [loadPeopleList, tableView, peoplePage, peopleStatusFilter, peopleSourceFilter, peopleCountryFilter]);

  // Reset pagination
  useEffect(() => { setCompaniesPage(1); }, [compQuery, compSizeFilter, compNaicsFilter, compResearchedFilter, matchCompanyDesc]);
  useEffect(() => { setPeoplePage(1); }, [peopleQuery, peopleStatusFilter, peopleSourceFilter, peopleCountryFilter]);

  // ──────────────────────────────────────────────────────────────────────────
  // Companies Write / Import Submit Handlers
  // ──────────────────────────────────────────────────────────────────────────

  const handleCompanyManualSubmit = (e) => {
    e.preventDefault();
    setSubmittingCompany(true);
    setCompanySubmitError(null);
    api.addCompany(companyManualForm)
      .then(() => {
        setSubmittingCompany(false);
        setShowAddCompanyModal(false);
        setCompanyManualForm({
          name: '', uei: '', cage_code: '', primary_naics: '', primary_naics_desc: '',
          city: '', state: '', country: 'USA', contact: '', contact_role: 'Procurement Manager',
          email: '', phone: '', size: 'Small', status: 'Active'
        });
        loadCompaniesList();
        loadAnalytics();
        notify('Company Added', 'Company details saved successfully.');
      })
      .catch(err => {
        setSubmittingCompany(false);
        setCompanySubmitError(err.message || 'Failed to save company details.');
      });
  };

  const handleCompanyImportSubmit = async (e) => {
    e.preventDefault();
    setSubmittingCompany(true);
    setCompanySubmitError(null);
    try {
      if (companyImportMode === 'document') {
        await api.importCompanies({ data: JSON.stringify([companyDocEditor]), format: 'json' });
      } else {
        if (!companySelectedFile) throw new Error("Select a CSV/JSON file to upload.");
        const format = companySelectedFile.name.toLowerCase().endsWith('.json') ? 'json' : 'csv';
        if (format === 'csv') {
          await api.importCompanies({ data: companySelectedFile, format: 'csv' });
        } else {
          const text = await new Promise((resolve, reject) => {
            const r = new FileReader();
            r.onload = e => resolve(e.target.result);
            r.onerror = () => reject(new Error("Failed to read file"));
            r.readAsText(companySelectedFile);
          });
          await api.importCompanies({ data: text, format: 'json' });
        }
      }
      setSubmittingCompany(false);
      setShowAddCompanyModal(false);
      setCompanySelectedFile(null);
      loadCompaniesList();
      loadAnalytics();
      notify('Import Completed', 'Import pipeline successfully completed.');
    } catch (err) {
      setSubmittingCompany(false);
      setCompanySubmitError(err.message || 'Failed to import data.');
    }
  };

  // ──────────────────────────────────────────────────────────────────────────
  // People Write / Import Submit Handlers
  // ──────────────────────────────────────────────────────────────────────────

  const handlePersonManualSubmit = (e) => {
    e.preventDefault();
    setSubmittingPerson(true);
    setPersonSubmitError(null);
    api.addPerson(personManualForm)
      .then(() => {
        setSubmittingPerson(false);
        setShowAddPersonModal(false);
        setPersonManualForm({ ...EMPTY_PERSON });
        loadPeopleList();
        loadAnalytics();
        notify('Contact Added', 'Person details saved successfully.');
      })
      .catch(err => {
        setSubmittingPerson(false);
        setPersonSubmitError(err.message || 'Failed to save person details.');
      });
  };

  const handlePersonFileSelect = (file) => {
    if (!file) return;
    setPersonSelectedFile(file);
    setPersonParsedRows([]);
    setPersonParseError(null);
    setPersonSubmitError(null);
    const r = new FileReader();
    r.onload = (e) => {
      try {
        const text = e.target.result;
        const allRows = parseCSVText(text);
        if (allRows.length < 2) { setPersonParseError('CSV has no data rows.'); return; }
        const rawHeaders = allRows[0];
        const headerMap = buildHeaderMap(rawHeaders);
        const mappedFields = new Set(Object.values(headerMap));
        const hasName = mappedFields.has('full_name') || mappedFields.has('first_name') || mappedFields.has('last_name');
        const hasEmail = mappedFields.has('email');
        if (!hasName && !hasEmail) {
          setPersonParseError('Missing contact identity columns (First Name, Last Name, or Email).');
          return;
        }

        const data = allRows.slice(1).map(vals => {
          const obj = Object.fromEntries(REQUIRED_COLS.map(c => [c, '']));
          rawHeaders.forEach((h, i) => {
            const field = headerMap[h];
            if (field) obj[field] = (vals[i] ?? '').trim();
          });
          if (!obj.full_name && (obj.first_name || obj.last_name)) {
            obj.full_name = `${obj.first_name} ${obj.last_name}`.trim();
          }
          return obj;
        }).filter(row => row.full_name || row.first_name || row.last_name || row.email);

        if (data.length === 0) {
          setPersonParseError('No rows containing name or email were found.');
          return;
        }
        setPersonParsedRows(data);
      } catch {
        setPersonParseError('Failed to parse CSV.');
      }
    };
    r.readAsText(file);
  };

  const handlePersonImportSubmit = async (e) => {
    e.preventDefault();
    setSubmittingPerson(true);
    setPersonSubmitError(null);
    try {
      if (!personParsedRows.length) throw new Error('Choose a CSV file with valid contacts.');
      await api.importPeopleJSON(personParsedRows);
      setSubmittingPerson(false);
      setShowAddPersonModal(false);
      setPersonSelectedFile(null);
      setPersonParsedRows([]);
      loadPeopleList();
      loadAnalytics();
      notify('Contacts Imported', 'Contacts database imported successfully.');
    } catch (err) {
      setSubmittingPerson(false);
      setPersonSubmitError(err.message || 'Import failed.');
    }
  };

  // ──────────────────────────────────────────────────────────────────────────
  // CRUD Updates & Delete
  // ──────────────────────────────────────────────────────────────────────────

  const openPersonEdit = (person) => {
    setEditPerson(person);
    setEditPersonForm({
      source: person.source || 'Manual Entry',
      status: person.status || 'Pending',
      organization_name: person.organization_name || '',
      first_name: person.first_name || '',
      last_name: person.last_name || '',
      full_name: person.full_name || '',
      title: person.title || '',
      function_name: person.function_name || '',
      seniority: person.seniority || '',
      email: person.email || '',
      email_status: person.email_status || '',
      email_confidence: person.email_confidence ?? '',
      phone: person.phone || '',
      linkedin_url: person.linkedin_url || '',
      city: person.city || '',
      state: person.state || '',
      country: person.country || '',
      job_start_date: person.job_start_date ? person.job_start_date.slice(0, 10) : '',
    });
    setEditPersonError(null);
  };

  const handlePersonEditSubmit = (e) => {
    e.preventDefault();
    setIsEditSubmitting(true);
    setEditPersonError(null);
    api.updatePerson(editPerson.id, editPersonForm)
      .then(() => {
        setIsEditSubmitting(false);
        setEditPerson(null);
        loadPeopleList();
        loadAnalytics();
        notify('Contact Updated', 'Contact details saved.');
      })
      .catch(err => {
        setIsEditSubmitting(false);
        setEditPersonError(err.message || 'Failed to save changes.');
      });
  };

  const handlePersonDeleteConfirm = () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    setDeleteError(null);
    api.deletePerson(deleteTarget.id)
      .then(() => {
        setIsDeleting(false);
        setDeleteTarget(null);
        loadPeopleList();
        loadAnalytics();
        notify('Contact Deleted', 'Contact removed from database.');
      })
      .catch(err => {
        setIsDeleting(false);
        setDeleteError(err.message || 'Failed to delete contact.');
      });
  };

  // ──────────────────────────────────────────────────────────────────────────
  // Recharts Chart Configurations
  // ──────────────────────────────────────────────────────────────────────────

  const topCountriesCombined = useMemo(() => {
    const countries = {};
    if (companiesSummary?.byCountry) {
      companiesSummary.byCountry.forEach(c => {
        countries[c.name] = (countries[c.name] || 0) + c.value;
      });
    }
    if (peopleSummary?.byCountry) {
      peopleSummary.byCountry.forEach(c => {
        countries[c.name] = (countries[c.name] || 0) + c.value;
      });
    }
    return Object.entries(countries)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 5);
  }, [companiesSummary, peopleSummary]);

  const recordTypesData = [
    { name: 'Companies', value: companiesSummary?.total || 0 },
    { name: 'People', value: peopleSummary?.total || 0 }
  ];

  const totalRecordsCount = (companiesSummary?.total || 0) + (peopleSummary?.total || 0);

  // ──────────────────────────────────────────────────────────────────────────
  // UI Render
  // ──────────────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-violet-500 shadow-soft">
            <Database size={20} className="text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-navy-900 dark:text-white">Unified Database</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">Complete contacts &amp; company listings dashboard</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* View Dropdown */}
          <div className="relative">
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-4 py-2.5 text-sm font-semibold text-navy-900 dark:text-white shadow-sm hover:border-brand-400 transition-colors"
            >
              {tableView === 'all' ? <Database size={15} /> : tableView === 'companies' ? <Building2 size={15} /> : <Users size={15} />}
              View: {tableView === 'all' ? 'All Data' : tableView === 'companies' ? 'Companies' : 'People'}
              <ChevronDown size={14} className={`transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
            </button>
            {dropdownOpen && (
              <div className="absolute right-0 mt-2 w-44 rounded-xl border border-slate-100 dark:border-navy-700 bg-white dark:bg-navy-800 shadow-xl z-30 overflow-hidden">
                {[
                  { value: 'all', label: 'All Combined', icon: Database },
                  { value: 'companies', label: 'Companies', icon: Building2 },
                  { value: 'people', label: 'People', icon: Users }
                ].map(opt => {
                  const Ico = opt.icon;
                  return (
                    <button
                      key={opt.value}
                      onClick={() => { setTableView(opt.value); setDropdownOpen(false); }}
                      className={`flex w-full items-center gap-2 px-4 py-3 text-sm font-semibold transition-colors ${tableView === opt.value ? 'bg-brand-50 dark:bg-brand-950/30 text-brand-600 dark:text-brand-400' : 'text-navy-900 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-navy-700'}`}
                    >
                      <Ico size={14} /> {opt.label}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Unified Add Button */}
          <button
            onClick={() => setShowAddChoiceModal(true)}
            className="flex items-center gap-2 rounded-xl bg-brand-500 hover:bg-brand-600 px-4 py-2.5 text-sm font-bold text-white shadow-soft transition-colors"
          >
            <Plus size={16} /> Add Record
          </button>
        </div>
      </div>

      {/* ─── STAT CARDS SECTION ─── */}
      {loadingAnalytics ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="rounded-2xl border border-slate-100 dark:border-navy-800 bg-white dark:bg-navy-900 p-5 shadow-card animate-pulse">
              <div className="h-10 w-10 rounded-xl bg-slate-100 dark:bg-navy-800 mb-3" />
              <div className="h-6 w-16 rounded bg-slate-100 dark:bg-navy-800 mb-1" />
              <div className="h-3 w-24 rounded bg-slate-100 dark:bg-navy-800" />
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {tableView === 'all' && (
            <>
              <StatCard icon={Database} label="Total Records" value={totalRecordsCount.toLocaleString()} color="brand" />
              <StatCard icon={Building2} label="Total Companies" value={companiesSummary?.total?.toLocaleString()} color="violet" />
              <StatCard icon={Users} label="Total People" value={peopleSummary?.total?.toLocaleString()} color="emerald" />
              <StatCard icon={Globe} label="Primary Country" value={companiesSummary?.topCountry || peopleSummary?.topCountry || '—'} color="amber" />
            </>
          )}

          {tableView === 'companies' && (
            <>
              <StatCard icon={Building2} label="Total Companies" value={companiesSummary?.total?.toLocaleString()} color="brand" />
              <StatCard icon={BarChart2} label="Status Summary" value={Object.values(companiesSummary?.byStatus || {}).reduce((a,b)=>a+b, 0).toLocaleString()} sub={Object.entries(companiesSummary?.byStatus || {}).map(([k,v])=>`${k}: ${v}`).join(' · ')} color="emerald" />
              <StatCard icon={Globe} label="Top Country" value={companiesSummary?.topCountry || '—'} color="violet" />
              <StatCard icon={Star} label="Top NAICS Category" value={companiesSummary?.topNaics?.slice(0, 26) || '—'} color="amber" />
            </>
          )}

          {tableView === 'people' && (
            <>
              <StatCard icon={Users} label="Total People" value={peopleSummary?.total?.toLocaleString()} color="brand" />
              <StatCard icon={BarChart2} label="Status Summary" value={Object.values(peopleSummary?.byStatus || {}).reduce((a,b)=>a+b, 0).toLocaleString()} sub={Object.entries(peopleSummary?.byStatus || {}).map(([k,v])=>`${k}: ${v}`).join(' · ')} color="emerald" />
              <StatCard icon={Globe} label="Top Country" value={peopleSummary?.topCountry || '—'} color="violet" />
              <StatCard icon={TrendingUp} label="Top Seniority" value={peopleSummary?.topSeniority || '—'} color="amber" />
            </>
          )}
        </div>
      )}

      {/* ─── GRAPHICAL ANALYTICS SECTION ─── */}
      {!loadingAnalytics && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {/* ALL/COMBINED VIEWS DASHBOARD */}
          {tableView === 'all' && (
            <>
              <Card>
                <div className="p-4 border-b dark:border-navy-850"><h4 className="text-xs font-bold text-navy-900 dark:text-white uppercase tracking-wider">Record Ratio (Companies vs People)</h4></div>
                <div className="h-64 p-4 flex items-center justify-center">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={recordTypesData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={80} paddingAngle={5} label>
                        {recordTypesData.map((entry, idx) => <Cell key={`cell-${idx}`} fill={COLORS[idx % COLORS.length]} />)}
                      </Pie>
                      <Tooltip />
                      <Legend verticalAlign="bottom" height={36} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </Card>

              <Card className="xl:col-span-2">
                <div className="p-4 border-b dark:border-navy-850"><h4 className="text-xs font-bold text-navy-900 dark:text-white uppercase tracking-wider">Location Country Breakdown (Combined)</h4></div>
                <div className="h-64 p-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={topCountriesCombined}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip />
                      <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} name="Total Records" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            </>
          )}

          {/* COMPANIES DASHBOARD */}
          {tableView === 'companies' && (
            <>
              <Card>
                <div className="p-4 border-b dark:border-navy-850"><h4 className="text-xs font-bold text-navy-900 dark:text-white uppercase tracking-wider">Business Size Ratio</h4></div>
                <div className="h-64 p-4 flex items-center justify-center">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={companiesSummary?.bySize || []} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={80} paddingAngle={5} label>
                        {(companiesSummary?.bySize || []).map((entry, idx) => <Cell key={`cell-${idx}`} fill={COLORS[idx % COLORS.length]} />)}
                      </Pie>
                      <Tooltip />
                      <Legend verticalAlign="bottom" height={36} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </Card>

              <Card className="xl:col-span-2">
                <div className="p-4 border-b dark:border-navy-850"><h4 className="text-xs font-bold text-navy-900 dark:text-white uppercase tracking-wider">Top NAICS Industry Distribution</h4></div>
                <div className="h-64 p-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={companiesSummary?.byNaics || []} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" tick={{ fontSize: 10 }} />
                      <YAxis dataKey="name" type="category" width={110} tick={{ fontSize: 9 }} />
                      <Tooltip />
                      <Bar dataKey="value" fill="#8b5cf6" radius={[0, 4, 4, 0]} name="Companies Count" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            </>
          )}

          {/* PEOPLE DASHBOARD */}
          {tableView === 'people' && (
            <>
              <Card>
                <div className="p-4 border-b dark:border-navy-850"><h4 className="text-xs font-bold text-navy-900 dark:text-white uppercase tracking-wider">Contact Sources Ratio</h4></div>
                <div className="h-64 p-4 flex items-center justify-center">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={peopleSummary?.bySource || []} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={80} paddingAngle={5} label>
                        {(peopleSummary?.bySource || []).map((entry, idx) => <Cell key={`cell-${idx}`} fill={COLORS[idx % COLORS.length]} />)}
                      </Pie>
                      <Tooltip />
                      <Legend verticalAlign="bottom" height={36} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </Card>

              <Card className="xl:col-span-2">
                <div className="p-4 border-b dark:border-navy-850"><h4 className="text-xs font-bold text-navy-900 dark:text-white uppercase tracking-wider">Contacts Seniority Level distribution</h4></div>
                <div className="h-64 p-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={peopleSummary?.bySeniority || []}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="name" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip />
                      <Bar dataKey="value" fill="#10b981" radius={[4, 4, 0, 0]} name="Contacts Count" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            </>
          )}
        </div>
      )}

      {/* ─── DETAILED TABLES VIEW ─── */}
      {(tableView === 'all' || tableView === 'companies') && (
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <Building2 size={16} className="text-brand-500" />
            <h3 className="text-sm font-extrabold text-navy-900 dark:text-white">Companies Directory</h3>
          </div>
          <CompaniesView />
        </Card>
      )}

      {(tableView === 'all' || tableView === 'people') && (
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <Users size={16} className="text-brand-500" />
            <h3 className="text-sm font-extrabold text-navy-900 dark:text-white">People &amp; Contacts Directory</h3>
          </div>
          <PeopleView />
        </Card>
      )}

      {/* ─── MODALS ─── */}

      {/* 1. Add Choice Modal */}
      {showAddChoiceModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4 backdrop-blur-md" onClick={() => setShowAddChoiceModal(false)}>
          <div className="w-full max-w-sm rounded-2xl bg-white dark:bg-navy-800 shadow-2xl p-5 border text-center space-y-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-extrabold text-navy-900 dark:text-white">What would you like to add?</h3>
            <p className="text-xs text-slate-400">Choose the type of entry you want to insert into the database.</p>
            <div className="grid grid-cols-2 gap-3">
              <button
                onClick={() => { setShowAddChoiceModal(false); setShowAddCompanyModal(true); }}
                className="flex flex-col items-center justify-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 p-4 hover:border-brand-500 hover:bg-brand-50/20"
              >
                <Building2 size={24} className="text-brand-500" />
                <span className="text-xs font-bold text-navy-900 dark:text-white">New Company</span>
              </button>
              <button
                onClick={() => { setShowAddChoiceModal(false); setShowAddPersonModal(true); }}
                className="flex flex-col items-center justify-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 p-4 hover:border-brand-500 hover:bg-brand-50/20"
              >
                <Users size={24} className="text-brand-500" />
                <span className="text-xs font-bold text-navy-900 dark:text-white">New Person</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 2. Add Company Modal */}
      {showAddCompanyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4 backdrop-blur-md" onClick={() => setShowAddCompanyModal(false)}>
          <div className="w-full max-w-2xl rounded-2xl bg-white dark:bg-navy-800 shadow-2xl overflow-hidden border flex flex-col max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b p-5 bg-white dark:bg-navy-800">
              <div>
                <h3 className="text-base font-extrabold text-navy-900 dark:text-white">Add New Company</h3>
                <p className="text-xs text-slate-400 mt-1">Add details manually or import CSV/JSON files</p>
              </div>
              <button onClick={() => setShowAddCompanyModal(false)} className="rounded-lg p-2 text-slate-400 hover:text-navy-950 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-navy-900 transition-colors">
                <X size={18} />
              </button>
            </div>

            <div className="flex border-b bg-slate-50 dark:bg-navy-900 shrink-0">
              <button onClick={() => setAddCompanyTab('manual')} className={`flex-1 py-3 text-xs font-bold border-b-2 ${addCompanyTab === 'manual' ? 'border-brand-500 text-brand-600 bg-white dark:bg-navy-800' : 'border-transparent text-slate-500'}`}>Manually Enter Details</button>
              <button onClick={() => setAddCompanyTab('import')} className={`flex-1 py-3 text-xs font-bold border-b-2 ${addCompanyTab === 'import' ? 'border-brand-500 text-brand-600 bg-white dark:bg-navy-800' : 'border-transparent text-slate-500'}`}>Import CSV / JSON</button>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              {companySubmitError && <div className="mb-4 rounded-xl bg-rose-50 border border-rose-105 p-3 text-xs font-semibold text-rose-600">{companySubmitError}</div>}

              {addCompanyTab === 'manual' ? (
                <form onSubmit={handleCompanyManualSubmit} className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Legal Business Name *</label>
                      <input required value={companyManualForm.name} onChange={e => setCompanyManualForm({...companyManualForm, name: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none focus:bg-white dark:focus:bg-navy-950" placeholder="Company Name"/>
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Unique Entity ID (UEI) *</label>
                      <input required value={companyManualForm.uei} onChange={e => setCompanyManualForm({...companyManualForm, uei: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none font-mono" placeholder="12-char ID"/>
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">CAGE Code (Optional)</label>
                      <input value={companyManualForm.cage_code} onChange={e => setCompanyManualForm({...companyManualForm, cage_code: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none font-mono" placeholder="5-char CAGE"/>
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Business Size (Optional)</label>
                      <select value={companyManualForm.size} onChange={e => setCompanyManualForm({...companyManualForm, size: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none">
                        <option value="Small">Small Business</option>
                        <option value="Large">Large Business</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Primary NAICS Code</label>
                      <input value={companyManualForm.primary_naics} onChange={e => setCompanyManualForm({...companyManualForm, primary_naics: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="e.g. 541511"/>
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Primary NAICS Description</label>
                      <input value={companyManualForm.primary_naics_desc} onChange={e => setCompanyManualForm({...companyManualForm, primary_naics_desc: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="e.g. Custom Computer Programming"/>
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">City</label>
                      <input value={companyManualForm.city} onChange={e => setCompanyManualForm({...companyManualForm, city: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="City"/>
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">State</label>
                      <input value={companyManualForm.state} onChange={e => setCompanyManualForm({...companyManualForm, state: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="State"/>
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Country</label>
                      <input value={companyManualForm.country} onChange={e => setCompanyManualForm({...companyManualForm, country: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="Country"/>
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Contact Name</label>
                      <input value={companyManualForm.contact} onChange={e => setCompanyManualForm({...companyManualForm, contact: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="Name"/>
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Contact Role</label>
                      <input value={companyManualForm.contact_role} onChange={e => setCompanyManualForm({...companyManualForm, contact_role: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="Role"/>
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Contact Email</label>
                      <input type="email" value={companyManualForm.email} onChange={e => setCompanyManualForm({...companyManualForm, email: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="Email"/>
                    </div>
                  </div>
                  <div className="flex justify-end gap-3 pt-5 border-t dark:border-navy-700 shrink-0">
                    <button type="button" onClick={() => setShowAddCompanyModal(false)} className="rounded-xl border dark:border-navy-700 px-5 py-2.5 text-xs font-semibold hover:bg-slate-50 dark:text-white">Cancel</button>
                    <button type="submit" disabled={submittingCompany} className="rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white hover:bg-brand-600 disabled:opacity-70 flex items-center gap-1.5">
                      {submittingCompany && <Loader2 className="animate-spin" size={14}/>} Save Details
                    </button>
                  </div>
                </form>
              ) : (
                <form onSubmit={handleCompanyImportSubmit} className="space-y-4">
                  <div className="flex gap-2 mb-2">
                    <button type="button" onClick={() => setCompanyImportMode('document')} className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${companyImportMode === 'document' ? 'bg-brand-500 text-white' : 'bg-slate-100 text-slate-600'}`}>Document Editor</button>
                    <button type="button" onClick={() => setCompanyImportMode('file')} className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${companyImportMode === 'file' ? 'bg-brand-500 text-white' : 'bg-slate-100 text-slate-600'}`}>Upload File</button>
                  </div>

                  {companyImportMode === 'document' ? (
                    <div className="rounded-xl border dark:border-navy-700 bg-slate-50 dark:bg-navy-950 p-4 font-mono text-xs space-y-2 max-h-80 overflow-y-auto">
                      <div className="pl-3 space-y-2.5">
                        {['name', 'uei', 'cage_code', 'primary_naics', 'primary_naics_desc', 'city', 'state', 'country', 'contact', 'email', 'phone'].map(key => (
                          <div key={key} className="flex items-center gap-2">
                            <span className="w-36 text-brand-600 dark:text-brand-400">"{key}"</span>
                            <input value={companyDocEditor[key] || ''} onChange={e => setCompanyDocEditor({...companyDocEditor, [key]: e.target.value})} className="flex-1 rounded border dark:border-navy-700 bg-white dark:bg-navy-900 px-3 py-1 text-xs text-navy-900 dark:text-white" placeholder={key}/>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center cursor-pointer hover:border-brand-400 border-slate-200 dark:border-navy-700" onClick={() => document.getElementById('company-file-upload-input').click()}>
                      <Upload className="text-slate-300 mb-2" size={32} />
                      <p className="text-sm font-semibold text-navy-900 dark:text-white">{companySelectedFile ? companySelectedFile.name : 'Click to upload CSV or JSON file'}</p>
                      <input id="company-file-upload-input" type="file" accept=".csv,.json" className="hidden" onChange={e => {if(e.target.files?.[0]) setCompanySelectedFile(e.target.files[0])}}/>
                    </div>
                  )}

                  <div className="flex justify-end gap-3 pt-5 border-t dark:border-navy-700 shrink-0">
                    <button type="button" onClick={() => setShowAddCompanyModal(false)} className="rounded-xl border dark:border-navy-700 px-5 py-2.5 text-xs font-semibold hover:bg-slate-50 dark:text-white">Cancel</button>
                    <button type="submit" disabled={submittingCompany} className="rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white hover:bg-brand-600 disabled:opacity-70 flex items-center gap-1.5">
                      {submittingCompany && <Loader2 className="animate-spin" size={14}/>} Bulk Import
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 3. Add Person / Contact Modal */}
      {showAddPersonModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4 backdrop-blur-md" onClick={() => setShowAddPersonModal(false)}>
          <div className="w-full max-w-4xl rounded-2xl bg-white dark:bg-navy-800 shadow-2xl overflow-hidden border flex flex-col max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b p-5 bg-white dark:bg-navy-800 shrink-0">
              <div>
                <h3 className="text-base font-extrabold text-navy-900 dark:text-white">Add People</h3>
                <p className="text-xs text-slate-400 mt-1">Add a person manually or upload a CSV file with interactive preview</p>
              </div>
              <button onClick={() => setShowAddPersonModal(false)} className="rounded-lg p-2 text-slate-400 hover:text-navy-955 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-navy-900 transition-colors">
                <X size={18} />
              </button>
            </div>

            <div className="flex border-b bg-slate-50 dark:bg-navy-900 shrink-0">
              <button onClick={() => setAddPersonTab('manual')} className={`flex-1 py-3 text-xs font-bold border-b-2 ${addPersonTab === 'manual' ? 'border-brand-500 text-brand-600 bg-white dark:bg-navy-800' : 'border-transparent text-slate-500'}`}>Manual Entry</button>
              <button onClick={() => setAddPersonTab('import')} className={`flex-1 py-3 text-xs font-bold border-b-2 ${addPersonTab === 'import' ? 'border-brand-500 text-brand-600 bg-white dark:bg-navy-800' : 'border-transparent text-slate-500'}`}>CSV Upload &amp; Review</button>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              {personSubmitError && <div className="mb-4 rounded-xl bg-rose-50 border border-rose-100 p-3 text-xs text-rose-600 font-semibold">{personSubmitError}</div>}

              {addPersonTab === 'manual' ? (
                <form onSubmit={handlePersonManualSubmit} className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">First Name</label><input value={personManualForm.first_name} onChange={e=>setPersonManualForm({...personManualForm, first_name: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="First Name"/></div>
                    <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Last Name</label><input value={personManualForm.last_name} onChange={e=>setPersonManualForm({...personManualForm, last_name: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="Last Name"/></div>
                    <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Job Title</label><input value={personManualForm.title} onChange={e=>setPersonManualForm({...personManualForm, title: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="e.g. Sales Director"/></div>
                    <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Organization / Company Name</label><input value={personManualForm.organization_name} onChange={e=>setPersonManualForm({...personManualForm, organization_name: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="Company"/></div>
                    <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Email Address</label><input type="email" value={personManualForm.email} onChange={e=>setPersonManualForm({...personManualForm, email: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="email@company.com"/></div>
                    <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Phone Number</label><input value={personManualForm.phone} onChange={e=>setPersonManualForm({...personManualForm, phone: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="+1-234-567-8900"/></div>
                    <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">LinkedIn Profile URL</label><input value={personManualForm.linkedin_url} onChange={e=>setPersonManualForm({...personManualForm, linkedin_url: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="https://linkedin.com/..."/></div>
                    <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Seniority</label><select value={personManualForm.seniority} onChange={e=>setPersonManualForm({...personManualForm, seniority: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none"><option value="">Select Level</option><option value="Junior">Junior</option><option value="Mid">Mid Level</option><option value="Senior">Senior</option><option value="Director">Director / Executive</option></select></div>
                    <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">City</label><input value={personManualForm.city} onChange={e=>setPersonManualForm({...personManualForm, city: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="City"/></div>
                    <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Country</label><input value={personManualForm.country} onChange={e=>setPersonManualForm({...personManualForm, country: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="Country"/></div>
                  </div>
                  <div className="flex justify-end gap-3 pt-5 border-t dark:border-navy-700 shrink-0">
                    <button type="button" onClick={() => setShowAddPersonModal(false)} className="rounded-xl border dark:border-navy-700 px-5 py-2.5 text-xs font-semibold hover:bg-slate-50 dark:text-white">Cancel</button>
                    <button type="submit" disabled={submittingPerson} className="rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white hover:bg-brand-600 disabled:opacity-70 flex items-center gap-1.5">
                      {submittingPerson && <Loader2 className="animate-spin" size={14}/>} Save Details
                    </button>
                  </div>
                </form>
              ) : (
                <form onSubmit={handlePersonImportSubmit} className="space-y-4">
                  {/* File selection dropzone */}
                  {!personParsedRows.length ? (
                    <div className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center cursor-pointer hover:border-brand-400 border-slate-200 dark:border-navy-700" onClick={() => document.getElementById('person-file-upload-input').click()}>
                      <Upload className="text-slate-300 mb-2" size={32} />
                      <p className="text-sm font-semibold text-navy-900 dark:text-white">Click to upload people CSV</p>
                      <input id="person-file-upload-input" type="file" accept=".csv" className="hidden" onChange={e => {if(e.target.files?.[0]) handlePersonFileSelect(e.target.files[0])}}/>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between rounded-xl bg-slate-50 dark:bg-navy-900 p-3">
                      <div className="flex items-center gap-2">
                        <FileText size={18} className="text-brand-500" />
                        <span className="text-xs font-bold text-navy-900 dark:text-white">{personSelectedFile?.name}</span>
                        <span className="text-[10px] text-slate-400">({personParsedRows.length} rows parsed)</span>
                      </div>
                      <button type="button" onClick={() => {setPersonParsedRows([]); setPersonSelectedFile(null);}} className="text-xs text-rose-500 font-bold hover:underline">Change File</button>
                    </div>
                  )}

                  {personParseError && <div className="rounded-xl bg-rose-50 border border-rose-100 p-3 text-xs text-rose-600 font-semibold">{personParseError}</div>}

                  {/* Interactive Table Review */}
                  {personParsedRows.length > 0 && (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-slate-500">Edit values inline before importing</span>
                        <button type="button" onClick={() => setPersonParsedRows([...personParsedRows, { ...EMPTY_PERSON, source: 'CSV Import' }])} className="flex items-center gap-1 text-xs font-bold text-brand-600 hover:text-brand-700">
                          <PlusCircle size={14} /> Add Row
                        </button>
                      </div>

                      <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-navy-700 max-h-72">
                        <table className="w-full text-xs border-collapse" style={{ minWidth: '1600px' }}>
                          <thead>
                            <tr className="bg-slate-100 dark:bg-navy-900 border-b border-slate-200 text-left">
                              <th className="px-3 py-2 text-slate-500 w-12 text-center">#</th>
                              {REQUIRED_COLS.map(col => <th key={col} className="px-3 py-2 text-slate-500 font-semibold">{COL_LABELS[col] || col}</th>)}
                              <th className="px-3 py-2 text-slate-500 w-16 text-center">Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {personParsedRows.map((row, rowIdx) => (
                              <tr key={rowIdx} className="border-b border-slate-100 hover:bg-slate-50/50">
                                <td className="px-3 py-2 text-slate-400 text-center font-mono">{rowIdx + 1}</td>
                                {REQUIRED_COLS.map(col => {
                                  const cellKey = `${rowIdx}-${col}`;
                                  const isEditing = personEditingCell?.row === rowIdx && personEditingCell?.col === col;
                                  return (
                                    <td key={col} className="px-2 py-1 border-r border-slate-50 cursor-pointer hover:bg-brand-50/20" onClick={() => setPersonEditingCell({ row: rowIdx, col })}>
                                      {isEditing ? (
                                        <input
                                          autoFocus
                                          value={row[col] || ''}
                                          onChange={e => {
                                            const val = e.target.value;
                                            setPersonParsedRows(prev => prev.map((r, i) => i === rowIdx ? { ...r, [col]: val } : r));
                                          }}
                                          onBlur={() => setPersonEditingCell(null)}
                                          onKeyDown={e => {if (e.key === 'Enter' || e.key === 'Escape') setPersonEditingCell(null)}}
                                          className="w-full border rounded px-1.5 py-0.5 text-xs outline-none focus:border-brand-500"
                                        />
                                      ) : (
                                        <span className="block min-h-[16px] truncate max-w-[140px] text-navy-900 dark:text-white">{row[col] || <span className="text-slate-350 italic">empty</span>}</span>
                                      )}
                                    </td>
                                  );
                                })}
                                <td className="px-3 py-2 text-center">
                                  <button type="button" onClick={() => setPersonParsedRows(prev => prev.filter((_, i) => i !== rowIdx))} className="text-rose-500 hover:text-rose-600"><Trash2 size={13}/></button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  <div className="flex justify-end gap-3 pt-5 border-t dark:border-navy-700 shrink-0">
                    <button type="button" onClick={() => setShowAddPersonModal(false)} className="rounded-xl border dark:border-navy-700 px-5 py-2.5 text-xs font-semibold hover:bg-slate-50 dark:text-white">Cancel</button>
                    <button type="submit" disabled={submittingPerson || !personParsedRows.length} className="rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white hover:bg-brand-600 disabled:opacity-70 flex items-center gap-1.5">
                      {submittingPerson && <Loader2 className="animate-spin" size={14}/>} Import Data
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 4. Edit Person Modal */}
      {editPerson && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-955/80 p-4 backdrop-blur-md" onClick={() => setEditPerson(null)}>
          <div className="w-full max-w-2xl rounded-2xl bg-white dark:bg-navy-800 shadow-2xl overflow-hidden border flex flex-col max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b p-5 bg-white dark:bg-navy-800">
              <div>
                <h3 className="text-base font-extrabold text-navy-900 dark:text-white">Edit Person Details</h3>
                <p className="text-xs text-slate-400 mt-1">Modify details for {editPerson.full_name}</p>
              </div>
              <button onClick={() => setEditPerson(null)} className="rounded-lg p-2 text-slate-400 hover:text-navy-950 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-navy-900 transition-colors">
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handlePersonEditSubmit} className="flex-1 overflow-y-auto p-5 space-y-4">
              {editPersonError && <div className="rounded-xl bg-rose-50 border border-rose-100 p-3 text-xs text-rose-600 font-semibold">{editPersonError}</div>}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">First Name</label><input value={editPersonForm.first_name} onChange={e=>setEditPersonForm({...editPersonForm, first_name: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" /></div>
                <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Last Name</label><input value={editPersonForm.last_name} onChange={e=>setEditPersonForm({...editPersonForm, last_name: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" /></div>
                <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Job Title</label><input value={editPersonForm.title} onChange={e=>setEditPersonForm({...editPersonForm, title: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" /></div>
                <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Organization</label><input value={editPersonForm.organization_name} onChange={e=>setEditPersonForm({...editPersonForm, organization_name: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" /></div>
                <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Email Address</label><input type="email" value={editPersonForm.email} onChange={e=>setEditPersonForm({...editPersonForm, email: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" /></div>
                <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Phone Number</label><input value={editPersonForm.phone} onChange={e=>setEditPersonForm({...editPersonForm, phone: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" /></div>
                <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">LinkedIn Profile URL</label><input value={editPersonForm.linkedin_url} onChange={e=>setEditPersonForm({...editPersonForm, linkedin_url: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" /></div>
                <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Seniority</label><select value={editPersonForm.seniority} onChange={e=>setEditPersonForm({...editPersonForm, seniority: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none"><option value="">Select Level</option><option value="Junior">Junior</option><option value="Mid">Mid Level</option><option value="Senior">Senior</option><option value="Director">Director / Executive</option></select></div>
                <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">City</label><input value={editPersonForm.city} onChange={e=>setEditPersonForm({...editPersonForm, city: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="City"/></div>
                <div><label className="block text-xs font-bold mb-1.5 text-slate-500 dark:text-slate-400">Country</label><input value={editPersonForm.country} onChange={e=>setEditPersonForm({...editPersonForm, country: e.target.value})} className="w-full text-xs rounded-xl border bg-slate-50 dark:bg-navy-900 dark:text-white border-slate-200 dark:border-navy-700 px-3.5 py-2.5 outline-none" placeholder="Country"/></div>
              </div>
              <div className="flex justify-end gap-3 pt-5 border-t dark:border-navy-700 shrink-0">
                <button type="button" onClick={() => setEditPerson(null)} className="rounded-xl border dark:border-navy-700 px-5 py-2.5 text-xs font-semibold hover:bg-slate-50 dark:text-white">Cancel</button>
                <button type="submit" disabled={isEditSubmitting} className="rounded-xl bg-brand-500 px-5 py-2.5 text-xs font-bold text-white hover:bg-brand-600 disabled:opacity-70 flex items-center gap-1.5">
                  {isEditSubmitting && <Loader2 className="animate-spin" size={14}/>} Save Changes
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 5. Delete Person Confirmation Modal */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/80 p-4 backdrop-blur-md" onClick={() => setDeleteTarget(null)}>
          <div className="w-full max-w-sm rounded-2xl bg-white dark:bg-navy-800 shadow-2xl p-5 border space-y-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-rose-50 text-rose-500 mx-auto"><AlertTriangle size={24} /></div>
            <div className="text-center space-y-2">
              <h3 className="text-base font-extrabold text-navy-900 dark:text-white">Delete Person?</h3>
              <p className="text-xs text-slate-400">Are you sure you want to permanently delete <strong>{deleteTarget.name}</strong>? This action cannot be undone.</p>
            </div>
            {deleteError && <div className="text-xs text-rose-500 text-center font-semibold">{deleteError}</div>}
            <div className="flex gap-3">
              <button type="button" onClick={() => setDeleteTarget(null)} className="flex-1 rounded-xl border py-2.5 text-xs font-semibold hover:bg-slate-50 dark:text-white">Cancel</button>
              <button type="button" onClick={handlePersonDeleteConfirm} disabled={isDeleting} className="flex-1 rounded-xl bg-rose-500 text-white py-2.5 text-xs font-bold hover:bg-rose-600 disabled:opacity-70 flex items-center justify-center gap-1.5">
                {isDeleting && <Loader2 className="animate-spin" size={14}/>} Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  // ──────────────────────────────────────────────────────────────────────────
  // Companies Table Sub-component
  // ──────────────────────────────────────────────────────────────────────────
  function CompaniesView() {
    const totalPages = Math.ceil(totalCompanies / LIMIT);
    return (
      <div className="space-y-4">
        {/* Filter controls */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-1 min-w-[280px] items-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 bg-slate-50 dark:bg-navy-800 px-3.5 py-2.5 text-xs">
            <Search size={14} className="text-slate-400" />
            <input
              value={compQuery}
              onChange={(e) => {
                const val = e.target.value;
                setCompQuery(val);
                if (matchCompanyDesc) setMatchCompanyDesc(false);
                if (debounceRef.current) clearTimeout(debounceRef.current);
                debounceRef.current = setTimeout(() => loadCompaniesList(val, 1), 400);
              }}
              placeholder="Search companies by name, UEI, or contact…"
              className="w-full bg-transparent outline-none placeholder:text-slate-400 dark:text-white"
            />
            {compQuery && <button onClick={() => { setCompQuery(''); setMatchCompanyDesc(false); }} className="rounded-full p-0.5 text-slate-400 hover:text-rose-500"><X size={12}/></button>}
          </div>

          <select value={compSizeFilter} onChange={e=>setCompSizeFilter(e.target.value)} className="rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3 py-2.5 text-xs font-semibold text-slate-600 dark:text-slate-300 outline-none cursor-pointer">
            <option value="All">All Sizes</option>
            <option value="Small">Small Business</option>
            <option value="Large">Large Business</option>
          </select>

          <select value={compNaicsFilter} onChange={e=>setCompNaicsFilter(e.target.value)} className="rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3 py-2.5 text-xs font-semibold text-slate-600 dark:text-slate-300 outline-none max-w-xs cursor-pointer truncate">
            <option value="All">All NAICS</option>
            {compNaicsCodes.map(code => <option key={code} value={code}>{code}</option>)}
          </select>

          <select value={compResearchedFilter} onChange={e=>setCompResearchedFilter(e.target.value)} className="rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3 py-2.5 text-xs font-semibold text-slate-600 dark:text-slate-300 outline-none cursor-pointer">
            <option value="All">All Research Status</option>
            <option value="Researched">Researched (AI Ready)</option>
            <option value="Not Researched">Not Researched</option>
          </select>
        </div>

        {/* Company matching bar */}
        <div className="flex flex-wrap items-center gap-3 pt-3 border-t border-slate-100 dark:border-navy-850">
          {entityOptions.length > 1 && (
            <select
              value={matchEntityId}
              onChange={(e) => {
                setMatchEntityId(e.target.value);
                if (matchCompanyDesc) {
                  const ent = entityOptions.find(opt => opt.id === e.target.value);
                  setCompQuery(ent?.description || '');
                }
              }}
              className="rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3 py-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300 outline-none cursor-pointer"
            >
              {entityOptions.map(ent => (
                <option key={ent.id} value={ent.id}>
                  {ent.name} {ent.isParent ? '(Main)' : '(Subsidiary)'}
                </option>
              ))}
            </select>
          )}

          <button
            onClick={() => {
              const entity = getSelectedEntity();
              if (!entity?.description) {
                alert("No profile description registered for the selected entity.");
                return;
              }
              const nextVal = !matchCompanyDesc;
              setMatchCompanyDesc(nextVal);
              setCompQuery(nextVal ? entity.description : '');
            }}
            className={`flex items-center gap-2 rounded-xl px-4 py-1.5 text-xs font-bold border transition-all ${
              matchCompanyDesc
                ? 'bg-brand-500 text-white border-brand-500 shadow-md shadow-brand-500/20'
                : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 dark:bg-navy-900 dark:text-slate-400 dark:border-navy-800'
            }`}
          >
            <SlidersHorizontal size={12} />
            Match {entityOptions.length > 1 ? getSelectedEntity()?.name : 'My Company'} Description
          </button>
        </div>

        {/* Table grid */}
        <div className="overflow-x-auto rounded-xl border border-slate-100 dark:border-navy-800">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-50 dark:bg-navy-800 border-b border-slate-100 dark:border-navy-700 text-left text-slate-400 uppercase tracking-wider text-[10px]">
                <th className="px-4 py-3 font-semibold">Company</th>
                <th className="px-4 py-3 font-semibold">UEI / CAGE</th>
                <th className="px-4 py-3 font-semibold">NAICS Sector</th>
                <th className="px-4 py-3 font-semibold">Location</th>
                <th className="px-4 py-3 font-semibold">Size</th>
                <th className="px-4 py-3 font-semibold">Match Score</th>
                <th className="px-4 py-3 font-semibold">Research</th>
                <th className="px-4 py-3 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody>
              {loadingCompanies ? (
                <tr><td colSpan={8} className="py-8 text-center text-slate-400"><Loader2 size={16} className="animate-spin mx-auto" /></td></tr>
              ) : companies.length === 0 ? (
                <tr><td colSpan={8} className="py-8 text-center text-slate-400">No companies found</td></tr>
              ) : companies.map(c => (
                <tr key={c.uei} className="border-b border-slate-50 dark:border-navy-850 hover:bg-slate-50/50 dark:hover:bg-navy-900/50">
                  <td className="px-4 py-3">
                    <Link to={`/companies/${c.uei}`} className="font-semibold text-navy-900 dark:text-white hover:text-brand-600">
                      {c.name || 'Unnamed Company'}
                    </Link>
                    {c.contact && <p className="text-[10px] text-slate-400">{c.contact}</p>}
                  </td>
                  <td className="px-4 py-3 font-mono text-slate-500">{c.uei || '—'}<br/><span className="text-[10px] text-slate-400">{c.cage_code}</span></td>
                  <td className="px-4 py-3 text-slate-500">{c.primary_naics || '—'}<p className="text-[10px] text-slate-400 truncate max-w-[130px]" title={c.primary_naics_desc}>{c.primary_naics_desc}</p></td>
                  <td className="px-4 py-3 text-slate-500">{renderSafeText(c.location || `${c.city || ''}, ${c.state || ''}`)}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex rounded-full px-2 py-0.5 text-[9px] font-bold ${c.size === 'Small' || c.size === 'S' ? 'bg-sky-50 text-sky-700' : 'bg-indigo-50 text-indigo-700'}`}>
                      {c.size === 'Small' || c.size === 'S' ? 'Small' : 'Large'}
                    </span>
                  </td>
                  <td className="px-4 py-3"><MatchBadge score={c.matchScore ?? c.match_score} /></td>
                  <td className="px-4 py-3">
                    {c.is_researched || c.hasResearchedProfile ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 text-emerald-700 px-2 py-0.5 font-semibold text-[10px]"><Check size={10}/> Researched</span>
                    ) : (
                      <span className="text-slate-400">Not Researched</span>
                    )}
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={c.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
            <span>Page {companiesPage} of {totalPages} ({totalCompanies} companies)</span>
            <div className="flex gap-1">
              <button disabled={companiesPage === 1} onClick={() => setCompaniesPage(p => p - 1)} className="rounded-lg border px-3 py-1.5 disabled:opacity-40 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-900">
                <ArrowUp size={12} className="rotate-[-90deg] dark:text-white" />
              </button>
              <button disabled={companiesPage === totalPages} onClick={() => setCompaniesPage(p => p + 1)} className="rounded-lg border px-3 py-1.5 disabled:opacity-40 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-900">
                <ArrowDown size={12} className="rotate-[-90deg] dark:text-white" />
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ──────────────────────────────────────────────────────────────────────────
  // People Table Sub-component
  // ──────────────────────────────────────────────────────────────────────────
  function PeopleView() {
    const totalPages = Math.ceil(totalPeople / LIMIT);
    return (
      <div className="space-y-4">
        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-1 min-w-[280px] items-center gap-2 rounded-xl border border-slate-200 dark:border-navy-700 bg-slate-50 dark:bg-navy-800 px-3.5 py-2.5 text-xs">
            <Search size={14} className="text-slate-400" />
            <input
              value={peopleQuery}
              onChange={(e) => {
                const val = e.target.value;
                setPeopleQuery(val);
                if (debounceRef.current) clearTimeout(debounceRef.current);
                debounceRef.current = setTimeout(() => loadPeopleList(val, 1), 400);
              }}
              placeholder="Search people by name, email, organization…"
              className="w-full bg-transparent outline-none placeholder:text-slate-400 dark:text-white"
            />
            {peopleQuery && <button onClick={() => setPeopleQuery('')} className="rounded-full p-0.5 text-slate-400 hover:text-rose-500"><X size={12}/></button>}
          </div>

          <select value={peopleStatusFilter} onChange={e=>setPeopleStatusFilter(e.target.value)} className="rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3 py-2.5 text-xs font-semibold text-slate-600 dark:text-slate-300 outline-none cursor-pointer">
            <option value="All">All Statuses</option>
            {STATUS_CHOICES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>

          <select value={peopleSourceFilter} onChange={e=>setPeopleSourceFilter(e.target.value)} className="rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3 py-2.5 text-xs font-semibold text-slate-600 dark:text-slate-300 outline-none cursor-pointer">
            <option value="All">All Sources</option>
            {(peopleSourceOptions.length ? peopleSourceOptions : SOURCE_CHOICES).map(s => <option key={s} value={s}>{s}</option>)}
          </select>

          <select value={peopleCountryFilter} onChange={e=>setPeopleCountryFilter(e.target.value)} className="rounded-xl border border-slate-200 dark:border-navy-700 bg-white dark:bg-navy-900 px-3 py-2.5 text-xs font-semibold text-slate-600 dark:text-slate-300 outline-none max-w-xs cursor-pointer truncate">
            <option value="All">All Countries</option>
            {peopleCountryOptions.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        {/* Table list */}
        <div className="overflow-x-auto rounded-xl border border-slate-100 dark:border-navy-800">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-50 dark:bg-navy-800 border-b border-slate-100 dark:border-navy-700 text-left text-slate-400 uppercase tracking-wider text-[10px]">
                <th className="px-4 py-3 font-semibold">Person</th>
                <th className="px-4 py-3 font-semibold">Organization</th>
                <th className="px-4 py-3 font-semibold">Contact</th>
                <th className="px-4 py-3 font-semibold">Location</th>
                <th className="px-4 py-3 font-semibold">Seniority</th>
                <th className="px-4 py-3 font-semibold">Source</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loadingPeople ? (
                <tr><td colSpan={8} className="py-8 text-center text-slate-400"><Loader2 size={16} className="animate-spin mx-auto" /></td></tr>
              ) : people.length === 0 ? (
                <tr><td colSpan={8} className="py-8 text-center text-slate-400">No people found</td></tr>
              ) : people.map(p => (
                <tr key={p.id} className="border-b border-slate-50 dark:border-navy-850 hover:bg-slate-50/50 dark:hover:bg-navy-900/50">
                  <td className="px-4 py-3">
                    <Link to={`/people/${p.id}`} className="font-semibold text-navy-900 dark:text-white hover:text-brand-600">
                      {p.full_name || 'Unnamed Person'}
                    </Link>
                    {p.title && <p className="text-[10px] text-slate-400">{p.title}</p>}
                  </td>
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{p.organization_name || '—'}</td>
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{p.email || '—'}<br/><span className="text-[10px] text-slate-400">{p.phone}</span></td>
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{renderSafeText(p.city && p.country ? `${p.city}, ${p.country}` : p.city || p.country)}</td>
                  <td className="px-4 py-3 text-slate-500 dark:text-slate-400">{p.seniority || '—'}</td>
                  <td className="px-4 py-3">
                    <span className="inline-flex rounded-full bg-slate-100 dark:bg-navy-800 px-2 py-0.5 font-semibold text-[10px] dark:text-slate-350">{p.source || '—'}</span>
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={p.status} /></td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <Link to={`/people/${p.id}`} className="text-slate-400 hover:text-brand-500" title="View"><Eye size={13}/></Link>
                      <button type="button" onClick={() => openPersonEdit(p)} className="text-slate-400 hover:text-amber-500" title="Edit"><Pencil size={13}/></button>
                      <button type="button" onClick={() => setDeleteTarget({ id: p.id, name: p.full_name || 'this contact' })} className="text-slate-400 hover:text-rose-500" title="Delete"><Trash2 size={13}/></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
            <span>Page {peoplePage} of {totalPages} ({totalPeople} people)</span>
            <div className="flex gap-1">
              <button disabled={peoplePage === 1} onClick={() => setPeoplePage(p => p - 1)} className="rounded-lg border px-3 py-1.5 disabled:opacity-40 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-900">
                <ArrowUp size={12} className="rotate-[-90deg] dark:text-white" />
              </button>
              <button disabled={peoplePage === totalPages} onClick={() => setPeoplePage(p => p + 1)} className="rounded-lg border px-3 py-1.5 disabled:opacity-40 hover:bg-slate-50 dark:border-navy-700 dark:bg-navy-900">
                <ArrowDown size={12} className="rotate-[-90deg] dark:text-white" />
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }
}
