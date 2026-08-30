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

SRC_DIR = Path(__file__).resolve().parents[2]

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
    return fields.get("program", []), fields.get("country", [])

def _persisted_scraped_page(target: RoadmapTarget, title: str, body: str) -> None:
    """
    Save the scraped page and index it into the vector store
    """
    frame = slugify(f"{target.program_type_slug}-{target.program_slug}-{target.country_slug}")
    extra_front_matter = {
        "program_type": target.program_type_label,
        "program": target.program_label,
        "country": target.country_label,
    }
    try:
        save_page(OUTPUT_DIR, fname, title, target.url, body, extra_front_matter=extra_front_matter)
        upsert_document(
            source=f"{fname}.md",
            title=title,
            source_url=target.url,
            content=body,
            extra_metadata=extra_front_matter,
        )
    except Exception as e:
        print(f"[live scrape] WARNING: scraped {target.url!r} OK but failed to persist it for future retrieval: {e}")
        
def scrape_selection(
    program_type_label: str,
    program_type_slug: str,
    program_label: str,
    country_code: str,
    country_label_by_code: dict[str, str],
) -> tuple[str, str, str]:
    """
    Resolve the working slugs for one program + one country, fetch the final page, save and index for future retrieval
    """
    verified_programs = verify_program_slugs(
        program_types={program_type_label: program_type_slug},
        programs_by_type={program_type_slug: [("", program_label)]},
        country_label_by_code=country_label_by_code,
    )
    program_slug = verified_programs.get((program_type_slug, program_label))
    
    if not program_slug:
        raise RuntimeError(
            f"Could not resolve a working URL slug for program {program_label!r} under {program_type_label!r}"
        )
        
    verified_countries = verify_country_slugs(
        codes_to_use=[country_code],
        country_label_by_code=country_label_by_code,
        sample_type_slug=program_type_slug,
        sample_program_slug=program_slug,
    )
    working_country = verified_countries.get(country_code)
    if not working_country:
        raise RuntimeError(f"Could not resolve a working URL slug for country code {country_code!r}.")
    country_label, country_slug = working_country
    
    target = RoadmapTarget(
        program_type_label=program_type_label,
        program_type_slug=program_type_slug,
        program_label=program_label,
        program_slug=program_slug,
        country_label=country_label,
        country_slug=country_slug,
    )
    
    html = fetch(target.url)
    title, body = clean_main_content(html)
    _persisted_scraped_page(target, title, body)
    return title, target.url, body