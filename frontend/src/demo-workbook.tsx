import { useEffect, useState } from "react";
import { errorMessage, request } from "./api";

type Case = { timesheet: string; activity: string; outcome: string; reasons: string[] };
type Obligation = { timesheet: string; currency: string; amount: string };
type Reconciliation = { status: string; balance: string };
type Demo = {
  projects: { project_id: number; name: string; status: string; results: Case[];
    obligations: Record<string, Obligation>; reconciliation: Record<string, Reconciliation> }[];
  totals: Record<string, { calculated: string; net: string; outstanding: string; overpaid: string }>;
};

export function DemoWorkbook({ show }: { show: "dashboard" | "projects" | "imports" | "batches" }) {
  const [demo, setDemo] = useState<Demo>();
  const [error, setError] = useState("");
  useEffect(() => { request<Demo>("/demo-workbook").then(setDemo, (failure) => setError(errorMessage(failure))); }, []);
  if (error) return <p role="alert">{error}</p>;
  if (!demo?.projects.length) return null;
  return <section className="glass-panel admin-form">
    <h2>DEMO workbook · Simulated evidence</h2>
    {show === "dashboard" && Object.entries(demo.totals).map(([currency, totals]) =>
      <p key={currency}>{currency} {totals.calculated} calculated · {totals.net} simulated net · {totals.outstanding} reconciled outstanding · {totals.overpaid} overpaid</p>)}
    {demo.projects.map((project) => <article key={project.project_id}>
      <h3>{project.name}</h3>
      <p>{project.status === "pending_human_approval" ? "Awaiting human authorization" : "Simulated reconciliation recorded"}
        {" · "}{project.results.length} timesheets · {Object.keys(project.obligations).length} calculated obligations</p>
      {show === "imports" && <ul>{project.results.map((row) => <li key={row.timesheet}>
        {row.timesheet} · {row.activity} · {row.outcome}{row.reasons.length ? ` · ${row.reasons.join(", ")}` : ""}
      </li>)}</ul>}
      {show === "batches" && <ul>{Object.entries(project.obligations).map(([ref, item]) =>
        <li key={ref}>{ref} · {item.timesheet} · {item.currency} {item.amount} · {project.reconciliation[ref]?.status ?? "Pending approval"}</li>)}</ul>}
    </article>)}
  </section>;
}
