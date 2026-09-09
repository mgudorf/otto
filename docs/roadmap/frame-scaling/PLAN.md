# Frame Scaling Plan

Status: planning, 2026-09-09.

Keeps the middle of every page the biggest thing on screen when the window is maximized on the
3440-wide monitor. Today the two side panels swallow the extra width while the middle's content
stops growing at 720px, so maximizing makes the part the owner actually works in look smaller, not
larger; without this the ultrawide is only usable windowed.

## Sources

| Source | Governs |
|---|---|
| `docs/ARCHITECTURE.md` "UI / Frame contract" | the three tracks, rail 56px, header 48px, track padding `19px 24px 24px`, gap 24px, the LEFT/MIDDLE/RIGHT paddings |
| `docs/ARCHITECTURE.md` "Config", "Daemon / Mechanisms" | `[ui]` seeds live settings on first start; the Settings page edits them afterwards |
| `docs/design/Personal Dashboard App.dc.html` line 44 | the `minmax(220px,4fr) minmax(300px,9fr) minmax(220px,4fr)` track definition, copied verbatim into the shell |
| `app/static/shell.js:135` | the grid this changes; `shell.js:157` is the Inspector's `maxWidth:'72ch'` |
| `app/static/pages/*.js` | the seven MIDDLE content caps (640, 720 x5, 960) that stop growing |
| `app/config.py:98` `Ui`, `config.toml [ui]`, `app/daemon.py:59-62`, `app/api.py:151` `UI_KEYS` | where the two new knobs land |
| Measurement on this machine, 2026-09-09, headless Chrome 152 against the live daemon | every number below |

Measured today on the live app; `dpr` 1, no display scaling (3440x1440 primary, working area 3440x1392):

| Viewport | LEFT | MIDDLE track | MIDDLE content | content fills track |
|---|---|---|---|---|
| 1584 (windowed) | 337 | 758 | 720 email / 640 home | 95% / 84% |
| 3424 (maximized) | 770 | 1732 | 720 / 640 | **42% / 37%** |

The tracks themselves behave correctly and stay proportional. The side panels grow 2.3x while the
middle's content is capped in fixed pixels and does not grow at all. That gap is the whole defect.

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | Side tracks become `clamp(220px, 22.8%, <ui.side_max>px)`; MIDDLE becomes `minmax(300px, 1fr)` and absorbs everything left over | 22.8% reproduces the artboard's 4/17 share to the pixel at windowed width (measured 337.4px against today's 337.4px), so windowed is unchanged and only the surplus is redirected |
| 2 | A ceiling on the sides, not on the whole frame | Capping the frame and centring it would leave ~700px of dead ground on each side of a monitor bought for width; the owner asked for a bigger middle, not an emptier screen |
| 3 | The MIDDLE content cap becomes `min(100%, <ui.middle_max>px)`, centred in the track | One rule replaces the seven per-page pixel caps; at windowed it resolves to the full track (725px against 720 today) and at maximized to 1400px centred, so the content never floats as a small blob against the left edge of a 2432px track |
| 4 | Prose keeps a reading measure: the Inspector (`shell.js:157`) and Activity's detail (`activity.js:60`) stay at `72ch`, centred | A 1400px line of body text reads worse, not better; the complaint is about the module's working area, not its prose |
| 5 | `ui.side_max` = 420 and `ui.middle_max` = 1400 are live settings, seeded from `[ui]`, edited on Settings > General | Same pattern as `ui.page_size`; the owner tunes the ceilings against the real monitor without restarting the daemon, and no ceiling is hard-coded. Both defaults confirmed by the owner 2026-09-09 |
| 9 | The two `auto-fit` stat strips bound themselves: `home.js` keeps 640 and centres, `finance.js` gets 720 on the strip only | Found by looking at the built page: `repeat(auto-fit, minmax(140px,1fr))` given 1400px spreads home's nine numbers into eight across plus an orphan, which reads worse than the compact block. A strip of numbers has a natural width; a list or table does not. Finance's strip stays left-aligned so it lines up with the tables under it, which do take the full 1400 |
| 8 | One ceiling for both sides, not one per side, and the middle's content centred rather than left-aligned | The owner asked for symmetry: LEFT and RIGHT stay identical at every width, and the ground left over in the middle track is split evenly (500px each side at maximized) instead of pooling on the right |
| 6 | The 22.8% stays in code, not a knob | It is the artboard's 4:9:4 ratio restated as a percentage, i.e. the design contract; making it adjustable would let the frame drift off the artboard |
| 7 | Pure CSS, no resize listener and no `matchMedia` | `clamp()` re-resolves on every window resize for free; the frontend has no viewport JS today and this adds none |

Rejected: a max-width wrapper on the whole frame (decision 2); a `@media` breakpoint switching the
template (needs a stylesheet rule to beat the inline styles, and steps rather than following the
window continuously); `minmax(220px, 420px)` on the sides (fr tracks only receive leftover space, so
the sides would jump straight to 420px and *shrink* the middle to 592px at windowed width, breaking
the one size the owner says is right); editing the per-page caps without changing the frame (leaves
the side panels ballooning).

Measured with the proposal injected into the live page, all three widths, no horizontal overflow:

| Viewport | LEFT / RIGHT | MIDDLE track | MIDDLE content | vs today |
|---|---|---|---|---|
| 1584 (windowed) | 337 | 757 | 725 | unchanged (337 / 758 / 720) |
| 1930 (clamp knee) | 416 | 945 | 913 | +1.3x content |
| 3424 (maximized) | 420 | 2432 | 1400 | **+1.9x content**, sides no longer grow |

## Layout

| File | Change |
|---|---|
| `config.toml` | `[ui]` gains `side_max = 420` and `middle_max = 1400`, each with a one-line comment |
| `app/config.py` | the `Ui` dataclass gains `side_max: int` and `middle_max: int` |
| `app/daemon.py` | two more lines in the settings seed block at lines 59-62 |
| `app/api.py` | `UI_KEYS` gains both keys as `int`, with range checks `280 <= side_max <= 900` and `640 <= middle_max <= 3000` |
| `app/static/shell.js` | the grid template is built from the two settings; the MIDDLE wrapper applies the cap and centring; the Inspector keeps `72ch` and gains `margin: 0 auto` |
| `app/static/pages/*.js` | remove the eight fixed `maxWidth` values (640, 720 x6 including `web_search`, 960) now that the frame owns the cap; `activity.js:60` keeps its `72ch` and centres; the two stat strips keep a ceiling of their own (decision 9) |
| `app/static/pages/settings.js` | two `num()` rows in the General section |
| `docs/ARCHITECTURE.md` | the Frame contract Tracks row restated; Config gains the two keys |
| `tests/test_app.py` | settings validation cases |

## Contract

Not a module: no manifest, no schedule, no routes, no MCP tools, no agent, no rail entry, no hue and
no icon. The shell contract changes in exactly one place, the Tracks row of the Frame contract:

    Tracks | clamp(220px, 22.8%, ui.side_max) minmax(300px,1fr) clamp(220px, 22.8%, ui.side_max),
             gap 0 24px, padding 19px 24px 24px; MIDDLE content min(100%, ui.middle_max), centred

Everything else in the Frame contract is untouched: rail 56px, header 48px, the 1px loading line,
every token, the 120ms page-switch fade, and the LEFT/MIDDLE/RIGHT paddings and panel surfaces. The
shell reads the two values out of `s.shell.settings` exactly as it already reads `ui.time_format`,
with the same `|| default` fallback so a shell fetched before the seed still renders.

Departures from the artboard: the artboard fixes the tracks at `4fr / 9fr / 4fr` with no ceiling and
no canvas width, so it specifies nothing above roughly 1950px. The ultrawide case is unspecified
there rather than contradicted. This plan holds the artboard's ratio exactly up to the knee and
departs only past it, where the artboard is silent. The seven per-page pixel caps being removed are
not artboard values either; they do not appear in `Personal Dashboard App.dc.html`.

## Data

No `schema.sql` change, no cursors, no external clients and no scheduled work. Nothing here reads or
writes module data, so the read-only versus write client split does not apply. The two knobs are
rows in the existing platform `settings` table, seeded at boot by `app/daemon.py` and written only
by the existing `PUT /api/settings` user action.

## Phases

| Phase | Builds | Usable result |
|---|---|---|
| 1 | The frame change with both ceilings as `[ui]` boot values: `config.toml`, `Ui`, the daemon seed, the `shell.js` grid and MIDDLE cap, and removal of the seven per-page caps | Maximizing on the ultrawide gives a 1400px middle instead of 720px, on every page, at the owner's next `python -m app` |
| 2 | Live editing: the `UI_KEYS` validation and the two Settings > General rows | The owner tunes the ceilings against the real monitor and watches the frame reflow without restarting the daemon |

Phase 1 is the fix and stands alone; phase 2 only makes it adjustable in place.

## Tests

- `PUT /api/settings` accepts `ui.side_max` and `ui.middle_max` and rejects out-of-range values with 400, alongside the existing `ui.page_size` case at `tests/test_app.py:78`.
- `/api/shell` reports both keys with their seeded defaults, so the shell always has a value to render.
- `app/config.py` fails at boot when either key is missing from `[ui]`, matching the existing every-key-required rule.
- No LLM touchpoint, so nothing to mock; the suite stays offline.
- The layout itself is confirmed by eye in the real window at both sizes, per the recorded smoke-test procedure, not by a unit test.

## Manifest

Present:

| Item | Version / location | Needed for |
|---|---|---|
| Google Chrome | 152.0.7977.83, `C:\Program Files\Google\Chrome\Application\chrome.exe` | renders the frame; resolved `clamp()` and `min()` in today's probe |
| Python | 3.14.7, `.venv/Scripts/python.exe` | daemon and tests |
| pytest | 9.1.1 | the suite |
| Primary monitor | 3440x1440, working area 3440x1392, no display scaling (`dpr` 1) | the widths every number above is measured at |
| `app/static/shell.js`, `app/static/pages/*.js` | present | the files changed |

Missing: none. This item adds no package, binary, credential, external API or scope.

Needs you: nothing. Both defaults are settled.

| Check | Command |
|---|---|
| Both knobs present after boot | `curl -s http://127.0.0.1:8765/api/settings` shows `ui.side_max` and `ui.middle_max` |
| Suite green | `.venv/Scripts/python.exe -m pytest -q` |
| Frame at both sizes | run the app, maximize on the 3440 monitor, then restore; MIDDLE content 1400 then ~725 |

## Worktree

    git worktree add ../otto-frame-scaling -b frame-scaling

Work there. Merge `main` into the branch before merging back, keep the `[ui]` keys and the `UI_KEYS`
entries in the order written here, then run `/sync-architecture` on `main`.

## Pending decisions

None. Both ceilings were settled by the owner on 2026-09-09: `ui.side_max` 420 and
`ui.middle_max` 1400, one knob for both sides, middle content centred, on a 3440x1440 primary.

At maximized the frame reads 420 | 500 | 1400 | 500 | 420, symmetric about the middle.

Confirmed in the built app on 2026-09-09, a worktree instance on port 8766 rendered at 3440x1392 and
1600x1000: tracks 420 / 2432 / 420, middle content 1400 centred when maximized and 725 when
windowed, matching the plan's arithmetic exactly. Looking at it is what turned up decision 9.
