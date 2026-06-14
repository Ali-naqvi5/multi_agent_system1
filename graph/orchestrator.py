
from langgraph.types import Command

import json
import re
from typing import Any
from datetime import datetime
import os
from config.settings import TMP_DIR
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt
from agents.agent2_pairing import build_pairing_agent
from graph import state
from graph.state import AgentState
from agents.agent1_query_search import build_query_search_agent
from agents.agent3_downloader_extractor import build_downloader_extractor_agent
from tools.agent4_tools import append_to_google_sheets


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

MAX_RETRIES = 3

def _safe_json(text) -> Any:
    """Extract the first JSON object or array from a possibly-noisy string."""
    # Handle Gemini-style list of content blocks
    if isinstance(text, list):
        text = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in text
        )
    text = text.strip()
    text = re.sub(r"```[a-z]*", "", text).strip("` \n")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for pattern in (r"\{.*\}", r"\[.*\]"):
            m = re.search(pattern, text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Node 0 — Search Tool Selector (NEW)
# ─────────────────────────────────────────────────────────────────────────────

def node_search_tool_selector(state: AgentState) -> AgentState:
    print("\n" + "="*60)
    print("NODE 0: Search Tool Selector")
    print("="*60)

    # Pause and wait for user input via interrupt
    # The value returned here comes from Command(resume=value) in run_pipeline
    user_choice = interrupt(
        {
            "message": (
                "\nSelect search engine:\n"
                "  [1] Serper (default)\n"
                "  [2] Perplexity\n"
                "  [3] Gemini\n"
                "\nType '1', '2', or '3' and press Enter:"
            ),
        }
    )

    # Map the choice to tool name
    tools_map = {
        "1": "serper",
        "2": "perplexity",
        "3": "gemini",
    }
    
    selected_tool = tools_map.get(str(user_choice).strip(), "serper")
    print(f"  Selected: {selected_tool.upper()}")

    # CRITICAL: Match the pattern from node_human_interrupt - unpack state
    return {**state, "search_tool": selected_tool, "status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# Node 1 — Query Search
# ─────────────────────────────────────────────────────────────────────────────

def node_query_search(state: AgentState) -> AgentState:
    print("\n" + "="*60)
    print("NODE 1: Query Parser + Search Agent")
    print(f"  Tool: {state.get('search_tool', 'serper')}")
    print("="*60)

    agent = build_query_search_agent()
    
    search_tool = state.get("search_tool", "serper")
    # Pass tool selection in message
    message = f"Use search tool: {search_tool}\n\n{state['user_query']}"
    retry_count = state.get("retry_count", 0)
    if retry_count > 0:
        wait = 20
        print(f"\n   Retry #{retry_count} — waiting {wait}s to avoid rate limit...")
        import time
        time.sleep(wait)
    while True:
        result = agent.invoke({"messages": [("user", message)]})
        raw_output = result["messages"][-1].content
        parsed = _safe_json(raw_output)

        # Agent 1 signals bad query — re-prompt the user right here
        if "error" in parsed:
            print(f"\n  ⚠️  {parsed['error']}")
            new_query = input("  Please refine your query: ").strip()
            state = {**state, "user_query": new_query}
            message = f"Use search tool: {search_tool}\n\n{new_query}"
            continue

        break  # Agent 1 accepted the query

    tagged_results = parsed.get("tagged_results", [])
    print(f"  Tagged pool size: {len(tagged_results)}")
    print(f"  QPs found: {sum(1 for r in tagged_results if r.get('tag') == 'QP')}")
    print(f"  MSs found: {sum(1 for r in tagged_results if r.get('tag') == 'MS')}")

    return {
        **state,
        "board":               parsed.get("board", ""),
        "level":               parsed.get("level", ""),
        "subject":             parsed.get("subject", ""),
        "year":                parsed.get("year", ""),
        "qp_query":            parsed.get("qp_query", ""),
        "ms_query":            parsed.get("ms_query", ""),
        "tagged_results_json": json.dumps(tagged_results),
        "status":              "ok",
        "error_message":       None,
    }

# ─────────────────────────────────────────────────────────────────────────────
# Node 2 — Pairing
# ─────────────────────────────────────────────────────────────────────────────
def node_pairing(state: AgentState) -> AgentState:
    print("\n" + "="*60)
    print("NODE 2: Pairing Agent")
    print("="*60)

    agent = build_pairing_agent()

    metadata = json.dumps({
        "board":   state.get("board", ""),
        "level":   state.get("level", ""),
        "subject": state.get("subject", ""),
        "year":    state.get("year", ""),
    })

    tagged_results = json.loads(state.get("tagged_results_json", "[]"))
    qps = [{"title": r["title"], "url": r["url"]} for r in tagged_results if r.get("tag") == "QP"]
    mss = [{"title": r["title"], "url": r["url"]} for r in tagged_results if r.get("tag") == "MS"]

    print(f"  QPs: {len(qps)} | MSs: {len(mss)}")

    if not qps or not mss:
        print("  Insufficient QPs or MSs — skipping.")
        return {**state, "pairs_json": json.dumps([]), "status": "ok"}

    message = (
        f"metadata={metadata}\n\n"
        f"qp_list={json.dumps(qps)}\n\n"
        f"ms_list={json.dumps(mss)}"
    )

    result = agent.invoke({"messages": [("user", message)]})
    raw_output = result["messages"][-1].content
    parsed = _safe_json(raw_output)

    pairs = parsed.get("pairs", [])
    print(f"  Confirmed pairs: {len(pairs)}")
    for p in pairs:
        print(f"    QP: {p.get('qp_title', '?')}")
        print(f"    MS: {p.get('ms_title', '?')}")

    if not pairs:
        return {
        **state,
        "pairs_json": json.dumps([]),
        "retry_count": state.get("retry_count", 0) + 1,
        "status": "ok",
    }

    return {**state, "pairs_json": json.dumps(pairs), "status": "ok"}
# ─────────────────────────────────────────────────────────────────────────────
# Node 3 — Human Interrupt (Images choice)
# ─────────────────────────────────────────────────────────────────────────────

def node_human_interrupt(state: AgentState) -> AgentState:
    print("\n" + "="*60)
    print("NODE 3: Human Interrupt — Image choice")
    print("="*60)

    pairs = json.loads(state.get("pairs_json", "[]"))

    if not pairs:
        print("  No confirmed pairs — skipping interrupt, proceeding to report.")
        return {**state, "include_images": False, "status": "ok"}

    print("\n  Confirmed pairs found:")
    for i, p in enumerate(pairs, 1):
        print(f"    {i}. QP: {p.get('qp_title', 'unknown')}")
        print(f"       MS: {p.get('ms_title', 'unknown')}")

    user_choice = interrupt(
        {
            "message": (
                "\nMatched pairs are ready.\n"
                "Choose output format:\n"
                "  [1] Text only  -> append to Google Sheets\n"
                "  [2] Text + Images -> export to HTML (.html)\n"
                "\nType '1' or '2' and press Enter:"
            ),
            "pairs_count": len(pairs),
        }
    )

    include_images = False
    if str(user_choice).strip() in ("2", "yes", "images", "excel"):
        include_images = True
        print("  User chose: Text + Images -> Excel")
    else:
        print("  User chose: Text only -> Google Sheets")

    return {**state, "include_images": include_images, "status": "ok"}

#_______________________________________________________________________________
#HTML Function 
#_______________________________________________________________________________
def _build_summary_html(tmp_dir: str) -> str:
    """
    Reads all per-pair JSON files from TMP_DIR and writes one elegant HTML file.
    Called right after the Agent 3 loop completes.
    """
    import glob

    # ── Collect all per-pair JSON files ──
    json_files = sorted(glob.glob(os.path.join(tmp_dir, "*.json")))
    if not json_files:
        print("  No JSON files found in TMP_DIR — skipping HTML build.")
        return ""

    all_rows = []
    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                all_rows.extend(data)
        except Exception as e:
            print(f"  Skipping {jf}: {e}")

    if not all_rows:
        print("  No rows found across JSON files — skipping HTML build.")
        return ""

    def _esc(text: str) -> str:
        return (str(text)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))

    def _cell(text: str) -> str:
        # HTML-escape plain text but leave $...$ and $$...$$ spans raw so MathJax renders them.
        parts = re.split(r'(\$\$[\s\S]*?\$\$|\$[^$\n]*?\$)', str(text))
        return "".join(p if p.startswith("$") else _esc(p) for p in parts)

    def _img_tag(path: str) -> str:
        if not path or not os.path.exists(path):
            return "<span style='color:#aaa;'>No diagram</span>"
        # Embed as base64 so HTML is fully self-contained
        import base64
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f'<img src="data:image/png;base64,{b64}" style="max-width:280px;max-height:180px;border:1px solid #ddd;border-radius:4px;">'

    TEXT_COLS = [
        "paper", "board", "level", "subject",
        "question_number", "question_text",
        "marks", "answer", "mark_breakdown", "additional_guidance",
    ]

    # ── Group rows by paper ──
    from collections import defaultdict
    grouped = defaultdict(list)
    for row in all_rows:
        key = row.get("paper", "Unknown Paper")
        grouped[key].append(row)

    # ── Build HTML sections per paper ──
    sections = []
    for paper_name, rows in grouped.items():
        header_cells = "".join(f"<th>{_esc(c)}</th>" for c in TEXT_COLS) + "<th>Diagram</th>"

        body_rows = []
        for row in rows:
            cells = ""
            for col in TEXT_COLS:
                val = str(row.get(col, ""))
                cells += f"<td>{_cell(val)}</td>"
            cells += f"<td>{_img_tag(row.get('diagram_path', ''))}</td>"
            body_rows.append(f"<tr>{cells}</tr>")

        sections.append(f"""
        <div class="paper-section">
            <h2>{_esc(paper_name)}</h2>
            <p class="meta">{len(rows)} question(s)</p>
            <div class="table-wrap">
            <table>
                <thead><tr>{header_cells}</tr></thead>
                <tbody>{"".join(body_rows)}</tbody>
            </table>
            </div>
        </div>
        """)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<script>
MathJax = {{
  tex: {{
    inlineMath: [['$', '$']],
    displayMath: [['$$', '$$']],
    packages: {{'[+]': ['mhchem']}}
  }},
  loader: {{load: ['[tex]/mhchem']}}
}};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<title>Past Papers Export — {timestamp}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
    background: #f0f2f5;
    color: #222;
    padding: 24px;
  }}
  h1 {{
    font-size: 22px;
    color: #1a1a2e;
    margin-bottom: 6px;
  }}
  .subtitle {{
    color: #666;
    font-size: 12px;
    margin-bottom: 28px;
  }}
  .paper-section {{
    background: #fff;
    border-radius: 10px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    margin-bottom: 32px;
    padding: 20px 24px;
  }}
  .paper-section h2 {{
    font-size: 16px;
    color: #2c3e50;
    margin-bottom: 4px;
    border-left: 4px solid #3498db;
    padding-left: 10px;
  }}
  .meta {{
    font-size: 11px;
    color: #999;
    margin-bottom: 14px;
    padding-left: 14px;
  }}
  .table-wrap {{
    overflow-x: auto;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    min-width: 900px;
  }}
  th {{
    background: #2c3e50;
    color: #fff;
    padding: 9px 10px;
    text-align: left;
    font-size: 12px;
    white-space: nowrap;
    position: sticky;
    top: 0;
  }}
  td {{
    border-bottom: 1px solid #eee;
    padding: 8px 10px;
    vertical-align: top;
    line-height: 1.5;
  }}
  tr:hover td {{
    background: #f7faff;
  }}
  td:nth-child(6) {{ max-width: 320px; word-wrap: break-word; }}  /* question_text */
  td:nth-child(8) {{ max-width: 280px; word-wrap: break-word; }}  /* answer */
  .footer {{
    text-align: center;
    color: #bbb;
    font-size: 11px;
    margin-top: 16px;
  }}
</style>
</head>
<body>
<h1>Past Papers Export</h1>
<p class="subtitle">Generated: {timestamp} &nbsp;|&nbsp; Total questions: {len(all_rows)}</p>

{"".join(sections)}

<p class="footer">Auto-generated by Past Papers Pipeline</p>
</body>
</html>"""

    out_path = os.path.join(tmp_dir, f"summary_{timestamp}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Summary HTML written: {out_path}")
    return out_path
# ─────────────────────────────────────────────────────────────────────────────
# Node 4 — Downloader + Extractor
# ─────────────────────────────────────────────────────────────────────────────

def node_downloader_extractor(state: AgentState) -> AgentState:
    print("\n" + "="*60)
    print("NODE 4: Downloader + Extractor Agent")
    print(f"  include_images = {state.get('include_images')}")
    print("="*60)

    metadata = json.dumps({
        "paper":   f"{state.get('board','')} {state.get('level','')} {state.get('subject','')} {state.get('year','')}".strip(),
        "board":   state.get("board", ""),
        "level":   state.get("level", ""),
        "subject": state.get("subject", ""),
    })

    pairs = json.loads(state.get("pairs_json", "[]"))
    include_images = state.get("include_images", False)

    all_rows = []
    all_diagram_map = {}
    all_failed_pairs = []

    

    for i, pair in enumerate(pairs):
        agent = build_downloader_extractor_agent()
        print(f"\n  Processing pair {i+1}/{len(pairs)}: {pair.get('qp_title', '?')}")

        message = (
            f"include_images={include_images}\n"
            f"paper_number={i+1}\n\n" 
            f"metadata={metadata}\n\n"
            f"{json.dumps([pair])}"
        )

        try:
            result = agent.invoke({"messages": [("user", message)]})
            raw_output = result["messages"][-1].content
            parsed = _safe_json(raw_output)

            rows         = parsed.get("extracted_rows", parsed.get("rows", []))
            diagram_maps = parsed.get("diagram_maps", {})
            # Per-paper map for this pair; fall back to legacy flat key for compatibility
            diagram_map  = diagram_maps.get(str(i + 1), parsed.get("diagram_map", {}))

            all_rows.extend(rows)
            all_diagram_map.update(diagram_map)
            all_failed_pairs.extend(parsed.get("failed_pairs", []))

            print(f"  Pair {i+1} → {len(rows)} questions extracted")

            # ── Write per-pair JSON immediately after each pair ──
            if include_images and rows:
                safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", pair.get("qp_title", f"pair_{i+1}"))[:60]
                timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename   = f"{safe_title}_pair{i+1}_{timestamp}.json"
                out_path   = os.path.join(TMP_DIR, filename)

                enriched_rows = []
                for row in rows:
                    # Use this row's paper_number to pick the right scoped map
                    row_paper_map = diagram_maps.get(str(row.get("paper_number", i + 1)), diagram_map)
                    fig_key = f'fig:{row.get("figure_number", "").strip()}'
                    tbl_key = f'tbl:{row.get("table_number",  "").strip()}'
                    q_key   = f'q:{row.get("question_number", "").strip()}'

                    diagram_path = (
                        row_paper_map.get(fig_key)
                        or row_paper_map.get(tbl_key)
                        or row_paper_map.get(q_key)
                        or ""
                    )
                    enriched_rows.append({**row, "diagram_path": diagram_path})

                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(enriched_rows, f, indent=2, ensure_ascii=False)

                print(f"  Per-pair JSON written: {out_path}")

        except Exception as e:
            print(f"  Pair {i+1} failed with exception: {e}")
            all_failed_pairs.append({
                "qp_url": pair.get("qp_url", "?"),
                "ms_url": pair.get("ms_url", "?"),
                "reason": str(e),
            })

    print(f"\n  Total questions extracted: {len(all_rows)}")

    if all_failed_pairs:
        print(f"  Failed pairs ({len(all_failed_pairs)}):")
        for fp in all_failed_pairs:
            print(f"    QP: {fp.get('qp_url', '?')} — Reason: {fp.get('reason', '?')}")

        retry_count = state.get("retry_count", 0)
        if retry_count < MAX_RETRIES and len(all_rows) == 0:
            print(f"  All pairs failed — triggering retry #{retry_count + 1}")
            return {
                **state,
                "extracted_rows_json": json.dumps([]),
                "error_message":       f"All pairs failed on attempt {retry_count + 1}: {all_failed_pairs}",
                "retry_count":         retry_count + 1,
                "status":              "retry",
            }

    # ── Build summary HTML from all per-pair JSONs ──
    if include_images:
        _build_summary_html(TMP_DIR)

    return {
        **state,
        "extracted_rows_json": json.dumps(all_rows),
        "diagram_map_json":    json.dumps(all_diagram_map),
        "status":              "ok",
        "error_message":       None,
    }
# ─────────────────────────────────────────────────────────────────────────────
# Node 5 — Feeder (Google Sheets)
# ─────────────────────────────────────────────────────────────────────────────

def node_feeder(state: AgentState) -> AgentState:
    print("\n" + "="*60)
    print("NODE 5: Feeder")
    print(f"  Destination: {'HTML' if state.get('include_images') else 'Google Sheets'}")
    print("="*60)

    include_images = state.get("include_images", False)

    if include_images:
        print("  Please Check the generated HTML file in the TMP_DIR for the exported QP,MS and diagrams.")
        return {**state, "status": "done"}

    rows_json = state["extracted_rows_json"]

    raw    = append_to_google_sheets.invoke({"rows_json": rows_json})
    result = json.loads(raw)

    if result.get("success"):
        print(f"  Rows written: {result.get('rows_written') or result.get('rows_appended', '?')}")
        if result.get("path"):
            print(f"  Output: {result.get('path')}")
    else:
        print(f"  Feeder error: {result.get('error', 'unknown')}")

    return {**state, "status": "done"}
# ─────────────────────────────────────────────────────────────────────────────
# Routing logic
# ─────────────────────────────────────────────────────────────────────────────

def route_after_extraction(state: AgentState) -> str:
    if state.get("status") == "retry":
        retry_count = state.get("retry_count", 0)
        if retry_count <= MAX_RETRIES:
            print(f"\n  Routing back to Agent 1 (retry {retry_count}/{MAX_RETRIES})")
            return "query_search"
        else:
            print(f"\n  Max retries ({MAX_RETRIES}) reached — aborting.")
            return END

    rows = json.loads(state.get("extracted_rows_json", "[]"))
    if not rows:
        print("\n  No extracted rows — ending without writing.")
        return END

    return "feeder"


def route_after_pairing(state: AgentState) -> str:
    pairs = json.loads(state.get("pairs_json", "[]"))
    if not pairs:
        retry_count = state.get("retry_count", 0)
        if retry_count < MAX_RETRIES:
            print(f"\n  No pairs found — retrying search (attempt {retry_count + 1}/{MAX_RETRIES})")
            return "query_search"
        print(f"\n  No pairs found after {MAX_RETRIES} retries — ending pipeline.")
        return END
    return "human_interrupt"


# ─────────────────────────────────────────────────────────────────────────────
# Graph assembly (Corrected)
# ─────────────────────────────────────────────────────────────────────────────

def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("search_tool_selector",    node_search_tool_selector)
    builder.add_node("query_search",            node_query_search)
    builder.add_node("pairing",                 node_pairing)
    builder.add_node("human_interrupt",         node_human_interrupt)
    builder.add_node("downloader_extractor",    node_downloader_extractor)
    builder.add_node("feeder",                  node_feeder)

    builder.set_entry_point("search_tool_selector")
    builder.add_edge("search_tool_selector", "query_search")
    builder.add_edge("query_search", "pairing")

    builder.add_conditional_edges(
        "pairing",
        route_after_pairing,
        {"human_interrupt": "human_interrupt", "query_search": "query_search", END: END},
    )

    builder.add_edge("human_interrupt", "downloader_extractor")

    builder.add_conditional_edges(          # ← THIS WAS MISSING
        "downloader_extractor",
        route_after_extraction,
        {"query_search": "query_search", "feeder": "feeder", END: END},
    )

    builder.add_edge("feeder", END)

    memory = MemorySaver()
    graph = builder.compile(checkpointer=memory)

    return graph
# ─────────────────────────────────────────────────────────────────────────────
# Public runner
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(user_query: str, thread_id: str = "default") -> None:
    graph = build_graph()
    config = {"configurable": {"thread_id": thread_id}}
    initial_state: AgentState = {
        "user_query":    user_query,
        "search_tool":   "serper",  # default
        "retry_count":   0,
        "status":        "ok",
        "error_message": None,
        "include_images": None,
    }
    print("\n" + "█"*60)
    print(f"  PIPELINE STARTED: {user_query}")
    print("█"*60)
    
    # Phase 1 — run until first interrupt (search tool selector)
    for event in graph.stream(initial_state, config=config, stream_mode="updates"):
        _print_event(event)
    
    # Check for search tool interrupt
    snapshot = graph.get_state(config)
    if snapshot.next and "search_tool_selector" in snapshot.next:
        while True:
            choice = input("\nPlease Enter: \n1 for Serp:\n2 for Perplexity:\n3 for Gemini: ").strip()
            if choice in ("1", "2", "3"):
                break
            print("  Please enter 1, 2, or 3.")
        tools_map = {"1": "serper", "2": "perplexity", "3": "gemini"}
        selected_tool = tools_map[choice]
        print(f"\n  Selected search tool: {selected_tool.upper()}")
        # Resume with NUMERIC choice (not tool name) — node maps "1"/"2"/"3" to tool name
        for event in graph.stream(
            Command(resume=choice),  # ← Pass "1", "2", or "3" — NOT selected_tool
            config=config,
            stream_mode="updates",
            subgraphs=False,
        ):
            _print_event(event)
    
    # Check for human interrupt (image choice)
    snapshot = graph.get_state(config)
    if snapshot.next and "human_interrupt" in snapshot.next:
        pairs = json.loads(snapshot.values.get("pairs_json", "[]"))
        print(f"\n  PAUSED — {len(pairs)} pair(s) found:")
        for i, p in enumerate(pairs, 1):
            print(f"    {i}. QP: {p.get('qp_title', '?')}")
            print(f"       MS: {p.get('ms_title', '?')}")
        print("\n  Choose output format:")
        print("    [1] Text only     → Google Sheets")
        print("    [2] Text + Images → HTML (.html)")
        while True:
            choice = input("\n  Enter 1 or 2: ").strip()
            if choice in ("1", "2"):
                break
            print("  Please enter 1 or 2.")
        user_input_arg = "excel" if choice == "2" else "sheets"
        # Resume
        for event in graph.stream(
            Command(resume=user_input_arg),
            config=config,
            stream_mode="updates",
            subgraphs=False,
        ):
            _print_event(event)
    
    print("\n" + "█"*60)
    print("  PIPELINE COMPLETE")
    print("█"*60)


def _print_event(event: dict) -> None:
    """Print only meaningful node activity — suppress raw message dumps."""
    for node_name, data in event.items():
        if node_name.startswith("__"):
            continue
        messages = data.get("messages", []) if isinstance(data, dict) else []
        for msg in messages:
            msg_type = type(msg).__name__
            if msg_type == "AIMessage":
                # content may be a list of blocks (Gemini thinking mode) or a plain str
                raw_c = msg.content
                if isinstance(raw_c, list):
                    text_c = "".join(
                        b.get("text", "") if isinstance(b, dict) and b.get("type") == "text"
                        else (b if isinstance(b, str) else "")
                        for b in raw_c
                    )
                else:
                    text_c = str(raw_c) if raw_c else ""
                if text_c.strip():
                    print(f"\n  [{node_name}]  {text_c.strip()}")
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        args_preview = ", ".join(
                            f"{k}={str(v)[:50]}" for k, v in tc["args"].items()
                        )
                        print(f"  [{node_name}] 🔧 {tc['name']}({args_preview})")
            elif msg_type == "ToolMessage":
                raw_tool = msg.content
                content  = raw_tool if isinstance(raw_tool, str) else str(raw_tool)
                content  = content.strip()
                preview  = content[:120] + "..." if len(content) > 120 else content
                print(f"  [{node_name}] {msg.name} → {preview}")








