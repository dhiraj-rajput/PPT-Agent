# SAM.gov Entity Management API — Definitive AI Context Reference
# Source: https://open.gsa.gov/api/entity-api/
# OpenAPI Spec: https://open.gsa.gov/api/entity-api/v1/openapi.yaml
# Verified Against: Official GSA documentation + live endpoint testing (July 2026)
# Purpose: Complete, AI-readable reference for building integrations with the SAM.gov Entity Management API.

---

## CRITICAL NOTES FOR AI AGENTS

1. **This API requires a REAL SAM.gov API key** — DEMO_KEY and other generic keys will NOT work.
   - Get a key at: https://sam.gov/workspace/profile/account-details → "Public API Key"
2. **API key goes in the URL query string** for Public/FOUO requests: `?api_key=YOUR_KEY`
3. **For Sensitive data only**: API key goes in the `X-Api-Key` HTTP header (NOT in the URL), and POST must be used.
4. **Default behavior (no params)**: Returns only SAM-registered, active + expired entities. Page size = 10.
5. **Max records**: Synchronous = 10,000. Async Extract = 1,000,000.
6. **Forbidden characters in parameter values**: `& | { } ^ \`
7. **Recommended version for new development**: v3 or v4 (most features, correct field names).

---

## 1. WHAT THIS API DOES

The SAM.gov Entity Management API provides access to entity data from the System for Award Management (SAM.gov).

An "entity" is any organization or individual registered with the U.S. federal government for procurement or assistance purposes. Each entity has a Unique Entity Identifier (UEI) — a 12-character alphanumeric value.

There are two categories of entities:
- **SAM-Registered entities**: Fully registered in SAM.gov (have active or expired registrations)
- **ID Assigned / Not Registered entities**: Have a UEI assigned but no SAM registration

---

## 2. DATA SENSITIVITY TIERS

| Tier | Label | Who Can Access | What Data |
|------|-------|---------------|-----------|
| Public | Unclassified | Any valid SAM.gov API key | Name, UEI, registration details, physical/mailing address, business types, PSC/NAICS codes, POC name & address |
| FOUO | CUI - For Official Use Only | Federal System Account with `read fouo` role | Public data + entity hierarchy, security levels, POC email/phone/fax, opted-out entities (NPDY) |
| Sensitive | CUI - Sensitive | Federal System Account with `read sensitive` role | FOUO data + banking (account/routing), SSN/TIN/EIN |

---

## 3. ENDPOINTS (ALL VERSIONS)

### 3.1 Production — Main Entity Query Endpoint

```
GET  https://api.sam.gov/entity-information/v1/entities?api_key=YOUR_KEY&<params>
GET  https://api.sam.gov/entity-information/v2/entities?api_key=YOUR_KEY&<params>
GET  https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY&<params>
GET  https://api.sam.gov/entity-information/v4/entities?api_key=YOUR_KEY&<params>

POST https://api.sam.gov/entity-information/v1/entities?<params>   [Sensitive only]
POST https://api.sam.gov/entity-information/v2/entities?<params>   [Sensitive only]
POST https://api.sam.gov/entity-information/v3/entities?<params>   [Sensitive only]
POST https://api.sam.gov/entity-information/v4/entities?<params>   [Sensitive only]
```

### 3.2 Production — File Download Endpoint (used after Extract API call)

```
GET  https://api.sam.gov/entity-information/v1/download-entities?token=TOKEN&api_key=YOUR_KEY
GET  https://api.sam.gov/entity-information/v3/download-entities?token=TOKEN&api_key=YOUR_KEY
```

> The download-entities endpoint is used ONLY to retrieve the async file after the entities endpoint
> returns a download URL. The URL contains a `token` parameter and a placeholder `REPLACE_WITH_API_KEY`.
> Replace that placeholder with your actual api_key and make the GET request.
> Response is a ZIP file containing the requested JSON or CSV data.

### 3.3 Alpha Environment (Testing/Staging)

```
GET  https://api-alpha.sam.gov/entity-information/v1/entities?api_key=YOUR_KEY&<params>
GET  https://api-alpha.sam.gov/entity-information/v2/entities?api_key=YOUR_KEY&<params>
GET  https://api-alpha.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY&<params>
GET  https://api-alpha.sam.gov/entity-information/v4/entities?api_key=YOUR_KEY&<params>

GET  https://api-alpha.sam.gov/entity-information/v3/download-entities?token=TOKEN&api_key=YOUR_KEY
```

---

## 4. AUTHENTICATION

### 4.1 Getting Your API Key (Personal/Individual Account)

1. Register at https://sam.gov
2. Go to: https://sam.gov/workspace/profile/account-details
3. Find the field "Public API Key"
4. Click the "Eye" icon → enter the One-Time Password sent to your registered email → key is revealed
5. Use this key as `api_key=YOUR_KEY` in every request URL

### 4.2 System Account Setup

System accounts are required for FOUO or Sensitive data access. Setup:

1. **Non-federal users**: Request System Account via SAM.gov Workspace widget
2. **Federal users**: Contact your CCB representative to get the System Accounts widget
3. Create & get System Account approved
4. Set password for the System Account
5. Retrieve the System Account API Key (enter password to reveal)

**Required System Account configuration:**
```
System Information:
  - Unique System ID: [Your System Account ID]

Permissions (choose the level you need):
  - "Entity Information: read public"          → Public data only
  - "Entity Information: read public, read fouo"    → Public + FOUO data
  - "Entity Information: read public, read fouo, read sensitive" → Public + FOUO + Sensitive data

Security Information:
  - IP Address(es): [All IPs your system calls the API from]
  - Type of Connection: REST APIs
```

### 4.3 Rate Limits by Account Type

| Account Type | API Key Type | Daily Limit |
|-------------|-------------|-------------|
| Non-federal, no SAM.gov Role | Personal | 10 requests/day |
| Non-federal, with SAM.gov Role | Personal | 1,000 requests/day |
| Federal User | Personal | 1,000 requests/day |
| Non-federal System Account | System | 1,000 requests/day |
| Federal System Account | System | 10,000 requests/day |

### 4.4 Sensitive Data POST Authentication (Detailed)

For Sensitive (CUI) data, use POST with these exact headers:

```
POST https://api.sam.gov/entity-information/v3/entities?<search_params>

Headers:
  X-Api-Key: <YOUR_SYSTEM_API_KEY>
  Authorization: Basic <base64(username:password)>
  Content-Type: application/json
  Accept: application/json
```

**IMPORTANT**: The API key is in `X-Api-Key` header, NOT in the URL for sensitive calls.

#### Computing the Authorization Header:
```python
# Python
import base64
encoded = base64.b64encode(b"system_username:system_password").decode("utf-8")
# Header: Authorization: Basic <encoded>
```
```javascript
// JavaScript
const encoded = btoa("system_username:system_password");
// Header: Authorization: Basic ${encoded}
```
```bash
# cURL — with base64 token:
curl -X POST "https://api.sam.gov/entity-information/v3/entities?ueiSAM=XXXXXXXXXXXX" \
  --header "X-Api-Key: YOUR_API_KEY" \
  --header "Content-Type: application/json" \
  --header "Accept: application/json" \
  --header "Authorization: Basic BASE64_TOKEN"

# cURL — with username:password directly:
curl -X POST "https://api.sam.gov/entity-information/v3/entities?ueiSAM=XXXXXXXXXXXX" \
  --header "X-Api-Key: YOUR_API_KEY" \
  --header "Content-Type: application/json" \
  --header "Accept: application/json" \
  --user "username:password"
```

Search parameters for sensitive POST calls can be sent either in the URL query string OR in the request body as JSON.

---

## 5. QUERY PARAMETERS — COMPLETE REFERENCE

All parameters are optional and can be combined. Parameters are AND-ed by default.

### 5.1 Pagination & Utility Parameters

| Parameter | Type | Description | Notes |
|-----------|------|-------------|-------|
| `page` | string | Page number (0-indexed) | Default: 0. Each page returns 10 records. |
| `size` | string | Records per page | Maximum: 10. Default: 10. |
| `sort` | string | Field to sort by | e.g., `legalBusinessName` |
| `sortOrder` | enum | Sort direction | `asc` or `desc` |
| `q` | string | Free-text search | Searches across entity fields |
| `qMode` | string | Controls q search mode | |
| `exactMatch` | boolean | Exact match for q search | |
| `includeSections` | string | Filter which sections to return | See Section 6 for valid values |
| `format` | string | Trigger async file extract | `csv` or `json` — returns download URL instead of data |
| `emailId` | string | Email download link | `Yes` — use with `format`. Sends link to email on file |
| `sensitivity` | string | Override sensitivity level | `public`, `fouo`, or `sensitive` (only lower than your key level) |

### 5.2 Entity Identity Parameters (Public)

| Parameter | Type | Format | Applicable Versions | Notes |
|-----------|------|--------|---------------------|-------|
| `ueiSAM` | string | 12-character alphanumeric | v1–v4 | Up to 100 comma-separated values. Works for registered AND ID-assigned entities. Example: `ueiSAM=FJFPKQEAAAW5` |
| `entityEFTIndicator` | string | 4 digits | v1–v4 | **MUST** be used together with `ueiSAM`. Example: `entityEFTIndicator=0000` |
| `cageCode` | string | 5-character | v1–v4 | Up to 100 comma-separated values. Example: `cageCode=0CDJ3` |
| `dodaac` | string | 9 characters | v1–v4 | Example: `dodaac=DOD123456` |
| `legalBusinessName` | string | Partial or complete | v1–v4 | Example: `legalBusinessName=ALLTEL` |
| `dbaName` | string | Partial or complete | v1–v4 | Doing Business As name. Example: `dbaName=ALLTEL` |

### 5.3 Registration Status Parameters (Public)

| Parameter | Type | Format | v1 | v2 | v3/v4 | Notes |
|-----------|------|--------|----|----|-------|-------|
| `samRegistered` | string | `Yes` or `No` | ✗ | `Yes` only | `Yes` or `No` | Default (no param) = registered entities only. `No` = ID-assigned/not registered entities. |
| `samExtractCode` | string | `A` or `E` | ✓ | ✗ | ✗ | v1 only. Use `registrationStatus` in v2+. |
| `registrationStatus` | string | `A` or `E` | ✗ | ✓ | ✓ | A=Active, E=Expired. Replaces `samExtractCode`. |

### 5.4 Date Parameters (Public)

All date parameters accept a single date or date range.
- **Single date format**: `MM/DD/YYYY`
- **Date range format**: `[MM/DD/YYYY,MM/DD/YYYY]`
- **Open-ended range**: `[04/03/2022,]` (from date onwards) or `[,04/03/2022]` (up to date)

| Parameter | v1 | v2+ | Notes |
|-----------|-----|-----|-------|
| `registrationDate` | ✓ | ✓ | Date entity first registered |
| `activationDate` | ✓ | ✓ | Date entity became active |
| `updateDate` | ✓ | ✓ | Date of last update |
| `expirationDate` | ✓ | ✗ | v1 only — use `registrationExpirationDate` in v2+ |
| `registrationExpirationDate` | ✗ | ✓ | Replaces `expirationDate` starting v2 |
| `ueiCreationDate` | ✗ | ✓ | Date UEI was created (v2+). Works for registered AND ID-assigned. |

### 5.5 Physical Address Parameters (Public)

| Parameter | Format | Notes |
|-----------|--------|-------|
| `physicalAddressCity` | Text | Example: `physicalAddressCity=Herndon` |
| `physicalAddressCongressionalDistrict` | 2-digit code | Example: `physicalAddressCongressionalDistrict=08`. SAM registrants only. |
| `physicalAddressCongressionalDistrictState` | 5 characters | Combined state+district |
| `physicalAddressCountryCode` | 3-char (registered) or 2-char/3-char (ID-assigned) | Example: `physicalAddressCountryCode=USA` |
| `physicalAddressProvinceOrStateCode` | 2-char | Example: `physicalAddressProvinceOrStateCode=VA` |
| `physicalAddressZipPostalCode` | 5-digit or 9-digit (US), or any length (non-US) | Example: `physicalAddressZipPostalCode=02201` or `physicalAddressZipPostalCode=21202-3117` |

### 5.6 Business Type & Structure Parameters (Public)

| Parameter | Format | Notes |
|-----------|--------|-------|
| `entityStructureCode` | 2-char code or null | Example: `entityStructureCode=2L` |
| `entityStructureDesc` | Text | Example: `entityStructureDesc=Partnership or Limited Liability Partnership` |
| `organizationStructureCode` | 2-char | Example: `organizationStructureCode=MF` |
| `organizationStructureDesc` | Text | Example: `organizationStructureDesc=MANUFACTURER OF GOODS` |
| `businessTypeCode` | 2-char | Example: `businessTypeCode=OY` |
| `businessTypeDesc` | Text | Example: `businessTypeDesc=Woman Owned Business` |
| `sbaBusinessTypeCode` | 2-char or null | Example: `sbaBusinessTypeCode=12` |
| `sbaBusinessTypeDesc` | Text | Example: `sbaBusinessTypeDesc=Woman Owned Small Business` |
| `stateOfIncorporationCode` | 2-char | Example: `stateOfIncorporationCode=VA` |
| `stateOfIncorporationDesc` | Text | Example: `stateOfIncorporationDesc=Virginia` |
| `countryOfIncorporationCode` | 3-char | Example: `countryOfIncorporationCode=USA` |
| `countryOfIncorporationDesc` | Text | Example: `countryOfIncorporationDesc=UNITED STATES` |
| `debtSubjectToOffset` | `Y`, `N`, `U`, or null | Example: `debtSubjectToOffset=Y` |
| `exclusionStatusFlag` | v1/v2: `D` or `""` / v3+: `Y` or `N` | Whether entity is debarred |

### 5.7 NAICS & PSC Parameters (Public)

| Parameter | Format | Notes |
|-----------|--------|-------|
| `primaryNaics` | 6-digit NAICS | Accepts multiple NAICS codes. Example: `primaryNaics=513310` |
| `naicsCode` | 6-char | Searches all NAICS (primary + secondary). Example: `naicsCode=513310` |
| `naicsDesc` | Text | Example: `naicsDesc=Furniture Stores` |
| `naicsLimitedSB` | 6-digit NAICS, `""`, or `!""` | Filter by SBA small business designation |
| `pscCode` | 4-char | Product/Service Code. Example: `pscCode=X1QA` |
| `pscDesc` | Text | Example: `pscDesc=Screws` |

### 5.8 Purpose of Registration Parameters (Public)

| Code | Description |
|------|-------------|
| `Z1` | Federal Assistance Awards Only |
| `Z2` | All Awards |
| `Z4` | Federal Assistance Awards and Contracts |
| `Z5` | Contracts Only |

Parameters:
- `purposeOfRegistrationCode`: 2-char code (e.g., `purposeOfRegistrationCode=Z2`)
- `purposeOfRegistrationDesc`: Text (e.g., `purposeOfRegistrationDesc=All Awards`)

### 5.9 Disaster Relief Parameters (Public)

| Parameter | Format | Notes |
|-----------|--------|-------|
| `servedDisasterStateCode` | 2-char state code or `any` | Example: `servedDisasterStateCode=VA` |
| `servedDisasterStateName` | Text or null | Example: `servedDisasterStateName=Virginia` |
| `servedDisasterCountyCode` | 3-digit county code | Example: `servedDisasterCountyCode=060` |
| `servedDisasterCountyName` | Text | Example: `servedDisasterCountyName=FAIRFAX` |
| `servedDisasterMSA` | 4-digit MSA code | Metropolitan Statistical Area. Example: `servedDisasterMSA=1720` |

### 5.10 Integrity & Proceedings Parameters (v3/v4, Public)

| Parameter | Format | Notes |
|-----------|--------|-------|
| `proceedingsData` | `Yes` (case-insensitive) | Must be used with `includeSections=integrityInformation`. Returns entities that have Proceedings data. |

### 5.11 FOUO-Level Parameters (Federal System Account with read fouo required)

| Parameter | Format | Notes |
|-----------|--------|-------|
| `edi` | `YES` or `NO` | Electronic Data Interchange |
| `companySecurityLevelCode` | 2-char | Example: `companySecurityLevelCode=92` |
| `companySecurityLevelDesc` | Text | Example: `companySecurityLevelDesc=Government Top Secret` |
| `highestEmployeeSecurityLevelCode` | 2-char | Example: `highestEmployeeSecurityLevelCode=90` |
| `highestEmployeeSecurityLevelDesc` | Text | Example: `highestEmployeeSecurityLevelDesc=Government Top Secret` |
| `ultimateParentUEISAM` | 12-char UEI | Filter by ultimate parent entity's UEI |
| `agencyBusinessPurposeCode` | Text | Example: `agencyBusinessPurposeCode=1` |
| `agencyBusinessPurposeDesc` | Text | Example: `agencyBusinessPurposeDesc=Buyer and Seller` |

### 5.12 Sensitive-Level Parameters (Federal System Account with read sensitive, POST only)

| Parameter | Format | Notes |
|-----------|--------|-------|
| `routingNumber` | Text | Bank routing number |
| `bankName` | Text | Bank name |
| `accountNumber` | Text | Bank account number |
| `eftWaiverFlag` | `Y` or `N` | EFT Waiver flag |
| `agencyLocationCode` | Text | Agency Location Code |
| `disbursingOfficeSymbol` | Text | Example: `disbursingOfficeSymbol=1093` |
| `taxpayerName` | Text | |
| `taxpayerIdentificationNumber` | Text | TIN/EIN/SSN |

---

## 6. includeSections — SECTION FILTERING

The `includeSections` parameter controls which sections of entity data are returned.
Without it, all available sections (except `repsAndCerts` and `integrityInformation`) are returned.

### For SAM-Registered Entities:

| Section Value | Description | Notes |
|--------------|-------------|-------|
| `entityRegistration` | Registration metadata (UEI, CAGE, dates, status) | |
| `coreData` | Address, hierarchy, financial, general info | |
| `assertions` | NAICS/PSC codes, disaster relief, EDI | |
| `pointsOfContact` | Contact information | |
| `repsAndCerts` | Representations and Certifications (FAR responses) | **NOT returned unless explicitly requested** |
| `All` | Returns entityRegistration + coreData + assertions + pointsOfContact + repsAndCerts | |
| `integrityInformation` | Proceedings, responsibility records, corporate relationships | **v3/v4 only. NOT included in `All` — must explicitly request** |

### For Not-Registered/ID-Assigned Entities:

| Section Value | Description |
|--------------|-------------|
| `entityRegistration` | Registration metadata |
| `coreData` | Address info |
| `All` | Returns entityRegistration + coreData |
| `integrityInformation` | Responsibility records (v3/v4 only — must explicitly request) |

### Examples:
```
includeSections=entityRegistration,coreData
includeSections=All
includeSections=All,integrityInformation
includeSections=repsAndCerts
includeSections=entityRegistration,coreData,integrityInformation,pointsOfContact
```

---

## 7. OPERATOR LOGIC — AND, OR, NOT

### AND (default)
Multiple different parameters are automatically AND-ed via the `&` URL separator.
```
?legalBusinessName=IBM&registrationStatus=A&physicalAddressCountryCode=USA
→ entities where name contains IBM AND status is Active AND country is USA
```

### OR (tilde `~`)
Separate multiple values for the SAME parameter with `~` to get OR logic.
```
?businessTypeDesc=Joint Venture Women~Asian-Pacific
→ entities where businessTypeDesc is "Joint Venture Women" OR "Asian-Pacific"
```

### NOT (exclamation `!`)
Prefix a value with `!` to exclude it.
```
?naicsCode=!513310
→ entities where naicsCode is NOT 513310

?naicsLimitedSB=!""
→ entities where naicsLimitedSB is not empty (has a value)
```

### Combining:
```
?businessTypeDesc=Joint Venture Women~Asian-Pacific&purposeOfRegistrationDesc=All Awards~Federal Assistance Awards
→ (businessTypeDesc = Joint Venture Women OR Asian-Pacific) AND (purposeOfRegistrationDesc = All Awards OR Federal Assistance Awards)
```

---

## 8. RESPONSE STRUCTURE — COMPLETE SCHEMA

### 8.1 Top-Level Response Object

```json
{
  "totalRecords": 125847,
  "entityData": [
    { ... entity object ... }
  ],
  "links": {
    "selfLink": "https://api.sam.gov/entity-information/v3/entities?...&page=0",
    "nextLink": "https://api.sam.gov/entity-information/v3/entities?...&page=1"
  }
}
```

> For Extract API calls (with `format=csv` or `format=json`), the response is:
```json
{
  "status": "Processing your request",
  "fileGenerationMessage": "File will be available for download shortly",
  "extractFull": "https://api.sam.gov/entity-information/v3/download-entities?token=TOKEN&api_key=REPLACE_WITH_API_KEY"
}
```

### 8.2 Entity Object — Section Breakdown

Each entity in `entityData` has this structure:
```json
{
  "entityRegistration": { ... },
  "coreData": { ... },
  "assertions": { ... },
  "repsAndCerts": { ... },
  "pointsOfContact": { ... },
  "integrityInformation": { ... }
}
```

---

### 8.3 entityRegistration Section

All fields are **Public** unless noted.

```json
{
  "entityRegistration": {
    "samRegistered": "Yes",                      // v2+: "Yes" or "No"
    "ueiSAM": "FJFPKQEAAAW5",                   // 12-char Unique Entity Identifier
    "entityEFTIndicator": null,                  // EFT Indicator
    "cageCode": "0CDJ3",                         // 5-char CAGE Code (null if no CAGE)
    "dodaac": null,                              // 9-char DoDAAC
    "legalBusinessName": "INTERNATIONAL BUSINESS MACHINES CORP",
    "dbaName": null,                             // Doing Business As name
    "purposeOfRegistrationCode": "Z2",
    "purposeOfRegistrationDesc": "All Awards",
    "registrationStatus": "Active",              // "Active" or "Expired"
    "evsSource": "D&B",                          // v3+ only: Source of entity validation
    "registrationDate": "1994-01-01",
    "lastUpdateDate": "2024-06-15",
    "registrationExpirationDate": "2025-06-30",  // v2+ (was "expirationDate" in v1)
    "activationDate": "2024-07-01",
    "ueiStatus": "Active",                       // v2+
    "ueiExpirationDate": null,                   // v2+
    "ueiCreationDate": "2022-04-04",             // v2+
    "publicDisplayFlag": "Y",                    // v3+: "Y" or "N". Was "noPublicDisplayFlag" in v1/v2.
    "exclusionStatusFlag": "N",                  // v1/v2: "D" or null. v3+: "Y" or "N"
    "exclusionURL": null,                        // URL to debarment record if exclusionStatusFlag is Y/D
    "dnbOpenData": "Y"                           // v2+: Dun & Bradstreet open data flag
  }
}
```

---

### 8.4 coreData Section

#### entityHierarchyInformation Sub-section (FOUO)

```json
{
  "entityHierarchyInformation": {
    "immediateParentEntity": {
      "ueiSAM": "PARENT_UEI_12CHAR",
      "legalBusinessName": "PARENT COMPANY NAME",
      "evsSource": "D&B",              // v3+ only
      "physicalAddress": {
        "addressLine1": "123 Main St",
        "addressLine2": null,
        "city": "Armonk",
        "stateOrProvinceCode": "NY",
        "zipCode": "10504",
        "zipCodePlus4": "1722",
        "countryCode": "USA"
      },
      "phoneNumber": "9145997900"
    },
    "intermediateParentEntities": [
      {
        "domesticParent": {
          "ueiSAM": "DOM_PARENT_UEI",
          "legalBusinessName": "DOMESTIC PARENT LLC",
          "evsSource": "D&B",          // v3+ only
          "physicalAddress": { ... },
          "phoneNumber": "..."
        },
        "hqParent": {
          "ueiSAM": "HQ_PARENT_UEI",
          "legalBusinessName": "HQ PARENT CORP",
          "evsSource": "D&B",          // v3+ only
          "physicalAddress": { ... },
          "phoneNumber": "..."
        }
      }
    ],
    "ultimateParentEntity": {
      "ueiSAM": "ULTIMATE_PARENT_UEI",
      "legalBusinessName": "ULTIMATE PARENT CORP",
      "evsSource": "D&B",              // v3+ only
      "physicalAddress": { ... },
      "phoneNumber": "..."
    },
    "evsMonitoring": {
      // v1: split into "dnbMonitoring" and "samMonitoring" objects
      // v2+: flat object (shown below)
      "legalBusinessName": "IBM CORP",
      "dbaName": null,
      "outOfBusinessFlag": "N",
      "monitoringStatus": "Y",
      "lastUpdated": "2024-06-01",
      "addressLine1": "1 New Orchard Rd",
      "addressLine2": null,
      "city": "Armonk",
      "postalCode": "10504",          // v2+ uses "postalCode" (v1 used "zipCode")
      "stateOrProvinceCode": "NY",
      "countryCode": "USA"
    }
  }
}
```

#### federalHierarchy Sub-section (FOUO)

```json
{
  "federalHierarchy": {
    "source": "SAM",
    "hierarchyDepartmentCode": "9700",
    "hierarchyDepartmentName": "Department of Defense",
    "hierarchyAgencyCode": "97AS",
    "hierarchyAgencyName": "Defense Logistics Agency",
    "hierarchyOfficeCode": null
  }
}
```

#### tinInformation Sub-section (Sensitive)

```json
{
  "tinInformation": {
    "taxpayerName": "IBM CORPORATION",
    "taxpayerIdentificationType": "EIN",
    "taxpayerIdentificationNumber": "13-0871985"
  }
}
```

#### entityInformation Sub-section (Public)

```json
{
  "entityInformation": {
    "entityURL": "https://www.ibm.com",
    "entityDivisionName": null,
    "entityDivisionNumber": null,
    "entityStartDate": "1911-06-16",
    "fiscalYearEndCloseDate": "12/31",
    "submissionDate": "2024-06-01"
  }
}
```

#### physicalAddress Sub-section (Public)

```json
{
  "physicalAddress": {
    "addressLine1": "1 New Orchard Rd",
    "addressLine2": null,
    "city": "Armonk",
    "stateOrProvinceCode": "NY",
    "zipCode": "10504",
    "zipCodePlus4": "1722",
    "countryCode": "USA"
  }
}
```

#### mailingAddress Sub-section (Public — registered entities only)

```json
{
  "mailingAddress": {
    "addressLine1": "1 New Orchard Rd",
    "addressLine2": null,
    "city": "Armonk",
    "stateOrProvinceCode": "NY",
    "zipCode": "10504",
    "zipCodePlus4": "1722",
    "countryCode": "USA"
  }
}
```

#### congressionalDistrict Sub-section (Public)

```json
{
  "congressionalDistrict": "17"
}
```

#### generalInformation Sub-section

```json
{
  "generalInformation": {
    // Public fields:
    "entityStructureCode": "2L",
    "entityStructureDescription": "Corporate Entity (Not Tax Exempt)",
    "entityTypeCode": "F",
    "entityTypeDesc": "Business or Organization",
    "profitStructureCode": "2X",
    "profitStructureDesc": "For Profit Organization",
    "organizationStructureCode": "XS",
    "organizationStructureDesc": "SMALL BUSINESS",
    "stateOfIncorporationCode": "NY",
    "stateOfIncorporationDesc": "NEW YORK",
    "countryOfIncorporationCode": "USA",
    "countryOfIncorporationDesc": "UNITED STATES",

    // FOUO fields (only returned with FOUO key):
    "agencyBusinessPurposeCode": null,
    "agencyBusinessPurposeDesc": null,
    "companySecurityLevelCode": "93",
    "companySecurityLevelDesc": "Government Top Secret/SCI",
    "highestEmployeeSecurityLevelCode": "90",
    "highestEmployeeSecurityLevelDesc": "Government Top Secret"
  }
}
```

#### businessTypes Sub-section (Public)

```json
{
  "businessTypes": {
    "businessTypeList": [
      {
        "businessTypeCode": "2X",
        "businessTypeDescription": "For Profit Organization"
      },
      {
        "businessTypeCode": "LJ",
        "businessTypeDescription": "Limited Liability Company"
      }
    ],
    "sbaBusinessTypeList": [
      {
        "sbaBusinessTypeCode": "A5",
        "sbaBusinessTypeDesc": "Economically Disadvantaged Women-Owned Small Business",
        "certificationEntryDate": "2022-01-01",
        "certificationExitDate": null
      }
    ]
  }
}
```

#### financialInformation Sub-section

```json
{
  "financialInformation": {
    // Public fields:
    "creditCardUsage": "N",
    "debtSubjectToOffset": "N",

    // Sensitive fields (only with Sensitive key):
    "financialAccount": {
      "authorizationDate": "2023-01-01",
      "eftInformation": "...",
      "accountType": "Checking",
      "accountNumber": "XXXXXXXXXX",
      "abaRoutingNumber": "XXXXXXXXX",
      "eftWaiver": "N",
      "lockboxNumber": null,
      "merchantID1": null,
      "merchantID2": null,
      "departmentCode": null,
      "agencyLocationCode": null,
      "disbursingOfficeSymbol": null,
      "accountingStation": null
    },
    "achInformation": {
      "usPhone": "9145997900",
      "nonUSPhone": null,
      "faxNumber": null,
      "email": "accounts@ibm.com"
    },
    "remittanceInformation": {
      "name": "IBM CORPORATION",
      "addressLine1": "1 New Orchard Rd",
      "addressLine2": null,
      "city": "Armonk",
      "stateOrProvinceCode": "NY",
      "zipCode": "10504",
      "zipCodePlus4": "1722",
      "countryCode": "USA"
    }
  }
}
```

---

### 8.5 assertions Section

#### goodsAndServices Sub-section (Public)

```json
{
  "goodsAndServices": {
    "primaryNaics": "541511",
    "naicsList": [
      {
        "naicsCode": "541511",
        "naicsDescription": "Custom Computer Programming Services",
        "sbaSmallBusiness": "N",
        "naicsException": null
      },
      {
        "naicsCode": "541512",
        "naicsDescription": "Computer Systems Design Services",
        "sbaSmallBusiness": "Y",
        "naicsException": "Exception for SB"
      }
    ],
    "pscList": [
      {
        "pscCode": "D302",
        "pscDescription": "IT AND TELECOM- DATA ENTRY SERVICES"
      }
    ]
  }
}
```

#### disasterReliefData Sub-section (Public + FOUO)

```json
{
  "disasterReliefData": {
    "disasterRegistryFlag": "N",
    "bondingFlag": "N",
    "geographicalAreaServed": [
      {
        "geographicalAreaServedStateCode": "VA",
        "geographicalAreaServedStateName": "Virginia",
        "geographicalAreaServedCountyCode": "059",
        "geographicalAreaServedCountyName": "FAIRFAX",
        "geographicalAreaServedmetropolitanStatisticalAreaCode": "1720",
        "geographicalAreaServedmetropolitanStatisticalAreaName": "Washington-Arlington-Alexandria, DC-VA-MD-WV"
      }
    ],
    "bondingLevels": null       // FOUO only
  }
}
```

#### sizeMetrics, sizeMetricDetails, industrySpecificSizeMetrics Sub-sections (FOUO)

```json
{
  "sizeMetrics": {
    "averageAnnualRevenue": "$ Over $40 Million",
    "averageNumberOfEmployees": "Over 1,000 Employees"
  },
  "sizeMetricDetails": {
    "employeesLocation": "All Locations",
    "receiptsLocation": "All Locations"
  },
  "industrySpecificSizeMetrics": {
    "barrelsCapacity": null,
    "totalAssets": null,
    "megawattHours": null
  }
}
```

#### ediInformation Sub-section (Public + FOUO)

```json
{
  "ediInformation": {
    "ediInformationFlag": "N",        // Public
    "vanProvider": null,               // FOUO
    "isaQualifier": null,              // FOUO
    "isaIdentifier": null,             // FOUO
    "functionalGroupIdentifier": null, // FOUO
    "requestFlag820s": null            // FOUO
  }
}
```

---

### 8.6 repsAndCerts Section (Public — must explicitly request)

Complex structure with FAR (Federal Acquisition Regulation) provision responses.

```json
{
  "repsAndCerts": {
    "certifications": {
      "fARResponses": [
        {
          "provisionId": "FAR 52.219-1",
          "listOfAnswers": [
            {
              "section": "I",
              "questionText": "Is the entity a small business?",
              "answerId": "1",
              "answerText": "YES",
              "country": null,
              "company": {
                "id": "1",
                "name": "IBM Corp",
                "tin": null,
                "uniqueEntityId": "FJFPKQEAAAW5",
                "yearEstablished": "1911"
              },
              "highestLevelOwnerCage": {
                "cageCode": "0CDJ3",
                "nCageCode": null,
                "legalBusinessName": "IBM CORP",
                "hasOwner": "Y",
                "id": "1"
              },
              "immediateOwnerCage": {
                "cageCode": "0CDJ3",
                "nCageCode": null,
                "legalBusinessName": "IBM CORP",
                "hasOwner": "N",
                "id": "1"
              },
              "personDetails": {
                "firstName": "John",
                "middleInitial": "A",
                "lastName": "Doe",
                "title": "VP Contracts"
              },
              "pointOfContact": {
                "id": "1",
                "firstName": "Jane",
                "middleInitial": null,
                "lastName": "Smith",
                "title": "Contracts Manager",
                "telephoneNumber": "9145997900",
                "extension": null,
                "internationalNumber": null
              },
              "architectExperiencesList": [],
              "disciplineInfoList": [],
              "endProductsList": [],
              "foreignGovtEntitiesList": [],
              "formerFirmsList": [],
              "fscInfoList": [],
              "jointVentureCompaniesList": [],
              "laborSurplusConcernsList": []
            }
          ]
        }
      ]
    }
  }
}
```

---

### 8.7 pointsOfContact Section (Public + FOUO)

Four POC types:
- `governmentBusinessPOC`
- `electronicBusinessPOC`
- `governmentBusinessAlternatePOC`
- `electronicBusinessAlternatePOC`

Each has the same structure:

```json
{
  "pointsOfContact": {
    "governmentBusinessPOC": {
      // Public fields:
      "firstName": "Jane",
      "middleInitial": "A",
      "lastName": "Smith",
      "title": "VP Government Affairs",
      "addressLine1": "1 New Orchard Rd",
      "addressLine2": null,
      "city": "Armonk",
      "stateOrProvinceCode": "NY",
      "zipCode": "10504",
      "zipCodePlus4": "1722",
      "countryCode": "USA",

      // FOUO fields (only returned with FOUO key):
      "usPhone": "9145997901",
      "usPhoneExtension": "1234",
      "nonUSPhone": null,
      "fax": "9145997999",
      "email": "jane.smith@ibm.com"
    },
    "electronicBusinessPOC": { ... same structure ... },
    "governmentBusinessAlternatePOC": { ... same structure ... },
    "electronicBusinessAlternatePOC": { ... same structure ... }
  }
}
```

---

### 8.8 integrityInformation Section (v3/v4 only — must explicitly request)

#### entitySummary Sub-section (Public)

```json
{
  "entitySummary": {
    "ueiSAM": "FJFPKQEAAAW5",
    "cageCode": "0CDJ3",
    "legalBusinessName": "IBM CORPORATION",
    "physicalAddress": {
      "addressLine1": "1 New Orchard Rd",
      "addressLine2": null,
      "city": "Armonk",
      "stateOrProvinceCode": "NY",
      "zipCode": "10504",
      "zipCodePlus4": "1722",
      "countryCode": "USA"
    }
  }
}
```

#### proceedingsData Sub-section (Public)

```json
{
  "proceedingsData": {
    "proceedingsQuestion1": "No",
    "proceedingsQuestion2": "No",
    "proceedingsQuestion3": "No",
    "proceedingsRecordCount": "0",
    "listOfProceedings": [],
    "proceedingsPointsOfContact": {
      "proceedingsPOC": {
        // Public fields:
        "firstName": "John",
        "middleInitial": null,
        "lastName": "Doe",
        "title": "Legal Counsel",
        "addressLine1": "1 New Orchard Rd",
        "addressLine2": null,
        "city": "Armonk",
        "stateOrProvinceCode": "NY",
        "zipCode": "10504",
        "zipCodePlus4": "1722",
        "countryCode": "USA",
        // FOUO fields:
        "usPhone": "9145997900",
        "usPhoneExtension": null,
        "nonUSPhone": null,
        "fax": null,
        "email": "legal@ibm.com"
      },
      "proceedingsAlternatePOC": { ... same structure ... }
    }
  }
}
```

Each proceeding in `listOfProceedings`:
```json
{
  "proceedingDate": "2020-01-15",
  "instrumentNumber": "DOJ-2020-001",
  "instrument": "Settlement Agreement",
  "proceedingStateCode": "DC",
  "proceedingType": "Administrative",
  "disposition": "Resolved",
  "proceedingDescription": "Settlement related to..."
}
```

#### responsibilityInformation Sub-sections (Public)

```json
{
  "responsibilityInformationCount": "3",
  "responsibilityInformationList": [
    {
      "recordType": "CONTRACT_AWARD",
      "recordTypeDesc": "Contract Award",
      "recordDate": "2023-06-15",
      "procurementIdOrFederalAssistanceId": "FA8523-23-C-0001",
      "referenceIdvPiid": null,
      "attachment": "https://presigned-s3-url-to-attachment..."
    }
  ]
}
```

#### corporateRelationships Sub-section (Public)

```json
{
  "corporateRelationships": {
    "highestOwner": {
      "legalBusinessName": "IBM CORPORATION",
      "cageCode": "0CDJ3",
      "integrityRecords": "Yes"     // "Yes", "No", or "N/A" (if cageCode is null)
    },
    "immediateOwner": {
      "legalBusinessName": "IBM CORPORATION",
      "cageCode": "0CDJ3",
      "integrityRecords": "Yes"
    },
    "predecessorsList": [
      {
        "legalBusinessName": "FORMER COMPANY NAME",
        "cageCode": "1ABC2",
        "integrityRecords": "No"
      }
    ]
  }
}
```

---

## 9. EXTRACT / ASYNC FILE DOWNLOAD — HOW IT WORKS

### Step-by-Step

1. **Make your normal query** but add `format=csv` or `format=json`:
   ```
   GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY&registrationStatus=A&format=csv
   ```

2. **API returns a JSON response** with a download URL (NOT the actual data):
   ```json
   {
     "status": "File Request Received",
     "fileGenerationMessage": "File will be available for download shortly.",
     "extractFull": "https://api.sam.gov/entity-information/v3/download-entities?token=XXXXXXXX&api_key=REPLACE_WITH_API_KEY"
   }
   ```

3. **Replace `REPLACE_WITH_API_KEY`** with your actual API key in the returned URL.

4. **Poll the download URL** until the file is ready:
   ```
   GET https://api.sam.gov/entity-information/v3/download-entities?token=XXXXXXXX&api_key=YOUR_KEY
   ```
   - If **ready**: Returns a ZIP file (application/zip) containing your JSON or CSV file.
   - If **not ready**: Returns a "file not yet available" message — retry after some time.

5. **Optionally send download link by email**: Add `emailId=Yes` to the original request:
   ```
   GET .../entities?api_key=YOUR_KEY&registrationStatus=A&format=csv&emailId=Yes
   ```
   The download link will be emailed to the address associated with your API key.

### Limits
| Mode | Max Records |
|------|-------------|
| Synchronous (no `format`) | 10,000 |
| Async Extract (`format=csv` or `format=json`) | 1,000,000 |

---

## 10. HTTP RESPONSE CODES

| Code | Status | Meaning | When It Occurs |
|------|--------|---------|----------------|
| 200 | OK | Success | Data returned normally |
| 201 | Created | Created | POST requests that trigger file generation |
| 400 | Bad Request | Invalid parameters | Bad param format, forbidden characters, invalid values |
| 401 | Unauthorized | Authentication failed | Missing or invalid API key |
| 403 | Forbidden | Insufficient permissions | Trying to access FOUO/Sensitive data with Public key; DEMO_KEY or invalid key |
| 404 | Not Found | No data or bad URL | No matching entities; wrong endpoint path |
| 429 | Too Many Requests | Rate limit exceeded | Daily quota exhausted |
| 500 | Internal Server Error | Server error | API server-side issue |

---

## 11. KEY RULES & GOTCHAS

1. **No `samRegistered` param** → returns only SAM-registered entities (both Active and Expired)
2. **`samRegistered=No`** → returns only ID-assigned/not-registered entities (v3/v4 only)
3. **`repsAndCerts`** section NEVER returned unless explicitly in `includeSections`
4. **`integrityInformation`** (v3/v4) is NOT part of `All` — must always explicitly request it
5. **`DEMO_KEY` does NOT work** for SAM.gov — always requires a real SAM.gov-issued API key
6. **Forbidden chars in param values**: `& | { } ^ \` — using them breaks the request
7. **Multiple values**: `ueiSAM` and `cageCode` accept up to 100 comma-separated values
8. **`entityEFTIndicator` requires `ueiSAM`** — cannot be used alone
9. **Sensitive calls require POST** — cannot use GET for Sensitive data
10. **`api_key` for Sensitive POST** goes in `X-Api-Key` header, NOT in the URL
11. **NPDY entities** (opted out of public display, `publicDisplayFlag=N`) require a Federal System Account with the Non-SAM NPDY Role to access
12. **v1 vs v2+ naming**: `samExtractCode` → `registrationStatus`, `expirationDate` → `registrationExpirationDate`, `noPublicDisplayFlag` → `publicDisplayFlag`
13. **Alpha vs Production**: Always use production endpoints (`api.sam.gov`) for real data; alpha (`api-alpha.sam.gov`) is for testing

---

## 12. PRACTICAL EXAMPLES — REAL QUERY STRINGS

### Example 1: Get entities updated after April 3, 2022 (EVS address/name changes)
```
GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY
  &updateDate=[04/03/2022,]
  &includeSections=entityRegistration,coreData
```

### Example 2: Get not-registered/ID-Assigned entities after April 3, 2022
```
GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY
  &samRegistered=No
  &ueiCreationDate=[04/03/2022,]
  &includeSections=entityRegistration,coreData
```

### Example 3: Joint Venture Women OR Asian-Pacific for All Awards OR Federal Assistance
```
GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY
  &businessTypeDesc=Joint Venture Women~Asian-Pacific
  &purposeOfRegistrationDesc=All Awards~Federal Assistance Awards
  &includeSections=entityRegistration,coreData
```

### Example 4: Look up a specific entity by UEI
```
GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY
  &ueiSAM=FJFPKQEAAAW5
  &includeSections=All,integrityInformation
```

### Example 5: Look up multiple entities by UEI (batch lookup)
```
GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY
  &ueiSAM=FJFPKQEAAAW5,XXXXXXXXXXXXM,YYYYYYYYYYYY
  &includeSections=entityRegistration
```

### Example 6: Get all Active registered entities in Virginia with NAICS 541511
```
GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY
  &registrationStatus=A
  &physicalAddressProvinceOrStateCode=VA
  &naicsCode=541511
  &includeSections=entityRegistration,coreData,assertions
```

### Example 7: Get Responsibility & Integrity Record (Public + NPDY) with Public key
```
GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY
  &ueiSAM=FJFPKQEAAAW5
  &includeSections=integrityInformation
```

### Example 8: Get not-registered/ID-Assigned integrity records (Public key)
```
GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY
  &samRegistered=No
  &includeSections=integrityInformation
```

### Example 9: Async CSV file of all Active registered entities
```
GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY
  &registrationStatus=A
  &format=csv
  &emailId=Yes
```
→ Returns a download URL. Replace REPLACE_WITH_API_KEY in the URL with your key and fetch to get the ZIP file.

### Example 10: Get all entities JSON via POST (Sensitive)
```
POST https://api.sam.gov/entity-information/v3/entities?format=json

Headers:
  X-Api-Key: YOUR_SYSTEM_API_KEY
  Authorization: Basic BASE64_ENCODED_CREDENTIALS
  Content-Type: application/json
  Accept: application/json
```

### Example 11: Get entities with Proceedings data
```
GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY
  &includeSections=integrityInformation
  &proceedingsData=Yes
```

### Example 12: Woman-owned small businesses in California
```
GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY
  &sbaBusinessTypeDesc=Woman Owned Small Business
  &physicalAddressProvinceOrStateCode=CA
  &registrationStatus=A
  &includeSections=entityRegistration,coreData,assertions
```

### Example 13: Paginate through results
```
GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY
  &registrationStatus=A
  &physicalAddressCountryCode=USA
  &page=0&size=10    # Page 1 (0-indexed)
  
GET https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY
  &registrationStatus=A
  &physicalAddressCountryCode=USA
  &page=1&size=10    # Page 2
```

---

## 13. VERSION DIFFERENCES (v1 → v2 → v3 → v4)

| Feature | v1 | v2 | v3 | v4 |
|---------|----|----|----|----|
| Registration status param | `samExtractCode` | `registrationStatus` | `registrationStatus` | `registrationStatus` |
| Expiration date param | `expirationDate` | `registrationExpirationDate` | `registrationExpirationDate` | `registrationExpirationDate` |
| Public display field | `noPublicDisplayFlag` | `noPublicDisplayFlag` | `publicDisplayFlag` | `publicDisplayFlag` |
| Exclusion flag values | `D` or null | `D` or null | `Y` or `N` | `Y` or `N` |
| `samRegistered` param | Not available | `Yes` only | `Yes` or `No` | `Yes` or `No` |
| `ueiCreationDate` param | No | Yes | Yes | Yes |
| `ueiStatus`, `ueiExpirationDate`, `ueiCreationDate` fields | No | Yes | Yes | Yes |
| `dnbOpenData` field | No | Yes | Yes | Yes |
| `samRegistered` field in response | No | Yes | Yes | Yes |
| `evsSource` field | No | No | Yes | Yes |
| EVS Monitoring structure | `dnbMonitoring` + `samMonitoring` objects | Flat `evsMonitoring` | Flat `evsMonitoring` | Flat `evsMonitoring` |
| `integrityInformation` section | No | No | Yes | Yes |
| `proceedingsData` parameter | No | No | Yes | Yes |
| `evsSource` in hierarchy fields | No | No | Yes | Yes |

---

## 14. OPENAPI SPEC LOCATION

The official OpenAPI 3.0.1 YAML specification is available at:
```
https://open.gsa.gov/api/entity-api/v1/openapi.yaml
```

It documents both production and alpha environments and covers v1 through v4 controllers.

---

## 15. QUICK-START CODE EXAMPLES

### Python (requests library)
```python
import requests

API_KEY = "your_sam_gov_api_key"
BASE_URL = "https://api.sam.gov/entity-information/v3/entities"

# Basic lookup by UEI
def get_entity_by_uei(uei):
    params = {
        "api_key": API_KEY,
        "ueiSAM": uei,
        "includeSections": "entityRegistration,coreData,assertions"
    }
    response = requests.get(BASE_URL, params=params)
    response.raise_for_status()
    return response.json()

# Search by business name and state
def search_entities(name, state=None, status="A"):
    params = {
        "api_key": API_KEY,
        "legalBusinessName": name,
        "registrationStatus": status,
        "includeSections": "entityRegistration,coreData"
    }
    if state:
        params["physicalAddressProvinceOrStateCode"] = state
    response = requests.get(BASE_URL, params=params)
    response.raise_for_status()
    return response.json()

# Get all active entities as CSV (async extract)
def request_csv_extract():
    params = {
        "api_key": API_KEY,
        "registrationStatus": "A",
        "format": "csv",
        "emailId": "Yes"
    }
    response = requests.get(BASE_URL, params=params)
    response.raise_for_status()
    data = response.json()
    # Returns URL in data["extractFull"] — replace REPLACE_WITH_API_KEY
    download_url = data["extractFull"].replace("REPLACE_WITH_API_KEY", API_KEY)
    return download_url

# Paginate through results
def get_all_entities_paginated(filters: dict):
    page = 0
    all_entities = []
    while True:
        params = {"api_key": API_KEY, "page": page, "size": 10, **filters}
        r = requests.get(BASE_URL, params=params).json()
        entities = r.get("entityData", [])
        all_entities.extend(entities)
        if not r.get("links", {}).get("nextLink"):
            break
        page += 1
    return all_entities
```

### JavaScript / Node.js (fetch)
```javascript
const API_KEY = "your_sam_gov_api_key";
const BASE_URL = "https://api.sam.gov/entity-information/v3/entities";

// Lookup entity by UEI
async function getEntityByUEI(uei) {
  const params = new URLSearchParams({
    api_key: API_KEY,
    ueiSAM: uei,
    includeSections: "entityRegistration,coreData"
  });
  const response = await fetch(`${BASE_URL}?${params}`);
  if (!response.ok) throw new Error(`API Error: ${response.status}`);
  return response.json();
}

// Search by name, state, NAICS
async function searchEntities({ name, state, naics, status = "A" }) {
  const params = new URLSearchParams({ api_key: API_KEY, registrationStatus: status });
  if (name) params.set("legalBusinessName", name);
  if (state) params.set("physicalAddressProvinceOrStateCode", state);
  if (naics) params.set("naicsCode", naics);
  params.set("includeSections", "entityRegistration,coreData,assertions");
  const response = await fetch(`${BASE_URL}?${params}`);
  return response.json();
}
```

### cURL Examples
```bash
# Public lookup by UEI
curl "https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY&ueiSAM=FJFPKQEAAAW5&includeSections=entityRegistration,coreData"

# Search by name
curl "https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY&legalBusinessName=ALLTEL&registrationStatus=A"

# Request CSV extract
curl "https://api.sam.gov/entity-information/v3/entities?api_key=YOUR_KEY&registrationStatus=A&format=csv"

# Sensitive POST with Basic Auth
curl -X POST "https://api.sam.gov/entity-information/v3/entities?ueiSAM=FJFPKQEAAAW5" \
  -H "X-Api-Key: YOUR_API_KEY" \
  -H "Authorization: Basic $(echo -n 'user:pass' | base64)" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json"

# Download async extract file
curl "https://api.sam.gov/entity-information/v3/download-entities?token=YOUR_TOKEN&api_key=YOUR_KEY" --output entities.zip
```

---

## 16. ADDITIONAL RESOURCES

| Resource | URL |
|---------|-----|
| Official API Documentation | https://open.gsa.gov/api/entity-api/ |
| OpenAPI Specification (YAML) | https://open.gsa.gov/api/entity-api/v1/openapi.yaml |
| SAM.gov API Key | https://sam.gov/workspace/profile/account-details |
| SAM.gov Help | https://sam.gov/content/entity-information |
| GSA Open Technology | https://open.gsa.gov/api/ |
| Contact/Support | https://www.fsd.gov (SAM.gov Federal Service Desk) |

---

*Documentation built from: official GSA open.gsa.gov API docs + OpenAPI 3.0.1 spec.*
*Live endpoint tested: July 2026. Requires real SAM.gov API key for actual data access.*
*Recommended version for all new integrations: v3 or v4.*
