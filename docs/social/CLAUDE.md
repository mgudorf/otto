# Social

1. Finds exciting social events and activities in and around Woodstock, Roswell, Canton, Alpharetta and Marietta, Georgia
2. Covers workshops, networking, making new friends, small business and startup events, live events, art/food/music, game nights, local events, animals, movies, and entertainment generally
3. Does not centre on drinking alcohol

## Built

| Piece | Current state |
|---|---|
| Table | `social_items(kind interest\|event, text, ref, why, category, city, venue, starts_at, status open\|going\|dismissed)`, unique on `(kind, ref, starts_at)` so one venue's recurring night keeps every date; an event must carry a `category` and a `starts_at`. `starts_at` is a naive local `YYYY-MM-DDTHH:MM`, so SQLite's `date()` and the browser's `new Date()` both read it as the local day; `T00:00` means the listing gave no time and renders as `all day` |
| Categories | `class` workshops and hands-on sessions, `meet` meetups and mixers, `biz` small business and startups, `music`, `art` (art, craft, maker, theatre), `food`, `game` (game nights, trivia), `animal`, `film`, `local` (festivals, fairs, community days). Six characters at most: the shared `Row` gives the leading slot 40px |
| Routes | `left` (query as `LIKE` per word over text, ref, venue, city and category; one chip per slice, each with its own order), `blank` (the configured towns, per-category counts, the going and interest totals, and the open events), `item/{id}`, `action/{capture\|forget\|going\|dismiss}`: `capture` records an interest, `forget` refuses an event (dismiss it), `going` and `dismiss` refuse an interest |
| Hooks | `numbers` (upcoming events still open), `today` (events happening today plus anything recorded today), `queue` (every upcoming open event, soonest first, so Home's Review group keeps it however old it is), `item`, `context` (interests verbatim, what is going, what awaits a decision, last scout) |
| Tools | read: `social_search`, `social_get`, `social_upcoming`; write: `social_interest`, `social_event` |
| Schedules | `social.scout` every 24h inside the nightly window. It runs with no interests recorded — the towns, the radius and the categories are enough — and interests only steer it. It lists the last hundred events so a url on a date is never proposed twice, names the towns and the `radius_miles`, bounds the search to `horizon_days`, and spells out that bar crawls, brewery tours, tastings and happy hours are skipped while a venue that merely serves alcohol is fine. It expects a JSON array of `{text, url, category, city, venue, date, time, why}`, drops anything without a known category or a date inside the horizon, and queues up to `events_per_run`. Cursor `social.scout` |
| Config | `[social]`: `cities`, `radius_miles`, `horizon_days`, `events_per_run` |
| Page | LEFT: search, the four chips, events grouped by the day they happen (`Sat 19 Sep`) with the category in the leading slot and the start time as the stamp; MIDDLE blank: the towns, the interest box, per-category counts that set the search, and the events waiting on a yes or no with `Going` / `Dismiss` on each; MIDDLE selected: date, venue and town, the reason, the url, category and status, and `Going` / `Dismiss` / `Open` |
| Departures | No artboard exists for this page; LEFT and MIDDLE follow Business's shape. The chips are slices rather than kinds, and there is no `All`: the shell resets every page's chip to `All` on navigation, and an unknown chip falls back to `Upcoming`, which is the useful landing slice. `Upcoming` carries dismissed events too, struck through, so every row is reachable from some chip. Group headers carry the weekday, which the other pages' `%d %b` does not, because the day of the week is what decides whether an event is worth going to |

## Patches

None open.
