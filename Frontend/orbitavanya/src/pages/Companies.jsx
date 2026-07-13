import { useState, useMemo, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Search, Plus, SlidersHorizontal, Eye, FileText, MoreHorizontal } from 'lucide-react';
import { PageHeader, Card, MatchBadge, StatusBadge } from '../components/ui/Common.jsx';
import { companies } from '../data/companies.js';

// Buckets the raw `size` range string (e.g. "1000-5000", "10000+") into a simple
// Large / Mid / Small / Other category for filtering.
function sizeCategory(size) {
  if (!size) return 'Other';
  const n = parseInt(String(size).replace(/[^0-9]/g, ''), 10);
  if (Number.isNaN(n)) return 'Other';
  if (n >= 5000) return 'Large';
  if (n >= 200) return 'Mid';
  if (n > 0) return 'Small';
  return 'Other';
}

export default function Companies() {
  const [query, setQuery] = useState('');
  const [industry, setIndustry] = useState('All');
  const [sizeFilter, setSizeFilter] = useState('All');
  const [allCompanies, setAllCompanies] = useState(companies);
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 20;

  useEffect(() => {
    fetch('/companies.json')
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load full dataset');
        return res.json();
      })
      .then((data) => {
        setAllCompanies(data);
      })
      .catch((err) => {
        console.warn("Could not load full companies.json, using fallback companies.js data.", err);
      });
  }, []);

  const industries = useMemo(() => {
    return ['All', ...new Set(allCompanies.map((c) => c.industry))];
  }, [allCompanies]);

  const filtered = useMemo(() => {
    return allCompanies.filter((c) => {
      const q = query.toLowerCase();
      const matchesQuery = 
        c.name.toLowerCase().includes(q) || 
        c.uei.toLowerCase().includes(q) || 
        c.contact.toLowerCase().includes(q);
      const matchesIndustry = industry === 'All' || c.industry === industry;
      const matchesSize = sizeFilter === 'All' || sizeCategory(c.size) === sizeFilter;
      return matchesQuery && matchesIndustry && matchesSize;
    });
  }, [allCompanies, query, industry, sizeFilter]);

  // Reset page when search or filter changes
  useEffect(() => {
    setCurrentPage(1);
  }, [query, industry, sizeFilter]);

  const pageCount = Math.ceil(filtered.length / itemsPerPage);
  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * itemsPerPage;
    return filtered.slice(start, start + itemsPerPage);
  }, [filtered, currentPage]);

  return (
    <div>
      <PageHeader
        title="Companies"
        subtitle={`${allCompanies.length.toLocaleString()} companies tracked across your pipeline`}
        action={
          <button className="flex items-center gap-2 rounded-xl bg-brand-500 px-4 py-2.5 text-sm font-bold text-white shadow-soft hover:bg-brand-600">
            <Plus size={16} /> Add Company
          </button>
        }
      />

      <Card className="!p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-1 min-w-[220px] items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 dark:border-navy-700 dark:bg-navy-800">
            <Search size={16} className="text-slate-400 dark:text-slate-500" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name, UEI or contact..."
              className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500 dark:text-white"
            />
          </div>
          <select
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white"
          >
            {industries.map((i) => <option key={i}>{i}</option>)}
          </select>
          <select
            value={sizeFilter}
            onChange={(e) => setSizeFilter(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white"
          >
            {['All', 'Large', 'Mid', 'Small', 'Other'].map((s) => (
              <option key={s} value={s}>{s === 'All' ? 'All Company Sizes' : `${s} Company`}</option>
            ))}
          </select>
          <button className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-medium text-navy-900 dark:border-navy-700 dark:bg-navy-800 dark:text-white">
            <SlidersHorizontal size={15} /> Filters
          </button>
        </div>
      </Card>

      <Card className="mt-5 !p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-[11px] uppercase tracking-wide text-slate-400 dark:border-navy-800 dark:text-slate-400">
                <th className="px-5 py-3 font-semibold">Company</th>
                <th className="px-5 py-3 font-semibold">Industry</th>
                <th className="px-5 py-3 font-semibold">Location</th>
                <th className="px-5 py-3 font-semibold">Size</th>
                <th className="px-5 py-3 font-semibold">Revenue</th>
                <th className="px-5 py-3 font-semibold">Match Score</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {paginatedData.map((c) => (
                <tr key={c.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50/60 dark:border-navy-800/40 dark:hover:bg-navy-800/40">
                  <td className="px-5 py-3.5">
                    <Link to={`/companies/${c.id}`} className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-xs font-bold text-brand-600 dark:bg-navy-800 dark:text-brand-400">
                        {c.name.slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <p className="font-semibold text-navy-900 hover:text-brand-600 dark:text-white dark:hover:text-brand-400 leading-tight">{c.name}</p>
                        <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">{c.contact}</p>
                      </div>
                    </Link>
                  </td>
                  <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{c.industry}</td>
                  <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{c.location}</td>
                  <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{sizeCategory(c.size)}</td>
                  <td className="px-5 py-3.5 text-slate-500 dark:text-slate-400">{c.revenue}</td>
                  <td className="px-5 py-3.5"><MatchBadge score={c.matchScore} /></td>
                  <td className="px-5 py-3.5"><StatusBadge status={c.status} /></td>
                  <td className="px-5 py-3.5">
                    <div className="flex items-center justify-end gap-1 text-slate-400 dark:text-slate-500">
                      <Link to={`/companies/${c.id}`} className="rounded-lg p-1.5 hover:bg-slate-100 dark:hover:bg-navy-800"><Eye size={14} /></Link>
                      <button className="rounded-lg p-1.5 hover:bg-slate-100 dark:hover:bg-navy-800"><FileText size={14} /></button>
                      <button className="rounded-lg p-1.5 hover:bg-slate-100 dark:hover:bg-navy-800"><MoreHorizontal size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-5 py-10 text-center text-slate-400 dark:text-slate-500">
                    No companies match your search.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls */}
        {pageCount > 1 && (
          <div className="flex items-center justify-between border-t border-slate-100 p-4 dark:border-navy-800">
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Showing <span className="font-semibold text-navy-900 dark:text-white">{(currentPage - 1) * itemsPerPage + 1}</span> to{' '}
              <span className="font-semibold text-navy-900 dark:text-white">
                {Math.min(currentPage * itemsPerPage, filtered.length)}
              </span>{' '}
              of <span className="font-semibold text-navy-900 dark:text-white">{filtered.length.toLocaleString()}</span> companies
            </p>
            <div className="flex gap-2">
              <button
                disabled={currentPage === 1}
                onClick={() => setCurrentPage((p) => p - 1)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 disabled:opacity-50 dark:border-navy-700 dark:text-white dark:hover:bg-navy-800"
              >
                Previous
              </button>
              <button
                disabled={currentPage === pageCount}
                onClick={() => setCurrentPage((p) => p + 1)}
                className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-navy-900 hover:bg-slate-50 disabled:opacity-50 dark:border-navy-700 dark:text-white dark:hover:bg-navy-800"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
