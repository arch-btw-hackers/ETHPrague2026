"use client";

// AIInsights v2 — radically minimal.
// Panic override: when the parent passes panic=true (status === COMPROMISED),
// the panel clears all chrome and shows ONLY the critical violation banner.

import useSWR from "swr";
import { motion, AnimatePresence } from "framer-motion";
import { RefreshCw } from "lucide-react";
import { fetcher, type Insight } from "@/lib/api";

const RISK_TONE: Record<Insight["riskLabel"], string> = {
  LOW: "text-emerald-400",
  MODERATE: "text-cyan",
  ELEVATED: "text-amber-400",
  CRITICAL: "text-warn",
};

interface Props {
  trackingCode: string;
  panic?: boolean;
}

export function AIInsights({ trackingCode, panic = false }: Props) {
  const { data, isLoading, mutate, isValidating } = useSWR<Insight>(
    `/api/shipments/${trackingCode}/insights`,
    fetcher,
    { refreshInterval: 30_000 }
  );

  if (panic) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3 }}
        className="relative overflow-hidden rounded-2xl border border-warn/40 bg-warn/[0.04] p-6"
      >
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_50%_0%,rgba(251,146,60,0.12),transparent_60%)]" />
        <div className="text-[10px] uppercase tracking-[0.28em] text-warn">
          Critical Violation
        </div>
        <div className="mt-3 font-mono text-base leading-relaxed text-warn">
          SHIPMENT COMPROMISED.
          <br />
          STAKED FUNDS PREPARED FOR REFUND.
        </div>
        <div className="mt-6 h-px w-full bg-warn/30" />
        <div className="mt-3 text-[10px] uppercase tracking-[0.22em] text-warn/60">
          Arbitrator → Refund Staged
        </div>
      </motion.div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.28em] text-white/40">
          AI Insights
        </div>
        <button
          onClick={() =>
            fetch(`/api/shipments/${trackingCode}/insights?force=1`).then(() =>
              mutate()
            )
          }
          className="rounded-full p-1 text-white/30 transition hover:text-white/80"
          aria-label="Refresh insights"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${isValidating ? "animate-spin" : ""}`}
          />
        </button>
      </div>

      <AnimatePresence mode="wait">
        {isLoading || !data ? (
          <motion.div
            key="loading"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mt-6 space-y-2"
          >
            <Shimmer className="h-7 w-3/4" />
            <Shimmer className="h-4 w-full" />
            <Shimmer className="h-4 w-5/6" />
          </motion.div>
        ) : (
          <motion.div
            key={data.generatedAt}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.35 }}
          >
            <div className="mt-5 flex items-end gap-4">
              <RiskGauge score={data.riskScore} label={data.riskLabel} />
              <div className="min-w-0 flex-1">
                <div
                  className={`text-[10px] uppercase tracking-[0.22em] ${RISK_TONE[data.riskLabel]}`}
                >
                  {data.riskLabel}
                </div>
                <h3 className="mt-1 truncate font-sans text-base font-medium text-white">
                  {data.headline}
                </h3>
              </div>
            </div>

            <p className="mt-4 text-sm leading-relaxed text-white/70">
              {data.summary}
            </p>

            {data.etaIso && (
              <div className="mt-5">
                <div className="flex items-baseline justify-between text-[10px] uppercase tracking-[0.22em]">
                  <span className="text-white/40">ETA</span>
                  <span className="font-mono text-white/70">
                    {new Date(data.etaIso).toLocaleString(undefined, {
                      day: "2-digit",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
                <div className="mt-2 h-[2px] w-full overflow-hidden rounded-full bg-white/10">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${data.etaConfidence}%` }}
                    transition={{ duration: 0.8, ease: "easeOut" }}
                    className="h-full bg-cyan"
                  />
                </div>
              </div>
            )}

            {data.anomalies.length > 0 && (
              <Section label="Anomalies">
                {data.anomalies.map((a, i) => (
                  <li key={i} className="text-white/70">
                    {a}
                  </li>
                ))}
              </Section>
            )}

            {data.recommendations.length > 0 && (
              <Section label="Actions">
                {data.recommendations.map((a, i) => (
                  <li key={i} className="text-white/70">
                    {a}
                  </li>
                ))}
              </Section>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-5">
      <div className="text-[10px] uppercase tracking-[0.28em] text-white/40">
        {label}
      </div>
      <ul className="mt-2 space-y-1.5 text-sm">{children}</ul>
    </div>
  );
}

function RiskGauge({
  score,
  label,
}: {
  score: number;
  label: Insight["riskLabel"];
}) {
  const SIZE = 64;
  const STROKE = 5;
  const r = (SIZE - STROKE) / 2;
  const c = 2 * Math.PI * r;
  const dash = (Math.min(100, Math.max(0, score)) / 100) * c;
  const color =
    label === "CRITICAL"
      ? "#FB923C"
      : label === "ELEVATED"
      ? "#FBBF24"
      : label === "MODERATE"
      ? "#22D3EE"
      : "#34D399";
  return (
    <div className="relative" style={{ width: SIZE, height: SIZE }}>
      <svg width={SIZE} height={SIZE} className="-rotate-90">
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={r}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={STROKE}
        />
        <motion.circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c - dash }}
          transition={{ duration: 0.9, ease: "easeOut" }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <span className="font-mono text-base text-white">{Math.round(score)}</span>
      </div>
    </div>
  );
}

function Shimmer({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-white/[0.06] ${className}`} />;
}
