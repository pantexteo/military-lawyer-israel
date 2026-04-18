#!/usr/bin/env python3
"""
Добавляет сводный трекер CTA-кликов (Telegram + WhatsApp) в каждый HTML,
в котором уже подключён gtag с ID G-CZV65B06MV.

Сейчас отправляет события параллельно в:
  - Google Analytics 4: gtag('event', 'cta_click', {...})
  - Яндекс.Метрика:      ym(108440645, 'reachGoal', 'cta_click_<type>', {...})

Идемпотентен:
  - если найден v2-маркер — пропускает файл
  - если найден v1-маркер — удаляет старый блок и вставляет v2 (миграция)
  - иначе — вставляет v2 блок перед </body>

Пропускает index.html (он патчится вручную — там трекер встроен в существующий <script>).

Использование:
  cd deploy && python3 scripts/inject_cta_tracking.py
"""
import re
from pathlib import Path

GA_ID_MARKER = "G-CZV65B06MV"
TRACKER_MARKER_V1 = "cta_click_tracker_v1"
TRACKER_MARKER_V2 = "cta_click_tracker_v2"

# Регэксп для удаления старого v1-блока (вместе с ведущим пустым переводом строки)
V1_BLOCK_RE = re.compile(
    r"\n?<script>\s*\n\s*//\s*cta_click_tracker_v1.*?</script>\s*\n?",
    re.DOTALL,
)

SCRIPT_BLOCK = """<script>
  // cta_click_tracker_v2 — GA4 + Yandex.Metrika event tracking for Telegram + WhatsApp CTAs
  (function() {
    var LOCATIONS = [
      ['.emergency-bar', 'emergency_bar'],
      ['.mobile-bar', 'mobile_bar'],
      ['.desktop-cta', 'desktop_cta'],
      ['.risk-cta', 'risk_cta'],
      ['.story__cta', 'story_cta'],
      ['.mid-cta', 'mid_cta'],
      ['.steps__cta', 'steps_cta'],
      ['.faq-item__answer-cta', 'faq_answer'],
      ['.final-cta', 'final_cta'],
      ['.hero', 'hero'],
      ['footer', 'footer'],
      ['.nav', 'nav_header']
    ];
    document.addEventListener('click', function(e) {
      var a = e.target.closest('a[href*="t.me/juli_x11"], a[href*="wa.me/79139406920"]');
      if (!a) return;
      var href = a.getAttribute('href') || '';
      var button_type = href.indexOf('wa.me') !== -1 ? 'whatsapp' : 'telegram';
      var button_location = 'other';
      for (var i = 0; i < LOCATIONS.length; i++) {
        if (a.closest(LOCATIONS[i][0])) { button_location = LOCATIONS[i][1]; break; }
      }
      try {
        if (typeof gtag === 'function') {
          gtag('event', 'cta_click', {
            button_location: button_location,
            button_type: button_type,
            page_path: location.pathname
          });
        }
        if (typeof ym === 'function') {
          ym(108440645, 'reachGoal', 'cta_click_' + button_type, { button_location: button_location });
        }
      } catch (err) { /* noop */ }
    }, true);
  })();
</script>
"""


def process(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    if GA_ID_MARKER not in content:
        return "skipped (no GA4)"
    if TRACKER_MARKER_V2 in content:
        return "skipped (already v2)"
    if "</body>" not in content:
        return "skipped (no </body>)"

    migrated_from_v1 = False
    if TRACKER_MARKER_V1 in content:
        new_content, n = V1_BLOCK_RE.subn("\n", content, count=1)
        if n == 0 or TRACKER_MARKER_V1 in new_content:
            return "error (v1 present but regex did not match — manual fix needed)"
        content = new_content
        migrated_from_v1 = True

    content = content.replace("</body>", SCRIPT_BLOCK + "\n</body>", 1)
    path.write_text(content, encoding="utf-8")
    return "migrated v1→v2" if migrated_from_v1 else "patched"


def main() -> None:
    deploy = Path(__file__).resolve().parent.parent
    targets = sorted(deploy.glob("*.html")) + sorted((deploy / "news").glob("*.html"))
    counters: dict[str, int] = {}
    for f in targets:
        rel = f.relative_to(deploy)
        # index.html патчится вручную — там трекер уже внутри существующего <script>
        if rel == Path("index.html"):
            result = "skipped (index.html, patched manually)"
        else:
            result = process(f)
        counters[result] = counters.get(result, 0) + 1
        print(f"{rel}: {result}")
    print("\nTotal:")
    for k, v in counters.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
