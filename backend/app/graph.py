"""Section 5 - The agent. A LangGraph state machine:

  profiler -> planner -> coder -> executor --error & attempts left--> coder (fix)
                                    |
                                    +--done--> record --more steps--> coder
                                                  |
                                                  +--no more steps--> reporter -> END
"""
import asyncio
import operator
import re
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from . import llm
from .config import MAX_FIX_ATTEMPTS, MAX_STEPS
from .profiler import load_csv, profile_dataframe, profile_to_text
from .prompts import CODER_SYSTEM, PLAN_SYSTEM, REPORT_SYSTEM
from .sandbox import run_code

MAX_ATTEMPTS = 1 + MAX_FIX_ATTEMPTS


class AgentState(TypedDict, total=False):
    run_id: str
    run_dir: str
    question: str
    profile_text: str
    plan: list            # [{"title", "goal"}]
    step: int             # index of the step being worked on
    attempt: int          # tries used on the current step
    code: str
    last_error: str | None
    last_result: dict
    # Lists with a reducer are appended to, not overwritten:
    findings: Annotated[list, operator.add]
    charts: Annotated[list, operator.add]
    events: Annotated[list, operator.add]   # streamed to the browser
    report: str


async def profiler_node(state: AgentState):
    df = load_csv(Path(state["run_dir"]) / "data.csv")
    profile = profile_dataframe(df)
    return {
        "profile_text": profile_to_text(profile), "step": 0, "attempt": 0, "last_error": None,
        "events": [{"type": "profile", "rows": profile["rows"], "columns": profile["columns"]}],
    }


async def planner_node(state: AgentState):
    question = state.get("question") or "No specific question. Do a general exploratory analysis."
    user = f"Dataset profile:\n{state['profile_text']}\n\nQuestion: {question}\n\nWrite at most {MAX_STEPS} steps."
    raw = await llm.complete(PLAN_SYSTEM, user)
    try:
        plan = [
            {"title": str(s.get("title", "Step"))[:80], "goal": str(s.get("goal", ""))[:300]}
            for s in llm.parse_json_list(raw) if isinstance(s, dict)
        ][:MAX_STEPS]
    except Exception:
        plan = []
    if not plan:  # never leave the agent without a plan
        plan = [{"title": "Explore the data", "goal": question}]
    return {"plan": plan, "events": [{"type": "plan", "steps": plan}]}


async def coder_node(state: AgentState):
    step, attempt = state["step"], state["attempt"] + 1
    spec = state["plan"][step]
    numbered = "\n".join(f"{i + 1}. {p['title']}" for i, p in enumerate(state["plan"]))
    prior = "\n\n".join(f"[{f['title']}]\n{f['output'][:1500]}" for f in state.get("findings", [])) or "(none yet)"
    user = (
        f"Dataset profile:\n{state['profile_text']}\n\n"
        f"Overall question: {state.get('question') or 'general exploration'}\n\n"
        f"Plan:\n{numbered}\n\nFindings so far:\n{prior}\n\n"
        f"Current step ({step + 1}/{len(state['plan'])}): {spec['title']}\nGoal: {spec['goal']}\n"
        f"Chart filename prefix: step{step + 1}"
    )
    is_fix = bool(state.get("last_error"))
    if is_fix:  # self-correction: show the model its own code and the real error
        user += (
            f"\n\nYour previous code:\n```python\n{state['code']}\n```\n"
            f"It failed with:\n{state['last_error']}\n\n"
            "Fix the root cause and return the complete corrected script."
        )
    code = llm.extract_code(await llm.complete(CODER_SYSTEM, user))
    return {"code": code, "attempt": attempt,
            "events": [{"type": "code", "step": step, "attempt": attempt, "code": code, "is_fix": is_fix}]}


async def executor_node(state: AgentState):
    tag = f"step{state['step'] + 1}_try{state['attempt']}"
    res = await asyncio.to_thread(run_code, Path(state["run_dir"]), state["code"], tag)  # don't block the event loop
    error = None if res.ok else (res.stderr or "Script failed with no error output.")[-1500:]
    return {
        "last_error": error,
        "last_result": {"ok": res.ok, "stdout": res.stdout, "charts": res.charts},
        "events": [{"type": "result", "step": state["step"], "attempt": state["attempt"], "ok": res.ok,
                    "stdout": res.stdout, "stderr": res.stderr, "charts": res.charts, "seconds": res.seconds}],
    }


async def record_node(state: AgentState):
    step, res = state["step"], state["last_result"]
    ok = not state.get("last_error")
    output = res["stdout"] if ok else f"FAILED after {state['attempt']} attempts. Last error: {state['last_error']}"
    return {
        "findings": [{"step": step, "title": state["plan"][step]["title"], "ok": ok, "output": output}],
        "charts": res["charts"] if ok else [],
        "step": step + 1, "attempt": 0, "last_error": None, "code": "",
        "events": [{"type": "step_done", "step": step, "status": "ok" if ok else "failed"}],
    }


async def reporter_node(state: AgentState):
    findings = "\n\n".join(
        f"## Step {f['step'] + 1}: {f['title']} ({'ok' if f['ok'] else 'FAILED'})\n{f['output'][:3000]}"
        for f in state["findings"]
    )
    user = (
        f"Question: {state.get('question') or 'general exploration'}\n\nFindings:\n{findings}\n\n"
        f"Available charts: {state.get('charts', [])}"
    )
    md = await llm.complete(REPORT_SYSTEM, user)
    # Turn chart:NAME.png placeholders into real URLs the browser can load.
    md = re.sub(r"\(chart:([\w\-.]+)\)", lambda m: f"(/api/runs/{state['run_id']}/charts/{m.group(1)})", md)
    return {"report": md, "events": [{"type": "report", "markdown": md}]}


def route_after_exec(state: AgentState) -> str:
    return "coder" if state.get("last_error") and state["attempt"] < MAX_ATTEMPTS else "record"


def route_after_record(state: AgentState) -> str:
    return "coder" if state["step"] < len(state["plan"]) else "reporter"


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("profiler", profiler_node)
    g.add_node("planner", planner_node)
    g.add_node("coder", coder_node)
    g.add_node("executor", executor_node)
    g.add_node("record", record_node)
    g.add_node("reporter", reporter_node)
    g.add_edge(START, "profiler")
    g.add_edge("profiler", "planner")
    g.add_edge("planner", "coder")
    g.add_edge("coder", "executor")
    g.add_conditional_edges("executor", route_after_exec, {"coder": "coder", "record": "record"})
    g.add_conditional_edges("record", route_after_record, {"coder": "coder", "reporter": "reporter"})
    g.add_edge("reporter", END)
    return g.compile()


graph = build_graph()
