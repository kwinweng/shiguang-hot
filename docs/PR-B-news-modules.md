# PR B: live news and daily reviews

PR B supersedes the earlier r3 homepage/navigation behavior described in
`SPEC-news-navigation-history-r1.md` and `NEWS-HISTORY-IMPLEMENTATION.md`.
The homepage is now the Telegram live feed. Its top source entry opens a source
list and individual source view. History uses a full-page month calendar and day
review. The old chronological archive HTML and sidecars remain compatible.
`today.html` contains today's journal items, without the old news area or calendar.

## Data and privacy

`data/live.json` contains newest-first Telegram messages and Beijing hourly groups.
Each record includes source identity/name, time, original link, image, category and
an extractive summary. Exact duplicates share both original link and the first 50
body characters. `data/sources.json` contains public sources, their type, today's
count, seven-calendar-day count including today, latest message time and status.
`SOURCE_STALE_HOURS` defaults to 24; only an age strictly greater than the threshold
is stale. Sources with no records are stale. These counts use publication time,
not collector insertion time. Future records do not contribute to source counts.

`history/YYYY-MM-DD.json` contains a summary of at most 60 characters, up to ten
events, category, distinct source count, original links, day statistics and a raw
message snapshot. The categories are 全球 / 财经 / 科技AI / 社会 / 其他. Both live
and day views expose six category buttons, including 全部. Clicking a message or
event opens its summary before the original-link action. Event raw messages expand
in place through native `details` controls.

The mock provider groups identical headlines and extracts source text. It does
not claim semantic clustering or AI inference. Days with sufficient distinct input
have 5–10 events; sparse days retain fewer rather than fabricate events. Days
without input get no file or enabled calendar date. Beijing midnight inclusive to
the next midnight exclusive defines each day. Only completed days are summarized.
All summary output is clearly marked MOCK. **真实 AI 总结未验证，等新 key**.

`FlashProvider` is an unimplemented future integration stub. It reads only
`FLASH_API_KEY` from the process environment when explicitly instantiated and its
summary method raises `NotImplementedError`. Neither build nor CLI instantiates
it. No `.env` loading, network operation or paid API is involved in summaries.

Private sources are filtered before serialization, even in private builds of the
new news modules. The existing atomic publication and public-tree checks still
guard the complete site. Existing private journal routes remain private-only.

## Offline preview and backfill

```sh
NO_FETCH=1 SITE_MODE=public python3 pipeline.py
# Force synthetic fixture data even when tg.db exists:
NO_FETCH=1 SAMPLE_DATA=1 SITE_MODE=public python3 pipeline.py
python3 tools/daily_summary.py --backfill-from 2026-10-16
# Isolated synthetic backfill:
python3 tools/daily_summary.py --sample --backfill-from 2026-10-16 --output /tmp/news-history-preview
```

With `NO_FETCH=1`, a missing database selects the synthetic fixture automatically;
otherwise the database is read without fetching. Sample headlines are explicitly
prefixed `[示例]`. Fixture days are relative to build time and contain no real news
claims. The CLI forces public, offline operation. It writes raw snapshots and
summaries to root `history/` by default. Site builds consume those files and retain
completed authorized snapshots in `site/history/`. Explicit CLI reruns replace root
day files, and those files take precedence on the next site build. Retention has
no rolling cutoff; keep root `history/` in the existing local backup process.

Run the summary CLI at **00:30 Beijing** to generate yesterday's review. For a
host whose cron timezone is UTC this is 16:30 UTC on the preceding date. This PR
documents the schedule; it does not install cron jobs or change deployment or
collection workflows. Backfill emits only dates with retained authorized inputs.

## Visual provenance

Checked modification times on 2026-10-23. The latest `two-modules/two.js` was
modified at 17:46, later than the `deploy/` prototype files. Production assets reuse
`two-modules/tokens.css`, `two.css` and Phosphor 2.1.1 `icons.js`, with production
viewport and accessibility adaptations in `web/news.css`. The design contract is
`/workspace/proto-bot/rebang-visual/deploy/DESIGN.md`: 灵记 v0.2, white surfaces,
thin dividers, no card containers, red interactions and regular/fill icons.
The prototype phone frame, sample stories and unrelated tabs are not published.

## Verification

```sh
python3 -m unittest discover tests
node --test tests/*.test.js
node --check web/news.js
```

New tests cover timezone boundaries, exact dedupe, category filtering, source
counts/staleness, deterministic summaries, no-network builds, retained snapshots,
calendar availability and safe text/original links. Optional Playwright tests use
locally routed static files; no external site is contacted.

Verified in this checkout: 153 Python tests passed, including offline Chromium
tests; eight Node tests passed; `node --check web/news.js` and `git diff --check`
passed. Both the existing-data offline public build and forced sample public
build succeeded. The sample build contains 48 messages and seven completed days.
The sample backfill from 2026-10-16 emitted seven documents into
`/tmp/prb-history-preview`. The host provides `python3`, without a `python` alias.

Local commit could not be created: `git add` failed with
`fatal: Unable to create '/workspace/rebang-work/base/.git/worktrees/features/index.lock': Read-only file system`.
The environment permits no approval escalation. Changes remain in the working
tree; no push, deployment, network collection or paid API call was performed.
