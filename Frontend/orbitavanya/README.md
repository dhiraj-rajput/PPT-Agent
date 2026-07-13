# OrbitAvanya Tech — AI Tender Platform (Frontend Demo)

A React + Tailwind CSS frontend prototype of the OrbitAvanya AI Tender Platform, built to match the provided
dashboard design. **This is a frontend-only build with dummy/mock data** — no backend or database is wired up yet,
so you can plug in your own Node.js API later.

## Tech stack
- React 18 + Vite
- React Router v6 (client-side routing)
- Tailwind CSS (design tokens matched to the reference screenshot)
- Recharts (charts)
- lucide-react (icons)

All data lives in `src/data/*.js` as plain JS arrays — swap these out for real API calls when your backend is ready.

## Getting started

```bash
npm install
npm run dev
```

Then open http://localhost:5173

To build for production:
```bash
npm run build
npm run preview
```

## Pages included

| Route | Page |
|---|---|
| `/login` | Login |
| `/` | Dashboard (matches the reference screenshot) |
| `/companies` , `/companies/:id` | Companies list & detail |
| `/tenders` , `/tenders/:id` | Tenders list & detail |
| `/ai-research` | AI Research |
| `/proposal-builder` | Proposal Builder |
| `/email-campaign` | Email Campaign |
| `/crm-pipeline` | CRM Pipeline (kanban) |
| `/meetings` | Meetings |
| `/tasks` | Tasks |
| `/analytics` | Analytics |
| `/reports` | Reports |
| `/settings` | Settings |
| `/settings/users` | Users & Roles |
| `/settings/integrations` | Integrations |

## Project structure

```
src/
  components/
    layout/        Sidebar, Topbar, AI Copilot panel
    ui/             Shared PageHeader, Card, Badge components
  data/             Dummy data (companies, tenders, campaigns, etc.)
  layouts/          DashboardLayout (sidebar + topbar + outlet shell)
  pages/            One file per route
  App.jsx           Route definitions
  main.jsx          Entry point
```

## Connecting your Node.js backend later

Each page imports its data from `src/data/*.js`, e.g.:

```js
import { companies } from '../data/companies.js';
```

To wire up real data, replace these imports with `fetch`/`axios` calls (e.g. inside a `useEffect`) pointing at your
Node/Express API, keeping the same field names (`id`, `name`, `matchScore`, etc.) so the UI keeps working without
further changes. A typical pattern:

```js
const [companies, setCompanies] = useState([]);
useEffect(() => {
  fetch('/api/companies').then(r => r.json()).then(setCompanies);
}, []);
```

## Notes
- The Login page is a static form — submitting it just navigates to the dashboard (no real auth yet).
- The AI Copilot panel and quick actions are UI-only placeholders.
- Design tokens (colors, radius, shadows) are defined in `tailwind.config.js` under `theme.extend`.
