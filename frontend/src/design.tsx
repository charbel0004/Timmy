import type { ReactNode } from "react";
import { ArrowRightFromLine, CalendarClock, Calculator, Check, ChevronUp, CircleAlert, ClipboardList, Folder, LayoutGrid, MessageCircle, Settings2, ShieldCheck, Sparkles, Upload, Wallet } from "lucide-react";

const symbols = {
  projects: Folder, activities: ClipboardList, access: ShieldCheck, users: ShieldCheck, roles: ShieldCheck, security: ShieldCheck,
  assistant: MessageCircle, dashboard: LayoutGrid, imports: ChevronUp, timesheets: ClipboardList,
  discrepancies: CircleAlert, batches: Wallet, settings: Settings2, ai: Sparkles,
  validation: Check, calculation: Calculator, approval: ShieldCheck, export: Upload,
  project: Folder, clock: CalendarClock, logout: ArrowRightFromLine,
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

export function Brand() {
  return <div className="brand"><span className="brand-mark"><Icon name="ai" /></span>
    <div><strong>Agent Timmy</strong><small>Staff Operations</small></div>
  </div>;
}
