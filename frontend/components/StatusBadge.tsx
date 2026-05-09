"use client";
import { BreathingDot } from "./BreathingDot";
import type { ShipmentStatus } from "@/lib/api";

const LABEL: Record<ShipmentStatus, string> = {
  IN_TRANSIT: "In Transit",
  COMPROMISED: "Compromised",
  DELIVERED: "Delivered",
};

export function StatusBadge({ status }: { status: ShipmentStatus }) {
  const tone =
    status === "COMPROMISED"
      ? "text-warn border-warn/40 bg-warn/5"
      : status === "DELIVERED"
      ? "text-slate-200 border-slate-800 bg-slate-900/40"
      : "text-cyan border-cyan/30 bg-cyan/5";

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[10px] uppercase tracking-[0.22em] ${tone}`}
    >
      <BreathingDot status={status} />
      {LABEL[status]}
    </span>
  );
}
