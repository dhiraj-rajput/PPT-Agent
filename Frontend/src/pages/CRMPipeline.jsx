import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, MoreHorizontal, Loader2, Building2, User, FileText, Calendar, Award } from 'lucide-react';
import { PageHeader, Card } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';

export default function CRMPipeline() {
  const navigate = useNavigate();
  const [pipelineData, setPipelineData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchPipeline = () => {
    setLoading(true);
    setError('');
    api.getCRMPipeline()
      .then((res) => {
        setPipelineData(res);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Error fetching CRM pipeline:', err);
        setError('Failed to load CRM pipeline data.');
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchPipeline();
  }, []);

  if (loading) {
    return (
      <div className="flex h-[70vh] flex-col items-center justify-center">
        <Loader2 className="animate-spin text-brand-500" size={36} />
        <p className="mt-4 text-sm text-slate-500 font-medium">Loading live pipeline states from DB...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-[50vh] flex-col items-center justify-center text-center p-4">
        <p className="text-sm font-semibold text-rose-600">{error}</p>
        <button 
          onClick={fetchPipeline} 
          className="mt-4 rounded-xl bg-brand-500 px-4 py-2 text-xs font-bold text-white shadow-soft"
        >
          Retry
        </button>
      </div>
    );
  }

  const columns = [
    { key: 'leads', label: 'Prospects', color: 'border-t-sky-400', items: pipelineData?.leads || [] },
    { key: 'contacted', label: 'Contacted', color: 'border-t-brand-400', items: pipelineData?.contacted || [] },
    { key: 'proposals', label: 'Proposals Generated', color: 'border-t-violet-400', items: pipelineData?.proposals || [] },
    { key: 'meetings', label: 'Meetings Booked', color: 'border-t-amber-400', items: pipelineData?.meetings || [] },
    { key: 'negotiation', label: 'In Negotiation', color: 'border-t-teal-400', items: pipelineData?.negotiation || [] },
    { key: 'won', label: 'Won Opportunities', color: 'border-t-emerald-400', items: pipelineData?.won || [] },
  ];

  return (
    <div>
      <PageHeader
        title="CRM Deal Pipeline"
        subtitle="Visual workflow tracking leads, outbound campaigns, and award statuses"
      />

      <div className="flex gap-3 overflow-x-auto pb-4 -mx-4 px-4 sm:mx-0 sm:gap-4 sm:px-0 snap-x snap-mandatory scroll-smooth [-webkit-overflow-scrolling:touch]">
        {columns.map((col) => (
          <div key={col.key} className="w-[82vw] max-w-[280px] shrink-0 snap-start sm:w-72 sm:max-w-none">
            <div className="mb-3 flex items-center justify-between px-1">
              <h3 className="truncate pr-2 text-sm font-bold text-navy-900 dark:text-white">{col.label}</h3>
              <span className="shrink-0 rounded-full bg-slate-100 dark:bg-navy-800 px-2 py-0.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
                {col.items.length}
              </span>
            </div>
            <div className={`flex flex-col gap-3 rounded-2xl border-t-4 ${col.color} bg-slate-50/60 dark:bg-navy-800/40 p-2 min-h-[400px]`}>
              {col.items.map((item) => {
                let title = '';
                let subtitle = '';
                let badgeText = '';
                let path = '';

                if (col.key === 'leads') {
                  title = item.name;
                  subtitle = item.industry || 'Prospect';
                  badgeText = item.matchScore ? `${item.matchScore}% Match` : 'No score';
                  path = `/companies/${item.uei || item.id}`;
                } else if (col.key === 'contacted' || col.key === 'negotiation') {
                  title = item.companyName || item.email;
                  subtitle = item.contactName || 'No Name';
                  badgeText = item.status ? item.status.toUpperCase() : 'CONTACTED';
                  path = '/email-campaign';
                } else if (col.key === 'proposals') {
                  title = item.title;
                  subtitle = item.company_name;
                  badgeText = item.proposal_type || 'PROPOSAL';
                  path = '/reports';
                } else if (col.key === 'meetings') {
                  title = item.title;
                  subtitle = `Host: ${item.host}`;
                  badgeText = item.startTime ? new Date(item.startTime).toLocaleDateString() : 'MEETING';
                  path = '/meetings';
                } else if (col.key === 'won') {
                  title = item.title;
                  subtitle = item.agency;
                  badgeText = item.value || 'AWARDED';
                  path = `/tenders/${item.id}`;
                }

                return (
                  <Card 
                    key={item.id} 
                    className="!p-3 cursor-pointer hover:shadow-soft transition-all"
                    onClick={() => path && navigate(path)}
                  >
                    <div className="flex items-start justify-between gap-1.5">
                      <p className="text-xs font-bold text-navy-900 dark:text-white line-clamp-2">{title}</p>
                    </div>
                    <p className="mt-1 text-[10px] text-slate-400 dark:text-slate-500 truncate">{subtitle}</p>
                    <div className="mt-2.5 flex items-center justify-between">
                      <span className="rounded bg-slate-100 dark:bg-navy-850 px-1.5 py-0.5 text-[9px] font-bold text-slate-600 dark:text-slate-300">
                        {badgeText}
                      </span>
                      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-50 text-brand-600 dark:bg-brand-500/10 dark:text-brand-400">
                        {col.key === 'leads' && <Building2 size={11} />}
                        {(col.key === 'contacted' || col.key === 'negotiation') && <User size={11} />}
                        {col.key === 'proposals' && <FileText size={11} />}
                        {col.key === 'meetings' && <Calendar size={11} />}
                        {col.key === 'won' && <Award size={11} />}
                      </div>
                    </div>
                  </Card>
                );
              })}
              {col.items.length === 0 && (
                <p className="py-8 text-center text-xs text-slate-400 dark:text-slate-500">No deals in this stage.</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
