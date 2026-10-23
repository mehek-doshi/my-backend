/* =====================================================================
   Tech Radar — front end (HTML + CSS + vanilla JS, no build step)
   ---------------------------------------------------------------------
   Open index.html in a browser. All data is mock data kept in the browser
   (localStorage) so every screen and rule can be tried without a backend.
   Where a backend call will go later, look for the  API:  comments.

   Simplified version.
   Roles: Admin and Contributor only (the Moderator role was merged into Admin).
   Admins see only the admin console. Contributors see only the dashboard,
   new use case and project artifacts pages.
   Removed on request: suggested use case on the dashboard, "Your progress",
   use case status, your submissions, findings and feedback, the SharePoint bar,
   overview, relevance, priority, pause, recent runs, topic review, volunteer
   stats, scheduling, visibility, request changes, users and roles, the
   certificate template, analytics and the audit log. "Award badge" and
   "New badge" are hidden for now (see HIDDEN below).

   Demo accounts (Sign in with Microsoft): Aarav = Admin, Priya = Contributor,
   plus a personal account to see the "outside tenant" denial.
   ===================================================================== */
(function () {
'use strict';

/* ---------------------------------------------------------------- utils */
var DAY = 86400000, HOUR = 3600000, MIN = 60000;
var $ = function (s, r) { return (r || document).querySelector(s); };
var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
function uid(p) { return p + Math.random().toString(36).slice(2, 8); }
function now() { return Date.now(); }
function ago(ts) {
  var d = now() - ts; if (d < 0) d = 0;
  if (d < MIN) return 'just now';
  if (d < HOUR) return Math.floor(d / MIN) + ' min ago';
  if (d < DAY) return Math.floor(d / HOUR) + 'h ago';
  if (d < 7 * DAY) return Math.floor(d / DAY) + 'd ago';
  if (d < 30 * DAY) return Math.floor(d / (7 * DAY)) + 'w ago';
  return Math.floor(d / (30 * DAY)) + ' mo ago';
}
function ageShort(ts) { // "2 days ago" style for tables
  var d = now() - ts;
  if (d < HOUR) return Math.max(1, Math.floor(d / MIN)) + ' min ago';
  if (d < DAY) return Math.floor(d / HOUR) + ' hours ago';
  if (d < 7 * DAY) { var n = Math.floor(d / DAY); return n + (n === 1 ? ' day ago' : ' days ago'); }
  var w = Math.floor(d / (7 * DAY)); return w + (w === 1 ? ' week ago' : ' weeks ago');
}
var MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function dShort(ts) { var d = new Date(ts); return ('0' + d.getDate()).slice(-2) + ' ' + MON[d.getMonth()]; }
function dLong(ts) { var d = new Date(ts); return ('0' + d.getDate()).slice(-2) + ' ' + MON[d.getMonth()] + ' ' + d.getFullYear(); }
function tTime(ts) { var d = new Date(ts); return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2); }
function whenLabel(ts) {
  var d = new Date(ts), n = new Date(), y = new Date(now() - DAY);
  if (d.toDateString() === n.toDateString()) return 'Today ' + tTime(ts);
  if (d.toDateString() === y.toDateString()) return 'Yesterday ' + tTime(ts);
  return dShort(ts) + ' ' + tTime(ts);
}
function startOfDay(ts) { var d = new Date(ts); d.setHours(0, 0, 0, 0); return d.getTime(); }
function daysUntil(ts) { return Math.ceil((startOfDay(ts) - startOfDay(now())) / DAY); }
function plural(n, a, b) { return n + ' ' + (n === 1 ? a : (b || a + 's')); }
function initials(n) { return n.split(' ').map(function (p) { return p[0]; }).slice(0, 2).join('').toUpperCase(); }
function slug(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }
function fmtSize(b) { return b >= 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB'; }

/* ---------------------------------------------------------------- icons */
var I = {
  grid: '<path d="M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  home: '<path d="m3 11 9-8 9 8v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',
  radar: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.5"/><path d="M12 12 19 6"/>',
  check: '<path d="m4 12 5 5L20 6"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
  cal: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  shield: '<path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5z"/><path d="m9 12 2 2 4-4"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  award: '<circle cx="12" cy="9" r="6"/><path d="m8.5 14-1.5 8 5-3 5 3-1.5-8"/>',
  chart: '<path d="M3 3v18h18"/><path d="M7 15v3M12 10v8M17 6v12"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  bell: '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0"/>',
  out: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  back: '<path d="M19 12H5M12 19l-7-7 7-7"/>',
  chev: '<path d="m6 9 6 6 6-6"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>'
};
function icon(n, cls) { return '<svg class="' + (cls || '') + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + I[n] + '</svg>'; }

/* ------------------------------------------------ logo + 3D badge art */
var LOGO = '<svg viewBox="0 0 48 48" aria-label="Neuleap"><rect width="48" height="48" rx="12" fill="#fff"/><path transform="translate(9 8)" fill="#857ffa" d="M8.1 3.7 14.4.5 17.9 2c1.3.8 10.9 5.8 11 6.6.4 1.9.1 4.3.1 6.2 0 3.1.2 6.3-.1 9.4l-7.3 3.9-5.4 3.3-1.5.7-7-3.7L.1 24.2C0 19 .3 13.4 0 8.3z"/><path transform="translate(17.1 8)" fill="#030204" d="M0 3.7 6.2.5 6.8 0l3 2 11 6.6c.4 1.9.1 4.3.1 6.2 0 3.1.2 6.3-.1 9.4l-7.3 3.9c0-.3.3-.6.5-.9-.4-.6-.5-6.4-.1-7l-.2-.5c0-.4 0-.5.3-.8l-.3-1.5c.3-1.2-.3-3.8.4-5-.3-.5-.6-.5-.6-1l.4-.1L7.8 7.6 7 7.4 6.6 7.2l-5.2-3.6z"/><path transform="translate(23.4 25.5)" fill="#b95efa" d="M.2 5.7c.1-.4.1-.5.1-.9L.5 4.6c.3.7-.4 5 0 6 .1.3.1.5 0 .7 1 .7 4.1.1 5.1-.6.3-.2.9-.2 1.4-.5.5-.6.1-6.9.2-8.1L7.4 0c.1.4.1 1.1.3 1.5l-.3.8c.1.2.1.4.2.5-.3.6-.3 6.4.1 7-.2.3-.5.5-.5.9-1.5 1.2-3.7 2.3-5.4 3.3l-1.5.7c0-.3-.2-.6-.3-.8.4-1.1.1-5.6 0-6.9z"/><path fill="#fff" d="M24.1 15.1c0-.8.1-5.7.3-6.1 3.5 2.5 8.7 4.4 12.3 7.4l-5.6 2.9-6-3.8z"/></svg>';
function badgeSVG(c1, c2, c3, glyph) {
  var id = 'b' + Math.random().toString(36).slice(2, 7);
  return '<svg viewBox="0 0 96 100" aria-hidden="true"><defs>' +
    '<linearGradient id="' + id + 'a" x1="0.5" y1="0" x2="0.5" y2="1"><stop offset="0" stop-color="' + c1 + '"/><stop offset="1" stop-color="' + c2 + '"/></linearGradient>' +
    '<linearGradient id="' + id + 'b" x1="0.5" y1="0" x2="0.5" y2="1"><stop offset="0" stop-color="' + c2 + '"/><stop offset="1" stop-color="' + c3 + '"/></linearGradient>' +
    '<linearGradient id="' + id + 'c" x1="0.5" y1="0" x2="0.5" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".7"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>' +
    '<ellipse cx="48" cy="92" rx="34" ry="6" fill="#000" fill-opacity=".45"/>' +
    '<circle cx="48" cy="46" r="44" fill="url(#' + id + 'a)"/><circle cx="48" cy="46" r="33" fill="url(#' + id + 'b)"/>' +
    '<g transform="translate(48 46)" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">' + glyph + '</g>' +
    '<ellipse cx="48" cy="26" rx="28" ry="17" fill="url(#' + id + 'c)"/>' +
    '<ellipse cx="31.5" cy="18.5" rx="4.5" ry="2.5" transform="rotate(-25 31.5 18.5)" fill="#fff" fill-opacity=".9"/></svg>';
}
var BADGE_ART = {
  'First Volunteer': ['#8dbbff', '#0a3a9e', '#176fff', '<path d="M-7 12V-4a3 3 0 0 1 6 0v8M-1 -8a3 3 0 0 1 6 0v8M5 -6a3 3 0 0 1 6 0v10c0 8-5 12-12 12h-2c-5 0-7-3-9-5l-5-5a3 3 0 0 1 4-4l3 3"/>'],
  'Test Case Contributor': ['#7df0ae', '#0e6b33', '#22c55e', '<path d="M-8 -14h16M-6 -14v12L-14 12a4 4 0 0 0 3.5 6h21A4 4 0 0 0 14 12L6 -2v-12M-9 6h18"/>'],
  'Artifact Author': ['#ffe9a0', '#a86a12', '#fbbf24', '<path d="M-14 8V-8a3 3 0 0 1 3-3h7l4 5h11a3 3 0 0 1 3 3V8a3 3 0 0 1-3 3h-22a3 3 0 0 1-3-3z"/>'],
  'Presenter': ['#c4a8ff', '#4c1d95', '#8b5cf6', '<rect x="-14" y="-12" width="28" height="19" rx="3"/><path d="M-6 17l6-7 6 7M-14 -12h28"/>'],
  'Explorer': ['#ff9a9a', '#a12626', '#ff5959', '<circle cx="0" cy="0" r="13"/><path d="m-5 5 3-9 9-3-3 9z"/>'],
  '_default': ['#8dbbff', '#0a3a9e', '#176fff', '<path d="m0 -14 4 9 10 1-7.500 7 2 10-8.500-5-8.500 5 2-10-7.500-7 10-1z"/>']
};
function badgeArt(name) { var a = BADGE_ART[name] || BADGE_ART._default; return badgeSVG(a[0], a[1], a[2], a[3]); }

/* ------------------------------------------------------------ constants */
var STAGES = ['Study', 'POC', 'Presentation'];
var STAGE_DAYS = { Study: 14, POC: 14, Presentation: 7 }; // stage defaults (REQ-028)
var SRC_TYPES = ['Website', 'Blog', 'RSS', 'Research feed', 'GitHub'];
var ART_TYPES = ['POC', 'Architecture pattern', 'Codebase', 'Document', 'Presentation'];
var CRITERIA = [
  { id: 'volunteer', label: 'Volunteer sign-ups' }, { id: 'testcases', label: 'Test cases added' },
  { id: 'artifacts', label: 'Approved artifacts' }, { id: 'presentations', label: 'Completed presentations' },
  { id: 'topics', label: 'Topics explored' }
];
var BLOCKED_EXT = ['exe', 'dll', 'msi', 'bin', 'com', 'bat', 'cmd', 'scr', 'so', 'dylib', 'dmg', 'app', 'apk', 'jar'];
var ALLOWED_EXT = ['zip', 'pdf', 'ppt', 'pptx', 'key', 'doc', 'docx', 'md', 'txt', 'ipynb', 'xls', 'xlsx', 'csv', 'py', 'js', 'ts', 'json', 'png', 'jpg', 'jpeg'];
var MAX_UPLOAD = 100 * 1024 * 1024;
// Admin buttons that are built but hidden for now. Set to false to bring them back.
var HIDDEN = { awardBadge: true, newBadge: true };

/* ----------------------------------------------------------- seed data */
function seed() {
  var t = now();
  var U = [
    ['u1', 'Aarav Mehta', 'Engineering', 'Admin', 'Today', 'Active', 'Software Engineer'],
    ['u2', 'Priya Sharma', 'Data', 'Contributor', 'Today', 'Active', 'Data Engineer'],
    ['u3', 'Nikhil Kapoor', 'Data', 'Contributor', 'Yesterday', 'Active', 'Data Scientist'],
    ['u4', 'Rhea Khanna', 'AI', 'Contributor', '2 days ago', 'Active', 'ML Engineer'],
    ['u5', 'Dev Bhatt', 'Cloud', 'Contributor', '3 days ago', 'Active', 'Cloud Engineer'],
    ['u6', 'Meera Tiwari', 'Data', 'Admin', 'Today', 'Active', 'Data Lead'],
    ['u7', 'Arjun Rao', 'Sales Engineering', 'Contributor', '1 week ago', 'Active', 'Solutions Engineer'],
    ['u8', 'Karan Verma', 'Engineering', 'Contributor', '12 Sep', 'Deactivated', 'Software Engineer'],
    ['u9', 'Rohan Kulkarni', 'Engineering', 'Contributor', 'Today', 'Active', 'Software Engineer'],
    ['u10', 'Sana Joshi', 'Data', 'Contributor', '2 days ago', 'Active', 'Analyst'],
    ['u11', 'Tara Nair', 'AI', 'Contributor', '4 days ago', 'Active', 'Researcher'],
    ['u12', 'Ishan Patel', 'Cloud', 'Contributor', '5 days ago', 'Active', 'DevOps Engineer'],
    ['u13', "Leo D'Souza", 'Engineering', 'Contributor', '1 week ago', 'Active', 'Software Engineer'],
    ['u14', 'Zoya Ali', 'AI', 'Contributor', '3 days ago', 'Active', 'ML Engineer']
  ].map(function (r) { return { id: r[0], name: r[1], email: r[1].toLowerCase().replace(/[^a-z ]/g, '').replace(' ', '.') + '@neuleap.ai', team: r[2], role: r[3], last: r[4], status: r[5], title: r[6] }; });

  var cats = ['Agentic AI', 'Data Engineering', 'Small Language Models', 'Cloud & Infra'].map(function (n, i) { return { id: 'c' + (i + 1), name: n, retired: false }; });

  var sources = [
    ['Hacker News · AI', 'Website', 10 * MIN], ['LangChain blog', 'Blog', HOUR], ['arXiv cs.AI', 'Research feed', 3 * HOUR],
    ['GitHub trending · Python', 'GitHub', 6 * HOUR], ['Snowflake release notes', 'RSS', DAY], ['Databricks blog', 'Blog', DAY]
  ].map(function (s, i) {
    return { id: 's' + (i + 1), name: s[0], type: s[1], url: 'https://example.com/' + slug(s[0]), last: t - s[2], error: i === 4 ? 'Source could not be reached after 3 retries' : '' };
  });

  function art(title, url) { return { title: title, url: url || 'https://example.com/' + slug(title) }; }
  function topic(id, title, cat, ageD, nSrc, sum, vols, o) {
    o = o || {};
    return {
      id: id, title: title, category: cat, status: 'approved', origin: o.origin || 'agent', detectedAt: t - ageD * DAY, sources: nSrc, summary: sum,
      articles: o.articles || [art('Official announcement and docs'), art('Hands-on walkthrough'), art('Community discussion')],
      testCases: o.testCases || [], suggestion: o.suggestion || '', lowCost: !!o.lowCost, requestedBy: o.requestedBy || '',
      volunteers: vols || [], waitlist: [], stage: o.stage || (vols && vols.length ? 'Study' : ''), deadline: o.deadline == null ? null : t + o.deadline * DAY,
      deliverable: o.deliverable !== false, lastActivity: t - (o.idle == null ? 1 : o.idle) * DAY, presented: []
    };
  }
  var topics = [
    topic('t1', 'Durable multi-agent workflows with LangGraph', 'Agentic AI', 2, 6, 'Agents can pause, persist state and resume after failures or human approval, which makes long-running workflows practical.', ['u2', 'u9', 'u3'],
      { stage: 'Presentation', deadline: 3, deliverable: true, articles: [art('LangGraph persistence and checkpointers'), art('Building human-in-the-loop agents'), art('Durable execution explained')],
        testCases: [{ title: 'Support triage with an approval step', url: 'https://example.com/tc-triage', author: 'u2', at: t - 9 * DAY }, { title: 'Research agent that resumes after a crash', url: 'https://example.com/tc-resume', author: 'u2', at: t - 7 * DAY }, { title: 'Approval timeout handling', url: 'https://example.com/tc-timeout', author: 'u2', at: t - 5 * DAY }],
        suggestion: 'Build an internal ticket-triage agent that pauses for manager approval and resumes from the last completed step after a failure.' }),
    topic('t2', 'Fine-tuning Qwen small models with LoRA', 'Small Language Models', 5, 5, 'Compact open models now match larger ones on narrow enterprise tasks at a fraction of the cost.', [], { idle: 5, suggestion: 'Fine-tune a 1.5B model on our support tickets and compare cost and accuracy with a hosted model.' }),
    topic('t3', 'Amazon Bedrock AgentCore managed runtime', 'Cloud & Infra', 7, 7, 'Managed runtime, memory and identity for agents on AWS. Costly to run, so a low-cost simulation approach is suggested.', ['u5'],
      { stage: 'Presentation', deadline: -5, deliverable: false, lowCost: true, idle: 6, suggestion: 'Simulate the AgentCore runtime locally with queues and a mocked model, then compare latency and cost against the managed service.' }),
    topic('t4', 'Snowflake Cortex AISQL for unstructured data', 'Data Engineering', 16, 4, 'Run LLM-powered classification and extraction inside SQL pipelines without moving data out of the warehouse.', ['u3', 'u10'], { stage: 'POC', deadline: 11, idle: 15 }),
    topic('t5', 'Databricks Agent Bricks', 'Data Engineering', 9, 3, 'Describe the task and let the platform build, evaluate and tune an agent against your data.', ['u10', 'u7', 'u11'], { stage: 'Study', deadline: 2, deliverable: false, idle: 2 }),
    topic('t6', 'MCP servers for enterprise data', 'Agentic AI', 11, 6, 'The Model Context Protocol gives agents a standard way to reach internal systems with scoped permissions.', ['u4', 'u11', 'u12', 'u13', 'u14', 'u8'], { stage: 'Study', deadline: 21, idle: 3 }),
    topic('t7', 'Vector search with pgvector', 'Data Engineering', 13, 3, 'Store and query embeddings next to relational data using a Postgres extension.', ['u3', 'u13'], { stage: 'Study', deadline: 27, idle: 4 })
  ];

  var invitations = [
    { id: 'i3', userId: 'u2', topicId: 't6', by: 'u1', at: t - 8 * DAY, status: 'pending' },
    { id: 'i4', userId: 'u2', topicId: 't2', by: 'u1', at: t - 2 * HOUR, status: 'pending' },
    { id: 'i5', userId: 'u2', topicId: 't5', by: 'u1', at: t - 5 * HOUR, status: 'pending' }
  ];

  var artifacts = [
    ['a1', 'Event-driven agent pipeline on AWS', 'Architecture pattern', 'u2', 14, 'Reference architecture for running Bedrock agents with queues and a low-cost simulation layer.'],
    ['a2', 'Cortex AISQL ticket classifier', 'Codebase', 'u3', 18, 'Codebase and notebook for classifying support tickets inside Snowflake.'],
    ['a3', 'LangGraph approval workflow', 'POC', 'u2', 24, 'Pause-and-resume agent with human approval, including the test cases.'],
    ['a4', 'Qwen LoRA tuning notes', 'Document', 'u4', 28, 'Hyperparameters, GPU cost and evaluation results for a 1.5B model.'],
    ['a5', 'RAG ingestion for SharePoint', 'Architecture pattern', 'u3', 36, 'Chunking, metadata and permission-aware retrieval across company documents.'],
    ['a6', 'Agent Bricks demo slides', 'Presentation', 'u7', 42, 'Slides and recording from the internal demo, with lessons learned.']
  ].map(function (a) { return { id: a[0], title: a[1], type: a[2], authorId: a[3], at: t - a[4] * DAY, summary: a[5], approved: true }; });

  var queue = [
    ['q1', 'Support triage with approval step', 'Use case', 'u9', 2, [], 'Use case · includes code upload', 't1'],
    ['q2', 'Bedrock queue-based agent runner', 'Architecture pattern', 'u2', 2, ['client'], 'Architecture pattern', null],
    ['q3', 'Snowflake PII masking notebook', 'Codebase', 'u3', 3, ['secret'], 'Codebase · 14 files', null],
    ['q4', 'Qwen LoRA cost notes', 'Document', 'u4', 4, [], 'Document', null],
    ['q5', 'RAG ingestion v2', 'Architecture pattern', 'u4', 5, ['duplicate'], 'Architecture pattern', null],
    ['q6', 'Agent Bricks demo slides v2', 'Presentation', 'u7', 7, [], 'Presentation', null]
  ].map(function (q) {
    var fl = { client: 'Flagged: mentions a client environment', secret: 'Flagged: secret detected in config.py (API key)', duplicate: 'Possible duplicate of an existing artifact' };
    return { id: q[0], title: q[1], type: q[2], authorId: q[3], at: t - q[4] * DAY, flags: q[5].map(function (k) { return { kind: k, text: fl[k] }; }), note: q[6], useCaseId: null, topicId: q[7], status: 'pending', summary: '' };
  });

  var badges = [
    { id: 'b1', name: 'First Volunteer', desc: 'Volunteer for a topic for the first time', criterion: 'volunteer', threshold: 1 },
    { id: 'b2', name: 'Test Case Contributor', desc: 'Add test cases to topics', criterion: 'testcases', threshold: 3 },
    { id: 'b3', name: 'Artifact Author', desc: 'Upload artifacts to the shared library', criterion: 'artifacts', threshold: 1 },
    { id: 'b4', name: 'Presenter', desc: 'Present a proof of concept to the office', criterion: 'presentations', threshold: 1 },
    { id: 'b5', name: 'Explorer', desc: 'Volunteer across several technologies', criterion: 'topics', threshold: 5 }
  ];
  var userBadges = { u2: [{ badge: 'b1', at: t - 37 * DAY }, { badge: 'b2', at: t - 29 * DAY }, { badge: 'b3', at: t - 18 * DAY }] };
  var certs = [
    { id: 'ce1', userId: 'u2', title: 'Agentic AI Explorer', topic: 'LangGraph checkpointing', at: t - 27 * DAY },
    { id: 'ce2', userId: 'u2', title: 'Data Engineering Contributor', topic: 'Cortex AISQL proof of concept', at: t - 11 * DAY }
  ];

  return {
    v: 4, session: null, users: U, categories: cats, sources: sources, topics: topics, invitations: invitations, artifacts: artifacts, queue: queue,
    badges: badges, userBadges: userBadges, certs: certs, useCases: [], drafts: {}, notifications: [],
    include: ['agent', 'LLM', 'RAG', 'fine-tuning'], exclude: ['crypto', 'hiring', 'funding'],
    settings: { expiryDays: 7, reminderDays: 3, maxVol: 5, retentionMonths: 12 },
    integrations: { SharePoint: true, 'Microsoft Teams': true, Email: true }
  };
}

/* --------------------------------------------------------------- state */
var KEY = 'techradar.demo.v4';
var S;
function load() {
  try { var raw = localStorage.getItem(KEY); if (raw) { var o = JSON.parse(raw); if (o && o.v === 4) return o; } } catch (e) { /* storage unavailable */ }
  return seed();
}
function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* ignore */ } }
S = load();
var UI = { collapsed: false, openTopic: null, filterCat: 'All', libType: 'All', libQ: '', profile: false, bell: false, modal: null, tab: {}, rev: {}, flt: {} };

/* ------------------------------------------------------------- helpers */
function user(id) { return S.users.filter(function (u) { return u.id === id; })[0]; }
function me() { return S.session ? user(S.session) : null; }
function role() { var u = me(); return u ? u.role : null; }
function isAdmin() { return role() === 'Admin'; }
function contributors() { return S.users.filter(function (u) { return u.role === 'Contributor' && u.status === 'Active'; }); }
function topic(id) { return S.topics.filter(function (t) { return t.id === id; })[0]; }
function catNames() { return S.categories.filter(function (c) { return !c.retired; }).map(function (c) { return c.name; }); }
function nameOf(id) { var u = user(id); return u ? u.name : 'Someone'; }
function short(id) { var u = user(id); if (!u) return 'Someone'; var p = u.name.split(' '); return p[0] + ' ' + p[1][0] + '.'; }
function audit() { /* API: the backend records the audit trail; there is no audit screen in this front end */ }
function notify(to, text) {
  var ids = Array.isArray(to) ? to : [to];
  ids.forEach(function (id) { S.notifications.unshift({ id: uid('n'), to: id, text: text, at: now(), read: false }); });
}
function admins() { return S.users.filter(function (u) { return u.role === 'Admin' && u.status === 'Active'; }).map(function (u) { return u.id; }); }
function activeUsers() { return S.users.filter(function (u) { return u.status === 'Active'; }); }
function approved() { return S.topics.filter(function (t) { return t.status === 'approved'; }); }

/* topic status, in the order given by the BRD (REQ-024, REQ-027, REQ-029) */
function topicStatus(t) {
  var n = t.volunteers.length;
  if (!n) return { key: 'needs', text: 'Needs a volunteer', tone: 'yellow' };
  if (n > S.settings.maxVol) return { key: 'cap', text: 'Over the cap of ' + S.settings.maxVol, tone: 'red' };
  if (t.deadline != null) {
    var d = daysUntil(t.deadline);
    if (d < 0) return { key: 'overdue', text: 'Overdue by ' + plural(-d, 'day'), tone: 'red' };
    if (d <= 3 && !t.deliverable) return { key: 'risk', text: 'At risk', tone: 'yellow' };
  }
  return { key: 'ok', text: 'On track', tone: 'green' };
}
function chip(text, tone) { return '<span class="chip ' + (tone || '') + '">' + esc(text) + '</span>'; }

/* badge progress & automatic awards (REQ-059) */
function stat(uidv, crit) {
  if (crit === 'volunteer') return S.topics.filter(function (t) { return t.volunteers.indexOf(uidv) > -1; }).length;
  if (crit === 'topics') return S.topics.filter(function (t) { return t.volunteers.indexOf(uidv) > -1; }).length;
  if (crit === 'testcases') return S.topics.reduce(function (n, t) { return n + t.testCases.filter(function (c) { return c.author === uidv; }).length; }, 0);
  if (crit === 'artifacts') return S.artifacts.filter(function (a) { return a.authorId === uidv && a.approved; }).length;
  if (crit === 'presentations') return S.topics.filter(function (t) { return t.presented && t.presented.indexOf(uidv) > -1; }).length;
  return 0;
}
function has(uidv, bid) { return (S.userBadges[uidv] || []).some(function (b) { return b.badge === bid; }); }
function award(uidv, bid, manual) {
  if (has(uidv, bid)) return false;
  (S.userBadges[uidv] = S.userBadges[uidv] || []).push({ badge: bid, at: now() });
  var b = S.badges.filter(function (x) { return x.id === bid; })[0];
  notify(uidv, 'You earned the "' + b.name + '" badge.');
  audit(manual ? 'Awarded a badge manually' : 'Awarded a badge', b.name + ' to ' + short(uidv), manual ? undefined : 'System');
  if (me() && uidv === me().id) toast('Badge earned: ' + b.name, 'ok');
  return true;
}
function checkBadges(uidv) { S.badges.forEach(function (b) { if (stat(uidv, b.criterion) >= b.threshold) award(uidv, b.id); }); }



/* ------------------------------------------------------- toast & modal */
function toast(msg, tone) {
  var box = $('#toasts'); if (!box) return;
  var el = document.createElement('div'); el.className = 'toast ' + (tone || ''); el.textContent = msg; box.appendChild(el);
  setTimeout(function () { el.remove(); }, 4200);
}
function openModal(o) {
  closeModal();
  var el = document.createElement('div'); el.className = 'scrim'; el.id = 'modal-root';
  el.innerHTML = '<div class="modal ' + (o.wide ? 'wide' : '') + '" role="dialog" aria-modal="true" aria-label="' + esc(o.title) + '"><h2>' + esc(o.title) + '</h2>' +
    (o.sub ? '<p class="modal-sub">' + esc(o.sub) + '</p>' : '') + '<div class="modal-body">' + o.body + '</div>' +
    '<div class="modal-foot">' + (o.actions || [{ label: 'Close', cls: 'secondary' }]).map(function (a, i) {
      return '<button class="btn ' + (a.cls || '') + '" data-mbtn="' + i + '">' + esc(a.label) + '</button>';
    }).join('') + '</div></div>';
  document.body.appendChild(el);
  el.addEventListener('mousedown', function (e) { if (e.target === el) closeModal(); });
  $$('[data-mbtn]', el).forEach(function (b) {
    b.addEventListener('click', function () {
      var a = (o.actions || [{}])[+b.getAttribute('data-mbtn')];
      var r = a.fn ? a.fn(el) : undefined;
      if (r !== false) closeModal();
    });
  });
  if (o.onOpen) o.onOpen(el);
  var f = $('input,select,textarea', el); if (f) f.focus();
}
function closeModal() { var m = $('#modal-root'); if (m) m.remove(); }
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { closeModal(); if (UI.profile || UI.bell) { UI.profile = UI.bell = false; render(); } } });

/* --------------------------------------------------------------- router */
function route() {
  var h = (location.hash || '').replace(/^#\/?/, ''), q = {};
  var qi = h.indexOf('?'); if (qi > -1) { h.slice(qi + 1).split('&').forEach(function (p) { var kv = p.split('='); q[kv[0]] = decodeURIComponent(kv[1] || ''); }); h = h.slice(0, qi); }
  return { name: h || 'dashboard', q: q };
}
function go(name) { if (location.hash === '#/' + name) render(); else location.hash = '#/' + name; }
window.addEventListener('hashchange', function () { closeModal(); UI.profile = UI.bell = false; render(); window.scrollTo(0, 0); });

var ADMIN_NAV = [
  ['admin/discovery', 'Discovery Agent', 'radar'], ['admin/volunteers', 'Volunteers', 'users'], ['moderation', 'Moderation', 'shield'],
  ['admin/badges', 'Badges & Certificates', 'award'], ['admin/settings', 'Settings', 'gear']
];
function homeRoute() { return isAdmin() ? 'admin/discovery' : 'dashboard'; }

/* ---------------------------------------------------------------- shell */
function render() {
  var app = $('#app'); if (!app) return;
  var u = me();
  if (!u) { app.innerHTML = signinView(); return; }
  var r = route(), adm = isAdmin();
  // Admins only ever see the admin console; anything else sends them back to it.
  if (adm && !ADMIN_NAV.some(function (n) { return n[0] === r.name; })) { location.hash = '#/' + homeRoute(); return; }
  var view = renderView(r);
  var nav, pending = S.queue.filter(function (q) { return q.status === 'pending'; }).length;
  if (adm) {
    nav = ADMIN_NAV.map(function (n) { return navItem(n[0], n[1], n[2], r.name, n[0] === 'moderation' ? pending : 0); }).join('');
  } else {
    nav = navItem('dashboard', 'Dashboard', 'grid', r.name) + navItem('new-use-case', 'New Use Case', 'plus', r.name) + navItem('artifacts', 'Project Artifacts', 'folder', r.name);
  }
  var unread = S.notifications.filter(function (n) { return n.to === u.id && !n.read; }).length;
  app.innerHTML =
    '<div class="shell ' + (UI.collapsed ? 'collapsed' : '') + '">' +
    '<aside class="sidebar" aria-label="Main navigation"><div class="brand"><div class="logo">' + LOGO + '</div><div><b>Tech Radar</b><small>' + (adm ? 'ADMIN CONSOLE' : '@NEULEAP.AI') + '</small></div></div>' +
    '<nav class="nav">' + nav + '</nav>' +
    '<div class="sidebar-foot"><button class="nav-item" data-act="signout">' + icon('out') + '<span>Sign out</span></button><div class="who">' + esc(u.email) + '</div></div></aside>' +
    '<main class="main"><header class="topbar"><button class="icon-btn" data-act="collapse" aria-label="Collapse sidebar" title="Collapse sidebar" style="margin-top:2px">' + icon('menu') + '</button>' +
    '<div class="titles">' + (view.crumbs || '') + '<h1>' + esc(view.title) + '</h1>' + (view.sub ? '<p class="sub">' + esc(view.sub) + '</p>' : '') + '</div>' +
    '<div class="top-actions">' + (view.action || '') +
    '<button class="icon-btn" data-act="bell" aria-label="Notifications">' + icon('bell') + (unread ? '<span class="dot">' + unread + '</span>' : '') + '</button>' +
    '<button class="avatar btn" data-act="profile" aria-label="Open profile" aria-expanded="' + UI.profile + '">' + esc(initials(u.name)) + '</button>' +
    (UI.profile ? profilePanel(u) : '') + (UI.bell ? bellPanel(u) : '') + '</div></header>' +
    '<div class="content">' + view.body + '</div></main></div>';
  if (view.after) view.after();
}
function navItem(to, label, ic, cur, count) {
  var on = cur === to;
  return '<button class="nav-item ' + (on ? 'active' : '') + '" data-act="goto" data-to="' + to + '" ' + (on ? 'aria-current="page"' : '') + ' title="' + esc(label) + '">' + icon(ic) + '<span>' + esc(label) + '</span>' + (count ? '<em class="count">' + count + '</em>' : '') + '</button>';
}
function denied(what) {
  return { title: 'Access denied', sub: '', body: '<div class="denied-page card"><h2>403 · You don\'t have access</h2><p class="muted">' + esc(what || 'Your role does not allow you to open this page.') + '</p><p class="muted small" style="margin-top:6px">Signed in as ' + esc(me().name) + ' (' + esc(me().role) + ').</p><div style="margin-top:18px"><button class="btn" data-act="goto" data-to="' + homeRoute() + '">Go back</button></div></div>' };
}
function renderView(r) {
  var n = r.name;
  if (n === 'dashboard') return dashboardView();
  if (n === 'new-use-case') return useCaseView(r.q);
  if (n === 'artifacts') return artifactsView();
  if (n === 'moderation') return isAdmin() ? moderationView() : denied('The moderation queue is only available to Admins.');
  if (n.indexOf('admin/') === 0) {
    if (!isAdmin()) return denied('This area is only available to Admins.');
    if (n === 'admin/discovery') return discoveryView();
    if (n === 'admin/volunteers') return volunteersView();
    if (n === 'admin/badges') return badgesView();
    if (n === 'admin/settings') return settingsView();
  }
  return dashboardView();
}

/* -------------------------------------------------------------- sign in */
function signinView() {
  var msg = UI.signinError ? '<div class="denied" role="alert">' + esc(UI.signinError) + '</div>' : '';
  return '<div class="signin"><div class="signin-card"><div class="logo">' + LOGO + '</div><h1>Sign in to Tech Radar</h1><p>Use your company Microsoft account to continue.</p>' +
    '<button class="ms-btn" data-act="ms-signin"><svg viewBox="0 0 21 21"><rect x="1" y="1" width="9" height="9" fill="#f25022"/><rect x="11" y="1" width="9" height="9" fill="#7fba00"/><rect x="1" y="11" width="9" height="9" fill="#00a4ef"/><rect x="11" y="11" width="9" height="9" fill="#ffb900"/></svg>Sign in with Microsoft</button>' +
    msg + '<div class="signin-foot">Access is limited to company accounts.</div></div></div>';
}

/* --------------------------------------------------------- profile bits */
function profilePanel(u) {
  var adm = u.role === 'Admin', extra = '';
  if (!adm) {
    var earned = (S.userBadges[u.id] || []);
    var badgeHtml = S.badges.map(function (b) {
      var e = earned.filter(function (x) { return x.badge === b.id; })[0];
      var val = Math.min(stat(u.id, b.criterion), b.threshold);
      var line = e ? 'Earned ' + dShort(e.at) : (val > 0 ? val + ' of ' + b.threshold + ' so far' : 'Not yet earned');
      return '<div class="badge ' + (e ? '' : 'locked') + '">' + badgeArt(b.name) + '<b>' + esc(b.name) + '</b><small>' + line + '</small>' +
        (e ? '' : '<div class="mini-bar"><i style="width:' + Math.round(val / b.threshold * 100) + '%"></i></div>') + '</div>';
    }).join('');
    var certs = S.certs.filter(function (c) { return c.userId === u.id; });
    var certHtml = certs.length ? certs.map(function (c) {
      return '<div class="cert-row"><div class="grow"><b>' + esc(c.title) + '</b><div class="small muted">Issued ' + dLong(c.at) + ' · ' + esc(c.topic) + '</div></div><button class="btn secondary sm" data-act="cert-dl" data-id="' + c.id + '">Download</button></div>';
    }).join('') : '<p class="muted small">No certificates yet. One is issued when your presentation is completed.</p>';
    extra = '<div class="label" style="margin-bottom:10px">Badges</div><div class="badge-row">' + badgeHtml + '</div>' +
      '<div class="label" style="margin:18px 0 4px">Certificates</div>' + certHtml;
  }
  var opts = S.users.filter(function (x) { return x.status === 'Active' && ['u1', 'u2'].indexOf(x.id) > -1; }).map(function (x) { return '<option value="' + x.id + '" ' + (x.id === u.id ? 'selected' : '') + '>' + esc(x.name) + ' — ' + x.role + '</option>'; }).join('');
  return '<div class="popover" role="dialog" aria-label="Profile"><div class="pop-head"><div class="avatar">' + esc(initials(u.name)) + '</div><div><h3>' + esc(u.name) + '</h3><div class="muted small">' + esc(u.title) + ' · ' + esc(u.email) + '</div><div style="margin-top:6px">' + chip(u.role, 'blue') + ' ' + chip(u.team) + '</div></div></div>' +
    extra +
    '<div class="demo"><div class="label" style="margin-bottom:6px">Demo tools (not part of the product)</div><div class="row"><select class="input" id="demo-user" aria-label="Switch demo user">' + opts + '</select><button class="btn secondary sm" data-act="switch-user">Switch</button></div>' +
    '<button class="btn ghost sm" data-act="reset-demo" style="margin-top:8px">Reset demo data</button></div></div>';
}
function bellPanel(u) {
  var list = S.notifications.filter(function (n) { return n.to === u.id; }).slice(0, 12);
  return '<div class="popover narrow" role="dialog" aria-label="Notifications"><div class="card-head"><h3 class="grow">Notifications</h3><button class="btn ghost sm" data-act="read-all">Mark all read</button></div>' +
    (list.length ? list.map(function (n) { return '<div class="notif"><div>' + esc(n.text) + '</div><time>' + ago(n.at) + '</time></div>'; }).join('') : '<p class="muted small">Nothing yet.</p>') + '</div>';
}

/* =============================================================  DASHBOARD */
function dashboardView() {
  var u = me(), cats = catNames();
  var list = approved().filter(function (t) { return UI.filterCat === 'All' || t.category === UI.filterCat; }).sort(function (a, b) { return b.detectedAt - a.detectedAt; });
  var inv = S.invitations.filter(function (i) { return i.userId === u.id && i.status === 'pending'; });
  var body = '<div class="grid cols-main"><section class="card flush" aria-label="Latest discoveries"><div class="card-head" style="padding:18px 20px 0"><h3 class="grow">Latest discoveries</h3>' +
    '<select class="input select-pill" id="cat-filter" aria-label="Filter by category"><option value="All">Category: All</option>' + cats.map(function (c) { return '<option ' + (UI.filterCat === c ? 'selected' : '') + ' value="' + esc(c) + '">Category: ' + esc(c) + '</option>'; }).join('') + '</select></div>' +
    '<div style="padding:4px 20px 20px">' + (list.length ? list.map(function (t) { return topicCard(t, u); }).join('') : '<div class="empty"><b>No topics in ' + esc(UI.filterCat) + ' yet</b>New discoveries appear here once an admin approves them.</div>') + '</div></section>' +
    '<aside class="card panel-mark" aria-label="Invitations"><div class="card-head"><div class="grow"><h3>Invitations</h3><div class="hint">' + (inv.length ? plural(inv.length, 'pending invitation') : 'No pending invitations') + '</div></div></div>' +
    (inv.length ? inv.map(function (i) { return inviteCard(i); }).join('') : '<p class="muted small">Volunteer to study a topic and present it to the office.</p>') + '</aside></div>';
  return { title: 'Discoveries Dashboard', sub: 'Latest technologies surfaced by the discovery agent. Pick one to explore.', action: '<button class="btn" data-act="custom-topic">' + icon('plus') + ' Add custom topic</button>', body: body };
}
function inviteCard(i) {
  var t = topic(i.topicId); if (!t) return '';
  var expired = now() - i.at > S.settings.expiryDays * DAY;
  return '<div class="invite ' + (expired ? 'expired' : '') + '"><h4>' + esc(t.title) + '</h4><div class="small muted">' + esc(t.category) + ' · invited ' + ago(i.at) + '</div>' +
    (expired ? '<div class="row">' + chip('Expired', 'red') + '<span class="small muted">Invitations expire after ' + plural(S.settings.expiryDays, 'day') + '</span></div>' :
      '<div class="row"><button class="btn sm" data-act="inv-accept" data-id="' + i.id + '">Accept</button><button class="btn secondary sm" data-act="inv-decline" data-id="' + i.id + '">Decline</button></div>') + '</div>';
}
function topicCard(t, u) {
  var n = t.volunteers.length, open = UI.openTopic === t.id, mine = t.volunteers.indexOf(u.id) > -1, wait = t.waitlist.indexOf(u.id) > -1;
  var volTxt = n === 0 ? 'No volunteers yet' : plural(n, 'volunteer');
  var btn = mine ? '<button class="btn" disabled>Exploring ✓</button>' : wait ? '<button class="btn" disabled>On the waitlist</button>' : '<button class="btn" data-act="volunteer" data-id="' + t.id + '">Volunteer to explore</button>';
  var arts = t.articles.slice(0, 3), tcs = t.testCases;
  var body = '';
  if (open) {
    body = '<div class="topic-body"><div class="two"><div><div class="label">Articles</div><ul class="list-links">' + (arts.length ? arts.map(function (a) { return '<li>' + icon('link') + '<a href="' + esc(a.url) + '" target="_blank" rel="noopener">' + esc(a.title) + '</a></li>'; }).join('') : '<li class="muted">No verified articles</li>') + '</ul></div>' +
      '<div><div class="label">Test cases</div><ul class="list-links">' + (tcs.length ? tcs.map(function (c) { return '<li><a href="' + esc(c.url || '#') + '" target="_blank" rel="noopener">' + esc(c.title) + '</a><small>' + esc(short(c.author)) + ' · ' + dShort(c.at) + '</small></li>'; }).join('') : '<li class="muted">No test cases yet</li>') + '</ul></div></div>' +
      '<div class="topic-actions"><button class="btn secondary" data-act="add-tc" data-id="' + t.id + '">Add your test case</button>' + btn + (mine ? '<button class="btn ghost" data-act="start-uc" data-id="' + t.id + '">Start a use case</button>' : '') + '</div></div>';
  }
  return '<article class="topic ' + (open ? 'open' : '') + '" id="topic-' + t.id + '"><div class="topic-head" data-act="toggle-topic" data-id="' + t.id + '" role="button" tabindex="0" aria-expanded="' + open + '">' +
    '<div class="grow"><div class="topic-meta"><span>' + esc(t.category) + ' · detected ' + ago(t.detectedAt) + ' · ' + plural(t.sources, 'source') + '</span>' + (t.origin === 'custom' ? chip('custom', 'purple') : '') + '</div>' +
    '<h3>' + esc(t.title) + '</h3><p class="sum">' + esc(t.summary) + '</p></div><div class="topic-meta" style="flex:none">' + chip(volTxt, n ? 'blue' : '') + '</div>' + icon('chev', 'chev') + '</div>' + body + '</article>';
}

/* ------------- topic actions (shared by dashboard, volunteers screens) */
function addVolunteer(t, uidv, how) {
  if (t.volunteers.indexOf(uidv) > -1) return;
  t.volunteers.push(uidv); t.waitlist = t.waitlist.filter(function (x) { return x !== uidv; });
  if (!t.stage) { t.stage = 'Study'; t.deadline = now() + STAGE_DAYS.Study * DAY; t.deliverable = false; }
  t.lastActivity = now();
  S.invitations.forEach(function (i) { if (i.userId === uidv && i.topicId === t.id && i.status === 'pending') i.status = 'accepted'; });
  checkBadges(uidv);
}
var A_volunteer = function (id) {
  var t = topic(id), u = me();
  if (t.volunteers.indexOf(u.id) > -1) return toast('You are already exploring this topic.', 'warn');
  if (t.volunteers.length >= S.settings.maxVol) {
    return openModal({ title: 'This topic is full', sub: t.title, body: '<p>' + t.volunteers.length + ' of ' + S.settings.maxVol + ' places are taken, so we can\'t add you right now.</p><p class="muted" style="margin-top:8px">Join the waitlist and you\'ll be notified if a place opens up.</p>',
      actions: [{ label: 'Not now', cls: 'secondary' }, { label: 'Join waitlist', fn: function () { if (t.waitlist.indexOf(u.id) < 0) t.waitlist.push(u.id); save(); toast('You are on the waitlist for this topic.', 'ok'); render(); } }] });
  }
  addVolunteer(t, u.id);
  notify(admins(), short(u.id) + ' volunteered to explore "' + t.title + '".');
  save(); toast('You\'re exploring this topic. Study deadline: ' + dShort(t.deadline) + '. Admins have been notified.', 'ok'); render();
};
function addTestCase(id) {
  var t = topic(id);
  openModal({ title: 'Add your test case', sub: t.title, body: '<div class="stack"><div class="field" id="f-tc-title"><label for="tc-title">Test case title</label><input class="input" id="tc-title" placeholder="e.g. Support triage with an approval step"><span class="err-msg">Enter a title.</span></div>' +
    '<div class="field" id="f-tc-url"><label for="tc-url">Link to the page or repo</label><input class="input" id="tc-url" placeholder="https://"><span class="err-msg">Enter a valid link starting with http:// or https://</span></div></div>',
    actions: [{ label: 'Cancel', cls: 'secondary' }, { label: 'Add test case', fn: function (m) {
      var ti = $('#tc-title', m).value.trim(), ur = $('#tc-url', m).value.trim(), bad = false;
      $('#f-tc-title', m).classList.toggle('invalid', !ti); if (!ti) bad = true;
      var okUrl = !ur || /^https?:\/\/\S+$/i.test(ur); $('#f-tc-url', m).classList.toggle('invalid', !okUrl); if (!okUrl) bad = true;
      if (bad) return false;
      t.testCases.push({ title: ti, url: ur, author: me().id, at: now() }); t.lastActivity = now(); checkBadges(me().id); save(); toast('Test case added to the topic.', 'ok'); render();
    } }] });
}
function advanceStage(id) {
  var t = topic(id), i = STAGES.indexOf(t.stage), next = STAGES[i + 1];
  if (!next) return toast('This topic is already at the final stage.', 'warn');
  t.stage = next; t.deadline = now() + STAGE_DAYS[next] * DAY; t.deliverable = false; t.lastActivity = now();
  audit('Advanced stage', t.title + ' → ' + next); save();
  toast('Moved to ' + next + '. Deadline: ' + dShort(t.deadline) + '.', 'ok'); render();
}
function customTopicModal() {
  var cats = catNames();
  openModal({ title: 'Add a custom topic', sub: 'Suggest a technology the agent missed. It appears on the dashboard straight away.',
    body: '<div class="stack"><div class="field" id="f-ct-title"><label for="ct-title">Topic title</label><input class="input" id="ct-title" placeholder="e.g. Azure AI Foundry agent service"><span class="err-msg">Enter a title for the topic.</span></div>' +
      '<div class="field"><label for="ct-cat">Category</label><select class="input" id="ct-cat">' + cats.map(function (c) { return '<option>' + esc(c) + '</option>'; }).join('') + '</select></div>' +
      '<div class="field"><label for="ct-sum">What is it and why does it matter?</label><textarea class="input" id="ct-sum" style="min-height:90px"></textarea></div>' +
      '<div class="field"><label for="ct-url">Link (optional)</label><input class="input" id="ct-url" placeholder="https://"></div></div>',
    actions: [{ label: 'Cancel', cls: 'secondary' }, { label: 'Submit topic', fn: function (m) {
      var ti = $('#ct-title', m).value.trim(); $('#f-ct-title', m).classList.toggle('invalid', !ti); if (!ti) return false;
      var url = $('#ct-url', m).value.trim();
      S.topics.push({ id: uid('t'), title: ti, category: $('#ct-cat', m).value, status: 'approved', origin: 'custom', detectedAt: now(), sources: url ? 1 : 0, summary: $('#ct-sum', m).value.trim() || 'Added by ' + me().name + '. Enrichment is running.', articles: url ? [{ title: url, url: url }] : [], testCases: [], suggestion: '', lowCost: false, requestedBy: me().id, volunteers: [], waitlist: [], stage: '', deadline: null, deliverable: true, lastActivity: now(), presented: [] });
      audit('Submitted a custom topic', ti); notify(admins(), me().name + ' added a custom topic: "' + ti + '".'); save(); toast('Topic added. It now appears on the dashboard.', 'ok'); render();
    } }] });
}

/* ==========================================================  NEW USE CASE */
function getDraft() {
  var u = me(), d = S.drafts[u.id];
  if (!d) {
    var mineTopic = approved().filter(function (t) { return t.volunteers.indexOf(u.id) > -1; })[0] || approved()[0];
    d = S.drafts[u.id] = { topicId: mineTopic ? mineTopic.id : '', title: '', problem: '', approach: '', co: [], files: [], repo: '', savedAt: 0, dirty: false };
  }
  return d;
}
function useCaseView(q) {
  var u = me(), d = getDraft(); if (q.topic && topic(q.topic)) d.topicId = q.topic;
  var t = topic(d.topicId);
  var accepted = S.useCases.filter(function (x) { return x.authorId === u.id && x.topicId === d.topicId && x.status === 'accepted'; })[0];
  var saved = d.savedAt ? 'Draft · autosaved ' + ago(d.savedAt) : 'Draft · not saved yet';
  var topicOpts = approved().map(function (x) { return '<option value="' + x.id + '" ' + (x.id === d.topicId ? 'selected' : '') + '>' + esc(x.title) + '</option>'; }).join('');
  var coChips = d.co.map(function (id) { return '<span class="chip blue">' + esc(nameOf(id)) + ' <button data-act="co-remove" data-id="' + id + '" aria-label="Remove ' + esc(nameOf(id)) + '">×</button></span>'; }).join(' ');
  var files = d.files.map(function (f, i) {
    return '<div class="file"><span class="ico">' + icon('file') + '</span><div class="grow"><div><b>' + esc(f.name) + '</b></div><div class="small muted">' + fmtSize(f.size) + ' · ' + esc(f.kind) + '</div></div><button class="btn ghost sm" data-act="file-remove" data-i="' + i + '" aria-label="Remove ' + esc(f.name) + '">' + icon('x') + '</button></div>';
  }).join('');
  var success = UI.lastSubmitted ? '<div class="notice ok" role="status"><b>Use case submitted.</b> It is now in the moderation queue. You\'ll be notified when it is reviewed.</div>' : '';
  var form =
    '<div class="stack"><section class="card"><h3>Topic and contributor</h3><div class="hint">Pick the topic you explored. Your profile comes from the employee directory.</div>' +
    '<div class="form-grid" style="margin-top:16px"><div class="field"><label for="uc-topic">Technology</label><select class="input" id="uc-topic" data-field="topicId">' + topicOpts + '</select></div>' +
    '<div class="field"><span class="lbl">Category</span><div class="input" style="display:flex;align-items:center;color:var(--text-2)" id="uc-cat">' + esc(t ? t.category : '—') + '</div></div>' +
    '<div class="field"><span class="lbl">Contributor</span><div class="input" style="display:flex;align-items:center;gap:10px"><span class="avatar sm">' + esc(initials(u.name)) + '</span>' + esc(u.name) + ' · ' + esc(u.title) + '</div></div>' +
    '<div class="field picker"><label for="co-input">Co-contributors (optional)</label><input class="input" id="co-input" placeholder="Select people from the directory" autocomplete="off"><div class="picker-list" id="co-list" hidden></div><div class="row wrap" style="margin-top:4px">' + coChips + '</div></div></div></section>' +

    '<section class="card"><h3>Use case and solution</h3><div class="hint">Describe what you tried and how you approached it.</div><div class="stack" style="margin-top:16px">' +
    '<div class="field" id="f-title"><label for="uc-title">Use case title</label><input class="input" id="uc-title" data-field="title" value="' + esc(d.title) + '" placeholder="e.g. Ticket triage agent with human approval"><span class="err-msg">Add a title.</span></div>' +
    '<div class="field" id="f-problem"><label for="uc-problem">What problem were you testing?</label><textarea class="input" id="uc-problem" data-field="problem" placeholder="Describe the scenario you chose to evaluate this technology against.">' + esc(d.problem) + '</textarea><span class="err-msg">Describe the problem you were testing.</span></div>' +
    '<div class="field" id="f-approach"><label for="uc-approach">Solution approach</label><textarea class="input" id="uc-approach" data-field="approach" style="min-height:150px" placeholder="Explain the architecture, the tools you used and the key decisions you made.">' + esc(d.approach) + '</textarea><span class="err-msg">Explain your solution approach.</span></div></div></section>' +

    '<section class="card"><h3>Code and documents</h3><div class="hint">Everything is saved to the shared SharePoint folder for this use case.</div><div class="stack" style="margin-top:16px">' +
    '<div class="field"><span class="lbl">Upload</span><div class="dropzone" id="dz"><b>Drag and drop your code or documents here</b><small>Zip archives, PDFs, slides and notebooks up to 100 MB each</small><button class="btn secondary sm" type="button" data-act="browse">Browse files</button><input type="file" id="file-input" multiple hidden></div><div class="notice err" id="upload-err" hidden role="alert"></div>' + files + '</div>' +
    '<div class="field" id="f-repo"><label for="uc-repo">Repository link (optional)</label><input class="input" id="uc-repo" data-field="repo" value="' + esc(d.repo) + '" placeholder="https://github.com/your-org/your-repo"><span class="err-msg">Enter a link starting with http:// or https://</span></div></div></section>' +

    '<div class="card row" style="position:sticky;bottom:12px;z-index:5;box-shadow:0 10px 30px #0008"><span class="small muted grow" id="autosave-label">' + saved + '</span><button class="btn secondary" data-act="uc-cancel">Cancel</button><button class="btn secondary" data-act="uc-save">Save draft</button><button class="btn" data-act="uc-submit">Submit use case</button></div></div>';
  var side = '<aside class="stack">' +
    (t && t.suggestion ? '<section class="card suggest" style="background:linear-gradient(135deg,#3b82f61a,#8b5cf61a)"><div class="label">Suggested use case</div>' + (t.lowCost ? '<div style="margin-top:6px">' + chip('low-cost simulation suggested', 'yellow') + '</div>' : '') + '<p style="margin:8px 0 12px">' + esc(t.suggestion) + '</p><button class="btn secondary sm" data-act="use-suggestion">Use this suggestion</button></section>' : '') +
    '<section class="card"><div class="label">Where this is saved</div><dl class="kv" style="margin-top:10px"><dt>SharePoint folder</dt><dd class="mono">Tech Radar / Use Cases / ' + esc(t ? t.category : '…') + ' / ' + esc(t ? t.title : '…') + '</dd><dt>Shareable link</dt><dd>' +
    (accepted ? '<a class="mono" href="#" data-act="open-page" data-id="' + accepted.id + '">' + esc(pageUrl(accepted)) + '</a>' : '<span class="muted">Available after an admin approves it</span>') + '</dd></dl></section></aside>';
  return { crumbs: '<div class="crumbs"><a href="#/dashboard">Dashboard</a> / ' + esc(t ? t.title : 'Topic') + ' / New use case</div>', title: 'New Use Case', sub: 'Share how you tried this technology so the rest of the office can learn from it.', body: success + '<div class="grid cols-side" style="margin-top:' + (success ? '16px' : '0') + '">' + form + side + '</div>', after: bindUseCase };
}
function pageUrl(uc) { return 'techradar.neuleap.ai/use-cases/' + slug(uc.title); }
function markDirty() { var d = getDraft(); d.dirty = true; }
function saveDraft(manual) {
  var d = S.drafts[S.session]; if (!d) return;
  if (!manual && !d.dirty) return;
  d.savedAt = now(); d.dirty = false; save(); // API: PUT /use-cases/draft
  var l = $('#autosave-label'); if (l) l.textContent = 'Draft · autosaved just now';
}
setInterval(function () { if (S.session) saveDraft(false); }, 20000); // autosave well inside the 60 s limit (REQ-042)
setInterval(function () { var l = $('#autosave-label'), d = S.session && S.drafts[S.session]; if (l && d && d.savedAt) l.textContent = 'Draft · autosaved ' + ago(d.savedAt); }, 30000);

function bindUseCase() {
  var d = getDraft();
  $$('[data-field]').forEach(function (el) {
    el.addEventListener('input', function () { d[el.getAttribute('data-field')] = el.value; markDirty(); el.closest('.field') && el.closest('.field').classList.remove('invalid'); });
    el.addEventListener('change', function () {
      d[el.getAttribute('data-field')] = el.value; markDirty();
      if (el.getAttribute('data-field') === 'topicId') { saveDraft(true); render(); }
    });
  });
  var inp = $('#co-input'), list = $('#co-list');
  function showList() {
    var qv = inp.value.trim().toLowerCase(); if (!qv) { list.hidden = true; return; }
    var m = activeUsers().filter(function (x) { return x.id !== S.session && d.co.indexOf(x.id) < 0 && (x.name.toLowerCase().indexOf(qv) > -1 || x.email.indexOf(qv) > -1); }).slice(0, 6);
    list.hidden = false;
    list.innerHTML = m.length ? m.map(function (x) { return '<button type="button" data-co="' + x.id + '"><span class="avatar sm">' + esc(initials(x.name)) + '</span><span>' + esc(x.name) + '<br><small class="muted">' + esc(x.email) + ' · ' + esc(x.team) + '</small></span></button>'; }).join('') : '<div class="empty small" style="padding:14px">No match in the company directory. Only people from the directory can be added.</div>';
  }
  inp.addEventListener('input', showList); inp.addEventListener('focus', showList);
  list.addEventListener('click', function (e) { var b = e.target.closest('[data-co]'); if (!b) return; d.co.push(b.getAttribute('data-co')); markDirty(); saveDraft(true); render(); });
  var fi = $('#file-input'), dz = $('#dz');
  fi.addEventListener('change', function () { addFiles(fi.files); fi.value = ''; });
  ['dragover', 'dragenter'].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add('over'); }); });
  ['dragleave', 'drop'].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove('over'); if (ev === 'drop') addFiles(e.dataTransfer.files); }); });
}
function addFiles(fl) {
  var d = getDraft(), errs = [], added = 0;
  Array.prototype.forEach.call(fl, function (f) {
    var ext = (f.name.split('.').pop() || '').toLowerCase();
    if (BLOCKED_EXT.indexOf(ext) > -1) errs.push(f.name + ': executable files are not allowed because they can\'t be scanned safely.');
    else if (f.size > MAX_UPLOAD) errs.push(f.name + ': ' + fmtSize(f.size) + ' is over the 100 MB limit for a single file.');
    else if (ALLOWED_EXT.indexOf(ext) < 0) errs.push(f.name + ': this file type isn\'t supported. Use zip archives, PDFs, slides, documents or notebooks.');
    else { d.files.push({ name: f.name, size: f.size, kind: ext === 'zip' ? 'code' : ext === 'ipynb' ? 'notebook' : /^pptx?$|key/.test(ext) ? 'slides' : 'document' }); added++; }
  });
  if (added) { markDirty(); saveDraft(true); }
  render();
  var box = $('#upload-err'); if (box && errs.length) { box.hidden = false; box.innerHTML = errs.map(esc).join('<br>'); }
}
function scanSubmission(text, files) {
  var flags = [];
  if (/\b(acme|globex|initech|client name|client environment|customer environment|client tenant|client prod)\b/i.test(text)) flags.push({ kind: 'client', text: 'Flagged: mentions a client environment' });
  if (/(AKIA[0-9A-Z]{8,}|api[_-]?key\s*[:=]|secret\s*[:=]|password\s*[:=]|bearer\s+[a-z0-9._-]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY)/i.test(text)) flags.push({ kind: 'secret', text: 'Flagged: possible secret (key, token or password)' });
  return flags;
}
function submitUseCase() {
  var d = getDraft(), miss = [];
  [['title', 'f-title', 'a title'], ['problem', 'f-problem', 'the problem'], ['approach', 'f-approach', 'a solution approach']].forEach(function (f) {
    var bad = !String(d[f[0]] || '').trim(); $('#' + f[1]).classList.toggle('invalid', bad); if (bad) miss.push(f[2]);
  });
  var repoBad = d.repo && !/^https?:\/\/\S+$/i.test(d.repo.trim()); $('#f-repo').classList.toggle('invalid', !!repoBad);
  if (miss.length || repoBad) {
    toast('Can\'t submit yet — add ' + (miss.length ? miss.join(', ') : 'a valid repository link') + '.', 'err');
    var first = $('.field.invalid'); if (first) { first.scrollIntoView({ block: 'center', behavior: 'smooth' }); var i = $('input,textarea,select', first); if (i) i.focus(); }
    return;
  }
  var t = topic(d.topicId), uc = { id: uid('uc'), topicId: d.topicId, authorId: S.session, title: d.title.trim(), problem: d.problem, approach: d.approach, co: d.co.slice(), files: d.files.slice(), repo: d.repo, status: 'review', at: now(), reason: '' };
  S.useCases.push(uc);
  var flags = scanSubmission([d.title, d.problem, d.approach].join(' ') + ' ' + d.files.map(function (f) { return f.name; }).join(' '), d.files);
  S.queue.unshift({ id: uid('q'), title: uc.title, type: 'Use case', authorId: uc.authorId, at: now(), flags: flags, note: 'Use case' + (d.files.length ? ' · includes ' + plural(d.files.length, 'file') : ''), useCaseId: uc.id, topicId: d.topicId, status: 'pending', summary: d.problem });
  notify(admins(), 'New use case waiting for moderation: "' + uc.title + '".');
  if (t) t.lastActivity = now();
  delete S.drafts[S.session]; UI.lastSubmitted = uc; save(); // API: POST /use-cases
  toast('Use case submitted. It is now in the moderation queue.', 'ok'); render(); window.scrollTo(0, 0);
}

/* ============================================================  ARTIFACTS */
function artifactsView() {
  var body = '<section class="card flush"><div class="card-head" style="padding:18px 20px 0"><h3>All artifacts</h3><span class="small muted grow" id="lib-count"></span><input class="input" id="lib-q" placeholder="Search artifacts" aria-label="Search artifacts" style="width:220px;border-radius:55px" value="' + esc(UI.libQ) + '">' +
    '<select class="input select-pill" id="lib-type" aria-label="Filter by type"><option value="All">Type: All</option>' + ART_TYPES.map(function (x) { return '<option ' + (UI.libType === x ? 'selected' : '') + ' value="' + esc(x) + '">Type: ' + esc(x) + '</option>'; }).join('') + '</select></div>' +
    '<div style="padding:12px 20px 20px" id="lib-grid"></div></section>';
  return { title: 'Project Artifacts', sub: 'A shared library of code, architecture patterns and learnings from real projects', action: '<button class="btn" data-act="upload-artifact">' + icon('upload') + ' Upload artifact</button>', body: body, after: renderLibrary };
}
function renderLibrary() {
  var t0 = performance.now(), u = me(), q = UI.libQ.trim().toLowerCase();
  var all = S.artifacts.filter(function (a) { return a.approved; });
  var list = all.filter(function (a) { return (UI.libType === 'All' || a.type === UI.libType) && (!q || (a.title + ' ' + a.summary + ' ' + nameOf(a.authorId) + ' ' + a.type).toLowerCase().indexOf(q) > -1); }).sort(function (a, b) { return b.at - a.at; });
  var g = $('#lib-grid'); if (!g) return;
  g.innerHTML = list.length ? '<div class="grid cols-2">' + list.map(function (a) {
    return '<article class="card" style="background:var(--bg-card)"><h3>' + esc(a.title) + '</h3><div class="small muted" style="margin:4px 0 8px">' + esc(a.type) + ' · ' + esc(short(a.authorId)) + ' · ' + dShort(a.at) + '</div><p style="color:var(--text-2)">' + esc(a.summary) + '</p><div style="margin-top:14px"><button class="btn secondary sm" data-act="open-artifact" data-id="' + a.id + '">Open</button></div></article>';
  }).join('') + '</div>' : '<div class="empty"><b>No artifacts match</b>Try a different type or search term.</div>';
  var ms = Math.max(1, Math.round(performance.now() - t0));
  $('#lib-count').textContent = 'Showing ' + list.length + ' of ' + all.length + ' · ' + ms + ' ms';
}

/* ===========================================================  MODERATION */
function flagChips(q) { return q.flags.map(function (f) { return '<div class="small" style="color:#ffb4b4;margin-top:4px">⚑ ' + esc(f.text) + (f.kind === 'secret' ? ' · <a href="#" data-act="mod-replaced" data-id="' + q.id + '">Simulate: contributor replaced the file</a>' : '') + '</div>'; }).join(''); }
function moderationView() {
  var f = UI.flt;
  var list = S.queue.filter(function (q) { return q.status === 'pending' && (!f.modType || f.modType === 'All' || q.type === f.modType); }).sort(function (a, b) { return b.at - a.at; });
  var types = ['Use case'].concat(ART_TYPES);
  var body = '<div class="stack"><section class="card flush"><div class="card-head" style="padding:18px 20px 0"><h3>Pending review</h3>' + chip(plural(list.length, 'item'), 'blue') + '<span class="grow"></span>' +
    '<select class="input select-pill" data-chg="modType" aria-label="Filter by type"><option value="All">Type: All</option>' + types.map(function (x) { return '<option ' + (f.modType === x ? 'selected' : '') + ' value="' + esc(x) + '">Type: ' + esc(x) + '</option>'; }).join('') + '</select></div>' +
    '<div class="table-wrap" style="margin-top:12px">' + (list.length ? '<table class="table"><thead><tr><th>Item</th><th>Type</th><th>Contributor</th><th>Submitted</th><th style="text-align:right">Actions</th></tr></thead><tbody>' + list.map(function (q) {
      return '<tr><td><div class="t-title">' + esc(q.title) + '</div><div class="t-sub">' + esc(q.note || q.type) + '</div>' + flagChips(q) + '</td><td>' + esc(q.type) + '</td><td>' + esc(short(q.authorId)) + '</td><td>' + ageShort(q.at) + '</td>' +
        '<td><div class="actions"><button class="btn sm" data-act="mod-approve" data-id="' + q.id + '">Approve</button><button class="btn danger sm" data-act="mod-reject" data-id="' + q.id + '">Reject</button></div></td></tr>';
    }).join('') + '</tbody></table>' : '<div class="empty"><b>The queue is clear</b>Submitted use cases and artifacts appear here for review.</div>') + '</div></section></div>';
  return { title: 'Moderation', sub: 'Review submitted use cases and artifacts before they are shared.', body: body };
}
function modApprove(id) {
  var q = S.queue.filter(function (x) { return x.id === id; })[0];
  if (q.flags.some(function (f) { return f.kind === 'secret'; })) return openModal({ title: 'Approval blocked', body: '<div class="notice err">A secret (key, token or password) was detected in this submission. Approval stays blocked until the file is replaced and scanned again.</div>', actions: [{ label: 'OK' }] });
  q.status = 'approved';
  var author = q.authorId;
  if (q.useCaseId) {
    var uc = S.useCases.filter(function (x) { return x.id === q.useCaseId; })[0];
    if (uc) { uc.status = 'accepted'; uc.pageUrl = pageUrl(uc); S.artifacts.unshift({ id: uid('a'), title: uc.title, type: 'POC', authorId: author, at: now(), summary: uc.problem, approved: true }); }
    var t = topic(q.topicId);
    notify(author, 'Your use case "' + q.title + '" was approved and published at ' + (uc ? pageUrl(uc) : '') + (t ? '. Files saved to Tech Radar/Use Cases/' + t.category + '/' + t.title + '/' : '.'));
  } else {
    S.artifacts.unshift({ id: uid('a'), title: q.title, type: q.type, authorId: author, at: now(), summary: q.summary || q.note || '', approved: true });
    notify(author, 'Your ' + q.type.toLowerCase() + ' "' + q.title + '" was approved.');
  }
  checkBadges(author); audit('Approved item', q.title); save(); toast('Approved and shared per its visibility.', 'ok'); render();
}
function modReason(id) {
  var q = S.queue.filter(function (x) { return x.id === id; })[0];
  openModal({ title: 'Reject this item', sub: q.title,
    body: '<div class="field" id="f-reason"><label for="reason">Reason (shown to the contributor)</label><textarea class="input" id="reason" placeholder="Why is this being rejected?"></textarea><span class="err-msg">A reason is required.</span></div>',
    actions: [{ label: 'Cancel', cls: 'secondary' }, { label: 'Reject', cls: 'danger', fn: function (m) {
      var r = $('#reason', m).value.trim(); $('#f-reason', m).classList.toggle('invalid', !r); if (!r) return false;
      q.status = 'rejected'; q.reason = r;
      if (q.useCaseId) { var uc = S.useCases.filter(function (x) { return x.id === q.useCaseId; })[0]; if (uc) { uc.status = 'rejected'; uc.reason = r; } }
      notify(q.authorId, 'Rejected: "' + q.title + '" — ' + r);
      audit('Rejected item', q.title); save(); toast('Contributor notified with your reason.', 'ok'); render();
    } }] });
}


/* ============================================================  DISCOVERY */
function discoveryView() {
  var topicCount = function (n) { return S.topics.filter(function (t) { return t.category === n; }).length; };
  var body = '<div class="grid cols-main" style="grid-template-columns:minmax(0,1fr) 380px"><section class="card flush"><div class="card-head" style="padding:18px 20px 0"><div class="grow"><h3>Sources</h3><div class="hint">Where the agent looks for new technology</div></div></div><div class="table-wrap" style="margin-top:12px"><table class="table"><thead><tr><th>Source</th><th>Type</th><th>Last crawl</th><th></th></tr></thead><tbody>' +
    S.sources.map(function (s) {
      return '<tr><td><div class="t-title">' + esc(s.name) + '</div></td><td>' + esc(s.type) + '</td><td>' + (s.last ? ago(s.last) : 'Not crawled yet') + (s.error ? '<div class="small" style="color:#ff8a8a">' + esc(s.error) + '</div>' : '') + '</td>' +
        '<td><div class="actions"><button class="btn ghost sm" data-act="src-edit" data-id="' + s.id + '">Edit</button><button class="btn ghost sm" data-act="src-remove" data-id="' + s.id + '">Remove</button></div></td></tr>';
    }).join('') + '</tbody></table></div></section>' +
    '<div class="stack"><section class="card"><div class="card-head"><div class="grow"><h3>Categories</h3><div class="hint">Used to group and filter topics</div></div><button class="btn secondary sm" data-act="cat-add">Add category</button></div>' +
    S.categories.map(function (c) { return '<div class="attn"><div class="grow"><b>' + esc(c.name) + '</b> ' + (c.retired ? chip('Retired', 'yellow') : '') + '<div class="small muted">' + plural(topicCount(c.name), 'topic') + '</div></div><button class="btn ghost sm" data-act="cat-rename" data-id="' + c.id + '">Rename</button><button class="btn ghost sm" data-act="cat-retire" data-id="' + c.id + '">' + (c.retired ? 'Restore' : 'Retire') + '</button></div>'; }).join('') + '</section>' +
    '<section class="card"><h3>Keywords</h3><div class="hint">The agent looks for these and skips the excluded ones</div>' +
    kwBlock('include', 'Include keywords') + kwBlock('exclude', 'Exclude keywords') + '</section></div></div>';
  return { title: 'Discovery Agent', sub: 'Control what the agent crawls.', action: '<button class="btn" data-act="src-add">' + icon('plus') + ' Add source</button>', body: body };
}
function kwBlock(kind, label) {
  return '<div class="field" style="margin-top:14px"><span class="lbl">' + label + '</span><div class="row wrap">' + S[kind].map(function (k, i) { return '<span class="chip ' + (kind === 'exclude' ? 'red' : 'blue') + '">' + esc(k) + ' <button data-act="kw-remove" data-kind="' + kind + '" data-i="' + i + '" aria-label="Remove ' + esc(k) + '">×</button></span>'; }).join('') + '</div>' +
    '<div class="row"><input class="input" id="kw-' + kind + '" placeholder="Add a keyword" style="min-height:36px"><button class="btn secondary sm" data-act="kw-add" data-kind="' + kind + '">Add</button></div></div>';
}
function sourceModal(id) {
  var s = id ? S.sources.filter(function (x) { return x.id === id; })[0] : { name: '', url: '', type: 'Blog' };
  openModal({ title: id ? 'Edit source' : 'Add source', body: '<div class="form-grid"><div class="field full" id="f-sn"><label for="sn">Name</label><input class="input" id="sn" value="' + esc(s.name) + '" placeholder="e.g. OpenAI Blog"><span class="err-msg">Enter a name.</span></div>' +
    '<div class="field full" id="f-su"><label for="su">URL</label><input class="input" id="su" value="' + esc(s.url) + '" placeholder="https://"><span class="err-msg">Enter a valid link starting with http:// or https://</span></div>' +
    '<div class="field full"><label for="st">Type</label><select class="input" id="st">' + SRC_TYPES.map(function (x) { return '<option ' + (s.type === x ? 'selected' : '') + '>' + x + '</option>'; }).join('') + '</select></div></div>',
    actions: [{ label: 'Cancel', cls: 'secondary' }, { label: 'Save', fn: function (m) {
      var n = $('#sn', m).value.trim(), u = $('#su', m).value.trim(); $('#f-sn', m).classList.toggle('invalid', !n); var okU = /^https?:\/\/\S+$/i.test(u); $('#f-su', m).classList.toggle('invalid', !okU);
      if (!n || !okU) return false;
      var o = id ? s : { id: uid('s'), last: 0, error: '' };
      o.name = n; o.url = u; o.type = $('#st', m).value;
      if (!id) S.sources.push(o); audit(id ? 'Edited a source' : 'Added a source', n); save(); toast('Source saved.', 'ok'); render();
    } }] });
}


/* =========================================================  VOLUNTEERS */
function volunteersView() {
  var list = approved().sort(function (a, b) { return a.deadline - b.deadline; });
  var f = UI.flt.vol || 'All';
  var shown = list.filter(function (t) { var s = topicStatus(t); return f === 'All' || s.key === f; });
  var body = '<div class="stack">' +
    '<section class="card flush"><div class="card-head" style="padding:18px 20px 0"><h3 class="grow">All topics in progress</h3><select class="input select-pill" data-chg="volStatus" aria-label="Status"><option value="All">Status: All</option><option value="needs" ' + (f === 'needs' ? 'selected' : '') + '>Needs a volunteer</option><option value="overdue" ' + (f === 'overdue' ? 'selected' : '') + '>Overdue</option><option value="cap" ' + (f === 'cap' ? 'selected' : '') + '>Over the cap</option><option value="risk" ' + (f === 'risk' ? 'selected' : '') + '>At risk</option><option value="ok" ' + (f === 'ok' ? 'selected' : '') + '>On track</option></select></div>' +
    '<div class="table-wrap" style="margin-top:12px"><table class="table"><thead><tr><th>Topic</th><th>Volunteers</th><th>Stage</th><th>Deadline</th><th>Status</th><th></th></tr></thead><tbody>' + shown.map(function (t) {
      var s = topicStatus(t), names = t.volunteers.map(short);
      return '<tr><td><div class="t-title">' + esc(t.title) + '</div></td><td>' + (names.length ? esc(names.join(', ')) : '<span class="muted">No volunteers yet</span>') + '</td><td>' + (t.stage || '—') + '</td><td>' + (t.deadline != null && t.volunteers.length ? dShort(t.deadline) : '—') + '</td><td>' + chip(s.text, s.tone) + '</td><td><div class="actions"><button class="btn secondary sm" data-act="vol-manage" data-id="' + t.id + '">Manage</button></div></td></tr>';
    }).join('') + '</tbody></table></div></section></div>';
  return { title: 'Volunteers', sub: 'See who is exploring what, and keep each deliverable on track.', action: '<button class="btn" data-act="vol-assign">' + icon('plus') + ' Assign volunteer</button>', body: body };
}
function manageModal(id) {
  var t = topic(id), s = topicStatus(t), idx = STAGES.indexOf(t.stage), next = STAGES[idx + 1];
  var cand = contributors().filter(function (u) { return t.volunteers.indexOf(u.id) < 0; });
  openModal({ wide: true, title: t.title, sub: t.category + ' · maximum ' + S.settings.maxVol + ' volunteers per topic', body:
    '<div class="row" style="margin-bottom:14px">' + chip(s.text, s.tone) + '<span class="muted small">Stage: ' + (t.stage || '—') + (t.deadline != null && t.volunteers.length ? ' · due ' + dShort(t.deadline) : '') + ' · Deliverable: ' + (t.deliverable ? 'added' : 'missing') + '</span></div>' +
    '<div class="label">Volunteers (' + t.volunteers.length + ')</div>' + (t.volunteers.length ? t.volunteers.map(function (v) { return '<div class="attn"><span class="avatar sm">' + esc(initials(nameOf(v))) + '</span><div class="grow">' + esc(nameOf(v)) + '</div><button class="btn ghost sm" data-mrm="' + v + '">Remove</button></div>'; }).join('') : '<p class="muted small">Nobody yet.</p>') +
    (t.waitlist.length ? '<div class="label" style="margin-top:12px">Waitlist</div><p class="small">' + esc(t.waitlist.map(nameOf).join(', ')) + '</p>' : '') +
    '<div class="field" style="margin-top:16px"><label for="as-user">Assign directly</label><div class="row"><select class="input" id="as-user">' + cand.map(function (u) { return '<option value="' + u.id + '">' + esc(u.name) + ' · ' + esc(u.team) + '</option>'; }).join('') + '</select><button class="btn" id="as-btn">Assign</button></div><span class="small muted">The person is added straight away and notified. No invitation to accept.</span></div>' +
    '<div class="row wrap" style="margin-top:16px">' + (next && t.volunteers.length ? '<button class="btn secondary sm" id="m-adv">Advance to ' + next + '</button>' : '') + (!t.deliverable && t.volunteers.length ? '<button class="btn secondary sm" id="m-del">Mark deliverable added</button>' : '') + (t.stage === 'Presentation' && t.volunteers.length && !(t.presented || []).length ? '<button class="btn secondary sm" id="m-pres">Mark presentation completed</button>' : '') + '</div>',
    actions: [{ label: 'Done' }],
    onOpen: function (m) {
      var ab = $('#as-btn', m); if (ab) ab.addEventListener('click', function () { var v = $('#as-user', m).value; if (v) { assignUser(t, v); closeModal(); manageModal(id); } });
      $$('[data-mrm]', m).forEach(function (b) { b.addEventListener('click', function () { var v = b.getAttribute('data-mrm'); t.volunteers = t.volunteers.filter(function (x) { return x !== v; }); if (t.waitlist.length && t.volunteers.length < S.settings.maxVol) { var w = t.waitlist.shift(); addVolunteer(t, w); notify(w, 'A place opened up on "' + t.title + '" and you were added from the waitlist.'); } audit('Removed a volunteer', nameOf(v) + ' from ' + t.title); save(); closeModal(); manageModal(id); render(); }); });
      var a = $('#m-adv', m); if (a) a.addEventListener('click', function () { advanceStage(id); closeModal(); manageModal(id); });
      var pr = $('#m-pres', m); if (pr) pr.addEventListener('click', function () { markPresented(t); closeModal(); manageModal(id); });
      var d = $('#m-del', m); if (d) d.addEventListener('click', function () { t.deliverable = true; t.lastActivity = now(); save(); toast('Deliverable recorded.', 'ok'); closeModal(); manageModal(id); render(); });
    } });
}
function assignUser(t, uidv) {
  addVolunteer(t, uidv); notify(uidv, 'You were assigned to explore "' + t.title + '". No action needed — you are already on the topic.');
  audit('Assigned a volunteer', nameOf(uidv) + ' to ' + t.title); save();
  var over = t.volunteers.length > S.settings.maxVol; toast(nameOf(uidv) + ' was added and notified.' + (over ? ' The topic is now over the cap of ' + S.settings.maxVol + '.' : ''), over ? 'warn' : 'ok'); render();
}
function markPresented(t) {
  t.presented = t.volunteers.slice(); t.lastActivity = now();
  t.volunteers.forEach(function (p) {
    S.certs.push({ id: uid('ce'), userId: p, title: t.category + ' Contributor', topic: t.title, at: now() });
    notify(p, 'Your certificate for presenting "' + t.title + '" is ready in your profile.'); checkBadges(p);
  });
  audit('Marked a presentation completed', t.title); save(); toast('Presentation completed. Certificates issued to ' + plural(t.presented.length, 'presenter') + '.', 'ok'); render();
}
function assignModal(preId) {
  var tops = approved();
  openModal({ title: 'Assign volunteer', body: '<div class="stack"><div class="field"><label for="av-t">Topic</label><select class="input" id="av-t">' + tops.map(function (t) { return '<option value="' + t.id + '" ' + (t.id === preId ? 'selected' : '') + '>' + esc(t.title) + '</option>'; }).join('') + '</select></div><div class="field"><label for="av-u">Person</label><select class="input" id="av-u">' + contributors().map(function (u) { return '<option value="' + u.id + '">' + esc(u.name) + ' · ' + esc(u.team) + '</option>'; }).join('') + '</select></div></div>',
    actions: [{ label: 'Cancel', cls: 'secondary' }, { label: 'Assign', fn: function (m) { var t = topic($('#av-t', m).value), u = $('#av-u', m).value; if (t.volunteers.indexOf(u) > -1) { toast('That person is already on this topic.', 'warn'); return false; } assignUser(t, u); } }] });
}



/* ================================================================  BADGES */
function badgesView() {
  var awards = function (b) { return Object.keys(S.userBadges).filter(function (uid2) { return has(uid2, b.id); }).length; };
  var tops = contributors().map(function (u) { return { u: u, n: stat(u.id, 'testcases') + stat(u.id, 'artifacts') + stat(u.id, 'presentations') + stat(u.id, 'volunteer') }; }).sort(function (a, b) { return b.n - a.n; }).slice(0, 3);
  var body = '<div class="grid cols-main" style="grid-template-columns:minmax(0,1fr) 380px"><section class="card"><div class="card-head"><div class="grow"><h3>Badges</h3><div class="hint">Criteria for each badge</div></div>' +
    (HIDDEN.newBadge ? '' : '<button class="btn secondary sm" data-act="badge-new">New badge</button>') + '</div>' +
    S.badges.map(function (b) {
      var crit = CRITERIA.filter(function (c) { return c.id === b.criterion; })[0];
      return '<div class="attn"><div style="width:64px;flex:none">' + badgeArt(b.name) + '</div><div class="grow"><b>' + esc(b.name) + '</b><div class="small muted">' + esc(b.desc) + '</div><div class="small" style="margin-top:4px">' + chip('Earned after ' + b.threshold + ' · ' + (crit ? crit.label.toLowerCase() : ''), 'blue') + ' <span class="muted">' + awards(b) + ' awarded</span></div></div><button class="btn secondary sm" data-act="badge-edit" data-id="' + b.id + '">Edit</button></div>';
    }).join('') + '</section><div class="stack">' +
    '<section class="card"><div class="card-head"><div class="grow"><h3>Top contributors</h3><div class="hint">This quarter</div></div></div>' + tops.map(function (r, i) { return '<div class="attn"><b style="width:18px">' + (i + 1) + '</b><span class="avatar sm">' + esc(initials(r.u.name)) + '</span><div class="grow">' + esc(r.u.name) + '</div><span class="muted small">' + plural(r.n, 'contribution') + '</span></div>'; }).join('') + '</section></div></div>';
  return { title: 'Badges & Certificates', sub: 'Define how people are recognised for contributing.', action: HIDDEN.awardBadge ? '' : '<button class="btn" data-act="badge-award">' + icon('award') + ' Award badge</button>', body: body };
}
function badgeModal(id) {
  var b = id ? S.badges.filter(function (x) { return x.id === id; })[0] : { name: '', desc: '', criterion: 'volunteer', threshold: 1 };
  openModal({ title: id ? 'Edit badge' : 'New badge', body: '<div class="stack"><div class="field" id="f-bn"><label for="bn">Name</label><input class="input" id="bn" value="' + esc(b.name) + '"><span class="err-msg">Enter a name.</span></div><div class="field"><label for="bd">Description</label><input class="input" id="bd" value="' + esc(b.desc) + '"></div><div class="form-grid"><div class="field"><label for="bc">Criterion</label><select class="input" id="bc">' + CRITERIA.map(function (c) { return '<option value="' + c.id + '" ' + (b.criterion === c.id ? 'selected' : '') + '>' + c.label + '</option>'; }).join('') + '</select></div><div class="field" id="f-bt"><label for="bt">Threshold</label><input class="input" type="number" min="1" id="bt" value="' + b.threshold + '"><span class="err-msg">Use a whole number of 1 or more.</span></div></div></div>',
    actions: [{ label: 'Cancel', cls: 'secondary' }, { label: 'Save badge', fn: function (m) {
      var n = $('#bn', m).value.trim(), th = parseInt($('#bt', m).value, 10); $('#f-bn', m).classList.toggle('invalid', !n); $('#f-bt', m).classList.toggle('invalid', !(th >= 1)); if (!n || !(th >= 1)) return false;
      var o = id ? b : { id: uid('b') }; o.name = n; o.desc = $('#bd', m).value.trim(); o.criterion = $('#bc', m).value; o.threshold = th; if (!id) S.badges.push(o);
      audit(id ? 'Edited a badge' : 'Defined a badge', n); activeUsers().forEach(function (u) { if (stat(u.id, o.criterion) >= o.threshold) award(u.id, o.id); }); save(); toast('Badge saved.', 'ok'); render();
    } }] });
}
function awardModal() {
  openModal({ title: 'Award badge', body: '<div class="stack"><div class="field"><label for="ab-u">Person</label><select class="input" id="ab-u">' + activeUsers().map(function (u) { return '<option value="' + u.id + '">' + esc(u.name) + '</option>'; }).join('') + '</select></div><div class="field"><label for="ab-b">Badge</label><select class="input" id="ab-b">' + S.badges.map(function (b) { return '<option value="' + b.id + '">' + esc(b.name) + '</option>'; }).join('') + '</select></div></div>',
    actions: [{ label: 'Cancel', cls: 'secondary' }, { label: 'Award', fn: function (m) { var u = $('#ab-u', m).value, b = $('#ab-b', m).value; if (!award(u, b, true)) { toast(nameOf(u) + ' already has this badge.', 'warn'); return false; } save(); toast('Badge awarded to ' + nameOf(u) + '.', 'ok'); render(); } }] });
}


/* ===============================================================  SETTINGS */
function settingsView() {
  var integ = Object.keys(S.integrations);
  var body = '<div class="grid cols-2" style="align-items:start"><div class="stack"><section class="card"><div class="card-head"><div class="grow"><h3>Connected services</h3></div></div>' + integ.map(function (n) {
    var v = S.integrations[n];
    return '<div class="attn"><div class="grow"><b>' + n + '</b></div>' + (v === 'error' ? chip('Connection error', 'red') : chip(v ? 'Connected' : 'Not connected', v ? 'green' : '')) + '<button class="btn secondary sm" data-act="integ" data-id="' + esc(n) + '">' + (v === true ? 'Configure' : 'Connect') + '</button></div>';
  }).join('') + '</section>' +
    '<section class="card"><h3>Data retention</h3><div class="form-grid" style="margin-top:14px">' + numField('rule-ret', 'Archive finished topics after (months)', S.settings.retentionMonths) + '</div><div class="row" style="margin-top:14px"><button class="btn" data-act="ret-save">Save</button></div></section></div>' +
    '<section class="card"><h3>Default invitation rules</h3><div class="hint">Applied to every new topic</div><div class="form-grid" style="margin-top:14px">' +
    numField('rule-exp', 'Invitation expires after (days)', S.settings.expiryDays) + numField('rule-rem', 'Send a reminder every (days)', S.settings.reminderDays) + numField('rule-max', 'Maximum volunteers per topic', S.settings.maxVol) +
    '</div><div class="row" style="margin-top:14px"><button class="btn" data-act="rules-save">Save rules</button></div></section></div>';
  return { title: 'Settings', sub: 'Integrations and invitation rules.', body: body };
}
function numField(id, label, v) { return '<div class="field" id="f-' + id + '"><label for="' + id + '">' + label + '</label><input class="input" type="number" min="1" id="' + id + '" value="' + v + '"><span class="err-msg">Enter a whole number of 1 or more.</span></div>'; }
function download(name, text, type) { var b = new Blob([text], { type: type || 'text/plain' }), a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = name; document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
function integModal(name) {
  var v = S.integrations[name];
  openModal({ title: (v === true ? 'Configure ' : 'Connect ') + name, sub: 'Connection details are stored securely by the backend. This demo only simulates the result.', body: '<div class="field" id="f-ig"><label for="ig">' + (name === 'Email' ? 'Sender address' : 'Tenant or site URL') + '</label><input class="input" id="ig" value="' + (v === true ? 'neuleap.ai' : '') + '" placeholder="e.g. neuleap.sharepoint.com"><span class="err-msg">Enter the connection detail.</span></div><p class="small muted" style="margin-top:10px">Tip: type "invalid" to see how a failed connection looks.</p>',
    actions: [{ label: 'Cancel', cls: 'secondary' }].concat(v === true ? [{ label: 'Disconnect', cls: 'danger', fn: function () { S.integrations[name] = false; audit('Disconnected an integration', name); save(); toast(name + ' disconnected.', 'warn'); render(); } }] : []).concat([{ label: 'Save', fn: function (m) {
      var val = $('#ig', m).value.trim(); $('#f-ig', m).classList.toggle('invalid', !val); if (!val) return false;
      var bad = /invalid/i.test(val); S.integrations[name] = bad ? 'error' : true; audit(bad ? 'Integration failed to connect' : 'Connected an integration', name); save(); toast(bad ? name + ' could not connect. Check the details and try again.' : name + ' connected.', bad ? 'err' : 'ok'); render();
    } }]) });
}

/* =========================================================  EVENT WIRING */
var ACT = {
  goto: function (d) { go(d.to); },
  collapse: function () { UI.collapsed = !UI.collapsed; render(); },
  profile: function () { UI.profile = !UI.profile; UI.bell = false; render(); },
  bell: function () { UI.bell = !UI.bell; UI.profile = false; render(); },
  'read-all': function () { S.notifications.forEach(function (n) { if (n.to === S.session) n.read = true; }); save(); render(); },
  signout: function () { S.session = null; UI.profile = UI.bell = false; UI.signinError = ''; save(); location.hash = ''; render(); },
  'ms-signin': function () {
    var accts = [['u1', 'Aarav Mehta', 'aarav.mehta@neuleap.ai', 'Admin'], ['u2', 'Priya Sharma', 'priya.sharma@neuleap.ai', 'Contributor'], ['u8', 'Karan Verma', 'karan.verma@neuleap.ai', 'Deactivated in directory'], ['ext', 'Sam Carter', 'sam.carter@gmail.com', 'Personal Microsoft account']];
    openModal({ title: 'Pick an account', sub: 'Demo: this stands in for the Microsoft sign-in window.', body: accts.map(function (a) { return '<button class="account" data-acct="' + a[0] + '"><span class="avatar sm">' + esc(initials(a[1])) + '</span><span><b>' + esc(a[1]) + '</b><br><small class="muted">' + esc(a[2]) + ' · ' + esc(a[3]) + '</small></span></button>'; }).join(''), actions: [{ label: 'Cancel', cls: 'secondary' }],
      onOpen: function (m) { $$('[data-acct]', m).forEach(function (b) { b.addEventListener('click', function () {
        var id = b.getAttribute('data-acct'); closeModal();
        if (id === 'ext') { UI.signinError = 'Access is limited to company accounts'; return render(); }
        var u = user(id); if (u.status !== 'Active') { UI.signinError = 'Your account is deactivated. Ask an admin to restore access.'; return render(); }
        S.session = id; UI.signinError = ''; u.last = 'Today'; save(); location.hash = '#/' + homeRoute(); render(); // API: OIDC redirect to Microsoft Entra ID
      }); }); } });
  },
  'switch-user': function () { var id = $('#demo-user').value; S.session = id; UI.profile = false; UI.lastSubmitted = null; save(); location.hash = '#/' + homeRoute(); render(); toast('Signed in as ' + nameOf(id) + ' (' + user(id).role + ').', 'ok'); },
  'reset-demo': function () { S = seed(); UI.profile = false; UI.lastSubmitted = null; save(); location.hash = ''; render(); },
  'cert-dl': function (d) { var c = S.certs.filter(function (x) { return x.id === d.id; })[0]; download('certificate-' + slug(c.title) + '.txt', 'CERTIFICATE OF CONTRIBUTION\n\n' + nameOf(c.userId) + '\n' + c.title + '\nfor ' + c.topic + '\nIssued ' + dLong(c.at) + '\n\nNeuleap.ai · Tech Radar\n'); toast('Certificate downloaded.', 'ok'); },
  'toggle-topic': function (d) { UI.openTopic = UI.openTopic === d.id ? null : d.id; render(); },
  volunteer: function (d) { A_volunteer(d.id); },
  'add-tc': function (d) { addTestCase(d.id); },
  advance: function (d) { advanceStage(d.id); },
  deliverable: function (d) { var t = topic(d.id); t.deliverable = true; t.lastActivity = now(); save(); toast('Deliverable recorded. The topic is back on track.', 'ok'); render(); },
  'start-uc': function (d) { go('new-use-case?topic=' + d.id); },
  'custom-topic': function () { customTopicModal(); },
  'inv-accept': function (d) {
    var i = S.invitations.filter(function (x) { return x.id === d.id; })[0], t = topic(i.topicId);
    if (now() - i.at > S.settings.expiryDays * DAY) return toast('This invitation has expired.', 'err');
    if (t.volunteers.length >= S.settings.maxVol) { i.status = 'declined'; if (t.waitlist.indexOf(i.userId) < 0) t.waitlist.push(i.userId); save(); toast('That topic is already full. You were added to the waitlist.', 'warn'); return render(); }
    addVolunteer(t, i.userId); i.status = 'accepted'; notify(admins(), short(i.userId) + ' accepted the invitation to "' + t.title + '".'); save(); toast('You joined "' + t.title + '". Study deadline: ' + dShort(t.deadline) + '.', 'ok'); render();
  },
  'inv-decline': function (d) { var i = S.invitations.filter(function (x) { return x.id === d.id; })[0], t = topic(i.topicId); i.status = 'declined'; notify(i.by, short(i.userId) + ' declined the invitation to "' + t.title + '".'); save(); toast('Declined. The admin who invited you has been notified.', 'ok'); render(); },
  browse: function () { var f = $('#file-input'); if (f) f.click(); },
  'file-remove': function (d) { var dr = getDraft(); dr.files.splice(+d.i, 1); markDirty(); saveDraft(true); render(); },
  'co-remove': function (d) { var dr = getDraft(); dr.co = dr.co.filter(function (x) { return x !== d.id; }); markDirty(); saveDraft(true); render(); },
  'use-suggestion': function () { var dr = getDraft(), t = topic(dr.topicId); dr.problem = t.suggestion; markDirty(); saveDraft(true); render(); toast('Problem prefilled from the agent suggestion.', 'ok'); },
  'uc-save': function () { saveDraft(true); toast('Draft saved.', 'ok'); },
  'uc-cancel': function () { delete S.drafts[S.session]; save(); go('dashboard'); },
  'uc-submit': function () { submitUseCase(); },
  'open-page': function (d, e) { e.preventDefault(); var uc = S.useCases.filter(function (x) { return x.id === d.id; })[0]; openModal({ title: uc.title, sub: pageUrl(uc), body: '<p class="muted small">Shareable page</p><h3 style="margin:8px 0 4px">Problem</h3><p>' + esc(uc.problem) + '</p><h3 style="margin:14px 0 4px">Solution approach</h3><p>' + esc(uc.approach) + '</p>', wide: true }); },
  'upload-artifact': function () {
    openModal({ title: 'Upload artifact', sub: 'It goes to the moderation queue before it is shared.', body: '<div class="stack"><div class="field" id="f-an"><label for="an-t">Title</label><input class="input" id="an-t"><span class="err-msg">Enter a title.</span></div><div class="stack"><div class="field"><label for="an-ty">Type</label><select class="input" id="an-ty">' + ART_TYPES.map(function (x) { return '<option>' + x + '</option>'; }).join('') + '</select></div></div><div class="field"><label for="an-s">Summary</label><textarea class="input" id="an-s" style="min-height:80px"></textarea></div></div>',
      actions: [{ label: 'Cancel', cls: 'secondary' }, { label: 'Submit for review', fn: function (m) { var t = $('#an-t', m).value.trim(); $('#f-an', m).classList.toggle('invalid', !t); if (!t) return false; var s = $('#an-s', m).value; S.queue.unshift({ id: uid('q'), title: t, type: $('#an-ty', m).value, authorId: S.session, at: now(), flags: scanSubmission(t + ' ' + s, []), note: $('#an-ty', m).value, summary: s, useCaseId: null, topicId: null, status: 'pending' }); save(); toast('Submitted for moderation.', 'ok'); } }] });
  },
  'open-artifact': function (d) { var a = S.artifacts.filter(function (x) { return x.id === d.id; })[0]; openModal({ title: a.title, sub: a.type + ' · ' + nameOf(a.authorId) + ' · ' + dLong(a.at), body: '<p>' + esc(a.summary) + '</p><dl class="kv" style="margin-top:14px"><dt>Location</dt><dd class="mono">SharePoint · Tech Radar Repository / ' + esc(a.type) + '</dd></dl>' }); },
  'mod-approve': function (d) { modApprove(d.id); }, 'mod-reject': function (d) { modReason(d.id); },
  'mod-replaced': function (d, e) { e.preventDefault(); var q = S.queue.filter(function (x) { return x.id === d.id; })[0]; q.flags = q.flags.filter(function (f) { return f.kind !== 'secret'; }); q.note = 'File replaced and scanned — no secrets found'; save(); toast('File replaced and re-scanned. Approval is now possible.', 'ok'); render(); },
  'src-add': function () { sourceModal(); }, 'src-edit': function (d) { sourceModal(d.id); },
  'src-remove': function (d) { var s = S.sources.filter(function (x) { return x.id === d.id; })[0]; openModal({ title: 'Remove source?', body: '<p>The agent will stop crawling <b>' + esc(s.name) + '</b>. Topics already found stay in place.</p>', actions: [{ label: 'Cancel', cls: 'secondary' }, { label: 'Remove', cls: 'danger', fn: function () { S.sources = S.sources.filter(function (x) { return x.id !== d.id; }); audit('Removed a source', s.name); save(); toast('Source removed.', 'ok'); render(); } }] }); },
  'cat-add': function () { openModal({ title: 'Add category', body: '<div class="field" id="f-cn"><label for="cn">Name</label><input class="input" id="cn"><span class="err-msg">Enter a unique name.</span></div>', actions: [{ label: 'Cancel', cls: 'secondary' }, { label: 'Add', fn: function (m) { var n = $('#cn', m).value.trim(), dup = S.categories.some(function (c) { return c.name.toLowerCase() === n.toLowerCase(); }); $('#f-cn', m).classList.toggle('invalid', !n || dup); if (!n || dup) return false; S.categories.push({ id: uid('c'), name: n, retired: false }); audit('Added a category', n); save(); toast('Category added.', 'ok'); render(); } }] }); },
  'cat-rename': function (d) { var c = S.categories.filter(function (x) { return x.id === d.id; })[0]; openModal({ title: 'Rename category', body: '<div class="field" id="f-cn"><label for="cn">Name</label><input class="input" id="cn" value="' + esc(c.name) + '"><span class="err-msg">Enter a unique name.</span></div>', actions: [{ label: 'Cancel', cls: 'secondary' }, { label: 'Save', fn: function (m) { var n = $('#cn', m).value.trim(), dup = S.categories.some(function (x) { return x.id !== c.id && x.name.toLowerCase() === n.toLowerCase(); }); $('#f-cn', m).classList.toggle('invalid', !n || dup); if (!n || dup) return false; S.topics.forEach(function (t) { if (t.category === c.name) t.category = n; }); if (UI.filterCat === c.name) UI.filterCat = n; audit('Renamed a category', c.name + ' → ' + n); c.name = n; save(); toast('Category renamed.', 'ok'); render(); } }] }); },
  'cat-retire': function (d) { var c = S.categories.filter(function (x) { return x.id === d.id; })[0]; c.retired = !c.retired; if (c.retired && UI.filterCat === c.name) UI.filterCat = 'All'; audit(c.retired ? 'Retired a category' : 'Restored a category', c.name); save(); toast(c.retired ? 'Category retired. It is no longer offered for new topics.' : 'Category restored.', 'ok'); render(); },
  'kw-add': function (d) { var el = $('#kw-' + d.kind), v = el.value.trim(); if (!v) return; if (S[d.kind].indexOf(v) < 0) S[d.kind].push(v); audit('Changed ' + d.kind + ' keywords', v); save(); render(); },
  'kw-remove': function (d) { var removed = S[d.kind].splice(+d.i, 1); audit('Changed ' + d.kind + ' keywords', 'removed ' + removed[0]); save(); render(); },
  'vol-manage': function (d) { manageModal(d.id); }, 'vol-assign': function () { assignModal(); },
  'badge-new': function () { badgeModal(); }, 'badge-edit': function (d) { badgeModal(d.id); }, 'badge-award': function () { awardModal(); },
  integ: function (d) { integModal(d.id); },
  'rules-save': function () {
    var ids = [['rule-exp', 'expiryDays'], ['rule-rem', 'reminderDays'], ['rule-max', 'maxVol']], vals = {}, bad = false;
    ids.forEach(function (x) { var v = parseInt($('#' + x[0]).value, 10), b = !(v >= 1); $('#f-' + x[0]).classList.toggle('invalid', b); if (b) bad = true; vals[x[1]] = v; });
    if (bad) return toast('Fix the highlighted fields.', 'err');
    Object.keys(vals).forEach(function (k) { S.settings[k] = vals[k]; }); audit('Changed default invitation rules', 'expiry ' + vals.expiryDays + 'd, reminder ' + vals.reminderDays + 'd, max ' + vals.maxVol); save(); toast('Rules saved. They apply to every new topic.', 'ok'); render();
  },
  'ret-save': function () { var v = parseInt($('#rule-ret').value, 10); if (!(v >= 1)) { $('#f-rule-ret').classList.add('invalid'); return; } S.settings.retentionMonths = v; audit('Changed data retention', v + ' months'); save(); toast('Retention saved.', 'ok'); render(); },
};
var CHG = {
  modType: function (v) { UI.flt.modType = v; render(); },
  volStatus: function (v) { UI.flt.vol = v; render(); }
};
document.addEventListener('click', function (e) {
  if (UI.profile || UI.bell) { if (!e.target.closest('.popover') && !e.target.closest('[data-act="profile"]') && !e.target.closest('[data-act="bell"]')) { UI.profile = UI.bell = false; render(); } }
  var el = e.target.closest('[data-act]'); if (!el) return;
  var f = ACT[el.getAttribute('data-act')]; if (!f) return;
  var d = {}; Array.prototype.forEach.call(el.attributes, function (a) { if (a.name.indexOf('data-') === 0) d[a.name.slice(5)] = a.value; });
  if (el.tagName === 'A') e.preventDefault();
  f(d, e);
});
document.addEventListener('keydown', function (e) { if ((e.key === 'Enter' || e.key === ' ') && e.target.getAttribute && e.target.getAttribute('data-act') === 'toggle-topic') { e.preventDefault(); ACT['toggle-topic']({ id: e.target.getAttribute('data-id') }); } });
document.addEventListener('change', function (e) {
  var t = e.target;
  if (t.id === 'cat-filter') { UI.filterCat = t.value; return render(); }
  if (t.id === 'lib-type') { UI.libType = t.value; return renderLibrary(); }
  var k = t.getAttribute && t.getAttribute('data-chg'); if (k && CHG[k]) CHG[k](t.value, t);
});
document.addEventListener('input', function (e) {
  var t = e.target;
  if (t.id === 'lib-q') { UI.libQ = t.value; return renderLibrary(); }
});

/* ----------------------------------------------------------------- boot */
render();
})();
