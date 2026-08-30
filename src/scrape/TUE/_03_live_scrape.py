# Live scrape the first admission and enrolment page due to large number of entries

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _01_scrape_tue_roadmap import (
    BASE_ROADMAP_URL,
    OUTPUT_DIR,
    RoadmapTarget,
    clean_main_content,
    discover_select_options,
    fetch,
    verify_country_slugs,
    verify_program_slugs,
)
from core import save_page, slugify

SRC_DIR = Path(__file__).resolve.parents[2]

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
    
from rag.build_index import upsert_document

PROGRAM_TYPES = {"Bachelor program": "bachelor-1", "Master program": "master-program"}

def list_program_types() -> dict[str, str]:
    return dict(PROGRAM_TYPES)

def list_program_and_country_options(program_type_slug: str):
    """
    Fetch the roadmap page for one program type and return the options for its 'program' and 'country' selects
    """
    url = f"{BASE_ROADMAP_URL}/{program_type_slug}"
    html = fetch(url)
    fields = discover_select_options(html)
    return fields.get("program", []), fields.get("country": [])
