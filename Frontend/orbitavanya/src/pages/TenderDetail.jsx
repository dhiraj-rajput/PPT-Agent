import { useParams, Link } from 'react-router-dom';
import { useState } from 'react';
import { ArrowLeft, Building2, DollarSign, Calendar, Sparkles, FileEdit, Users, ExternalLink, Send, Check } from 'lucide-react';
import { Card, MatchBadge, StatusBadge } from '../components/ui/Common.jsx';
import { tenders, daysUntilClosing } from '../data/tenders.js';
import { companies } from '../data/companies.js';

export default function TenderDetail() {
  const { id } = useParams();
  const tender = tenders.find((t) => String(t.id) === id) || tenders[0];
  const suggestedCompanies = companies.slice(0, 3);
  const [draftRequested, setDraftRequested] = useState(false);
  const isClosed = tender.status === 'Closed' || daysUntilClosing(tender.closingDate) < 0;

  return (
    <div>
      <Link to="/tenders" className="mb-4 flex w-fit items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-navy-900 dark:text-slate-400 dark:hover:text-white">
        <ArrowLeft size={15} /> Back to Tenders
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <span className="rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-semibold text-brand-600 dark:bg-navy-800 dark:text-brand-400">{tender.category}</span>
          <h1 className="mt-3 max-w-2xl text-2xl font-extrabold text-navy-900 dark:text-white">{tender.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
            <span className="flex items-center gap-1.5"><Building2 size={14} /> {tender.agency}</span>
            <span className="flex items-center gap-1.5"><DollarSign size={14} /> {tender.value}</span>
            <span className="flex items-center gap-1.5"><Calendar size={14} /> {tender.postedDate} → Closes {tender.closingDate}</span>
            <StatusBadge status={tender.status} />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <MatchBadge score={tender.match} />
          <a
            href={tender.rfpUrl}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-bold text-navy-900 hover:bg-slate-50 dark:border-navy-700 dark:text-white dark:hover:bg-navy-800"
          >
            <ExternalLink size={15} /> View RFP
          </a>
          {!isClosed && (
            <button
              onClick={() => setDraftRequested(true)}
              disabled={draftRequested}
              className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft disabled:opacity-70"
            >
              {draftRequested ? <Check size={15} /> : <Send size={15} />}
              {draftRequested ? 'Draft Requested' : 'Ask for Project (Draft)'}
            </button>
          )}
          <Link to="/proposal-builder" className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft">
            <FileEdit size={15} /> Draft Proposal
          </Link>
        </div>
      </div>

      {draftRequested && (
        <div className="mt-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400">
          Draft request sent — a proposal writer will be assigned and a draft will be started in Proposal Builder shortly.
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="flex flex-col gap-5 lg:col-span-2">
          <Card>
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Overview</h3>
            <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-300">{tender.description}</p>
            <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
              Vendors must demonstrate prior experience delivering comparable solutions within regulated environments,
              provide a phased implementation timeline, and include a detailed risk mitigation plan as part of the technical
              volume. Past performance references from the last three years are required.
            </p>
          </Card>

          <Card>
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-brand-500" />
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">AI Analysis</h3>
            </div>
            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded-xl bg-emerald-50 p-3 dark:bg-emerald-950/30">
                <p className="text-xs text-emerald-700 dark:text-emerald-400">Win Probability</p>
                <p className="text-xl font-extrabold text-emerald-700 dark:text-emerald-400">74%</p>
              </div>
              <div className="rounded-xl bg-amber-50 p-3 dark:bg-amber-950/30">
                <p className="text-xs text-amber-700 dark:text-amber-400">Competition Level</p>
                <p className="text-xl font-extrabold text-amber-700 dark:text-amber-400">Medium</p>
              </div>
              <div className="rounded-xl bg-brand-50 p-3 dark:bg-navy-800">
                <p className="text-xs text-brand-700 dark:text-brand-400">Est. Effort</p>
                <p className="text-xl font-extrabold text-brand-700 dark:text-brand-400">6-8 wks</p>
              </div>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
              This opportunity closely matches your organization's past awards in this sector. Prioritize the technical
              volume around integration capabilities, since that's the area most cited in similar agency evaluations.
            </p>
          </Card>
        </div>

        <div className="flex flex-col gap-5">
          <Card>
            <div className="flex items-center gap-2">
              <Users size={16} className="text-slate-400" />
              <h3 className="text-sm font-bold text-navy-900 dark:text-white">Suggested Companies</h3>
            </div>
            <div className="mt-3 flex flex-col gap-3">
              {suggestedCompanies.map((c) => (
                <Link to={`/companies/${c.id}`} key={c.id} className="flex items-center justify-between rounded-xl border border-slate-100 p-3 hover:border-brand-200 dark:border-navy-800 dark:hover:border-brand-500/50">
                  <div>
                    <p className="text-sm font-semibold text-navy-900 dark:text-white">{c.name}</p>
                    <p className="text-xs text-slate-400 dark:text-slate-500">{c.industry}</p>
                  </div>
                  <MatchBadge score={c.matchScore} />
                </Link>
              ))}
            </div>
          </Card>

          <Card>
            <h3 className="text-sm font-bold text-navy-900 dark:text-white">Key Dates</h3>
            <div className="mt-3 flex flex-col gap-2 text-sm">
              <div className="flex justify-between"><span className="text-slate-400 dark:text-slate-500">Posted</span><span className="font-medium text-navy-900 dark:text-white">{tender.postedDate}</span></div>
              <div className="flex justify-between"><span className="text-slate-400 dark:text-slate-500">Q&A Deadline</span><span className="font-medium text-navy-900 dark:text-white">May 29, 2026</span></div>
              <div className="flex justify-between"><span className="text-slate-400 dark:text-slate-500">Closing Date</span><span className="font-medium text-navy-900 dark:text-white">{tender.closingDate}</span></div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
