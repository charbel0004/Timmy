import { useEffect, useState, useCallback } from "react";
import type { FormEvent, ReactNode } from "react";
import { api, documentDownload, errorMessage } from "./api";
import type { Session, OperationsSection } from "./api";
import { Badge, Brand, Icon } from "./design";
import type { IconName } from "./design";

type LoadState<T> = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: T };

function ApiPanel<T>({ load, render }: { load: () => Promise<T>; render: (value: T) => ReactNode }) {
  const [state, setState] = useState<LoadState<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    load().then(
      (data) => { if (active) setState({ status: "ready", data }); },
      (error) => { if (active) setState({ status: "error", message: errorMessage(error) }); },
    );
    return () => { active = false; };
  }, [load, attempt]);
  if (state.status === "loading") return <p role="status">Loading…</p>;
  if (state.status === "error") return <>
    <p role="alert">{state.message}</p>
    <button onClick={() => { setState({ status: "loading" }); setAttempt(attempt + 1); }}>Retry</button>
  </>;
  return render(state.data);
}

export function Login({ onLogin }: { onLogin: (session: Session) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      onLogin(await api.login(String(form.get("username")), String(form.get("password"))));
    } catch (error) {
      setError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }
  return <main className="login-layout glass-panel">
    <section className="login-intro">
      <Brand />
      <h1>From timesheets to payment review</h1>
      <p>A local workspace for AJ to organize volunteer records and prepare payment lists for human approval.</p>
    </section>
    <form onSubmit={submit} className="login-form">
      <div><h2>Sign in</h2><p className="muted">Use your local workspace account.</p></div>
      <label>Username<input required name="username" autoComplete="username" maxLength={80} /></label>
      <label>Password<input required name="password" type="password" autoComplete="current-password" maxLength={1024} /></label>
      {error && <p role="alert">{error}</p>}
      <button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </form>
  </main>;
}

const metrics: { label: string; icon: IconName; note: string }[] = [
  { label: "Total Timesheets", icon: "imports", note: "Imports planned" },
  { label: "Validated Records", icon: "validation", note: "Validation planned" },
  { label: "Pending Discrepancies", icon: "discrepancies", note: "Review queue planned" },
  { label: "Calculated Payments", icon: "calculation", note: "Calculation planned" },
  { label: "Awaiting Approval", icon: "approval", note: "Approvals planned" },
];

const steps: { label: string; icon: IconName; detail: string; status: string }[] = [
  { label: "Upload timesheets", icon: "imports", detail: "Import Arabic and English Excel or CSV files.", status: "Planned" },
  { label: "AI extraction", icon: "ai", detail: "Ollama proposes structured values from the original cells.", status: "Adapter available" },
  { label: "Validation", icon: "validation", detail: "Python verifies source provenance, dates, and quantities.", status: "Extraction checks available" },
  { label: "Payment calculation", icon: "calculation", detail: "Deterministic Python rules calculate eligible amounts.", status: "Planned" },
  { label: "Human approval", icon: "approval", detail: "An authorized reviewer approves the batch.", status: "Planned" },
  { label: "Export", icon: "export", detail: "Export approved lists for external payment execution.", status: "Planned" },
];

const aiLabels = {
  ready: "Model available",
  model_missing: "Configured model missing",
  unreachable: "Ollama unavailable",
} as const;

function LocalAI() {
  return <div aria-label="Ollama connection">
    <ApiPanel load={api.aiStatus} render={({ status, model }) =>
      <div className="ai-state"><Badge tone={status === "ready" ? "green" : "amber"}>
        <span className="status-dot" aria-hidden="true" /> {aiLabels[status]}
      </Badge><span className="model-tag" data-mono dir="auto">{model}</span></div>} />
  </div>;
}

function ProcessingPipeline() {
  return <section className="glass-panel" aria-labelledby="workflow-title">
    <div className="section-heading"><div><h2 id="workflow-title">Processing pipeline</h2>
      <p className="muted">Open a stage to see what it does and what’s available.</p></div></div>
    <ol className="workflow">{steps.map(({ label, icon, detail, status }) =>
      <li key={label}><details>
        <summary><span className="tile-icon"><Icon name={icon} /></span>
          <strong>{label}</strong>
          <Badge tone={status === "Planned" ? "neutral" : "cyan"}>{status}</Badge>
        </summary>
        <p className="muted">{detail}</p>
      </details></li>)}</ol>
  </section>;
}

function ProjectList() {
  return <ApiPanel load={api.projects} render={(projects) => projects.length > 0
    ? <ul className="project-list">{projects.map((project) =>
      <li key={project.id}><Icon name="project" /><span dir="auto">{project.name}</span></li>)}</ul>
    : <p className="empty-state">No projects assigned to this account.</p>} />;
}

export function Dashboard() {
  return <div className="dashboard">
    <section className="hero glass-panel">
      <div>
        <p className="hero-label"><Icon name="clock" /> Reporting period unavailable</p>
        <h1>Staff Operations</h1>
        <p>AI-powered timesheet validation &amp; payment management</p>
      </div>
      <div className="hero-controls">
        <LocalAI />
        <a href="#imports" className="hero-action"><Icon name="imports" /> View imports</a>
      </div>
    </section>
    <section aria-labelledby="metrics-title">
      <h2 id="metrics-title" className="mb-3">Processing overview</h2>
      <dl className="metrics">{metrics.map(({ label, icon, note }) =>
        <div className={`glass-panel metric metric--${icon}`} key={label}>
          <span className="tile-icon"><Icon name={icon} /></span>
          <dt>{label}</dt><dd data-mono><span aria-hidden="true">—</span><span className="sr-only">Unavailable</span></dd>
          <p>{note}</p>
        </div>)}</dl>
    </section>
    <section className="glass-panel operation-panel">
      <h2>Spreadsheet intake</h2>
      <ApiPanel load={api.documentMetrics} render={(metrics) => <dl className="status-list">
        <div><dt><a href="#imports">Stored spreadsheets</a></dt><dd>{metrics.documents}</dd></div>
        <div><dt>Source rows awaiting mapping</dt><dd>{metrics.source_rows}</dd></div>
      </dl>} />
    </section>
    <ProcessingPipeline />
    <div className="dashboard-bottom">
      <section className="glass-panel"><h2>Assigned projects</h2><ProjectList /></section>
      <section className="glass-panel"><h2>Operational insights</h2>
        <dl className="status-list">
          <div><dt>Validation and activity charts</dt><dd>No reporting API</dd></div>
          <div><dt>Payment batch overview</dt><dd>Planned</dd></div>
          <div><dt>Recent imports and discrepancies</dt><dd>Planned</dd></div>
          <div><dt>Records requiring AJ’s attention</dt><dd>Review queue planned</dd></div>
        </dl>
      </section>
    </div>
  </div>;
}

const operationCopy = {
  imports: ["Source file", "No imports recorded for your projects.", "This table lists legacy import records. New spreadsheet uploads are shown above."],
  timesheets: ["Source file", "No timesheets recorded for your projects.", "Source comparison and record editing are pending."],
  discrepancies: ["Issue code", "No discrepancies recorded for your projects.", "Issue resolution and reassignment are pending."],
  batches: ["Policy version", "No payment batches recorded for your projects.", "Calculation and approval are pending. Transfers are handled externally."],
};

export function DocumentHistory() {
  return <section className="glass-panel operation-panel">
    <h2>Stored spreadsheets</h2>
    <ApiPanel load={api.documents} render={(documents) => documents.length ? <div className="chat-table" tabIndex={0} role="region" aria-label="Stored spreadsheets">
      <table><thead><tr><th scope="col">File</th><th scope="col">Project ID</th><th scope="col">Source rows</th><th scope="col">Status</th></tr></thead>
        <tbody>{documents.map((file) => <tr key={file.id}><td><a href={documentDownload(file.id)} dir="auto">{file.filename}</a></td>
          <td>{file.project_id}</td><td>{file.rows}</td><td>Parsed · Mapping required</td></tr>)}</tbody></table>
    </div> : <p className="empty-state">No spreadsheets are stored for your projects.</p>} />
    <a href="#assistant">Open AI Assistant to upload a spreadsheet</a>
  </section>;
}

export function OperationsPage({ section }: { section: OperationsSection }) {
  const [reference, empty, capability] = operationCopy[section];
  const [search, setSearch] = useState("");
  const load = useCallback(() => api.operations(section), [section]);
  return <section className="glass-panel operation-panel">
    <p className="muted">{capability}</p>
    <ApiPanel load={load} render={(rows) => {
      if (!rows.length) return <p className="empty-state">{empty}</p>;
      const term = search.trim().toLocaleLowerCase();
      const filtered = rows.filter((row) => `${row.project} ${row.reference} ${row.id}`.toLocaleLowerCase().includes(term));
      return <>
        <label className="operation-filter">Filter recent records
          <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} />
        </label>
        <p className="muted">{filtered.length} of {rows.length} recent records</p>
        {filtered.length === 0 ? <p className="empty-state">No matching records.</p> :
          <div className="chat-table" tabIndex={0} role="region" aria-label="Recent records">
            <table><thead><tr><th scope="col">ID</th><th scope="col">Project</th><th scope="col">{reference}</th>
              {(section === "timesheets" || section === "discrepancies") && <th scope="col">Source row</th>}</tr></thead>
              <tbody>{filtered.map((row) => <tr key={row.id}><td data-mono>{row.id}</td>
                <td dir="auto">{row.project}</td><td dir="auto">{row.reference}</td>
                {(section === "timesheets" || section === "discrepancies") && <td data-mono>{row.source_row ?? "—"}</td>}</tr>)}</tbody>
            </table>
          </div>}
      </>;
    }} />
  </section>;
}

export function SettingsPanel() {
  return <div className="dashboard-bottom">
    <section className="glass-panel"><h2>Workspace configuration</h2>
      <ApiPanel load={api.settings} render={(settings) => <dl className="status-list">
        <div><dt>Configured model</dt><dd data-mono>{settings.ollama_model}</dd></div>
        <div><dt>Demo mode</dt><dd>{settings.demo_mode ? "Enabled" : "Disabled"}</dd></div>
      </dl>} />
    </section>
    <section className="glass-panel"><h2>Assigned projects</h2><ProjectList /></section>
  </div>;
}
