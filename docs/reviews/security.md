# Security Review — feat/cta-faq-analytics

Scope: `index.html` (hero WhatsApp CTA, FAQ accordion, GA4 CTA tracker), `scripts/inject_cta_tracking.py` (propagates tracker to other HTML files), injected block in `dezertir-cahala.html`.

## Summary

**Secure — No security issues found.**

The changes are limited to static HTML, a client-side click listener that emits GA4 events, and a one-shot Python injector that performs a single literal `str.replace()` on `</body>`. There is no user input, no server, no dynamic content, no templating, no `innerHTML`/`insertAdjacentHTML`/`document.write`/`eval`, no `postMessage` receivers, no fetch/XHR added by these changes. Threat surface is essentially zero beyond what GA4 itself already implies.

## Critical issues

None.

## Medium issues

None.

## Nits

1. **`page_path: location.pathname` in GA4** — technically user-navigated, but `pathname` cannot contain hash or query, so no PII leak risk from the URL fragment. GA4 already collects `page_location` by default, so this field is redundant but harmless. Acceptable.
2. **`button_location` / `button_type` fields** — derived from CSS class/`href` prefix on internal anchors only, no user input. Cardinality bounded by `LOCATIONS` array (12 values) + `'other'`. No PII, acceptable for GA4 custom dimensions.
3. **GA4 ID `G-CZV65B06MV` in source** — measurement IDs are public by design (visible in every GA4-enabled page's Network tab). Not a secret. OK.
4. **Inline `<script>` blocks vs. future CSP** — if later a strict CSP is added on Vercel, inline scripts (both the existing gtag bootstrap and the new tracker) would need either `'unsafe-inline'`, hashes, or a nonce. Purely hypothetical for current Vercel setup (no CSP header configured per brief). Not an issue today; flag for the day a CSP is introduced.
5. **`inject_cta_tracking.py` — path traversal** — `Path(__file__).resolve().parent.parent` resolves from the script's own location, then globs `*.html` and `news/*.html` with no user input anywhere in the path. No traversal vector. Safe.
6. **`inject_cta_tracking.py` — content injection** — does a single `content.replace("</body>", SCRIPT_BLOCK + "\n</body>", 1)`. The source strings are hardcoded; the replacement string is a constant literal. No interpolation of untrusted data. Idempotency guard (`TRACKER_MARKER in content`) prevents double-injection. Safe.
7. **Script block is inserted verbatim into arbitrary HTML** — if a target file were adversarial and contained, say, a broken `</body>` inside a `<script>` or HTML comment, the injector could insert into a location the author did not intend. In practice the repo content is authored in-house, so this is author-trust territory, not an attacker vector. Note but not actionable.

## Что хорошо сделано

- **All external CTAs use `target="_blank" rel="noopener noreferrer"` consistently** — grep across `index.html` shows every `t.me/juli_x11` and `wa.me/79139406920` anchor carries both `noopener` and `noreferrer`. Reverse-tabnabbing and referrer leakage to WhatsApp/Telegram are both closed.
- **Event listener is delegated and uses `a.closest()` with a specific href filter** — no way for a click on unrelated content to trigger the tracker; no DOM writes of any kind.
- **No untrusted data flows into the DOM** — the new code only *reads* (`getAttribute('href')`, `closest()`, `location.pathname`) and *calls* `gtag()`. `textContent` is used in the FAQ-show-more/reviews toggles but only with hardcoded literal strings. No `innerHTML` anywhere in the added code.
- **Python injector is idempotent and defensive** — guards on `GA_ID_MARKER`, `TRACKER_MARKER`, presence of `</body>`, and explicitly skips `index.html`. `.replace(..., 1)` limits to first occurrence.
- **PII hygiene in GA4 payload** — only `button_location` (enum), `button_type` (`'whatsapp'|'telegram'`), `page_path` (static route). No query strings, no Telegram prefilled message text, no user input — even though the anchor `href`s contain Russian prefilled messages via `?text=...`, the tracker ignores them (`getAttribute('href')` is used only for the `wa.me` substring check, not forwarded to gtag).
- **FAQ accordion uses class toggles + `aria-expanded`** — no HTML rewriting, no injected content, just `classList.toggle` and attribute updates. Accessibility-correct and XSS-free.
- **`try/catch` around `gtag(...)`** — a failed analytics call cannot break navigation or surface an error to users.
- **No new secrets, tokens, keys or configs** introduced.

---

**Verdict:** Ship it. No security changes required for this PR.
