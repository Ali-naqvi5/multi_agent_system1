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

_META_PROMPT = """You are an assessment designer creating a grading prompt for a downstream AI grader marking UK exam papers.

Goal: Write one self-contained grading prompt for the question below. The prompt you write will later have a student's answer appended under "## Student Answer:" and be passed to an AI grader.

The grading prompt you produce MUST contain these sections in order:

1. An examiner role statement naming the paper.
   Example: "You are an examiner for {paper_label}."

2. The question text verbatim and its maximum marks.

3. The complete mark scheme:
   - The model answer
   - Each individual mark point from the mark breakdown as given
   - Any accept / allow / ignore / do not accept notes from additional guidance

4. Grading rules (state these explicitly):
   - Award each mark point independently
   - Allow partial credit where the mark scheme permits
   - Apply all accept / allow / ignore guidance exactly as stated
   - Do not award marks for points not supported by the mark scheme

5. The exact output schema the grader must return, copied verbatim:

{{
  "awarded_marks": <int>,
  "max_marks": <int>,
  "awarded_points": [<list of mark point strings the answer earned>],
  "missing_points": [<list of mark point strings the answer did not earn>],
  "reasoning": "<concise justification grounded in the mark scheme>"
}}

6. End with exactly this sentence: "The student's answer follows under '## Student Answer:'."

Constraints:
- Output the grading prompt text only. No markdown fences around your response, no preamble, no commentary before or after the prompt.
- Do NOT include any student answer or fabricated answer inside the prompt.
- Do NOT invent mark points that are not present in the mark scheme below.

Question details:
Board: {board}
Level: {level}
Subject: {subject}
Paper: {paper_label}
Question number: {question_number}
Maximum marks: {marks}

Question text:
{question_text}

Model answer:
{answer}

Mark breakdown:
{mark_breakdown}

Additional guidance:
{additional_guidance}"""


def generate_eval_prompt(question: dict, metadata: dict, feedback: str = "") -> str:
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

    prompt = _META_PROMPT.format(
        board           = board,
        level           = level,
        subject         = subject,
        paper_label     = paper_label,
        question_number = question.get("question_number", ""),
        marks           = question.get("marks", 0),
        question_text   = question.get("question_text", ""),
        answer          = question.get("answer", ""),
        mark_breakdown  = question.get("mark_breakdown", ""),
        additional_guidance = question.get("additional_guidance", "") or "(none)",
    )

    # Append feedback section AFTER format() so curly braces in feedback are safe
    if feedback:
        prompt += (
            "\n\n## Revision required\n\n"
            "A senior moderator reviewed grades produced by a previous version of this grading "
            "prompt and identified the following specific issues:\n\n"
            + feedback +
            "\n\nRevise the grading prompt above to address these issues precisely. "
            "Do NOT invent rules or mark points that are not supported by the mark scheme. "
            "Keep the same six-section structure and the exact output schema unchanged."
        )

    response = invoke_with_retry(_llm_fast, prompt)
    result   = extract_text(response).strip()

    # Strip any stray markdown fences the model might add despite instructions
    result = re.sub(r"^```[a-z]*\n?", "", result)
    result = re.sub(r"\n?```$",       "", result)
    return result.strip()
