"use client";

// SensorChart v3 — minimalist forensic chart.
//   - No chrome. No grid. Just a glowing line + dashed forecast.
//   - The big live readout sits in the chart's top-right (replaces the
//     separate stat strip — "merge stats and charts" requirement).
//   - Tiny axis affordances: a single Y-axis label on the left edge and
//     a "TIMELINE" tag on the bottom-left, in 9px tracking.

import { useId, useMemo } from "react";
import {
  Area,
  AreaChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { motion } from "framer-motion";

export type AccentName = "cyan" | "warn" | "violet" | "emerald";

const ACCENTS: Record<AccentName, string> = {
  cyan: "#22D3EE",
  warn: "#FB923C",
  violet: "#A78BFA",
  emerald: "#34D399",
};

interface Sample { t: number; v: number; }

interface Props {
  data: Sample[];
  forecast?: Sample[];
  unit: string;
  altUnit?: { label: string; convert: (v: number) => number };
  label: string;
  axisLabel?: string;          // e.g. "Temp" — printed as the Y-axis hint
  threshold?: number;
  accent?: AccentName;
  height?: number;
  precision?: number;
  panic?: boolean;
  /** Optional override for the big readout (e.g., scrubbed value). */
  liveValue?: number;
  /** Temporal mode — affects readout colour + footer label. */
  mode?: "past" | "live" | "future";
}

export function SensorChart({
  data,
  forecast = [],
  unit,
  altUnit,
  label,
  axisLabel,
  threshold,
  accent = "cyan",
  height = 220,
  precision = 2,
  panic = false,
  liveValue,
  mode = "live",
}: Props) {
  const gid = useId().replace(/:/g, "");
  const stroke = panic ? "#FB923C" : ACCENTS[accent];

  const merged = useMemo(() => {
    type Row = { t: number; v?: number; vf?: number };
    const rows: Row[] = data.map((d) => ({ t: d.t, v: d.v }));
    if (forecast.length && data.length) {
      const last = data[data.length - 1];
      rows.push({ t: last.t, vf: last.v });
      for (const f of forecast) rows.push({ t: f.t, vf: f.v });
    }
    return rows;
  }, [data, forecast]);

  const last = data.at(-1);
  const display = liveValue ?? last?.v ?? 0;
  const breached = threshold != null && display > threshold;
  const altText = altUnit ? `${altUnit.convert(display).toFixed(2)} ${altUnit.label}` : null;
  const forecastStartT = data.length ? data[data.length - 1].t : null;
  const startTs = data[0]?.t;
  const endTs = data[data.length - 1]?.t;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="relative rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5"
    >
      {/* Header row: tiny label, big glowing readout. */}
      <div className="flex items-baseline justify-between gap-4">
        <div className="flex items-center gap-2">
          <div className="text-[10px] uppercase tracking-[0.28em] text-white/80">
            {label}
          </div>
          {mode !== "live" && (
            <span
              className="rounded-full border px-1.5 py-px font-mono text-[8px] uppercase tracking-[0.28em]"
              style={{
                color: mode === "future" ? "#A78BFA" : "#94A3B8",
                borderColor: mode === "future" ? "#A78BFA66" : "#94A3B866",
                background:
                  mode === "future" ? "rgba(167,139,250,0.08)" : "rgba(148,163,184,0.06)",
              }}
            >
              {mode === "future" ? "forecast" : "replay"}
            </span>
          )}
        </div>
        <div className="text-right">
          <div className="flex items-baseline justify-end gap-1.5">
            <span
              className={`font-mono text-3xl tracking-tight ${
                breached || panic ? "text-warn" : "text-white"
              }`}
              style={{
                textShadow: breached || panic
                  ? "0 0 22px rgba(251,146,60,0.55)"
                  : `0 0 22px ${stroke}55`,
              }}
            >
              {display.toFixed(precision)}
            </span>
            <span className="text-xs text-white/30">{unit}</span>
          </div>
          {altText && (
            <div className="mt-0.5 font-mono text-[10px] text-white/30">
              {altText}
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 w-full" style={{ height }}>
        {data.length < 2 ? (
          <div className="grid h-full place-items-center text-[10px] uppercase tracking-widest text-white/20">
            awaiting telemetry
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={merged} margin={{ top: 6, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={`grad-${gid}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.55} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                </linearGradient>
                <linearGradient id={`fgrad-${gid}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.18} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                </linearGradient>
                <filter id={`glow-${gid}`} x="-20%" y="-50%" width="140%" height="200%">
                  <feGaussianBlur stdDeviation="3" result="b" />
                  <feMerge>
                    <feMergeNode in="b" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>
              <Tooltip
                cursor={{ stroke: "rgba(255,255,255,0.08)", strokeWidth: 1 }}
                contentStyle={{
                  background: "rgba(0,0,0,0.94)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 10,
                  fontSize: 11,
                  padding: "6px 10px",
                  color: "#E6E9EF",
                }}
                labelStyle={{ color: "rgba(255,255,255,0.4)", marginBottom: 2 }}
                labelFormatter={(ts) => new Date(ts as number).toLocaleTimeString()}
                formatter={(v: unknown, name) => {
                  if (v == null) return ["—", name as string];
                  const n = Number(v);
                  return [
                    `${n.toFixed(precision)} ${unit}` +
                      (altUnit ? ` · ${altUnit.convert(n).toFixed(2)} ${altUnit.label}` : ""),
                    name === "vf" ? "Forecast" : label,
                  ];
                }}
              />
              {threshold != null && (
                <ReferenceLine
                  y={threshold}
                  stroke="#FB923C"
                  strokeOpacity={0.45}
                  strokeDasharray="3 4"
                />
              )}
              {forecastStartT && forecast.length > 0 && (
                <ReferenceLine
                  x={forecastStartT}
                  stroke="rgba(255,255,255,0.28)"
                  strokeDasharray="2 4"
                  label={{
                    value: "now",
                    position: "top",
                    fill: "rgba(255,255,255,0.55)",
                    fontSize: 9,
                    letterSpacing: 2,
                  }}
                />
              )}
              <Area
                type="monotone"
                dataKey="v"
                stroke={stroke}
                strokeWidth={1.6}
                fill={`url(#grad-${gid})`}
                connectNulls={false}
                isAnimationActive
                animationDuration={500}
                filter={`url(#glow-${gid})`}
                activeDot={{ r: 3.5, fill: stroke, stroke: "#000", strokeWidth: 2 }}
              />
              <Area
                type="monotone"
                dataKey="vf"
                stroke={stroke}
                strokeWidth={1.2}
                strokeDasharray="3 4"
                fill={`url(#fgrad-${gid})`}
                connectNulls={false}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Footer: minimal timeline axis. */}
      <div className="mt-2 flex items-center justify-between font-mono text-[9px] uppercase tracking-[0.28em] text-white/65">
        <span>timeline</span>
        <span>
          {startTs ? new Date(startTs).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"}
          <span className="mx-2 text-white/40">→</span>
          {forecast.length
            ? "+24m forecast"
            : endTs
            ? new Date(endTs).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
            : "—"}
        </span>
      </div>
    </motion.div>
  );
}
