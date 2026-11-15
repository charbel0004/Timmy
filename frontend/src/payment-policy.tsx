import { useEffect, useState } from "react";
import { errorMessage, request } from "./api";

type Selection = {
  family: "session" | "hours" | null;
  configuration_editable: false;
  status: "fixed_session_contract" | "pending_hourly_contract" | "unassigned_legacy";
};

export function ProjectPaymentPolicies({ projectId }: {
  projectId: number;
  canManage: boolean;
  csrf: string;
}) {
  const [policy, setPolicy] = useState<Selection | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    request<Selection>(`/payment-policies/${projectId}`).then(
      (value) => { if (active) setPolicy(value); },
      (failure) => { if (active) setError(errorMessage(failure)); },
    );
    return () => { active = false; };
  }, [projectId]);

  return <div className="muted" aria-live="polite">
    {error && <p role="alert">{error}</p>}
    {policy && <p>
      Payment policy: {policy.family === "session"
        ? "Session-based (fixed approved rules)"
        : policy.family === "hours"
          ? "Hours-based (final rules pending approval)"
          : "Unassigned legacy project — needs administrator review"}.
      There are no per-project policy settings.
    </p>}
  </div>;
}
