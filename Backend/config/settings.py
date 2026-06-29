"""
Central configuration — all env vars and constants live here.
"""
import os
import time
import random
import tempfile
import threading
from dotenv import load_dotenv

load_dotenv()

# ── API keys ────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")

# ── LLM ─────────────────────────────────────────────────────────────────────
# Fast model: 15 RPM free-tier, supports vision — used for agent reasoning + vision extraction
LLM_MODEL_FAST  = "gemini-3.5-flash"
# Smart model: used for pairing + merge. 2.5-flash has 250 RPD vs 100 RPD for pro,
# 10 RPM vs 5 RPM, and is near-pro quality for structured matching/extraction tasks.
LLM_MODEL_SMART = "gemini-2.5-flash"
LLM_MODEL       = LLM_MODEL_FAST   # backwards-compatible alias
LLM_TEMPERATURE = 0.1

# ── Response text extractor ──────────────────────────────────────────────────
def extract_text(response) -> str:
    """
    Gemini models with thinking enabled return content as a list of typed
    blocks, e.g. [{"type": "thinking", "thinking": "..."}, {"type": "text",
    "text": "..."}].  Plain models return a str.  This handles both.
    """
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif "text" in block and block.get("type") != "thinking":
                    parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


# ── Retry helper ─────────────────────────────────────────────────────────────
def invoke_with_retry(llm, *args, **kwargs):
    """Calls llm.invoke() with exponential backoff on 429 RESOURCE_EXHAUSTED or 504 DEADLINE_EXCEEDED."""
    for attempt in range(5):
        try:
            return llm.invoke(*args, **kwargs)
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err \
                    or "504" in err or "DEADLINE_EXCEEDED" in err:
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"  [retry] transient error — waiting {wait:.1f}s (attempt {attempt + 1}/5): {err[:80]}")
                time.sleep(wait)
            else:
                raise
    return llm.invoke(*args, **kwargs)  # final attempt — let it raise


def invoke_with_retry_slow(llm, *args, **kwargs):
    """
    Calls llm.invoke() with a longer exponential backoff suitable for low-RPM
    models (e.g. gemini-2.5-flash at 10 RPM = 6 seconds between calls).

    Waits 15s, 30s, 60s, 120s, 240s — total ~7.5 minutes across all retries.
    This ensures the 60-second RPM window resets before each attempt.
    Handles both 429 RESOURCE_EXHAUSTED and 504 DEADLINE_EXCEEDED.
    """
    for attempt in range(5):
        try:
            return llm.invoke(*args, **kwargs)
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err \
                    or "504" in err or "DEADLINE_EXCEEDED" in err:
                wait = (15 * (2 ** attempt)) + random.uniform(0, 2)
                print(f"  [retry-slow] transient error — waiting {wait:.1f}s (attempt {attempt + 1}/5): {err[:80]}")
                time.sleep(wait)
            else:
                raise
    return llm.invoke(*args, **kwargs)  # final attempt — let it raise

# ── Paths ────────────────────────────────────────────────────────────────────
TMP_DIR = os.environ.get("TMP_DIR", os.path.join(tempfile.gettempdir(), "past_papers"))
os.makedirs(TMP_DIR, exist_ok=True)

# ── Per-run working directory ────────────────────────────────────────────────
# Each pipeline run gets its own subfolder under TMP_DIR so that concurrent runs
# (e.g. two users triggering a paper at the same time) never read or delete each
# other's image files. Stored thread-local because the API runs every job in its
# own thread, and all image I/O happens synchronously within that thread.
_run_ctx = threading.local()


def set_run_dir(path: str) -> str:
    """Set this thread's pipeline working directory and ensure it exists."""
    _run_ctx.dir = path
    os.makedirs(path, exist_ok=True)
    return path


def get_run_dir() -> str:
    """Return this thread's working directory, falling back to TMP_DIR if unset."""
    return getattr(_run_ctx, "dir", None) or TMP_DIR


def clear_run_dir() -> None:
    """Forget this thread's working directory (does not delete any files)."""
    _run_ctx.dir = None

# ── Columns ──────────────────────────────────────────────────────────────────
HTML_COLUMNS = [
    "paper", "board", "level", "subject",
    "question_number", "question_text",
    "marks", "answer", "mark_breakdown", "additional_guidance",
    "diagram",                          # ← cropped diagram image column for HTML output
]

