import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { request, errorMessage } from "./api";
import { Badge } from "./design";

export type User = { id: number; username: string; first_name?: string; last_name?: string; email?: string;
  role: string; active: boolean; activation_pending: boolean; password_change_required: boolean;
  project_permissions: Record<string, string[]>; project_overrides: Record<string, string[]>;
  project_ids: number[]; extra_roles: number[]; scoped_roles: Record<string, number[]> };
type Project = { id: number; name: string };
type Role = { id: number; name: string; description: string; permissions: string[] };
export const titleCase = (value: string) => value.replace(/[_.:-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const nameOf = (user: User) => [user.first_name, user.last_name].filter(Boolean).join(" ") || user.username;
const statusOf = (user: User) => user.activation_pending ? "Pending activation" : !user.active ? "Inactive" : user.password_change_required ? "Password change required" : "Active";

export function Dialog({ title, close, children }: { title: string; close: () => void; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return <dialog ref={dialog} className="iam-dialog" aria-labelledby="iam-dialog-title" onCancel={(event) => { event.preventDefault(); close(); }}>
    <header><h2 id="iam-dialog-title">{title}</h2><button type="button" className="secondary" onClick={close}>Close</button></header>
    {children}
  </dialog>;
}

export function Directory({ users, projects, roles, custom, csrf, username, adding, setAdding, reload }: {
  users: User[]; projects: Project[]; roles: Record<string, string[]>; custom: Role[];
  csrf: string; username: string; adding: boolean; setAdding: (value: boolean) => void; reload: () => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const [status, setStatus] = useState("");
  const [project, setProject] = useState("");
  const [sort, setSort] = useState<{ key: "name" | "username" | "role" | "status"; desc: boolean }>({ key: "name", desc: false });
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<User>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [secret, setSecret] = useState("");
  const value = (user: User) => sort.key === "name" ? nameOf(user) : sort.key === "status" ? statusOf(user) : user[sort.key];
  const rows = users.filter((user) => (!filter || user.role === filter) && (!status || statusOf(user) === status)
    && (!project || user.project_ids.includes(Number(project)))
    && [nameOf(user), user.username, user.email].join(" ").toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => value(a).localeCompare(value(b)) * (sort.desc ? -1 : 1));
  const currentPage = Math.min(page, Math.max(0, Math.ceil(rows.length / 12) - 1));

  async function save(path: string, method: string, body: object) {
    setError(""); setBusy(true);
    try {
      const result = await request<{ temporary_password?: string; activation_url?: string } | undefined>(`/workspace${path}`, {
        method, headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(body),
      });
      setSecret(result?.temporary_password ?? result?.activation_url ?? "");
      setAdding(false); setSelected(undefined); reload();
    } catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return <section className="glass-panel admin-form">
    <div className="iam-filters">
      <label>Search users<input type="search" value={query} onChange={(e) => { setQuery(e.target.value); setPage(0); }} /></label>
      <label>Role<select value={filter} onChange={(e) => { setFilter(e.target.value); setPage(0); }}><option value="">All roles</option>
        {Object.keys(roles).map((role) => <option key={role} value={role}>{titleCase(role)}</option>)}</select></label>
      <label>Status<select value={status} onChange={(e) => { setStatus(e.target.value); setPage(0); }}><option value="">All statuses</option>
        {["Active", "Inactive", "Pending activation", "Password change required"].map((item) => <option key={item}>{item}</option>)}</select></label>
      <label>Project<select value={project} onChange={(e) => { setProject(e.target.value); setPage(0); }}><option value="">All projects</option>
        {projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    </div>
    <div className="chat-table" tabIndex={0} role="region" aria-label="User directory"><table>
      <thead><tr>{(["name", "username", "role", "status"] as const).map((key) => <th key={key} scope="col"
        aria-sort={sort.key === key ? sort.desc ? "descending" : "ascending" : undefined}>
        <button className="secondary" onClick={() => setSort({ key, desc: sort.key === key && !sort.desc })}>
          {{ name: "User", username: "Username", role: "Roles", status: "Account status" }[key]}</button></th>)}
        <th scope="col">Projects</th><th scope="col">Actions</th></tr></thead>
      <tbody>{rows.slice(currentPage * 12, (currentPage + 1) * 12).map((user) => <tr key={user.id}>
        <td><strong dir="auto">{nameOf(user)}</strong><div className="muted">{user.email}</div></td><td>{user.username}</td>
        <td>{[titleCase(user.role), ...custom.filter((role) => user.extra_roles.includes(role.id)).map((role) => role.name)].join(", ")}</td>
        <td><Badge tone={user.active ? "green" : "amber"}>{statusOf(user)}</Badge></td><td>{user.project_ids.length}</td>
        <td><button className="secondary" aria-label={`Details for ${user.username}`} onClick={() => { setError(""); setSelected(user); }}>Details</button></td>
      </tr>)}</tbody>
    </table></div>
    {!rows.length && <p className="muted">No users match these filters.</p>}
    {rows.length > 12 && <div className="admin-actions"><button className="secondary" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button>
      <span>Page {currentPage + 1} of {Math.ceil(rows.length / 12)}</span>
      <button className="secondary" disabled={(currentPage + 1) * 12 >= rows.length} onClick={() => setPage(currentPage + 1)}>Next</button></div>}
    {adding && <Wizard roles={roles} custom={custom} projects={projects} busy={busy} error={error}
      close={() => { if (!busy) { setError(""); setAdding(false); } }} create={(body) => void save("/users", "POST", body)} />}
    {selected && <Dialog title={nameOf(selected)} close={() => { if (!busy) setSelected(undefined); }}>
      <div className="admin-grid">
        <div><h3>Profile</h3><p>{selected.username} · {selected.email || "Email unavailable"}</p><Badge>{statusOf(selected)}</Badge></div>
        {error && <p role="alert">{error}</p>}
        {selected.username !== username && <>
          <form className="admin-grid" onSubmit={(event) => {
            event.preventDefault(); const fields = new FormData(event.currentTarget);
            void save(`/users/${selected.id}`, "PATCH", { role: fields.get("role"), active: fields.has("active"), project_ids: fields.getAll("project").map(Number) });
          }}>
            <label>Primary role<select name="role" defaultValue={selected.role}>{Object.keys(roles).map((role) => <option key={role} value={role}>{titleCase(role)}</option>)}</select></label>
            <fieldset><legend>Project access</legend>{projects.map((item) => <label className="iam-check" key={item.id}>
              <input type="checkbox" className="admin-checkbox" name="project" value={item.id} defaultChecked={selected.project_ids.includes(item.id)} /> {item.name}</label>)}</fieldset>
            <label className="iam-check"><input type="checkbox" className="admin-checkbox" name="active" defaultChecked={selected.active} /> Active account</label>
            <div><button disabled={busy}>Save account</button></div>
          </form>
          <form className="iam-filters" onSubmit={(event) => {
            event.preventDefault(); const mode = new FormData(event.currentTarget).get("mode");
            if (window.confirm(`Reset credentials for ${selected.username}?`)) void save(`/users/${selected.id}/reset`, "POST", { mode });
          }}><label>Security<select name="mode"><option value="temporary">Temporary password</option><option value="activation">Activation link</option></select></label>
            <button disabled={busy} className="secondary">Reset credentials</button></form>
        </>}
      </div>
    </Dialog>}
    {secret && <Dialog title="One-time onboarding details" close={() => setSecret("")}>
      <p>Share these privately with the intended user.</p><code className="iam-secret">{secret}</code>
    </Dialog>}
  </section>;
}

function Wizard({ roles, custom, projects, busy, error, close, create }: {
  roles: Record<string, string[]>; custom: Role[]; projects: Project[]; busy: boolean; error: string;
  close: () => void; create: (body: object) => void;
}) {
  const [step, setStep] = useState(0);
  const [identity, setIdentity] = useState({ first_name: "", middle_name: "", last_name: "", email: "", username: "" });
  const [mode, setMode] = useState("temporary");
  const [role, setRole] = useState("viewer");
  const [roleSearch, setRoleSearch] = useState("");
  const [projectIds, setProjectIds] = useState<number[]>([]);
  const [extraRoles, setExtraRoles] = useState<number[]>([]);
  const fields = { first_name: "First name", middle_name: "Middle name", last_name: "Last name", email: "Email", username: "Username" } as const;
  const steps = ["Personal Information", "Account Setup", "Roles & Project Access", "Review & Create"];
  const methods = { temporary: ["Temporary password", "The user changes the generated password at first login."],
    activation: ["Activation link", "Share a single-use link privately so the user can set a password."] };
  const permissions = [...new Set([...(roles[role] ?? []), ...custom.filter((item) => extraRoles.includes(item.id)).flatMap((item) => item.permissions)])];
  return <Dialog title="Add user" close={close}>
    <ol className="iam-steps">{steps.map((label, i) => <li key={label} aria-current={step === i ? "step" : undefined}>{i + 1}. {label}</li>)}</ol>
    <form className="admin-grid" onSubmit={(event) => {
      event.preventDefault();
      if (step < 3) setStep(step + 1);
      else create({ ...identity, mode, role, project_ids: projectIds, extra_roles: extraRoles });
    }}>
      <h3>{steps[step]}</h3>
      {step === 0 && <div className="iam-identity">{(Object.keys(fields) as (keyof typeof fields)[]).map((key) =>
        <label key={key} className={`iam-field-${key}`}>{fields[key]}{key === "middle_name" && " (optional)"}
          <input type={key === "email" ? "email" : "text"} maxLength={key === "email" ? 254 : 80}
            required={key !== "middle_name"} pattern={key === "middle_name" ? undefined : ".*\\S.*"} value={identity[key]}
            onChange={(event) => setIdentity({ ...identity, [key]: event.target.value })} /></label>)}</div>}
      {step === 1 && <fieldset className="iam-fields"><legend>Onboarding method</legend>{Object.entries(methods).map(([key, [label, help]]) =>
        <label className="iam-choice" key={key}><input className="admin-checkbox" type="radio" name="onboarding" checked={mode === key} onChange={() => setMode(key)} />
          <strong>{label}</strong><small>{help}</small></label>)}</fieldset>}
      {step === 2 && <div className="iam-fields">
        <fieldset><legend>Global roles</legend><label>Search roles<input type="search" value={roleSearch} onChange={(e) => setRoleSearch(e.target.value)} /></label>
          {Object.keys(roles).filter((item) => item === role || item.toLowerCase().includes(roleSearch.toLowerCase())).map((item) =>
            <label className="iam-check" key={item}><input className="admin-checkbox" type="radio" name="primary" checked={role === item} onChange={() => setRole(item)} /> {titleCase(item)}</label>)}
          {custom.filter((item) => extraRoles.includes(item.id) || item.name.toLowerCase().includes(roleSearch.toLowerCase())).map((item) =>
            <label className="iam-check" key={item.id}><input className="admin-checkbox" type="checkbox" checked={extraRoles.includes(item.id)}
              onChange={(e) => setExtraRoles(e.target.checked ? [...extraRoles, item.id] : extraRoles.filter((id) => id !== item.id))} /> {item.name} <small>{item.description}</small></label>)}
        </fieldset>
        <fieldset><legend>Project membership</legend>{projects.map((item) =>
          <label className="iam-check" key={item.id}><input className="admin-checkbox" type="checkbox" checked={projectIds.includes(item.id)}
            onChange={(e) => setProjectIds(e.target.checked ? [...projectIds, item.id] : projectIds.filter((id) => id !== item.id))} /> {item.name}</label>)}
          {!projects.length && <p className="muted">No projects available.</p>}
          <p className="muted">Configure project-specific roles after creation in Project Access.</p></fieldset>
      </div>}
      {step === 3 && <dl className="status-list">
        <div><dt>Identity</dt><dd>{identity.first_name} {identity.middle_name} {identity.last_name} · {identity.email} · {identity.username}</dd></div>
        <div><dt>Onboarding</dt><dd>{mode === "temporary" ? "Temporary password" : "Activation link"}</dd></div>
        <div><dt>Roles</dt><dd>{[titleCase(role), ...custom.filter((item) => extraRoles.includes(item.id)).map((item) => item.name)].join(", ")}</dd></div>
        <div><dt>Projects</dt><dd>{projects.filter((item) => projectIds.includes(item.id)).map((item) => item.name).join(", ") || "No project access assigned"}</dd></div>
        <div><dt>Access after onboarding</dt><dd>{permissions.map(titleCase).join(", ")}</dd></div>
      </dl>}
      {error && <p role="alert">{error}</p>}
      <footer className="iam-footer">{step > 0 && <button type="button" className="secondary" disabled={busy} onClick={() => setStep(step - 1)}>Back</button>}
        <button disabled={busy}>{step === 3 ? busy ? "Creating…" : "Create user" : "Continue"}</button></footer>
    </form>
  </Dialog>;
}
