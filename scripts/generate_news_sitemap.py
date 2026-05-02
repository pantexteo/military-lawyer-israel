#!/usr/bin/env python3
"""
Генерирует sitemap-news.xml — отдельный Google News Sitemap для
новостных статей в /news/.

Формат: https://developers.google.com/search/docs/crawling-indexing/sitemaps/news-sitemap

Правила Google News:
- Включать только статьи опубликованные за последние 2 дня
- Максимум 1000 URL
- В нашем случае — для News-индексации Google использует обычный sitemap
  плюс эти news-метки. Включаем все статьи за последние 30 дней
  с правильным publication_date (полезно даже без партнёрки с Google News —
  даёт сигнал что это новостной контент).

Использование:
  cd deploy && python3 scripts/generate_news_sitemap.py
"""
import re
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone
from html import escape

SITE_URL = "https://tzahal-advokat.com"
NEWS_DIR = Path("news")
OUTPUT = Path("sitemap-news.xml")
MAX_AGE_DAYS = 60  # включаем статьи за последние 60 дней


def git_first_commit_iso(path: Path) -> str:
    """Возвращает дату ПЕРВОГО git-коммита по файлу в ISO 8601 — это когда
    статья появилась на сайте. Это и есть publication_date."""
    try:
        out = subprocess.check_output(
            ["git", "log", "--diff-filter=A", "--format=%cI", "--", str(path)],
            stderr=subprocess.DEVNULL,
        ).decode().strip().splitlines()
        if out:
            return out[-1]  # последняя строка = самый ранний коммит
    except Exception:
        pass
    return ""


def git_last_commit_iso(path: Path) -> str:
    """Дата последнего коммита — для lastmod."""
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI", "--", str(path)],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if out:
            return out
    except Exception:
        pass
    return ""


def article_published_iso(html: str) -> str:
    """Пытаемся извлечь дату публикации из HTML — meta tag или time element."""
    # 1. <meta property="article:published_time" content="2026-04-22T...">
    m = re.search(r'<meta property="article:published_time" content="([^"]+)"', html)
    if m:
        return m.group(1)
    # 2. <time datetime="2026-04-22" pubdate>
    m = re.search(r'<time[^>]*datetime="([^"]+)"[^>]*>', html)
    if m:
        return m.group(1)
    # 3. JSON-LD datePublished
    m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1)
    return ""


def get_title(html: str) -> str:
    m = re.search(r"<title>([^<]+)</title>", html)
    if not m:
        return ""
    title = m.group(1).strip()
    # Очистим " | suffix" если есть
    title = re.split(r"\s*[|—]\s*tzahal", title, maxsplit=1)[0]
    return title.strip()


def main() -> None:
    if not NEWS_DIR.exists():
        print(f"News dir not found: {NEWS_DIR}")
        return

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    entries = []

    for path in sorted(NEWS_DIR.glob("*.html")):
        if path.name == "index.html":
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue

        # publication_date — из HTML или из первого git-коммита
        pub_iso = article_published_iso(html) or git_first_commit_iso(path)
        if not pub_iso:
            continue
        try:
            article_date = datetime.fromisoformat(pub_iso)
        except ValueError:
            continue
        if article_date < cutoff:
            continue

        # lastmod — последний коммит
        lastmod_iso = git_last_commit_iso(path) or pub_iso
        try:
            lastmod_date = datetime.fromisoformat(lastmod_iso)
        except ValueError:
            lastmod_date = article_date

        title = get_title(html)
        if not title:
            continue
        url = f"{SITE_URL}/news/{path.name}"
        entries.append({
            "url": url,
            "title": title,
            "date": pub_iso,
            "lastmod": lastmod_date.strftime("%Y-%m-%d"),
        })

    # Сортируем по дате (новые первыми)
    entries.sort(key=lambda e: e["date"], reverse=True)

    # Собираем XML
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">',
        '',
    ]
    for e in entries:
        lines += [
            "  <url>",
            f"    <loc>{escape(e['url'])}</loc>",
            f"    <lastmod>{e['lastmod']}</lastmod>",
            "    <news:news>",
            "      <news:publication>",
            "        <news:name>tzahal-advokat.com</news:name>",
            "        <news:language>ru</news:language>",
            "      </news:publication>",
            f"      <news:publication_date>{escape(e['date'])}</news:publication_date>",
            f"      <news:title>{escape(e['title'])}</news:title>",
            "    </news:news>",
            "  </url>",
        ]
    lines.append("</urlset>")
    lines.append("")

    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {OUTPUT} with {len(entries)} news URLs")


if __name__ == "__main__":
    main()
