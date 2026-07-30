import { useParams, Link } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { ArrowLeft, Mail, Phone, MapPin, Building2, Linkedin, Briefcase, Calendar, Loader2, AlertTriangle } from 'lucide-react';
import { Card, StatusBadge, renderSafeText } from '../components/ui/Common.jsx';
import { api } from '../lib/api.jsx';

function InfoRow({ icon: Icon, label, value, href }) {
  if (!value) return null;
  const content = (
    <div className="flex items-start gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-50 text-slate-400 dark:bg-navy-900">
        <Icon size={16} />
      </div>
      <div className="min-w-0">
        <p className="text-[11px] uppercase tracking-wide text-slate-400 font-semibold">{label}</p>
        <p className="text-sm font-semibold text-navy-900 dark:text-white break-words">{value}</p>
      </div>
    </div>
  );
  return href ? <a href={href} target="_blank" rel="noreferrer" className="hover:opacity-80 transition-opacity">{content}</a> : content;
}

export default function PersonDetail() {
  const { id } = useParams();
  const [person, setPerson] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.getPerson(id)
      .then((data) => setPerson(data))
      .catch((err) => setError(err.message || 'Failed to load contact'))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <Card className="flex flex-col items-center justify-center py-24">
        <Loader2 className="animate-spin text-brand-500" size={32} />
        <p className="mt-4 text-sm text-slate-500 dark:text-slate-400 font-medium">Loading contact...</p>
      </Card>
    );
  }

  if (error || !person) {
    return (
      <Card className="flex flex-col items-center justify-center py-24 text-center">
        <AlertTriangle className="text-amber-500 mb-3" size={32} />
        <p className="text-sm font-semibold text-navy-900 dark:text-white">Couldn't load this contact</p>
        <p className="text-xs text-slate-400 mt-1">{error || 'Contact not found'}</p>
        <Link to="/people" className="mt-4 inline-flex items-center gap-1.5 text-xs font-bold text-brand-600 dark:text-brand-400 hover:underline">
          <ArrowLeft size={14} /> Back to People
        </Link>
      </Card>
    );
  }

  const location = [person.city, person.state, person.country].filter(Boolean).join(', ');

  return (
    <div className="space-y-5">
      <Link to="/people" className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-500 hover:text-brand-600 dark:text-slate-400 dark:hover:text-brand-400">
        <ArrowLeft size={14} /> Back to People
      </Link>

      {/* Header Card */}
      <Card className="!p-6">
        <div className="flex flex-col sm:flex-row sm:items-center gap-4 justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-brand-50 text-lg font-bold text-brand-600 dark:bg-navy-900 dark:text-brand-400">
              {(person.full_name || '??').slice(0, 2).toUpperCase()}
            </div>
            <div>
              <h1 className="text-xl font-extrabold text-navy-900 dark:text-white">{person.full_name || 'Unnamed Contact'}</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
                {renderSafeText(person.title)}{person.organization_name ? ` · ${person.organization_name}` : ''}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={person.status} />
            <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-semibold text-slate-600 dark:bg-navy-800 dark:text-slate-300">
              {person.source || 'Manual Entry'}
            </span>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Contact Info */}
        <Card className="!p-6 space-y-5">
          <h2 className="text-sm font-extrabold text-navy-900 dark:text-white uppercase tracking-wide">Contact Details</h2>
          <InfoRow icon={Mail} label="Email" value={person.email} href={person.email ? `mailto:${person.email}` : undefined} />
          <InfoRow icon={Phone} label="Phone" value={person.phone} href={person.phone ? `tel:${person.phone}` : undefined} />
          <InfoRow icon={Linkedin} label="LinkedIn" value={person.linkedin_url ? 'View Profile' : ''} href={person.linkedin_url} />
          <InfoRow icon={MapPin} label="Location" value={location} />
          {person.email_status && (
            <div className="pt-3 border-t border-slate-100 dark:border-navy-800 text-xs text-slate-500 dark:text-slate-400">
              Email verification: <span className="font-semibold text-navy-900 dark:text-white">{person.email_status}</span>
              {person.email_confidence != null && ` (${Math.round(person.email_confidence * 100)}% confidence)`}
            </div>
          )}
        </Card>

        {/* Professional Info */}
        <Card className="!p-6 space-y-5">
          <h2 className="text-sm font-extrabold text-navy-900 dark:text-white uppercase tracking-wide">Professional Details</h2>
          <InfoRow icon={Building2} label="Organization" value={person.organization_name} />
          <InfoRow icon={Briefcase} label="Function" value={person.function_name} />
          <InfoRow icon={Briefcase} label="Seniority" value={person.seniority} />
          <InfoRow icon={Calendar} label="Job Start Date" value={person.job_start_date ? new Date(person.job_start_date).toLocaleDateString() : ''} />
        </Card>
      </div>
    </div>
  );
}
