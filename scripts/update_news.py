#!/usr/bin/env python3
"""
Автоматическое обновление блока новостей на tzahal-advokat.com
Использует Exa AI для поиска свежих новостей о ЦАХАЛе и призыве.

Запуск:
  EXA_API_KEY=your_key python3 scripts/update_news.py
"""

import os
import re
import sys
from datetime import datetime, timezone, timedelta

try:
    from exa_py import Exa
except ImportError:
    print("ERROR: exa_py not installed. Run: pip install exa-py")
    sys.exit(1)

# ---- Настройки ----
HTML_FILE = "deploy/index.html"
START_MARKER = "<!-- NEWS_BLOCK_START -->"
END_MARKER = "<!-- NEWS_BLOCK_END -->"
NEWS_COUNT = 5
ISRAEL_TZ = timezone(timedelta(hours=3))

SEARCH_QUERIES = [
    "ЦАХАЛ дезертир уклонист призыв 2026",
    "армия Израиль призывники закон 2026",
    "мобилизация Израиль харедим призыв",
]

CARD_TEMPLATE = """\
        <a href="{url}" target="_blank" rel="noopener noreferrer" style="display:block;background:var(--bg-white);border:1px solid var(--border-light);border-radius:var(--radius-md);padding:20px 22px;text-decoration:none;transition:border-color 0.2s,box-shadow 0.2s;" onmouseover="this.style.borderColor='var(--accent)';this.style.boxShadow='var(--card-shadow-hover)'" onmouseout="this.style.borderColor='var(--border-light)';this.style.boxShadow='none'">
          <div style="font-size:0.8rem;color:var(--accent);font-weight:600;margin-bottom:8px;font-family:var(--font-display);">{date} · {source}</div>
          <div style="font-family:var(--font-display);font-size:1rem;font-weight:600;color:var(--text-primary);line-height:1.4;margin-bottom:8px;">{title}</div>
          <div style="font-size:0.875rem;color:var(--text-muted);line-height:1.5;">{summary}</div>
        </a>"""


def format_date_ru(iso_date: str) -> str:
    """Конвертирует ISO дату в русский формат: 3 апреля 2026"""
    months_ru = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря"
    ]
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        dt = dt.astimezone(ISRAEL_TZ)
        return f"{dt.day} {months_ru[dt.month]} {dt.year}"
    except Exception:
        return iso_date[:10]


def get_source_name(url: str) -> str:
    """Извлекает название источника из URL"""
    known = {
        "newsru.co.il": "NEWSru.co.il",
        "vesty.co.il": "Вести",
        "israelinfo.co.il": "israelinfo.co.il",
        "maariv.co.il": "Маарив",
        "ynet.co.il": "Ynet",
        "haaretz.co.il": "Haaretz",
        "jpost.com": "Jerusalem Post",
        "timesofisrael.com": "Times of Israel",
        "theins.ru": "The Insider",
        "meduza.io": "Meduza",
        "9tv.co.il": "Девятый канал",
    }
    for domain, name in known.items():
        if domain in url:
            return name
    # Fallback — берём домен без www
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.netloc.replace("www.", "").replace("beta.", "")
        return host
    except Exception:
        return "Источник"


def truncate(text: str, max_len: int = 140) -> str:
    """Обрезает текст до max_len символов"""
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def escape_html(text: str) -> str:
    """Минимальный экранирование HTML"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def fetch_news(api_key: str) -> list[dict]:
    """Загружает свежие новости через Exa"""
    exa = Exa(api_key=api_key)
    results = []
    seen_urls = set()

    for query in SEARCH_QUERIES:
        try:
            response = exa.search_and_contents(
                query,
                num_results=4,
                use_autoprompt=True,
                text={"max_characters": 300},
                highlights={"num_sentences": 2},
                start_published_date=(
                    datetime.now(timezone.utc) - timedelta(days=90)
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                type="news",
            )
            for item in response.results:
                if item.url not in seen_urls:
                    seen_urls.add(item.url)
                    # Краткое описание: сначала highlights, потом text
                    summary = ""
                    if hasattr(item, "highlights") and item.highlights:
                        summary = " ".join(item.highlights[:1])
                    elif hasattr(item, "text") and item.text:
                        summary = item.text
                    results.append({
                        "url": item.url,
                        "title": item.title or "",
                        "date": item.published_date or "",
                        "summary": summary,
                    })
        except Exception as e:
            print(f"WARNING: Exa query '{query}' failed: {e}")

    # Сортируем по дате (новые первые) и берём первые NEWS_COUNT
    results.sort(key=lambda x: x["date"], reverse=True)
    return results[:NEWS_COUNT]


def build_cards(news_items: list[dict]) -> str:
    """Генерирует HTML-карточки новостей"""
    cards = []
    for item in news_items:
        card = CARD_TEMPLATE.format(
            url=escape_html(item["url"]),
            date=escape_html(format_date_ru(item["date"])),
            source=escape_html(get_source_name(item["url"])),
            title=escape_html(truncate(item["title"], 100)),
            summary=escape_html(truncate(item["summary"], 140)),
        )
        cards.append(card)
    return "\n\n".join(cards)


def update_html(html_path: str, new_cards_html: str) -> bool:
    """Вставляет новые карточки между маркерами в HTML-файле"""
    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    start_idx = content.find(START_MARKER)
    end_idx = content.find(END_MARKER)

    if start_idx == -1 or end_idx == -1:
        print(f"ERROR: Markers not found in {html_path}")
        return False

    after_start = start_idx + len(START_MARKER)
    new_content = (
        content[:after_start]
        + "\n"
        + new_cards_html
        + "\n        "
        + content[end_idx:]
    )

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"OK: Updated {html_path} with {len(new_cards_html.split(START_MARKER))} news cards")
    return True


def main():
    api_key = os.environ.get("EXA_API_KEY")
    if not api_key:
        print("ERROR: EXA_API_KEY environment variable not set")
        sys.exit(1)

    print(f"[{datetime.now(ISRAEL_TZ).strftime('%Y-%m-%d %H:%M')} IST] Fetching news...")
    news_items = fetch_news(api_key)

    if not news_items:
        print("WARNING: No news found, keeping existing content")
        sys.exit(0)

    print(f"Found {len(news_items)} articles")
    for item in news_items:
        print(f"  - {item['title'][:60]}...")

    cards_html = build_cards(news_items)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    html_path = os.path.join(project_root, HTML_FILE)

    if not os.path.exists(html_path):
        print(f"ERROR: HTML file not found: {html_path}")
        sys.exit(1)

    success = update_html(html_path, cards_html)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
