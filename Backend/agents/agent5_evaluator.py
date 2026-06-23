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

_PARSE_ERROR = {
    "awarded_marks":  None,
    "max_marks":      None,
    "awarded_points": [],
    "missing_points": [],
    "reasoning":      "",
}

_BATCH_SUFFIX = """

---

## All Student Answers to Grade (in order):

{answers_block}

---

Return a JSON array of exactly {n} evaluation objects, one per answer, in the SAME ORDER as listed above.
Each object must follow the output schema defined in the grading prompt above.
No markdown fences, no commentary — only the JSON array:
[
  {{"awarded_marks": <int>, "max_marks": <int>, "awarded_points": [...], "missing_points": [...], "reasoning": "..."}},
  ...
]"""


def _parse_evaluation(raw: str) -> dict | None:
    """Strip fences, parse JSON, return dict or None on failure."""
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
    """Strip fences, parse JSON array, return list or None on failure."""
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


def _coerce(result: dict) -> dict:
    """Coerce awarded_marks / max_marks to int where safely possible."""
    for key in ("awarded_marks", "max_marks"):
        val = result.get(key)
        if val is not None:
            try:
                result[key] = int(val)
            except (ValueError, TypeError):
                pass
    return result


def evaluate_answer(eval_prompt: str, answer_text: str) -> dict:
    """Grade a single student answer. Used by the Node 6 refine loop."""
    message = eval_prompt + "\n\n## Student Answer:\n" + (answer_text or "")

    response = invoke_with_retry(_llm_fast, message)
    result   = _parse_evaluation(extract_text(response))

    if result is None:
        print("  [evaluator] parse failed — retrying once...")
        response2 = invoke_with_retry(_llm_fast, message)
        result     = _parse_evaluation(extract_text(response2))

    if result is None:
        return {**_PARSE_ERROR, "error": "could not parse grader response after retry"}

    return _coerce(result)


def evaluate_all_answers(eval_prompt: str, answers: list) -> list[dict]:
    """Grade all student answers for one question in a single LLM call.

    Falls back to individual evaluate_answer() calls if batch parse fails.
    """
    answers_block = "\n\n".join(
        f"Answer {i + 1} (category: {a.get('category', '?')}):\n{a.get('answer_text', '')}"
        for i, a in enumerate(answers)
    )

    message = eval_prompt + _BATCH_SUFFIX.format(
        answers_block=answers_block,
        n=len(answers),
    )

    response = invoke_with_retry(_llm_fast, message)
    result   = _parse_batch(extract_text(response))

    if result is None or len(result) != len(answers):
        print(f"  [evaluator-batch] parse failed or wrong count — retrying once...")
        response2 = invoke_with_retry(_llm_fast, message)
        result    = _parse_batch(extract_text(response2))

    if result is None or len(result) != len(answers):
        print("  [evaluator-batch] falling back to individual calls...")
        return [evaluate_answer(eval_prompt, a.get("answer_text", "")) for a in answers]

    return [_coerce(r) for r in result]
