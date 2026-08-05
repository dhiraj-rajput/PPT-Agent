/**
 * src/lib/passwordStrength.jsx
 * ----------------------------
 * Client-side password strength checker.
 * Mirrors the Node.js server/utils/passwordStrength.jsx logic for
 * consistent validation between client and server.
 */

/**
 * Returns an object describing password strength.
 * @param {string} password
 * @returns {{ isStrong: boolean, score: number, checks: object }}
 */
export function checkPasswordRules(password) {
  const checks = {
    minLength: password.length >= 8,
    hasUppercase: /[A-Z]/.test(password),
    hasLowercase: /[a-z]/.test(password),
    hasNumber: /\d/.test(password),
    hasSpecial: /[^A-Za-z0-9]/.test(password),
  };

  const score = Object.values(checks).filter(Boolean).length;
  const isStrong = score === 5;

  return { isStrong, score, checks };
}

/**
 * Returns a human-readable label for the strength score.
 * @param {number} score
 * @returns {string}
 */
export function strengthLabel(score) {
  if (score <= 1) return 'Very Weak';
  if (score === 2) return 'Weak';
  if (score === 3) return 'Fair';
  if (score === 4) return 'Good';
  return 'Strong';
}

/**
 * Returns a CSS color class (Tailwind) for the strength indicator bar.
 * @param {number} score
 * @returns {string}
 */
import { Check, X } from 'lucide-react';

const STRENGTH_BAR_COLORS = {
  'Very Weak': 'bg-tomato-500',
  Weak: 'bg-orange-400',
  Fair: 'bg-yellow-400',
  Good: 'bg-blue-400',
  Strong: 'bg-green-500',
};

export function PasswordStrengthMeter({ password }) {
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
            className={`h-1.5 flex-1 rounded-full ${
              i < score ? STRENGTH_BAR_COLORS[label] || 'bg-slate-200' : 'bg-slate-200'
            }`}
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
