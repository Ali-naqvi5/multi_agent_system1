import json
import re

from langchain_google_genai import ChatGoogleGenerativeAI

from config.settings import LLM_MODEL_FAST, LLM_TEMPERATURE, invoke_with_retry, extract_text


_llm = ChatGoogleGenerativeAI(model=LLM_MODEL_FAST, temperature=LLM_TEMPERATURE)

_PROMPT_TEMPLATE = """You are extracting structured metadata from two free-text descriptions of the same UK exam paper — one for the Question Paper (QP) and one for the Mark Scheme (MS).

QP URL: {qp_url}
QP description: {qp_metadata_raw}

MS URL: {ms_url}
MS description: {ms_metadata_raw}

Goal: Extract the canonical metadata fields from the two descriptions. Both strings describe the SAME paper (one is the QP, one is the MS).

Constraints:
- board: the exam board (e.g. "Edexcel", "AQA", "OCR", "WJEC", "CCEA"). If unclear, infer from context.
- level: the qualification level (e.g. "GCSE", "A-Level", "AS-Level", "IGCSE"). If unclear, infer.
- subject: the subject name (e.g. "Mathematics", "Biology", "Chemistry", "English Language").
- year: 4-digit year as a string (e.g. "2023"). If not found, use "".
- paper_code: the paper code including tier letter if present (e.g. "1H", "2F", "1", "3"). Extract from patterns like "Paper 1H", "Paper 2F", "Paper 3". If none found, use "".
- paper_number: the numeric part of paper_code only (e.g. "1", "2", "3"). If paper_code is "1H", paper_number is "1". If no paper_code, use "".
- tier: if the paper_code ends with "H" use "Higher"; if it ends with "F" use "Foundation"; if no tier letter or A-Level/AS-Level paper, use "".
- mismatch_warning: if the two descriptions disagree on board, subject, year, or paper_code, set this to a short human-readable message describing the disagreement. Otherwise set to "".

Return ONLY raw JSON with no markdown fences, no explanation:
{{"board": "...", "level": "...", "subject": "...", "year": "...", "paper_code": "...", "paper_number": "...", "tier": "...", "mismatch_warning": "..."}}"""


def parse_metadata(qp_url: str, qp_metadata_raw: str, ms_url: str, ms_metadata_raw: str) -> dict:
    prompt = _PROMPT_TEMPLATE.format(
        qp_url=qp_url,
        qp_metadata_raw=qp_metadata_raw,
        ms_url=ms_url,
        ms_metadata_raw=ms_metadata_raw,
    )
    response = invoke_with_retry(_llm, prompt)
    raw = extract_text(response).strip()
    raw = re.sub(r"```[a-z]*", "", raw).strip("` \n")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {
        "board": "", "level": "", "subject": "", "year": "",
        "paper_code": "", "paper_number": "", "tier": "",
        "mismatch_warning": "Failed to parse LLM response",
    }
