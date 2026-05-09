"use client";
import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Gavel,
  Radio,
  ShieldAlert,
} from "lucide-react";
import type { TimelineEvent } from "@/lib/api";

const ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  TELEMETRY_OK: Radio,
  VIOLATION: AlertTriangle,
  STATUS_CHANGE: Activity,
  REFUND_PREPARED: ShieldAlert,
  JUDGE_VERDICT: Gavel,
  DELIVERED: CheckCircle2,
};

function tone(kind: string) {
  if (kind === "VIOLATION" || kind === "REFUND_PREPARED") return "text-warn";
  if (kind === "JUDGE_VERDICT") return "text-cyan";
  if (kind === "STATUS_CHANGE") return "text-slate-200";
  return "text-slate-400";
}

export function StatusTimeline({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) {
    return (
      <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-6 text-xs text-slate-500">
        Awaiting first event…
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-5 backdrop-blur-sm">
      <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Timeline</div>
      <ol className="relative mt-5 space-y-5 pl-5">
        <span className="absolute left-[7px] top-1 bottom-1 w-px bg-slate-800" />
        {events.map((e, i) => {
          const Icon = ICON[e.kind] ?? Activity;
          return (
            <motion.li
              key={e.id}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.03 }}
              className="relative"
            >
              <span className="absolute -left-5 top-1 grid h-3.5 w-3.5 place-items-center rounded-full bg-slate-950 ring-1 ring-slate-700">
                <Icon className={`h-2.5 w-2.5 ${tone(e.kind)}`} />
              </span>
              <div className="flex items-baseline justify-between gap-4">
                <div className="text-sm text-slate-200">{e.message}</div>
                <time className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-slate-500">
                  {new Date(e.createdAt).toLocaleTimeString()}
                </time>
              </div>
              <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-slate-600">
                {e.kind.replace(/_/g, " ")}
                {e.violation ? ` · ${e.violation.replace(/_/g, " ")}` : ""}
              </div>
            </motion.li>
          );
        })}
      </ol>
    </div>
  );
}
