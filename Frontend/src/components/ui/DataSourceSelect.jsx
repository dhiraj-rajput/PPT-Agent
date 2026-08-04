import React from "react";
import { Building2, Globe2, Layers } from "lucide-react";

export default function DataSourceSelect({ value, onChange, includeAll = true, className = "" }) {
  return (
    <div className={`inline-flex max-w-full overflow-x-auto scrollbar-none items-center space-x-1 p-1 bg-slate-100 dark:bg-slate-800/80 rounded-xl border border-slate-200 dark:border-slate-700/60 ${className}`}>
      {includeAll && (
        <button
          type="button"
          onClick={() => onChange("All")}
          className={`flex shrink-0 items-center gap-1.5 px-2.5 sm:px-3 py-1.5 text-[11px] sm:text-xs font-semibold rounded-lg transition-all ${
            value === "All" || !value
              ? "bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-sm border border-slate-200/80 dark:border-slate-700"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>All Sources</span>
        </button>
      )}

      <button
        type="button"
        onClick={() => onChange("SAM.gov")}
        className={`flex shrink-0 items-center gap-1.5 px-2.5 sm:px-3 py-1.5 text-[11px] sm:text-xs font-semibold rounded-lg transition-all ${
          value === "SAM.gov" || value === "sam_gov"
            ? "bg-white dark:bg-slate-900 text-blue-600 dark:text-blue-400 shadow-sm border border-slate-200/80 dark:border-slate-700"
            : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
        }`}
      >
        <Globe2 className="w-3.5 h-3.5 text-blue-500" />
        <span>SAM.gov (US)</span>
      </button>

      <button
        type="button"
        onClick={() => onChange("Companies House")}
        className={`flex shrink-0 items-center gap-1.5 px-2.5 sm:px-3 py-1.5 text-[11px] sm:text-xs font-semibold rounded-lg transition-all ${
          value === "Companies House" || value === "companies_house_uk" || value === "companies_house"
            ? "bg-white dark:bg-slate-900 text-emerald-600 dark:text-emerald-400 shadow-sm border border-slate-200/80 dark:border-slate-700"
            : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
        }`}
      >
        <Building2 className="w-3.5 h-3.5 text-emerald-500" />
        <span>Companies House (UK)</span>
      </button>
    </div>
  );
}
