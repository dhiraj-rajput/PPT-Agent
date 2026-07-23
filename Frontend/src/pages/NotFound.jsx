import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#F6F7FB] dark:bg-navy-950 px-6 text-center">
      <p className="text-6xl font-extrabold text-brand-500">404</p>
      <h1 className="mt-3 text-xl font-bold text-navy-900 dark:text-white">Page not found</h1>
      <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">The page you're looking for doesn't exist or has moved.</p>
      <Link to="/" className="mt-6 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-bold text-white shadow-soft">
        Back to Dashboard
      </Link>
    </div>
  );
}
