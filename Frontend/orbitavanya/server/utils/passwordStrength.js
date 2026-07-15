// Mirrors src/lib/passwordStrength.js on the frontend. Kept as a separate
// file because the frontend and backend are separate npm projects, but the
// rules here must stay identical to the client-side ones.

const COMMON_PASSWORDS = new Set([
  'password', 'password1', 'password123', '12345678', '123456789',
  'qwerty123', 'qwertyuiop', 'letmein', 'welcome1', 'admin123',
  'iloveyou', 'football', 'monkey123', 'abc12345', '11111111',
  'passw0rd', 'sunshine', 'princess', 'dragon123', 'trustno1',
]);

export function checkPasswordRules(password = '') {
  const checks = {
    length: password.length >= 8,
    lower: /[a-z]/.test(password),
    upper: /[A-Z]/.test(password),
    number: /\d/.test(password),
    special: /[!@#$%^&*(),.?":{}|<>_\-+=[\]/\\~`;']/.test(password),
    notCommon: !COMMON_PASSWORDS.has(password.toLowerCase()),
  };

  const isStrong =
    checks.length && checks.lower && checks.upper && checks.number && checks.special && checks.notCommon;

  return { checks, isStrong };
}
