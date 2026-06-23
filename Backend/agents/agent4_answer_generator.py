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

_PROMPT = """You are simulating realistic UK student answers to an exam question for assessment research purposes.

Goal: Write exactly 10 student answers to the question below, one per student category. Each answer must authentically represent how a student in that category would write under exam conditions — grounded in the actual question and mark scheme.

Paper: {paper_label}
Question number: {question_number}
Maximum marks: {marks}

Question text:
{question_text}

Model answer (mark scheme):
{answer}

Mark breakdown:
{mark_breakdown}

Additional guidance:
{additional_guidance}

Categories — produce answers in exactly this order:
1. top              — fully correct; hits all or nearly all mark points from the mark scheme
2. strong_minor_slip— strong response with exactly one small slip, error, or omission
3. mid              — roughly half the available mark points; genuine understanding but notable gaps
4. weak             — only one or two mark points; major gaps in understanding
5. method_no_answer — shows correct working / method but arrives at a wrong final value (for pure recall questions, shows the right reasoning approach but draws a wrong conclusion)
6. misconception    — contains a real, topic-specific misconception common for {subject} at {level}; a plausible but wrong conceptual model, not random nonsense
7. poor_literacy    — correct scientific/mathematical content but with poor spelling, grammar, or notation; the intended meaning is still recoverable
8. verbose_waffle   — long, padded response; correct key points are buried but present; most of the text is irrelevant filler
9. off_topic        — misreads the question and answers something adjacent but wrong; confident but in the wrong direction
10. blank_minimal   — empty or near-empty; at most one vague word or phrase that earns no marks

Rules:
- Never skip a category; always return exactly 10 objects.
- Do NOT attach any score, grade, target mark, or "correct/incorrect" label to any answer.
- If a category does not perfectly fit this question type, still produce the closest plausible student response in that student's voice.
- Misconception answer must reflect a real misconception for THIS specific topic, not a generic one.
- Top answer must actually address the mark scheme's specific points, not just sound confident.
- If the question references a figure or table the model cannot see, generate best-effort answers from the question text alone — do not fabricate the figure's contents.
- Answers should vary appropriately in length and register for each category.

Return ONLY a JSON array of exactly 10 objects. No markdown fences, no preamble, no commentary:
[
  {{"category": "top",               "answer_text": "..."}},
  {{"category": "strong_minor_slip", "answer_text": "..."}},
  {{"category": "mid",               "answer_text": "..."}},
  {{"category": "weak",              "answer_text": "..."}},
  {{"category": "method_no_answer",  "answer_text": "..."}},
  {{"category": "misconception",     "answer_text": "..."}},
  {{"category": "poor_literacy",     "answer_text": "..."}},
  {{"category": "verbose_waffle",    "answer_text": "..."}},
  {{"category": "off_topic",         "answer_text": "..."}},
  {{"category": "blank_minimal",     "answer_text": "..."}}
]"""


def _parse_answers(raw: str) -> list:
    raw = raw.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return []


def generate_answers(question: dict, metadata: dict) -> list:
    board      = metadata.get("board", "")
    level      = metadata.get("level", "")
    subject    = metadata.get("subject", "")
    year       = metadata.get("year", "")
    paper_code = metadata.get("paper_code", "")
    tier       = metadata.get("tier", "")

    paper_label = " ".join(filter(None, [
        board, level, subject, year,
        f"Paper {paper_code}" if paper_code else "",
        tier if tier else "",
    ]))

    prompt = _PROMPT.format(
        paper_label         = paper_label,
        board               = board,
        level               = level,
        subject             = subject,
        question_number     = question.get("question_number", ""),
        marks               = question.get("marks", 0),
        question_text       = question.get("question_text", ""),
        answer              = question.get("answer", ""),
        mark_breakdown      = question.get("mark_breakdown", ""),
        additional_guidance = question.get("additional_guidance", "") or "(none)",
    )

    response = invoke_with_retry(_llm_fast, prompt)
    parsed   = _parse_answers(extract_text(response))

    if len(parsed) != 10:
        print(f"  [answer_gen] got {len(parsed)} answers — retrying once...")
        response2 = invoke_with_retry(_llm_fast, prompt)
        retry     = _parse_answers(extract_text(response2))
        if len(retry) != 10:
            print(f"  [answer_gen] retry returned {len(retry)} answers — using best available")
            parsed = retry if len(retry) > len(parsed) else parsed
        else:
            parsed = retry

    q_num = str(question.get("question_number", ""))
    return [
        {
            "answer_id":   f"{q_num}::{item.get('category', '')}",
            "category":    item.get("category", ""),
            "answer_text": item.get("answer_text", ""),
        }
        for item in parsed
    ]
