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
export function strengthColor(score) {
  if (score <= 1) return 'bg-rose-500';
  if (score === 2) return 'bg-orange-500';
  if (score === 3) return 'bg-yellow-500';
  if (score === 4) return 'bg-blue-500';
  return 'bg-emerald-500';
}
