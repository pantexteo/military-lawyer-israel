#!/usr/bin/env python3
"""
Cross-linking «силосовая» структура между 15 ситуационными страницами.

3 тематических кластера:
  1. Дезертир: dezertir-cahala (hub) + snyatie, posledstviya,
     ne-znal, voennyj-tribunal
  2. Аэропорт/задержание: zaderzhali-v-aeroportu (hub) +
     voennaya-prokuratura, voennyj-tribunal, dvojnoe-grazhdanstvo
  3. Превентив: proverit-voennyj-status (hub) + repatriant,
     zhenshchina, izrailtyanin, miluim, bnej-mehagrym, vernut-sya

Каждая страница получает 3 контекстных ссылки на родственные —
это пасс PageRank по кластеру и более точное topical relevance
для Google.

Идемпотентен (маркер silo-links-v1).

Использование:
  cd deploy && python3 scripts/inject_silo_links.py
"""
import re
from pathlib import Path

MARKER = "silo-links-v1"

# ID каждой страницы → (название для anchor, cluster, [3 related slugs])
PAGES = {
    # КЛАСТЕР 1: ДЕЗЕРТИР
    "dezertir-cahala.html": {
        "anchor": "Дезертир ЦАХАЛ — как снять статус",
        "related": [
            ("snyatie-statusa-dezertira-cahala.html", "Снятие статуса дезертира за 14 дней"),
            ("posledstviya-ukloneniya-cahala.html", "Последствия уклонения: паспорт, банк, арест"),
            ("voennyj-tribunal-izrail.html", "Военный трибунал: сколько сажают и как защититься"),
        ],
    },
    "snyatie-statusa-dezertira-cahala.html": {
        "anchor": "Снятие статуса дезертира ЦАХАЛ",
        "related": [
            ("dezertir-cahala.html", "Дезертир ЦАХАЛ — что грозит и можно ли вернуться"),
            ("posledstviya-ukloneniya-cahala.html", "Последствия уклонения: паспорт, банк, арест"),
            ("ne-znal-ob-armii-izrail.html", "Не знал об армии Израиля — 5 шагов"),
        ],
    },
    "posledstviya-ukloneniya-cahala.html": {
        "anchor": "Последствия уклонения от ЦАХАЛ",
        "related": [
            ("dezertir-cahala.html", "Дезертир ЦАХАЛ — как снять статус"),
            ("snyatie-statusa-dezertira-cahala.html", "Снятие статуса дезертира за 14 дней"),
            ("voennyj-tribunal-izrail.html", "Военный трибунал — сколько сажают"),
        ],
    },
    "ne-znal-ob-armii-izrail.html": {
        "anchor": "Не знал об армии Израиля",
        "related": [
            ("dezertir-cahala.html", "Дезертир ЦАХАЛ — как снять статус"),
            ("snyatie-statusa-dezertira-cahala.html", "Снятие статуса дезертира за 14 дней"),
            ("posledstviya-ukloneniya-cahala.html", "Последствия уклонения для паспорта и банка"),
        ],
    },
    # КЛАСТЕР 2: АЭРОПОРТ / ЗАДЕРЖАНИЕ
    "zaderzhali-v-aeroportu.html": {
        "anchor": "Задержали в Бен-Гурионе",
        "related": [
            ("voennaya-prokuratura-izrail.html", "Вызов в военную прокуратуру: ваши права"),
            ("voennyj-tribunal-izrail.html", "Военный трибунал — как защититься"),
            ("dvojnoe-grazhdanstvo-armiya.html", "Двойное гражданство и ЦАХАЛ"),
        ],
    },
    "voennaya-prokuratura-izrail.html": {
        "anchor": "Вызов в военную прокуратуру",
        "related": [
            ("zaderzhali-v-aeroportu.html", "Задержали в Бен-Гурионе — что делать"),
            ("voennyj-tribunal-izrail.html", "Военный трибунал — как защититься"),
            ("dezertir-cahala.html", "Дезертир ЦАХАЛ — как снять статус"),
        ],
    },
    "voennyj-tribunal-izrail.html": {
        "anchor": "Военный трибунал ЦАХАЛ",
        "related": [
            ("zaderzhali-v-aeroportu.html", "Задержали в Бен-Гурионе — инструкция"),
            ("voennaya-prokuratura-izrail.html", "Вызов в военную прокуратуру"),
            ("posledstviya-ukloneniya-cahala.html", "Последствия уклонения для паспорта"),
        ],
    },
    "dvojnoe-grazhdanstvo-armiya.html": {
        "anchor": "Двойное гражданство и армия Израиля",
        "related": [
            ("zaderzhali-v-aeroportu.html", "Задержали в Бен-Гурионе"),
            ("repatriant-cahala.html", "Репатриант и ЦАХАЛ — обязанности"),
            ("ne-znal-ob-armii-izrail.html", "Не знал об армии Израиля"),
        ],
    },
    # КЛАСТЕР 3: ПРЕВЕНТИВ
    "proverit-voennyj-status-izrail.html": {
        "anchor": "Проверить статус ЦАХАЛ удалённо",
        "related": [
            ("repatriant-cahala.html", "Репатриант и ЦАХАЛ — кто обязан"),
            ("zhenshchina-cahala.html", "Женщины и ЦАХАЛ — 4 основания освобождения"),
            ("izrailtyanin-za-rubezhom-cahala.html", "Гражданин Израиля живу за рубежом"),
        ],
    },
    "repatriant-cahala.html": {
        "anchor": "Репатриант и ЦАХАЛ",
        "related": [
            ("proverit-voennyj-status-izrail.html", "Проверить статус ЦАХАЛ удалённо"),
            ("miluim-cahala.html", "Милуим из-за границы — штраф до 15 000 шек."),
            ("dvojnoe-grazhdanstvo-armiya.html", "Двойное гражданство и армия"),
        ],
    },
    "zhenshchina-cahala.html": {
        "anchor": "Женщины и ЦАХАЛ",
        "related": [
            ("proverit-voennyj-status-izrail.html", "Проверить статус ЦАХАЛ удалённо"),
            ("repatriant-cahala.html", "Репатриант и ЦАХАЛ — кто обязан"),
            ("ne-znal-ob-armii-izrail.html", "Не знал об армии Израиля — 5 шагов"),
        ],
    },
    "izrailtyanin-za-rubezhom-cahala.html": {
        "anchor": "Гражданин Израиля за рубежом",
        "related": [
            ("proverit-voennyj-status-izrail.html", "Проверить статус ЦАХАЛ удалённо"),
            ("miluim-cahala.html", "Милуим из-за границы"),
            ("vernut-sya-zhit-v-izrail-cahala.html", "Вернуться жить в Израиль"),
        ],
    },
    "miluim-cahala.html": {
        "anchor": "Милуим — резервная служба",
        "related": [
            ("izrailtyanin-za-rubezhom-cahala.html", "Гражданин Израиля за рубежом"),
            ("repatriant-cahala.html", "Репатриант и ЦАХАЛ"),
            ("proverit-voennyj-status-izrail.html", "Проверить статус ЦАХАЛ удалённо"),
        ],
    },
    "vernut-sya-zhit-v-izrail-cahala.html": {
        "anchor": "Вернуться жить в Израиль",
        "related": [
            ("izrailtyanin-za-rubezhom-cahala.html", "Гражданин Израиля за рубежом"),
            ("miluim-cahala.html", "Милуим — резервная служба"),
            ("dezertir-cahala.html", "Дезертир ЦАХАЛ — как снять статус"),
        ],
    },
    "bnej-mehagrym-cahala.html": {
        "anchor": "Бней мехагрим — уехали ребёнком",
        "related": [
            ("ne-znal-ob-armii-izrail.html", "Не знал об армии Израиля"),
            ("repatriant-cahala.html", "Репатриант и ЦАХАЛ"),
            ("snyatie-statusa-dezertira-cahala.html", "Снятие статуса дезертира за 14 дней"),
        ],
    },
}


# CSS вставляется один раз перед </style>
SILO_CSS = """
    /* silo-links-v1 */
    .silo-links {
      padding: 40px 0;
      background: var(--bg-warm, #faf7f2);
      border-top: 1px solid var(--border-light, #e9e4dc);
    }
    .silo-links__title {
      font-family: var(--font-display, Georgia, serif);
      font-size: 1.2rem;
      font-weight: 600;
      color: var(--text-primary, #2c2620);
      margin-bottom: 20px;
    }
    .silo-links__grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
      gap: 12px;
    }
    .silo-links__card {
      display: block;
      padding: 16px 20px;
      background: var(--bg-white, #fff);
      border: 1px solid var(--border-light, #e9e4dc);
      border-radius: var(--radius-md, 8px);
      text-decoration: none;
      color: var(--text-primary, #2c2620);
      font-size: 0.95rem;
      font-weight: 500;
      line-height: 1.4;
      transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
    }
    .silo-links__card:hover {
      border-color: var(--accent, #b8551e);
      box-shadow: var(--card-shadow-hover, 0 4px 16px rgba(0,0,0,0.08));
      transform: translateY(-2px);
    }
    .silo-links__card::after {
      content: " →";
      color: var(--accent, #b8551e);
      font-weight: 600;
    }
"""


def make_block(related: list) -> str:
    """HTML блок «По теме»."""
    cards = []
    for slug, anchor in related:
        cards.append(f'        <a href="{slug}" class="silo-links__card">{anchor}</a>')
    cards_html = "\n".join(cards)
    return f"""
  <!-- silo-links-v1 — внутренние ссылки тематического кластера -->
  <section class="silo-links" aria-label="По теме">
    <div class="container container--narrow">
      <h2 class="silo-links__title">По теме</h2>
      <div class="silo-links__grid">
{cards_html}
      </div>
    </div>
  </section>
"""


# Регэксп для удаления старого блока «Читайте по теме» (без маркера)
OLD_READ_BLOCK_RE = re.compile(
    r'\n?\s*<!-- (Читайте|Читать) по теме -->\s*\n.*?</section>\s*\n',
    re.DOTALL,
)
# Альтернативно — иногда блок без HTML-комментария, ищем по h2-тексту
OLD_READ_BLOCK_RE_2 = re.compile(
    r'\n?\s*<section[^>]*>\s*<div class="container">\s*<h2[^>]*>Читайте по теме</h2>.*?</section>\s*\n',
    re.DOTALL,
)


def process(path: Path, config: dict) -> str:
    html = path.read_text(encoding="utf-8")

    if MARKER in html:
        return "skipped (already patched)"

    # 1. Удалить старый «Читайте по теме» блок если есть
    html, n1 = OLD_READ_BLOCK_RE.subn("\n", html, count=1)
    html, n2 = OLD_READ_BLOCK_RE_2.subn("\n", html, count=1)
    removed_old = n1 + n2

    # 2. Вставить CSS перед </style>
    style_close = html.find("</style>")
    if style_close != -1 and "silo-links-v1" not in html[:style_close]:
        html = html[:style_close] + SILO_CSS + html[style_close:]

    # 3. Вставить HTML блок после </main> или перед author-block
    block = make_block(config["related"])

    # Предпочтительно: после </main> и перед author-block (если есть)
    if "<!-- author-block-v1" in html:
        idx = html.find("<!-- author-block-v1")
        html = html[:idx] + block + "\n  " + html[idx:]
    elif "</main>" in html:
        html = html.replace("</main>", "</main>\n" + block, 1)
    else:
        # вставим перед <footer
        idx = html.find("<footer")
        if idx == -1:
            return "skipped (no </main>, author-block, or <footer>)"
        html = html[:idx] + block + "\n  " + html[idx:]

    path.write_text(html, encoding="utf-8")
    note = f" (removed {removed_old} old)" if removed_old else ""
    return f"patched{note}"


def main() -> None:
    deploy = Path(__file__).resolve().parent.parent
    counters = {"patched": 0, "skipped": 0, "error": 0}
    for filename, config in PAGES.items():
        p = deploy / filename
        if not p.exists():
            print(f"  ! {filename}: NOT FOUND")
            counters["error"] += 1
            continue
        result = process(p, config)
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
