import { useEffect, useState } from "react";
import { errorMessage, request } from "./api";
import type { Session } from "./api";
import { Dialog, Directory, titleCase } from "./iam-users";
import type { User } from "./iam-users";

type CustomRole = { id: number; name: string; description: string; permissions: string[]; assigned_users: number };
type RoleCatalog = { catalog: string[]; delegable: string[]; custom: CustomRole[] };
type Project = { id: number; name: string };
type Audit = { id: number; actor_id: number | null; action: string; timestamp: number; target: string | null; resource: string | null; outcome: string | null };

const tabs = ["Users", "Roles & Permissions", "Project Access", "Audit Log"] as const;
const root = "/workspace/iam";

export function AccessManagement({ session }: { session: Session }) {
  const [tab, setTab] = useState<typeof tabs[number]>("Users");
  const [catalog, setCatalog] = useState<RoleCatalog>();
  const [members, setMembers] = useState<User[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [projectId, setProjectId] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);

  const [system, setSystem] = useState<Record<string, string[]>>({});
  const [adding, setAdding] = useState(false);
  const [selectedRole, setSelectedRole] = useState("system:admin");
  const [roleSearch, setRoleSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [notice, setNotice] = useState("");
  const [auditFrom, setAuditFrom] = useState("");
  const [auditTo, setAuditTo] = useState("");
  const [auditAction, setAuditAction] = useState("");
  const [auditResult, setAuditResult] = useState("");
  const reload = () => setRevision((value) => value + 1);

  useEffect(() => {
    let current = true;
    setBusy(true);
    setError("");
    Promise.all([
      request<RoleCatalog>(root + "/roles"), request<User[]>("/workspace/users"),
      request<Project[]>("/workspace/projects"), request<Record<string, string[]>>("/workspace/roles"),
    ]).then(([roles, users, scoped, reserved]) => {
      if (current) { setCatalog(roles); setMembers(users); setProjects(scoped); setSystem(reserved); setLoaded(true); }
    }).catch((error) => { if (current) setError(errorMessage(error)); })
      .finally(() => { if (current) setBusy(false); });
    return () => { current = false; };
  }, [revision]);

  useEffect(() => {
    if (tab !== "Audit Log") return;
    let current = true;
    request<Audit[]>(root + "/audit").then((events) => { if (current) setAudit(events); })
      .catch((error) => { if (current) setError(errorMessage(error)); });
    return () => { current = false; };
  }, [tab, revision]);

  async function save(path: string, method: string, body: object, scope = root) {
    setError(""); setBusy(true);
    try {
      await request(scope + path, { method, headers: {
        "X-CSRF-Token": session.csrf_token, "Content-Type": "application/json",
      }, body: JSON.stringify(body) });
      setCreating(false);
      setNotice("Changes saved.");
      reload();
    } catch (error) { setError(errorMessage(error)); setBusy(false); }
  }

  const roleList = [
    ...Object.entries(system).map(([name, permissions]) => ({
      key: `system:${name}`, name, permissions, description: "Built-in workspace role",
      assigned_users: members.filter((user) => user.role === name).length, custom: undefined,
    })),
    ...(catalog?.custom ?? []).map((role) => ({ ...role, key: `custom:${role.id}`, custom: role })),
  ];
  const activeRole = roleList.find((role) => role.key === selectedRole) ?? roleList[0];
  const statistics = [["Total users", members.length], ["Active users", members.filter((item) => item.active).length],
    ["Roles", roleList.length], ["Pending activations", members.filter((item) => item.activation_pending).length]];

  return <section className="admin-grid" aria-label="Access Management">
    <header className="iam-heading"><div><h1>Access Management</h1><p className="muted">Manage users, roles, permissions and project access</p></div>
      <button disabled={!loaded} onClick={() => { setTab("Users"); setAdding(true); }}>Add user</button></header>
    <dl className="iam-stats">{statistics.map(([label, total]) => <div className="glass-panel" key={label}><dt>{label}</dt><dd>{loaded ? total : "—"}</dd></div>)}</dl>
    <nav className="glass-panel iam-tabs" aria-label="Access Management sections">
      {tabs.map((item) => <button className="secondary" aria-pressed={item === tab} key={item}
        onClick={() => { setError(""); setNotice(""); setTab(item); }}>{item}</button>)}
    </nav>
    {error && <div role="alert">{error} <button className="secondary" onClick={reload}>Retry</button></div>}
    {notice && <p role="status">{notice}</p>}
    {busy && <p role="status">Loading access records…</p>}
    {tab === "Users" && loaded && <Directory users={members} projects={projects} roles={system} custom={catalog?.custom ?? []}
      csrf={session.csrf_token} username={session.username} adding={adding} setAdding={setAdding} reload={reload} />}
    {tab === "Roles & Permissions" && catalog && <div className="iam-role-layout">
      <aside className="glass-panel admin-form"><div className="iam-heading"><h2>Role directory</h2>
        <button className="secondary" onClick={() => { setError(""); setCreating(true); }}>Create role</button></div>
        <label>Search roles<input type="search" value={roleSearch} onChange={(e) => setRoleSearch(e.target.value)} /></label>
        <ul>{roleList.filter((role) => role.name.toLowerCase().includes(roleSearch.toLowerCase())).map((role) =>
          <li key={role.key}><button className="secondary iam-role-link" aria-pressed={activeRole?.key === role.key} onClick={() => setSelectedRole(role.key)}>
            <strong>{titleCase(role.name)}</strong><small>{role.custom ? "Custom" : "System"} · {role.assigned_users} assigned</small>
            <small>{role.description}</small></button></li>)}</ul>
      </aside>
      {activeRole && <div className="glass-panel admin-form">
        <div className="iam-heading"><div><h2>{titleCase(activeRole.name)}</h2>
          <p className="muted">{activeRole.custom ? "Assignable globally or by project" : "Protected system role"} · {activeRole.assigned_users} assigned</p></div></div>
        {activeRole.custom ? <RoleEditor key={`${activeRole.key}-${revision}`} role={activeRole.custom} keys={catalog.delegable}
          busy={busy} onSave={(body) => void save(`/roles/${activeRole.custom?.id}`, "PATCH", body)} /> :
          <PermissionMatrix keys={catalog.catalog} checked={activeRole.permissions} />}
      </div>}
      {creating && <Dialog title="Create role" close={() => { if (!busy) setCreating(false); }}>
        {error && <p role="alert">{error}</p>}
        <RoleEditor keys={catalog.delegable} busy={busy} onSave={(body) => void save("/roles", "POST", body)} />
      </Dialog>}
    </div>}
    {tab === "Project Access" && <div className="glass-panel admin-form">
      <label>Project<select value={projectId} onChange={(event) => setProjectId(event.target.value)}>
        <option value="">Choose a project</option>{projects.map((project) =>
          <option key={project.id} value={project.id}>{project.name}</option>)}
      </select></label>
      {projectId && <form className="iam-filters" onSubmit={(event) => {
        event.preventDefault();
        const id = Number(new FormData(event.currentTarget).get("member"));
        const member = members.find((item) => item.id === id);
        if (member) void save(`/users/${id}`, "PATCH", {
          role: member.role, active: member.active, project_ids: [...member.project_ids, Number(projectId)],
        }, "/workspace");
      }}>
        <label>Add member<select name="member" required defaultValue=""><option value="">Choose a user</option>
          {members.filter((item) => item.username !== session.username && !item.project_ids.includes(Number(projectId))).map((item) =>
            <option key={item.id} value={item.id}>{item.username}</option>)}</select></label>
        <div><button disabled={busy}>Add member</button></div>
      </form>}
      {projectId && members.filter((item) => item.project_ids.includes(Number(projectId))).map((item) =>
        <form className="admin-grid" key={`${projectId}-${item.id}`} onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          if (window.confirm(`Replace scoped roles for ${item.username}?`)) void save("/assignments", "PUT", {
            user_id: item.id, project_id: Number(projectId), role_ids: data.getAll("role").map(Number),
          });
        }}>
          <strong>{item.username}</strong>
          {item.username !== session.username && <fieldset><legend>Replace scoped roles</legend>
            {catalog?.custom.map((role) => <label className="iam-check" key={role.id}>
              <input className="admin-checkbox" type="checkbox" name="role" value={role.id} defaultChecked={item.scoped_roles[projectId]?.includes(role.id)} /> {role.name}
            </label>)}
            <button disabled={busy || !catalog?.custom.length}>Apply roles</button>
          </fieldset>}
        </form>)}
      {projectId && catalog && members.filter((item) => item.username !== session.username && item.project_ids.includes(Number(projectId))).map((item) =>
        <details key={`permissions-${projectId}-${item.id}-${revision}`}>
          <summary>Edit permissions for {item.username}</summary>
          <MemberPermissionEditor keys={catalog.delegable} initial={item.project_permissions?.[projectId] ?? []}
            overridden={Object.hasOwn(item.project_overrides ?? {}, projectId)} busy={busy}
            save={(permissions) => void save(`/projects/${projectId}/members/${item.id}/permissions`, "PUT", { permissions })} />
        </details>)}
      <p className="muted">Manage project membership in User Directory.</p>
    </div>}
    {tab === "Audit Log" && <div className="glass-panel admin-form">
      <div className="iam-filters">
        <label>Actor or target<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        <label>From<input type="date" value={auditFrom} onChange={(e) => setAuditFrom(e.target.value)} /></label>
        <label>Through<input type="date" value={auditTo} onChange={(e) => setAuditTo(e.target.value)} /></label>
        <label>Action<select value={auditAction} onChange={(e) => setAuditAction(e.target.value)}><option value="">All actions</option>
          {[...new Set(audit.map((item) => item.action))].map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}</select></label>
        <label>Result<select value={auditResult} onChange={(e) => setAuditResult(e.target.value)}><option value="">All results</option>
          {[...new Set(audit.map((item) => item.outcome).filter(Boolean))].map((item) => <option key={item} value={item ?? ""}>{item}</option>)}</select></label>
      </div>
      <div className="chat-table" tabIndex={0} role="region" aria-label="Audit events"><table>
        <thead><tr>{["When", "Actor", "Action", "Target", "Outcome"].map((label) => <th scope="col" key={label}>{label}</th>)}</tr></thead>
        <tbody>{audit.filter((event) => [event.target, event.actor_id].join(" ").includes(search.trim())
          && (!auditAction || event.action === auditAction) && (!auditResult || event.outcome === auditResult)
          && (!auditFrom || event.timestamp * 1000 >= new Date(auditFrom + "T00:00").getTime())
          && (!auditTo || event.timestamp * 1000 <= new Date(auditTo + "T23:59:59").getTime())).map((event) => <tr key={event.id}>
          <td>{new Date(event.timestamp * 1000).toLocaleString()}</td><td>{event.actor_id ?? "—"}</td>
          <td>{titleCase(event.action)}</td><td>{[event.resource, event.target].filter(Boolean).join(" ") || "—"}</td><td>{event.outcome ?? "—"}</td>
        </tr>)}</tbody>
      </table></div>
    </div>}

  </section>;
}

const labels: Record<string, string> = {
  "projects:read": "View projects", "projects:manage": "Manage projects", "projects.delete": "Delete projects",
  "activities.view": "View activities", "timesheets.view": "View timesheets", "discrepancies.view": "View discrepancies",
  "payments.view": "View payments", "users:manage": "Manage users", "roles:read": "View roles",
  "iam.roles.manage": "Manage roles", "iam.audit.view": "View access audit", "settings:read": "View settings",
};

function PermissionMatrix({ keys, checked, change }: { keys: string[]; checked: string[]; change?: (next: string[]) => void }) {
  const groups: Record<string, string[]> = {};
  for (const key of keys) {
    const module = key.startsWith("iam.roles") || key.startsWith("roles:") ? "Roles & Permissions"
      : key.startsWith("iam.audit") ? "Access Audit" : key.startsWith("users:") ? "User Administration"
      : titleCase(key.split(/[.:]/)[0]);
    (groups[module] ??= []).push(key);
  }
  return <div className="iam-matrix">{Object.entries(groups).map(([module, permissions]) =>
    <fieldset key={module}><legend>{module}</legend>
      {change && <div className="iam-module-actions">
        <button type="button" className="secondary" onClick={() => change([...new Set([...checked, ...permissions])])}>Select all</button>
        <button type="button" className="secondary" onClick={() => change(checked.filter((key) => !permissions.includes(key)))}>Clear</button>
      </div>}
      {permissions.map((key) => <label className="iam-check" title={key} key={key}>
        <input type="checkbox" className="admin-checkbox" checked={checked.includes(key)} disabled={!change}
          onChange={(e) => change?.(e.target.checked ? [...checked, key] : checked.filter((item) => item !== key))} /> {labels[key] ?? titleCase(key)}
      </label>)}
    </fieldset>)}</div>;
}

function RoleEditor({ role, keys, busy, onSave }: { role?: CustomRole; keys: string[]; busy: boolean; onSave: (value: object) => void }) {
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [permissions, setPermissions] = useState(role?.permissions ?? []);
  const changed = name !== (role?.name ?? "") || description !== (role?.description ?? "")
    || permissions.length !== (role?.permissions.length ?? 0) || permissions.some((key) => !role?.permissions.includes(key));
  return <form className="admin-grid" onSubmit={(event) => {
    event.preventDefault();
    if (role?.assigned_users && !window.confirm(`These changes affect ${role.assigned_users} assigned users. Save changes?`)) return;
    onSave({ name, description, permissions });
  }}>
    <div className="iam-fields"><label>Role name<input required maxLength={40} value={name} onChange={(e) => setName(e.target.value)} /></label>
      <label>Description<input maxLength={240} value={description} onChange={(e) => setDescription(e.target.value)} /></label></div>
    <PermissionMatrix keys={keys} checked={permissions} change={setPermissions} />
    <footer className="iam-footer">{changed && <span className="muted">Unsaved changes</span>}
      {role && <button type="button" className="secondary" disabled={!changed || busy} onClick={() => {
        setName(role.name); setDescription(role.description ?? ""); setPermissions(role.permissions);
      }}>Cancel changes</button>}
      <button disabled={!changed || !name.trim() || busy}>{role ? "Save changes" : "Create role"}</button>
    </footer>
  </form>;
}


function MemberPermissionEditor({ keys, initial, overridden, busy, save }: {
  keys: string[]; initial: string[]; overridden: boolean; busy: boolean; save: (permissions: string[] | null) => void;
}) {
  const [checked, setChecked] = useState(initial);
  return <div className="admin-grid">
    <p className="muted">{overridden ? "Custom permissions for this project" : "Inherited permissions"}.
      Saving replaces this member’s project permissions. Shared roles are unaffected.</p>
    <PermissionMatrix keys={keys} checked={checked} change={setChecked} />
    <div className="admin-actions">
      <button disabled={busy} onClick={() => save(checked)}>Save project permissions</button>
      {overridden && <button className="secondary" disabled={busy} onClick={() => save(null)}>Restore inherited permissions</button>}
    </div>
  </div>;
}
