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

NETHERLANDS_SLUG_FALLBACK = "nederland"

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
    Return a dict keyed by field name ('programtype', 'country', 'program') mapping to a list of 
        (value, label) tuples for that <select>'s options.
    
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

"""
Build the scoped URL lists
"""

@dataclass
class RoadmapTarget:
    program_type_label: str
    program_type_slug: str
    program_label: str
    program_slug: str
    country_label: str
    country_slug: str
    
    @ property
    def url(self) -> str:
        return (
            f"{BASE_ROADMAP_URL}/{self.program_type_slug}"
            f"/program/{self.program_slug}/country/{self.country_slug}"
        )
        
def build_scoped_targets(program_types, programs_by_type, verified_slugs, verified_countries):
    """
    verified_slugs: dict {(type_slug, program_label): working_slug_or_None}, as returned by verify_program_slugs(). 
        Programs with no working slug are skipped entirely.

    verified_countries: dict {iso_code: (working_label, working_slug) or None}, as returned by verify_country_slugs(). 
        Countries with no working slug (neither the Dutch nor the English spelling resolved) are skipped.
    """
    countries_to_use = {}
    for code, working in verified_countries.items():
        if not working:
            print(f"WARNING: country code '{code}' has no working slug (checked EN and NL spellings), skipping")
            continue
        label, slug = working
        countries_to_use[label] = slug

    targets = []
    skipped = 0
    for pt_label, pt_slug in program_types.items():
        for _raw_value, prog_label in programs_by_type.get(pt_slug, []):
            prog_slug = verified_slugs.get((pt_slug, prog_label))
            if not prog_slug:
                skipped += 1
                continue
            for country_label, country_slug in countries_to_use.items():
                targets.append(
                    RoadmapTarget(
                        program_type_label=pt_label,
                        program_type_slug=pt_slug,
                        program_label=prog_label,
                        program_slug=prog_slug,
                        country_label=country_label,
                        country_slug=country_slug,
                    )
                )
    print(f"[DEBUG] build_scoped_targets() -> {len(targets)} target(s), {skipped} program(s) skipped (unverified)")
    return targets

def verify_program_slugs(program_types, programs_by_type, country_label_by_code):
    """
    HEAD-checks every unique (program_type, program_slug) guess against a known-good country (Netherlands) BEFORE running the full scrape.
    Catch slugify() guesses that don't match TU/e's real slug (e.g. a program needing a "-2" collision suffix) cheaply -- one request per rogram (~38) 
 
    Returns a dict {(type_slug, program_label): working_slug_or_None}.
    """

    discovered_nl_slug = slugify(country_label_by_code.get("NL", "Nederland"))
    netherlands_slug_candidates = list(dict.fromkeys([discovered_nl_slug, NETHERLANDS_SLUG_FALLBACK]))
    print(f"[DEBUG] verify_program_slugs() -> checking each program slug guess "
          f"against country in {netherlands_slug_candidates}...")
    results = {}
    for pt_label, pt_slug in program_types.items():
        for _raw_value, prog_label in programs_by_type.get(pt_slug, []):
            base_slug = slugify(prog_label)
            working_slug = None
            
            for candidate in [base_slug] + [f"{base_slug}-{n}" for n in (1, 2, 3)]:
                for netherlands_slug in netherlands_slug_candidates:
                    url = (
                        f"{BASE_ROADMAP_URL}/{pt_slug}/program/{candidate}"
                        f"/country/{netherlands_slug}"
                    )
                    try:
                        resp = requests.head(url, headers=REQUEST_HEADERS, timeout=15, allow_redirects=True)
                        if resp.status_code < 400:
                            working_slug = candidate
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))
                if working_slug:
                    break
            results[(pt_slug, prog_label)] = working_slug
            status = working_slug if working_slug else "NO WORKING SLUG FOUND -- needs manual check"
            print(f"[DEBUG] verify_program_slugs() {pt_slug}/{prog_label!r}: {status}")
    return results

def verify_country_slugs(codes_to_use, country_label_by_code, sample_type_slug, sample_program_slug):
    """
    HEAD-checks the pre-resolved English slug and the Dutch dropdown label for each country code against a single known-good program URL, 
        since TU/e's real slug is Dutch for some countries and English for others

    Returns a dict {iso_code: (working_label, working_slug) or None}.
    """
    print(f"[DEBUG] verify_country_slugs() -> checking each country slug guess "
          f"against {sample_type_slug}/program/{sample_program_slug}...")
    results = {}
    for code in codes_to_use:
        dutch_label = country_label_by_code.get(code)
        english_slug = COUNTRY_ENGLISH_SLUGS.get(code)

        candidates = []
        seen_slugs = set()
        if english_slug and english_slug not in seen_slugs:
            english_label = english_slug.replace("-", " ").title()
            candidates.append(("english", english_label, english_slug))
            seen_slugs.add(english_slug)
        if dutch_label:
            dutch_slug = slugify(dutch_label)
            if dutch_slug not in seen_slugs:
                candidates.append(("dutch", dutch_label, dutch_slug))
                seen_slugs.add(dutch_slug)
        if code == "NL" and NETHERLANDS_SLUG_FALLBACK not in seen_slugs:
            candidates.append(("nl-fallback", "Nederland", NETHERLANDS_SLUG_FALLBACK))

        static_dutch_slug = COUNTRY_DUTCH_SLUGS.get(code)
        if static_dutch_slug and static_dutch_slug not in seen_slugs:
            static_label = dutch_label or static_dutch_slug.replace("-", " ").title()
            candidates.append(("dutch-static-fallback", static_label, static_dutch_slug))
            seen_slugs.add(static_dutch_slug)

        if not candidates:
            print(f"[DEBUG] verify_country_slugs() {code}: no Dutch or English label available, skipping")
            results[code] = None
            continue

        working = None
        for source, label, slug in candidates:
            url = (
                f"{BASE_ROADMAP_URL}/{sample_type_slug}/program/{sample_program_slug}"
                f"/country/{slug}"
            )
            try:
                resp = requests.head(url, headers=REQUEST_HEADERS, timeout=15, allow_redirects=True)
                if resp.status_code < 400:
                    working = (label, slug)
                    print(f"[DEBUG] verify_country_slugs() {code}: {source} slug {slug!r} works")
                    break
                else:
                    print(f"[DEBUG] verify_country_slugs() {code}: {source} slug {slug!r} "
                          f"-> status={resp.status_code}")
            except requests.RequestException as e:
                print(f"[DEBUG] verify_country_slugs() {code}: {source} slug {slug!r} -> error {e}")
            time.sleep(random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))

        results[code] = working
        if not working:
            print(f"[DEBUG] verify_country_slugs() {code}: NO WORKING SLUG FOUND -- needs manual check")
    return results