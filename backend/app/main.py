"""Section 6 - API layer: upload a CSV, stream an agent run over SSE, serve charts."""
import json
import re
import shutil
import uuid

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .config import CORS_ORIGINS, MAX_UPLOAD_MB, RUNS_DIR
from .graph import graph
from .profiler import load_csv, profile_dataframe

app = FastAPI(title="Autonomous Data Analyst Agent")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

ID_RE = re.compile(r"^[a-f0-9]{12}$")
CHART_RE = re.compile(r"^[\w\-]+\.png$")


class AnalyzeRequest(BaseModel):
    dataset_id: str
    question: str = ""


def sse(payload: dict) -> str:
    return f"event: {payload['type']}\ndata: {json.dumps(payload)}\n\n"


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "Upload a .csv file.")
    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"File is larger than {MAX_UPLOAD_MB} MB.")
    dataset_id = uuid.uuid4().hex[:12]
    folder = RUNS_DIR / "datasets" / dataset_id
    folder.mkdir(parents=True)
    path = folder / "data.csv"
    path.write_bytes(data)
    try:
        df = load_csv(path)
        if df.empty:
            raise ValueError("The file has no rows.")
    except (pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(400, f"Could not read this CSV: {e}")
    return {"dataset_id": dataset_id, "filename": file.filename, **profile_dataframe(df)}


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    if not ID_RE.match(req.dataset_id):
        raise HTTPException(400, "Invalid dataset id.")
    source = RUNS_DIR / "datasets" / req.dataset_id / "data.csv"
    if not source.exists():
        raise HTTPException(404, "Dataset not found. Upload it again.")

    run_id = uuid.uuid4().hex[:12]
    run_dir = RUNS_DIR / "runs" / run_id
    run_dir.mkdir(parents=True)
    shutil.copy(source, run_dir / "data.csv")  # each run gets its own working folder

    async def stream():
        yield sse({"type": "run_started", "run_id": run_id})
        try:
            init = {"run_id": run_id, "run_dir": str(run_dir), "question": req.question.strip()}
            async for update in graph.astream(init, config={"recursion_limit": 100}, stream_mode="updates"):
                for _node, delta in update.items():
                    for event in (delta or {}).get("events", []):
                        yield sse(event)
            yield sse({"type": "done", "run_id": run_id})
        except Exception as e:  # surface failures in the UI instead of a dead stream
            yield sse({"type": "error", "message": f"{type(e).__name__}: {e}"})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/runs/{run_id}/charts/{name}")
def get_chart(run_id: str, name: str):
    if not ID_RE.match(run_id) or not CHART_RE.match(name):
        raise HTTPException(400, "Bad request.")
    path = RUNS_DIR / "runs" / run_id / "charts" / name
    if not path.exists():
        raise HTTPException(404, "Chart not found.")
    return FileResponse(path, media_type="image/png")
