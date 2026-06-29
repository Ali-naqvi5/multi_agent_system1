
import asyncio
import json
import os
import re
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any
from config.settings import TMP_DIR, set_run_dir, clear_run_dir
from langgraph.graph import StateGraph, END
from graph.state import AgentState
from graph.progress import report as _progress, set_callback, clear_callback
from agents.agent2_downloader_extractor import build_downloader_extractor_agent
from agents.agent1_query_parser import parse_metadata
from agents.agent3_prompt_generator import generate_eval_prompt
from agents.agent4_answer_generator import generate_answers
from agents.agent5_evaluator import evaluate_answer, evaluate_all_answers
from agents.agent6_verifier import verify_evaluation, verify_all_answers


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_json(text) -> Any:
    """Extract the first JSON object or array from a possibly-noisy string."""
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


MAX_RETRIES = 3


def _norm_q(v: str) -> str:
    """Normalise a question-number string for map keys and lookups.

    Strips leading 'question ' prefix and removes parentheses / spaces so that
    labels like '2(a)', 'Question 2a', and '2 a' all collapse to '2a'.
    """
    v = v.strip().lower()
    v = re.sub(r"^question\s*", "", v)
    v = re.sub(r"[() ]", "", v)
    return v


def _build_diagram_map(saved_diagrams: list) -> dict:
    """Build a diagram-map dict deterministically from a raw saved_diagrams list."""
    dm = {}
    for item in saved_diagrams:
        path = item.get("file_path", "")
        if not path:
            continue
        fig = _norm_q(str(item.get("figure_number") or ""))
        tbl = _norm_q(str(item.get("table_number")  or ""))
        q   = _norm_q(str(item.get("question_number") or ""))
        if fig:
            dm[f"fig:{fig}"] = path
        if tbl:
            dm[f"tbl:{tbl}"] = path
        if q:
            dm[f"q:{q}"] = path
    return dm


def build_feedback_string(failed_answers: list) -> str:
    """Concatenate verification issues from all failed answers into one labelled block."""
    blocks = []
    for answer in failed_answers:
        v         = answer.get("verification", {})
        issues    = v.get("issues", [])
        reasoning = v.get("reasoning", "")
        aid       = answer.get("answer_id", "?")
        if issues or reasoning:
            lines = [f"Answer {aid}:"]
            for issue in issues:
                lines.append(f"  - {issue}")
            if reasoning:
                lines.append(f"  Reasoning: {reasoning}")
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "Grade inconsistent with mark scheme."


# ─────────────────────────────────────────────────────────────────────────────
# Node 1 — Parse Metadata
# ─────────────────────────────────────────────────────────────────────────────

def node_parse_metadata(state: AgentState) -> AgentState:
    print("\n" + "="*60)
    print("NODE 1: Query Parser")
    print("="*60)

    qp_url          = state.get("qp_url", "")
    qp_metadata_raw = state.get("qp_metadata_raw", "")
    ms_url          = state.get("ms_url", "")
    ms_metadata_raw = state.get("ms_metadata_raw", "")

    parsed = parse_metadata(qp_url, qp_metadata_raw, ms_url, ms_metadata_raw)

    board        = parsed.get("board", "")
    level        = parsed.get("level", "")
    subject      = parsed.get("subject", "")
    year         = parsed.get("year", "")
    paper_code   = parsed.get("paper_code", "")
    paper_number = parsed.get("paper_number", "")
    tier         = parsed.get("tier", "")
    warning      = parsed.get("mismatch_warning", "")

    print(f"  board={board}  level={level}  subject={subject}  year={year}")
    print(f"  paper_code={paper_code}  paper_number={paper_number}  tier={tier}")
    if warning:
        print(f"  WARNING: {warning}")

    pairs_json = json.dumps([{
        "qp_url":   qp_url,
        "ms_url":   ms_url,
        "qp_title": qp_metadata_raw,
        "ms_title": ms_metadata_raw,
    }])

    return {
        **state,
        "board":        board,
        "level":        level,
        "subject":      subject,
        "year":         year,
        "paper_code":   paper_code,
        "paper_number": paper_number,
        "tier":         tier,
        "pairs_json":   pairs_json,
        "status":       "ok",
        "error_message": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 2 — Downloader + Extractor
# ─────────────────────────────────────────────────────────────────────────────

def node_downloader_extractor(state: AgentState) -> AgentState:
    print("\n" + "="*60)
    print("NODE 2: Downloader + Extractor Agent")
    print("="*60)

    board      = state.get("board", "")
    level      = state.get("level", "")
    subject    = state.get("subject", "")
    year       = state.get("year", "")
    paper_code = state.get("paper_code", "")
    tier       = state.get("tier", "")

    paper_str = " ".join(filter(None, [
        board, level, subject, year,
        f"Paper {paper_code}" if paper_code else "",
    ]))

    metadata = json.dumps({
        "paper":      paper_str,
        "board":      board,
        "level":      level,
        "subject":    subject,
        "year":       year,
        "paper_code": paper_code,
        "tier":       tier,
    })

    pairs = json.loads(state.get("pairs_json", "[]"))

    all_rows = []
    all_diagram_map = {}
    all_failed_pairs = []

    for i, pair in enumerate(pairs):
        agent = build_downloader_extractor_agent()
        print(f"\n  Processing pair {i+1}/{len(pairs)}: {pair.get('qp_title', '?')}")

        message = (
            f"paper_number={i+1}\n\n"
            f"metadata={metadata}\n\n"
            f"{json.dumps([pair])}"
        )

        try:
            result = agent.invoke({"messages": [("user", message)]})

            parsed = {}
            for msg in reversed(result["messages"]):
                content = msg.content
                if isinstance(content, list):
                    content = " ".join(
                        block.get("text", "") if isinstance(block, dict) else str(block)
                        for block in content
                    )
                candidate = _safe_json(str(content)) if content else {}
                if candidate.get("extracted_rows") or candidate.get("rows"):
                    parsed = candidate
                    break

            rows         = parsed.get("extracted_rows", parsed.get("rows", []))
            diagram_maps = parsed.get("diagram_maps", {})

            # Prefer deterministic Python rebuild over LLM-constructed diagram_maps
            raw_saved = parsed.get("saved_diagrams_by_paper", {}).get(str(i + 1), [])
            if raw_saved:
                diagram_map = _build_diagram_map(raw_saved)
            else:
                diagram_map = diagram_maps.get(str(i + 1), parsed.get("diagram_map", {}))

            # Direct question-number fallback: catches cases where Gemini tagged a
            # diagram with figure_number only and left question_number empty, so
            # the q: key was never added to diagram_map. We build a separate lookup
            # keyed purely by question_number from the raw saved list.
            _q_fallback = {
                _norm_q(s["question_number"]): s["file_path"]
                for s in raw_saved
                if s.get("question_number") and s.get("file_path")
            }

            for row in rows:
                fig = _norm_q(str(row.get("figure_number") or ""))
                tbl = _norm_q(str(row.get("table_number")  or ""))
                q   = _norm_q(str(row.get("question_number") or ""))
                row["image_path"] = (
                    (diagram_map.get(f"fig:{fig}") if fig else None)
                    or (diagram_map.get(f"tbl:{tbl}") if tbl else None)
                    or (diagram_map.get(f"q:{q}")   if q   else None)
                    or (_q_fallback.get(q)          if q   else None)
                    or ""
                )

            all_rows.extend(rows)
            all_diagram_map.update(diagram_map)
            all_failed_pairs.extend(parsed.get("failed_pairs", []))

            print(f"  Pair {i+1} → {len(rows)} questions extracted")

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

    if not all_rows:
        print("\n  No questions extracted.")
    else:
        print("\n  Extracted questions:")
        for row in all_rows:
            q_num  = row.get("question_number", "?")
            q_text = row.get("question_text", "")
            preview = q_text[:80] + ("..." if len(q_text) > 80 else "")
            print(f"    Q{q_num}: {preview}")

        # ── JSON snapshot (debug only) — disabled ──
        # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # out_path  = os.path.join(TMP_DIR, f"extracted_{timestamp}.json")
        # with open(out_path, "w", encoding="utf-8") as f:
        #     json.dump(all_rows, f, indent=2, ensure_ascii=False)
        # print(f"\n  Rows saved to: {out_path}")

    return {
        **state,
        "extracted_rows_json": json.dumps(all_rows),
        "diagram_map_json":    json.dumps(all_diagram_map),
        "status":              "ok",
        "error_message":       None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 3 — Prompt Generator
# ─────────────────────────────────────────────────────────────────────────────

def node_generate_prompts(state: AgentState) -> AgentState:
    print("\n" + "="*60)
    print("NODE 3: Prompt Generator")
    print("="*60)

    rows = json.loads(state.get("extracted_rows_json", "[]"))

    if not rows:
        print("\n  No extracted rows — skipping prompt generation.")
        return {**state, "status": "ok"}

    metadata = {
        "board":      state.get("board", ""),
        "level":      state.get("level", ""),
        "subject":    state.get("subject", ""),
        "year":       state.get("year", ""),
        "paper_code": state.get("paper_code", ""),
        "tier":       state.get("tier", ""),
    }

    total = len(rows)
    print(f"\n  Generating evaluation prompts for {total} question(s) (parallel)...")
    _done = [0]
    _done_lock = threading.Lock()

    def _gen_prompt(row):
        q_num     = row.get("question_number", "?")
        answer    = (row.get("answer") or "").strip()
        breakdown = (row.get("mark_breakdown") or "").strip()
        if not answer and not breakdown:
            row["eval_prompt"] = ""
            print(f"    Q{q_num}: no mark scheme — skipped")
        else:
            row["eval_prompt"] = generate_eval_prompt(row, metadata)
            print(f"    Q{q_num}: prompt generated")
        with _done_lock:
            _done[0] += 1
            _progress(f"Generating prompts… {_done[0]}/{total}", 20 + int(15 * _done[0] / total))
        return row

    with ThreadPoolExecutor(max_workers=5) as ex:
        rows = list(ex.map(_gen_prompt, rows))

    # ── JSON snapshot (debug only) — disabled ──
    # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # out_path  = os.path.join(TMP_DIR, f"extracted_with_prompts_{timestamp}.json")
    # with open(out_path, "w", encoding="utf-8") as f:
    #     json.dump(rows, f, indent=2, ensure_ascii=False)
    # print(f"\n  Enriched rows saved to: {out_path}")

    return {
        **state,
        "extracted_rows_json": json.dumps(rows),
        "status":              "ok",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 4 — Answer Generator
# ─────────────────────────────────────────────────────────────────────────────

def node_generate_answers(state: AgentState) -> AgentState:
    print("\n" + "="*60)
    print("NODE 4: Answer Generator")
    print("="*60)

    rows = json.loads(state.get("extracted_rows_json", "[]"))

    if not rows:
        print("\n  No extracted rows — skipping answer generation.")
        return {**state, "status": "ok"}

    metadata = {
        "board":      state.get("board", ""),
        "level":      state.get("level", ""),
        "subject":    state.get("subject", ""),
        "year":       state.get("year", ""),
        "paper_code": state.get("paper_code", ""),
        "tier":       state.get("tier", ""),
    }

    total = len(rows)
    print(f"\n  Generating answers for {total} question(s) (parallel)...")
    _done = [0]
    _done_lock = threading.Lock()

    def _gen_answers(row):
        q_num = row.get("question_number", "?")
        if not row.get("eval_prompt"):
            row["answers"] = []
            print(f"    Q{q_num}: no eval_prompt — skipped")
        else:
            row["answers"] = generate_answers(row, metadata)
            print(f"    Q{q_num}: {len(row['answers'])} answers generated")
        with _done_lock:
            _done[0] += 1
            _progress(f"Generating answers… {_done[0]}/{total}", 35 + int(20 * _done[0] / total))
        return row

    with ThreadPoolExecutor(max_workers=5) as ex:
        rows = list(ex.map(_gen_answers, rows))

    # ── JSON snapshot (debug only) — disabled ──
    # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # out_path  = os.path.join(TMP_DIR, f"extracted_with_answers_{timestamp}.json")
    # with open(out_path, "w", encoding="utf-8") as f:
    #     json.dump(rows, f, indent=2, ensure_ascii=False)
    # print(f"\n  Enriched rows saved to: {out_path}")

    return {
        **state,
        "extracted_rows_json": json.dumps(rows),
        "status":              "ok",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 5 — Evaluator
# ─────────────────────────────────────────────────────────────────────────────

def node_evaluate_answers(state: AgentState) -> AgentState:
    print("\n" + "="*60)
    print("NODE 5: Evaluator")
    print("="*60)

    rows = json.loads(state.get("extracted_rows_json", "[]"))

    if not rows:
        print("\n  No extracted rows — skipping evaluation.")
        return {**state, "status": "ok"}

    total = len(rows)
    _done = [0]
    _done_lock = threading.Lock()

    def _eval_row(row):
        q_num       = row.get("question_number", "?")
        answers     = row.get("answers", [])
        eval_prompt = row.get("eval_prompt", "")
        if not answers:
            print(f"  Q{q_num}: no answers — skipped")
        else:
            evaluations = evaluate_all_answers(eval_prompt, answers)
            for answer, evaluation in zip(answers, evaluations):
                answer["evaluation"] = evaluation
            print(f"  Q{q_num}: graded {len(evaluations)}/{len(answers)} answers (batch)")
            for answer in answers:
                ev    = answer["evaluation"]
                cat   = answer.get("category", "?")
                score = "ERR" if "error" in ev else f"{ev.get('awarded_marks', '?')}/{ev.get('max_marks', '?')}"
                print(f"    {cat:<18} -> {score}")
        with _done_lock:
            _done[0] += 1
            _progress(f"Evaluating answers… {_done[0]}/{total}", 55 + int(20 * _done[0] / total))
        return row

    with ThreadPoolExecutor(max_workers=5) as ex:
        rows = list(ex.map(_eval_row, rows))

    # ── JSON snapshot (debug only) — disabled ──
    # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # out_path  = os.path.join(TMP_DIR, f"extracted_with_evaluations_{timestamp}.json")
    # with open(out_path, "w", encoding="utf-8") as f:
    #     json.dump(rows, f, indent=2, ensure_ascii=False)
    # print(f"\n  Enriched rows saved to: {out_path}")

    return {
        **state,
        "extracted_rows_json": json.dumps(rows),
        "status":              "ok",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 6 — Verifier + Refine Loop
# ─────────────────────────────────────────────────────────────────────────────

def node_verify_and_refine(state: AgentState) -> AgentState:
    print("\n" + "="*60)
    print("NODE 6: Verifier + Refine Loop")
    print("="*60)

    rows = json.loads(state.get("extracted_rows_json", "[]"))

    if not rows:
        print("\n  No extracted rows — skipping verification.")
        return {**state, "status": "done"}

    metadata = {
        "board":      state.get("board", ""),
        "level":      state.get("level", ""),
        "subject":    state.get("subject", ""),
        "year":       state.get("year", ""),
        "paper_code": state.get("paper_code", ""),
        "tier":       state.get("tier", ""),
    }

    total = len(rows)
    _done = [0]
    _done_lock = threading.Lock()

    def _verify_row(row):
        q_num   = row.get("question_number", "?")
        answers = row.get("answers", [])

        if not answers:
            row["verification_status"] = "skipped"
            print(f"\n  Q{q_num}: no answers — skipped")
        else:
            row["prompt_version"] = 0
            attempt = 0

            while True:
                # Verify all answers in one batch call
                verdicts = verify_all_answers(row, answers)
                for answer, verdict in zip(answers, verdicts):
                    answer["verification"] = verdict

                failed = [a for a in answers if a["verification"]["verdict"] == "fail"]

                if not failed:
                    row["verification_status"] = "validated"
                    break

                if attempt >= MAX_RETRIES:
                    row["verification_status"] = "unconvergeable"
                    break

                attempt += 1
                row["prompt_version"] = attempt

                # Build one feedback block from all failures
                feedback = build_feedback_string(failed)

                # Refine this question's eval_prompt using Phase 1 generator + feedback
                row["eval_prompt"] = generate_eval_prompt(row, metadata, feedback=feedback)

                # Re-grade ALL answers against the new prompt (individual calls for precision)
                for answer in answers:
                    answer["evaluation"] = evaluate_answer(
                        row["eval_prompt"], answer.get("answer_text", "")
                    )

            pass_count = sum(1 for a in answers if a.get("verification", {}).get("verdict") == "pass")
            status = row["verification_status"]
            print(f"\n  Q{q_num}: {status} after {attempt} refine(s) — {pass_count}/{len(answers)} passed")

        with _done_lock:
            _done[0] += 1
            _progress(f"Verifying grades… {_done[0]}/{total}", 75 + int(15 * _done[0] / total))
        return row

    with ThreadPoolExecutor(max_workers=5) as ex:
        rows = list(ex.map(_verify_row, rows))

    # ── JSON snapshot (debug only) — disabled ──
    # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # out_path  = os.path.join(TMP_DIR, f"final_{timestamp}.json")
    # with open(out_path, "w", encoding="utf-8") as f:
    #     json.dump(rows, f, indent=2, ensure_ascii=False)
    # print(f"\n  Final rows saved to: {out_path}")

    return {
        **state,
        "extracted_rows_json": json.dumps(rows),
        "status":              "done",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 7 — Save to Database
# ─────────────────────────────────────────────────────────────────────────────

def node_save_to_db(state: AgentState) -> AgentState:
    print("\n" + "="*60)
    print("NODE 7: Save to Database")
    print("="*60)

    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from db.models import Paper, Question, Answer, Image as DBImage

    rows = json.loads(state.get("extracted_rows_json", "[]"))

    if not rows:
        print("\n  No rows to save.")
        return {**state, "status": "done"}

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("\n  DATABASE_URL not set — skipping DB save.")
        return {**state, "status": "done"}

    async def _persist():
        engine  = create_async_engine(db_url)
        Session = async_sessionmaker(engine, expire_on_commit=False)

        async with Session() as session:
            # One Paper row per pipeline run, built from state metadata
            paper_num_raw = state.get("paper_number", "")
            paper = Paper(
                board        = state.get("board")        or rows[0].get("board"),
                level        = state.get("level")        or rows[0].get("level"),
                subject      = state.get("subject")      or rows[0].get("subject"),
                year         = state.get("year")         or rows[0].get("year"),
                paper_code   = state.get("paper_code")   or None,
                paper_number = int(paper_num_raw) if str(paper_num_raw).isdigit() else None,
                tier         = state.get("tier")         or None,
            )
            session.add(paper)

            for row in rows:
                q = Question(
                    question_number     = str(row.get("question_number", "")),
                    question_text       = row.get("question_text", ""),
                    marks               = row.get("marks") or None,
                    answer              = row.get("answer") or None,
                    mark_breakdown      = row.get("mark_breakdown") or None,
                    additional_guidance = row.get("additional_guidance") or None,
                    eval_prompt         = row.get("eval_prompt") or None,
                    verification_status = row.get("verification_status") or None,
                )
                q.paper = paper
                session.add(q)

                for ans in row.get("answers", []):
                    ev      = ans.get("evaluation", {}) or {}
                    vf      = ans.get("verification", {}) or {}
                    verdict = vf.get("verdict")
                    awarded = ev.get("awarded_marks")
                    a = Answer(
                        category     = ans.get("category", ""),
                        answer_text  = ans.get("answer_text", ""),
                        awarded_marks= int(awarded) if isinstance(awarded, (int, float)) else None,
                        verified     = (verdict == "pass") if verdict in ("pass", "fail") else None,
                    )
                    a.question = q
                    session.add(a)

                # Read image bytes → save to DB → mark file for deletion
                image_path = row.get("image_path", "")
                if image_path and os.path.exists(image_path):
                    try:
                        with open(image_path, "rb") as f:
                            img_bytes = f.read()
                        img = DBImage(
                            figure_number = str(row.get("figure_number") or ""),
                            image_bytes   = img_bytes,
                            mime_type     = "image/png",
                        )
                        img.question = q
                        session.add(img)
                    except Exception as exc:
                        print(f"  Warning: could not read image {image_path}: {exc}")

            await session.commit()
            await session.refresh(paper)
            saved_paper_id = paper.id

        await engine.dispose()

        return saved_paper_id

    paper_id = None
    try:
        paper_id = asyncio.run(_persist())
        print(f"\n  Saved {len(rows)} question(s) to database (paper_id={paper_id}).")
        # Temp files for this run are removed by the runner's finally block —
        # see run_pipeline_with_params / run_pipeline. This keeps cleanup scoped
        # to the current run's folder so concurrent runs never delete each other.
    except Exception as exc:
        print(f"\n  DB save failed: {exc}")

    return {**state, "status": "done", "paper_id": paper_id}


# ─────────────────────────────────────────────────────────────────────────────
# Graph assembly
# ─────────────────────────────────────────────────────────────────────────────

def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("parse_metadata",       node_parse_metadata)
    builder.add_node("downloader_extractor", node_downloader_extractor)
    builder.add_node("generate_prompts",     node_generate_prompts)
    builder.add_node("generate_answers",     node_generate_answers)
    builder.add_node("evaluate_answers",     node_evaluate_answers)
    builder.add_node("verify_and_refine",    node_verify_and_refine)
    builder.add_node("save_to_db",           node_save_to_db)

    builder.set_entry_point("parse_metadata")
    builder.add_edge("parse_metadata",       "downloader_extractor")
    builder.add_edge("downloader_extractor", "generate_prompts")
    builder.add_edge("generate_prompts",     "generate_answers")
    builder.add_edge("generate_answers",     "evaluate_answers")
    builder.add_edge("evaluate_answers",     "verify_and_refine")
    builder.add_edge("verify_and_refine",    "save_to_db")
    builder.add_edge("save_to_db",           END)

    return builder.compile()


# ─────────────────────────────────────────────────────────────────────────────
# Public runner
# ─────────────────────────────────────────────────────────────────────────────

def _make_initial_state(qp_url, qp_meta, ms_url, ms_meta) -> AgentState:
    return {
        "qp_url":          qp_url,
        "qp_metadata_raw": qp_meta,
        "ms_url":          ms_url,
        "ms_metadata_raw": ms_meta,
        "retry_count":     0,
        "status":          "ok",
    }


def run_pipeline() -> None:
    """Interactive CLI entry point."""
    qp_url  = input("Enter Question Paper PDF link: ").strip()
    qp_meta = input("Enter QP metadata (e.g. 'Edexcel GCSE Mathematics 2023 Paper 1H'): ").strip()
    ms_url  = input("Enter Mark Scheme PDF link: ").strip()
    ms_meta = input("Enter MS metadata (e.g. 'Edexcel GCSE Mathematics 2023 Paper 1H Mark Scheme'): ").strip()

    graph = build_graph()

    print("\n" + "█"*60)
    print("  PIPELINE STARTED")
    print("█"*60)

    run_dir = set_run_dir(os.path.join(TMP_DIR, f"run_{uuid.uuid4().hex[:12]}"))
    try:
        for event in graph.stream(_make_initial_state(qp_url, qp_meta, ms_url, ms_meta), stream_mode="updates"):
            _print_event(event)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
        clear_run_dir()

    print("\n" + "█"*60)
    print("  PIPELINE COMPLETE")
    print("█"*60)


_NODE_PROGRESS = {
    "parse_metadata":       ("Downloading and extracting questions…", 5),
    "downloader_extractor": ("Generating grading prompts…",          20),
    "generate_prompts":     ("Generating student answers…",          35),
    "generate_answers":     ("Evaluating answers…",                  55),
    "evaluate_answers":     ("Verifying grades…",                    75),
    "verify_and_refine":    ("Saving to database…",                  90),
    "save_to_db":           ("Done!",                               100),
}


def run_pipeline_with_params(
    qp_url: str,
    qp_metadata_raw: str,
    ms_url: str,
    ms_metadata_raw: str,
    progress_cb=None,
) -> int | None:
    """Programmatic entry point used by the FastAPI server. Returns the saved paper_id."""
    if progress_cb:
        set_callback(progress_cb)
        progress_cb("Starting pipeline…", 0)

    graph = build_graph()

    print("\n" + "█"*60)
    print("  PIPELINE STARTED (API)")
    print("█"*60)

    run_dir = set_run_dir(os.path.join(TMP_DIR, f"run_{uuid.uuid4().hex[:12]}"))
    accumulated: dict = {}
    try:
        for event in graph.stream(
            _make_initial_state(qp_url, qp_metadata_raw, ms_url, ms_metadata_raw),
            stream_mode="updates",
        ):
            _print_event(event)
            for node_name, updates in event.items():
                if node_name.startswith("__"):
                    continue
                if isinstance(updates, dict):
                    accumulated.update(updates)
                if node_name in _NODE_PROGRESS:
                    msg, pct = _NODE_PROGRESS[node_name]
                    _progress(msg, pct)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
        clear_run_dir()
        if progress_cb:
            clear_callback()

    print("\n" + "█"*60)
    print("  PIPELINE COMPLETE")
    print("█"*60)

    return accumulated.get("paper_id")


def _print_event(event: dict) -> None:
    """Print only meaningful node activity — suppress raw message dumps."""
    for node_name, data in event.items():
        if node_name.startswith("__"):
            continue
        messages = data.get("messages", []) if isinstance(data, dict) else []
        for msg in messages:
            msg_type = type(msg).__name__
            if msg_type == "AIMessage":
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
                        print(f"  [{node_name}] Tool: {tc['name']}({args_preview})")
            elif msg_type == "ToolMessage":
                raw_tool = msg.content
                content  = raw_tool if isinstance(raw_tool, str) else str(raw_tool)
                content  = content.strip()
                preview  = content[:120] + "..." if len(content) > 120 else content
                print(f"  [{node_name}] {msg.name} -> {preview}")
