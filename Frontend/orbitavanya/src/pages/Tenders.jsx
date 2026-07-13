import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, SlidersHorizontal, DollarSign, Calendar, Building2 } from 'lucide-react';
import { PageHeader, Card, MatchBadge, StatusBadge } from '../components/ui/Common.jsx';
import { tenders } from '../data/tenders.js';

export default function Tenders() {
  const [query, setQuery] = useState('');
  const filtered = tenders.filter((t) => t.title.toLowerCase().includes(query.toLowerCase()));

  return (
    <div>
      <PageHeader title="Tenders" subtitle={`${tenders.length} active tenders imported from SAM.gov`} />

      <Card className="!p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-1 min-w-[220px] items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 dark:border-navy-700 dark:bg-navy-800">
            <Search size={16} className="text-slate-400 dark:text-slate-500" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search tenders..."
              className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500 dark:text-white"
            />
          </div>
          <button className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-medium text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white dark:hover:bg-navy-700">
            <SlidersHorizontal size={15} /> Filters
          </button>
        </div>
      </Card>

      <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
        {filtered.map((t) => (
          <Link to={`/tenders/${t.id}`} key={t.id}>
            <Card className="h-full transition-shadow hover:shadow-soft dark:hover:border-brand-500/50">
              <div className="flex items-start justify-between gap-2">
                <span className="rounded-full bg-brand-50 px-2.5 py-1 text-[11px] font-semibold text-brand-600 dark:bg-navy-800 dark:text-brand-400">{t.category}</span>
                <MatchBadge score={t.match} />
              </div>
              <h3 className="mt-3 text-sm font-bold leading-snug text-navy-900 dark:text-white">{t.title}</h3>
              <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400 line-clamp-2">{t.description}</p>
              <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-slate-500 dark:text-slate-400">
                <span className="flex items-center gap-1"><Building2 size={13} /> {t.agency}</span>
                <span className="flex items-center gap-1"><DollarSign size={13} /> {t.value}</span>
                <span className="flex items-center gap-1"><Calendar size={13} /> {t.postedDate} → {t.closingDate}</span>
              </div>
              <div className="mt-3"><StatusBadge status={t.status} /></div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
