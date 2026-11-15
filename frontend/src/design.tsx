import { useState } from "react";
import type { ReactNode } from "react";
import { Activity, BarChart3, RefreshCw, ArrowRightFromLine, CalendarClock, Calculator, Check, ChevronUp, CircleAlert, ClipboardList, Folder, LayoutGrid, MessageCircle, Settings2, ShieldCheck, Sparkles, Upload, Wallet } from "lucide-react";

const symbols = {
  evidence: ShieldCheck, observatory: Activity, reports: BarChart3, reconciliation: RefreshCw,
  projects: Folder, activities: ClipboardList, access: ShieldCheck, users: ShieldCheck, roles: ShieldCheck, security: ShieldCheck,
  assistant: MessageCircle, dashboard: LayoutGrid, imports: ChevronUp, timesheets: ClipboardList,
  discrepancies: CircleAlert, batches: Wallet, settings: Settings2, ai: Sparkles,
  validation: Check, calculation: Calculator, approval: ShieldCheck, export: Upload,
  project: Folder, clock: CalendarClock, logout: Activity, BarChart3, RefreshCw, ArrowRightFromLine,
};
export type IconName = keyof typeof symbols;

export function Icon({ name }: { name: IconName }) {
  const Glyph = symbols[name];
  return <Glyph aria-hidden="true" className="icon" size={17} />;
}

export function Badge({ children, tone = "neutral" }: {
  children: ReactNode; tone?: "neutral" | "amber" | "green" | "cyan";
}) {
  return <span className={`badge badge--${tone}`}>{children}</span>;
}

export function AgentAvatar({ className = "", size = 36 }: { className?: string; size?: number }) {
  const [unavailable, setUnavailable] = useState(false);
  return unavailable ? <Sparkles className={className} size={size} aria-hidden="true" />
    : <img src="/assets/timmy-avatar.webp" className={`agent-avatar ${className}`} width={size} height={size}
        alt="" onError={() => setUnavailable(true)} />;
}

export function Brand() {
  return <div className="brand"><span className="brand-mark"><AgentAvatar size={36} /></span>
    <div><strong>Agent Timmy</strong><small>Operations command center</small></div>
  </div>;
}
