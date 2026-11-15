import { ExecutionSummary } from "./observatory";
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
  if (state.status === "loading") return <div className="skeleton" role="status">Loading workspace data…</div>;
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


const steps: { label: string; icon: IconName; detail: string; status: string }[] = [
  { label: "Upload timesheets", icon: "imports", detail: "Import Arabic and English Excel or CSV files. Original values and source bytes are preserved.", status: "Available" },
  { label: "AI extraction", icon: "ai", detail: "Ollama proposes structured values from the original cells.", status: "Adapter available" },
  { label: "Validation", icon: "validation", detail: "Python verifies source provenance, dates, and quantities.", status: "Guarded structural checks" },
  { label: "Payment calculation", icon: "calculation", detail: "Deterministic Python rules calculate eligible amounts.", status: "Planned" },
  { label: "Human approval", icon: "approval", detail: "An authorized reviewer approves the batch.", status: "Planned" },
  { label: "Export", icon: "export", detail: "Export approved lists for external payment execution.", status: "Planned" },
];

const aiLabels = {
  ready: "Model available",
  model_missing: "Configured model missing",
  unreachable: "Ollama unavailable",
} as const;

const checkAIStatus = async () => ({ ...await api.aiStatus(), checkedAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) });
export function LocalAI() {
  const [revision, setRevision] = useState(0);
  return <div aria-label="Ollama connection" className="ai-connection-check">
    <ApiPanel key={revision} load={checkAIStatus} render={({ status, model, checkedAt }) =>
      <div className="ai-state" title={`Checked ${checkedAt}`}><Badge tone={status === "ready" ? "green" : "amber"}>
        <span className="status-dot" aria-hidden="true" /> {aiLabels[status]}
      </Badge><span className="model-tag" data-mono dir="auto">{model}</span><small>Checked {checkedAt}</small></div>} />
    <button className="secondary" aria-label="Refresh Ollama status" onClick={() => setRevision(value => value + 1)}>↻</button>
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
    <section className="hero glass-panel"><div><p className="eyebrow">Operations command center</p>
      <h1>A clearer view of your operations.</h1><p>Review source evidence, resolve exceptions, and prepare the next decision.</p></div>
      <div className="hero-controls"><LocalAI /><a href="#assistant" className="hero-action"><Icon name="ai" /> Open AI Workspace</a></div>
    </section>
    <ApiPanel load={loadOverview} render={(data) => <>
      <dl className="command-metrics">{[
        ["Active projects", data.active_projects, "projects?status=active", "Currently active in your scope"],
        ["Current activities", data.current_activities, "activities", "Within recorded planned dates"],
        ["Mapping reviews", data.mapping_reviews, "assistant", "Your proposals awaiting confirmation"],
        ["Source documents", data.documents, "imports", "Stored in authorized projects"],
        ["Structural validations", data.structural_validations, "imports", "Your recorded validation snapshots"],
        ["Payment-ready obligations", data.payment_ready, "batches", "Entitlement summary unavailable"],
        ["Outstanding obligations", data.outstanding_obligations, "reconciliation", "Settlement summary unavailable"],
      ].map(([label, value, link, note]) => <a className="glass-panel command-metric" href={`#${link}`} key={String(label)}><dt>{label}</dt>
        <dd data-mono>{value === null ? "Unavailable" : value}</dd><small>{note}</small><span aria-hidden="true">↗</span></a>)}</dl>
      <section className="glass-panel workflow-report"><header><h2>Workflow outcomes</h2><span className="muted">Your stored receipts · last 7 UTC days</span></header>
        <div className="workflow-outcome-chart">{data.workflow_trend.map(day => <div key={day.day}><small>{day.day.slice(5)}</small><div role="img" aria-label={`${day.day}: ${day.completed} completed, ${day.needs_review} need review, ${day.blocked} blocked, ${day.failed} failed`}>
          {(['completed', 'needs_review', 'blocked', 'failed'] as const).map(status => <span className={`outcome-${status}`} key={status} style={{ width: `${day[status] / Math.max(1, ...data.workflow_trend.map(item => item.completed + item.needs_review + item.blocked + item.failed)) * 100}%` }} />)}</div><span>{day.completed} complete · {day.needs_review} review · {day.blocked} blocked · {day.failed} failed</span></div>)}</div>
        <p className="muted">Workflow completion does not confer approval, eligibility or settlement.</p>
      </section>
      {!!data.pending_reviews.length && <section className="glass-panel operation-panel"><h2>Mappings awaiting your review</h2><ul>{data.pending_reviews.map((review, index) => <li key={`${review.conversation_id}-${index}`}><a className="pending-review-link" href={`#assistant/${review.conversation_id}`}>{review.title || 'Open source mapping review'} ↗</a></li>)}</ul></section>}
    </>} />
    <ExecutionSummary />
    <div className="dashboard-bottom"><section className="glass-panel"><h2>Assigned projects</h2><ProjectList /></section>
      <section className="glass-panel"><span className="eyebrow">Human control</span><h2>Your next decision</h2>
        <p className="muted">Confirm source mappings, review validation evidence, and resolve blockers before preparing payments.</p>
        <a className="hero-action" href="#imports">Review source evidence →</a>
        <p className="muted">Timmy prepares. Authorized humans approve. Transfers and settlement occur externally.</p></section></div>
    <ProcessingPipeline />
  </div>;
}
const loadOverview = () => request<{ active_projects: number; current_activities: number; mapping_reviews: number;
  workflow_trend: { day: string; completed: number; needs_review: number; blocked: number; failed: number }[];
  pending_reviews: { conversation_id: string; title: string | null; created_at: number }[];
  documents: number; structural_validations: number; payment_ready: null; outstanding_obligations: null }>("/overview");

const operationCopy = {
  imports: ["Source file", "No imports recorded for your projects.", "This table lists legacy import records. New spreadsheet uploads are shown above."],
  timesheets: ["Source file", "No timesheets recorded for your projects.", "Source comparison and record editing are pending."],
  discrepancies: ["Issue code", "No discrepancies recorded for your projects.", "Issue resolution and reassignment are pending."],
  batches: ["Policy version", "No payment batches recorded for your projects.", "Calculation and approval are pending. Transfers are handled externally."],
};

export function DocumentHistory() {
  return <section className="glass-panel operation-panel">
    <h2>Stored spreadsheets</h2><p className="muted">Each row is a stored upload. Repeated filenames can belong to different conversations or file versions; compare the original hash before treating them as duplicates. Mapping confirmation does not approve evidence or payments.</p>
    <ApiPanel load={api.documents} render={(documents) => documents.length ? <div className="chat-table" tabIndex={0} role="region" aria-label="Stored spreadsheets">
      <table><thead><tr><th scope="col">File</th><th scope="col">Project ID</th><th scope="col">Data rows</th><th scope="col">Status</th></tr></thead>
        <tbody>{documents.map((file) => <tr key={file.id}><td><a href={documentDownload(file.id)} dir="auto">{file.filename}</a></td>
          <td>{file.project_id ?? 'Global source'}</td><td>{file.data_rows ?? file.rows}</td><td>{file.status === 'MAPPING_CONFIRMED' ? 'Column mapping confirmed · evidence approval separate' : 'Parsed · Column mapping review required'}{file.conversation_id && <p><a href={`#assistant/${file.conversation_id}`}>Open source conversation</a></p>}<small>Uploaded {file.uploaded_at || 'date unavailable'} · File {file.id}</small><details><summary>Original SHA-256</summary><code>{file.sha256}</code></details></td></tr>)}</tbody></table>
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
    <section className="glass-panel"><h2>Approved instruction metadata</h2><ApiPanel load={instructionMetadata} render={(data) => <dl className="status-list">
      <div><dt>Instruction set</dt><dd>{data.instruction_set}</dd></div><div><dt>Pinned version</dt><dd className="trace-id">{data.version}</dd></div>
      <div><dt>Configuration</dt><dd>{data.configuration_version}</dd></div></dl>} /><p className="muted">Confidential instruction text is excluded. Invocation nodes show the fingerprint of the context actually supplied.</p></section>
    <section className="glass-panel"><h2>Assigned projects</h2><ProjectList /></section>
  </div>;
}
const instructionMetadata = () => request<{ instruction_set: string; version: string; configuration_version: string }>("/executions/instructions");


type Validation = { id: number; project_id: number; activities: Array<{
  policy_family?: string; project_code: string; activity_code: string; structure: string; session_pairs: number; role_slots: number;
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
  const currentDecision = (kind: "planning" | "staff") => history.find(
    (row) => row.kind === kind && row.project_code === item.project_code &&
      row.activity_code === item.activity_code,
  )?.decision;
  const outstanding = kinds.filter((kind) => currentDecision(kind) !== "confirmed");
  const nextKind = outstanding[0] ?? kinds[0];
  useEffect(() => {
    let current = true;
    request<EvidenceReview[]>(path).then(
      (rows) => { if (current) setHistory(rows); },
      (error) => { if (current) setError(errorMessage(error)); },
    );
    return () => { current = false; };
  }, [path]);
  return <details open={history.length === 0 || outstanding.length > 0} key={`${validation}-${item.activity_code}-${outstanding.join(",")}`}>
    <summary>Evidence review · {outstanding.length
      ? `Action required: ${outstanding.map(kind => kind === "planning" ? "planning" : "staff identities").join(" and ")}`
      : "Planning and staff reviews confirmed"}</summary>
    <p className="muted">Decisions below are current for this saved snapshot. External report authority and payment approval remain separate.</p>
    {(["planning", "staff"] as const).map((kind) => {
      const latest = history.find((row) => row.kind === kind && row.project_code === item.project_code
        && row.activity_code === item.activity_code);
      return <p key={kind}>{kind === "planning" ? "Planning evidence" : "Staff evidence"}: {latest?.decision ?? "awaiting review"}</p>;
    })}
    <details><summary>Past evidence decisions</summary><ul>{history.filter((row) => row.project_code === item.project_code && row.activity_code === item.activity_code).map((row) =>
      <li key={row.id}>{row.kind}: {row.decision} · {row.evidence_ref} · Reviewer #{row.actor_id}</li>)}</ul></details>
    {error && <p role="alert">{error}</p>}
    {(['planning','staff'] as const).filter(kind=>!kinds.includes(kind)).map(kind=><p role="status" key={kind}>You can inspect this evidence, but recording {kind} decisions requires the project-scoped {kind}.verify permission. Ask an administrator to assign it to the authorized reviewer; admin status alone does not grant review authority.</p>)}
    {kinds.length > 0 && outstanding.length === 0 && <p role="status">Both reviews are confirmed. No further evidence decision is required unless you need to correct a previous decision.</p>}
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
      <label>Evidence category<select name="kind" key={nextKind} defaultValue={nextKind}>{kinds.map((kind) => <option key={kind} value={kind}>{kind === "planning" ? "Planning authority" : "Staff identity verification"}{currentDecision(kind) === "confirmed" ? " (already confirmed)" : " (action required)"}</option>)}</select></label>
      <label>Decision<select name="decision"><option value="confirmed">Confirm review</option><option value="rejected">Reject evidence</option></select></label>
      <label>Independent evidence reference<input name="evidence" required minLength={5} maxLength={500} /></label>
      <div><button disabled={busy}>Record decision</button></div>
    </form>}
  </details>;
}

export function EvidenceReviewInbox({session}:{session:Session}) {
 const [items,setItems]=useState<{name:string;id:number}[]>([]),[error,setError]=useState(''),[loading,setLoading]=useState(true);
 useEffect(()=>{let active=true;api.projects().then(async projects=>{
  const results=await Promise.all(projects.filter(project=>session.project_permissions?.[String(project.id)]?.includes('timesheets.view')).map(async project=>({name:project.name,validation:await request<Validation|null>(`/documents/structural-validation/${project.id}`)})));
  if(active)setItems(results.filter(r=>r.validation).map(r=>({name:r.name,id:r.validation!.id})));
 }).catch(e=>{if(active)setError(errorMessage(e));}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[]);
 return <section><h2>Planning and staff evidence reviews</h2><p className="muted">Review the saved project evidence below. Each decision requires an authorized human and resumes the owner's existing workflow. No approval is inferred from an Excel label.</p>{loading&&<p role="status">Loading saved evidence…</p>}{error&&<p role="alert">{error}</p>}{!loading&&!items.length&&!error&&<p>No saved validations are available. Process your documents in AI Workspace first.</p>}{items.map(item=><section key={item.id}><h3>{item.name}</h3><StructuralReview session={session} validationId={String(item.id)}/></section>)}</section>;
}

export function StructuralReview({ session, validationId }: { session: Session; validationId?: string }) {
  const [project, setProject] = useState("");
  const [saved, setSaved] = useState<Validation | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const path = `/documents/structural-validation/${project}`;
  useEffect(() => {
    let current = true;
    setSaved(null);
    setError("");
    if (validationId || project) request<Validation | null>(validationId ? `/documents/validation/${validationId}` : path).then(
      (value) => { if (current) setSaved(value); },
      (error) => { if (current) setError(errorMessage(error)); },
    );
    return () => { current = false; };
  }, [project, path, validationId]);

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
    {validationId ? <a href="#imports">Browse project validations</a> : <ApiPanel load={api.projects} render={(projects) => <label>Active project
      <select disabled={busy} value={project} onChange={(event) => setProject(event.target.value)}>
        <option value="">Select project</option>
        {projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
    </label>} />}
    {!validationId && session.permissions.includes("projects:manage") && <div>
      <button disabled={!project || busy} onClick={() => void validate()}>{busy ? "Checking files…" : "Run and save structural checks"}</button>
    </div>}
    {error && <p role="alert">{error}</p>}
    {saved && <><p role="status">Saved validation #{saved.id}</p>
      {saved.activities.map((item) => <article key={JSON.stringify([item.project_code, item.activity_code])}>
        <h3>{item.project_code} / {item.activity_code}</h3>
        <p>{item.structure}{item.policy_family === "hours" ? " · HOURS source checks" : ` · ${item.session_pairs}/6 session pairs · ${item.role_slots}/12 role slots`}</p>
        <details><summary>Historical snapshot gate details</summary><p>At calculation: Planning {item.planning} · Identity {item.staff} · External report {item.report}. These are historical values, not live decisions.</p>
        <p>At calculation: Eligibility {item.eligibility} · Approval {item.approval} · Settlement {item.settlement}.</p></details>
        {item.report_evidence && <p>Frozen cutoff: {item.report_evidence.cutoff} · Validated version: {item.report_evidence.version}</p>}
        <EvidenceHistory key={saved.id} validation={saved.id} item={item} session={session} project={String(saved.project_id)} />
        <details><summary>Snapshot issue codes (historical)</summary><ul>{[...Object.keys(item.issues), ...item.review_tasks].map((code) => <li key={code}>{code}</li>)}</ul></details>
      </article>)}</>}
  </section>;
}

const workflowDefinitions = () => request<{version:string;workflows:{id:string;label:string;trigger:string;steps:{step:string;prerequisites:string;expected_outcome:string;next_action:string;availability:string}[]}[]}>('/workflows/definitions');
export function WorkflowDefinitions() {
  return <section className="glass-panel operation-panel"><h2>Workflow requirements and completion paths</h2>
    <p className="muted">Available handlers, required evidence and remaining integrations are listed separately. A source preview does not approve a payment.</p>
    <ApiPanel load={workflowDefinitions} render={data => <>{data.workflows.map(workflow => <details key={workflow.id} className="operation-panel"><summary>{workflow.label}</summary>
      <p className="muted">Trigger: {workflow.trigger}</p>
      <ol>{workflow.steps.map(step => <li key={step.step} className="operation-panel"><h3>{step.step.replaceAll('_',' ')}</h3><Badge tone={step.availability==='available'?'green':'amber'}>{step.availability.replaceAll('_',' ')}</Badge>
        <dl className="status-list"><div><dt>Prerequisites</dt><dd>{step.prerequisites}</dd></div><div><dt>Completion evidence</dt><dd>{step.expected_outcome}</dd></div><div><dt>Next required action</dt><dd>{step.next_action}</dd></div></dl></li>)}</ol>
    </details>)}</>} /></section>;
}
