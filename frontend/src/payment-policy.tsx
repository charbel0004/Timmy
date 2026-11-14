import { useEffect, useState } from "react";
import { errorMessage, request } from "./api";

export function readPolicy(fields: FormData) {
  const value = (name: string) => String(fields.get(`policy_${name}`) ?? "");
  const number = (name: string) => value(name) ? Number(value(name)) : null;
  return {
    family: value("family"), rate: value("rate"), currency: value("currency"),
    start: value("start"), end: value("end") || null, precision: number("precision"),
    monetary_rounding: value("money"), eligibility: "approved_evidence_only",
    duration_rounding: value("duration") || null, increment_minutes: number("increment"),
    overnight: value("overnight") || null, daily_cap: number("daily"),
    activity_cap: number("activity"), period_cap: number("cap"), period: value("period") || null,
  };
}

export function PolicyFields() {
  const [hours, setHours] = useState(true);
  const [rounding, setRounding] = useState("exact");
  return <fieldset className="admin-grid">
    <legend>Payment configuration</legend>
    <label>Payment type<select name="policy_family" onChange={(e) => { setHours(e.target.value === "hours"); setRounding("exact"); }}>
      <option value="hours">Hourly</option><option value="session">Per approved session</option>
    </select></label>
    <label>{hours ? "Hourly rate" : "Rate per approved session"}<input name="policy_rate" required type="number" min="0.000001" step="0.000001" /></label>
    <label>Currency<select name="policy_currency"><option>USD</option><option>LBP</option></select></label>
    <label>Effective date<input type="date" name="policy_start" required /></label>
    <label>Expiration date<input type="date" name="policy_end" /></label>
    <label>Currency precision<input name="policy_precision" required type="number" min="0" max="6" /></label>
    <label>Monetary rounding<select name="policy_money" required defaultValue="">
      <option value="">Select rounding</option><option value="half_up">Half up</option>
      <option value="half_even">Half even</option><option value="down">Down</option><option value="up">Up</option>
    </select></label>
    {hours && <>
      <label>Duration rounding<select name="policy_duration" value={rounding} onChange={(e) => setRounding(e.target.value)}>
        <option value="exact">Exact minutes</option><option value="half_up">Nearest increment, half up</option>
        <option value="down">Down</option><option value="up">Up</option>
      </select></label>
      {rounding !== "exact" && <label>Rounding increment (minutes)<input name="policy_increment" required type="number" min="1" max="60" /></label>}
      <label>Overnight handling<select name="policy_overnight" required defaultValue="">
        <option value="">Confirm a rule</option><option value="continuous">Continuous elapsed time (suggested)</option>
        <option value="reject">Reject overnight claims</option>
      </select></label>
      <label>Maximum minutes per activity<input name="policy_activity" type="number" min="1" /></label>
    </>}
    <label>Daily cap ({hours ? "minutes" : "sessions"})<input name="policy_daily" type="number" min="1" max="1440" required={hours} /></label>
    <label>Period cap ({hours ? "minutes" : "sessions"})<input name="policy_cap" type="number" min="1" /></label>
    <label>Cap period<select name="policy_period"><option value="">No period cap</option><option value="calendar_month">Calendar month</option></select></label>
    <p>Eligibility requires approved evidence. The per-session option is separate from the legacy three-credit pooling rule.</p>
  </fieldset>;
}

type Policy = { id: number; version: number; status: string; configuration: ReturnType<typeof readPolicy> | null };

export function ProjectPaymentPolicies({ projectId, canManage, csrf }: { projectId: number; canManage: boolean; csrf: string }) {
  const path = `/payment-policies/${projectId}`;
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { request<Policy[]>(path).then(setPolicies, (failure) => setError(errorMessage(failure))); }, [path]);
  async function send(suffix: string, body: object, example = false) {
    setBusy(true);
    setError("");
    try {
      const result = await request<{ amount?: string; currency?: string; raw_quantity?: number; unit?: string }>(path + suffix, {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify(body),
      });
      if (example) setPreview(`Example for ${result.raw_quantity} ${result.unit}: ${result.currency} ${result.amount}`);
      else setPolicies(await request<Policy[]>(path));
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  return <details><summary>Payment policies</summary>
    {error && <p role="alert">{error}</p>}
    {policies.map(({ id, version, status, configuration: c }) => <article key={id}>
      <p>Version {version} · {status}{c && ` · ${c.currency} ${c.rate} per ${c.family === "hours" ? "hour" : "session"} · ${c.start}${c.end ? ` to ${c.end}` : ""}`}</p>
      {canManage && ["draft", "superseded"].includes(status) && <button type="button" disabled={busy}
        className="secondary" onClick={() => {
          if (window.confirm(`Archive policy version ${version}?`)) void send(`/${id}/archive`, { confirmed: true });
        }}>Archive version</button>}
      {canManage && status === "draft" && c && <form onSubmit={(event) => {
        event.preventDefault();
        const supersede = new FormData(event.currentTarget).get("supersede");
        void send(`/${id}/activate`, { confirmed: true, supersede_policy_id: supersede ? Number(supersede) : null });
      }}>
        <label>Replace active version<select name="supersede"><option value="">None</option>
          {policies.filter((policy) => policy.status === "active").map((policy) =>
            <option key={policy.id} value={policy.id}>Version {policy.version}</option>)}</select></label>
        <label><input type="checkbox" required /> I confirm the rules for version {version}</label>
        <button disabled={busy}>Activate policy</button>
      </form>}
    </article>)}
    {canManage && <form onSubmit={(event) => {
      event.preventDefault();
      const button = (event.nativeEvent as SubmitEvent).submitter;
      const example = button?.getAttribute("value") === "example";
      void send(example ? "/example" : "", readPolicy(new FormData(event.currentTarget)), example);
    }}>
      <PolicyFields />
      <button disabled={busy} value="example" className="secondary">Preview example</button>{" "}
      <button disabled={busy}>Save new draft version</button>
      {preview && <p role="status">{preview}</p>}
    </form>}
  </details>;
}
