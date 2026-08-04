# Companies House API — Master Reference

> Source: https://developer.company-information.service.gov.uk/ and https://developer-specs.company-information.service.gov.uk/
> Compiled: August 2026. This document is written to be handed to an AI assistant (or a developer) as complete working context for building an integration against the Companies House API — no prior knowledge of the API assumed.

---

## 1. What this API is

The Companies House API is a **REST** API run by Companies House, the UK's registrar of companies. It gives programmatic read access to the UK public company register (and, for authorised clients, the ability to file/change certain data). It replaced an older XML-RPC style interface.

- **Style:** REST — each resource has a unique URL; standard HTTP verbs (`GET`, `POST`, `PUT`, `DELETE`) act on it, same as submitting a web form.
- **Format:** All request/response bodies are **JSON**.
- **Spec format:** Every product is documented as an **OpenAPI (Swagger 2.0)** spec.
- **Client responsibilities:** JSON field order is not guaranteed stable, and new fields can appear over time — parse by key name, tolerate unknown fields, never rely on position.

```
GET  /company/{companyNumber}        → read a resource
POST /company/{companyNumber}        → create/modify (JSON body)
PUT  /company/{companyNumber}        → replace a resource
DELETE /company/{companyNumber}      → remove a resource
```

---

## 2. The seven API products

| Product | Purpose | Auth needed | Base path prefix |
|---|---|---|---|
| **Public Data API** | Read-only search & retrieval of public company data (profiles, officers, filings, PSC, charges, insolvency, search) | API key (Basic) | `https://api.company-information.service.gov.uk` |
| **Streaming API** | Real-time feed of register changes | Stream key (Basic) | `https://stream.company-information.service.gov.uk` |
| **Document API** | Filing-history document metadata + binary/PDF downloads | API key (Basic) or OAuth | `https://document-api.company-information.service.gov.uk` |
| **Manipulate Company Data (Filing API)** | Write access — file changes (e.g. registered office address, confirmation statement) via transactions | OAuth 2.0 Bearer token | via the Transactions API |
| **Companies House Identity Service** | Underlying OAuth 2.0 identity/authentication service | — | `identity.company-information.service.gov.uk` |
| **Discrepancies API** | For Obliged Entities only — report PSC discrepancies | OAuth 2.0 | — |
| **Sandbox Test Data Generator API** | Sandbox-only — create/delete disposable test companies & users on demand | API key (sandbox) | `test-data-sandbox.company-information.service.gov.uk` |

**For a read-only data-extraction / ingestion pipeline (e.g. into MongoDB), only the Public Data API (and optionally the Streaming API for real-time updates) is needed. Both authenticate with a plain API/stream key — no OAuth required.**

---

## 3. Authentication

### 3.1 API key / stream key — HTTP Basic Auth (used by Public Data API & Streaming API)

The key is sent as the **username**; the password is **left blank**.

```bash
curl -XGET -u my_api_key: https://api.company-information.service.gov.uk/company/00000006
```

Raw HTTP:
```
GET /company/00000006 HTTP/1.1
Host: api.company-information.service.gov.uk
Authorization: Basic <base64(my_api_key:)>
```
> Note the trailing colon after the key — it tells the client there is no password.

### 3.2 OAuth 2.0 — HTTP Bearer Auth (used by Filing/write APIs & Discrepancies API)

**Setup (once per app):**
1. Register an application in the developer portal.
2. Create a *web client* to get a `client_id` + `client_secret`. Store these securely (env vars, not source).

**Authorization Code flow:**
1. Redirect the user's browser to `/oauth2/authorise` with `client_id`, requested `scope`, and a registered `redirect_uri`. If a scope targets a specific company, the user must also supply that company's authentication code.
2. User signs in and grants permission.
3. User is redirected back to `redirect_uri` with a one-time `code`.
4. Server-to-server (not via browser) `POST` to `/oauth/token` with `code`, `client_id`, `client_secret`, `grant_type=authorization_code` → response contains `access_token` + `refresh_token`.
5. Use the access token as `Authorization: Bearer <token>` on subsequent calls.

**Verify a token:** `POST /oauth/verify` directly (server-to-server).

**Refresh an expired token:** `POST /oauth/token` again with `grant_type=refresh_token` and the stored `refresh_token`.

```bash
curl -XGET -H "Authorization: Bearer my_access_token" \
  https://api.company-information.service.gov.uk/company/00000006
```

Companies House publishes an example OAuth test-harness app on GitHub with a setup README.

### 3.3 API client types

| Client type | Auth style | Use |
|---|---|---|
| API key | Basic | Public GET requests (profile, officers, filings, PSC, etc.) |
| Stream key | Basic | Streaming API connections |
| OAuth web client | Bearer (OAuth 2.0) | Filing/write operations, user-authorised access |

---

## 4. Rate limits & developer guidelines

- **600 requests per rolling 5-minute window** per key.
- Exceeding it → `HTTP 429 Too Many Requests` for the rest of the window; resets automatically after 5 minutes.
- Higher limits available on request (contact Companies House).
- Apps that repeatedly exceed/bypass limits may be **banned without notice** — implement backoff/retry on 429s.
- API is **TLS-only** (TLS 1.2 recommended minimum).
- **Enumerated types:** many response fields reference coded enum values rather than embedding text, so the API stays self-documenting; the enum-to-text mapping tables are published on GitHub, grouped into classes. (A future enhancement may expose these as endpoints with ETag-based change checking.)

### API key security checklist
- Never embed keys in code.
- Never commit keys inside the source tree (even config/env files) — keep them out of version control.
- Restrict key usage by IP/domain where possible.
- Regenerate keys regularly, including on every release.
- Delete unused keys from the developer portal.

---

## 5. Environments

| Environment | Base URL | Notes |
|---|---|---|
| **Live** | `https://api.company-information.service.gov.uk` | Real data, real users. Runs every API except the test data generator. |
| **Sandbox** | `https://api-sandbox.company-information.service.gov.uk` | Safe for OAuth/filing integration testing. Streaming & Document APIs unavailable; Search responds with live data (processing limitation). No browser-based UI for sandbox data. |
| Sandbox identity service | `https://identity-sandbox.company-information.service.gov.uk` | |
| Sandbox test data generator | `https://test-data-sandbox.company-information.service.gov.uk` | Sandbox-only |

- Public **read-only** endpoints (company data, search, streaming) can be tested against **either** live or sandbox.
- **Filing** endpoints (POST/PUT/PATCH, OAuth-protected) should **only** be tested in sandbox — a successful live test would actually change the public register.
- Sandbox filing test workflow:
  1. Create a test company via the Test Data Generator API → note the returned `company_number` and `authentication_code` (code is unrecoverable later — store it if reusing the company).
  2. Read the company profile from the sandbox API to confirm it exists.
  3. Complete OAuth using a sandbox user + the test company's auth code → get an access token.
  4. Create a filing/transaction via the Transactions API using that token.
  5. Submit the transaction.
  6. Poll the transaction for the (mocked) status update; handle accepted/rejected.
  - A test company can be reused or deleted via a separate Test Data Generator endpoint; sandbox users can be reused too.
- Swap API keys / OAuth client credentials for their sandbox-registered counterparts when pointing at sandbox — live and sandbox credentials are not interchangeable.

---

## 6. Public Data API — full endpoint reference

Base URL: `https://api.company-information.service.gov.uk`
Auth: API key, HTTP Basic (`-u API_KEY:`)
All responses: JSON, with an `ETag` header on most resources.

### 6.1 Company profile

| Method | Path | Description |
|---|---|---|
| GET | `/company/{company_number}` | Basic company information |

**Path params:** `company_number` (string, required)
**Response resource:** `companyProfile` — includes company name, status, type, incorporation date, registered office address, SIC codes, accounts/confirmation-statement dates, etc.
**Errors:** 401 Unauthorised, 404 Not Found

### 6.2 Registered office address

| Method | Path | Description |
|---|---|---|
| GET | `/company/{companyNumber}/registered-office-address` | Registered office address only |

**Path params:** `companyNumber` (string, required)

### 6.3 Search

| Method | Path | Description |
|---|---|---|
| GET | `/search` | Search across companies, officers, and disqualified officers combined |
| GET | `/search/companies` | Search companies only |
| GET | `/search/officers` | Search company officers |
| GET | `/search/disqualified-officers` | Search disqualified officers |
| GET | `/alphabetical-search/companies` | Alphabetical company name search (typeahead-style) |
| GET | `/dissolved-search/companies` | Search dissolved companies |
| GET | `/advanced-search/companies` | Advanced multi-filter company search |

**`/search`, `/search/companies`, `/search/officers`, `/search/disqualified-officers`** — query params:
| Param | Type | Required | Description |
|---|---|---|---|
| `q` | string | Yes | Search term |
| `items_per_page` | integer | No | Results per page |
| `start_index` | integer | No | Index of first result |
| `restrictions` *(companies only)* | string | No | Space-separated restriction flags, e.g. `active-companies legally-equivalent-company-name` for a name-availability check |

**`/alphabetical-search/companies`** — query params:
| Param | Type | Required | Description |
|---|---|---|---|
| `q` | string | Yes | Company name being searched |
| `search_above` | string | No | `ordered_alpha_key_with_id` cursor for paging |
| `search_below` | string | No | `ordered_alpha_key_with_id` cursor for paging |
| `size` | string | No | Max results, 1–100 |

422 returned if `size` is out of range.

**`/advanced-search/companies`** — query params:
| Param | Type | Description |
|---|---|---|
| `company_name_includes` | string | Name-includes filter |
| `company_name_excludes` | string | Name-excludes filter |
| `company_status` | list | Comma-delimited or repeated key, e.g. `company_status=active&company_status=dissolved` |
| `company_subtype` | string | Comma-delimited list |
| `company_type` | list | Comma-delimited or repeated key |
| `dissolved_from` / `dissolved_to` | date | Dissolution date range |
| `incorporated_from` / `incorporated_to` | date | Incorporation date range |
| `location` | string | Location filter |
| `sic_codes` | list | Comma-delimited or repeated key |
| `size` | string | Max results, 1–5000 |
| `start_index` | string | Paging offset |

### 6.4 Officers

| Method | Path | Description |
|---|---|---|
| GET | `/company/{company_number}/officers` | List all officers of a company |
| GET | `/company/{company_number}/appointments/{appointment_id}` | Get one officer appointment |

**List officers — query params:**
| Param | Type | Description |
|---|---|---|
| `items_per_page` | integer | Results per page |
| `start_index` | integer | Paging offset |
| `order_by` | string | `appointed_on` \| `resigned_on` \| `surname` |
| `register_type` | string | `directors` \| `secretaries` \| `llp_members` — only applies when `register_view=true` |
| `register_view` | string (`true`/`false`) | If the register is held at Companies House and this is `true` with a valid `register_type`, only active officers on that register are returned. Default `false`. |

### 6.5 Officer appointments (cross-company)

| Method | Path | Description |
|---|---|---|
| GET | `/officers/{officer_id}/appointments` | All appointments held by one officer, across companies |

**Query params:**
| Param | Type | Description |
|---|---|---|
| `filter` | string | `active` → only active appointments |
| `items_per_page` | integer | Results per page |
| `start_index` | integer | Paging offset (0-based) |

### 6.6 Officer disqualifications

| Method | Path | Description |
|---|---|---|
| GET | `/disqualified-officers/natural/{officer_id}` | Disqualification record for a natural (human) officer |
| GET | `/disqualified-officers/corporate/{officer_id}` | Disqualification record for a corporate officer |

### 6.7 Registers

| Method | Path | Description |
|---|---|---|
| GET | `/company/{company_number}/registers` | Which statutory registers (directors, PSC, etc.) the company holds at Companies House vs. elsewhere |

### 6.8 Charges (mortgages/security interests)

| Method | Path | Description |
|---|---|---|
| GET | `/company/{company_number}/charges` | List all charges for a company |
| GET | `/company/{company_number}/charges/{charge_id}` | Get one charge |

### 6.9 Filing history

| Method | Path | Description |
|---|---|---|
| GET | `/company/{company_number}/filing-history` | List filing history items |
| GET | `/company/{company_number}/filing-history/{transaction_id}` | Get one filing history item |

**List — query params:**
| Param | Type | Description |
|---|---|---|
| `category` | string | Comma-separated categories to filter by (inclusive) |
| `items_per_page` | integer | Results per page |
| `start_index` | integer | Paging offset |

404 if no filing history is available for the company.

### 6.10 Insolvency

| Method | Path | Description |
|---|---|---|
| GET | `/company/{company_number}/insolvency` | Insolvency case details |

### 6.11 Exemptions

| Method | Path | Description |
|---|---|---|
| GET | `/company/{company_number}/exemptions` | Exemptions the company holds (e.g. from keeping a PSC register) |

### 6.12 UK Establishments

| Method | Path | Description |
|---|---|---|
| GET | `/company/{company_number}/uk-establishments` | UK establishments of an overseas company |

### 6.13 Persons with Significant Control (PSC)

| Method | Path | Description |
|---|---|---|
| GET | `/company/{company_number}/persons-with-significant-control` | List all PSCs |
| GET | `/company/{company_number}/persons-with-significant-control/individual/{notification_id}` | Get an individual PSC |
| GET | `/company/{company_number}/persons-with-significant-control/individual-beneficial-owner/{notification_id}` | Get an individual beneficial owner |
| GET | `/company/{company_number}/persons-with-significant-control/corporate-entity/{notification_id}` | Get a corporate-entity PSC |
| GET | `/company/{company_number}/persons-with-significant-control/corporate-entity-beneficial-owner/{notification_id}` | Get a corporate-entity beneficial owner |
| GET | `/company/{company_number}/persons-with-significant-control/legal-person/{notification_id}` | Get a legal-person PSC |
| GET | `/company/{company_number}/persons-with-significant-control/legal-person-beneficial-owner/{notification_id}` | Get a legal-person beneficial owner |
| GET | `/company/{company_number}/persons-with-significant-control/super-secure/{super_secure_id}` | Get a "super secure" PSC (protected details) |
| GET | `/company/{company_number}/persons-with-significant-control/super-secure-beneficial-owner/{super_secure_id}` | Get a "super secure" beneficial owner |
| GET | `/company/{company_number}/persons-with-significant-control-statements` | List PSC statements (e.g. "no PSCs to report") |
| GET | `/company/{company_number}/persons-with-significant-control-statements/{statement_id}` | Get one PSC statement |
| GET | `/company/{company_number}/persons-with-significant-control/{psc_id}/notifications` | List notifications for a specific PSC (change history) |

**List PSCs — query params:**
| Param | Type | Description |
|---|---|---|
| `items_per_page` | string | Results per page |
| `start_index` | string | Paging offset |
| `register_view` | string (`true`/`false`) | If the register is held at Companies House and this is `true`, only active/recently-terminated PSCs are shown. Default `false`. |

### 6.14 Common response headers & status codes (Public Data API)

| Status | Meaning |
|---|---|
| 200 | OK — resource returned (usually with `ETag` header) |
| 400 | Bad Request |
| 401 | Unauthorized — bad/missing API key |
| 404 | Not Found |
| 422 | Unprocessable — e.g. invalid `size` param |
| 429 | Too Many Requests — rate limit exceeded |

---

## 7. Streaming API — full endpoint reference

Base concept: long-lived HTTP connections that push newline-delimited JSON events as the register changes. Auth via **stream key**, HTTP Basic, same pattern as the Public Data API key.

| Method | Path | Stream contents |
|---|---|---|
| GET | `/companies` | Basic company information changes |
| GET | `/filings` | Company filing history changes |
| GET | `/insolvency-cases` | Insolvency case changes |
| GET | `/charges` | Charges changes |
| GET | `/officers` | Officer changes |
| GET | `/persons-with-significant-control` | PSC changes |
| GET | `/disqualified-officers` | Disqualified officer changes |
| GET | `/company-exemptions` | Company exemption changes |
| GET | `/persons-with-significant-control-statements` | PSC statement changes |

Base host: `https://stream.company-information.service.gov.uk` (streaming endpoints are not available in sandbox).

---

## 8. Document API — full endpoint reference

Used to fetch filing document metadata and the actual scanned/filed documents (PDF/etc.) referenced from filing-history items.

| Method | Path | Description |
|---|---|---|
| GET | `/document/{document_id}` | Fetch a document's metadata |
| GET | `/document/{document_id}/content` | Fetch/download the document itself |

`document_id` is obtained from a filing-history item's `links.document_metadata` field.

---

## 9. Manipulate Company Data (Filing API)

Write access to change company data (e.g. registered office address, confirmation statement), authorised via **OAuth 2.0 Bearer token** (see §3.2), operating through a **Transactions API** pattern:

1. Open a transaction.
2. Submit the relevant filing resource(s) against that transaction.
3. Submit/close the transaction.
4. Poll the transaction for a status update (accepted/rejected).

This product should only be tested against the **sandbox** environment (see §5) since successful live submissions genuinely change the public register.

---

## 10. Companies House Identity Service

The underlying identity/authentication service behind the OAuth 2.0 flow described in §3.2 (`/oauth2/authorise`, `/oauth/token`, `/oauth/verify`). Not typically called directly beyond that flow.

---

## 11. Discrepancies API

For **Obliged Entities only** (regulated firms with AML obligations) to report discrepancies found in PSC data versus their own due-diligence records. Requires OAuth 2.0 authorisation.

---

## 12. Sandbox Test Data Generator API

Sandbox-only. Creates/deletes disposable test companies (and returns a `company_number` + `authentication_code`) and test users, for exercising OAuth/filing flows safely. See the sandbox workflow in §5.

---

## 13. Creating an application & getting credentials

**Create an application:**
1. Sign in to the developer portal.
2. Name + describe the application.
3. Choose **Test** (sandbox) or **Live** (production).
4. Optionally add privacy-policy and T&C URLs.
5. Create.

**Create an API client (key) for that application:**
1. Open the application overview.
2. Select the application (or create one).
3. "Create new key" → name it, choose client type (API key / stream key / OAuth web client).
4. Create → credentials generated.

---

## 14. Quick-reference cheat sheet

```
Base (live):        https://api.company-information.service.gov.uk
Base (sandbox):     https://api-sandbox.company-information.service.gov.uk
Base (streaming):   https://stream.company-information.service.gov.uk
Base (documents):   https://document-api.company-information.service.gov.uk

Auth (read):   HTTP Basic — username = API key, password = blank
Auth (write):  HTTP Bearer — OAuth 2.0 access token

Rate limit:    600 requests / 5 minutes → 429 if exceeded

Core read endpoints (company_number-scoped):
  GET /company/{company_number}
  GET /company/{company_number}/registered-office-address
  GET /company/{company_number}/officers
  GET /company/{company_number}/appointments/{appointment_id}
  GET /company/{company_number}/registers
  GET /company/{company_number}/charges[/{charge_id}]
  GET /company/{company_number}/filing-history[/{transaction_id}]
  GET /company/{company_number}/insolvency
  GET /company/{company_number}/exemptions
  GET /company/{company_number}/uk-establishments
  GET /company/{company_number}/persons-with-significant-control[...]
  GET /company/{company_number}/persons-with-significant-control-statements[...]

Cross-entity endpoints:
  GET /officers/{officer_id}/appointments
  GET /disqualified-officers/natural/{officer_id}
  GET /disqualified-officers/corporate/{officer_id}

Search endpoints:
  GET /search
  GET /search/companies
  GET /search/officers
  GET /search/disqualified-officers
  GET /alphabetical-search/companies
  GET /dissolved-search/companies
  GET /advanced-search/companies
```

---

## 15. Example: reading a company profile end to end

```bash
curl -s -u YOUR_API_KEY: \
  "https://api.company-information.service.gov.uk/company/00000006" \
  | jq .
```

Then, e.g., pull its officers:

```bash
curl -s -u YOUR_API_KEY: \
  "https://api.company-information.service.gov.uk/company/00000006/officers?items_per_page=50&start_index=0" \
  | jq .
```

And its filing history filtered to accounts filings:

```bash
curl -s -u YOUR_API_KEY: \
  "https://api.company-information.service.gov.uk/company/00000006/filing-history?category=accounts&items_per_page=25" \
  | jq .
```

---

## 16. Reference links (for deeper drill-down if needed)

- Overview: https://developer.company-information.service.gov.uk/overview
- Get started: https://developer.company-information.service.gov.uk/get-started
- How to create an application: https://developer.company-information.service.gov.uk/how-to-create-an-application
- Authentication: https://developer.company-information.service.gov.uk/authentication
- Developer guidelines: https://developer.company-information.service.gov.uk/developer-guidelines
- API testing: https://developer.company-information.service.gov.uk/api-testing
- Full API specifications list (all products, per-endpoint schemas + OpenAPI downloads): https://developer-specs.company-information.service.gov.uk
  - Public Data API reference: https://developer-specs.company-information.service.gov.uk/companies-house-public-data-api/reference
  - Public Data API OpenAPI spec: https://developer-specs.company-information.service.gov.uk/api.ch.gov.uk-specifications/swagger-2.0/spec/swagger.json
  - Streaming API reference: https://developer-specs.company-information.service.gov.uk/streaming-api/reference
  - Streaming API OpenAPI spec: https://developer-specs.company-information.service.gov.uk/api.ch.gov.uk-specifications/swagger-2.0/spec/streaming.json
  - Document API reference: https://developer-specs.company-information.service.gov.uk/document-api/reference
  - Manipulate Company Data (Filing) API: https://developer-specs.company-information.service.gov.uk/manipulate-company-data-api-filing/reference
  - Identity Service: https://developer-specs.company-information.service.gov.uk/companies-house-identity-service/reference
  - Discrepancies API: https://developer-specs.company-information.service.gov.uk/discrepancies/reference
  - Sandbox Test Data Generator: https://developer-specs.company-information.service.gov.uk/sandbox-test-data-generator-api/reference

---

*Compiled for: UK Company Data Extraction Project. This file is intended as complete, self-contained context — an AI or developer reading only this document should be able to authenticate, call, paginate, and parse every Public Data API and Streaming API endpoint without visiting the source pages.*
