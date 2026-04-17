#!/usr/bin/env python3
"""
Добавляет GA4-трекер CTA-кликов (Telegram + WhatsApp) в каждый HTML,
в котором уже подключён gtag с ID G-CZV65B06MV.

Идемпотентен: повторный запуск не дублирует скрипт (проверка по маркеру).
Пропускает index.html (он патчится вручную — там другая точка вставки).

Использование:
  cd deploy && python3 scripts/inject_cta_tracking.py
"""
from pathlib import Path

GA_ID_MARKER = "G-CZV65B06MV"
TRACKER_MARKER = "cta_click_tracker_v1"

SCRIPT_BLOCK = """<script>
  // cta_click_tracker_v1 — GA4 event tracking for Telegram + WhatsApp CTAs
  (function() {
    if (typeof gtag !== 'function') return;
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
        gtag('event', 'cta_click', {
          button_location: button_location,
          button_type: button_type,
          page_path: location.pathname
        });
      } catch (err) { /* noop */ }
    }, true);
  })();
</script>
"""


def process(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    if GA_ID_MARKER not in content:
        return "skipped (no GA4)"
    if TRACKER_MARKER in content:
        return "skipped (already patched)"
    if "</body>" not in content:
        return "skipped (no </body>)"
    new_content = content.replace("</body>", SCRIPT_BLOCK + "\n</body>", 1)
    path.write_text(new_content, encoding="utf-8")
    return "patched"


def main() -> None:
    deploy = Path(__file__).resolve().parent.parent
    targets = sorted(deploy.glob("*.html")) + sorted((deploy / "news").glob("*.html"))
    patched = skipped = 0
    for f in targets:
        rel = f.relative_to(deploy)
        # index.html патчится вручную — там трекер уже внутри существующего <script>
        if rel == Path("index.html"):
            print(f"{rel}: skipped (index.html, patched manually)")
            skipped += 1
            continue
        result = process(f)
        print(f"{rel}: {result}")
        if result == "patched":
            patched += 1
        else:
            skipped += 1
    print(f"\nTotal: patched={patched}, skipped={skipped}")


if __name__ == "__main__":
    main()
