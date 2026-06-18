"""
AgentState — the LangGraph state schema.

Every field is a plain JSON-serialisable type so agents can pass data as
JSON strings and the graph can inspect / route on primitive values.
"""
from typing import Optional
from typing_extensions import TypedDict


class AgentState(TypedDict, total=False):
    # ── User input ────────────────────────────────────────────────────────────
    user_query: str                  

    # ── Search tool selection ─────────────────────────────────────────────────
    search_tool: str                 

    # ── Agent 1 outputs ───────────────────────────────────────────────────────
    board: str
    level: str
    subject: str
    year: str
    qp_query: str                    
    ms_query: str                    
    tagged_results_json: str         # JSON list of {title, url, tag}

    # ── Agent 2 outputs ───────────────────────────────────────────────────────
    pairs_json: str                  # JSON list of {qp_title, qp_url, ms_title, ms_url}

    # ── Human interrupts ──────────────────────────────────────────────────────
    include_images: Optional[bool]   

    # ── Agent 3 outputs ───────────────────────────────────────────────────────
    extracted_rows_json: str         
    diagram_map_json: str            

    # ── Control flow ──────────────────────────────────────────────────────────
    error_message: Optional[str]     
    retry_count: int #ss                 
    status: str                      