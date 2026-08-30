import os
import sys
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

SRC_DIR = REPO_ROOT / "src"
for p in (
    SRC_DIR / "scrape",
    SRC_DIR / "scrape" / "TUE",
    SRC_DIR / "rag",
):
    p = str(p)
    if p not in sys.path:
        sys.path.insert(0, p)
        
os.chdir(REPO_ROOT)

from _03_live_scrape import list_program_and_country_options, list_program_types, scrape_selection
from retriever import retrieve
from answer import generate_answer

app = FastAPI(title="Campus-AI API")

default_origins = "http://localhost:3000,http://127.0.0.1:3000"
allowed_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allowed_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

