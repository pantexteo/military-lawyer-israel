#!/usr/bin/env python3
"""
Обновляет <lastmod> в sitemap.xml на дату реального изменения файлов.

Сейчас все записи имеют lastmod=2026-04-15 (время первого деплоя),
что снижает доверие Google к sitemap. Запуск этого скрипта
проставляет каждому URL дату последнего git-коммита, который
менял его файл — это и есть «правда» для поисковика.

Использование:
  cd deploy && python3 scripts/regenerate_sitemap_lastmod.py
"""
import re
import subprocess
from pathlib import Path
from datetime import datetime, timezone

SITEMAP = Path("sitemap.xml")
SITE_URL = "https://tzahal-advokat.com"


def git_lastmod(path: Path) -> str:
    """ISO дата последнего коммита, который менял этот файл."""
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI", "--", str(path)],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if out:
            # %cI = strict ISO 8601 — берём только дату
            return out.split("T")[0]
    except Exception:
        pass
    # Fallback — mtime файла
    if path.exists():
        ts = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return ts.strftime("%Y-%m-%d")
    return ""


def url_to_path(url: str) -> Path:
    """Маппинг URL из sitemap → путь к файлу в deploy/."""
    rel = url.replace(SITE_URL, "").lstrip("/")
    if rel == "" or rel.endswith("/"):
        rel = (rel + "index.html").lstrip("/")
    return Path(rel)


def main() -> None:
    content = SITEMAP.read_text(encoding="utf-8")
    # Находим блоки <url>...</url> и обновляем lastmod в каждом
    updated = 0
    skipped = 0

    def repl(match: "re.Match[str]") -> str:
        nonlocal updated, skipped
        block = match.group(0)
        loc_m = re.search(r"<loc>([^<]+)</loc>", block)
        if not loc_m:
            return block
        url = loc_m.group(1).strip()
        path = url_to_path(url)
        if not path.exists():
            skipped += 1
            return block
        new_date = git_lastmod(path)
        if not new_date:
            skipped += 1
            return block
        new_block, n = re.subn(
            r"<lastmod>[^<]+</lastmod>",
            f"<lastmod>{new_date}</lastmod>",
            block,
            count=1,
        )
        if n == 0:
            # lastmod отсутствовал — добавим перед </url>
            new_block = block.replace(
                "</url>",
                f"  <lastmod>{new_date}</lastmod>\n  </url>",
                1,
            )
        if new_block != block:
            updated += 1
        return new_block

    new_content = re.sub(r"<url>.*?</url>", repl, content, flags=re.DOTALL)
    SITEMAP.write_text(new_content, encoding="utf-8")
    print(f"sitemap.xml: updated {updated} entries, skipped {skipped}")


if __name__ == "__main__":
    main()
