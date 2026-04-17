# Critical Errors Review — feat/cta-faq-analytics

Scope: GA4 CTA tracker (inline in index.html + injected into 50 sibling pages via Python), FAQ show-more, CSS for `.btn--whatsapp` / `.faq__more`, hero CTAs.

## Summary

**OK with one real gap and several medium/nit issues.**

No crashing bugs, no syntax errors, no regressions of the existing FAQ accordion or smooth-scroll. The delegated GA4 click listener is implemented correctly and does not block or intercept existing Telegram/WhatsApp link navigation. The Python injector is idempotent.

The one substantive gap is that **`privacy.html` has no GA4 snippet and therefore will be silently skipped by the injector** — any CTA click there will not be tracked. This may be intentional (privacy page has no CTAs that matter) but should be confirmed.

---

## Critical issues

None. Nothing in the diff will break existing functionality.

Specifically verified:
- Delegated `document.addEventListener('click', ..., true)` uses capture phase but **does not call `preventDefault()` or `stopPropagation()`** — native `<a target="_blank">` navigation continues to work as before. Other registered listeners (FAQ accordion, smooth-scroll, burger menu, nav scroll) operate on different selectors and are unaffected.
- `typeof gtag !== 'function'` guard is evaluated **at IIFE execution time**. Because `gtag` is declared synchronously on line 42 (`function gtag(){dataLayer.push(arguments);}`) before the inline GTM script loads, it IS a function by the time the IIFE at line 3206 runs. The guard therefore protects against the case where the GA `<script>` block was stripped (e.g., ad-blocker removing line 42 contents), not a normal network failure. Events buffered via `dataLayer.push` will flush when gtag.js arrives; no events will be lost on slow networks.
- FAQ accordion (line 3132) binds listeners via `forEach` on `.faq-item__question`. It attaches during initial script execution at end of `<body>` — all FAQ items, including `.hidden-faq` ones, exist in the DOM at that point. When show-more reveals hidden items, they already have working handlers. **No regression.**
- The injected script in 50 files is placed just before `</body>`, AFTER all markup, so same timing guarantee applies there.
- Script is inline at end of body (no `DOMContentLoaded` wrapper), which is fine — all parsed DOM above it exists before `<script>` executes. No race with clicks: the script is synchronous and blocks parsing, so the browser won't render anything interactive until it finishes.

---

## Medium issues

### M1. `privacy.html` has no GA4 tag → tracker is skipped there
`scripts/inject_cta_tracking.py` correctly no-ops when `G-CZV65B06MV` is absent. Grep confirms: privacy.html lacks the marker (all other 50 files have it). It does contain `t.me/juli_x11` / `wa.me` links. If privacy page clicks should be tracked, the GA snippet needs to be added there first. If clicks on privacy are explicitly out of scope, this is acceptable — document the decision.

### M2. Nav-header mapping uses a broad `nav` selector
`LOCATIONS` includes `['nav', 'nav_header']`. `a.closest('nav')` matches any `<nav>` ancestor. In the 51 HTML files, if any page has a secondary `<nav>` (e.g., breadcrumbs, pagination in `news/`), its CTA clicks would be labeled `nav_header`. Not broken, but label fidelity could drift. Recommend `.nav` (the class used in index.html line 1923) for stricter matching across all pages.

### M3. `LOCATIONS` iteration order = label precedence
The first matching selector wins. For example, a link inside `.hero` that is *also* inside `nav` (unlikely but possible via portals) would be labeled `hero`. This is also the ordering that places `.emergency-bar` before `nav` — emergency-bar sits inside `<header>` but `<header>` is not in the list, so this is fine. The order looks intentional. Worth documenting.

### M4. `hidden` count is captured once at listener registration
In the FAQ show-more IIFE (line 3197):
```js
var hidden = list.querySelectorAll('.hidden-faq').length;
```
`hidden` is evaluated at script startup. If the hidden FAQ set ever becomes dynamic (e.g., loaded async), the button label `'Ещё N вопросов '` will go stale. Not an issue today (static HTML), but a fragility to flag.

### M5. Button initial text has leading/trailing whitespace, JS writes trimmed text
The source HTML contains `"\n            Ещё 10 вопросов\n            "` as `firstChild.textContent`. The handler replaces it with `'Ещё 10 вопросов '` (single trailing space). After the first toggle, the rendered whitespace around the SVG caret shifts very slightly. Cosmetic only; identical to the pattern used on `show-more-reviews` (line 3124) and was not flagged previously.

### M6. `firstChild.textContent` fragility if markup is reformatted
If a future edit removes the leading newline (e.g., `<button>Ещё 10 вопросов<svg ...>`), `firstChild` becomes the SVG and `.textContent = ...` would replace the SVG's text content (the SVG has no text, so UI breaks silently). Consider `querySelector(':scope > *:first-child')` replacement or a dedicated `<span>` wrapper in the future. Not broken today; same pattern exists in the pre-existing testimonials code, so at least it's consistent.

### M7. Python script does not recurse beyond `news/`
`targets = sorted(deploy.glob("*.html")) + sorted((deploy / "news").glob("*.html"))`. If future content is added under other subdirectories (e.g., `blog/`, `articles/`), they won't be patched. Document the expected layout or add recursion (`rglob`) with an explicit include-list.

---

## Nits

### N1. `<a href="#">` nav brand would match `a[href^="#"]` smooth-scroll handler
Line 1926 `<a href="#" class="nav__brand">` — the smooth-scroll handler calls `document.querySelector("#")` which is invalid as a selector and throws a `SyntaxError` via `querySelector`. The try/catch is **absent** here; clicking the brand link will throw in the console (but default nav still happens because `preventDefault` is inside the `if (target)` block, and `target` is `null`, so the anchor still navigates to `#`). **Not a regression from this PR** — it predates these changes — but flagging since you asked to look at event listeners. Filing a nit rather than a bug.

Actually, correction after re-reading: `document.querySelector('#')` throws in modern Chromium/Firefox (`Failed to execute 'querySelector' on 'Document': '#' is not a valid selector`). Again, pre-existing code path, not this PR's regression.

### N2. `closest()` selector has a comma
`e.target.closest('a[href*="t.me/juli_x11"], a[href*="wa.me/79139406920"]')` — `Element.closest()` has supported comma-separated selector lists since 2020 (Chromium 88+, Firefox 88+, Safari 14+). No issue on any realistic target browser, but worth being aware of if IE11 ever became a requirement (it isn't).

### N3. Duplicate `LOCATIONS` array
The array is hardcoded both in `index.html` (line 3208) and in `scripts/inject_cta_tracking.py` (line 21). Changes to one must be manually synced to the other. Consider having the script rewrite index.html too, or extract the block to a shared file.

### N4. Idempotency marker is string-based
`TRACKER_MARKER = "cta_click_tracker_v1"` appears inside an HTML comment in the injected block. Safe. If the comment is ever manually edited out of a file, re-running the injector would duplicate. Low risk but tag-worthy: a second marker check against the distinctive opening tag would be more robust. What exists is fine for the current ops pattern.

### N5. `GA_ID_MARKER` presence is a proxy for "should inject"
The script skips files without the GA ID. If a future page legitimately uses GA but via a different ID, it would be skipped silently. Print "skipped" lines are helpful here — they make the condition visible in the run output.

### N6. `preventDefault` on smooth-scroll could still race with capture-phase listener
The GA listener is on `document` in **capture** phase; the smooth-scroll listener is on each `a[href^="#"]` in **bubble** phase. Capture runs first. The GA listener only fires for `t.me` / `wa.me` hrefs, so there is no interaction with anchor links. No conflict.

---

## What's done well

- **Delegated listener is the right architecture.** One handler on `document` handles all CTAs present and future, including those injected later.
- **Capture phase with no preventDefault** is the correct pattern for telemetry-on-click — the event is observed before any child `stopPropagation()` could suppress it, and native navigation still proceeds.
- **try/catch around `gtag(...)`** is appropriate: gtag proxies to `dataLayer.push`, which can theoretically throw if the page is being torn down; swallowing the error keeps the user-facing click working.
- **Idempotent Python injector with marker check, GA-presence check, and `</body>` check** — three independent guards before writing. Safe to rerun.
- **Skipping `index.html`** explicitly (different injection context) with a clear reason in the comment is good ops hygiene.
- **Exit codes/summary counts** at end of run (`patched=N, skipped=M`) make CI/sanity verification easy.
- **`a[href*="..."]` selectors** correctly tolerate the `?text=` query-param variants used throughout the site — every single existing Telegram/WhatsApp CTA I checked matches.
- **FAQ show-more CSS pattern** (`display: none` on `.hidden-faq`, overridden by `.expanded` parent class) follows the exact same structure as testimonials. Consistent, no new CSS cascade traps.
- **`.btn--whatsapp` styling** is purely additive — new class, doesn't override any existing selector, uses the same `padding: 16px 32px` and `transform: translateY(-2px)` pattern as `.btn--teal`. No regression risk.

---

## Verification suggestions

1. In DevTools Network tab, trigger one click of each button type and confirm a `google-analytics.com/g/collect` request with `en=cta_click` and the expected `button_location` / `button_type` parameters.
2. Run the Python script twice back-to-back — confirm second run reports 50 skipped, 0 patched.
3. Add `privacy.html` to a skip-list (or add GA to it) depending on intent.
4. Grep all 50 files for `cta_click_tracker_v1` after deploy to confirm coverage.
5. Consider a Yandex.Metrika counterpart event: `ym(108440645, 'reachGoal', 'cta_click', { button_location, button_type })` inside the same try block, so both analytics systems stay in sync.
