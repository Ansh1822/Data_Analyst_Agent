"""Runs the whole graph with a fake LLM, so it needs no API key and proves the wiring works."""
import asyncio
import json
import shutil
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import llm  # noqa: E402
from app.config import RUNS_DIR  # noqa: E402
from app.graph import graph  # noqa: E402
from app.prompts import CODER_SYSTEM, PLAN_SYSTEM  # noqa: E402
from app.sandbox import check_code  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[2] / "sample_data" / "sales.csv"


async def fake_complete(system, user):
    if system == PLAN_SYSTEM:
        return json.dumps([{"title": "Revenue by region", "goal": "Compare regions"},
                           {"title": "Category mix", "goal": "Chart categories"}])
    if system == CODER_SYSTEM:
        if "Current step (1/" in user:
            if "It failed with" not in user:  # first try has a deliberate bug
                return "```python\nprint(df['revenue_usd'].sum())\n```"
            return "```python\nprint(duckdb.sql('SELECT region, ROUND(SUM(revenue),2) AS rev FROM df GROUP BY 1 ORDER BY 2 DESC').df().to_string())\n```"
        return ("```python\ndf.groupby('category')['revenue'].sum().plot.bar()\n"
                "plt.title('Revenue by category')\nplt.savefig('charts/step2_cat.png')\nplt.close()\nprint('chart saved')\n```")
    return "## Summary\nDone.\n![Revenue by category](chart:step2_cat.png)"


def test_blocked_code():
    assert check_code("import os\nos.system('ls')")
    assert check_code("open('x.txt','w')")
    assert check_code("df.groupby('a').sum()") is None


def test_agent_self_corrects_and_reports(monkeypatch):
    monkeypatch.setattr(llm, "complete", fake_complete)
    run_id = uuid.uuid4().hex[:12]
    run_dir = RUNS_DIR / "runs" / run_id
    run_dir.mkdir(parents=True)
    shutil.copy(SAMPLE, run_dir / "data.csv")

    async def collect():
        events = []
        init = {"run_id": run_id, "run_dir": str(run_dir), "question": "Which region earns most?"}
        async for upd in graph.astream(init, config={"recursion_limit": 100}, stream_mode="updates"):
            for delta in upd.values():
                events += delta.get("events", [])
        return events

    events = asyncio.run(collect())
    kinds = [e["type"] for e in events]
    results = [e for e in events if e["type"] == "result"]

    assert kinds[0] == "profile" and kinds[1] == "plan" and kinds[-1] == "report"
    assert results[0]["ok"] is False and "revenue_usd" in results[0]["stderr"]   # bug caught
    assert results[1]["ok"] is True and results[1]["attempt"] == 2               # self-fixed
    assert results[2]["charts"] == ["step2_cat.png"]                             # chart produced
    assert f"/api/runs/{run_id}/charts/step2_cat.png" in events[-1]["markdown"]  # URL rewritten
    assert (run_dir / "charts" / "step2_cat.png").exists()
