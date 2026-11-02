import { useReducer, useRef, useState } from "react";
import { streamAnalyze, uploadCsv } from "./api.js";
import Timeline from "./components/Timeline.jsx";
import Report from "./components/Report.jsx";

const idle = { status: "idle", runId: null, profile: null, plan: [], steps: {}, report: "", error: "" };

// Section 8 - One reducer turns the server's event stream into UI state.
function reducer(state, ev) {
  switch (ev.type) {
    case "clear":
      return idle;
    case "reset":
      return { ...idle, status: "running" };
    case "run_started":
      return { ...state, runId: ev.run_id };
    case "profile":
      return { ...state, profile: ev };
    case "plan":
      return { ...state, plan: ev.steps };
    case "code": {
      const s = state.steps[ev.step] ?? { status: "running", attempts: [] };
      const attempts = [...s.attempts, { n: ev.attempt, code: ev.code, result: null }];
      return { ...state, steps: { ...state.steps, [ev.step]: { ...s, attempts } } };
    }
    case "result": {
      const s = state.steps[ev.step];
      const attempts = s.attempts.map((a) => (a.n === ev.attempt ? { ...a, result: ev } : a));
      return { ...state, steps: { ...state.steps, [ev.step]: { ...s, attempts } } };
    }
    case "step_done": {
      const s = state.steps[ev.step];
      return { ...state, steps: { ...state.steps, [ev.step]: { ...s, status: ev.status } } };
    }
    case "report":
      return { ...state, report: ev.markdown };
    case "error":
      return { ...state, status: "error", error: ev.message };
    case "done":
      return state.status === "error" ? state : { ...state, status: "done" };
    default:
      return state;
  }
}

export default function App() {
  const [dataset, setDataset] = useState(null);
  const [question, setQuestion] = useState("");
  const [accessCode, setAccessCode] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [run, dispatch] = useReducer(reducer, idle);
  const abortRef = useRef(null);
  const running = run.status === "running";

  async function onFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError("");
    try {
      setDataset(await uploadCsv(file, accessCode));
      dispatch({ type: "clear" });
    } catch (err) {
      setDataset(null);
      setUploadError(err.message);
    }
  }

  async function start() {
    abortRef.current = new AbortController();
    dispatch({ type: "reset" });
    try {
      await streamAnalyze({
        datasetId: dataset.dataset_id,
        question,
        accessCode,
        onEvent: (ev) => dispatch(ev),
        signal: abortRef.current.signal,
      });
    } catch (err) {
      if (err.name !== "AbortError") dispatch({ type: "error", message: err.message });
    }
  }

  return (
    <div className="shell">
      <aside className="side">
        <h1>Data Analyst Agent</h1>
        <p className="muted">Upload a CSV, ask a question, and watch the agent plan, write code, fix its own errors, and report.</p>

        <label className="field">
          Access code (if required)
          <input className="text" type="password" value={accessCode} onChange={(e) => setAccessCode(e.target.value)} disabled={running} />
        </label>

        <label className="drop">
          <input type="file" accept=".csv" onChange={onFile} disabled={running} />
          <span>{dataset ? dataset.filename : "Choose a CSV file"}</span>
        </label>
        {uploadError && <p className="error">{uploadError}</p>}

        {dataset && (
          <div className="schema">
            <p className="muted">{dataset.rows.toLocaleString()} rows, {dataset.columns} columns</p>
            <ul>
              {dataset.column_info.map((c) => (
                <li key={c.name}><code>{c.name}</code><span className="muted"> {c.dtype}{c.nulls ? `, ${c.nulls} missing` : ""}</span></li>
              ))}
            </ul>
          </div>
        )}

        <label className="field">
          Question (optional)
          <textarea rows={4} value={question} onChange={(e) => setQuestion(e.target.value)}
            placeholder="Which region is underperforming, and why?" disabled={running} />
        </label>

        {running ? (
          <button className="btn stop" onClick={() => abortRef.current?.abort()}>Stop run</button>
        ) : (
          <button className="btn" onClick={start} disabled={!dataset}>Run analysis</button>
        )}
      </aside>

      <main className="main">
        {run.status === "idle" || (!run.plan.length && !running && !run.error) ? (
          <div className="empty">
            <h2>No analysis yet</h2>
            <p className="muted">Upload a CSV on the left, then choose Run analysis. Each step the agent takes will appear here, including the code it writes and any mistakes it corrects.</p>
          </div>
        ) : (
          <>
            {run.error && <p className="error">{run.error}</p>}
            {run.profile && <p className="muted">Read {run.profile.rows.toLocaleString()} rows and {run.profile.columns} columns.</p>}
            {running && !run.plan.length && <p className="muted">Planning the analysis…</p>}
            <Timeline plan={run.plan} steps={run.steps} runId={run.runId} />
            {running && run.plan.length > 0 && !run.report && <p className="muted">Working…</p>}
            <Report markdown={run.report} />
          </>
        )}
      </main>
    </div>
  );
}
