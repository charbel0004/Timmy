import { Observatory, ExecutionSummary } from "./observatory";
import { MotionConfig, motion } from "motion/react";
import { Menu, Moon, Sun } from "lucide-react";
import { DemoWorkbook } from "./demo-workbook";
import { workspaceLocation } from "./workspace-location";
import { AccessManagement } from "./iam";
import { Administration, PasswordScreen } from "./workspace";
import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, ApiError, errorMessage } from "./api";
import type { Session } from "./api";
import { StructuralReview, LocalAI, Dashboard, DocumentHistory, Login, OperationsPage, SettingsPanel } from "./features";
import { Badge, Brand, Icon } from "./design";
import { Assistant, ConversationHistory } from "./assistant";

import type { ChatMessage, Conversation } from "./chat";
import "./styles.css";

const pages = {
  dashboard: "Overview",
  assistant: "AI Workspace",
  projects: "Projects",
  activities: "Activities",
  imports: "Timesheet Imports",
  timesheets: "Timesheets",
  discrepancies: "Discrepancies",
  evidence: "Evidence Review",
  batches: "Payments",
  reconciliation: "Reconciliation",
  observatory: "Execution Observatory",
  reports: "Reports",
  access: "Administration",
  users: "Users",
  roles: "Roles & Permissions",
  settings: "Settings",
  security: "Account Security",
} as const;
type Page = keyof typeof pages;

function Workspace({ session, onExit, onSession }: { session: Session; onExit: () => void; onSession: (session: Session) => void }) {
  const [theme, setTheme] = useState(() => localStorage.getItem("timmy-theme") || (matchMedia('(prefers-color-scheme: dark)').matches ? "dark" : "light"));
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.setItem("timmy-theme", theme); }, [theme]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string>();
  const [chatVersion, setChatVersion] = useState(0);
  const [historyError, setHistoryError] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [hash, setHash] = useState(() => window.location.hash);
  const location = workspaceLocation(hash);
  if (hash.startsWith("#observatory/")) location.page = "observatory";
  if (/^#assistant\/[0-9a-f-]{36}$/.test(hash)) location.page = "assistant";
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
  const hasGrant = (permission: string) => session.permissions.includes(permission) || Object.values(session.project_permissions).some((grants) => grants.includes(permission));
  const visible = (key: Page) => key === "security" || hasGrant(
    key === "settings" ? "settings:read" : (key === "users" || key === "access") ? "users:manage" : key === "roles" ? "roles:read"
      : key === "activities" ? "activities.view" : ["imports", "timesheets", "evidence"].includes(key) ? "timesheets.view"
        : key === "discrepancies" ? "discrepancies.view" : ["batches", "reconciliation"].includes(key) ? "payments.view" : "projects:read",
  );
  const canReadProjects = session.permissions.includes("projects:read");
  useEffect(() => {
    if (!canReadProjects) return;
    let active = true;
    api.conversations().then(
      (items) => { if (active) setConversations(current => items.map(item => current.find(existing => existing.id === item.id) ?? item)); },
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
        setConversations((current) => [item, ...current.filter(entry => entry.id !== id)]);
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

  useEffect(() => {
    const target = /^#assistant\/([0-9a-f-]{36})$/.exec(hash)?.[1];
    if (target && target !== activeId && !chatBusy) void openConversation(target);
  }, [hash]);

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
    <MotionConfig reducedMotion="user" transition={{ duration: 0.2 }}><div className={`workspace${collapsed ? " sidebar-collapsed" : ""}`}>
      <aside className="sidebar glass-panel">
        <Brand />
        <nav aria-label="Workspace">
          {(Object.keys(pages) as Page[]).filter((key) => visible(key) && key !== "users" && key !== "roles").map((key) =>
            <a key={key} href={`#${key}`} aria-label={pages[key]} title={pages[key]} aria-current={key === page ? "page" : undefined}>
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
          <div className="topbar-context"><button className="secondary shell-toggle" aria-label="Toggle navigation" aria-expanded={!collapsed} onClick={() => setCollapsed(!collapsed)}><Menu size={17} /></button><span className="muted">Workspace /</span><span className="topbar-title">{pages[page]}</span></div>
          <div className="account">
            {canReadProjects && <div className="topbar-system-status" title="Ollama status checked when the workspace opens"><LocalAI /></div>}
            <a href="#security" className="account-link">{session.username}<small>{session.role}</small></a>
            <button className="secondary theme-toggle" aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}</button>
            {session.demo_mode && <Badge tone="amber">Demo mode</Badge>}

          </div>
        </header>
        <motion.main key={page} initial={{ opacity: 0 }} animate={{ opacity: 1 }} id="main" tabIndex={-1} className="workspace-content">
          {page !== "observatory" && page !== "dashboard" && page !== "assistant" && !["access", "users", "roles"].includes(page) && <h1 className="page-heading">{pages[page]}</h1>}
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
          {page === "observatory" && canReadProjects && <Observatory />}
          {page === "reports" && canReadProjects && <ExecutionSummary />}
          {page === "reconciliation" && visible(page) && <section className="glass-panel operation-panel"><h2>External payment reconciliation</h2><p className="muted">Use the existing guarded reconciliation workflow in AI Workspace with the payment report attached. Its stored receipts identify source evidence, unmatched records, and approval blockers.</p><a href="#assistant" className="hero-action">Open reconciliation workspace →</a><p className="muted">External settlement remains a separate source of authority. The payment obligation summary adapter is unavailable.</p></section>}
          {page === "settings" && (canReadSettings ? <SettingsPanel /> : <p role="alert">Permission denied.</p>)}
          {(page === "projects" || page === "activities") &&
            (visible(page) ? <Administration key={page} page={page} session={session} /> : <p role="alert">Permission denied.</p>)}
          {(page === "access" || page === "users" || page === "roles") &&
            (visible("access") ? <AccessManagement session={session} /> : <p role="alert">Permission denied.</p>)}
          {page === "evidence" && visible(page) && <StructuralReview session={session} />}
          {page === "imports" && visible(page) && <><DocumentHistory /><StructuralReview key={validationId ?? "project"} session={session} validationId={validationId} /></>}
          {(page === "imports" || page === "timesheets" || page === "discrepancies" || page === "batches") &&
            (canReadProjects ? <OperationsPage key={page} section={page} /> : <p role="alert">Permission denied.</p>)}
          {page === "security" && <PasswordScreen session={session} onDone={(value) => {
            if (value) { onSession(value); window.location.hash = "assistant"; }
          }} />}

        </motion.main>
      </div>
    </div></MotionConfig>
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
