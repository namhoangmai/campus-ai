import time
import random
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import fetch, slugify, save_page, MIN_DELAY_SECONDS, MAX_DELAY_SECONDS
from _01_scrape_tue_roadmap import clean_main_content

OUTPUT_DIR = Path("data/TUE/raw")

# Static page URLs to scrape
STATIC_PAGES = [
    "https://www.tue.nl/en/education/become-a-tue-student/visa-residence-permit",
    "https://www.tue.nl/en/education/become-a-tue-student/tuition-fees-and-other-study-costs",
    "https://www.tue.nl/en/education/become-a-tue-student/tuition-fees-and-other-study-costs/application-fee",
    "https://www.tue.nl/en/education/become-a-tue-student/tuition-fees-and-other-study-costs/tuition-fee",
    "https://www.tue.nl/en/education/become-a-tue-student/tuition-fees-and-other-study-costs/tuition-fee/payment-options",
    "https://www.tue.nl/en/education/become-a-tue-student/tuition-fees-and-other-study-costs/tuition-fee/refunding-tuition-fees",
    "https://www.tue.nl/en/education/become-a-tue-student/tuition-fees-and-other-study-costs/tuition-fee/payment-exemption",
    "https://www.tue.nl/en/education/become-a-tue-student/scholarships-and-grants",
    "https://www.tue.nl/en/education/become-a-tue-student/scholarships-and-grants/tue-scholarship-for-excellence-shaping-the-future-of-microchip-innovation",
    "https://www.tue.nl/en/education/become-a-tue-student/housing",
]

DRY_RUN = True # True to check the page first

def save_static_page(url: str, page_html: str) -> Path:
    title, body = clean_main_content(page_html)
    return save_page(OUTPUT_DIR, slugify(title), title, url, body)

def main():
    print(f"[DEBUG] main() -> DRY_RUN={DRY_RUN}, {len(STATIC_PAGES)} static page(s) queued")
    
    if DRY_RUN:
        print("DRY_RUN=True -- printing the page list and stopping")
        for url in STATIC_PAGES:
            print(url)
        return
    
    for i, url in enumerate(STATIC_PAGES, 1):
        try:
            page_html = fetch(url)
            path = save_static_page(url, page_html)
            print(f"[{i}/{len(STATIC_PAGES)}] saved {path}")
            
        except requests.HTTPError as e:
            print(f"[{i}/{len(STATIC_PAGES)}] FAILED {url}: {e}")
        time.sleep(random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS))

if __name__ == "__main__":
    main()