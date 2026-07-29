import { Check, X } from 'lucide-react';
import { checkPasswordRules, strengthLabel } from '../../lib/passwordStrength.jsx';

const getBarColor = (i, currentScore) => {
  if (i >= currentScore) return 'bg-slate-200';
  if (currentScore <= 1) return 'bg-rose-500';
  if (currentScore === 2) return 'bg-orange-500';
  if (currentScore === 3) return 'bg-yellow-500';
  if (currentScore === 4) return 'bg-blue-500';
  return 'bg-emerald-500';
};

export default function PasswordStrengthMeter({ password }) {
  const { checks, score } = checkPasswordRules(password);
  const label = strengthLabel(score);

  const rules = [
    { key: 'minLength', label: 'At least 8 characters' },
    { key: 'hasUppercase', label: 'One uppercase letter' },
    { key: 'hasLowercase', label: 'One lowercase letter' },
    { key: 'hasNumber', label: 'One number' },
    { key: 'hasSpecial', label: 'One special character' },
  ];

  if (!password) return null;

  return (
    <div className="mt-2">
      <div className="flex gap-1">
        {[0, 1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className={`h-1.5 flex-1 rounded-full ${getBarColor(i, score)}`}
          />
        ))}
      </div>
      <p className="mt-1 text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</p>
      <ul className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2">
        {rules.map((rule) => (
          <li key={rule.key} className="flex items-center gap-1.5 text-xs">
            {checks[rule.key] ? (
              <Check size={13} className="shrink-0 text-green-600" />
            ) : (
              <X size={13} className="shrink-0 text-slate-300" />
            )}
            <span className={checks[rule.key] ? 'text-slate-600' : 'text-slate-400'}>{rule.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
