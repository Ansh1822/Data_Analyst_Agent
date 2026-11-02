import ReactMarkdown from "react-markdown";

export default function Report({ markdown }) {
  if (!markdown) return null;
  function download() {
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "analysis-report.md" });
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <section className="report">
      <div className="report-head">
        <h2>Report</h2>
        <button className="btn small" onClick={download}>Download Markdown</button>
      </div>
      <ReactMarkdown>{markdown}</ReactMarkdown>
    </section>
  );
}
