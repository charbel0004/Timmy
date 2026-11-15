import { ProjectPaymentPolicies } from "./payment-policy";
import { Dialog } from "./iam-users";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { errorMessage, request } from "./api";
import type { Session } from "./api";

interface Project { id: number; name: string; project_code: string | null; policy_family: "session" | "hours" | null; status: string }
interface Activity { id: number; name: string; project: string; activity_code: string | null; code_authority: string; planned_start: string | null; planned_end: string | null }
function mutate<T>(path: string, method: string, csrf?: string, body?: object) {
  return request<T>(`/workspace${path}`, {
    method,
    headers: { ...(csrf ? { "X-CSRF-Token": csrf } : {}), ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
}

export function PasswordScreen({ session, activation, onDone }: {
  session?: Session; activation?: string; onDone: (value?: Session) => void;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const password = String(fields.get("password"));
    if (password !== fields.get("confirm")) { setError("Passwords must match."); return; }
    setBusy(true);
    setError("");
    try {
      if (activation) {
        await mutate("/activate", "POST", undefined, { token: activation, password });
        onDone();
      } else {
        onDone(await mutate<Session>("/password", "POST", session?.csrf_token, {
          current_password: fields.get("current"), password,
        }));
      }
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return <main className="mx-auto mt-12 max-w-lg px-4"><form className="glass-panel admin-form" onSubmit={submit}>
    <h1>{activation ? "Activate your account" : "Change password"}</h1>
    {!activation && <label>Current password<input type="password" name="current" required autoComplete="current-password" /></label>}
    <label>New password<input type="password" name="password" minLength={12} maxLength={1024} required autoComplete="new-password" /></label>
    <label>Confirm new password<input type="password" name="confirm" minLength={12} maxLength={1024} required autoComplete="new-password" /></label>
    {error && <p role="alert">{error}</p>}<button disabled={busy}>{busy ? "Saving…" : "Save password"}</button>
  </form></main>;
}

function ProjectSelect({ projects }: { projects: Project[] }) {
  return <label>Project<select name="project" required defaultValue="">
    <option value="">Choose a project</option>
    {projects.map((project) => <option key={project.id} value={project.id}>{project.name} · {project.status}</option>)}
  </select></label>;
}

const transitionOptions: Record<string, string[]> = {
  draft: ["activate", "archive"], active: ["complete", "archive"], completed: ["archive"], archived: ["restore"],
};

export function Administration({ page, session }: {
  page: "projects" | "activities"; session: Session;
}) {
  const [scopeFilter, setScopeFilter] = useState(() => new URLSearchParams(window.location.hash.split("?")[1] || "").get("status") || "all");
  const [projects, setProjects] = useState<Project[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const canManage = session.permissions.includes("projects:manage");

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const scoped = await request<Project[]>("/workspace/projects");
        if (active) setProjects(scoped);
        if (page === "activities") {
          const records = await request<Activity[]>("/workspace/activities");
          if (active) setActivities(records);
        }
      } catch (error) { if (active) setError(errorMessage(error)); }
      finally { if (active) setBusy(false); }
    };
    void load();
    return () => { active = false; };
  }, [page, revision]);

  async function save(path: string, method: string, body?: object) {
    setError(""); setBusy(true);
    try {
      await mutate(path, method, session.csrf_token, body);
      if (path === "/projects" && method === "POST") { setCreating(false); setNotice("Project created."); }
      setRevision((value) => value + 1);
    } catch (error) { setError(errorMessage(error)); setBusy(false); }
  }
  function submit(event: FormEvent<HTMLFormElement>, use: (fields: FormData) => void) {
    event.preventDefault();
    use(new FormData(event.currentTarget));
  }

  return <section className="admin-grid" aria-busy={busy}>
    {busy && <p role="status">Loading workspace…</p>}
    {error && !creating && <p role="alert">{error}</p>}
    {page === "projects" && <>
      <div className="iam-heading"><p className="muted">Manage project access and lifecycle.</p>
        {canManage && <button disabled={busy} onClick={() => { setError(""); setNotice(""); setCreating(true); }}>New project</button>}</div>
      <label className="operation-filter">Project status<select value={scopeFilter} onChange={(event) => setScopeFilter(event.target.value)}>{['all', 'active', 'draft', 'completed', 'archived'].map(status => <option key={status}>{status}</option>)}</select></label>
      {notice && <p role="status">{notice}</p>}
      {creating && <Dialog title="New project" close={() => { if (!busy) setCreating(false); }}>
        <form className="admin-form" onSubmit={(event) => submit(event, (fields) =>
          void save("/projects", "POST", { name: fields.get("name"), code: fields.get("code"),
            policy_family: fields.get("policy_family") }))}>
          <div className="iam-fields"><label>Project name<input name="name" required maxLength={160} /></label>
            <label>Project acronym<input name="code" required maxLength={80} /></label></div>
          <label>Payment policy<select name="policy_family" required defaultValue="">
            <option value="" disabled>Select policy type</option>
            <option value="session">Session-based</option>
            <option value="hours">Hours-based</option>
          </select></label>
          <p className="muted">Policy rules are fixed in the application. No project-specific rate or rule editing.</p>
          {error && <p role="alert">{error}</p>}
          <footer className="iam-footer"><button type="button" className="secondary" disabled={busy} onClick={() => setCreating(false)}>Cancel</button>
            <button disabled={busy}>{busy ? "Creating…" : "Create project"}</button></footer>
        </form>
      </Dialog>}
      {!busy && !error && !projects.length && <p>No projects available.</p>}
      {projects.filter(project => scopeFilter === "all" || project.status === scopeFilter).map((project) => <article key={project.id} className="glass-panel admin-form">
        <h2 dir="auto">{project.name}</h2><p>{project.project_code ?? "Code unassigned"} · {project.status} · {project.policy_family === "session" ? "Session-based" : project.policy_family === "hours" ? "Hours-based (policy pending approval)" : "Legacy project: policy type unassigned"}</p>
        {canManage && project.status !== "archived" && <details><summary>Edit project</summary>
          <form className="admin-grid" onSubmit={(event) => submit(event, (f) =>
            void save(`/projects/${project.id}`, "PATCH", { name: f.get("name"), code: f.get("code") }))}>
            <label>Name<input required name="name" defaultValue={project.name} maxLength={160} /></label>
            <label>Project code<input required name="code" defaultValue={project.project_code ?? ""} maxLength={80} /></label>
            <button disabled={busy}>Save project</button>
          </form></details>}
        <ProjectPaymentPolicies projectId={project.id} csrf={session.csrf_token} canManage={canManage && ["draft", "active"].includes(project.status)} />
        <div className="admin-actions">{canManage && transitionOptions[project.status]?.map((action) =>
          <button className="secondary capitalize" key={action} disabled={busy} onClick={() => {
            if ((action === "archive" || action === "complete") && !window.confirm(`${action} ${project.name}?`)) return;
            void save(`/projects/${project.id}/transition`, "POST", { action });
          }}>{({ activate: "Activate project", complete: "Mark complete", archive: "Archive", restore: "Restore" } as Record<string, string>)[action]}</button>)}
        {session.permissions.includes("projects.delete") && <button className="secondary" disabled={busy} onClick={() => {
          if (window.confirm(`Permanently delete ${project.name}?`)) void save(`/projects/${project.id}?confirmed=true`, "DELETE");
        }}>Delete permanently</button>}</div>
      </article>)}
    </>}
    {page === "activities" && <>
      <div className="glass-panel admin-form"><h2>Project activities</h2>
        <p>Activities are events imported from planning. Their permanent codes link planning, timesheets and reports to this list.</p>
        <p>Process the planning sheet in the assistant. Codes must be supplied by authoritative planning. Missing codes are blocked; Timmy never generates them.</p>
        {!busy && !error && !activities.length && <p>No activities recorded.</p>}
        <ul>{activities.map((item) => <li key={item.id}>{item.project} · {item.activity_code ?? "Legacy activity: planning link required"} · {item.name}
          {item.code_authority !== "source_supplied" && <small> · Legacy identity: source-authority review required</small>}
          {item.planned_start && <small> · {item.planned_start} – {item.planned_end} · Imported planning evidence; approval remains separate</small>}</li>)}</ul>
      </div>
    </>}
  </section>;
}
