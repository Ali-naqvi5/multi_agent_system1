import base64
import json
import os
import re
import tempfile
import time

import requests
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

from config.settings import LLM_MODEL_FAST, LLM_MODEL_SMART, LLM_TEMPERATURE, get_run_dir, invoke_with_retry, invoke_with_retry_slow, extract_text


_llm_fast = ChatGoogleGenerativeAI(
    model=LLM_MODEL_FAST,
    temperature=LLM_TEMPERATURE,
    request_timeout=180,
    max_retries=1,
)


_llm_smart = ChatGoogleGenerativeAI(
    model=LLM_MODEL_SMART,
    temperature=LLM_TEMPERATURE,
    request_timeout=180,
    max_retries=1,
)


# -----------------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------------

def _clean_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"```[a-z]*", "", raw).strip("` \n")
    return raw


def _page_has_visuals(page) -> bool:
    """True if the page contains at least one embedded raster image."""
    return bool(page.get_images(full=False))


def _download_pdf(url: str, retries: int = 3) -> bytes:
    """Download a PDF's bytes with retry + timeout so a slow or flaky host
    (e.g. Physics & Maths Tutor) doesn't kill the whole run.

    Retries on read/connect timeouts, dropped connections, and 5xx responses
    with exponential backoff; fails fast on 4xx (a genuinely bad URL).
    Timeout is (15s connect, 120s read).
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=(15, 120))
            resp.raise_for_status()
            return resp.content
        except requests.HTTPError as e:
            # 4xx means the URL itself is wrong — retrying won't help.
            if e.response is not None and 400 <= e.response.status_code < 500:
                raise
            last_err = e
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
        if attempt < retries - 1:
            time.sleep(2 ** attempt)  # 1s, 2s backoff between attempts
    raise last_err  # type: ignore[misc]


# =============================================================================
# TEXT BRANCH
# =============================================================================

@tool
def extract_pdf_text(url: str, mode: str = "QP") -> str:
    """
    Downloads and extracts plain text from a PDF at the given URL.

    Args:
        url:  Direct URL to the PDF file.
        mode: "QP" for question paper, "MS" for mark scheme.

    Returns JSON string:
        {"text": str, "pages": int, "mode": str, "error": str}
    """
    tmp_path = None
    try:
        from langchain_community.document_loaders import PyPDFLoader
        # Download with retry/timeout, then load from a local file (more reliable
        # than letting PyPDFLoader fetch the URL itself with no timeout control).
        pdf_bytes = _download_pdf(url)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        pages = PyPDFLoader(tmp_path).load()
        text  = "\n\n--- PAGE BREAK ---\n\n".join(
            p.page_content for p in pages if p.page_content
        )
        return json.dumps({
            "text":  text,
            "pages": len(pages),
            "mode":  mode,
            "error": "",
        })
    except Exception as e:
        return json.dumps({"text": "", "pages": 0, "mode": mode, "error": str(e)})
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@tool
def merge_qp_ms_rows(qp_data: str, ms_data: str, metadata: str) -> str:
    """
    Uses Gemini to match question paper text with mark scheme text and produce
    structured rows ready for downstream grading.

    Args:
        qp_data:  Plain text extracted from the question paper PDF.
        ms_data:  Plain text extracted from the mark scheme PDF.
        metadata: JSON string — {"paper": str, "board": str, "level": str, "subject": str}

    Returns JSON string:
        {"rows": [{"paper", "board", "level", "subject", "question_number",
                   "question_text", "marks", "answer", "mark_breakdown",
                   "additional_guidance"}, ...]}
    """
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        meta = {}

    prompt = f"""You are an expert UK exam paper analyst.

## Ground Truth (embed these values in EVERY row):
  paper:   {meta.get('paper', 'unknown')}
  board:   {meta.get('board', 'unknown')}
  level:   {meta.get('level', 'unknown')}
  subject: {meta.get('subject', 'unknown')}

## Question Paper Text:
{qp_data[:15000]}

## Mark Scheme Text:
{ms_data[:15000]}

## Instructions:
- Produce one JSON row per question found in the Question Paper text.
- Match each question to its mark scheme entry by question number.
- Every row MUST have paper/board/level/subject filled from Ground Truth above.
- question_number: the question label exactly as it appears (e.g. "1", "2a", "3b")
- question_text: full question text as written in the Question Paper
- marks: integer, extract from "[X marks]" or "(X)" notation, else 0
- answer: correct answer from Mark Scheme — search ENTIRE MS text for this question
- mark_breakdown: REQUIRED. Search the ENTIRE mark scheme text for this question number.
  Extract every individual mark allocation line (M1, A1, B1, B2 etc.) with its description.
  Format as pipe-separated string e.g. "M1: correct substitution | A1: correct answer | B1: unit".
  If the mark scheme shows a table or bullet list, convert each line to this format.
  Do NOT leave this empty if the mark scheme has any content for this question.

- additional_guidance: REQUIRED. Search the ENTIRE mark scheme text for examiner notes,
  "accept", "allow", "ignore", "do not accept", "note", or "guidance" sections
  associated with this question. Copy them verbatim as a single string.
  Do NOT leave this empty if any guidance exists in the mark scheme for this question.
- Try all numbering variants (e.g. "Q1", "1", "01", "Question 1")
- Do not fabricate — only use what is in the texts above
- figure_number: the figure number this question refers to.
  Extract from question text e.g. "refer to Figure 1" -> "1". Leave "" if none.
- table_number: the table number this question refers to.
  Extract from question text e.g. "refer to Table 2" -> "2". Leave "" if none.
- question_number: already defined above — this is the question label as printed.

## Equations, Formulas & Mathematical Notation:
The output is rendered in HTML using MathJax, so all mathematical content MUST be written
as proper LaTeX, wrapped in delimiters: inline math uses $...$ and standalone/display
equations use $$...$$. Do NOT use plain-ASCII workarounds like x^2 or sqrt(x) — use real
LaTeX commands (\\frac{{}}{{}}, ^{{}}, _{{}}, \\sqrt{{}}, \\int, \\sum, \\lim, \\to, etc.)

CRITICAL — JSON ESCAPING: Your output is a JSON string, so every backslash in a LaTeX
command MUST be written as a DOUBLE backslash. Write \\frac, \\times, \\rightarrow,
\\rightleftharpoons, \\Delta, \\sqrt, \\log, \\int, \\sum, \\lim, \\neq, \\geq, \\leq,
\\approx, \\text, \\dfrac — NEVER a single backslash. A single backslash before a letter
(e.g. \times, \frac) is INVALID JSON and will corrupt the output. This rule applies to
EVERY LaTeX command used anywhere in your output, in both math and chemistry content.

Examples:
  "The gradient of $y = x^3 - 4x$ is $\\frac{{dy}}{{dx}} = 3x^2 - 4$"
  "Solve $\\int_0^2 (3x^2 + 1)\\,dx$"
  "Show that $\\frac{{x+1}}{{x^2-1}}$ simplifies to $\\frac{{1}}{{x-1}}$ for $x \\neq -1$"
  "Given $F = \\frac{{mv^2}}{{r}}$, find $F$ when $m = 2$, $v = 3$, $r = 0.5$"
  "Prove that $\\sum_{{i=1}}^{{n}} i = \\frac{{n(n+1)}}{{2}}$"
  "Find $\\lim_{{x \\to 0}} \\frac{{\\sin x}}{{x}}$"
  "The equation of the circle is $(x-3)^2 + (y+1)^2 = 25$"
  "$[H^+] = 10^{{-pH}}$, so $pH = -\\log_{{10}}[H^+]$"
  "$E_k = \\frac{{1}}{{2}}mv^2$"
  "$\\lambda = \\frac{{h}}{{mv}}$ (de Broglie wavelength)"

## Chemistry notation:
Chemical formulas and equations also use LaTeX for subscripts/superscripts/charges so
they render correctly in HTML.

- Chemical formulas:   $H_2O$, $CO_2$, $H_2SO_4$, $Ca(OH)_2$
- Charges/ions:        $H^+$, $OH^-$, $Fe^{{2+}}$, $SO_4^{{2-}}$, $PO_4^{{3-}}$
- Isotope notation:    $^{{14}}_{{6}}C$ or write as "Carbon-14"
- Equations:           use $\\rightarrow$ for forward reaction, $\\rightleftharpoons$ for
                       reversible/equilibrium
- State symbols:       (s), (l), (g), (aq) — keep as plain text
- Concentration:       $[HCl] = 0.1 \\text{{ mol/dm}}^3$
- Equilibrium const:   $K_c = \\dfrac{{[products]}}{{[reactants]}}$
- Enthalpy:            $\\Delta H = -286 \\text{{ kJ/mol}}$
- Activation energy:   $E_a$
- Rate equation:       $rate = k[A]^m[B]^n$
- Half-equation:       $Fe \\rightarrow Fe^{{2+}} + 2e^-$  or  $O_2 + 4H^+ + 4e^- \\rightarrow 2H_2O$
- Moles/amounts:       $n = \\frac{{m}}{{M}}$, $n = cv$
- Avogadro:            $6.022 \\times 10^{{23}}$
- pH / pKa:            $pH = -\\log_{{10}}[H^+]$, $pK_a = -\\log_{{10}}K_a$
- Organic notation:    write IUPAC names in full (e.g. ethanoic acid), structural formulas
                       as $CH_3COOH$, $C_2H_5OH$, $CH_2=CH_2$, $CH \\equiv CH$
- Benzene ring:        write as $C_6H_6$ or "benzene ring" (no structural diagrams)
- Mechanisms:          use $\\rightarrow$ for reaction direction; describe arrow-pushing
                       in words, e.g. "nucleophile attacks carbon, bond forms, leaving
                       group departs"

Examples:
  "$2H_2(g) + O_2(g) \\rightarrow 2H_2O(l)$, $\\Delta H = -572 \\text{{ kJ/mol}}$"
  "$CH_3COOH(aq) \\rightleftharpoons CH_3COO^-(aq) + H^+(aq)$"
  "$K_c = \\dfrac{{[NH_3]^2}}{{[N_2][H_2]^3}}$"
  "$Fe^{{2+}}(aq) \\rightarrow Fe^{{3+}}(aq) + e^-$"
  "$rate = k[NO]^2[O_2]$"
  "$pH = -\\log_{{10}}(1.5 \\times 10^{{-3}})$"
  "$n(HCl) = 0.25 \\times 0.1 = 0.025 \\text{{ mol}}$"
  "$M_r(H_2SO_4) = 2 + 32 + 64 = 98 \\text{{ g/mol}}$"
  "$CH_2=CH_2 + HBr \\rightarrow CH_3CH_2Br$"
  "$Ca^{{2+}}(aq) + CO_3^{{2-}}(aq) \\rightarrow CaCO_3(s)$"

Return ONLY valid JSON, no markdown, no explanation:
{{"rows": [
  {{
    "paper": "{meta.get('paper', 'unknown')}",
    "board": "{meta.get('board', 'unknown')}",
    "level": "{meta.get('level', 'unknown')}",
    "subject": "{meta.get('subject', 'unknown')}",
    "question_number": "1",
    "figure_number": "",
    "table_number":    "",
    "question_text":   "...",
    "marks": 0,
    "answer": "...",
    "mark_breakdown": "...",
    "additional_guidance": "..."
  }}
]}}"""

    response = invoke_with_retry_slow(_llm_smart, prompt)
    cleaned = _clean_json(extract_text(response))
    try:
        parsed = json.loads(cleaned)
        return json.dumps(parsed)
    except json.JSONDecodeError:
        return json.dumps({"rows": [], "error": "LLM returned invalid JSON"})


# =============================================================================
# VISION BRANCH
# =============================================================================

@tool
def scan_and_render_visual_pages(url: str, mode: str = "QP", paper_label: str = "") -> str:
    """
    Downloads a PDF, identifies pages that contain raster images using
    _page_has_visuals(), and renders ONLY those pages as PNG files saved to disk.
    Filenames embed the paper label for traceability.

    Args:
        url:         Direct URL to the PDF file.
        mode:        "QP" or "MS" — used to name the output folder.
        paper_label: Human-readable paper identifier embedded in output filenames,
                     e.g. "AQA_GCSE_Biology_2023_QP".

    Returns JSON string:
        {
          "pages": [{"page_number": int, "page_index": int, "file_path": str}, ...],
          "visual_page_indices": [int, ...],
          "total_pages": int,
          "mode": str,
          "error": str
        }

    Only pages where _page_has_visuals() returns True are rendered and returned.
    page_index is 0-based; page_number is 1-based.
    """
    try:
        import fitz  # PyMuPDF

        # Download PDF (retry/timeout via shared helper)
        pdf_bytes = _download_pdf(url)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        safe_paper = re.sub(r"[^a-zA-Z0-9_-]", "_", paper_label)[:60] if paper_label else re.sub(r"[^a-zA-Z0-9_-]", "_", url[-30:])
        pages_dir  = os.path.join(get_run_dir(), f"visual_{mode}_{safe_paper}")
        os.makedirs(pages_dir, exist_ok=True)

        doc            = fitz.open(tmp_path)
        total          = len(doc)
        matrix         = fitz.Matrix(150 / 72, 150 / 72)  # 150 DPI for clean crops
        pages          = []
        visual_indices = []

        for page_index in range(total):
            page = doc[page_index]
            if not _page_has_visuals(page):
                continue
            visual_indices.append(page_index)
            page_number = page_index + 1
            file_path   = os.path.join(pages_dir, f"{safe_paper}_{mode}_page_{page_number:04d}.png")
            if not os.path.exists(file_path):
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                pix.save(file_path)
            pages.append({
                "page_number": page_number,
                "page_index":  page_index,
                "file_path":   file_path,
            })

        doc.close()
        os.unlink(tmp_path)

        return json.dumps({
            "pages":               pages,
            "visual_page_indices": visual_indices,
            "total_pages":         total,
            "mode":                mode,
            "error":               "",
        })

    except Exception as e:
        return json.dumps({"pages": [], "visual_page_indices": [], "total_pages": 0, "mode": mode, "error": str(e)})


@tool
def detect_diagram_bboxes(file_paths_json: str, metadata: str, paper_label: str = "") -> str:
    """
    Sends rendered visual pages to Gemini Vision to detect diagram bounding boxes.
    For each diagram found, returns the page_index (0-based), the question number
    it belongs to, and its bounding box normalized to 0-1000.

    Args:
        file_paths_json: JSON array of objects: [{"page_index": int, "file_path": str}, ...]
        metadata:        JSON string — {"board": str, "level": str, "subject": str}
        paper_label:     Paper identifier for prompt context.

    Returns JSON string:
        {
          "detections": [
            {
              "page_index": int,
              "file_path": str,
              "question_number": str,
              "bbox": [ymin, xmin, ymax, xmax]
            }
          ],
          "error": str
        }

    bbox values are integers in [0, 1000] where (0,0) is top-left of the page image.
    """
    try:
        try:
            meta = json.loads(metadata)
        except json.JSONDecodeError:
            meta = {}

        try:
            page_entries = json.loads(file_paths_json)
        except (json.JSONDecodeError, TypeError):
            page_entries = []

        board   = meta.get("board",   "unknown")
        level   = meta.get("level",   "unknown")
        subject = meta.get("subject", "unknown")

        valid_entries = [
            e for e in page_entries
            if isinstance(e, dict) and os.path.exists(e.get("file_path", ""))
        ]
        if not valid_entries:
            return json.dumps({"detections": [], "error": "No valid page files provided"})

        from langchain_core.messages import HumanMessage

        BATCH_SIZE  = 4
        instruction = f"""These pages are from a {board} {level} {subject} Question Paper: "{paper_label}".

For EVERY diagram, figure, graph, or table visible across all pages:

#Instructions:
- Identify and extract ALL scientific/technical diagrams, including graphs, charts with axes, tables of data, apparatus setups, circuit diagrams, molecular structures, biological illustrations, maps, geometric figures etc.
A "diagram" includes: scientific/technical illustrations (molecular structures, 
circuit diagrams, apparatus setups, biological diagrams, maps, graphs/charts with 
axes, geometric figures, tables of data).

A "diagram" does NOT include: checkboxes, tick boxes, multiple-choice option 
bubbles/letters (A/B/C/D), answer lines, ruled writing space, exam logos, 
page headers/footers, question number boxes, or borders/frames with no 
scientific content inside them.

If you are uncertain whether something is a diagram or just a UI/answer element, 
DO NOT include it.

Steps to extract each diagram:
1. Record the page_index (0-based integer) of the page where the diagram appears.
   Each page was labelled [Page page_index=N] immediately after the image above.
2a. REQUIRED — always populate question_number.
    Find the nearest question label printed above, beside, or below the visual
    (e.g. "Question 1", "2(a)", "3b", "Q4"). Return just the label as printed
    (e.g. "3b", not "Question 3b"). If no label is directly adjacent, scan
    the surrounding text to identify which question this diagram accompanies
    and use that number. Only leave as "" if the diagram is genuinely a
    standalone page illustration with absolutely no associated question.
    This field is required even when figure_number or table_number is also set.
2b. Identify the figure number if the visual is labelled "Figure N" — return "N".
    If it is not a labelled figure, use "".
2c. Identify the table number if the visual is labelled "Table N" — return "N".
    If it is not a labelled table, use "".
3. Return the bounding box of the diagram as [ymin, xmin, ymax, xmax] where each
   value is an integer normalized to 0-1000 relative to that page image's dimensions.
   - (0, 0) = top-left corner of the page image.
   - (1000, 1000) = bottom-right corner of the page image.
   - ymin < ymax, xmin < xmax.
4. If one diagram clearly belongs to multiple questions, include it once for the primary question.
5. If a page has no diagrams, skip it entirely — do NOT output empty detections.
6.Before finalizing each bbox, check: does this box contain everything that 
   visually belongs to this figure number, including any labels, sub-panel 
   letters, or axes? If parts of the figure extend outside your box, expand 
   the box to include them.
Return ONLY valid JSON, no markdown, no explanation:
{{"detections": [
  {{
    "page_index": 0,
    "question_number": "2",   <- question label printed nearest the visual (e.g. "1", "2a", "3(b)")
    "figure_number": "1",      <- Figure N label printed on/near the visual, or "" if none
    "table_number": "1",       <- Table N label printed on/near the visual, or "" if none
    "bbox": [100, 50, 400, 600]
  }}
], "error": ""}}"""

        all_detections = []
        batches = [valid_entries[i:i + BATCH_SIZE] for i in range(0, len(valid_entries), BATCH_SIZE)]
        for batch in batches:
            content_blocks = []
            for entry in batch:
                with open(entry["file_path"], "rb") as f:
                    page_b64 = base64.b64encode(f.read()).decode("utf-8")
                content_blocks.append(
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{page_b64}"}}
                )
                content_blocks.append(
                    {"type": "text", "text": f"[Page page_index={entry['page_index']}]"}
                )
            content_blocks.append({"type": "text", "text": instruction})
            message  = HumanMessage(content=content_blocks)
            response = invoke_with_retry(_llm_fast, [message])
            raw      = _clean_json(extract_text(response))
            parsed   = json.loads(raw)
            all_detections.extend(parsed.get("detections", []))

        idx_to_path = {e["page_index"]: e["file_path"] for e in valid_entries}
        detections  = []
        for det in all_detections:
            pidx = det.get("page_index")
            detections.append({
                "page_index":      pidx,
                "file_path":       idx_to_path.get(pidx, ""),
                "question_number": str(det.get("question_number", "")).strip(),
                "figure_number":   str(det.get("figure_number", "")).strip(),
                "table_number":    str(det.get("table_number", "")).strip(),
                "bbox":            det.get("bbox", [0, 0, 1000, 1000]),
            })

        return json.dumps({"detections": detections, "error": ""})

    except Exception as e:
        return json.dumps({"detections": [], "error": str(e)})


@tool
def crop_and_save_diagrams(detections_json: str, paper_label: str = "", paper_number: int = 1) -> str:
    """
    Uses PIL to crop each detected diagram from its rendered page image using the
    bounding box returned by detect_diagram_bboxes. Saves each crop as a PNG file
    in a per-paper subfolder with a name encoding the paper label, paper number,
    and figure/table identifier for traceability.

    Args:
        detections_json: JSON from detect_diagram_bboxes — either the full response
                         dict {"detections": [...]} or a bare list of detection objects.
                         Each detection must have: page_index, file_path,
                         question_number, bbox ([ymin, xmin, ymax, xmax] in 0-1000).
        paper_label:     Paper identifier embedded in output filenames,
                         e.g. "AQA_GCSE_Biology_2023_QP".
        paper_number:    1-based index of this paper within the current batch.
                         Used to create a dedicated subfolder and embed in filenames.

    Returns JSON string:
    {
      "saved_diagrams": [
        {
          "question_number": str,
          "figure_number":   str,
          "table_number":    str,
          "file_path":       str
        }, ...
      ],
      "error": str
    }
    """
    try:
        from PIL import Image

        try:
            payload = json.loads(detections_json)
            detections = payload.get("detections", payload) if isinstance(payload, dict) else payload
        except (json.JSONDecodeError, TypeError):
            detections = []

        safe_paper = re.sub(r"[^a-zA-Z0-9_-]", "_", paper_label)[:60] if paper_label else "paper"
        paper_dir = os.path.join(get_run_dir(), safe_paper)

        os.makedirs(paper_dir, exist_ok=True)
        saved      = []

        for det in detections:
            src_path = det.get("file_path", "")
            q_num    = str(det.get("question_number", "")).strip()
            f_num    = str(det.get("figure_number",   "")).strip()
            t_num    = str(det.get("table_number",    "")).strip()
            bbox     = det.get("bbox", [])

            # Need a valid source image, at least one identifier, and a valid bbox
            primary = q_num or f_num or t_num
            if not src_path or not os.path.exists(src_path) or not primary or len(bbox) != 4:
                continue

            ymin, xmin, ymax, xmax = bbox
            img  = Image.open(src_path)
            W, H = img.size

            # Convert normalized 0-1000 coords to pixel coords
            left  = int(xmin / 1000 * W)
            upper = int(ymin / 1000 * H)
            right = int(xmax / 1000 * W)
            lower = int(ymax / 1000 * H)

            # Clamp to image bounds
            left,  upper = max(0, left),  max(0, upper)
            right, lower = min(W, right), min(H, lower)

            if right <= left or lower <= upper:
                continue

            crop = img.crop((left, upper, right, lower))

            # Build filename: figure/table identifier takes priority over question number
            if f_num:
                safe_id      = re.sub(r"[^a-zA-Z0-9_-]", "_", f_num)
                out_filename = f"{safe_paper}_Figure{safe_id}.png"
            elif t_num:
                safe_id      = re.sub(r"[^a-zA-Z0-9_-]", "_", t_num)
                out_filename = f"{safe_paper}_Table{safe_id}.png"
            else:
                safe_id      = re.sub(r"[^a-zA-Z0-9_-]", "_", q_num)
                out_filename = f"{safe_paper}_Q{safe_id}.png"
            out_path = os.path.join(paper_dir, out_filename)
            crop.save(out_path)

            saved.append({
                "question_number": q_num,
                "figure_number":   f_num,
                "table_number":    t_num,
                "file_path":       out_path,
            })

        return json.dumps({"saved_diagrams": saved, "error": ""})

    except Exception as e:
        return json.dumps({"saved_diagrams": [], "error": str(e)})








