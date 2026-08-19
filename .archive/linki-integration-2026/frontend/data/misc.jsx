export const pipelineStages = [
  { key: 'leads', label: 'New Leads', count: 120, icon: 'Users', color: 'sky' },
  { key: 'research', label: 'Research', count: 85, icon: 'Search', color: 'brand' },
  { key: 'proposal', label: 'Proposal Sent', count: 42, icon: 'FileText', color: 'violet' },
  { key: 'interested', label: 'Interested', count: 18, icon: 'Heart', color: 'amber' },
  { key: 'negotiation', label: 'Negotiation', count: 9, icon: 'Handshake', color: 'teal' },
  { key: 'won', label: 'Won', count: 14, icon: 'Trophy', color: 'emerald' },
];

export const emailPerformance = [
  { day: 'Mon', sent: 320, opened: 180, clicked: 80, replied: 24 },
  { day: 'Tue', sent: 450, opened: 240, clicked: 110, replied: 35 },
  { day: 'Wed', sent: 390, opened: 210, clicked: 95, replied: 28 },
  { day: 'Thu', sent: 480, opened: 280, clicked: 130, replied: 42 },
  { day: 'Fri', sent: 510, opened: 310, clicked: 150, replied: 48 },
  { day: 'Sat', sent: 120, opened: 70, clicked: 25, replied: 8 },
  { day: 'Sun', sent: 90, opened: 50, clicked: 15, replied: 5 }
];

export const matchDistribution = [
  { label: 'High (80%+)', value: 124, color: '#6366f1' },
  { label: 'Medium (50-80%)', value: 345, color: '#a855f7' },
  { label: 'Low (<50%)', value: 82, color: '#cbd5e1' }
];

export const revenueTrend = [
  { month: 'Jan', revenue: 0.8 },
  { month: 'Feb', revenue: 1.1 },
  { month: 'Mar', revenue: 1.5 },
  { month: 'Apr', revenue: 1.9 },
  { month: 'May', revenue: 2.2 },
  { month: 'Jun', revenue: 2.45 }
];

export const aiAccuracy = [
  { month: 'Jan', accuracy: 91 },
  { month: 'Feb', accuracy: 93 },
  { month: 'Mar', accuracy: 92 },
  { month: 'Apr', accuracy: 94 },
  { month: 'May', accuracy: 96 },
  { month: 'Jun', accuracy: 97 }
];

export const conversionFunnel = [
  { stage: 'Leads', value: 500 },
  { stage: 'Research', value: 380 },
  { stage: 'Proposal Sent', value: 240 },
  { stage: 'Negotiation', value: 110 },
  { stage: 'Won', value: 35 }
];

export const teamUsers = [
  { id: 1, name: 'John Doe', seed: 'john', role: 'Administrator', email: 'john.doe@orbitavanya.com' },
  { id: 2, name: 'Sarah Connor', seed: 'sarah', role: 'Proposal Writer', email: 'sarah.c@orbitavanya.com' },
  { id: 3, name: 'Michael Scott', seed: 'michael', role: 'Contract Specialist', email: 'm.scott@orbitavanya.com' },
  { id: 4, name: 'Pam Beesly', seed: 'pam', role: 'Business Development', email: 'pam.b@orbitavanya.com' }
];

export const tasks = [
  { id: 1, title: 'Review GSA AI Assistant RFP requirements', due: 'Today', assigneeId: 2, done: false },
  { id: 2, title: 'Draft Executive Summary for FAA Cybersecurity proposal', due: 'Tomorrow', assigneeId: 2, done: false },
  { id: 3, title: 'Schedule sync call with Hope Pulse Foundation', due: 'In 2 days', assigneeId: 4, done: false },
  { id: 4, title: 'Upload past performance documents to system database', due: 'Next week', assigneeId: 3, done: true },
  { id: 5, title: 'Export monthly pipeline metrics for board review', due: 'Next week', assigneeId: 1, done: false }
];

export const proposals = [
  {
    id: 1,
    title: 'Executive Summary & Tech Approach - GSA AI Assistant',
    company: 'OrbitAvanya Tech',
    tender: 'Generative AI Assistant (GSA)',
    status: 'Draft',
    progress: 45,
    updated: '2 hours ago'
  },
  {
    id: 2,
    title: 'FAA Cybersecurity Network Security Volume',
    company: 'OrbitAvanya Tech',
    tender: 'Enterprise Cybersecurity Upgrade (FAA)',
    status: 'In Review',
    progress: 85,
    updated: 'Yesterday'
  },
  {
    id: 3,
    title: 'Cloud Infrastructure Transition Plan - Veterans Affairs',
    company: 'OrbitAvanya Tech',
    tender: 'Cloud Infrastructure Migration (VA)',
    status: 'Submitted',
    progress: 100,
    updated: '3 days ago'
  }
];

export const campaigns = [
  {
    id: 1,
    name: 'Q2 Procurement Officers Outreach',
    status: 'Running',
    sent: 1200,
    opened: 720,
    clicked: 310,
    replied: 98,
    created: '2026-05-01'
  },
  {
    id: 2,
    name: 'Healthcare IT Deciders Campaign',
    status: 'Completed',
    sent: 2500,
    opened: 1350,
    clicked: 490,
    replied: 145,
    created: '2026-04-12'
  },
  {
    id: 3,
    name: 'State and Local Opportunity Intro',
    status: 'Paused',
    sent: 500,
    opened: 270,
    clicked: 56,
    replied: 12,
    created: '2026-05-10'
  }
];

export const websiteEngagement = [
  {
    id: 1,
    company: 'GREAT LAKES HOMES LLC',
    campaign: 'Q2 Procurement Officers Outreach',
    timeActive: '4m 32s',
    pagesViewed: 3,
    pages: ['Home', 'AI Capabilities', 'Contact Us'],
    lastVisit: '3 hours ago'
  },
  {
    id: 2,
    company: 'ACIOE FOUNDATION',
    campaign: 'Healthcare IT Deciders Campaign',
    timeActive: '8m 15s',
    pagesViewed: 5,
    pages: ['Home', 'Services', 'Pricing', 'Case Studies', 'Schedule Demo'],
    lastVisit: '5 hours ago'
  },
  {
    id: 3,
    company: 'HAUS OF THREAD LLC',
    campaign: 'Q2 Procurement Officers Outreach',
    timeActive: '1m 45s',
    pagesViewed: 2,
    pages: ['Home', 'AI Capabilities'],
    lastVisit: 'Yesterday'
  }
];

export const meetings = [
  {
    id: 1,
    title: 'Initial Discovery Call',
    with: 'HOPE PULSE FOUNDATION',
    date: '2026-07-16',
    time: '14:00',
    type: 'Video Call',
    provider: 'google'
  },
  {
    id: 2,
    title: 'RFP Proposal Review and Q&A',
    with: 'V42 MANAGEMENT CONSULTING INC',
    date: '2026-07-18',
    time: '11:30',
    type: 'Video Call',
    provider: 'google'
  },
  {
    id: 3,
    title: 'Technical Scoping Sync',
    with: 'Scientific Cyber Security Association',
    date: '2026-07-22',
    time: '16:00',
    type: 'Video Call',
    provider: 'outlook'
  }
];
