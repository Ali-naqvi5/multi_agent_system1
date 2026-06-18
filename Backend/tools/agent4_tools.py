import json
import os
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials
from langchain_core.tools import tool

from config.settings import (
    GOOGLE_SERVICE_ACCOUNT_PATH,
    GOOGLE_SHEET_ID,
    SHEETS_COLUMNS,
    
)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_sheets_client() -> gspread.Client:
    creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_PATH, scopes=_SCOPES)
    return gspread.authorize(creds)


def _flatten_mark_breakdown(value) -> str:
    """Converts a list-of-dicts or JSON-array mark_breakdown into pipe-separated plain text."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") or stripped.startswith("{"):
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                try:
                    import ast
                    value = ast.literal_eval(stripped)
                except Exception:
                    return stripped
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                m = item.get("marks", "")
                d = item.get("description", "")
                if m != "":
                    parts.append(f"{m} mark{'s' if m != 1 else ''}: {d}")
                else:
                    parts.append(d)
            else:
                parts.append(str(item))
        return " | ".join(parts)
    return str(value)


# ─────────────────────────────────────────────────────────────────────────────
# Tool — append_to_google_sheets  
# ─────────────────────────────────────────────────────────────────────────────

@tool
def append_to_google_sheets(rows_json: str) -> str:
    """
    Appends serialised extracted rows to the existing Google Sheet.
    Columns written (in order):
      paper | board | level | subject | question_number | question_text |
      marks | answer | mark_breakdown | additional_guidance

    Args:
        rows_json: JSON string — list of row dicts from merge_qp_ms_rows.
                   Each dict must contain the SHEETS_COLUMNS keys.

    Returns a JSON string:
        {"success": bool, "rows_appended": int, "error": str}

    The agent calls this when include_images=False.
    Rows are APPENDED to whatever data already exists (accumulate mode).
    """
    try:
        payload = json.loads(rows_json)
        # Accept either {"rows": [...]} or a bare list
        rows = payload.get("rows", payload) if isinstance(payload, dict) else payload
    except json.JSONDecodeError as exc:
        return json.dumps({"success": False, "rows_appended": 0, "error": f"JSON parse: {exc}"})

    if not rows:
        return json.dumps({"success": True, "rows_appended": 0, "error": "No rows to append"})

    try:
        gc = _get_sheets_client()
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        ws = sh.sheet1

        # Ensure header row exists
        existing = ws.get_all_values()
        if not existing:
            ws.append_row(SHEETS_COLUMNS)
        elif existing[0] != SHEETS_COLUMNS:
            ws.insert_row(SHEETS_COLUMNS, index=1)

        batch: list[list] = []
        for row in rows:
            batch.append([str(row.get(col, "")) for col in SHEETS_COLUMNS])

        if batch:
            ws.append_rows(batch, value_input_option="USER_ENTERED")

        return json.dumps({"success": True, "rows_appended": len(batch), "error": ""})

    except Exception as exc:
        return json.dumps({"success": False, "rows_appended": 0, "error": str(exc)})

