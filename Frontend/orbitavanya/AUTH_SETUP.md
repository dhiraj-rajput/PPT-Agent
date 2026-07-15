# Auth, 2FA & MongoDB — Setup Guide

This adds real authentication to the OrbitAvanya frontend:

- Register → Login → Email OTP (2FA) → Dashboard
- Passwords hashed with **bcrypt** (never stored in plaintext)
- OTP codes are also hashed before being stored, and expire after 10 minutes
- Sessions use JWT
- Data is stored in your existing MongoDB: `mongodb://127.0.0.1:27017/company_scraper`
  (in the `users` collection)
- 2FA codes are emailed via Gmail SMTP (nodemailer)

## What was added

```
server/                      ← new Node/Express auth API (separate from the React app)
  index.js
  models/User.js
  routes/auth.js
  middleware/auth.js
  utils/mailer.js
  utils/otp.js
  .env.example
  package.json

src/pages/Register.jsx       ← new
src/pages/VerifyOtp.jsx      ← new (handles both signup verification and login 2FA)
src/pages/Login.jsx          ← now calls the real API instead of a dummy submit
src/context/AuthContext.jsx  ← new, tracks the logged-in user + JWT
src/components/ProtectedRoute.jsx ← new, blocks the dashboard until you're signed in
src/lib/api.js               ← new, fetch wrapper for the auth API
src/App.jsx                  ← added /register and /verify-otp routes, dashboard now
                                 requires being signed in
.env.example                 ← new, frontend API URL
```

## 1. Start MongoDB

Make sure `mongod` is running locally on the default port (27017), same as your
scraper already uses.

## 2. Configure and run the backend

```bash
cd server
cp .env.example .env
npm install
```

Open `server/.env` and fill in:

- `JWT_SECRET` — generate one with:
  ```bash
  node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"
  ```
- `SMTP_PASS` — a Gmail **App Password**, not your normal Gmail password:
  1. Turn on 2-Step Verification: https://myaccount.google.com/security
  2. Create an App Password: https://myaccount.google.com/apppasswords
  3. Paste the 16-character code as `SMTP_PASS`

`SMTP_USER` is already set to `prasannadhamal982005@gmail.com` — change it if you
want a different sending address.

Then start the API:

```bash
npm start
```

You should see:

```
Connected to MongoDB: mongodb://127.0.0.1:27017/company_scraper
Auth server listening on http://localhost:5000
```

## 3. Configure and run the frontend

```bash
cp .env.example .env    # from the project root
npm install
npm run dev
```

`VITE_API_URL` defaults to `http://localhost:5000` — change it if your backend
runs somewhere else.

## 4. Try it

1. Go to `/register`, create an account → check your email for a 6-digit code.
2. Enter the code → you're logged in and redirected to the dashboard.
3. Log out (clear localStorage or add a logout button) and log back in via
   `/login` → you'll get a **second** email code (2FA) before you're let in.

## Security notes

- Passwords are hashed with bcrypt (12 salt rounds) — the database never sees
  a plaintext password.
- OTP codes are generated with a cryptographically secure RNG and stored only
  as a bcrypt hash, with a 10-minute expiry and a 5-attempt limit.
- Login failures return a generic "invalid email or password" message so the
  API can't be used to check which emails are registered.
- Auth endpoints are rate-limited (20 requests / 15 min / IP) to slow down
  brute-force attempts.
- `server/.env` is git-ignored — never commit real secrets to source control.
- The JWT is stored in `localStorage` on the frontend for simplicity. For
  production hardening, consider moving to an httpOnly cookie instead.
