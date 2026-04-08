#!/usr/bin/env python3
"""
Автоматическое обновление новостей на tzahal-advokat.com

1. Exa AI ищет свежие новости о ЦАХАЛе и призыве
2. Nemotron 49B генерирует полноценную статью (600-800 слов) + FAQ
3. Создаёт HTML-страницу в /news/
4. Обновляет карточки на главной (ссылки на НАШИ статьи)
5. Обновляет sitemap.xml

Запуск:
  python3 scripts/update_news.py
"""

import os
import re
import sys
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urlparse

# Загрузка .env файла
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

try:
    from exa_py import Exa
except ImportError:
    print("ERROR: exa_py not installed. Run: pip install exa-py")
    sys.exit(1)

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai not installed. Run: pip install openai")
    sys.exit(1)

# ---- Настройки ----
DEPLOY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
NEWS_DIR = os.path.join(DEPLOY_DIR, "news")
INDEX_HTML = os.path.join(DEPLOY_DIR, "index.html")
SITEMAP_XML = os.path.join(DEPLOY_DIR, "sitemap.xml")
START_MARKER = "<!-- NEWS_BLOCK_START -->"
END_MARKER = "<!-- NEWS_BLOCK_END -->"
NEWS_COUNT = 3  # статей за запуск (больше = дольше генерация)
ISRAEL_TZ = timezone(timedelta(hours=3))
SITE_URL = "https://tzahal-advokat.com"

# NVIDIA NIM
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL_NAME = "nvidia/llama-3.3-nemotron-super-49b-v1.5"

SEARCH_QUERIES = [
    "ЦАХАЛ дезертир уклонист призыв 2026",
    "армия Израиль призывники закон уклонение 2026",
    "мобилизация Израиль харедим резервисты призыв",
]

BLOCKED_DOMAINS = ["haaretz.com", "jpost.com", "timesofisrael.com", "ynetnews.com"]

# Промпт для генерации полной статьи
ARTICLE_PROMPT = """\
Ты — редактор русскоязычного сайта tzahal-advokat.com. Сайт помогает выходцам из СНГ с проблемами военной службы в Израиле (ЦАХАЛ): дезертиры, уклонисты, задержанные в аэропорту, резервисты.

Основатель проекта — Юлия. Она не адвокат, но сама прошла через задержание в аэропорту Бен-Гурион и теперь помогает другим через связи с военными адвокатами (бывшими прокурорами).

Вот новость:
Заголовок: {title}
Источник: {source}
Дата: {date}
Текст: {text}

ЗАДАЧА: напиши статью для нашего сайта на основе этой новости.

ФОРМАТ ОТВЕТА — строго JSON (без markdown, без ```):
{{
  "title": "SEO-заголовок статьи на русском (50-70 символов, с ключевым словом)",
  "meta_description": "Описание для Google (130-155 символов)",
  "lead": "Вводный абзац: что случилось и почему это важно для нашей аудитории (2-3 предложения)",
  "sections": [
    {{
      "heading": "Подзаголовок секции",
      "text": "Текст секции (2-4 абзаца, разделённых \\n\\n)"
    }},
    {{
      "heading": "Ещё подзаголовок",
      "text": "Текст"
    }}
  ],
  "faq": [
    {{
      "question": "Вопрос, который задала бы наша аудитория",
      "answer": "Ответ (2-3 предложения)"
    }},
    {{
      "question": "Ещё вопрос",
      "answer": "Ответ"
    }},
    {{
      "question": "Третий вопрос",
      "answer": "Ответ"
    }}
  ],
  "card_summary": "Описание для карточки на главной (2 предложения, до 150 символов)",
  "slug": "transliterated-slug-for-url"
}}

ПРАВИЛА:
1. Пиши по-русски, простым языком, как для друга. Без канцелярита.
2. Статья 600-800 слов. 2-3 секции.
3. Объясни что эта новость значит для человека, который числится дезертиром/уклонистом или боится лететь в Израиль.
4. Упомяни Юлию и проект естественно (не рекламно): "Мы проверяем статус бесплатно" или "Если вас это касается — напишите нам".
5. Используй конкретику из новости: даты, цифры, имена, законы.
6. FAQ — вопросы, которые реально задал бы испуганный человек.
7. Slug — транслитерация (prizyv-reservistov-2026), без кириллицы, через дефис.
8. Если новость нерелевантна аудитории — верни: {{"skip": true}}"""

# Промпт для summary (если статья уже была пропущена)
SUMMARY_PROMPT = """\
Напиши 2 предложения (до 150 символов) для карточки новости. Аудитория — русскоязычные с проблемами с армией Израиля.
Заголовок: {title}
Текст: {text}
Верни ТОЛЬКО текст, без кавычек."""


def format_date_ru(iso_date: str) -> str:
    months_ru = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
                 "июля", "августа", "сентября", "октября", "ноября", "декабря"]
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        dt = dt.astimezone(ISRAEL_TZ)
        return f"{dt.day} {months_ru[dt.month]} {dt.year}"
    except Exception:
        return iso_date[:10] if iso_date else ""


def format_date_iso(iso_date: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(ISRAEL_TZ).strftime("%Y-%m-%d")


def get_source_name(url: str) -> str:
    known = {
        "newsru.co.il": "NEWSru.co.il", "vesty.co.il": "Вести",
        "israelinfo.co.il": "israelinfo.co.il", "maariv.co.il": "Маарив",
        "ynet.co.il": "Ynet", "theins.ru": "The Insider",
        "meduza.io": "Meduza", "9tv.co.il": "Девятый канал",
        "iton.tv": "iton.tv", "detaly.co.il": "Детали",
    }
    for domain, name in known.items():
        if domain in url:
            return name
    try:
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return "Источник"


def is_blocked(url: str) -> bool:
    return any(d in url for d in BLOCKED_DOMAINS)


def escape_html(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def slug_exists(slug: str) -> bool:
    return os.path.exists(os.path.join(NEWS_DIR, f"{slug}.html"))


def fetch_news(exa_key: str) -> list:
    exa = Exa(api_key=exa_key)
    results = []
    seen_urls = set()

    for query in SEARCH_QUERIES:
        try:
            response = exa.search_and_contents(
                query, num_results=5,
                text={"max_characters": 800},
                start_published_date=(
                    datetime.now(timezone.utc) - timedelta(days=60)
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                type="auto",
            )
            for item in response.results:
                if item.url in seen_urls or is_blocked(item.url):
                    continue
                seen_urls.add(item.url)
                raw_text = item.text[:800] if hasattr(item, "text") and item.text else ""
                results.append({
                    "url": item.url,
                    "title": item.title or "",
                    "date": item.published_date or "",
                    "raw_text": raw_text,
                    "source": get_source_name(item.url),
                })
        except Exception as e:
            print(f"WARNING: Exa query '{query}' failed: {e}")

    results.sort(key=lambda x: x["date"], reverse=True)
    return results[:NEWS_COUNT + 5]  # запас на фильтрацию


def generate_article(client: OpenAI, item: dict) -> Optional[dict]:
    """Генерирует полную статью через Nemotron."""
    prompt = ARTICLE_PROMPT.format(
        title=item["title"],
        source=item["source"],
        date=format_date_ru(item["date"]),
        text=item["raw_text"][:600],
    )
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            max_tokens=4096,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.choices[0].message.content
        if not content:
            print(f"  WARNING: Empty response for '{item['title'][:40]}'")
            return None

        # Парсим JSON
        # Убираем возможные markdown-обёртки
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```\w*\n?", "", content)
            content = re.sub(r"\n?```$", "", content)

        data = json.loads(content)
        if data.get("skip"):
            return None

        # Проверяем обязательные поля
        required = ["title", "meta_description", "lead", "sections", "faq", "card_summary", "slug"]
        if not all(k in data for k in required):
            print(f"  WARNING: Missing fields in response")
            return None

        # Очистка slug
        data["slug"] = re.sub(r"[^a-z0-9-]", "", data["slug"].lower().replace(" ", "-"))

        return data
    except json.JSONDecodeError as e:
        print(f"  WARNING: JSON parse error: {e}")
        return None
    except Exception as e:
        print(f"  WARNING: Article generation failed: {e}")
        return None


def build_article_html(article: dict, item: dict) -> str:
    """Создаёт HTML-страницу статьи."""
    slug = article["slug"]
    date_iso = format_date_iso(item["date"])
    date_ru = format_date_ru(item["date"])
    today_iso = datetime.now(ISRAEL_TZ).strftime("%Y-%m-%d")

    # Секции статьи
    sections_html = ""
    for section in article["sections"]:
        paragraphs = section["text"].split("\n\n")
        p_html = "\n".join(f"            <p>{escape_html(p.strip())}</p>" for p in paragraphs if p.strip())
        sections_html += f"""
        <section style="margin-bottom:48px;">
          <h2 style="font-family:var(--font-display);font-size:clamp(1.3rem,2.5vw,1.7rem);font-weight:600;color:var(--text-primary);margin-bottom:20px;line-height:1.3;">{escape_html(section["heading"])}</h2>
          <div style="font-size:1.05rem;line-height:1.8;color:var(--text-body);">
{p_html}
          </div>
        </section>"""

    # FAQ HTML
    faq_items_html = ""
    faq_schema_items = []
    for faq in article["faq"]:
        faq_items_html += f"""
          <div class="faq-item">
            <button class="faq-item__question" aria-expanded="false">
              <span class="faq-item__question-text">{escape_html(faq["question"])}</span>
              <svg class="faq-item__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
            <div class="faq-item__answer">
              <div class="faq-item__answer-inner">{escape_html(faq["answer"])}</div>
            </div>
          </div>"""
        faq_schema_items.append({
            "@type": "Question",
            "name": faq["question"],
            "acceptedAnswer": {"@type": "Answer", "text": faq["answer"]}
        })

    faq_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faq_schema_items
    }, ensure_ascii=False, indent=2)

    breadcrumb_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": f"{SITE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": "Новости", "item": f"{SITE_URL}/news/"},
            {"@type": "ListItem", "position": 3, "name": article["title"], "item": f"{SITE_URL}/news/{slug}.html"}
        ]
    }, ensure_ascii=False, indent=2)

    article_schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": article["title"],
        "description": article["meta_description"],
        "datePublished": f"{date_iso}T00:00:00+03:00",
        "dateModified": f"{today_iso}T00:00:00+03:00",
        "author": {"@type": "Person", "name": "Юлия", "url": f"{SITE_URL}/"},
        "publisher": {"@type": "Organization", "name": "Юлия — Помощь с армией Израиля"},
        "mainEntityOfPage": f"{SITE_URL}/news/{slug}.html",
        "image": f"{SITE_URL}/img/og-cover.jpg"
    }, ensure_ascii=False, indent=2)

    return f"""<!DOCTYPE html>
<html lang="ru" dir="ltr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">

  <title>{escape_html(article["title"])}</title>
  <meta name="description" content="{escape_html(article["meta_description"])}">

  <meta name="robots" content="index, follow">
  <link rel="canonical" href="{SITE_URL}/news/{slug}.html">

  <meta name="google-site-verification" content="zHuvCkzCcL93xjS8lIrfD8SkIoKhUom2khvFGUHoA1s">
  <meta name="yandex-verification" content="c9a5e7506b420bf2">

  <meta property="og:type" content="article">
  <meta property="og:locale" content="ru_RU">
  <meta property="og:title" content="{escape_html(article["title"])}">
  <meta property="og:description" content="{escape_html(article["meta_description"])}">
  <meta property="og:image" content="{SITE_URL}/img/og-cover.jpg">
  <meta property="og:url" content="{SITE_URL}/news/{slug}.html">
  <meta property="article:published_time" content="{date_iso}T00:00:00+03:00">
  <meta property="article:modified_time" content="{today_iso}T00:00:00+03:00">
  <meta property="og:site_name" content="Юлия — Помощь с армией Израиля">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape_html(article["title"])}">
  <meta name="twitter:description" content="{escape_html(article["meta_description"])}">

  <!-- Analytics -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-CZV65B06MV"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-CZV65B06MV');</script>
  <script>(function(m,e,t,r,i,k,a){{m[i]=m[i]||function(){{(m[i].a=m[i].a||[]).push(arguments)}};m[i].l=1*new Date();for(var j=0;j<document.scripts.length;j++){{if(document.scripts[j].src===r){{return;}}}}k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)}})(window,document,"script","https://mc.yandex.ru/metrika/tag.js","ym");ym(108440645,"init",{{clickmap:true,trackLinks:true,accurateTrackBounce:true,webvisor:true}});</script>

  <!-- Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">

  <!-- Schema -->
  <script type="application/ld+json">{faq_schema}</script>
  <script type="application/ld+json">{breadcrumb_schema}</script>
  <script type="application/ld+json">{article_schema}</script>

  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ scroll-behavior: smooth; }}
    :root {{
      --bg-cream: #FAF8F5; --bg-warm: #F0EDE8; --bg-paper: #F5F2ED; --bg-white: #FFFFFF;
      --text-primary: #1A1A2E; --text-secondary: #3D3D56; --text-body: #4A4A5A; --text-muted: #7A7A8A;
      --accent: #B85C38; --accent-hover: #9E4D2E; --accent-bg: rgba(184,92,56,0.06); --accent-border: rgba(184,92,56,0.2);
      --teal: #2C6E63; --crisis: #DC2626;
      --card-shadow: 0 1px 3px rgba(26,26,46,0.04), 0 6px 24px rgba(26,26,46,0.06);
      --card-shadow-hover: 0 2px 8px rgba(26,26,46,0.06), 0 12px 36px rgba(26,26,46,0.1);
      --border-light: rgba(26,26,46,0.08); --border-medium: rgba(26,26,46,0.12);
      --font-display: 'Outfit', sans-serif; --font-body: 'DM Sans', sans-serif;
      --content-max: 720px; --radius-md: 14px;
    }}
    body {{ font-family: var(--font-body); font-size: 17px; line-height: 1.7; color: var(--text-body); background: var(--bg-cream); -webkit-font-smoothing: antialiased; overflow-x: hidden; }}
    h1,h2,h3 {{ font-family: var(--font-display); color: var(--text-primary); line-height: 1.2; font-weight: 600; }}
    a {{ color: var(--accent); text-decoration: none; transition: color 0.2s; }}
    a:hover {{ color: var(--accent-hover); }}
    p {{ margin-bottom: 1.25em; }} p:last-child {{ margin-bottom: 0; }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 0 clamp(20px,4vw,40px); }}
    .container--narrow {{ max-width: var(--content-max); margin: 0 auto; padding: 0 clamp(20px,4vw,40px); }}

    .emergency-bar {{ position: fixed; top: 0; left: 0; right: 0; z-index: 1000; background: linear-gradient(90deg,#7f1d1d 0%,#DC2626 50%,#7f1d1d 100%); padding: 10px 0; }}
    .emergency-bar__inner {{ display: flex; align-items: center; justify-content: center; gap: 12px; flex-wrap: wrap; text-align: center; }}
    .emergency-bar__pulse {{ width: 8px; height: 8px; border-radius: 50%; background: #fff; animation: pulse-dot 2s ease-in-out infinite; }}
    @keyframes pulse-dot {{ 0%,100% {{ opacity:1;transform:scale(1); }} 50% {{ opacity:0.5;transform:scale(1.4); }} }}
    .emergency-bar__text {{ font-size: 14px; font-weight: 600; color: #fff; }}
    .emergency-bar__link {{ display: inline-flex; align-items: center; gap: 6px; padding: 5px 16px; background: #fff; color: #DC2626; border-radius: 100px; font-size: 13px; font-weight: 700; transition: background 0.2s; }}
    .emergency-bar__link:hover {{ background: #fee2e2; color: #DC2626; }}

    .nav {{ position: fixed; top: 44px; left: 0; right: 0; z-index: 900; background: rgba(250,248,245,0.92); backdrop-filter: blur(16px); border-bottom: 1px solid var(--border-light); }}
    .nav__inner {{ display: flex; align-items: center; justify-content: space-between; height: 64px; }}
    .nav__brand {{ font-family: var(--font-display); font-size: 1.15rem; font-weight: 600; color: var(--text-primary); }}
    .nav__brand span {{ color: var(--text-muted); font-weight: 400; font-size: 0.95rem; margin-left: 4px; }}
    .nav__cta {{ padding: 8px 20px; background: var(--accent); color: #fff !important; border-radius: 100px; font-size: 13px; font-weight: 600; transition: background 0.2s; }}
    .nav__cta:hover {{ background: var(--accent-hover); color: #fff !important; }}

    .breadcrumb {{ padding: 12px 0; border-bottom: 1px solid var(--border-light); background: var(--bg-white); margin-top: calc(44px + 64px); }}
    .breadcrumb__list {{ display: flex; align-items: center; gap: 8px; list-style: none; font-size: 13px; color: var(--text-muted); }}
    .breadcrumb__list a {{ color: var(--text-muted); }} .breadcrumb__list a:hover {{ color: var(--accent); }}

    .article-hero {{ padding: calc(44px + 64px + clamp(40px,6vw,64px)) 0 clamp(40px,6vw,64px); background: var(--bg-cream); }}
    .article-hero h1 {{ font-size: clamp(1.8rem,4vw,2.8rem); letter-spacing: -0.02em; margin-bottom: 20px; max-width: 720px; }}
    .article-meta {{ font-size: 0.9rem; color: var(--text-muted); margin-bottom: 32px; display: flex; gap: 16px; flex-wrap: wrap; }}
    .article-lead {{ font-size: clamp(1.05rem,1.8vw,1.2rem); color: var(--text-secondary); line-height: 1.8; max-width: 680px; }}

    .article-body {{ padding: clamp(40px,6vw,80px) 0; background: var(--bg-white); border-top: 1px solid var(--border-light); }}

    .faq {{ background: var(--bg-warm); border-top: 1px solid var(--border-light); padding: clamp(48px,8vw,80px) 0; }}
    .faq-list {{ max-width: 720px; }}
    .faq-item {{ border-bottom: 1px solid var(--border-light); }}
    .faq-item__question {{ width: 100%; background: none; border: none; text-align: left; padding: 20px 0; cursor: pointer; display: flex; align-items: center; justify-content: space-between; gap: 16px; }}
    .faq-item__question-text {{ font-family: var(--font-display); font-size: 1rem; font-weight: 600; color: var(--text-primary); line-height: 1.4; }}
    .faq-item__icon {{ width: 20px; height: 20px; flex-shrink: 0; color: var(--accent); transition: transform 0.3s; }}
    .faq-item.open .faq-item__icon {{ transform: rotate(45deg); }}
    .faq-item__answer {{ max-height: 0; overflow: hidden; transition: max-height 0.4s; }}
    .faq-item.open .faq-item__answer {{ max-height: 400px; }}
    .faq-item__answer-inner {{ padding: 0 0 20px; font-size: 0.95rem; color: var(--text-secondary); line-height: 1.75; }}

    .final-cta {{ background: var(--bg-cream); border-top: 1px solid var(--border-light); padding: clamp(48px,8vw,80px) 0; }}
    .btn--primary {{ display: inline-flex; align-items: center; gap: 8px; padding: 16px 32px; background: var(--accent); color: #fff; border-radius: 100px; font-weight: 600; font-size: 15px; border: none; cursor: pointer; transition: all 0.25s; text-decoration: none; }}
    .btn--primary:hover {{ background: var(--accent-hover); color: #fff; transform: translateY(-2px); }}
    .icon-tg {{ width: 18px; height: 18px; fill: currentColor; }}

    .source-link {{ margin-top: 40px; padding: 20px 24px; background: var(--bg-paper); border: 1px solid var(--border-light); border-radius: var(--radius-md); font-size: 0.9rem; }}
    .source-link a {{ font-weight: 600; }}

    .footer {{ background: var(--bg-warm); border-top: 1px solid var(--border-light); padding: clamp(40px,6vw,64px) 0; }}
    .footer__brand {{ font-family: var(--font-display); font-size: 1.1rem; font-weight: 600; color: var(--text-primary); }}
    .footer__links {{ display: flex; gap: 24px; list-style: none; flex-wrap: wrap; margin-top: 12px; }}
    .footer__links a {{ font-size: 14px; color: var(--text-muted); }}
    .footer__copy {{ font-size: 13px; color: var(--text-muted); max-width: 560px; line-height: 1.6; margin-top: 12px; }}

    .mobile-bar {{ display: none; position: fixed; bottom: 0; left: 0; right: 0; z-index: 800; background: var(--bg-white); border-top: 1px solid var(--border-light); padding: 12px 16px; padding-bottom: calc(12px + env(safe-area-inset-bottom)); }}
    .mobile-bar__btn {{ display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; padding: 16px; background: var(--accent); color: #fff; border-radius: 14px; font-weight: 700; font-size: 16px; text-decoration: none; }}
    @media (max-width: 768px) {{ .mobile-bar {{ display: block; }} body {{ padding-bottom: 80px; }} }}
  </style>
</head>
<body>
  <!-- Emergency bar -->
  <div class="emergency-bar" role="alert">
    <div class="container">
      <div class="emergency-bar__inner">
        <div class="emergency-bar__pulse"></div>
        <span class="emergency-bar__text">Задержали прямо сейчас?</span>
        <a href="https://t.me/juli_x11?text=%D0%9C%D0%B5%D0%BD%D1%8F%20%D0%B7%D0%B0%D0%B4%D0%B5%D1%80%D0%B6%D0%B0%D0%BB%D0%B8" class="emergency-bar__link">Написать срочно</a>
      </div>
    </div>
  </div>

  <!-- Nav -->
  <nav class="nav">
    <div class="container">
      <div class="nav__inner">
        <a href="/" class="nav__brand">Юлия<span>Помощь с армией Израиля</span></a>
        <a href="https://t.me/juli_x11" class="nav__cta" target="_blank" rel="noopener noreferrer">Написать в Telegram</a>
      </div>
    </div>
  </nav>

  <!-- Breadcrumb -->
  <div class="breadcrumb">
    <div class="container">
      <ol class="breadcrumb__list">
        <li><a href="/">Главная</a></li>
        <li style="color:var(--border-medium);">/</li>
        <li style="color:var(--text-secondary);font-weight:500;">{escape_html(article["title"])}</li>
      </ol>
    </div>
  </div>

  <main>
    <!-- Hero -->
    <section class="article-hero">
      <div class="container--narrow">
        <h1>{escape_html(article["title"])}</h1>
        <div class="article-meta">
          <span>{date_ru}</span>
          <span>Источник: {escape_html(item["source"])}</span>
          <span>Автор: Юлия</span>
        </div>
        <p class="article-lead">{escape_html(article["lead"])}</p>
      </div>
    </section>

    <!-- Article body -->
    <section class="article-body">
      <div class="container--narrow">
{sections_html}

        <div class="source-link">
          Источник новости: <a href="{escape_html(item["url"])}" target="_blank" rel="noopener noreferrer">{escape_html(item["source"])}</a>
        </div>
      </div>
    </section>

    <!-- FAQ -->
    <section class="faq">
      <div class="container--narrow">
        <h2 style="font-family:var(--font-display);font-size:clamp(1.5rem,3vw,2rem);margin-bottom:32px;">Вопросы по теме</h2>
        <div class="faq-list">
{faq_items_html}
        </div>
      </div>
    </section>

    <!-- CTA -->
    <section class="final-cta">
      <div class="container--narrow" style="text-align:center;">
        <h2 style="font-family:var(--font-display);font-size:clamp(1.5rem,3vw,2rem);margin-bottom:20px;">Хотите узнать свой статус?</h2>
        <p style="font-size:1.05rem;color:var(--text-secondary);margin-bottom:32px;line-height:1.8;">Напишите в Telegram — проверим бесплатно, есть ли у вас проблемы с армией Израиля. Конфиденциально, без обязательств.</p>
        <a href="https://t.me/juli_x11?text=%D0%97%D0%B4%D1%80%D0%B0%D0%B2%D1%81%D1%82%D0%B2%D1%83%D0%B9%D1%82%D0%B5%2C%20%D1%85%D0%BE%D1%87%D1%83%20%D0%BF%D1%80%D0%BE%D0%B2%D0%B5%D1%80%D0%B8%D1%82%D1%8C%20%D1%81%D1%82%D0%B0%D1%82%D1%83%D1%81" class="btn--primary" target="_blank" rel="noopener noreferrer">
          <svg class="icon-tg" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.2-.04-.28-.02-.12.03-2.02 1.28-5.69 3.77-.54.37-1.03.55-1.47.54-.48-.01-1.4-.27-2.09-.49-.84-.27-1.51-.42-1.45-.88.03-.24.37-.49 1.02-.74 3.99-1.74 6.65-2.89 7.99-3.45 3.8-1.6 4.59-1.88 5.1-1.89.11 0 .37.03.54.17.14.12.18.28.2.45-.01.06.01.24 0 .45z"/></svg>
          Проверить статус бесплатно
        </a>
      </div>
    </section>
  </main>

  <!-- Footer -->
  <footer class="footer">
    <div class="container">
      <div class="footer__brand">Юлия | Помощь с армией Израиля</div>
      <ul class="footer__links">
        <li><a href="https://t.me/juli_x11" target="_blank">Telegram</a></li>
        <li><a href="mailto:chinchin-co@mail.ru">chinchin-co@mail.ru</a></li>
        <li><a href="/">На главную</a></li>
      </ul>
      <p class="footer__copy">Юридическое сопровождение ведут адвокаты — бывшие военные прокуроры Израиля.</p>
      <p style="margin-top:8px;font-size:0.8rem;color:var(--text-muted);">&copy; 2026 Юлия — Помощь с армией Израиля</p>
    </div>
  </footer>

  <!-- Mobile bar -->
  <div class="mobile-bar">
    <a href="https://t.me/juli_x11" class="mobile-bar__btn" target="_blank">
      <svg class="icon-tg" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.2-.04-.28-.02-.12.03-2.02 1.28-5.69 3.77-.54.37-1.03.55-1.47.54-.48-.01-1.4-.27-2.09-.49-.84-.27-1.51-.42-1.45-.88.03-.24.37-.49 1.02-.74 3.99-1.74 6.65-2.89 7.99-3.45 3.8-1.6 4.59-1.88 5.1-1.89.11 0 .37.03.54.17.14.12.18.28.2.45-.01.06.01.24 0 .45z"/></svg>
      Проверить статус бесплатно
    </a>
  </div>

  <script>
    document.querySelectorAll('.faq-item__question').forEach(function(btn){{
      btn.addEventListener('click',function(){{
        var item=this.closest('.faq-item');
        var isOpen=item.classList.contains('open');
        document.querySelectorAll('.faq-item.open').forEach(function(o){{if(o!==item){{o.classList.remove('open');o.querySelector('.faq-item__question').setAttribute('aria-expanded','false');}}}});
        item.classList.toggle('open',!isOpen);
        this.setAttribute('aria-expanded',!isOpen);
      }});
    }});
  </script>
</body>
</html>"""


def build_card_html(article: dict, item: dict) -> str:
    """Карточка для блока новостей на главной."""
    slug = article["slug"]
    return f"""\
        <a href="news/{slug}.html" style="display:block;background:var(--bg-white);border:1px solid var(--border-light);border-radius:var(--radius-md);padding:20px 22px;text-decoration:none;transition:border-color 0.2s,box-shadow 0.2s;" onmouseover="this.style.borderColor='var(--accent)';this.style.boxShadow='var(--card-shadow-hover)'" onmouseout="this.style.borderColor='var(--border-light)';this.style.boxShadow='none'">
          <div style="font-size:0.8rem;color:var(--accent);font-weight:600;margin-bottom:8px;font-family:var(--font-display);">{escape_html(format_date_ru(item["date"]))} · {escape_html(item["source"])}</div>
          <div style="font-family:var(--font-display);font-size:1rem;font-weight:600;color:var(--text-primary);line-height:1.4;margin-bottom:8px;">{escape_html(article["title"])}</div>
          <div style="font-size:0.875rem;color:var(--text-muted);line-height:1.5;">{escape_html(article["card_summary"])}</div>
        </a>"""


def update_index(cards_html: str) -> bool:
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        content = f.read()
    start = content.find(START_MARKER)
    end = content.find(END_MARKER)
    if start == -1 or end == -1:
        print("ERROR: Markers not found in index.html")
        return False
    after_start = start + len(START_MARKER)
    content = content[:after_start] + "\n" + cards_html + "\n        " + content[end:]
    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def update_sitemap(slugs: list, dates: list):
    if not os.path.exists(SITEMAP_XML):
        return
    with open(SITEMAP_XML, "r", encoding="utf-8") as f:
        content = f.read()
    insert_before = "</urlset>"
    new_entries = ""
    for slug, date in zip(slugs, dates):
        url = f"{SITE_URL}/news/{slug}.html"
        if url in content:
            continue
        date_iso = format_date_iso(date)
        new_entries += f"""  <url>
    <loc>{url}</loc>
    <lastmod>{date_iso}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>
"""
    if new_entries:
        content = content.replace(insert_before, new_entries + insert_before)
        with open(SITEMAP_XML, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  Sitemap: added {len(slugs)} URLs")


def main():
    exa_key = os.environ.get("EXA_API_KEY")
    nvidia_key = os.environ.get("NVIDIA_API_KEY")
    if not exa_key:
        print("ERROR: EXA_API_KEY not set"); sys.exit(1)
    if not nvidia_key:
        print("ERROR: NVIDIA_API_KEY not set"); sys.exit(1)

    os.makedirs(NEWS_DIR, exist_ok=True)

    now = datetime.now(ISRAEL_TZ).strftime("%Y-%m-%d %H:%M")
    print(f"[{now} IST] Step 1: Fetching news via Exa...")
    candidates = fetch_news(exa_key)
    print(f"  Found {len(candidates)} candidates")

    print("Step 2: Generating articles via Nemotron 49B (NVIDIA NIM)...")
    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=nvidia_key)

    articles = []  # (article_data, news_item)
    for item in candidates:
        if len(articles) >= NEWS_COUNT:
            break
        print(f"  Processing: {item['title'][:60]}...")
        article = generate_article(client, item)
        if article is None:
            print(f"    SKIP")
            continue
        if slug_exists(article["slug"]):
            print(f"    SKIP (already exists): {article['slug']}")
            continue
        articles.append((article, item))
        print(f"    OK: {article['slug']}")

    if not articles:
        print("WARNING: No new articles generated")
        sys.exit(0)

    print(f"Step 3: Writing {len(articles)} article pages...")
    cards = []
    slugs = []
    dates = []
    for article, item in articles:
        html = build_article_html(article, item)
        path = os.path.join(NEWS_DIR, f"{article['slug']}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  Created: news/{article['slug']}.html")
        cards.append(build_card_html(article, item))
        slugs.append(article["slug"])
        dates.append(item["date"])

    print("Step 4: Updating index.html news block...")
    cards_html = "\n\n".join(cards)
    if update_index(cards_html):
        print("  OK: index.html updated")

    print("Step 5: Updating sitemap.xml...")
    update_sitemap(slugs, dates)

    print(f"\nDone! Created {len(articles)} articles.")


if __name__ == "__main__":
    main()
