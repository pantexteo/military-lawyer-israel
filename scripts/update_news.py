#!/usr/bin/env python3
"""
Автоматическое обновление блока новостей на tzahal-advokat.com

Шаг 1: Exa AI ищет свежие новости о ЦАХАЛе и призыве
Шаг 2: Claude переписывает summary с SEO-ключевиками для русской аудитории
Шаг 3: Обновляет index.html между маркерами NEWS_BLOCK_START/END

Запуск:
  EXA_API_KEY=xxx ANTHROPIC_API_KEY=sk-ant-xxx python3 scripts/update_news.py
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

try:
    from exa_py import Exa
except ImportError:
    print("ERROR: exa_py not installed. Run: pip install exa-py")
    sys.exit(1)

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic not installed. Run: pip install anthropic")
    sys.exit(1)

# ---- Настройки ----
HTML_FILE = "deploy/index.html"
START_MARKER = "<!-- NEWS_BLOCK_START -->"
END_MARKER = "<!-- NEWS_BLOCK_END -->"
NEWS_COUNT = 5
ISRAEL_TZ = timezone(timedelta(hours=3))

# SEO-ключевики для органичного вплетения в текст
SEO_KEYWORDS = [
    "дезертир ЦАХАЛ",
    "уклонист от армии Израиля",
    "задержали в аэропорту Израиль",
    "призыв в ЦАХАЛ",
    "военная служба Израиль",
    "проблемы с армией Израиля",
]

SEARCH_QUERIES = [
    "ЦАХАЛ дезертир уклонист призыв 2026",
    "армия Израиль призывники закон уклонение 2026",
    "мобилизация Израиль харедим резервисты призыв",
]

# Домены, которые НЕ подходят (не русскоязычная аудитория или нерелевантно)
BLOCKED_DOMAINS = ["haaretz.com", "jpost.com", "timesofisrael.com", "ynetnews.com"]

CARD_TEMPLATE = """\
        <a href="{url}" target="_blank" rel="noopener noreferrer" style="display:block;background:var(--bg-white);border:1px solid var(--border-light);border-radius:var(--radius-md);padding:20px 22px;text-decoration:none;transition:border-color 0.2s,box-shadow 0.2s;" onmouseover="this.style.borderColor='var(--accent)';this.style.boxShadow='var(--card-shadow-hover)'" onmouseout="this.style.borderColor='var(--border-light)';this.style.boxShadow='none'">
          <div style="font-size:0.8rem;color:var(--accent);font-weight:600;margin-bottom:8px;font-family:var(--font-display);">{date} · {source}</div>
          <div style="font-family:var(--font-display);font-size:1rem;font-weight:600;color:var(--text-primary);line-height:1.4;margin-bottom:8px;">{title}</div>
          <div style="font-size:0.875rem;color:var(--text-muted);line-height:1.5;">{summary}</div>
        </a>"""

SEO_PROMPT = """\
Ты SEO-редактор русскоязычного сайта про армию Израиля. Аудитория — выходцы из СНГ, у которых проблемы с военной службой в Израиле (ЦАХАЛ): дезертиры, уклонисты, те кого задержали в аэропорту, резервисты за рубежом.

Вот новость:
Заголовок: {title}
Текст: {text}

Задача: напиши краткое описание (2 предложения, до 150 символов) для карточки новости на сайте.

Правила:
1. Только по-русски, простым языком
2. Органично вплети ОДНО из этих слов/фраз: {keyword}
3. Объясни почему это важно для человека с проблемами с армией Израиля
4. Не переусердствуй с SEO — текст должен звучать естественно
5. Верни ТОЛЬКО текст описания, без кавычек, без пояснений

Если новость нерелевантна для аудитории (не связана с армией/призывом/дезертирами) — верни строку: SKIP"""


def format_date_ru(iso_date: str) -> str:
    months_ru = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
                 "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        dt = dt.astimezone(ISRAEL_TZ)
        return f"{dt.day} {months_ru[dt.month]} {dt.year}"
    except Exception:
        return iso_date[:10] if iso_date else ""


def get_source_name(url: str) -> str:
    known = {
        "newsru.co.il": "NEWSru.co.il",
        "vesty.co.il": "Вести",
        "israelinfo.co.il": "israelinfo.co.il",
        "maariv.co.il": "Маарив",
        "ynet.co.il": "Ynet",
        "haaretz.co.il": "Haaretz",
        "theins.ru": "The Insider",
        "meduza.io": "Meduza",
        "9tv.co.il": "Девятый канал",
        "iton.tv": "iton.tv",
        "detaly.co.il": "Детали",
    }
    for domain, name in known.items():
        if domain in url:
            return name
    try:
        host = urlparse(url).netloc.replace("www.", "").replace("beta.", "")
        return host
    except Exception:
        return "Источник"


def is_blocked(url: str) -> bool:
    return any(d in url for d in BLOCKED_DOMAINS)


def escape_html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def truncate(text: str, max_len: int = 120) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def fetch_news(exa_key: str) -> list[dict]:
    """Шаг 1: Загружает свежие новости через Exa"""
    exa = Exa(api_key=exa_key)
    results = []
    seen_urls = set()

    for query in SEARCH_QUERIES:
        try:
            response = exa.search_and_contents(
                query,
                num_results=5,
                use_autoprompt=True,
                text={"max_characters": 500},
                highlights={"num_sentences": 2},
                start_published_date=(
                    datetime.now(timezone.utc) - timedelta(days=90)
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                type="news",
            )
            for item in response.results:
                if item.url in seen_urls or is_blocked(item.url):
                    continue
                seen_urls.add(item.url)
                raw_text = ""
                if hasattr(item, "highlights") and item.highlights:
                    raw_text = " ".join(item.highlights[:2])
                elif hasattr(item, "text") and item.text:
                    raw_text = item.text[:500]
                results.append({
                    "url": item.url,
                    "title": item.title or "",
                    "date": item.published_date or "",
                    "raw_text": raw_text,
                    "summary": "",  # заполнится Claude
                })
        except Exception as e:
            print(f"WARNING: Exa query '{query}' failed: {e}")

    results.sort(key=lambda x: x["date"], reverse=True)
    return results[:NEWS_COUNT + 3]  # берём с запасом — некоторые могут быть отфильтрованы


def seo_rewrite(claude: anthropic.Anthropic, item: dict, keyword: str) -> str | None:
    """Шаг 2: Claude переписывает summary с SEO-ключевиком. Возвращает None если нерелевантно."""
    prompt = SEO_PROMPT.format(
        title=item["title"],
        text=item["raw_text"][:400],
        keyword=keyword,
    )
    try:
        message = claude.messages.create(
            model="claude-haiku-3-5",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        result = message.content[0].text.strip()
        if result == "SKIP" or result.startswith("SKIP"):
            return None
        return result
    except Exception as e:
        print(f"WARNING: Claude rewrite failed for '{item['title'][:40]}': {e}")
        # Fallback — используем raw_text обрезанный
        return truncate(item["raw_text"], 140) or None


def build_cards(news_items: list[dict]) -> str:
    """Шаг 3: Генерирует HTML-карточки"""
    cards = []
    for item in news_items:
        card = CARD_TEMPLATE.format(
            url=escape_html(item["url"]),
            date=escape_html(format_date_ru(item["date"])),
            source=escape_html(get_source_name(item["url"])),
            title=escape_html(truncate(item["title"], 100)),
            summary=escape_html(item["summary"]),
        )
        cards.append(card)
    return "\n\n".join(cards)


def update_html(html_path: str, new_cards_html: str) -> bool:
    """Вставляет карточки между маркерами в HTML-файле"""
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

    return True


def main():
    exa_key = os.environ.get("EXA_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if not exa_key:
        print("ERROR: EXA_API_KEY not set")
        sys.exit(1)
    if not anthropic_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    now = datetime.now(ISRAEL_TZ).strftime("%Y-%m-%d %H:%M")
    print(f"[{now} IST] Step 1: Fetching news via Exa...")
    candidates = fetch_news(exa_key)
    print(f"  Found {len(candidates)} candidates")

    print("Step 2: SEO rewrite via Claude...")
    claude = anthropic.Anthropic(api_key=anthropic_key)
    final_items = []
    keyword_idx = 0

    for item in candidates:
        if len(final_items) >= NEWS_COUNT:
            break
        keyword = SEO_KEYWORDS[keyword_idx % len(SEO_KEYWORDS)]
        summary = seo_rewrite(claude, item, keyword)
        if summary is None:
            print(f"  SKIP (irrelevant): {item['title'][:50]}")
            continue
        item["summary"] = summary
        final_items.append(item)
        keyword_idx += 1
        print(f"  OK [{keyword[:20]}…]: {item['title'][:50]}")

    if not final_items:
        print("WARNING: No relevant news found, keeping existing content")
        sys.exit(0)

    print(f"Step 3: Building {len(final_items)} cards...")
    cards_html = build_cards(final_items)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    html_path = os.path.join(project_root, HTML_FILE)

    if not os.path.exists(html_path):
        print(f"ERROR: HTML file not found: {html_path}")
        sys.exit(1)

    if update_html(html_path, cards_html):
        print(f"OK: {html_path} updated successfully")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
