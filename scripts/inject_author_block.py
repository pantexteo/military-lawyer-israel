#!/usr/bin/env python3
"""
Добавляет Author Block (видимый блок «Об авторе» от Юлии) и
JSON-LD Article schema на 15 русских ситуационных страниц.

Это E-E-A-T-сигнал для Google в YMYL-нише — рекомендация
Senior SEO 01.05. Сейчас Юлия упоминается только в hero,
но на подстраницах нет явного authorship.

Идемпотентен:
- Если блок уже вставлен (маркер author-block-v1) — пропускает
- Если Article schema уже есть — не дублирует

Использование:
  cd deploy && python3 scripts/inject_author_block.py
"""
import re
from pathlib import Path

MARKER = "author-block-v1"

# Author block — HTML
AUTHOR_BLOCK_TEMPLATE = """\

  <!-- author-block-v1 — E-E-A-T для YMYL: явное authorship + проверка адвокатом -->
  <aside class="author-block">
    <div class="container container--narrow">
      <div class="author-block__inner">
        <div class="author-block__photo">
          <img src="img/yulia-portrait.jpg" alt="Юлия — основатель проекта" loading="lazy" width="80" height="80">
        </div>
        <div class="author-block__content">
          <p class="author-block__label">Об авторе</p>
          <h2 class="author-block__name">Юлия — основатель проекта &laquo;Помощь с&nbsp;армией Израиля&raquo;</h2>
          <p class="author-block__bio">Прошла через задержание в&nbsp;аэропорту Бен-Гурион и&nbsp;военную тюрьму за&nbsp;статус дезертира, о&nbsp;котором не&nbsp;знала. С&nbsp;2024&nbsp;года вместе с&nbsp;командой бывших военных прокуроров помогает другим репатриантам урегулировать военный статус в&nbsp;ЦАХАЛе&nbsp;&mdash; от&nbsp;проверки статуса до&nbsp;закрытия дела.</p>
          <p class="author-block__verified">Юридическую часть этой страницы проверил <a href="/#team">адвокат Давид Леви</a>&nbsp;&mdash; член Коллегии адвокатов Израиля, бывший военный адвокат ЦАХАЛ.</p>
        </div>
      </div>
    </div>
  </aside>
"""

# CSS — будет вставлен один раз перед </style> в каждой странице
AUTHOR_BLOCK_CSS = """
    /* author-block-v1 */
    .author-block {
      padding: 36px 0;
      background: var(--bg-warm, #faf7f2);
      border-top: 1px solid var(--border-light, #e9e4dc);
    }
    .author-block__inner {
      display: flex;
      gap: 20px;
      align-items: flex-start;
    }
    .author-block__photo {
      flex-shrink: 0;
      width: 80px;
      height: 80px;
      border-radius: 50%;
      overflow: hidden;
      border: 1px solid var(--border-medium, #d6cfc1);
    }
    .author-block__photo img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .author-block__content { flex: 1; min-width: 0; }
    .author-block__label {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted, #6b6357);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 6px;
    }
    .author-block__name {
      font-family: var(--font-display, Georgia, serif);
      font-size: 1.05rem;
      font-weight: 600;
      color: var(--text-primary, #2c2620);
      line-height: 1.35;
      margin-bottom: 8px;
    }
    .author-block__bio {
      font-size: 0.95rem;
      line-height: 1.6;
      color: var(--text-body, #443d34);
      margin-bottom: 10px;
    }
    .author-block__verified {
      font-size: 0.85rem;
      color: var(--text-muted, #6b6357);
      padding: 8px 12px;
      background: var(--bg-white, #fff);
      border-left: 3px solid var(--accent, #b8551e);
      border-radius: 4px;
    }
    .author-block__verified a {
      color: var(--accent, #b8551e);
      font-weight: 600;
      text-decoration: none;
    }
    .author-block__verified a:hover { text-decoration: underline; }
    @media (max-width: 600px) {
      .author-block__inner { flex-direction: column; gap: 16px; }
    }
"""

# 15 русских ситуационных страниц
PAGES = [
    "dezertir-cahala.html",
    "zaderzhali-v-aeroportu.html",
    "proverit-voennyj-status-izrail.html",
    "ne-znal-ob-armii-izrail.html",
    "repatriant-cahala.html",
    "miluim-cahala.html",
    "zhenshchina-cahala.html",
    "bnej-mehagrym-cahala.html",
    "izrailtyanin-za-rubezhom-cahala.html",
    "snyatie-statusa-dezertira-cahala.html",
    "voennaya-prokuratura-izrail.html",
    "voennyj-tribunal-izrail.html",
    "dvojnoe-grazhdanstvo-armiya.html",
    "vernut-sya-zhit-v-izrail-cahala.html",
    "posledstviya-ukloneniya-cahala.html",
]


def get_meta(html: str, key: str, attr: str = "name") -> str:
    """Извлекает <meta name=key content=...>"""
    m = re.search(rf'<meta {attr}="{key}" content="([^"]+)"', html)
    return m.group(1) if m else ""


def get_canonical(html: str) -> str:
    m = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    return m.group(1) if m else ""


def get_title(html: str) -> str:
    m = re.search(r"<title>([^<]+)</title>", html)
    return m.group(1) if m else ""


def already_has_article(html: str) -> bool:
    return '"@type": "Article"' in html or '"@type":"Article"' in html


def make_article_schema(title: str, desc: str, url: str) -> str:
    # Конкретное JSON для Article с author=#yulia, publisher=#org
    return (
        "\n  <!-- author-block-v1 — Article schema (E-E-A-T) -->\n"
        '  <script type="application/ld+json">\n'
        "  {\n"
        '    "@context": "https://schema.org",\n'
        '    "@type": "Article",\n'
        f'    "headline": {repr_json(title)},\n'
        f'    "description": {repr_json(desc)},\n'
        '    "image": "https://tzahal-advokat.com/img/og-cover.jpg",\n'
        f'    "url": "{url}",\n'
        '    "author": {"@type": "Person", "@id": "https://tzahal-advokat.com/#yulia"},\n'
        '    "publisher": {"@type": "Organization", "@id": "https://tzahal-advokat.com/#org"},\n'
        '    "inLanguage": "ru",\n'
        '    "isAccessibleForFree": true,\n'
        '    "datePublished": "2026-04-09",\n'
        '    "dateModified": "2026-05-01"\n'
        "  }\n"
        "  </script>\n"
    )


def repr_json(s: str) -> str:
    """Экранирует строку для JSON-вставки в HTML."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def process(path: Path) -> str:
    html = path.read_text(encoding="utf-8")

    if MARKER in html:
        return "skipped (already patched)"

    title = get_title(html)
    desc = get_meta(html, "description")
    url = get_canonical(html)
    if not (title and desc and url):
        return f"skipped (missing title/desc/canonical: {bool(title)}/{bool(desc)}/{bool(url)})"

    # 1. Article schema — после последнего </script> с ld+json (скорее всего BreadcrumbList)
    if not already_has_article(html):
        # Найдём последний JSON-LD скрипт и вставим Article после него
        last_jsonld = list(re.finditer(
            r'<script type="application/ld\+json">.*?</script>',
            html, re.DOTALL
        ))
        if last_jsonld:
            insert_at = last_jsonld[-1].end()
            article = make_article_schema(title, desc, url)
            html = html[:insert_at] + article + html[insert_at:]

    # 2. Author block CSS — перед закрытием первого <style>
    style_close = html.find("</style>")
    if style_close != -1:
        html = html[:style_close] + AUTHOR_BLOCK_CSS + html[style_close:]

    # 3. Author block HTML — после </main> или перед <footer>
    if "</main>" in html:
        html = html.replace("</main>", "</main>\n" + AUTHOR_BLOCK_TEMPLATE, 1)
    elif "<footer" in html:
        # вставим перед первым <footer>
        idx = html.find("<footer")
        html = html[:idx] + AUTHOR_BLOCK_TEMPLATE + "\n  " + html[idx:]
    else:
        return "skipped (no </main> nor <footer>)"

    path.write_text(html, encoding="utf-8")
    return "patched"


def main() -> None:
    deploy = Path(__file__).resolve().parent.parent
    counters = {"patched": 0, "skipped": 0, "error": 0}
    for filename in PAGES:
        p = deploy / filename
        if not p.exists():
            print(f"  ! {filename}: NOT FOUND")
            counters["error"] += 1
            continue
        result = process(p)
        print(f"  {filename}: {result}")
        if result.startswith("patched"):
            counters["patched"] += 1
        elif result.startswith("skipped"):
            counters["skipped"] += 1
        else:
            counters["error"] += 1
    print(f"\nTotal: {counters}")


if __name__ == "__main__":
    main()
