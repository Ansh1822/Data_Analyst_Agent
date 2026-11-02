# Autonomous Data Analyst Agent

Upload a CSV, ask a question, and an agent plans the analysis, writes pandas/DuckDB-SQL code, runs it in a sandbox,
fixes its own errors, draws charts, and writes a report. Every step streams live to a React UI.

**Stack:** FastAPI, LangGraph, Groq (free tier, Llama 3.3 70B), React + Vite, subprocess or Docker sandbox.

## Run it (Windows-friendly)

Backend (terminal 1):
```
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # then put your free GROQ_API_KEY in .env
uvicorn app.main:app --reload --port 8000
```

Frontend (terminal 2):
```
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

Try it with `sample_data/sales.csv` and ask: "Which region is underperforming, and when did it start?"
(There is a hidden Q3 slump in the West region for the agent to find.)

Tests (no API key needed, uses a fake LLM): `cd backend && python -m pytest tests -q`

## Workflow

```
upload CSV -> profiler -> planner -> [ coder -> executor -> (error? back to coder) -> record ] x steps -> reporter -> report
```

| Node | Uses LLM | Job |
|---|---|---|
| profiler | no | Column types, nulls, ranges, top values |
| planner | yes | 3-5 analysis steps as JSON |
| coder | yes | One Python script per step; on failure it sees its code plus the error |
| executor | no | Runs the script in the sandbox, collects stdout and charts |
| record | no | Saves the finding, moves to the next step |
| reporter | yes | Markdown report using only numbers found in the findings |

## Free-tier notes (Groq)

- Get a free key at https://console.groq.com/keys. No card needed.
- The free tier has per-minute request and token caps. `llm.py` waits and retries automatically on rate-limit errors.
- If you still hit limits, set `ANALYST_MODEL=llama-3.1-8b-instant` (higher limits, slightly weaker code), or lower `MAX_STEPS` in `.env`.
- Model names change over time; check console.groq.com/docs/models if one stops working.

## Safety

1. Static blocklist (no os/sys/subprocess/network/file I/O) before anything runs.
2. Separate process with a timeout and a stripped environment (the GROQ_API_KEY is never visible to generated code).
3. `SANDBOX_MODE=docker`: no network, 512 MB RAM, 1 CPU, read-only filesystem. Build once:
   `docker build -t analyst-sandbox backend/sandbox`

## Deploying

- Backend: Render/Railway/Fly. Set `GROQ_API_KEY`, `CORS_ORIGINS` (your frontend URL), and use `SANDBOX_MODE=docker` or E2B for public demos.
- Frontend: Vercel/Netlify. In production replace the Vite proxy by pointing the `fetch` URLs in `src/api.js` at your backend URL.

## Ideas to extend

- Database connector: read-only SQLAlchemy URL, load query results into `df`.
- Eval set: 10 questions with known answers (the sample data has one), score accuracy and retries per run.
- Tracing: log tokens, latency, and retries per node (Langfuse or your own table).
- Human approval before a step runs, and an E2B sandbox adapter.
