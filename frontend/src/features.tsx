import { useEffect, useState, useCallback } from "react";
import type { FormEvent, ReactNode } from "react";
import { request, api, documentDownload, errorMessage } from "./api";
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
        {settings.report_integration && <div><dt>External report integration</dt><dd>
          {settings.report_integration.status}<ul>{settings.report_integration.missing.map((item) => <li key={item}>{item}</li>)}</ul>
        </dd></div>}
      </dl>} />
    </section>
    <section className="glass-panel"><h2>Assigned projects</h2><ProjectList /></section>
  </div>;
}


type Validation = { id: number; activities: Array<{
  project_code: string; activity_code: string; structure: string; session_pairs: number; role_slots: number;
  planning: string; staff: string; report: string; eligibility: string; approval: string; settlement: string;
  issues: Record<string, number>; review_tasks: string[];
  report_evidence?: { id: number; cutoff: string; version: string } | null;
}> };

type EvidenceReview = { id: number; kind: string; decision: string; evidence_ref: string;
  project_code: string; activity_code: string; actor_id: number };

function EvidenceHistory({ validation, item, session, project }: {
  validation: number; item: Validation["activities"][number]; session: Session; project: string;
}) {
  const path = `/documents/reviews/${validation}`;
  const [history, setHistory] = useState<EvidenceReview[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const kinds = (["planning", "staff"] as const).filter((kind) =>
    session.project_permissions?.[project]?.includes(`${kind}.verify`));
  useEffect(() => {
    let current = true;
    request<EvidenceReview[]>(path).then(
      (rows) => { if (current) setHistory(rows); },
      (error) => { if (current) setError(errorMessage(error)); },
    );
    return () => { current = false; };
  }, [path]);
  return <details>
    <summary>Evidence review</summary>
    <p className="muted">Reviews apply to this snapshot. Report authority and payment eligibility are checked separately.</p>
    <ul>{history.filter((row) => row.project_code === item.project_code && row.activity_code === item.activity_code).map((row) =>
      <li key={row.id}>{row.kind}: {row.decision} · {row.evidence_ref} · Reviewer #{row.actor_id}</li>)}</ul>
    {error && <p role="alert">{error}</p>}
    {kinds.length > 0 && <form className="admin-grid" onSubmit={async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const fields = new FormData(form);
      setBusy(true); setError("");
      try {
        await request(path, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token },
          body: JSON.stringify({ project_code: item.project_code, activity_code: item.activity_code,
            kind: fields.get("kind"), decision: fields.get("decision"), evidence_ref: fields.get("evidence") }) });
        setHistory(await request<EvidenceReview[]>(path));
        form.reset();
      } catch (error) { setError(errorMessage(error)); }
      finally { setBusy(false); }
    }}>
      <label>Evidence category<select name="kind">{kinds.map((kind) => <option key={kind}>{kind}</option>)}</select></label>
      <label>Decision<select name="decision"><option value="confirmed">Confirm review</option><option value="rejected">Reject evidence</option></select></label>
      <label>Independent evidence reference<input name="evidence" required minLength={5} maxLength={500} /></label>
      <div><button disabled={busy}>Record decision</button></div>
    </form>}
  </details>;
}

export function StructuralReview({ session }: { session: Session }) {
  const [project, setProject] = useState("");
  const [saved, setSaved] = useState<Validation | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const path = `/documents/structural-validation/${project}`;
  useEffect(() => {
    let current = true;
    setSaved(null);
    setError("");
    if (project) request<Validation | null>(path).then(
      (value) => { if (current) setSaved(value); },
      (error) => { if (current) setError(errorMessage(error)); },
    );
    return () => { current = false; };
  }, [project, path]);

  async function validate() {
    setBusy(true);
    setError("");
    try {
      setSaved(await request<Validation>(path, {
        method: "POST", headers: { "X-CSRF-Token": session.csrf_token },
      }));
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }

  return <section className="glass-panel admin-form">
    <h2>Structural validation &amp; review</h2>
    <ApiPanel load={api.projects} render={(projects) => <label>Active project
      <select disabled={busy} value={project} onChange={(event) => setProject(event.target.value)}>
        <option value="">Select project</option>
        {projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
    </label>} />
    {session.permissions.includes("projects:manage") && <div>
      <button disabled={!project || busy} onClick={() => void validate()}>{busy ? "Checking files…" : "Run and save structural checks"}</button>
    </div>}
    {error && <p role="alert">{error}</p>}
    {saved && <><p role="status">Saved validation #{saved.id}</p>
      {saved.activities.map((item) => <article key={JSON.stringify([item.project_code, item.activity_code])}>
        <h3>{item.project_code} / {item.activity_code}</h3>
        <p>{item.structure} · {item.session_pairs}/6 session pairs · {item.role_slots}/12 role slots</p>
        <p>Planning: {item.planning} · Identity: {item.staff} · External report: {item.report}</p>
        <p>Eligibility: {item.eligibility} · Approval: {item.approval} · Settlement: {item.settlement}</p>
        {item.report_evidence && <p>Frozen cutoff: {item.report_evidence.cutoff} · Validated version: {item.report_evidence.version}</p>}
        <EvidenceHistory key={saved.id} validation={saved.id} item={item} session={session} project={project} />
        <ul>{[...Object.keys(item.issues), ...item.review_tasks].map((code) => <li key={code}>{code}</li>)}</ul>
      </article>)}</>}
  </section>;
}
