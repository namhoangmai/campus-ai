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

# Schemas

class ProgramOptionsResponse(BaseModel):
    programs: list[tuple[str, str]]
    countries: list[tuple[str, str]]
    
class ScrapeRequest(BaseModel):
    program_type_label: str
    program_type_slug: str
    program_label: str
    country_code: str
    country_label_by_code: dict[str, str]
    
class LivePage(BaseModel):
    title: str
    url: str
    body: str
    
class ScrapeResponse(BaseModel):
    title: str
    url: str
    body: str
    
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    
class ChatRequest(BaseModel):
    question: str
    chat_history: list[ChatMessage] = []
    live_page: Optional[LivePage] = None
    
class Source(BaseModel):
    title: str
    url: str
    
class ChatResponse(BaseModel):
    reply: str
    sources: list[Source]
    
# Routes

@app.get("/api/health")
def health():
    return{"status": "ok"}

@app.get("/api/program-types")
def program_types() -> dict[str, str]:
    return list_program_types()

@app.get("/api/program-options", response_model=ProgramOptionsResponse)
def program_options(program_type_slug: str):
    try:
        programs, countries = list_program_and_country_options(program_type_slug)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not load options: {e}") from e
    return ProgramOptionsResponse(programs=programs, countries=countries)
    
