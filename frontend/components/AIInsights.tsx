"use client";

// AIInsights v3 — forensic, silent, interactive.
//   ◇ Top: tiny "AI INSIGHTS" header + Ethereum diamond mark + refresh.
//   ◇ Hero: large risk number, STATUS chip, single-line headline. NO PARAGRAPH.
//   ◇ Collapsed bullets: anomalies + actions, dense, no chrome.
//   ◇ Chat: ask the Supreme Judge anything → forensic reply, telemetry-grounded.
//   ◇ Footer: PDF report button (downloads /report.pdf), branded with EthLogo.

import { useState } from "react";
import useSWR from "swr";
import { motion, AnimatePresence } from "framer-motion";
import { RefreshCw, Send, FileDown, Sparkles } from "lucide-react";
import { fetcher, type Insight } from "@/lib/api";
import { EthLogo } from "./EthLogo";

const RISK_TONE: Record<Insight["riskLabel"], string> = {
  LOW: "text-emerald-400",
  MODERATE: "text-cyan",
  ELEVATED: "text-amber-400",
  CRITICAL: "text-warn",
};

const STATUS_LABEL: Record<Insight["riskLabel"], string> = {
  LOW: "NOMINAL",
  MODERATE: "ELEVATED ATTENTION",
  ELEVATED: "WATCHLIST",
  CRITICAL: "BREACH",
};

interface ChatTurn { role: "user" | "assistant"; content: string }

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

  const [history, setHistory] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  async function ask(question: string) {
    if (!question.trim() || sending) return;
    setSending(true);
    const userTurn: ChatTurn = { role: "user", content: question };
    setHistory((h) => [...h, userTurn]);
    setInput("");
    try {
      const r = await fetch(`/api/shipments/${trackingCode}/chat`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question, history }),
      });
      const j = (await r.json()) as { answer: string };
      setHistory((h) => [...h, { role: "assistant", content: j.answer }]);
    } catch {
      setHistory((h) => [
        ...h,
        { role: "assistant", content: "Network error. Retry." },
      ]);
    } finally {
      setSending(false);
    }
  }

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

  const tone = data ? RISK_TONE[data.riskLabel] : "text-white/60";
  const statusText = data ? STATUS_LABEL[data.riskLabel] : "ANALYSING";

  return (
    <div className="relative flex h-full max-h-[calc(100vh-180px)] min-h-[460px] flex-col overflow-hidden rounded-2xl border border-white/[0.06] bg-white/[0.015]">
      {/* Subtle inner glow */}
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(circle_at_50%_-20%,rgba(34,211,238,0.06),transparent_60%)]" />

      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/[0.05] px-5 py-3.5">
        <div className="flex items-center gap-2.5">
          <EthLogo size={12} tint="#A4B0FF" />
          <div className="text-[10px] uppercase tracking-[0.32em] text-white/55">
            AI Insights
          </div>
        </div>
        <button
          onClick={() =>
            fetch(`/api/shipments/${trackingCode}/insights?force=1`).then(() =>
              mutate()
            )
          }
          className="rounded-full p-1 text-white/40 transition hover:text-white"
          aria-label="Refresh insights"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${isValidating ? "animate-spin" : ""}`}
          />
        </button>
      </div>

      {/* Hero verdict */}
      <div className="px-5 pt-5">
        <AnimatePresence mode="wait">
          {isLoading || !data ? (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="space-y-3"
            >
              <Shimmer className="h-12 w-1/3" />
              <Shimmer className="h-4 w-2/3" />
            </motion.div>
          ) : (
            <motion.div
              key={data.generatedAt}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35 }}
              className="space-y-3"
            >
              <div className="flex items-end gap-5">
                <RiskGauge score={data.riskScore} label={data.riskLabel} />
                <div className="min-w-0 flex-1 pb-1">
                  <div
                    className={`text-[9px] uppercase tracking-[0.32em] ${tone}`}
                  >
                    STATUS · {statusText}
                  </div>
                  <h3 className="mt-1.5 font-sans text-[15px] font-medium leading-snug text-white/95">
                    {data.headline}
                  </h3>
                </div>
              </div>

              {/* Compact metadata strip — replaces the paragraph */}
              {data.etaIso && (
                <div className="flex items-baseline justify-between border-t border-white/[0.05] pt-3 text-[10px] uppercase tracking-[0.24em]">
                  <span className="text-white/55">ETA</span>
                  <span className="font-mono text-white/85">
                    {new Date(data.etaIso).toLocaleString(undefined, {
                      day: "2-digit",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
              )}

              {/* Bullets — only if present, dense */}
              {(data.anomalies.length > 0 || data.recommendations.length > 0) && (
                <div className="grid grid-cols-2 gap-x-5 gap-y-1 pt-1">
                  {data.anomalies.length > 0 && (
                    <BulletList label="Anomalies" items={data.anomalies} />
                  )}
                  {data.recommendations.length > 0 && (
                    <BulletList label="Actions" items={data.recommendations} />
                  )}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Chat thread */}
      <div className="mt-4 flex-1 overflow-y-auto px-5">
        {history.length === 0 ? (
          <div className="rounded-xl border border-dashed border-white/[0.06] px-4 py-3 text-[11px] leading-relaxed text-white/45">
            Ask the Supreme Judge — e.g.&nbsp;
            <button
              onClick={() => ask("Are we exposed to a refund right now?")}
              className="text-cyan/80 underline-offset-2 hover:underline"
            >
              "Are we exposed to a refund right now?"
            </button>
          </div>
        ) : (
          <div className="space-y-2.5 pb-3">
            {history.map((m, i) => (
              <ChatBubble key={i} role={m.role} content={m.content} />
            ))}
            {sending && (
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.28em] text-white/35">
                <Sparkles className="h-3 w-3 animate-pulse" />
                judge thinking…
              </div>
            )}
          </div>
        )}
      </div>

      {/* Input + actions */}
      <div className="border-t border-white/[0.05] px-3 py-3">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
          className="flex items-center gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask the Supreme Judge…"
            disabled={sending}
            className="flex-1 rounded-xl border border-white/[0.06] bg-black/40 px-3.5 py-2 text-[13px] text-white placeholder:text-white/30 outline-none transition focus:border-cyan/40 focus:bg-black/60"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            className="grid h-9 w-9 place-items-center rounded-xl border border-white/[0.06] text-white/55 transition hover:border-cyan/40 hover:text-cyan disabled:opacity-30"
            aria-label="Send"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
          <a
            href={`/api/shipments/${trackingCode}/report.pdf`}
            target="_blank"
            rel="noreferrer"
            className="group flex h-9 items-center gap-2 rounded-xl border border-white/[0.06] bg-gradient-to-br from-[#1a2046]/70 to-[#0a0d1a]/40 px-3 text-[10px] uppercase tracking-[0.24em] text-white/75 transition hover:border-[#A4B0FF]/40 hover:text-white"
            aria-label="Generate AI PDF report"
          >
            <EthLogo size={11} tint="#A4B0FF" />
            <FileDown className="h-3 w-3" />
            <span className="hidden md:inline">Report</span>
          </a>
        </form>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Sub-components
// ----------------------------------------------------------------------------

function ChatBubble({ role, content }: ChatTurn) {
  const isUser = role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[90%] rounded-xl px-3 py-2 text-[12.5px] leading-relaxed ${
          isUser
            ? "bg-cyan/[0.08] text-white/90 border border-cyan/20"
            : "bg-white/[0.03] text-white/85 border border-white/[0.06]"
        }`}
      >
        {!isUser && (
          <div className="mb-1 flex items-center gap-1.5 text-[8px] uppercase tracking-[0.32em] text-white/40">
            <EthLogo size={9} tint="#A4B0FF" />
            judge
          </div>
        )}
        <span className="whitespace-pre-wrap">{content}</span>
      </div>
    </motion.div>
  );
}

function BulletList({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-[0.28em] text-white/45">
        {label}
      </div>
      <ul className="mt-1 space-y-0.5">
        {items.slice(0, 3).map((a, i) => (
          <li key={i} className="text-[11.5px] leading-snug text-white/72">
            · {a}
          </li>
        ))}
      </ul>
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
  const SIZE = 76;
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
          stroke="rgba(255,255,255,0.07)"
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
          style={{ filter: `drop-shadow(0 0 8px ${color}66)` }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <span className="font-mono text-2xl text-white" style={{ textShadow: `0 0 18px ${color}55` }}>
          {Math.round(score)}
        </span>
      </div>
    </div>
  );
}

function Shimmer({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-white/[0.06] ${className}`} />;
}
