import json
import re

from langchain_google_genai import ChatGoogleGenerativeAI

from config.settings import (
    LLM_MODEL_FAST,
    LLM_TEMPERATURE,
    invoke_with_retry,
    extract_text,
)

_llm_fast = ChatGoogleGenerativeAI(
    model=LLM_MODEL_FAST,
    temperature=LLM_TEMPERATURE,
    request_timeout=180,
    max_retries=1,
)

_PARSE_FAIL = {
    "verdict":   "fail",
    "issues":    ["verifier parse error"],
    "reasoning": "",
}

_PROMPT = """You are a senior examiner moderating a junior examiner's grade for a UK exam paper.

Goal: Decide whether the evaluation below is consistent with the mark scheme for this question. A "pass" verdict means the awarded marks, awarded_points, and missing_points are defensible against the mark scheme — not necessarily identical to how you would grade, but not contradicting it. A "fail" verdict means the grade clearly contradicts what the mark scheme supports for this specific answer.

Question text:
{question_text}

Maximum marks: {marks}

Mark scheme:
Model answer: {answer}
Mark breakdown: {mark_breakdown}
Additional guidance: {additional_guidance}

Student answer:
{answer_text}

Evaluation to check:
  awarded_marks:  {awarded_marks}
  max_marks:      {max_marks}
  awarded_points: {awarded_points}
  missing_points: {missing_points}
  reasoning:      {reasoning}

Constraints:
- Judge solely against the mark scheme. Do NOT factor in the student's ability level or writing style.
- If awarded_marks is None or the evaluation contains an error field, verdict must be "fail".
- issues must be a list of short, specific strings citing exactly which mark point or guidance clause is violated, or an empty list if verdict is "pass".
- Do NOT reveal or reference any category label — none was provided.

Return ONLY valid JSON, no markdown fences, no commentary:
{{"verdict": "pass", "issues": [], "reasoning": "..."}}
or
{{"verdict": "fail", "issues": ["..."], "reasoning": "..."}}"""

_BATCH_PROMPT = """You are a senior examiner moderating grades for all student answers to one exam question.

Question text:
{question_text}

Maximum marks: {marks}

Mark scheme:
Model answer: {answer}
Mark breakdown: {mark_breakdown}
Additional guidance: {additional_guidance}

Constraints:
- Judge solely against the mark scheme for each answer.
- If an evaluation has awarded_marks = None or contains an error field, verdict must be "fail".
- issues must list the specific mark point or guidance clause violated, or be empty for a pass.
- Do NOT reference any student category label.

---

## All Student Answers and Their Evaluations (in order):

{answers_block}

---

Return a JSON array of exactly {n} verdict objects, one per answer, in the SAME ORDER as listed above.
No markdown fences, no commentary — only the JSON array:
[
  {{"verdict": "pass", "issues": [], "reasoning": "..."}},
  {{"verdict": "fail", "issues": ["..."], "reasoning": "..."}},
  ...
]"""


def _parse_verdict(raw: str) -> dict | None:
    raw = raw.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$",       "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return None


def _parse_batch(raw: str) -> list | None:
    raw = raw.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$",       "", raw).strip()
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                result = json.loads(m.group(0))
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                pass
    return None


def verify_evaluation(question: dict, answer_text: str, evaluation: dict) -> dict:
    """Verify a single answer's evaluation. Used by the Node 6 refine loop."""
    ev = evaluation or {}
    prompt = _PROMPT.format(
        question_text   = question.get("question_text", ""),
        marks           = question.get("marks", 0),
        answer          = question.get("answer", ""),
        mark_breakdown  = question.get("mark_breakdown", ""),
        additional_guidance = question.get("additional_guidance", "") or "(none)",
        answer_text     = answer_text or "",
        awarded_marks   = ev.get("awarded_marks", "N/A"),
        max_marks       = ev.get("max_marks", "N/A"),
        awarded_points  = ev.get("awarded_points", []),
        missing_points  = ev.get("missing_points", []),
        reasoning       = ev.get("reasoning", ""),
    )

    if "error" in ev:
        return {
            "verdict":   "fail",
            "issues":    [f"upstream evaluator error: {ev['error']}"],
            "reasoning": "",
        }

    response = invoke_with_retry(_llm_fast, prompt)
    result   = _parse_verdict(extract_text(response))

    if result is None:
        print("  [verifier] parse failed — retrying once...")
        response2 = invoke_with_retry(_llm_fast, prompt)
        result     = _parse_verdict(extract_text(response2))

    return result if result is not None else {**_PARSE_FAIL}


def verify_all_answers(question: dict, answers: list) -> list[dict]:
    """Verify all answer evaluations for one question in a single LLM call.

    Falls back to individual verify_evaluation() calls if batch parse fails.
    """
    answers_block = "\n\n".join(
        f"Answer {i + 1}:\n"
        f"  answer_text:    {a.get('answer_text', '')}\n"
        f"  awarded_marks:  {(a.get('evaluation') or {{}}).get('awarded_marks', 'N/A')}\n"
        f"  max_marks:      {(a.get('evaluation') or {{}}).get('max_marks', 'N/A')}\n"
        f"  awarded_points: {(a.get('evaluation') or {{}}).get('awarded_points', [])}\n"
        f"  missing_points: {(a.get('evaluation') or {{}}).get('missing_points', [])}\n"
        f"  reasoning:      {(a.get('evaluation') or {{}}).get('reasoning', '')}"
        for i, a in enumerate(answers)
    )

    prompt = _BATCH_PROMPT.format(
        question_text       = question.get("question_text", ""),
        marks               = question.get("marks", 0),
        answer              = question.get("answer", ""),
        mark_breakdown      = question.get("mark_breakdown", ""),
        additional_guidance = question.get("additional_guidance", "") or "(none)",
        answers_block       = answers_block,
        n                   = len(answers),
    )

    response = invoke_with_retry(_llm_fast, prompt)
    result   = _parse_batch(extract_text(response))

    if result is None or len(result) != len(answers):
        print("  [verifier-batch] parse failed or wrong count — retrying once...")
        response2 = invoke_with_retry(_llm_fast, prompt)
        result    = _parse_batch(extract_text(response2))

    if result is None or len(result) != len(answers):
        print("  [verifier-batch] falling back to individual calls...")
        return [
            verify_evaluation(question, a.get("answer_text", ""), a.get("evaluation", {}))
            for a in answers
        ]

    return result
