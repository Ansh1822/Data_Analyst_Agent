// Section 7 - API client. Upload is plain fetch; the analysis is a streamed POST (SSE).
export async function uploadCsv(file) {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Upload failed");
  return res.json();
}

// EventSource only supports GET, so we read the POST response stream by hand.
export async function streamAnalyze({ datasetId, question, onEvent, signal }) {
  const res = await fetch("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset_id: datasetId, question }),
    signal,
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Analysis failed to start");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n"); // one SSE frame per blank line
    buffer = frames.pop();               // keep the unfinished tail for the next chunk
    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data: "));
      if (line) onEvent(JSON.parse(line.slice(6)));
    }
  }
}
