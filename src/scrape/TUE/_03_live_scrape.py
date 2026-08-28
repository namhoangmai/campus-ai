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

