// Mock data for the preview: the facets, their lobes on the brain, the item types, every item, and the open conversations.
// Shapes follow the app's ROW contract ({id, module, title, when, tags, fixed, …extras}). An item's one immutable tag is its
// facet's; `type` picks its renderer; `verbs` are what the facet allows on the item; `waits` ranks it in Priority.
// Dates are 2026-09-20 today.

const TARGET = '<circle cx="4.5" cy="10" r="2.6"></circle><path d="M8.7 7v6M11.3 7v6"></path><circle cx="15.5" cy="10" r="2.6"></circle>';
const DOC = '<rect x="4" y="3" width="12" height="14" rx="1.5"></rect><path d="M7 7.5c.8-.8 1.6.8 2.4 0s1.6.8 2.4 0 1.2-.4 1.2-.4M7 10.5c.8-.8 1.6.8 2.4 0s1.6.8 2.4 0 1.2-.4 1.2-.4M7 13.5c.8-.8 1.6.8 2.4 0s1.2-.4 1.2-.4"></path>';
export const MODS = {
  otto: { id: 'otto', title: 'Otto', hue: '#ECEEF2', icon: TARGET },
  chat: { id: 'chat', title: 'Chat', hue: '#E0A06E', icon: '<path d="M4 4h12v9H9l-4 3v-3H4Z"></path>' },
  email: { id: 'email', title: 'Email', hue: '#E38A8A', icon: '<rect x="3" y="5" width="14" height="10" rx="2"></rect><path d="M3 7l7 5 7-5"></path>' },
  education: { id: 'education', title: 'Education', hue: '#86AAE3', icon: '<path d="M2 8l8-4 8 4-8 4-8-4Z"></path><path d="M6 10v4c0 1.2 2 2 4 2s4-.8 4-2v-4"></path><path d="M18 8v5"></path>' },
  second_brain: { id: 'second_brain', title: 'Note', hue: '#DDB06F', icon: DOC },
  science: { id: 'science', title: 'Science', hue: '#7FC0C4', icon: '<path d="M8 3v6l-4.5 7.5A1 1 0 0 0 4.4 18h11.2a1 1 0 0 0 .9-1.5L12 9V3"></path><path d="M6.5 3h7"></path><path d="M6 13h8"></path>' },
  finance: { id: 'finance', title: 'Finance', hue: '#8CC79E', icon: '<rect x="2" y="5" width="16" height="10" rx="1.5"></rect><circle cx="10" cy="10" r="2.5"></circle><path d="M5 8.5v3M15 8.5v3"></path>' },
  newsfeed: { id: 'newsfeed', title: 'Newsfeed', hue: '#D79EBB', icon: '<path d="M4 12a4 4 0 0 1 4 4"></path><path d="M4 8a8 8 0 0 1 8 8"></path><path d="M4 4a12 12 0 0 1 12 12"></path><circle cx="4.5" cy="15.5" r="1"></circle>' },
  database: { id: 'database', title: 'Database', hue: '#B39BDB', icon: '<rect x="3" y="4" width="14" height="12" rx="2"></rect><path d="M3 10h14"></path>' },
  activity: { id: 'activity', title: 'Activity', hue: '#A6ACB8', icon: '<path d="M3 12h4l2-6 3 10 2-6h3"></path>' },
  system: { id: 'system', title: 'System', hue: '#A6ACB8', icon: '<circle cx="10" cy="10" r="7"></circle><path d="M10 6v4l3 2"></path>' },
  settings: { id: 'settings', title: 'Settings', hue: '#A6ACB8', icon: '<circle cx="10" cy="10" r="6.5"></circle><circle cx="10" cy="10" r="2"></circle>' },
};
export const ORDER = ['otto', 'chat', 'email', 'education', 'second_brain', 'science', 'finance', 'newsfeed', 'database', 'system'];

// The immutable tags: one per facet, in the facets' order. An item carries exactly one; its renderer is its `type`.
export const FIXED_ORDER = ['entry', 'chats', 'email', 'education', 'science', 'finance', 'newsfeed', 'database', 'routine'];
export const FIXED_MOD = { entry: 'second_brain', chats: 'chat', email: 'email', education: 'education', science: 'science', finance: 'finance', newsfeed: 'newsfeed', database: 'database', routine: 'system' };   // routine: what the daemon and its agents run on a schedule

// Where each facet sits on the figure: a heading around the vertical axis (0 is the front) and an elevation. Entry and
// finance on the frontal lobe either side of the fissure, chats and email on the temporal lobes, education and science on
// the parietal lobes, newsfeed on the occipital lobe, database on the cerebellum, routine on the stem.
export const LOBES = [
  { id: 'second_brain', th: 25, ph: 40 }, { id: 'finance', th: -25, ph: 40 },
  { id: 'chat', th: -71, ph: -25 }, { id: 'email', th: 71, ph: -25 },
  { id: 'education', th: -140, ph: 40 }, { id: 'science', th: 140, ph: 40 },
  { id: 'newsfeed', th: 180, ph: 12 }, { id: 'database', th: 180, ph: -36 }, { id: 'system', th: 180, ph: -79 },
];

const MAIL = (...ps) => ps.map((p) => `<p>${p}</p>`).join('');
const EMAIL_VERBS = [['archive', 'Archive'], ['star', 'Star'], ['open', 'Open in Gmail'], ['trash', 'Trash']];
const READ_VERBS = [['archive', 'Archive'], ['unread', 'Mark unread'], ['open', 'Open in Gmail'], ['trash', 'Trash']];
const ENTRY_VERBS = [['update', 'Update amount'], ['due', 'Set date'], ['end', 'End'], ['edit', 'Edit'], ['forget', 'Forget']];
const ACCT_VERBS = [['update', 'Update amount'], ['end', 'End'], ['edit', 'Edit'], ['forget', 'Forget']];
const ART_VERBS = [['accept', 'Accept'], ['link', 'Open link'], ['dismiss', 'Dismiss']];
export const ITEMS = [
  { id: 'd1', module: 'otto', type: 'decision', title: 'Tuition of $2,140 due 10-01 leaves checking at $412 after rent', when: '2026-09-20T06:10', tags: ['decision', 'tuition', 'fall-2026'], fixed: ['finance'], due: '2026-10-01', waits: 1,
    kv: [['Checking', '$2,552.00 today'], ['Rent', '$2,145.00 on 09-25-2026'], ['Tuition', '$2,140.00 on 10-01-2026'], ['Savings', '$6,300.00']],
    summary: 'Rent and tuition both land before the next paycheck; $300 from savings covers the gap without touching the floor.', body: '<p>Moving $300 keeps checking above $700 through the 15th. Nothing else is due before then.</p>', related: ['e1', 'f9', 'f1'],
    verbs: [['do', 'Move $300 to checking'], ['later', 'Not now'], ['edit', 'Edit'], ['delete', 'Delete']],
    reply: 'Rent clears 09-25 and leaves $407; tuition on 10-01 would overdraw by $1,733 without the move. Savings can spare $300 and stay above its floor. Say “do” and I file the transfer as an entry for you to make.' },

  { id: 'e1', module: 'email', type: 'email', title: 'Fall 2026 tuition statement', snip: 'Bursar’s Office', when: '2026-09-20T08:14', unread: true, tags: ['tuition', 'fall-2026'], fixed: ['email'], waits: 2,
    summary: 'The fall term statement: $2,140 due 10-01, with a 1.5% monthly charge after that.',
    kv: [['From', 'Bursar’s Office'], ['Priority', 'high, a balance due in eleven days'], ['Attached', 'statement-fall-2026.pdf']],
    body: MAIL('Your statement for the Fall 2026 term is available.<span class="url">↗</span> The balance of $2,140.00 is due October 1.', 'Payments received after the due date accrue a 1.5% monthly finance charge.'), related: ['d1', 'f9'], verbs: EMAIL_VERBS,
    reply: 'A statement, not a bill you can dispute: $2,140 due 10-01, with a 1.5% charge a month after. I filed it as a Finance entry and put the shortfall at the top of Priority.' },
  { id: 'e10', module: 'email', type: 'email', title: 'Q3 estimated tax: payment window closes 09-15', snip: 'IRS Direct Pay', when: '2026-09-20T07:05', unread: true, tags: ['tax'], fixed: ['email'], waits: 8,
    kv: [['From', 'IRS Direct Pay'], ['Priority', 'high, the deadline has passed']],
    body: MAIL('Your scheduled payment for the third quarter has not been received. Payments made after September 15 may accrue a penalty.'), related: ['f7', 'b6'], verbs: EMAIL_VERBS,
    reply: 'It is five days late. The Finance entry says $6,400; the task to pay it is still open under Note.' },
  { id: 'e3', module: 'email', type: 'email', title: 'Passport renewal appointment confirmed', snip: 'travel.state.gov', when: '2026-09-19T15:40', unread: true, tags: ['travel'], fixed: ['email'],
    kv: [['From', 'travel.state.gov'], ['Priority', 'normal']], body: MAIL('Your appointment is confirmed for 10-14-2026 at 9:30. Bring the DS-82 form, one photo, and your current passport.'), related: ['b2'], verbs: EMAIL_VERBS },
  { id: 'e2', module: 'email', type: 'email', title: 'Your September statement is ready', snip: 'Chase', when: '2026-09-19T17:02', dim: true, tags: ['statements'], fixed: ['email'],
    kv: [['From', 'Chase'], ['Priority', 'low']], body: MAIL('Your statement for the period ending 09-18-2026 is available in the app.'), verbs: READ_VERBS },
  { id: 'e4', module: 'email', type: 'email', title: 'Weekly digest: math.DG', snip: 'arXiv', when: '2026-09-19T06:00', dim: true, tags: ['geometry', 'newsletters'], fixed: ['email'],
    kv: [['From', 'arXiv'], ['Priority', 'low']], body: MAIL('Fourteen new listings in differential geometry this week.'), verbs: READ_VERBS },
  { id: 'e5', module: 'email', type: 'email', title: 'Receipt: Trader Joe’s $86.40', snip: 'Trader Joe’s', when: '2026-09-18T19:22', dim: true, tags: ['groceries', 'receipts'], fixed: ['email'],
    kv: [['From', 'Trader Joe’s'], ['Priority', 'low']], body: MAIL('Thanks for shopping with us. Your total was $86.40.'), verbs: READ_VERBS },
  { id: 'e6', module: 'email', type: 'email', title: 'Photos from the lake', snip: 'Dad', when: '2026-09-18T12:10', dim: true, tags: ['family'], fixed: ['email'],
    kv: [['From', 'Dad'], ['Priority', 'normal'], ['Attached', '6 photos']], body: MAIL('Finally got the boat out. Your mother says hello.'), verbs: EMAIL_VERBS },
  { id: 'e7', module: 'email', type: 'email', title: 'Your Claude Max invoice', snip: 'Anthropic', when: '2026-09-17T09:31', dim: true, tags: ['otto', 'receipts'], fixed: ['email'],
    kv: [['From', 'Anthropic'], ['Priority', 'low']], body: MAIL('Invoice for September: $200.00, paid.'), verbs: READ_VERBS },
  { id: 'e8', module: 'email', type: 'email', title: 'Membership renews 10-01', snip: 'Fitness 19', when: '2026-09-16T08:00', dim: true, tags: ['gym'], fixed: ['email'],
    kv: [['From', 'Fitness 19'], ['Priority', 'low']], body: MAIL('Your monthly membership of $49.00 renews on October 1.'), verbs: READ_VERBS },
  { id: 'e9', module: 'email', type: 'email', title: 'Policy documents for 2026–27', snip: 'Lemonade', when: '2026-09-15T11:45', dim: true, tags: ['insurance', 'home'], fixed: ['email'],
    kv: [['From', 'Lemonade'], ['Priority', 'low'], ['Attached', 'policy-2026.pdf']], body: MAIL('Your renewed homeowners policy is attached. The annual premium is $1,284.00, due 10-12.'), verbs: READ_VERBS },

  { id: 'q1', module: 'education', type: 'question', title: 'Möbius maps of the disc are hyperbolic isometries', when: '2026-09-19T23:40', tags: ['hyperbolic-geometry'], fixed: ['education'], pct: 50, waits: 6, summary: 'Two parts: the derivative of a disc automorphism, then the pullback of the metric. Part (a) is graded.',
    defs: ['A Möbius transformation of the disc is a map <i>f</i>(<i>z</i>) = <i>e</i><sup><i>iθ</i></sup>(<i>z</i> − <i>a</i>)/(1 − <i>āz</i>) with |<i>a</i>| &lt; 1 and <i>θ</i> real.', 'The hyperbolic metric is <i>ds</i> = 2|<i>dz</i>| / (1 − |<i>z</i>|<sup>2</sup>) on the open unit disc.'],
    premise: 'Let <i>f</i> be a Möbius transformation that preserves the unit disc.',
    parts: [{ n: 'a', title: 'Derivative', ask: 'Compute |<i>f</i>′(<i>z</i>)| and express it in terms of |<i>a</i>| and |1 − <i>āz</i>|.', score: 82 }, { n: 'b', title: 'Pullback', ask: 'Show that <i>f</i> pulls the hyperbolic metric back to itself.', score: null }],
    verbs: [['answer', 'Answer'], ['explain', 'Explain'], ['delete', 'Delete']] },
  { id: 'q3', module: 'education', type: 'question', title: 'Cross-ratio invariance under Möbius maps', when: '2026-09-19T23:41', tags: ['hyperbolic-geometry'], fixed: ['education'], pct: 0, waits: 9,
    defs: ['The cross-ratio of four distinct points is [<i>z</i><sub>1</sub>, <i>z</i><sub>2</sub>; <i>z</i><sub>3</sub>, <i>z</i><sub>4</sub>] = (<i>z</i><sub>1</sub> − <i>z</i><sub>3</sub>)(<i>z</i><sub>2</sub> − <i>z</i><sub>4</sub>) / ((<i>z</i><sub>1</sub> − <i>z</i><sub>4</sub>)(<i>z</i><sub>2</sub> − <i>z</i><sub>3</sub>)).'],
    premise: 'Let <i>f</i> be any Möbius transformation of the Riemann sphere.',
    parts: [{ n: 'a', title: 'Generators', ask: 'Show the cross-ratio is unchanged by translations, dilations and the inversion <i>z</i> ↦ 1/<i>z</i>.', score: null }, { n: 'b', title: 'Distance', ask: 'Express the hyperbolic distance between two points of the disc through a cross-ratio with their ideal endpoints.', score: null }],
    verbs: [['answer', 'Answer'], ['explain', 'Explain'], ['delete', 'Delete']] },
  { id: 'q2', module: 'education', type: 'question', title: 'Gauss–Bonnet on a hyperbolic pair of pants', when: '2026-09-14T22:10', tags: ['hyperbolic-geometry', 'geometry'], fixed: ['education'], pct: 100, done: true,
    defs: ['A pair of pants is a sphere with three boundary circles, here with a hyperbolic metric making each boundary a geodesic.'],
    premise: 'Let <i>P</i> be a hyperbolic pair of pants with geodesic boundary.',
    parts: [{ n: 'a', title: 'Area', ask: 'Compute the area of <i>P</i> from Gauss–Bonnet.', score: 96 }, { n: 'b', title: 'Seams', ask: 'Show the three seams cut <i>P</i> into two right-angled hexagons.', score: 88 }],
    verbs: [['delete', 'Delete']] },
  { id: 'q4', module: 'education', type: 'question', title: 'Horocycles and the ideal boundary', when: '2026-09-12T21:30', tags: ['hyperbolic-geometry'], fixed: ['education'], pct: 100, done: true,
    defs: ['A horocycle is a curve in the disc model that is a Euclidean circle tangent to the boundary circle from the inside.'],
    premise: 'Fix an ideal point <i>ξ</i> on the boundary of the disc.',
    parts: [{ n: 'a', title: 'Orthogonality', ask: 'Show every geodesic ending at <i>ξ</i> meets every horocycle at <i>ξ</i> at a right angle.', score: 90 }],
    verbs: [['delete', 'Delete']] },

  { id: 'b1', module: 'second_brain', type: 'suggestion', title: 'Tag the three notebooks under thesis/ with #causal', when: '2026-09-20T03:30', tags: ['suggestion'], fixed: ['entry'], waits: 5, taggable: false,
    body: '<p>sensitivity_bounds.ipynb, iv_weak_instruments.ipynb and ope_doubly_robust.ipynb are read by the notes tagged #causal and carry no tag of their own.</p>',
    verbs: [['accept', 'Accept'], ['dismiss', 'Dismiss']] },
  { id: 'b2', module: 'second_brain', type: 'task', title: 'Renew passport before the March trip', when: '2026-09-18T10:05', tags: ['task', 'travel', 'march-trip'], fixed: ['entry'], done: false, related: ['e3', 'c1'],
    verbs: [['done', 'Done'], ['edit', 'Edit'], ['forget', 'Forget']] },
  { id: 'b6', module: 'second_brain', type: 'task', title: 'Pay Q3 estimated tax', when: '2026-09-17T21:40', tags: ['task', 'tax', 'urgent'], fixed: ['entry'], done: false, related: ['f7', 'e10'],
    verbs: [['done', 'Done'], ['edit', 'Edit'], ['forget', 'Forget']] },
  { id: 'b3', module: 'second_brain', type: 'note', title: 'Geodesics of the disc model are circle arcs meeting the boundary at right angles; diameters are the degenerate case', snip: 'from the Quiz chat', when: '2026-09-19T23:55', tags: ['hyperbolic-geometry'], fixed: ['entry'],
    verbs: [['edit', 'Edit'], ['forget', 'Forget']] },
  { id: 'b4', module: 'second_brain', type: 'note', title: 'Idea: score each nightly search by how many entries I accept, retire the ones below 10 percent after a month', when: '2026-09-16T23:02', tags: ['otto', 'ideas'], fixed: ['entry'],
    verbs: [['edit', 'Edit'], ['forget', 'Forget']] },
  { id: 'b9', module: 'second_brain', type: 'note', title: 'Off-policy evaluation with doubly robust estimators blows up when the behavior policy is near-deterministic; clip the ratio at 20', when: '2026-09-14T22:10', tags: ['rl', 'thesis'], fixed: ['entry'],
    verbs: [['edit', 'Edit'], ['forget', 'Forget']] },
  { id: 'b5', module: 'second_brain', type: 'quote', title: '“A model is a lie that helps you see the truth.” Howard Skipper', when: '2026-09-15T19:47', tags: ['quote', 'reading', 'quotes'], fixed: ['entry'],
    verbs: [['edit', 'Edit'], ['forget', 'Forget']] },
  { id: 'b7', module: 'second_brain', type: 'link', title: 'arxiv.org/abs/2609.01234 Chronos-2: zero-shot forecasting with covariates', when: '2026-09-17T12:14', tags: ['link', 'time-series', 'reading'], fixed: ['entry'],
    verbs: [['open', 'Open'], ['forget', 'Forget']] },
  { id: 'b8', module: 'second_brain', type: 'task', title: 'Replace furnace filter', when: '2026-09-16T08:30', tags: ['task', 'home'], fixed: ['entry'], done: true,
    verbs: [['reopen', 'Reopen'], ['forget', 'Forget']] },

  { id: 's1', module: 'science', type: 'notebook', title: 'thesis/disc_isometries.ipynb', when: '2026-09-19T22:31', tags: ['notebook', 'hyperbolic-geometry', 'thesis'], fixed: ['science'], right: 'cell 6 raised', summary: 'Samples the disc metric; cell 6 divides by zero on the boundary circle.', status: 'idle, 09-19-2026 22:31',
    cells: [{ g: '[5]', code: '<span class="k">def</span> metric(z):\n    <span class="k">return</span> <span class="n">2</span> / (<span class="n">1</span> - abs(z)**<span class="n">2</span>)' }, { g: '[6]', run: true, code: 'samples = disc_boundary(<span class="n">64</span>)\n[metric(z) <span class="k">for</span> z <span class="k">in</span> samples]', out: 'ZeroDivisionError: float division by zero', err: true }],
    verbs: [['run', 'Run all'], ['restart', 'Restart kernel'], ['shutdown', 'Shut down kernel'], ['schedule', 'Schedule']],
    reply: 'Cell 6 samples the boundary circle itself, where 1 − |z|² is exactly zero. Sample a radius just inside, 0.999, or skip the boundary: the metric has no value there by design.' },
  { id: 's2', module: 'science', type: 'script', title: 'rl/sweep_spec.py', when: '2026-09-17T09:12', tags: ['script', 'rl', 'thesis'], fixed: ['science'], right: 'every 1 d at 06:00', related: ['r6'], status: 'scheduled, every 1 d at 06:00, last exit 0',
    cells: [{ g: '', code: '<span class="k">import</span> json, itertools\n\nGRID = {<span class="s">"lr"</span>: [<span class="n">1e-4</span>, <span class="n">3e-4</span>], <span class="s">"clip"</span>: [<span class="n">10</span>, <span class="n">20</span>]}\n<span class="k">for</span> spec <span class="k">in</span> itertools.product(*GRID.values()):\n    print(json.dumps(dict(zip(GRID, spec))))' }],
    verbs: [['run', 'Run'], ['unschedule', 'Unschedule']] },

  { id: 'f1', module: 'finance', type: 'ledger', title: 'Rent', snip: 'monthly', when: '2026-09-20T09:00', tags: ['recurring', 'home'], fixed: ['finance'], amount: '$2,145.00', due: '2026-09-25', waits: 7,
    kv: [['Cadence', 'monthly'], ['Note', 'Landlord ACH on the 25th.']], hist: [['09-01-2026', '$2,145.00'], ['03-01-2026', '$2,095.00'], ['03-01-2025', '$1,995.00']], verbs: ENTRY_VERBS },
  { id: 'f9', module: 'finance', type: 'ledger', title: 'Tuition', snip: 'from the Tuition chat', when: '2026-09-20T08:20', tags: ['recurring', 'tuition', 'fall-2026'], fixed: ['finance'], amount: '$2,140.00', due: '2026-10-01',
    kv: [['Cadence', 'yearly'], ['Note', 'Fall term statement; the bursar charges 1.5% a month after the due date.']], hist: [['09-20-2026', '$2,140.00']], related: ['e1', 'd1'], verbs: ENTRY_VERBS },
  { id: 'f7', module: 'finance', type: 'ledger', title: 'Q3 estimated tax', snip: 'yearly', when: '2026-09-10T09:00', tags: ['recurring', 'tax', 'urgent'], fixed: ['finance'], amount: '$6,400.00', due: '2026-09-15', late: true, waits: 3,
    kv: [['Cadence', 'yearly'], ['Note', 'IRS Direct Pay, third quarter.']], hist: [['09-10-2026', '$6,400.00'], ['06-10-2026', '$6,400.00']], related: ['e10', 'b6'], verbs: ENTRY_VERBS },
  { id: 'f3', module: 'finance', type: 'ledger', title: 'Checking 4471', when: '2026-09-20T08:00', tags: ['account'], fixed: ['finance'], amount: '$2,552.00',
    kv: [['Note', 'Balance as of this morning.']], hist: [['09-20-2026', '$2,552.00'], ['09-13-2026', '$3,910.00'], ['09-06-2026', '$4,102.00']], verbs: ACCT_VERBS },
  { id: 'f4', module: 'finance', type: 'ledger', title: 'Savings', when: '2026-09-15T08:00', tags: ['account'], fixed: ['finance'], amount: '$6,300.00',
    kv: [['Note', 'Floor of $5,000.']], hist: [['09-15-2026', '$6,300.00'], ['08-15-2026', '$6,100.00']], verbs: ACCT_VERBS },
  { id: 'f5', module: 'finance', type: 'ledger', title: 'VTI', when: '2026-09-15T08:00', tags: ['holding', 'index'], fixed: ['finance'], amount: '$52,100.50',
    kv: [['Note', 'Brokerage, 172 shares.']], hist: [['09-15-2026', '$52,100.50'], ['08-15-2026', '$50,880.00']], verbs: ACCT_VERBS },
  { id: 'f6', module: 'finance', type: 'ledger', title: 'Homeowners insurance', snip: 'yearly', when: '2026-09-17T18:30', tags: ['recurring', 'insurance', 'home'], fixed: ['finance'], amount: '$1,284.00', due: '2026-10-12',
    kv: [['Cadence', 'yearly'], ['Note', 'Lemonade, renews in October.']], hist: [['09-17-2026', '$1,284.00'], ['09-17-2025', '$1,190.00']], related: ['e9'], verbs: ENTRY_VERBS },
  { id: 'f8', module: 'finance', type: 'ledger', title: 'Claude Max', snip: 'monthly', when: '2026-09-04T09:00', tags: ['recurring', 'otto'], fixed: ['finance'], amount: '$200.00', due: '2026-10-04',
    kv: [['Cadence', 'monthly']], hist: [['09-04-2026', '$200.00']], related: ['e7'], verbs: ENTRY_VERBS },
  { id: 'f2', module: 'finance', type: 'ledger', title: 'Groceries', snip: 'monthly', when: '2026-09-01T09:00', tags: ['budget', 'groceries'], fixed: ['finance'], amount: '$600.00',
    kv: [['Cadence', 'monthly'], ['Note', 'Normalized to the month; the totals strip counts it under budget.']], hist: [['09-01-2026', '$600.00'], ['01-01-2026', '$550.00']], verbs: ACCT_VERBS },

  { id: 'a1', module: 'newsfeed', type: 'article', title: 'Geometric deep learning on hyperbolic manifolds: a survey', snip: 'arXiv', when: '2026-09-20T04:12', tags: ['hyperbolic-geometry', 'survey'], fixed: ['newsfeed'], status: 'open', waits: 4, summary: 'A survey of learning in negatively curved spaces; the parts on hyperbolic attention bear on the thesis.',
    kv: [['Search', 'hyperbolic geometry, every 7 d'], ['Link', 'arxiv.org']], body: '<p>Representation learning in negatively curved spaces: Poincaré and Lorentz models, hyperbolic attention, and where the gains over Euclidean embeddings actually show up.</p>', verbs: ART_VERBS },
  { id: 'a2', module: 'newsfeed', type: 'article', title: 'Hyperbolic attention at scale', snip: 'arXiv', when: '2026-09-20T04:10', tags: ['hyperbolic-geometry'], fixed: ['newsfeed'], status: 'open', waits: 10,
    kv: [['Search', 'hyperbolic geometry, every 7 d'], ['Link', 'arxiv.org']], body: '<p>Attention scores computed from Lorentz inner products; the authors report gains on tree-like graphs and none on flat ones.</p>', verbs: ART_VERBS },
  { id: 'a4', module: 'newsfeed', type: 'article', title: 'Weak instruments, revisited', snip: 'arXiv', when: '2026-09-19T04:15', tags: ['causal', 'thesis'], fixed: ['newsfeed'], status: 'open', waits: 11,
    kv: [['Search', 'causal inference, every 3 d'], ['Link', 'arxiv.org']], body: '<p>New bounds on bias when the first stage is weak, with a diagnostic that needs only the reduced form.</p>', verbs: ART_VERBS },
  { id: 'a5', module: 'newsfeed', type: 'article', title: 'Teichmüller space of a pair of pants', snip: 'arXiv', when: '2026-09-18T04:12', tags: ['hyperbolic-geometry', 'geometry'], fixed: ['newsfeed'], status: 'open', waits: 12,
    kv: [['Search', 'hyperbolic geometry, every 7 d'], ['Link', 'arxiv.org']], body: '<p>An expository note: the three boundary lengths coordinatize the space, and the seams give the hexagon decomposition.</p>', verbs: ART_VERBS },
  { id: 'a3', module: 'newsfeed', type: 'article', title: 'Chronos-2: zero-shot forecasting with covariates', snip: 'arXiv', when: '2026-09-17T04:20', tags: ['time-series', 'forecasting'], fixed: ['newsfeed'], status: 'accepted', dim: true,
    kv: [['Search', 'time series, every 7 d'], ['Link', 'arxiv.org']], body: '<p>A pretrained forecaster that takes exogenous covariates at inference time.</p>', related: ['b7'], verbs: [['link', 'Open link'], ['dismiss', 'Dismiss']] },

  { id: 'c1', module: 'chat', type: 'conversation', title: 'Planning the March trip', when: '2026-09-18T20:12', tags: ['travel', 'march-trip'], fixed: ['chats'],
    turns: [['user', 'Compare flights for the second week of March, two adults, out on a Saturday.'], ['model', 'Three fares under $600 return; the Saturday departure is the cheapest by $80. Your passport lapses in February, so I filed the renewal as a task.']], related: ['b2', 'e3'],
    verbs: [['reopen', 'Reopen'], ['delete', 'Delete']] },
  { id: 'c2', module: 'chat', type: 'conversation', title: 'One page for Otto', when: '2026-09-19T21:30', tags: ['otto', 'ideas'], fixed: ['chats'],
    turns: [['user', 'Every module page is a context switch. What if there were one feed?'], ['model', 'Then a facet is only tools, a schema and a widget, and the page never changes under you. The graph becomes the way in.']],
    verbs: [['reopen', 'Reopen'], ['delete', 'Delete']] },
  { id: 'c3', module: 'chat', type: 'conversation', title: 'Sensitivity bounds write-up', when: '2026-09-16T14:20', tags: ['thesis', 'causal', 'writing'], fixed: ['chats'],
    turns: [['user', 'Draft the lemma on exclusion conditional on the covariate set.'], ['model', 'Drafted under thesis/lemma_exclusion.md, with the proof sketch as a numbered list.']],
    verbs: [['reopen', 'Reopen'], ['delete', 'Delete']] },
  { id: 'c4', module: 'chat', type: 'conversation', title: 'Furnace filter size', when: '2026-09-15T09:10', tags: ['home'], fixed: ['chats'],
    turns: [['user', 'Which filter fits the Carrier unit?'], ['model', '16 × 25 × 1, MERV 11. The last change was 06-14, so the task is due now.']],
    verbs: [['reopen', 'Reopen'], ['delete', 'Delete']] },

  { id: 'r4', module: 'system', type: 'routine', title: 'email.triage', snip: 'nightly', when: '2026-09-20T02:05', tags: ['nightly'], fixed: ['routine'], right: 'failed', late: true, waits: 13, summary: 'Did not run last night: the nightly budget was spent before its turn.',
    kv: [['Interval', 'nightly'], ['Last run', '09-20-2026 02:05'], ['Next run', '09-21-2026 02:00'], ['Last result', 'BudgetExceeded: 3 of 3 nightly runs used before it started']], verbs: [['run', 'Run now'], ['pause', 'Pause']],
    reply: 'It never ran: the nightly budget was spent by the two generators before its turn. Say run to run it now, outside the window, or raise the budget in Settings.' },
  { id: 'r1', module: 'system', type: 'routine', title: 'email.sync', snip: 'every 5 m', when: '2026-09-20T09:40', tags: ['sync'], fixed: ['routine'], right: 'every 5 m',
    kv: [['Interval', '5 m'], ['Last run', '09-20-2026 09:40'], ['Next run', '09:45'], ['Last result', 'ok, 3 new']], verbs: [['run', 'Run now'], ['pause', 'Pause']] },
  { id: 'r6', module: 'system', type: 'routine', title: 'science.due', snip: 'every 5 m', when: '2026-09-20T09:40', tags: ['sync'], fixed: ['routine'], right: 'every 5 m', related: ['s2'],
    kv: [['Interval', '5 m'], ['Last run', '09-20-2026 09:40'], ['Next run', '09:45'], ['Last result', 'nothing due']], verbs: [['run', 'Run now'], ['pause', 'Pause']] },
  { id: 'r5', module: 'system', type: 'routine', title: 'graph.rebuild', snip: 'every 15 m', when: '2026-09-20T09:30', tags: ['sync'], fixed: ['routine'], right: 'every 15 m',
    kv: [['Interval', '15 m'], ['Last run', '09-20-2026 09:30'], ['Next run', '09:45'], ['Last result', '61 tags, 214 edges']], verbs: [['run', 'Run now'], ['pause', 'Pause']] },
  { id: 'r3', module: 'system', type: 'routine', title: 'newsfeed.run', snip: 'nightly', when: '2026-09-20T02:30', tags: ['nightly'], fixed: ['routine'], right: 'nightly',
    kv: [['Interval', 'nightly'], ['Last run', '09-20-2026 02:30'], ['Next run', '09-21-2026 02:00'], ['Last result', '4 entries']], verbs: [['run', 'Run now'], ['pause', 'Pause']] },
  { id: 'r2', module: 'system', type: 'routine', title: 'education.generate', snip: 'nightly', when: '2026-09-20T02:10', tags: ['nightly'], fixed: ['routine'], right: 'nightly',
    kv: [['Interval', 'nightly'], ['Last run', '09-20-2026 02:10'], ['Next run', '09-21-2026 02:00'], ['Last result', '2 questions']], verbs: [['run', 'Run now'], ['pause', 'Pause']] },

  { id: 't1', module: 'database', type: 'table', title: 'finance_entries', right: '1,284 rows', when: '', tags: ['table'], fixed: ['database'], taggable: false,
    cols: [['id', 'INTEGER', 'primary key'], ['kind', 'TEXT', 'not null'], ['name', 'TEXT', 'not null'], ['amount', 'INTEGER', 'cents'], ['cadence', 'TEXT', ''], ['ended', 'TEXT', '']],
    verbs: [['query', 'Query'], ['export', 'Export']] },
  { id: 't2', module: 'database', type: 'table', title: 'app_tags', right: '3,902 rows', when: '', tags: ['table'], fixed: ['database'], taggable: false,
    cols: [['module', 'TEXT', 'not null'], ['item_id', 'TEXT', 'not null'], ['tag', 'TEXT', 'not null']],
    verbs: [['query', 'Query'], ['export', 'Export']] },
  { id: 't3', module: 'database', type: 'query', title: 'unread by sender', snip: 'saved', when: '2026-09-18T16:40', tags: ['query', 'queries'], fixed: ['database'],
    sql: 'SELECT sender, COUNT(*) AS n\nFROM email_messages\nWHERE unread = 1\nGROUP BY sender\nORDER BY n DESC;',
    verbs: [['load', 'Load'], ['delete', 'Delete']] },
];

// The drawer's open conversations: one agent, one tab each.
export const SESSIONS = [
  { id: 'quiz', label: 'Quiz', turns: [
    { role: 'user', text: '(a) Write f(z) = e^{iθ}(z − a)/(1 − āz). Differentiating and using |e^{iθ}| = 1 gives |f′(z)| = (1 − |a|²) / |1 − āz|².' },
    { role: 'tool', tool: 'education_grade', status: 'done' },
    { role: 'model', hue: '#86AAE3', blocks: [{ kind: 'grade', score: '82 / 100', text: 'The derivative is right, and so is the modulus. What the rubric wanted as well is the identity 1 − |f(z)|² = (1 − |a|²)(1 − |z|²) / |1 − āz|², since (b) rests on it.' }], text: 'Resubmit (a) with the identity, or go on: (b) is the token below.' },
    { role: 'tool', tool: 'note_add', status: 'note filed' },
  ] },
  { id: 'tuition', label: 'Tuition', turns: [
    { role: 'user', text: 'What is due before the 15th?' },
    { role: 'tool', tool: 'finance_totals', status: 'done' },
    { role: 'model', hue: '#8CC79E', text: 'Rent on 09-25 ($2,145), tuition on 10-01 ($2,140) and Claude Max on 10-04 ($200). Checking holds $2,552, so tuition overdraws it by $1,733 unless something moves.' },
    { role: 'tool', tool: 'finance_entry_add', status: 'Tuition' },
    { role: 'model', hue: '#8CC79E', text: 'I filed Tuition as an entry due 10-01 and put the shortfall at the top of Priority as a decision.' },
  ] },
];
