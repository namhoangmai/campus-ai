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

COUNTRY_DUTCH_SLUGS_FALLBACK: dict[str, str] = json.loads(
    Path("data/country_code_slugs_nl.json").read_text(encoding="utf-8")
)