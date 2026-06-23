"""
AgentState — the LangGraph state schema.

Every field is a plain JSON-serialisable type so agents can pass data as
JSON strings and the graph can inspect / route on primitive values.
"""
from typing import Optional
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    # ── User input ────────────────────────────────────────────────────────────
    qp_url: str
    ms_url: str
    qp_metadata_raw: str
    ms_metadata_raw: str

    # ── Parsed metadata ───────────────────────────────────────────────────────
    board: str
    level: str
    subject: str
    year: str
    paper_code: str          # e.g. "1H", "2F"
    paper_number: str        # numeric part only, e.g. "1", "2"
    tier: str                # "Foundation" | "Higher" | ""

    # ── Agent 3 inputs ────────────────────────────────────────────────────────
    pairs_json: str          # JSON list of {qp_title, qp_url, ms_title, ms_url}

    # ── Processing options ────────────────────────────────────────────────────
    include_images: Optional[bool]

    # ── Agent 3 outputs ───────────────────────────────────────────────────────
    extracted_rows_json: str
    diagram_map_json: str

    # ── Control flow ──────────────────────────────────────────────────────────
    error_message: Optional[str]
    retry_count: int
    status: str

    # ── DB output ─────────────────────────────────────────────────────────────
    paper_id: Optional[int]     # set by node_save_to_db after commit
