import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Mail, Phone, MapPin, Building2, Sparkles, FileText, Calendar } from 'lucide-react';
import { Card, MatchBadge, StatusBadge } from '../components/ui/Common.jsx';
import { companies } from '../data/companies.js';
import { tenders } from '../data/tenders.js';

export default function CompanyDetail() {
  const { id } = useParams();
  const company = companies.find((c) => String(c.id) === id) || companies[0];
  const matchedTenders = tenders.slice(0, 3);

  return (
    <div>
      <Link to="/companies" className="mb-4 flex w-fit items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-navy-900 dark:text-slate-400 dark:hover:text-white">
        <ArrowLeft size={15} /> Back to Companies
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-lg font-bold text-brand-600 dark:bg-navy-800 dark:text-brand-400">
            {company.name.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-navy-900 dark:text-white">{company.name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span>{company.industry}</span>·<span>{company.location}</span>·<StatusBadge status={company.status} />
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700">
            <Mail size={15} /> Email
          </button>
          <button className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft">
            <FileText size={15} /> Generate Proposal
          </button>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="flex flex-col gap-5 lg:col-span-2">
          <Card>
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Company Overview</h3>
            <div className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">Company Size</p>
                <p className="font-semibold text-navy-900 dark:text-white">{company.size}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">Annual Revenue</p>
                <p className="font-semibold text-navy-900 dark:text-white">{company.revenue}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">AI Match Score</p>
                <MatchBadge score={company.matchScore} />
              </div>
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">Primary Contact</p>
                <p className="font-semibold text-navy-900 dark:text-white">{company.contact}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">Email</p>
                <p className="font-semibold text-navy-900 dark:text-white">{company.email}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400 dark:text-slate-500">Location</p>
                <p className="font-semibold text-navy-900 dark:text-white">{company.location}</p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {company.tags.map((t) => (
                <span key={t} className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 dark:bg-navy-800 dark:text-slate-400">{t}</span>
              ))}
            </div>
          </Card>

          <Card>
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-brand-500" />
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">AI Insights</h3>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
              {company.name} shows strong alignment with federal and state IT modernization initiatives. Based on past award
              history and current capacity signals, this account has a high probability of responding favorably to outreach
              around cloud migration and AI integration services. Recommended next step: schedule a discovery call within
              the next 5 business days to capitalize on active budget cycles.
            </p>
          </Card>

          <Card>
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Matched Tenders</h3>
            <div className="mt-3 flex flex-col gap-3">
              {matchedTenders.map((t) => (
                <Link to={`/tenders/${t.id}`} key={t.id} className="flex items-center justify-between rounded-xl border border-slate-100 p-3 hover:border-brand-200 dark:border-navy-800 dark:hover:border-brand-500/50">
                  <div>
                    <p className="text-sm font-semibold text-navy-900 dark:text-white">{t.title}</p>
                    <p className="text-xs text-slate-400 dark:text-slate-500">{t.agency} · {t.value}</p>
                  </div>
                  <MatchBadge score={t.match} />
                </Link>
              ))}
            </div>
          </Card>
        </div>

        <div className="flex flex-col gap-5">
          <Card>
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Contact</h3>
            <div className="mt-3 flex flex-col gap-3 text-sm">
              <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300"><Mail size={15} className="text-slate-400 dark:text-slate-500" /> {company.email}</div>
              <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300"><Phone size={15} className="text-slate-400 dark:text-slate-500" /> +1 (555) 019-2833</div>
              <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300"><MapPin size={15} className="text-slate-400 dark:text-slate-500" /> {company.location}</div>
              <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300"><Building2 size={15} className="text-slate-400 dark:text-slate-500" /> {company.industry}</div>
            </div>
          </Card>

          <Card>
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Upcoming</h3>
            <div className="mt-3 flex items-start gap-3 rounded-xl border border-slate-100 p-3 dark:border-navy-800">
              <Calendar size={16} className="mt-0.5 text-brand-500" />
              <div>
                <p className="text-sm font-semibold text-navy-900 dark:text-white">Discovery Call</p>
                <p className="text-xs text-slate-400 dark:text-slate-500">Jun 15, 2026 · 10:00 AM</p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
