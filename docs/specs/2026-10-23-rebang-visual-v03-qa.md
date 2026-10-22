# 热榜视觉系统 v0.3 — local implementation and acceptance

Implemented on `feat/rebang-visual-v03`. No branch changes, pushes, merges, or deployments.

## Changes

- Imported the approved `tokens.json` and generated `tokens.css` unchanged. Removed the old style variables, ambient page backgrounds, dimmed news images, and decorative lead markup.
- Added one plain-JavaScript renderer for today, news/quick/hot, play, buy, favorites, daily briefs, details, search, columns/tags, sources, history, onboarding, calendar, drawer, lightbox, refresh, toast, offline, and install surfaces.
- Preserved the publication source boundary and existing bookmark IDs. Presentation data comes from existing public/private publication pools and trial catalogues. Source acquisition and feed adapters remain unchanged.
- Added responsive desktop navigation, four-column cards, a 340px right rail, and scoped offline application caching.
- Applied approved Q1–Q4: exact bottom clearance, solid backing, regular selected category labels, original image brightness, design groups including 北京.

## Verification

Commands run locally:

```text
python3 -m pytest tests -q --tb=short
166 passed, 42 subtests passed

node tests/*.test.js
5 passed (Node treats subsequent filenames as arguments)

node --test tests/*.test.js
7 passed, 0 failed

NO_FETCH=1 python3 pipeline.py build
built site -> /workspace/sh-v03/site

python3 tools/qa_v03.py
light: 48 screens passed
dark: 48 screens passed
96 screenshots: /workspace/shiguang-rebang/v03-shots
```

Browser plugin was unavailable; existing Playwright and local Chromium were used. Mobile captures are 402×874 CSS pixels at DPR 3; desktop captures are 1440×900. The script checks token values, horizontal overflow, image decoding, JavaScript errors, and bottom clearance on scrolling content. Interaction tests cover joint filters, search states, six pages' loading/empty/error states, five detail variants, bookmark removal/undo, calendar selection, focus containment/restoration, dark image brightness, refresh retry, toast expiry, and cache scope rejection.

A separate production-data smoke check verified three today sections, five news rows, bookmark persistence, and a service-worker offline reload without JavaScript errors. Production publication contains 2,310 news entries, 130 news images, 255 trial cards, 24 daily briefs, and nine market cells for the current local dataset.

Git persistence tests now isolate hooks inside their temporary repositories. The host's pre-push hook otherwise rejects their local fixture remotes. The work repository's hooks and configuration were not changed. Commits use the command-local identity `Codex <codex@local.invalid>` because this checkout had no author configured.

## Evidence and limitations

- Screenshots use the approved local prototype content and images as deterministic fixtures, rendered by production components. Fixtures are not published with production data.
- Headless Chromium reports zero safe-area insets. The screenshot transport substitutes only the two CSS `env()` inputs with 59pt top and 34pt bottom. Source CSS retains the exact approved formula; mobile screenshot clearance is 136pt. Browser interaction tests additionally exercise the native zero-inset case.
- Hot mini charts show actual source mentions over 72 hours. Missing upstream GitHub star/language fields remain explicit placeholders; no new collection or invented values were added.
- Native Safari/Chrome installation UI was not exercised on physical devices. The install guidance and browser prompt integration are implemented.
- Design-bot visual sign-off remains external and pending. Local checks do not claim that sign-off.

Screenshot filenames follow `<screen-id>-<light|dark>.png`. The list in `tools/qa_v03.py` matches all 48 spec IDs.
