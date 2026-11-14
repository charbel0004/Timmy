import { Dictation, SpokenResponse } from "./voice";
import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { ArrowUp, CalendarDays, Copy, FileSpreadsheet, ListFilter, Paperclip, PanelRight, Plus, Sparkles, Wallet, X } from "lucide-react";
import Markdown from "react-markdown";
import { api, documentDownload, errorMessage } from "./api";
import type { DocumentRecord, Project } from "./api";
import type { ChatMessage, Conversation } from "./chat";
import { Badge } from "./design";

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

function Message({ message, csrf }: { message: ChatMessage; csrf?: string }) {
  const [copyStatus, setCopyStatus] = useState("");
  return <article className={`chat-message chat-message--${message.role}`}>
    <header>{message.role === "assistant" && <Sparkles className="message-avatar" size={18} aria-hidden="true" />}<strong>{message.role === "user" ? "You" : "Agent Timmy"}</strong>
      <time dateTime={message.timestamp}>{new Date(message.timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</time>
    </header>
    <div dir="auto" className="message-body">
      {message.role === "assistant" ? <Markdown skipHtml>{message.text}</Markdown> : <p>{message.text}</p>}
    </div>
    {!!message.attachments?.length && <ul className="attachment-list">{message.attachments.map((name, i) =>
      <li key={i} dir="auto">{name}</li>)}</ul>}
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

export function Assistant({ conversation, append, canReadProjects, csrfToken, onBusy }: {
  conversation?: Conversation; append: (conversationId: string, ...messages: ChatMessage[]) => void;
  canReadProjects: boolean; csrfToken: string; onBusy: (busy: boolean) => void;
}) {
  const pending = useRef<{ id?: string; message: string; requestId: string }>(undefined);
  const [draft, setDraft] = useState("");
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [open, setOpen] = useState(false);
  const [activity, setActivity] = useState<"connecting" | "processing">();
  const busy = activity !== undefined;
  const [submitted, setSubmitted] = useState<ChatMessage>();
  const textarea = useRef<HTMLTextAreaElement>(null);
  const sending = useRef(false);
  const [error, setError] = useState("");
  const [projects, setProjects] = useState<Project[]>();
  const [projectError, setProjectError] = useState(false);
  const [projectId, setProjectId] = useState<number>();
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
    if (!canReadProjects || !open) return;
    let active = true;
    api.projects().then(
      (data) => { if (active) { setProjects(data); setProjectError(false); } },
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
  }, [canReadProjects, open]);

  useEffect(() => {
    if (!conversation?.id) return;
    let active = true;
    api.documents(conversation.id).then(
      (records) => { if (active) setDocuments(records); },
      (error) => { if (active) setError(errorMessage(error)); },
    );
    return () => { active = false; };
  }, [conversation?.id]);

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
    if (files.length && projectId === undefined) {
      setOpen(true);
      setError("Open Context and select an active project for these files.");
      return;
    }
    sending.current = true;
    const attempt = pending.current?.message === message ? pending.current : {
      id: pending.current?.id ?? conversation?.id, message, requestId: crypto.randomUUID(),
    };
    pending.current = attempt;
    const optimistic: ChatMessage = {
      id: attempt.requestId, role: "user", text: message, timestamp: new Date().toISOString(),
    };
    setSubmitted(optimistic);
    setDraft("");
    setActivity(attempt.id ? "processing" : "connecting");
    onBusy(true);
    setError("");
    try {
      const id = attempt.id ?? (await api.createConversation(csrfToken)).id;
      attempt.id = id;
      if (projectId !== undefined) {
        for (const file of files) {
          const record = await api.uploadDocument(projectId, id, file, csrfToken);
          setDocuments((current) => [...current, record]);
          setFiles((current) => current.filter((item) => item !== file));
          append(id);
        }
      }
      setActivity("processing");
      const reply = await api.sendMessage(id, message, csrfToken, attempt.requestId);
      append(id, { ...optimistic, timestamp: reply.message.timestamp }, reply.message);
      pending.current = undefined;
    } catch (error) {
      setError(errorMessage(error));
      setDraft(message);
    } finally {
      setSubmitted(undefined);
      setActivity(undefined);
      sending.current = false;
      onBusy(false);
      textarea.current?.focus();
    }
  }

  return <div className={`assistant-layout${open ? " assistant-layout--context" : ""}`}>
    <section className="assistant-chat glass-panel" aria-label="AI Assistant">
      <header className="assistant-toolbar"><h1>AI Assistant</h1>
        <button type="button" className="secondary" aria-expanded={open} aria-controls="assistant-context"
          onClick={() => setOpen(!open)}><PanelRight size={16} /> Context</button>
      </header>
      <div className="assistant-transcript" aria-live="polite">
        {messages.length === 0 && !submitted ? <div className="assistant-welcome">
          <span className="assistant-mark"><Sparkles size={29} aria-hidden="true" /></span>
          <h2>How can I help you today?</h2>
          <p>Explore timesheets, staff activities, and payment preparation.</p>
          <div className="suggestions">{suggestions.map(({ label, text, Icon }) =>
            <button type="button" className="secondary" key={label} onClick={() => {
              setDraft(text); document.getElementById("chat-input")?.focus();
            }}><Icon size={18} aria-hidden="true" />{label}</button>)}</div>
        </div> : messages.map((message) => <Message key={message.id} message={message} csrf={csrfToken} />)}
        {submitted && <Message message={submitted} />}
        {activity && <p className="assistant-activity" role="status"><Sparkles size={16} aria-hidden="true" />
          {activity === "connecting" ? "Connecting…" : "Processing your request…"}</p>}
      </div>
      <form className="chat-composer" onSubmit={submit}>
        <p className="muted"><Badge tone="cyan">Local Ollama</Badge> Select a project in Context before sending CSV or XLSX files.</p>
        <label htmlFor="chat-input" className="sr-only">Message Agent Timmy</label>
        <textarea ref={textarea} id="chat-input" dir="auto" rows={2} placeholder="Message Agent Timmy…" maxLength={1500} value={draft}
          readOnly={busy} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }} />
        {documents.length > 0 && <ul className="attachment-list">{documents.map((document) =>
          <li key={document.id}><a href={documentDownload(document.id)} dir="auto">{document.filename}</a>
            <small>{document.rows} rows · Mapping required</small></li>)}</ul>}
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
      {canReadProjects && <><label htmlFor="chat-project">Project</label>
        <select id="chat-project" value={projectId ?? ""} disabled={!projects?.length}
          onChange={(event) => setProjectId(event.target.value ? Number(event.target.value) : undefined)}>
          <option value="">{projects ? (projects.length ? "Select a project" : "No assigned projects")
            : projectError ? "Projects unavailable" : "Loading projects…"}</option>
          {projects?.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select>
        <p role="status" className="muted">{model}</p></>}
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
