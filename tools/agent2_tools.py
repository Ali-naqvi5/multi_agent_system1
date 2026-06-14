import json
import re
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from config.settings import LLM_MODEL_SMART, LLM_TEMPERATURE, invoke_with_retry_slow, extract_text

# Pairing is the one step that genuinely needs the highest-quality model
_llm = ChatGoogleGenerativeAI(model=LLM_MODEL_SMART, temperature=LLM_TEMPERATURE)


@tool
def llm_pair_results(qp_list: str, ms_list: str, metadata: str) -> str:
    """
    Takes the full QP pool and MS pool and returns confirmed pairs.

    Args:
        qp_list:  JSON string — list of {"title": str, "url": str}
        ms_list:  JSON string — list of {"title": str, "url": str}
        metadata: JSON string — {"board": str, "level": str, "subject": str, "year": str}

    Returns JSON string:
        {
          "pairs": [{"qp_title": str, "qp_url": str, "ms_title": str, "ms_url": str}],
          "skipped_qps": [str],
          "skipped_mss": [str]
        }
    """
    try:
        qps      = json.loads(qp_list)
        mss      = json.loads(ms_list)
        meta     = json.loads(metadata)
    except json.JSONDecodeError as e:
        return json.dumps({"error": str(e), "pairs": [], "skipped_qps": [], "skipped_mss": []})

    qp_formatted = "\n".join(
        f"{i}: Title: {q['title']} | URL: {q['url']}"
        for i, q in enumerate(qps)
    )
    ms_formatted = "\n".join(
        f"{i}: Title: {m['title']} | URL: {m['url']}"
        for i, m in enumerate(mss)
    )

    prompt = f"""You are an expert UK exam paper matching assistant. Your job is to correctly pair question papers with their mark schemes for UK qualifications (GCSE, A-Level, AS-Level, International A-Level, etc.).

=== KNOWN GROUND TRUTH ===
  Board:   {meta.get('board', 'unknown')}
  Level:   {meta.get('level', 'unknown')}
  Subject: {meta.get('subject', 'unknown')}
  Year:    {meta.get('year', 'unknown')}

=== MATCHING RULES (apply ALL that are relevant) ===

1. PAPER NUMBER
   - Match paper numbers exactly: Paper 1 ↔ Paper 1, Paper 2 ↔ Paper 2
   - Watch for aliases: "P1" = "Paper 1", "Unit 1" = "Paper 1" in some boards
   - Do NOT match Paper 1 with Paper 2 under any circumstances

2. EXAM SESSION
   - Match by session in the TITLE only — IGNORE the URL when determining session
   - URLs often contain incorrect or upload dates (e.g. a June 2022 paper may have "may-2022" in the URL — this is fine, use the title)
   - Valid session formats: "June 2022", "Summer 2022", "November 2021", "January 2022"
   - "Summer" = "June" for matching purposes
   - Do NOT match different years (e.g. June 2022 ≠ June 2021)

3. TIER (GCSE only)
   - Higher (H) MUST match Higher (H)
   - Foundation (F) MUST match Foundation (F)
   - NEVER mix tiers under any circumstances

4. LEVEL
   - A-Level ≠ AS-Level ≠ GCSE ≠ International A-Level (IAL)
   - Match level exactly. "A-Level" and "AS-Level" are different qualifications

5. SUBJECT / COMPONENT
   - Pure Mathematics 1 ≠ Pure Mathematics 2
   - Statistics ≠ Mechanics ≠ Pure
   - Match the component or unit exactly if specified

6. EXAM BOARD
   - Edexcel ≠ AQA ≠ OCR ≠ Cambridge
   - Only match within the same board

=== URL GUIDANCE ===
- Use URLs only to identify the file, NOT to determine session, paper, or tier
- Titles are the ground truth for all matching decisions
- A mismatch between URL date and title date should be IGNORED — trust the title
- Reject MS from unofficial sites: weebly.com, scribd.com, slideshare.net, school/personal sites

=== WHAT TO DO IF UNSURE ===
- If two or more mark schemes could plausibly match a question paper, pick the one whose title is most specific and complete
- If you genuinely cannot find a confident match after applying all rules, skip that question paper entirely
- Never guess. Never match just because it is the only option left if the criteria do not align

=== INPUT ===

Question Papers:
{qp_formatted}

Mark Schemes:
{ms_formatted}

=== OUTPUT FORMAT ===
Return ONLY a valid JSON object. No explanation, no markdown, no backticks, no preamble.

{{
  "pairs": [
    {{
      "qp_title": "title of the question paper",
      "qp_url": "full URL of the question paper",
      "ms_title": "title of the mark scheme",
      "ms_url": "full URL of the matched mark scheme"
    }}
  ],
  "skipped_qps": ["title of any unmatched question paper"],
  "skipped_mss": ["title of any unmatched mark scheme"]
}}

If there are zero valid matches return: {{"pairs": [], "skipped_qps": [], "skipped_mss": []}}
## Question Papers:
{qp_formatted}

## Mark Schemes:
{ms_formatted}

Return ONLY a valid JSON object, no markdown, no explanation:
{{
  "pairs": [
    {{
      "qp_title": "...",
      "qp_url": "...",
      "ms_title": "...",
      "ms_url": "..."
    }}
  ],
  "skipped_qps": ["title1", ...],
  "skipped_mss": ["title1", ...]
}}

"""
    response = invoke_with_retry_slow(_llm, prompt)
    raw = extract_text(response).strip()
    raw = re.sub(r"```[a-z]*", "", raw).strip("` \n")

    try:
        return raw  # already valid JSON
    except Exception:
        return json.dumps({"pairs": [], "skipped_qps": [], "skipped_mss": []})































