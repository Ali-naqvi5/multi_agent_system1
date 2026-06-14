# Past Paper Pipeline
A multi-agent LangGraph + LangChain system that searches, pairs, downloads, and vision-extracts UK past exam papers (Question Papers + Mark Schemes) across major exam boards (AQA, OCR, Edexcel, CIE, WJEC) for GCSE, A-Level, and AS-Level.

## Architecture
User Query
    │
    ▼
[Agent 1] Query Parser + Search
    │  extract_entities → build_search_queries → search (×N) → tag_search_result (×N)
    │
    ▼
[Agent 2] Pairing
    │  LLM reasons over full raw result pool → pairs QP ↔ MS
    │  (uses session aliases, tier matching, paper code knowledge)
    │
    └── on zero pairs → loop back to query_search (retry)
    │
    ▼
[Human Interrupt] ── "Include images? text-only / image-inclusive"
    │
    ▼
[Agent 3] Downloader + Extractor (ReAct agent)
    │  download_pdf → render_pdf_pages (PyMuPDF, 150 DPI PNG)
    │  extract_page_text (×all pages)
    │  if image-inclusive: extract_page_vision (Gemini Vision —
    │     diagram/figure/table detection + bbox)
    │  crop_and_save_diagrams → merge_qp_ms_rows
    │
    └── on total failure → loop back to Agent 1 (max 3 retries)
    │
    ▼
[node_feeder] (hardcoded routing node)
    │  text-only        → append_to_google_sheets
    │  image-inclusive  → write_html_json (LaTeX/MathJax rendering)
    ▼
  END


## Stack

Orchestration: LangGraph + LangChain
LLM: Gemini 3.5 Pro
Search: SerpAPI
PDF rendering: PyMuPDF → PNG at 150 DPI
Vision extraction: Gemini Vision — bounding boxes in [ymin, xmin, ymax, xmax] order, normalized 0–1000 relative to page image dimensions
Output: Google Sheets (text-only) or HTML + JSON with MathJax (image-inclusive)

## Setup
1. Install dependencies
bashpip install -r requirements.txt
2. Configure environment
bashcp .env.example .env
### Edit .env with your keys
Required variables:

SERPER_API_KEY — from serper.dev
GEMINI_API_KEY — Gemini 2.5 Pro access required
GOOGLE_SERVICE_ACCOUNT_JSON — absolute path to your service account JSON (for Sheets output)
GOOGLE_SHEET_ID — ID from your Sheet URL

3. Google Sheets setup (text-only runs)

Create a Google Cloud service account with Sheets + Drive API enabled
Download the JSON key file
Share your target Sheet with the service account email (Editor role)
Copy the Sheet ID from its URL: https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit


## Output Schemas
1. Google Sheets columns (text-only)
paper | board | level | subject | question_number | question_text | marks | answer | mark_breakdown | additional_guidance
2. HTML + JSON (image-inclusive)


JSON includes per-question fields above plus:

figure_number, table_number (if applicable)
bbox — [ymin, xmin, ymax, xmax], normalized 0–1000
Cropped diagram image references
LaTeX/MathJax-rendered math content




