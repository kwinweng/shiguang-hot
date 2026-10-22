# News navigation/history r3 implementation record

Implementation starts from `b7267d2fb4e2e4c2409fa42f91e12264cec91510` on `codex/news-navigation-history-impl`.
The user's implementation instruction supplies authorization beyond the Spec's earlier document-only phase.
The Spec itself remains unchanged.

## Files changed

| Files | Purpose |
| --- | --- |
| `shiguang/site/history.py` | Stable bookmark UIDs, qualified publication times, date precision, chronological order, fixed public boundary, day JSON, joint date manifest, compatible archive reuse, and news markup. |
| `shiguang/site/pages.py` | Uncapped Today/archive news; Today-only column summaries; news entry through the existing navigation slot; scoped media copying. |
| `shiguang/site/build.py` | Publish the content-hashed history script; preserve old shared assets; validate disallowed configured sources. Atomic staging and public validation remain in place. |
| `shiguang/site/render.py` | Load the optional news controller, follow system theme, and render local Phosphor navigation glyphs. |
| `shiguang/site/phosphor.json`, `LICENSES/phosphor-icons.txt` | Vendored Phosphor regular glyphs and filled bookmark, with MIT license; no runtime package dependency. |
| `web/history.js` | Day requests, exact joint filtering, loaded-date search, UID deduplication, local same-source folding, native continuation, calendar, capsule, request generations, URL/history/reading restoration, and failed-image layout. |
| `web/style.css` | Scoped gray/green news tokens, system typography, icon controls, left thumbnails, and light/dark/reduced-motion capsule states. |
| `tests/test_news_history.py`, `tests/test_news_browser.py`, `tests/news_history.test.js` | Offline backend, Chromium, and Node acceptance tests. |
| `tests/test_feeds.py`, `tests/test_render.py` | Update old cap/hero/asset-cleanup/navigation expectations for the explicit r3 replacements. |
| `tools/benchmark_news_history.py` | Synthetic 30/365-day, three-run comparison with separate copy/index/render/validation costs. Never reads a database. |
| `docs/NEWS-HISTORY-IMPLEMENTATION.md` | This acceptance and validation record. |

## Acceptance evidence

| Criterion | Implementation and evidence |
| --- | --- |
| A1 — chronology, precision, count, identity | Aware original timestamps normalize to Asia/Shanghai; unqualified timestamps retain date precision rather than acquiring a fabricated timezone. Date-only records follow exact times within their day. Ties use source order, descending numeric native ID, and stable UID. No `rank_home`, hero promotion, global cap, or global expansion gate remains in the news path. Tests cover 25 same-time stories, cross-midnight UTC, date-only and missing-timezone records, old journal dates, duplicate UIDs, and equality with existing bookmark hashes. |
| A2 — day continuation | Initial entry requests the selected day only. Scrolling into the sentinel loads the next older jointly matching day even when a same-source group remains collapsed. Calendar/capsule jumps request the target directly. Tests record request order, cache hits, a year-old direct jump, retry after HTTP 503, preserved cards on failure, and earliest-archive feedback. Missing base days and present-but-unmatched days have separate messages. |
| A3 — joint filtering/search/races | The manifest contains actual `(canonical source, alias, topic)` tuples. Calendar and capsule share the same predicate as day records, including technology subtopics and international aliases. Late responses return no rows after generation invalidation. Search touches loaded records only; new days join that search. Tests cover false independent-count intersections, source aliases, blocked/absent-source emptiness, future dates, loaded-only search followed by continuation, and stale-response exclusion. Collector status is never serialized. |
| A4 — capsule C | Hidden at rest; user scrolling reveals it; a controlled clock checks visibility at 999 ms and fade start after 1000 ms. Hover/focus/drag prevent timeout dismissal. Mouse capture, release/cancel, Esc, arrows, Home/End, and Enter separate preview from committed reading date. Tests check keyboard and pointer cancellation, 44 px hit width, 6 px resting glyph, dark `rgba(180,216,179,.55)`, and no horizontal overflow at 320/393/1280 px. CSS supplies 10×56 px held state, 12/17 px labels, 11 px hint, 150 ms fade, bottom-safe placement and reduced-motion handling. Physical-device and complete visual/accessibility sign-off remain outstanding; see limits below. |
| A5 — retained text/images | Existing retained inputs produce day files without a rolling text/history cutoff. Tests retain 30/365-day samples, original links and bookmark buttons with expired images, and verify no network retrieval during archive generation. The browser removes failed media without removing the article. Earliest date comes from retained authorized archive days. Existing image expiration/collection configuration is untouched. |
| A6a — incremental rendering | Input fingerprints, schema/template/source/scope/shared-asset compatibility, and day-data hashes control reuse. Same-version addition renders only the added archive day; old HTML/data hashes remain equal. Corrections and deletion rebuild their original day. Today and mutable entry points remain separately writable. Tests exercise these cases and 30/365-day baselines. Incompatible or absent baselines regenerate sidecars in code; this has only run on synthetic temporary fixtures. |
| A6b — total cost | The standalone benchmark reports full baseline render/index, staging copy, incremental index/day data, archive render, validation, total and bytes. Three runs use medians. Transfer and production capacity are deliberately unmeasured; no total O(1) or performance-budget claim is made. |
| A7 — public boundary | Public Content admits exactly the existing 13 canonical IDs plus four column IDs. Filtering happens before rendering/serialization. Unknown/private rows cannot create public cards or dates. The copied media tree admits visible Telegram channels only. Scope/source-contract changes cannot carry private-only dates into a public manifest. Tests cover unknown rows/dates, stale private media, private-to-public baseline reuse, structured private-marker rejection, and absent collector-state fields. Existing public-tree scans still run before atomic publication. |
| A8 — compatibility and scope | Existing `index.html`, `archive/<day>.html`, source, journal, favorite IDs and `hot.html` remain. `#screens/look` opens news and `#screens/focus` reaches the retained hotspot page. Explicit changes push history; reading updates replace it; snapshots preserve loaded days, anchor and offset for navigation and return. Browser tests cover back/forward and missing-sidecar fallback. Old hashed CSS/JS are retained. Hotspot candidate/merge/score/member-count/window/day/hour code is unchanged; existing three-day timeline tests pass. Summaries remain on Today and are hidden in the news view; archive pages contain none. No date/scroll library was added. |

## Checks

Run from the repository root. All listed final checks returned exit code 0.

| Command | Result |
| --- | --- |
| `GIT_CONFIG_GLOBAL=/dev/null python3 -m unittest discover tests` | 132 passed, including seven offline Chromium tests; no skips in this environment. |
| `node --test tests/news_history.test.js` | 5 passed. |
| `node --check web/app.js` | Passed. |
| `node --check web/history.js` | Passed. |
| `python3 tools/benchmark_news_history.py` | Passed 30/365-day comparisons, three runs each; every unchanged archive hash matched. |
| `git diff --check` | Passed. |

The Python suite's Git-persistence tests use throwaway repositories and a local bare fixture remote.
`GIT_CONFIG_GLOBAL=/dev/null` isolates those fixtures from the host's global hooks; fixture-local rejection hooks still execute.
No project branch was pushed. Fixtures may create their own synthetic file named `tg.db`; the repository database is untouched.
There is no package manifest, web bundler, web lint command, Python lint configuration, or separate web build command in this checkout.
The suite exercises complete offline static builds as well as the new day-data path.
Chromium uses optional Playwright and `/opt/ungoogled-chromium/chrome`; another machine can set `NEWS_TEST_CHROME`.

### Offline benchmark

Three-run medians; one synthetic article per historical day, no images. These measurements are not representative production capacity estimates.

| Measurement | 30 days | 365 days |
| --- | ---: | ---: |
| Full baseline render + index, seconds | 0.01030 | 0.11804 |
| Copy, seconds | 0.00305 | 0.04176 |
| Incremental index + day data, seconds | 0.00330 | 0.02885 |
| Archive rendering, seconds | 0.00052 | 0.00067 |
| Public validation, seconds | 0.10383 | 1.05010 |
| Incremental total, seconds | 0.11124 | 1.11595 |
| Added archive days rendered | 1 | 1 |
| Unchanged archive days rendered | 0 | 0 |
| Complete staged artifact bytes | 922109 | 9536195 |

The harness excludes deployment transfer and does not benchmark every mutable source/issue page.
Validation, copying, and index serialization still scale with retained history.

## Limits, deviations, and rollback

- **Commit unfinished:** `git add` failed with `fatal: Unable to create '/workspace/codex-runs/hot-impl14-1501/.git/index.lock': Read-only file system`. The environment exposes `.git` read-only and provides no approval escalation. Changes remain in the working tree on the requested branch; no commit or alternate history was created.
- This checkout contains the earlier Today/Hot/Columns implementation, not the r1 prototype described by the Spec. The existing Hot slot now reaches the news surface inside `index.html`; its two views retain `hot.html` as the hotspot endpoint. No extra navigation slot or page is introduced. The referenced r1 representative/member query UI is absent from the supplied baseline; its behavior cannot be claimed as verified. The actual hotspot computation and output grouping were preserved rather than inventing changed hotspot behavior.
- Browser automation supplies desktop Chromium evidence, simulated pointer/keyboard input, narrow viewports and controlled time. Physical touch-device evidence, exhaustive zoom/screen-reader review, and formal visual/contrast approval are not completed. No screenshots are presented as physical-device evidence.
- Production history inventory, actual earliest retained production day, platform limits/headroom, transfer timings and operator time/capacity budgets remain unmeasured. No lost history recovery or infinite storage claim is made.
- No real-data first-build migration/backfill, collector run, production build, push, merge or deployment occurred. No workflow, deploy setup, secret, `.env`, credentials, source configuration or repository `tg.db` was modified.
- Pre-integration code and assets remain recoverable at baseline SHA `b7267d2fb4e2e4c2409fa42f91e12264cec91510`. No live deployed HTML snapshot was available or taken. Formal integration should retain that actual deployed snapshot before release, as §6.3 requires. Restore baseline code and its matching HTML/assets together under the existing release approval process. New sidecars can then be discarded without changing standalone HTML. Offline tests remove the manifest/day directory and confirm retained article text, date precision and bookmark buttons remain readable. No rollback or release was performed.
