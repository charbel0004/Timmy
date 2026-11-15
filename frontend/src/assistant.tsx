import { WorkflowPayments } from "./workflow-payments";
import { GlobalMappings } from "./global-mappings";
import { ReportingRegisterPanel } from "./reporting-register";
import { WorkflowFindings } from "./workflow-findings";
import { createRequestId } from "./request-id";
import { ExecutionTimeline } from "./observatory";
import remarkGfm from "remark-gfm";
import { Dictation, SpokenResponse } from "./voice";
import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { ArrowUp, CalendarDays, Copy, FileSpreadsheet, ListFilter, Paperclip, PanelRight, Plus, Sparkles, Wallet, X } from "lucide-react";
import Markdown from "react-markdown";
import { api, documentDownload, errorMessage } from "./api";
import type { DocumentRecord, Project, ConversationWorkflow } from "./api";
import type { ChatMessage, Conversation } from "./chat";
import { AgentAvatar, Badge } from "./design";

const suggestions = [
  { label: "Analyze timesheets", text: "Analyze this week’s timesheets.", Icon: FileSpreadsheet },
  { label: "Summarize activities", text: "Summarize staff activities this month.", Icon: CalendarDays },
  { label: "Review discrepancies", text: "Which records contain discrepancies?", Icon: ListFilter },
  { label: "Prepare payments", text: "Help me prepare a payment batch for review.", Icon: Wallet },
];

export function ConversationHistory({ conversations, activeId, onSelect, onNew, onRename, onDelete }: {
  conversations: Conversation[]; activeId?: string; onSelect: (id: string) => void; onNew: () => void;
  onRename: (id: string, title: string) => void; onDelete: (id: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<string>();
  return <section className="chat-history" aria-label="Recent conversations">
    <button type="button" className="secondary" onClick={onNew}><Plus size={16} /> New chat</button>
    {conversations.length > 0 && <label>Recent conversations<input type="search" placeholder="Search chats"
      value={search} onChange={(event) => setSearch(event.target.value)} /></label>}
    <ul>{conversations.filter((item) => (item.title || item.messages[0]?.text || "Untitled conversation")
      .toLowerCase().includes(search.trim().toLowerCase())).map(({ id, title, messages }) => {
      const label = title || messages[0]?.text || "Untitled conversation";
      return <li key={id}><button type="button" aria-current={id === activeId ? "true" : undefined}
        onClick={() => onSelect(id)} dir="auto">{label}</button>
        <details><summary aria-label={`Manage ${label}`}>⋯</summary>
          {editing === id ? <form className="chat-rename" onSubmit={(event) => {
            event.preventDefault();
            const name = String(new FormData(event.currentTarget).get("title")).trim();
            if (name) { onRename(id, name); setEditing(undefined); }
          }}>
            <label>Chat name<input name="title" defaultValue={label.slice(0, 120)} required maxLength={120} /></label>
            <button type="submit">Save name</button>
            <button type="button" onClick={() => setEditing(undefined)}>Cancel</button>
          </form> : <button type="button" onClick={() => setEditing(id)}>Rename</button>}
          <button onClick={() => { if (window.confirm("Delete this conversation?")) onDelete(id); }}>Delete</button>
        </details>
      </li>;
    })}</ul>
  </section>;
}

function ActivitySteps({ steps, requestId, live = false }: {
  steps: string[]; requestId?: string; live?: boolean;
}) {
  return <details open={live || undefined} className="assistant-activity">
    <summary>Assistant activity</summary>
    <ol>{steps.map((step, index) => <li key={index}>{step}</li>)}</ol>
    {requestId && <small>Request ID: <code>{requestId}</code></small>}
  </details>;
}

function Message({ message, csrf }: { message: ChatMessage; csrf?: string }) {
  const [copyStatus, setCopyStatus] = useState("");
  return <article className={`chat-message chat-message--${message.role}`}>
    <header>{message.role === "assistant" && <AgentAvatar className="message-avatar" size={32} />}<strong>{message.role === "user" ? "You" : "Agent Timmy"}</strong>
      <time dateTime={message.timestamp}>{new Date(message.timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</time>
    </header>
    <div dir="auto" className="message-body">
      {message.role === "assistant" ? <Markdown skipHtml remarkPlugins={[remarkGfm]}>{message.text}</Markdown> : <p>{message.text}</p>}
    </div>
    {!!message.attachments?.length && <ul className="attachment-list">{message.attachments.map((name, i) =>
      <li key={i} dir="auto">{name}</li>)}</ul>}
    {message.executionId && <a className="message-execution-link" href={`#observatory/${message.executionId}`}>Inspect recorded execution ↗</a>}
    {!!message.activity?.length && <ActivitySteps steps={message.activity} requestId={message.requestId} />}
    {message.tables?.map((table, index) => <details key={index}>
      <summary>{table.title}</summary>
      <div className="chat-table" tabIndex={0} role="region" aria-label={table.title}>
        <table><thead><tr>{table.columns.map((column, i) => <th key={i} scope="col" dir="auto">{column}</th>)}</tr></thead>
          <tbody>{table.rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j} dir="auto">{cell}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </details>)}
    {message.role === "assistant" && <div className="message-actions">
      <button type="button" className="secondary" aria-label="Copy response" onClick={async () => {
        try { await navigator.clipboard.writeText(message.text); setCopyStatus("Copied"); }
        catch { setCopyStatus("Copy unavailable"); }
      }}><Copy size={15} aria-hidden="true" /></button>
      <span role="status">{copyStatus}</span>
      {csrf && <SpokenResponse csrf={csrf} text={message.text} />}
    </div>}
  </article>;
}

function MappingReview({ state, conversationId, csrf, onResult }: {
  state: ConversationWorkflow; conversationId: string; csrf: string;
  onResult: (state: ConversationWorkflow, messages: ChatMessage[]) => void;
}) {
  const proposal = state.mapping!;
  const [selections, setSelections] = useState(() => proposal.sheets.map((sheet) => ({
    file_id: sheet.file_id, sheet_index: sheet.sheet_index, kind: sheet.kind, columns: { ...sheet.columns },
  })));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return <details open className="glass-panel">
    <summary>Review column mappings · version {proposal.version}</summary>
    <p>Confirm the source columns below. This confirms column interpretation, not staff identity, report approval, or payment authority.</p>
    <form onSubmit={async (event) => {
      event.preventDefault(); setBusy(true); setError("");
      try {
        const result = await api.confirmMapping(conversationId, proposal.id, proposal.version, proposal.fingerprint, selections, csrf);
        const history = await api.conversation(conversationId);
        onResult(result.workflow, history.messages);
      } catch (error) { setError(errorMessage(error)); }
      finally { setBusy(false); }
    }}>
      {proposal.sheets.map((sheet, i) => <fieldset key={`${sheet.file_id}:${sheet.sheet_index}`} disabled={busy}>
        <legend>{sheet.filename} · sheet {sheet.sheet_index + 1}</legend>
        <label>Document category<select value={selections[i].kind} onChange={(event) => {
          const kind = event.target.value;
          setSelections((current) => current.map((entry, j) => j === i ? { ...entry, kind, columns: {} } : entry));
        }}>
          <option value="unsupported">Select category</option>
          {Object.keys(proposal.categories).map((kind) => <option key={kind}>{kind}</option>)}
        </select></label>
        {(proposal.categories[selections[i].kind] ?? []).map((field) => <label key={field}>{field}
          <select value={selections[i].columns[field] ?? -1} onChange={(event) => {
            const column = Number(event.target.value);
            setSelections((current) => current.map((entry, j) => {
              if (i !== j) return entry;
              const columns = { ...entry.columns };
              if (column < 0) delete columns[field]; else columns[field] = column;
              return { ...entry, columns };
            }));
          }}>
            <option value={-1}>Select source column</option>
            {sheet.headers.map((header, column) => <option key={column} value={column}>{column + 1}: {header || "Empty header"}</option>)}
          </select>
        </label>)}
      </fieldset>)}
      {error && <p role="alert">{error}</p>}
      <button type="submit" disabled={busy || state.scope_fresh === false}>{busy ? "Checking confirmation…" : "Confirm mappings and run checks"}</button>
    </form>
  </details>;
}

export function Assistant({ conversation, append, canReadProjects, csrfToken, onBusy, canDesignateReports=false, canConfirmReports=false, projectPermissions={} }: {
  conversation?: Conversation; append: (conversationId: string, ...messages: ChatMessage[]) => void;
  projectPermissions?: Record<string,string[]>; canDesignateReports?: boolean; canConfirmReports?: boolean; canReadProjects: boolean; csrfToken: string; onBusy: (busy: boolean) => void;
}) {
  const pending = useRef<{ id?: string; message: string; requestId: string }>(undefined);
  const [draft, setDraft] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [workflow, setWorkflow] = useState<ConversationWorkflow>();
  const [files, setFiles] = useState<File[]>([]);
  const [open, setOpen] = useState(false);
  const [activity, setActivity] = useState<"connecting" | "processing">();
  const [steps, setSteps] = useState<string[]>([]);
  const [failedRequest, setFailedRequest] = useState<string>();
  const busy = activity !== undefined;
  const [submitted, setSubmitted] = useState<ChatMessage>();
  const textarea = useRef<HTMLTextAreaElement>(null);
  const sending = useRef(false);
  const [error, setError] = useState("");
  const [projects, setProjects] = useState<Project[]>();
  const [projectError, setProjectError] = useState(false);
  const [model, setModel] = useState("Checking Ollama…");
  const messages = conversation?.messages ?? [];

  useEffect(() => {
    const input = textarea.current;
    if (input) {
      input.style.height = "auto";
      input.style.height = `${input.scrollHeight}px`;
    }
  }, [draft]);

  useEffect(() => {
    if (!canReadProjects) return;
    let active = true;
    api.projects().then(
      (data) => {
        if (!active) return;
        setProjects(data);
        setProjectError(false);
        // Global source matching stays the default, including single-project accounts.
        // Selecting a legacy project scope is an explicit user action.
      },
      () => { if (active) setProjectError(true); },
    );
    api.aiStatus().then(
      ({ model, status }) => {
        if (active) setModel(status === "ready" ? `${model} available`
          : status === "model_missing" ? `${model} missing` : "Ollama unavailable");
      },
      () => { if (active) setModel("Ollama status unavailable"); },
    );
    return () => { active = false; };
  }, [canReadProjects]);

  useEffect(() => {
    if (!conversation?.id) return;
    let active = true;
    api.workflowState(conversation.id).then(
      (state) => { if (active) { setWorkflow(state); } },
      (error) => { if (active) { setWorkflow(undefined); setError(errorMessage(error)); } },
    );
    api.documents(conversation.id).then(
      (records) => { if (active) setDocuments(records); },
      (error) => { if (active) setError(errorMessage(error)); },
    );
    return () => { active = false; };
  }, [conversation?.id, conversation?.messages.length]);

  function refreshAfterEvidence() {
    if (!conversation?.id) return;
    const id = conversation.id;
    // Global receipts do not embed the column mapping proposal. Refresh the
    // independently persisted file statuses as well as the conversation.
    void Promise.all([api.conversation(id), api.documents(id), api.workflowState(id)])
      .then(([updated, records, state]) => {
        setDocuments(records);
        setWorkflow(state);
        const known = new Set(messages.map(message => message.id));
        append(id, ...updated.messages.filter(message => !known.has(message.id)));
      })
      .catch(err => setError(errorMessage(err)));
  }

  function selectFiles(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.currentTarget.files ?? []);
    setFiles((current) => [...current, ...selected.filter((file) => /\.(csv|xlsx)$/i.test(file.name))]);
    setError(selected.some((file) => !/\.(csv|xlsx)$/i.test(file.name)) ? "Select CSV or Excel files." : "");
    event.currentTarget.value = "";
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (sending.current || !message) return;
    let attempt: { id?: string; message: string; requestId: string };
    try {
      attempt = pending.current?.message === message ? pending.current : {
        id: pending.current?.id ?? conversation?.id, message, requestId: createRequestId(),
      };
    } catch {
      setError("Could not prepare this request. Reload the page or try another browser.");
      return;
    }
    sending.current = true;
    pending.current = attempt;
    const optimistic: ChatMessage = {
      id: attempt.requestId, role: "user", text: message, timestamp: new Date().toISOString(),
    };
    setSubmitted(optimistic);
    setFailedRequest(undefined);
    setSteps([attempt.id ? "Preparing your request" : "Opening a conversation"]);
    setDraft("");
    setActivity(attempt.id ? "processing" : "connecting");
    onBusy(true);
    setError("");
    let timer: ReturnType<typeof setInterval> | undefined;
    let polling = false;
    let inFlight = false;
    let sent = false;
    async function refreshSteps() {
      if (!attempt.id || inFlight) return;
      inFlight = true;
      try {
        const update = await api.assistantActivity(attempt.id, attempt.requestId);
        if (polling && update.steps.length) setSteps(update.steps);
      } catch {
        // Activity is supplemental; the message request reports its own failure.
      } finally { inFlight = false; }
    }
    try {
      const id = attempt.id ?? (await api.createConversation(csrfToken)).id;
      attempt.id = id;
      if (files.length) setSteps(["Uploading attachments for project mapping"]);
      for (const file of files) {
        const record = await api.uploadDocument(undefined, id, file, csrfToken);
        setDocuments((current) => [...current, record]);
        setFiles((current) => current.filter((item) => item !== file));
        append(id);
      }
      setActivity("processing");
      setSteps(["Sending your message"]);
      sent = true;
      polling = true;
      timer = setInterval(() => void refreshSteps(), 2000);
      const reply = await api.sendMessage(id, message, csrfToken, attempt.requestId);
      try {
        reply.message.activity = (await api.assistantActivity(id, attempt.requestId)).steps;
      } catch { /* The reply remains usable if the activity request fails. */ }
      append(id, { ...optimistic, timestamp: reply.message.timestamp }, reply.message);
      pending.current = undefined;
    } catch (error) {
      setError(errorMessage(error));
      setDraft(message);
      setFailedRequest(attempt.requestId);
      if (sent && attempt.id) {
        try {
          const update = await api.assistantActivity(attempt.id, attempt.requestId);
          if (update.steps.length) setSteps(update.steps);
        } catch { /* Retain the last known step. */ }
      }
    } finally {
      polling = false;
      clearInterval(timer);
      setSubmitted(undefined);
      setActivity(undefined);
      sending.current = false;
      onBusy(false);
      textarea.current?.focus();
    }
  }

  return <div className={`assistant-layout${open ? " assistant-layout--context" : ""}`}>
    <section className="assistant-chat glass-panel" aria-label="AI Assistant">
      <header className="assistant-toolbar"><h1>AI Workspace</h1>
        <button type="button" className="secondary" aria-expanded={open} aria-controls="assistant-context"
          onClick={() => setOpen(!open)}><PanelRight size={16} /> Context</button>
      </header>
      <div className="assistant-transcript" aria-live="polite">
        {messages.length === 0 && !submitted ? <div className="assistant-welcome">
          <span className="assistant-mark"><AgentAvatar size={76} /></span>
          <h2>How can I help you today?</h2>
          <p>Explore timesheets, staff activities, and payment preparation.</p>
          <div className="suggestions">{suggestions.map(({ label, text, Icon }) =>
            <button type="button" className="secondary" key={label} onClick={() => {
              setDraft(text); document.getElementById("chat-input")?.focus();
            }}><Icon size={18} aria-hidden="true" />{label}</button>)}</div>
        </div> : messages.map((message) => <Message key={message.id} message={message} csrf={csrfToken} />)}
        {submitted && <Message message={submitted} />}
        <ExecutionTimeline conversation={conversation?.id ?? pending.current?.id} busy={busy} />
        {(activity || failedRequest) && <ActivitySteps steps={steps} requestId={failedRequest} live />}
      </div>
      {workflow?.mapping?.status === "proposed" && conversation?.id && <MappingReview key={workflow.mapping.id}
        state={workflow} conversationId={conversation.id} csrf={csrfToken}
        onResult={(state, persistedMessages) => {
          setWorkflow(state);
          const knownIds = new Set(messages.map((message) => message.id));
          append(conversation.id, ...persistedMessages.filter((message) => !knownIds.has(message.id)));
        }} />}
      {!!workflow?.project_runs?.some(run=>run.validation_id) && <section className="report-register-panel"><h2>Planning and staff evidence reviews</h2><p>Open each saved project review, inspect the evidence, and record an authorized decision. Source mapping and report provenance do not replace these decisions.</p>{workflow.project_runs.filter(run=>run.validation_id).map(run=><p key={run.project_id}><a href={`#imports/validation/${run.validation_id}`}>Review project {run.project_id} planning and staff evidence →</a></p>)}</section>}
      <GlobalMappings conversation={conversation?.id} csrf={csrfToken} canConfirm={canConfirmReports} revision={messages.length+documents.length} onResumed={refreshAfterEvidence} />
      <ReportingRegisterPanel onResumed={refreshAfterEvidence} conversation={conversation?.id} csrf={csrfToken} canDesignate={canDesignateReports} canConfirm={canConfirmReports} revision={messages.length+documents.length} />
      <WorkflowFindings conversation={conversation?.id} csrf={csrfToken} permissions={projectPermissions} revision={messages.length+documents.length} onResumed={refreshAfterEvidence} />
      <WorkflowPayments conversation={conversation?.id} csrf={csrfToken} permissions={projectPermissions} revision={messages.length+documents.length} onResumed={refreshAfterEvidence} />
      <form className="chat-composer" onSubmit={submit}>
        <p className="muted"><Badge tone="cyan">Guarded operations</Badge> All active authorized projects are in context. Timmy matches this conversation's source rows by approved project and activity codes.</p>
        <label htmlFor="chat-input" className="sr-only">Message Agent Timmy</label>
        <textarea ref={textarea} id="chat-input" dir="auto" rows={2} placeholder="Message Agent Timmy…" maxLength={1500} value={draft}
          readOnly={busy} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }} />
        {workflow?.scope && <div role="status" aria-label="Persisted workflow state">
          <p>Workflow: {workflow.stage} · {workflow.scope.source_ids.length} files · {workflow.scope.source_rows} source rows in scope.</p>
          {workflow.mapping?.confirmation_method === "verified_format_reuse" && <p>Using your previously confirmed column format; routine checks continued automatically.</p>}
          {!!workflow.project_runs?.length && <div role="region" aria-label="Recorded project workflow steps">
            {workflow.project_runs.map((run) => <details key={run.project_id} open>
              <summary>Project {run.project_id} · {run.workflow_id} · Run #{run.run_id} · {run.status}</summary>
              <ol>{run.steps.map((step, index) => <li key={index}>{step.step}: {step.status}
                {step.issue_codes.length > 0 ? ` · ${step.issue_codes.join(", ")}` : ""}</li>)}</ol>
            </details>)}
          </div>}
          {workflow.validation && <p>{workflow.project_runs?.length ? "Global routing" : "Structural validation"}: {workflow.validation.status}
            {workflow.validation.run_id && ` · Run #${workflow.validation.run_id}`}
            {workflow.validation.error_code && ` · ${workflow.validation.error_code}`}</p>}
          {workflow.scope_fresh === false && <p>The source scope changed. Request Process to review a fresh mapping proposal.</p>}
          {workflow.mapping?.status === "confirmed" && <button type="button" className="secondary" disabled={busy}
            onClick={() => { setDraft("Revise column mappings"); textarea.current?.focus(); }}>Revise column mappings</button>}
        </div>}
        {documents.length > 0 && <ul className="attachment-list">{documents.map((document) =>
          <li key={document.id}><a href={documentDownload(document.id)} dir="auto">{document.filename}</a>
            <small>{document.rows} rows · {document.status === "MAPPING_CONFIRMED"
              ? "Column mapping confirmed · evidence review separate" : "Column mapping review required"}</small></li>)}</ul>}
        {files.length > 0 && <ul className="attachment-list">{files.map((file, i) =>
          <li key={i}><span dir="auto">{file.name}</span>
            <button type="button" className="secondary" aria-label={`Remove ${file.name}`}
              disabled={busy} onClick={() => setFiles(files.filter((_, index) => index !== i))}><X size={13} /></button></li>)}</ul>}
        {error && <p role="alert">{error}</p>}
        <div className="composer-actions">
          <label className="attach-control"><Paperclip size={17} aria-hidden="true" /> Attach files
            <input type="file" className="sr-only" accept=".csv,.xlsx" multiple disabled={busy} onChange={selectFiles} />
          </label>
          <div className="voice-controls">
          <Dictation csrf={csrfToken} disabled={busy} insert={(text) => {
            setDraft((current) => [current, text].filter(Boolean).join("\n").slice(0, 1500));
            textarea.current?.focus();
          }} />
          <button type="submit" className="composer-send" aria-label="Send message" aria-busy={busy} disabled={busy || !draft.trim()}>
            <ArrowUp size={20} aria-hidden="true" />
          </button>
          </div>
        </div>
      </form>
    </section>
    {open && <aside id="assistant-context" className="assistant-context glass-panel" aria-label="Conversation context">
      <h2>Conversation context</h2>
      {canReadProjects && <>
        <h3>Project context: all active authorized projects</h3>
        {projects ? <ul className="project-list">{projects
          .filter(project => project.status === "active" &&
            projectPermissions[String(project.id)]?.includes("projects:read") &&
            projectPermissions[String(project.id)]?.includes("timesheets.view"))
          .map(project => <li key={project.id}>{project.name}</li>)}</ul> :
          <p role="status" className="muted">{projectError ? "Projects unavailable" : "Loading authorized projects…"}</p>}
        <p className="muted">No project selection is required. Source rows are matched within this conversation; unrelated conversations are not included.</p>
        <p role="status" className="muted">{model}</p>
      </>}
      <dl className="status-list">
        <div><dt>Reporting period</dt><dd>Unavailable</dd></div>
        <div><dt>Processing</dt><dd>{busy ? "Request in progress" : "No task running"}</dd></div>
        <div><dt>Validation and approvals</dt><dd>Workflow API pending</dd></div>
      </dl>
      <h2>Selected documents</h2>
      {files.length ? <ul className="project-list">{files.map((file, i) => <li key={i} dir="auto">{file.name}</li>)}</ul>
        : <p className="muted">No files selected.</p>}
    </aside>}
  </div>;
}
