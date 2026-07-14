export const tenders = [
  {
    id: "1",
    title: "AI-Powered Technical Proposal Compactor and Analyser Platform",
    category: "Software Development",
    match: 98,
    description: "Seeking a qualified AI development vendor to build a machine learning pipeline that parses, indexes, and extracts key structured variables from large Government RFP/Tender PDFs, then matches them against organizational capability indexes and draft proposals.",
    agency: "Department of Commerce",
    value: "$1.2M",
    postedDate: "2026-05-10",
    closingDate: "2026-08-30",
    status: "Open",
    rfpUrl: "https://sam.gov/opp/ai-tender-compactor-001/view"
  },
  {
    id: "2",
    title: "Enterprise Cybersecurity Network Upgrade and Monitoring",
    category: "Cybersecurity",
    match: 94,
    description: "Requirement for full upgrade of firewalls, network switches, and implementation of zero-trust network access (ZTNA) with 24/7 security operations center (SOC) monitoring and compliance logging.",
    agency: "Federal Aviation Administration",
    value: "$3.5M",
    postedDate: "2026-05-15",
    closingDate: "2026-08-15",
    status: "Open",
    rfpUrl: "https://sam.gov/opp/faa-cyber-upgrade-2026/view"
  },
  {
    id: "3",
    title: "Cloud Infrastructure Migration & Managed Services",
    category: "Cloud Computing",
    match: 86,
    description: "Migration of legacy on-premise systems to a secure AWS GovCloud environment. The contractor will be responsible for architecture design, data migration, and subsequent managed service support.",
    agency: "Department of Veterans Affairs",
    value: "$850K",
    postedDate: "2026-05-01",
    closingDate: "2026-07-28",
    status: "Open",
    rfpUrl: "https://sam.gov/opp/va-cloud-migration/view"
  },
  {
    id: "4",
    title: "Health IT Systems Integration and Data Interoperability Support",
    category: "Healthcare IT",
    match: 82,
    description: "Support for integrating health information exchange platforms across federal and state databases. Vendor must comply with HL7 FHIR standards and ensure complete HIPAA-compliant transport layers.",
    agency: "Centers for Medicare & Medicaid Services",
    value: "$2.1M",
    postedDate: "2026-04-20",
    closingDate: "2026-06-25",
    status: "Closed",
    rfpUrl: "https://sam.gov/opp/cms-hit-integration/view"
  },
  {
    id: "5",
    title: "Generative AI Assistant for Procurement Officer Support",
    category: "Artificial Intelligence",
    match: 96,
    description: "Development of a secure, offline-capable large language model (LLM) chatbot to assist contract officers in querying internal federal procurement regulations (FAR) and guidelines.",
    agency: "General Services Administration",
    value: "$450K",
    postedDate: "2026-05-18",
    closingDate: "2026-09-10",
    status: "Open",
    rfpUrl: "https://sam.gov/opp/gsa-ai-assistant/view"
  },
  {
    id: "6",
    title: "Mobile App Development for Visitor Portal",
    category: "Software Development",
    match: 75,
    description: "Development of companion iOS and Android mobile apps for the official visitor portal, including offline interactive maps, ticketing integration, and push notification alerts.",
    agency: "National Park Service",
    value: "$290K",
    postedDate: "2026-05-02",
    closingDate: "2026-08-01",
    status: "Open",
    rfpUrl: "https://sam.gov/opp/nps-visitor-app/view"
  },
  {
    id: "7",
    title: "Decentralized Database Syncing for Emergency Services",
    category: "Database Services",
    match: 88,
    description: "Looking for an architectural solution for edge syncing databases during disaster response events where internet connectivity is intermittent. Peer-to-peer sync protocols preferred.",
    agency: "Federal Emergency Management Agency",
    value: "$1.8M",
    postedDate: "2026-05-05",
    closingDate: "2026-08-20",
    status: "Open",
    rfpUrl: "https://sam.gov/opp/fema-db-sync/view"
  }
];

export function daysUntilClosing(dateStr) {
  if (!dateStr) return 0;
  const closing = new Date(dateStr);
  const now = new Date();
  
  // Set times to midnight to calculate full calendar days
  closing.setHours(0, 0, 0, 0);
  now.setHours(0, 0, 0, 0);
  
  const diffTime = closing.getTime() - now.getTime();
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  return Number.isNaN(diffDays) ? 0 : diffDays;
}
