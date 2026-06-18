
import json
import os
import re
import requests
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from config.settings import (
    SERPER_NUM_PER_PAGE,
    LLM_MODEL_FAST,
    LLM_TEMPERATURE,
    invoke_with_retry,
    extract_text,
)

_llm = ChatGoogleGenerativeAI(model=LLM_MODEL_FAST, temperature=LLM_TEMPERATURE)


# ─────────────────────────────────────────────────────────────────────────────
# Tool 1 — extract_entities
# ─────────────────────────────────────────────────────────────────────────────

@tool
def extract_entities(user_query: str) -> str:
    """Extracts board, level, subject, and year from a user query."""
    
    prompt = f"""You are an exam-paper metadata extractor.
Extract the following four fields from the user query below.
Return ONLY a raw JSON object — no markdown, no explanation, no backticks.

Fields:
  board   — exam board (e.g. "Cambridge", "Edexcel", "AQA", "OCR", "IB")
  level   — qualification level (e.g. "A Level", "IGCSE", "GCSE", "AS Level")
  subject — subject name (e.g. "Physics", "Mathematics", "Biology")
  year    — exam year (e.g. "2023", "2022") — empty string if not specified

User query: {user_query}

JSON:"""

    response = invoke_with_retry(_llm, prompt)
    raw = extract_text(response).strip()

    # Defensive parse — strip accidental markdown fences
    raw = re.sub(r"```[a-z]*", "", raw).strip("` \n")

    try:
        parsed = json.loads(raw)
        # Normalise keys to lowercase stripped strings
        result = {
            "board":   str(parsed.get("board",   "")).strip(),
            "level":   str(parsed.get("level",   "")).strip(),
            "subject": str(parsed.get("subject", "")).strip(),
            "year":    str(parsed.get("year",    "")).strip(),
        }
    except json.JSONDecodeError:
        # Fallback — return blanks so the agent can decide what to do
        result = {"board": "", "level": "", "subject": "", "year": ""}

    return json.dumps(result)


# ─────────────────────────────────────────────────────────────────────────────
# Tool 2 — build_search_queries
# ─────────────────────────────────────────────────────────────────────────────

@tool
def build_search_queries(board: str, level: str, subject: str, year: str) -> str:
    """
    Constructs Google-style PDF search queries for both QP and MS from exam metadata.

    Args:
        board:   Exam board (e.g. "Edexcel", "AQA", "Cambridge").
        level:   Qualification level (e.g. "A Level", "GCSE").
        subject: Subject name (e.g. "Physics", "Mathematics").
        year:    Exam year (e.g. "2023") — empty string if unknown.

    Returns JSON string:
        {"qp_query": str, "ms_query": str}
    """
    # Build a clean base: board + level + subject + year (omit blanks)
    parts = [p for p in [board, level, subject, year] if p]
    base = " ".join(parts)

    qp_query = f'{base} "question paper" filetype:pdf'
    ms_query = f'{base} "mark scheme" filetype:pdf'

    return json.dumps({"qp_query": qp_query, "ms_query": ms_query})


# ─────────────────────────────────────────────────────────────────────────────
# Tool 3 — serp-search
# ─────────────────────────────────────────────────────────────────────────────

@tool
def serper_search(query: str, page: int = 1) -> str:
    """
    Executes a Google search via SerpAPI and returns organic results as a tagged list.

    Args:
        query: The search query string (e.g. 'Edexcel A Level Physics 2023 "question paper" filetype:pdf').
        page:  1-based page number for paginated results. Defaults to 1.

    Returns JSON string:
        [{"title": str, "url": str, "snippet": str}, ...]
        On error: {"error": str, "results": []}
    """
    from serpapi import GoogleSearch

    # agent1_tools.py — in serper_search tool
    params = {
        "q":       query,
        "api_key": os.getenv("SERPAPI_KEY"),  
        "engine":  "google",
        "num":     SERPER_NUM_PER_PAGE,
        "start":   (page - 1) * SERPER_NUM_PER_PAGE,
    }

    try:
        results = GoogleSearch(params).get_dict()
    except Exception as exc:
        return json.dumps({"error": str(exc), "results": []})

    organic = results.get("organic_results", [])
    items = [
        {
            "title":   r.get("title", ""),
            "url":     r.get("link", ""),
            "snippet": r.get("snippet", ""),
        }
        for r in organic
        if r.get("link")
    ]
    return json.dumps(items)


# ─────────────────────────────────────────────────────────────────────────────
# Tool 3a — perplexity_search
# ─────────────────────────────────────────────────────────────────────────────

@tool



def perplexity_search(query: str, page: int = 1) -> str:
    """
    Searches for past exam paper PDF links using the Perplexity online LLM API.
    Falls back to empty list if PERPLEXITY_API_KEY is not set or response cannot be parsed.

    Args:
        query: The search query string describing the exam paper to find.
        page:  Pagination hint passed to the query (not natively supported by Perplexity).

    Returns JSON string:
        [{"title": str, "url": str}, ...]
        On error: {"error": str, "results": []}
    """
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        return json.dumps({"error": "PERPLEXITY_API_KEY not set", "results": []})
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": "pplx-7b-online",
        "messages": [
            {
                "role": "user",
                "content": f"Search for PDF links related to: {query}. Return only URLs and titles in JSON format."
            }
        ],
        "temperature": 0.7,
        "max_tokens": 1000,
    }
    
    try:
        response = requests.post(
            "https://api.perplexity.ai/chat/completions",
            json=payload,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        # Parse Perplexity response
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        # Try to extract JSON from response
        try:
            items = json.loads(content)
            if isinstance(items, list):
                return json.dumps(items)
        except json.JSONDecodeError:
            pass
        
        # Fallback: return empty if parsing fails
        return json.dumps([])
        
    except Exception as exc:
        return json.dumps({"error": str(exc), "results": []})


# ─────────────────────────────────────────────────────────────────────────────
# Tool 3b — gemini_search
# ─────────────────────────────────────────────────────────────────────────────

@tool
def gemini_search(query: str, page: int = 1) -> str:
    """
    Prompts the Gemini LLM to surface past exam paper URLs matching the query.
    Used as a fallback search engine when SerpAPI and Perplexity are unavailable.
    Results depend on Gemini's training knowledge — no live web access.

    Args:
        query: The search query string describing the exam paper to find.
        page:  Unused — included for interface parity with serper_search and perplexity_search.

    Returns JSON string:
        [{"title": str, "url": str, "snippet": str}, ...]
        On error: {"error": str, "results": []}
    """
    prompt = f"""Search the web for past exam papers matching: {query}

Return results as a JSON array with this structure:
[{{"title": "...", "url": "...", "snippet": "..."}}]

Return ONLY valid JSON, no markdown or explanation."""

    try:
        response = invoke_with_retry(_llm, prompt)
        content = extract_text(response).strip()
        content = re.sub(r"```[a-z]*", "", content).strip("` \n")
        items = json.loads(content)
        if isinstance(items, list):
            return json.dumps(items)
        return json.dumps([])
    except Exception as exc:
        return json.dumps({"error": str(exc), "results": []})


# ─────────────────────────────────────────────────────────────────────────────
# Tool 4 — tag_search_result
# ─────────────────────────────────────────────────────────────────────────────


_QP_SIGNALS = re.compile(
    r"\b(question\s*paper|qp|exam\s*paper|past\s*paper|_qp_|-qp-|qp\.pdf)\b",
    re.IGNORECASE,
)
_MS_SIGNALS = re.compile(
    r"\b(mark\s*scheme|ms|marking\s*scheme|_ms_|-ms-|ms\.pdf|markscheme)\b",
    re.IGNORECASE,
)

# URL-based signals — filename often more reliable than title
_URL_QP = re.compile(r"[-_]qp[-_.]", re.IGNORECASE)
_URL_MS = re.compile(r"[-_]ms[-_.]", re.IGNORECASE)

@tool
def tag_search_result(title: str, url: str, board: str = "", level: str = "", subject: str = "", year: str = "") -> str:
    """
    Labels a result as QP, MS, or discard.
    Uses title, URL, and known metadata to filter irrelevant results.
    """
    combined_title = title.lower()
    combined_url   = url.lower()
    # URL path-based tagging — more reliable than title for structured sites
    url_path = combined_url.split("?")[0]  # strip query params
    path_segments = url_path.replace("-", "/").replace("_", "/").split("/")

    if "ms" in path_segments or "mark-scheme" in path_segments:
        return json.dumps({"tag": "MS", "title": title, "url": url})
    if "qp" in path_segments or "question-paper" in path_segments:
        return json.dumps({"tag": "QP", "title": title, "url": url})
    # ── Reject wrong year if year is known ───────────────────────────
    if year:
        year_short = year[-2:]  # "2023" → "23"
        has_year = (
            year in combined_title or
            year in combined_url or
            year_short in combined_url  # handles JUN23, NOV23
        )
        # Check for explicitly wrong years
        all_years = re.findall(r"20\d{2}|[a-z]{2,3}\d{2}", combined_url + " " + combined_title)
        wrong_year = any(
            y not in [year, year_short, f"jun{year_short}", f"nov{year_short}", f"jan{year_short}"]
            and re.match(r"20\d{2}|\w+\d{2}", y)
            for y in all_years
        )
        if wrong_year and not has_year:
            return json.dumps({"tag": "discard", "title": title, "url": url})

    # ── Reject wrong subject if subject is known ──────────────────────
    if subject:
        subject_lower = subject.lower()
        # Map common subjects to their codes/keywords
        subject_keywords = {
            "mathematics": ["math", "maths", "8300", "1ma1", "9ma0"],
            "biology":     ["biology", "8461", "bio"],
            "chemistry":   ["chemistry", "8462", "chem"],
            "physics":     ["physics", "8463", "phy"],
            "english":     ["english", "8700", "8702"],
            "economics":   ["economics", "9ec0", "7136"],
        }
        # Get keywords for the requested subject
        valid_keywords = subject_keywords.get(subject_lower, [subject_lower])
        # Get keywords for ALL other subjects to detect mismatches
        wrong_keywords = []
        for subj, kws in subject_keywords.items():
            if subj != subject_lower:
                wrong_keywords.extend(kws)

        has_wrong_subject = any(kw in combined_title for kw in wrong_keywords
                                if kw not in valid_keywords)
        if has_wrong_subject:
            return json.dumps({"tag": "discard", "title": title, "url": url})

    # ── Reject unofficial domains ─────────────────────────────────────
    reject_domains = ["weebly.com", "scribd.com", "slideshare.net", "academia.edu"]
    if any(d in combined_url for d in reject_domains):
        return json.dumps({"tag": "discard", "title": title, "url": url})

    # ── QP / MS signal detection ──────────────────────────────────────
    has_qp = bool(_QP_SIGNALS.search(combined_title)) or bool(_URL_QP.search(combined_url))
    has_ms = bool(_MS_SIGNALS.search(combined_title)) or bool(_URL_MS.search(combined_url))

    if has_qp and not has_ms:
        tag = "QP"
    elif has_ms and not has_qp:
        tag = "MS"
    else:
        tag = "discard"

    return json.dumps({"tag": tag, "title": title, "url": url})