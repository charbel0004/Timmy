import { DemoWorkbook } from "./demo-workbook";
import { workspaceLocation } from "./workspace-location";
import { AccessManagement } from "./iam";
import { Administration, PasswordScreen } from "./workspace";
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, ApiError, errorMessage } from "./api";
import type { Session } from "./api";
import { StructuralReview, Dashboard, DocumentHistory, Login, OperationsPage, SettingsPanel } from "./features";
import { Badge, Brand, Icon } from "./design";
import { Assistant, ConversationHistory } from "./assistant";

import type { ChatMessage, Conversation } from "./chat";
import "./styles.css";

const pages = {
  assistant: "AI Assistant",
  dashboard: "Overview",
  projects: "Projects",
  activities: "Activities & Tasks",
  imports: "Timesheet Imports",
  timesheets: "Timesheets",
  discrepancies: "Discrepancies",
  batches: "Payments",
  access: "Access Management",
  users: "Users",
  roles: "Roles & Permissions",
  settings: "Settings",
  security: "Account Security",
} as const;
type Page = keyof typeof pages;

function Workspace({ session, onExit, onSession }: { session: Session; onExit: () => void; onSession: (session: Session) => void }) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string>();
  const [chatVersion, setChatVersion] = useState(0);
  const [historyError, setHistoryError] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [hash, setHash] = useState(() => window.location.hash);
  const location = workspaceLocation(hash);
  const page: Page = Object.hasOwn(pages, location.page) ? location.page as Page : "assistant";
  const { validationId } = location;
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const change = () => setHash(window.location.hash);
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  const canReadSettings = session.permissions.includes("settings:read");
  const visible = (key: Page) => key === "security" || session.permissions.includes(
    key === "settings" ? "settings:read" : (key === "users" || key === "access") ? "users:manage" : key === "roles" ? "roles:read" : "projects:read",
  );
  const canReadProjects = session.permissions.includes("projects:read");
  useEffect(() => {
    if (!canReadProjects) return;
    let active = true;
    api.conversations().then(
      (items) => { if (active) setConversations(items); },
      (error) => { if (active) setHistoryError(errorMessage(error)); },
    );
    return () => { active = false; };
  }, [canReadProjects]);

  async function openConversation(id?: string) {
    if (chatBusy) return;
    setChatBusy(true);
    setHistoryError("");
    try {
      if (id) {
        const item = await api.conversation(id);
        setConversations((current) => current.map((entry) => entry.id === id ? item : entry));
      }
      setActiveId(id);
      setChatVersion((current) => current + 1);
      window.location.hash = "assistant";
    } catch (error) {
      setHistoryError(errorMessage(error));
    } finally {
      setChatBusy(false);
    }
  }

  function append(id: string, ...messages: ChatMessage[]) {
    setActiveId(id);
    setConversations((current) => {
      const existing = current.find((item) => item.id === id);
      return [{ id, title: existing?.title, messages: [...(existing?.messages ?? []), ...messages] },
        ...current.filter((item) => item.id !== id)];
    });
  }
  async function manageChat(id: string, title?: string) {
    if (chatBusy) return;
    setChatBusy(true);
    setHistoryError("");
    try {
      if (title) {
        const updated = await api.renameConversation(id, title, session.csrf_token);
        setConversations((items) => items.map((item) => item.id === id ? updated : item));
      } else {
        await api.deleteConversation(id, session.csrf_token);
        setConversations((items) => items.filter((item) => item.id !== id));
        if (id === activeId) { setActiveId(undefined); setChatVersion((value) => value + 1); }
      }
    } catch (error) { setHistoryError(errorMessage(error)); }
    finally { setChatBusy(false); }
  }
  async function signOut() {
    setBusy(true);
    setError("");
    try {
      await api.logout(session.csrf_token);
      onExit();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onExit();
      else setError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }
  return <>
    <a className="sr-only focus:not-sr-only" href="#main" onClick={(event) => { event.preventDefault(); document.getElementById("main")?.focus(); }}>Skip to content</a>
    <div className="workspace">
      <aside className="sidebar glass-panel">
        <Brand />
        <nav aria-label="Workspace">
          {(Object.keys(pages) as Page[]).filter((key) => visible(key) && key !== "users" && key !== "roles").map((key) =>
            <a key={key} href={`#${key}`} aria-current={key === page ? "page" : undefined}>
              <Icon name={key} /><span>{pages[key]}</span>
            </a>)}
        </nav>
        <ConversationHistory conversations={conversations} activeId={page === "assistant" ? activeId : undefined}
          onSelect={openConversation} onNew={() => openConversation()} onRename={manageChat} onDelete={manageChat} />
        <div className="sidebar-footer"><div className="profile-name" dir="auto"><strong>{session.username}</strong><small>{session.role}</small></div>
          <button className="secondary" disabled={busy} onClick={signOut}><Icon name="logout" /> Sign out</button>
        </div>
      </aside>
      <div className="workspace-body">
        <header className="topbar glass-panel">
          <span className="topbar-title">{pages[page]}</span>
          <div className="account">
            {session.demo_mode && <Badge tone="amber">Demo mode</Badge>}

          </div>
        </header>
        <main id="main" tabIndex={-1} className="workspace-content">
          {page !== "dashboard" && page !== "assistant" && !["access", "users", "roles"].includes(page) && <h1 className="page-heading">{pages[page]}</h1>}
          {error && <p role="alert" className="mb-4">{error}</p>}
          {page === "assistant" && <>
            {historyError && <p role="alert">{historyError}</p>}
            {canReadProjects ? <Assistant key={chatVersion} conversation={conversations.find((item) => item.id === activeId)}
              append={append} canReadProjects={canReadProjects} csrfToken={session.csrf_token}
              onBusy={setChatBusy} /> : <p role="alert">Permission denied.</p>}
          </>}
          {session.demo_mode && (page === "dashboard" || page === "projects" || page === "imports" || page === "batches")
            && <DemoWorkbook key={page} show={page} />}
          {page === "dashboard" && (canReadProjects ? <Dashboard /> : <p role="alert">Permission denied.</p>)}
          {page === "settings" && (canReadSettings ? <SettingsPanel /> : <p role="alert">Permission denied.</p>)}
          {(page === "projects" || page === "activities") &&
            (visible(page) ? <Administration key={page} page={page} session={session} /> : <p role="alert">Permission denied.</p>)}
          {(page === "access" || page === "users" || page === "roles") &&
            (visible("access") ? <AccessManagement session={session} /> : <p role="alert">Permission denied.</p>)}
          {page === "imports" && canReadProjects && <><DocumentHistory /><StructuralReview key={validationId ?? "project"} session={session} validationId={validationId} /></>}
          {(page === "imports" || page === "timesheets" || page === "discrepancies" || page === "batches") &&
            (canReadProjects ? <OperationsPage key={page} section={page} /> : <p role="alert">Permission denied.</p>)}
          {page === "security" && <PasswordScreen session={session} onDone={(value) => {
            if (value) { onSession(value); window.location.hash = "assistant"; }
          }} />}

        </main>
      </div>
    </div>
  </>;
}

function App() {
  const [session, setSession] = useState<Session | null>();
  const [activation, setActivation] = useState(() => {
    const hash = window.location.hash;
    if (hash.startsWith("#activate=")) {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
      return hash.slice("#activate=".length);
    }
  });
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    api.session().then(
      (value) => { if (active) setSession(value); },
      (error) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) setSession(null);
        else setError(errorMessage(error));
      },
    );
    return () => { active = false; };
  }, [attempt]);
  if (activation) return <PasswordScreen activation={activation} onDone={() => { setActivation(undefined); setSession(null); }} />;
  if (session?.must_change_password) return <PasswordScreen session={session} onDone={setSession} />;
  if (error) return <main className="mx-auto mt-20 max-w-md px-5">
    <h1>Agent Timmy</h1><p role="alert" className="my-4">{error}</p>
    <button onClick={() => { setError(""); setAttempt(attempt + 1); }}>Retry</button>
  </main>;
  if (session === undefined) return <p role="status" className="p-6">Checking session…</p>;
  return session ? <Workspace session={session} onSession={setSession} onExit={() => setSession(null)} /> : <Login onLogin={setSession} />;
}

createRoot(document.getElementById("root")!).render(<App />);
