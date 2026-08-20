import json
import re
import time
import random
from dataclasses import dataclass
from pathlib import Path
from itertools import product

import pycountry
import requests
from bs4 import BeautifulSoup

from core import (
    REQUEST_HEADERS,
    MIN_DELAY_SECONDS,
    MAX_DELAY_SECONDS,
    fetch,
    slugify,
    save_page,
)
from core import clean_main_content as _clean_main_content

BASE_ROADMAP_URL = (
    "https://www.tue.nl/en/education/become-a-tue-student"
    "/admission-and-enrollment/programtype"
)

COUNTRY_ENGLISH_SLUGS: dict[str, str] = json.loads(
    Path("data/country_code_slugs_en.json").read_text(encoding="utf-8")
)

COUNTRY_DUTCH_SLUGS: dict[str, str] = json.loads(
    Path("data/country_code_slugs_nl.json").read_text(encoding="utf-8")
)

OUTPUT_DIR = Path("data/TUE/raw")

DRY_RUN = True # Set to True when checking the URL

def discover_select_options(html: str) -> dict[str, list[tuple[str, str]]]:
    """
    Return a dict keyed by field name ('programtype', 'country', 'program') mapping to a list of (value, label) tuples for that <select>'s options.
    Select are identified by the *name* attribute suffix
    """
    soup = BeautifulSoup(html, "html.parser")
    selects = soup.find_all("select")
 
    FIELD_SUFFIXES = {
        "programtype": "[programtype]",
        "country": "[country]",
        "program": "[program]",  # checked after [programtype] since both end differently, safe with endswith
    }
 
    results: dict[str, list[tuple[str, str]]] = {}
    for sel in selects:
        name = sel.get("name", "") or ""
        options = [
            (opt.get("value", "").strip(), opt.get_text(strip=True))
            for opt in sel.find_all("option")
            if opt.get("value")  # skip the blank "Select" placeholder
        ]
        matched_field = next((f for f, suf in FIELD_SUFFIXES.items() if name.endswith(suf)), None)
        if matched_field and options:
            results[matched_field] = options
 
    print(f"[DEBUG] discover_select_options() -> fields={ {k: len(v) for k, v in results.items()} }")
    return results

def discover_roadmap_slugs():
    """
    Fetch one roadmap page per program type and get
    - real program labels
    - real country labels, keyed by ISO code
    """
    program_types = {"Bachelor program": "bachelor-1", "Master program": "master-program"}
 
    programs_by_type = {}
    country_label_by_code = {}
 
    for label, type_slug in program_types.items():
        url = f"{BASE_ROADMAP_URL}/{type_slug}"
        html = fetch(url)
        time.sleep(random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))
 
        fields = discover_select_options(html)
        program_options = fields.get("program", [])
        country_options = fields.get("country", [])
 
        if program_options:
            programs_by_type[type_slug] = program_options
        else:
            print(f"WARNING: expected a 'program' field on {url} "
                  f"but got fields={list(fields.keys())}; inspect manually.")
 
        country_label_by_code.update(dict(country_options))
 
    print(f"[DEBUG] discover_roadmap_slugs() -> "
          f"programs_by_type={ {k: len(v) for k, v in programs_by_type.items()} }, "
          f"countries={len(country_label_by_code)}")
    return program_types, programs_by_type, country_label_by_code

