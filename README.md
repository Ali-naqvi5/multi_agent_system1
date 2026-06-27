# ExamEval — Past Paper AI Pipeline

A multi-agent system that takes a UK past exam paper (Question Paper + Mark Scheme) as PDF links, extracts every question with its diagram, generates AI student answers across multiple ability levels, grades them, and stores everything in a database — all accessible through a web UI.

---

## Architecture

```
[FastAPI] ← HTTP
    │
    ▼
[LangGraph Orchestrator]
    │
    ├── Node 1: parse_metadata
    │     Parses raw metadata string → board, level, subject, year, paper code
    │
    ├── Node 2: downloader_extractor  (Agent 2)
    │     Downloads both PDFs → renders pages as 150 DPI PNGs (PyMuPDF)
    │     Gemini Vision detects diagrams with bounding boxes
    │     Crops and saves diagram images; extracts question + mark scheme rows
    │
    ├── Node 3: generate_prompts  (Agent 3)  ← ThreadPoolExecutor × 5
    │     For each question, builds a grading prompt (question text + mark scheme)
    │
    ├── Node 4: generate_answers  (Agent 4)  ← ThreadPoolExecutor × 5
    │     Generates 10 student answers per question at varying ability levels
    │
    ├── Node 5: evaluate_answers  (Agent 5)  ← batch (10 answers → 1 call) + ThreadPoolExecutor
    │     Scores each answer against the mark scheme; returns awarded_marks + reasoning
    │
    ├── Node 6: verify_and_refine  (Agent 6)  ← batch + ThreadPoolExecutor
    │     Verifies each score independently; re-grades if verdict is "fail"
    │     Marks question as validated / unconvergeable after max retries
    │
    └── Node 7: save_to_db
          Persists Paper, Questions (with images as BYTEA), and Answers to PostgreSQL
```

---

## Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph + LangChain |
| LLMs | Gemini 3.5 Flash (fast, 15 RPM) · Gemini 2.5 Flash (smart, 10 RPM) |
| PDF rendering | PyMuPDF → PNG at 150 DPI |
| Vision extraction | Gemini Vision — bounding boxes [ymin, xmin, ymax, xmax] normalised 0–1000 |
| API | FastAPI + Uvicorn |
| Database | PostgreSQL 16 (Docker) · SQLAlchemy async ORM |
| Frontend | Next.js 15 (App Router) · Tailwind CSS · KaTeX (LaTeX rendering) |

---

## Project Structure

```
multi_agent_system/
├── Backend/
│   ├── agents/
│   │   ├── agent2_downloader_extractor.py   # PDF download, vision extraction, crop
│   │   ├── agent3_prompt_generator.py        # Grading prompt builder (fast model)
│   │   ├── agent4_answer_generator.py        # Student answer generator
│   │   ├── agent5_evaluator.py               # Batch evaluator (fast model)
│   │   └── agent6_verifier.py                # Batch verifier + refine loop (fast model)
│   ├── api/
│   │   ├── app.py                            # FastAPI app + routers
│   │   ├── schemas.py                        # Pydantic request/response models
│   │   ├── deps.py                           # DB session dependency
│   │   └── routers/
│   │       ├── pipeline.py                   # POST /run, GET /status/{job_id}
│   │       └── papers.py                     # GET /papers, GET /papers/{id}, GET /images/{id}
│   ├── config/settings.py                    # LLM models, retry helpers, paths
│   ├── db/models.py                          # SQLAlchemy ORM: Paper, Question, Answer
│   ├── graph/
│   │   ├── orchestrator.py                   # LangGraph StateGraph + run_pipeline_with_params
│   │   ├── state.py                          # AgentState TypedDict
│   │   └── progress.py                       # Thread-safe progress callback
│   ├── docker-compose.yml                    # PostgreSQL 16 with named volume
│   └── main.py                               # Uvicorn entry point
└── Frontend/
    ├── app/
    │   ├── layout.tsx                        # Navbar, KaTeX CSS, global layout
    │   ├── page.tsx                          # Pipeline runner form + live progress bar
    │   └── papers/
    │       ├── page.tsx                      # Papers list with board-coloured cards
    │       └── [id]/page.tsx                 # Paper detail: stats + question cards
    ├── components/
    │   ├── QuestionCard.tsx                  # Collapsible question with diagram, mark scheme, answers
    │   └── MathText.tsx                      # LaTeX renderer (react-latex-next + KaTeX)
    └── lib/api.ts                            # Typed API client
```

---

## Setup

### 1. Database (Docker)

```bash
cd Backend
docker compose up -d
```

This starts PostgreSQL 16 on port `5432`. Data persists in the named Docker volume `pgdata` — safe to `docker compose down` without data loss. Only `docker compose down -v` removes the volume.

### 2. Backend

```bash
cd Backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Create `Backend/.env`:

```env
GEMINI_API_KEY=your_key_here
DATABASE_URL=postgresql+asyncpg://exam:exam@localhost:5432/exam_eval
```

Start the API:

```bash
python -m uvicorn api.app:app --reload --port 8000
```

The API creates database tables on first startup.

### 3. Frontend

```bash
cd Frontend
npm install --legacy-peer-deps
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

The frontend expects the API at `http://localhost:8000`. Override via `Frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Usage

1. Navigate to **Run Pipeline** (`/`)
2. Paste the PDF URL and metadata for the Question Paper and Mark Scheme
3. Click **Run Pipeline** — a live progress bar shows the current node
4. On completion, click **View Results** to browse extracted questions, diagrams, and AI-graded answers
5. All past runs are available under **Browse Papers** (`/papers`)

---

## Environment Variables

| Variable | Where | Description |
|---|---|---|
| `GEMINI_API_KEY` | `Backend/.env` | Google Gemini API key |
| `DATABASE_URL` | `Backend/.env` | Async PostgreSQL connection string |
| `NEXT_PUBLIC_API_URL` | `Frontend/.env.local` | Backend base URL (default: `http://localhost:8000`) |

---

## Performance

For a 50-question paper, approximate runtimes after optimisation:

| Node | Calls | Time |
|---|---|---|
| Node 2 — extraction | 1 batch | ~3 min |
| Node 3 — prompts | 50 (×5 parallel) | ~4 min |
| Node 4 — answers | 50 (×5 parallel) | ~3 min |
| Node 5 — evaluate | 50 batch calls (×5 parallel) | ~6 min |
| Node 6 — verify | 50 batch calls (×5 parallel) | ~8 min |
| **Total** | | **~25 min** |

