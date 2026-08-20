import json
import re
import time
import random
import unicodedata
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_md

MIN_DELAY_SECONDS = 1.5
MAX_DELAY_SECONDS = 3.0

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

# Print URL + status code
def fetch(url: str) -> str:
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
    print(f"[DEBUG] fetch {url}) -> status={resp.status_code}, {len(resp.text)} chars of HTML")
    resp.raise_for_status()
    return resp.text

def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "untitled"

BREADCRUMB_LINE_RE = re.compile(r"^\d+\.\s*\[.+?\]\(.+?\)", re.MULTILINE)

def clean_main_content(
    html: str,
    footer_start_markers: list[str] = (),
    content_start_markers: list[str] = (),
    breadcrumb_re: re.Pattern = BREADCRUMB_LINE_RE,
) -> tuple[str, str]:
    # Returns (title, cleaned_markdown_body)
    soup = BeautifulSoup(html, "html.parser")
    
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "Untitled"
    
    md_text = html_to_md(str(soup.body or soup), heading_style="ATX")
    print(f"[DEBUG] clean_main_content() full-page markdown length: {len(md_text)} chars")
    
    # Take the first breadcrumb match
    breadcrumb_matches = list(breadcrumb_re.finditer(md_text))
    start_idx = breadcrumb_matches[0].start() if breadcrumb_matches else 0
    print(f"[DEBUG] clean_main_content() breadcrumb start_idx: {start_idx}"
          f"({'found' if breadcrumb_matches else 'NOT found, using 0'})")
    
    # If a content-start marker shows up after the breadcrumb, skipp boilerplate sits between the breadcrumb and it
    for marker in content_start_markers:
        pos = md_text.find(marker, start_idx)
        if pos != -1:
            print(f"[DEBUG] clean_main_content() skipping boilerplate"
                  f"jumpping start_idx {start_idx} -> {pos} (marker: {marker!r})")
            start_idx = pos
            break
        
    # Only search for footer markers after the breadcrumb
    cut_at = len(md_text)
    triggered_by = None
    for marker in footer_start_markers:
        pos = md_text.find(marker, start_idx)
        if pos != -1 and pos < cut_at:
            cut_at = pos
            triggered_by = marker
    print(f"[DEBUG] clean_main_content() cutoff at {cut_at} chars, triggered by: {triggered_by!r}")
    
    content = md_text[start_idx:cut_at].strip()
    
    # Drop the breadcrumb line itself
    lines = [ln for ln in content.split("\n") if not breadcrumb_re.match(ln.strip())]
    
    print(f"[DEBUG] clean_main_content({title!r}) -> {len(content)} chars final")
    return title, content

def save_page(
    output_dir: Path, 
    filename_stem: str,
    title: str,
    source_url: str,
    body: str,
    extra_front_matter: dict[str, str] | None = None,
) -> Path:
    title = unicodedata.normalize("NFC", title)
    body = unicodedata.normalize("NFC", body)
    
    fields = {"title": title, "source_url": source_url, "scraped_date": date.today().isoformat()}
    fields.update(extra_front_matter or {})
    front_matter = "---\n" + "".join(f"{key}: {json.dumps(value)}\n" for key, value in fields.items()) + "---\n\n"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{filename_stem}.md"
    out_path.write_text(front_matter + body, encoding="utf-8")
    print(f"[DEBUG] save_page() -> {out_path}")
    return out_path