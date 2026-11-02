const LABEL = { pending: "Waiting", running: "Working", ok: "Done", failed: "Failed" };

function lastLine(text = "") {
  const lines = text.trim().split("\n").filter(Boolean);
  return lines[lines.length - 1] ?? "Unknown error";
}

function Attempt({ attempt, runId }) {
  const r = attempt.result;
  const state = !r ? "running" : r.ok ? "ok" : "failed";
  const summary = !r ? "running…" : r.ok ? `passed in ${r.seconds}s` : `failed: ${lastLine(r.stderr)}`;
  return (
    <details className={`attempt ${state}`}>
      <summary>
        Attempt {attempt.n}: {summary}
      </summary>
      <pre className="code">{attempt.code}</pre>
      {r && <pre className="out">{(r.ok ? r.stdout : r.stderr) || "(no output)"}</pre>}
      {r?.charts.map((c) => (
        <img key={c} className="chart" alt={c} src={`/api/runs/${runId}/charts/${c}`} />
      ))}
    </details>
  );
}

// Each plan step is a stage on a rail; failed attempts stay visible so you can see the agent recover.
export default function Timeline({ plan, steps, runId }) {
  if (!plan.length) return null;
  return (
    <ol className="rail">
      {plan.map((p, i) => {
        const s = steps[i];
        const status = s?.status ?? "pending";
        return (
          <li key={i} className={`stage ${status}`}>
            <div className="stage-head">
              <h3>{p.title}</h3>
              <span className="badge">{LABEL[status]}</span>
            </div>
            <p className="muted">{p.goal}</p>
            {s?.attempts.map((a) => <Attempt key={a.n} attempt={a} runId={runId} />)}
          </li>
        );
      })}
    </ol>
  );
}
