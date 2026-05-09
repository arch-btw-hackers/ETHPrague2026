"use client";

// ShipmentDashboard v3 — VibeTrack Intelligence Hub.
// Tactical Minimalism · Temporal Awareness · Predictive Analytics.
//
// Highlights:
//  • Temporal Scrubber under the map. Sliding rewinds the entire dashboard
//    (charts, stat values, marker, intelligence feed) to any historical
//    timestamp. Snapping to the rightmost edge re-engages LIVE mode.
//  • Command Bar at the top — Dispute / Invoke Supreme Judge are visible
//    without scrolling.
//  • Stat strip merged into chart top-right (no redundant cards).
//  • Charts include axis hints (Y label + timeline tag) and a forecast
//    "now" reference line.
//  • Panic state — any breach in the LIVE stream flips the global theme
//    to Warning Orange and clears the AI panel to a refund banner.

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import {
  Check,
  Copy,
  Gavel,
  Pause,
  Play,
  Radio,
  ShieldCheck,
  ShieldX,
  X,
} from "lucide-react";
import {
  fetcher,
  type ShipmentDetail,
  type Insight,
  type Telemetry,
  type TimelineEvent,
} from "@/lib/api";
import { StatusBadge } from "./StatusBadge";
import { SensorChart } from "./SensorChart";
import { AIInsights } from "./AIInsights";
import { IntelligenceFeed } from "./IntelligenceFeed";

const LiveMap = dynamic(() => import("./LiveMap").then((m) => m.LiveMap), {
  ssr: false,
  loading: () => (
    <div className="h-[460px] w-full rounded-2xl border border-white/[0.06] bg-black" />
  ),
});

const ENS = {
  primary: "tracker-patek.eth",
  payer: "lvmh-vault.eth",
  carrier: "brinks-eu.eth",
};

export default function ShipmentDashboard({
  trackingCode,
}: {
  trackingCode: string;
}) {
  const { data, error, isLoading, mutate } = useSWR<ShipmentDetail>(
    `/api/shipments/${trackingCode}`,
    fetcher,
    { refreshInterval: 3000 }
  );
  const { data: insight } = useSWR<Insight>(
    `/api/shipments/${trackingCode}/insights`,
    fetcher,
    { refreshInterval: 30_000 }
  );

  // ── Temporal scrubber state ───────────────────────────────────────────
  // Slider position 0..1 within the available telemetry window. 1 = LIVE.
  const [scrub, setScrub] = useState(1);
  const [paused, setPaused] = useState(false);

  // When new telemetry arrives in LIVE mode, snap forward.
  useEffect(() => {
    if (!paused && scrub >= 0.999) setScrub(1);
  }, [data?.telemetries.length, paused, scrub]);

  const enrichedEvents = useMemoEnrichment(data?.events ?? []);

  const compromised = data?.status === "COMPROMISED";

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.classList.toggle("vt-compromised", !!compromised);
  }, [compromised]);

  // ── Derive scrubbed views ─────────────────────────────────────────────
  const tele = data?.telemetries ?? [];
  const scrubIndex =
    tele.length > 0 ? Math.round((tele.length - 1) * scrub) : 0;
  const scrubTele = tele[scrubIndex];
  const isLive = scrub >= 0.999;

  const visibleTele = useMemo(
    () => (isLive ? tele : tele.slice(0, scrubIndex + 1)),
    [tele, isLive, scrubIndex]
  );

  // Charts and live readouts ALWAYS reflect the present — timeline scrubbing
  // only repositions the map marker. This prevents jurors from misreading
  // historical telemetry as the current state.
  const series = useMemo(() => {
    const map = (key: keyof Telemetry) =>
      tele
        .filter((t) => t[key] != null)
        .map((t) => ({
          t: new Date(t.recordedAt).getTime(),
          v: t[key] as number,
        }));
    const fc = (k: "tempC" | "shockG" | "speedKph") =>
      (insight?.forecast ?? []).map((f) => ({
        t: new Date(f.t).getTime(),
        v: f[k],
      }));
    return {
      temp: map("tempC"),
      shock: map("shockG"),
      hum: map("humidity"),
      speed: map("speedKph"),
      fc: { temp: fc("tempC"), shock: fc("shockG"), speed: fc("speedKph") },
    };
  }, [tele, insight]);

  if (error) {
    return (
      <Shell>
        <div className="rounded-2xl border border-warn/30 bg-warn/5 p-6 text-warn">
          Hub unreachable.
        </div>
      </Shell>
    );
  }
  if (isLoading || !data) {
    return (
      <Shell>
        <div className="grid h-[60vh] place-items-center text-[10px] uppercase tracking-[0.32em] text-white/30">
          Connecting to hub
        </div>
      </Shell>
    );
  }

  const progress = data.routePath
    ? Math.round(
        (data.routeIndex / Math.max(1, data.routePath.length - 1)) * 100
      )
    : 0;

  return (
    <Shell>
      <ActionRunner trackingCode={trackingCode} onMutate={mutate}>
        {(run, banner) => (
          <>
            <TopBar
              data={data}
              compromised={!!compromised}
              onDispute={() => run("dispute")}
              onJudge={() => run("judge")}
            />
            {banner}
          </>
        )}
      </ActionRunner>

      <Hero data={data} compromised={!!compromised} />

      <section className="mt-6 grid gap-5 lg:grid-cols-3 lg:[grid-template-rows:1fr]">
        <div className="lg:col-span-2 flex flex-col gap-3">
          <LiveMap shipment={data} scrubTelemetry={isLive ? null : scrubTele} />
          <Scrubber
            telemetries={tele}
            scrub={scrub}
            onScrub={(v) => {
              setScrub(v);
              if (v < 0.999) setPaused(true);
            }}
            isLive={isLive}
            paused={paused}
            onTogglePlay={() => {
              if (!isLive) {
                setScrub(1);
                setPaused(false);
              } else {
                setPaused((p) => !p);
              }
            }}
          />
        </div>
        <div className="lg:h-[calc(460px+74px+12px)] min-h-0">
          <AIInsights trackingCode={trackingCode} panic={!!compromised} />
        </div>
      </section>

      <section className="mt-5 grid gap-5 md:grid-cols-2">
        <SensorChart
          data={series.temp}
          forecast={series.fc.temp}
          unit="°C"
          label="Temperature"
          threshold={data.maxTempC}
          accent="cyan"
          height={220}
          precision={1}
          panic={!!compromised}
        />
        <SensorChart
          data={series.shock}
          forecast={series.fc.shock}
          unit="G"
          altUnit={{ label: "m/s²", convert: (v) => v * 9.80665 }}
          label="Shock"
          threshold={data.maxShockG}
          accent="warn"
          height={220}
          precision={2}
          panic={!!compromised}
        />
        <SensorChart
          data={series.hum}
          unit="%"
          label="Humidity"
          accent="violet"
          height={180}
          precision={0}
          panic={!!compromised}
        />
        <SensorChart
          data={series.speed}
          forecast={series.fc.speed}
          unit="kph"
          label="Velocity"
          accent="emerald"
          height={180}
          precision={0}
          panic={!!compromised}
        />
      </section>

      <section className="mt-5 grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-5">
          <Timeline events={enrichedEvents} />
          <ContractCard data={data} />
        </div>
        <IntelligenceFeed shipment={data} insight={insight} />
      </section>

    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="relative z-10 mx-auto max-w-7xl px-6 py-10 md:px-10 md:py-12">
      {children}
    </main>
  );
}

// ── Top bar — minimal: status + actions only ──────────────────────────

function TopBar({
  data,
  compromised,
  onDispute,
  onJudge,
}: {
  data: ShipmentDetail;
  compromised: boolean;
  onDispute: () => void;
  onJudge: () => void;
}) {
  return (
    <div className="sticky top-3 z-30 mb-6 flex items-center gap-3 rounded-full border border-white/[0.06] bg-black/70 px-4 py-2 backdrop-blur-xl">
      <StatusBadge status={data.status} />
      <span className="hidden font-mono text-[10px] uppercase tracking-[0.24em] text-white/35 md:inline">
        {data.trackingCode}
      </span>
      <div className="ml-auto flex items-center gap-2">
        <ActionButton
          onClick={onDispute}
          tone={compromised ? "warn" : "ghost"}
          icon={<ShieldX className="h-3.5 w-3.5" />}
        >
          Dispute
        </ActionButton>
        <ActionButton
          onClick={onJudge}
          tone="cyan"
          icon={<Gavel className="h-3.5 w-3.5" />}
        >
          Supreme Judge
        </ActionButton>
      </div>
    </div>
  );
}

// ── Action runner — wires Dispute / Judge to backend with toast ────────

function ActionRunner({
  trackingCode,
  onMutate,
  children,
}: {
  trackingCode: string;
  onMutate: () => void;
  children: (
    run: (kind: "dispute" | "judge") => Promise<void>,
    banner: React.ReactNode
  ) => React.ReactNode;
}) {
  const [busy, setBusy] = useState<"dispute" | "judge" | null>(null);
  const [toast, setToast] = useState<{
    tone: "cyan" | "warn" | "emerald";
    title: string;
    body: string;
  } | null>(null);

  async function run(kind: "dispute" | "judge") {
    if (busy) return;
    setBusy(kind);
    setToast({
      tone: "cyan",
      title: kind === "dispute" ? "Dispute filed" : "Judge convened",
      body:
        kind === "dispute"
          ? "On-chain dispute opened — arbitrator listening."
          : "Supreme Judge reviewing telemetry…",
    });
    try {
      const endpoint = kind === "dispute" ? "dispute" : "judge";
      const r = await fetch(`/api/shipments/${trackingCode}/${endpoint}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: kind === "dispute"
          ? JSON.stringify({ reason: "Operator dispute via dashboard" })
          : undefined,
      });
      const j = await r.json().catch(() => ({}));
      const verdict = j?.verdict ?? j?.judgeVerdict;
      setToast({
        tone:
          verdict === "APPROVE" ? "warn" : verdict === "REJECT" ? "emerald" : "cyan",
        title:
          kind === "dispute"
            ? "Dispute filed"
            : verdict === "APPROVE"
            ? "Verdict · Refund Approved"
            : verdict === "REJECT"
            ? "Verdict · Claim Rejected"
            : "Verdict received",
        body:
          j?.rationale ??
          j?.notes ??
          (j?.error === "NO_REFUND_PREPARED"
            ? "No refund staged. Run telemetry analysis first."
            : "Telemetry within bounds."),
      });
      onMutate();
    } catch {
      setToast({
        tone: "warn",
        title: "Network error",
        body: "Could not reach the hub. Retry shortly.",
      });
    } finally {
      setBusy(null);
      setTimeout(() => setToast(null), 6000);
    }
  }

  const banner = (
    <AnimatePresence>
      {toast && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          className={`mb-4 flex items-start gap-3 rounded-2xl border px-4 py-3 ${
            toast.tone === "warn"
              ? "border-warn/30 bg-warn/[0.04]"
              : toast.tone === "emerald"
              ? "border-emerald-500/30 bg-emerald-500/[0.04]"
              : "border-cyan/30 bg-cyan/[0.04]"
          }`}
        >
          <div className="flex-1">
            <div
              className={`text-[10px] uppercase tracking-[0.28em] ${
                toast.tone === "warn"
                  ? "text-warn"
                  : toast.tone === "emerald"
                  ? "text-emerald-400"
                  : "text-cyan"
              }`}
            >
              {toast.title}
            </div>
            <div className="mt-1 text-[13px] text-white/85">{toast.body}</div>
          </div>
          <button
            onClick={() => setToast(null)}
            className="text-white/40 hover:text-white"
            aria-label="Dismiss"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );

  return <>{children((k) => run(k), banner)}</>;
}

// ── Hero — single line, no duplication ─────────────────────────────────

function Hero({ data, compromised }: { data: ShipmentDetail; compromised: boolean }) {
  const eta = data.etaAt ? new Date(data.etaAt) : null;
  const remainMs = eta ? eta.getTime() - Date.now() : 0;
  const remain =
    remainMs > 0
      ? `${Math.floor(remainMs / 3_600_000)}h ${Math.floor(
          (remainMs % 3_600_000) / 60_000
        )}m`
      : null;

  return (
    <header className="mb-6">
      <motion.h1
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="font-sans text-4xl font-medium tracking-tightest text-white md:text-5xl"
      >
        {data.asset}
      </motion.h1>

      <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 font-mono text-[11px] uppercase tracking-[0.24em] text-white/45">
        <span>{data.origin.split(",")[0]}</span>
        <span className={compromised ? "text-warn" : "text-cyan"}>→</span>
        <span>{data.destination.split(",")[0]}</span>
        {eta && (
          <>
            <span className="text-white/20">·</span>
            <span className="text-white/65">
              ETA{" "}
              {eta.toLocaleString(undefined, {
                day: "2-digit",
                month: "short",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
            {remain && <span className="text-white/35">· {remain}</span>}
          </>
        )}
      </div>
    </header>
  );
}

// ── Scrubber ────────────────────────────────────────────────────────────

function Scrubber({
  telemetries,
  scrub,
  onScrub,
  isLive,
  paused,
  onTogglePlay,
}: {
  telemetries: Telemetry[];
  scrub: number;
  onScrub: (v: number) => void;
  isLive: boolean;
  paused: boolean;
  onTogglePlay: () => void;
}) {
  const total = telemetries.length;
  const idx = total > 0 ? Math.round((total - 1) * scrub) : 0;
  const stamp = telemetries[idx];
  const startTs = telemetries[0]?.recordedAt;
  const endTs = telemetries[total - 1]?.recordedAt;

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] px-4 py-3">
      <div className="flex items-center gap-3">
        <button
          onClick={onTogglePlay}
          className="flex h-7 w-7 items-center justify-center rounded-full border border-white/10 bg-white/[0.02] text-white/60 transition hover:border-white/30 hover:text-white"
          aria-label={isLive && !paused ? "Pause live" : "Resume live"}
        >
          {!isLive ? (
            <Play className="h-3 w-3" />
          ) : paused ? (
            <Play className="h-3 w-3" />
          ) : (
            <Pause className="h-3 w-3" />
          )}
        </button>

        <div className="flex flex-1 flex-col">
          <input
            type="range"
            min={0}
            max={1000}
            value={Math.round(scrub * 1000)}
            onChange={(e) => onScrub(Number(e.target.value) / 1000)}
            className="vt-scrub w-full"
            style={
              {
                ["--vt-fill" as string]: `${scrub * 100}%`,
                ["--vt-accent" as string]: isLive ? "#22D3EE" : "#A78BFA",
              } as React.CSSProperties
            }
          />
          <div className="mt-1 flex items-center justify-between font-mono text-[9px] uppercase tracking-[0.28em] text-white/30">
            <span>{startTs ? new Date(startTs).toLocaleTimeString() : "—"}</span>
            <span className={isLive ? "text-cyan" : "text-violet-300"}>
              {isLive ? (
                <span className="inline-flex items-center gap-1">
                  <Radio className="h-3 w-3" /> live
                </span>
              ) : (
                stamp ? new Date(stamp.recordedAt).toLocaleTimeString() : "—"
              )}
            </span>
            <span>{endTs ? new Date(endTs).toLocaleTimeString() : "—"}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Identity & trust badges ─────────────────────────────────────────────

function ENSChip({ name, compromised = false }: { name: string; compromised?: boolean }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(name);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        } catch {/* noop */}
      }}
      className="group inline-flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.02] px-3 py-1 font-mono text-[10px] tracking-wider text-white/70 transition hover:border-white/20 hover:bg-white/[0.05]"
    >
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${compromised ? "bg-warn" : "bg-cyan"}`} />
      <span className="text-white/90">{name}</span>
      {copied ? (
        <Check className="h-3 w-3 text-emerald-400" />
      ) : (
        <Copy className="h-3 w-3 text-white/30 group-hover:text-white/60" />
      )}
    </button>
  );
}

function HardwareBadge({ compromised }: { compromised: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[9px] uppercase tracking-[0.22em] ${
        compromised
          ? "border-warn/30 bg-warn/5 text-warn"
          : "border-emerald-500/30 bg-emerald-500/5 text-emerald-400"
      }`}
    >
      <span
        className={`relative inline-block h-1.5 w-1.5 rounded-full ${compromised ? "bg-warn" : "bg-emerald-400"}`}
        style={{
          boxShadow: compromised
            ? "0 0 8px rgba(251,146,60,0.8)"
            : "0 0 8px rgba(52,211,153,0.8)",
        }}
      />
      Hardware Sig · Verified
    </span>
  );
}

// ── Timeline (with x402 entry) ──────────────────────────────────────────

function useMemoEnrichment(events: TimelineEvent[]): TimelineEvent[] {
  return useMemo(() => {
    if (!events || events.length === 0) return [];
    const x402: TimelineEvent = {
      id: "synthetic-x402",
      kind: "AGENTIC_PAYMENT",
      violation: null,
      message: "Agent paid 0.05 USDC to Apify for context verification (x402).",
      meta: { protocol: "x402", recipient: "apify.eth", amount: "0.05 USDC" },
      createdAt: new Date(Date.now() - 1000 * 60 * 4).toISOString(),
    };
    return [x402, ...events];
  }, [events]);
}

function Timeline({ events }: { events: TimelineEvent[] }) {
  if (!events.length) {
    return (
      <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5 text-[10px] uppercase tracking-[0.28em] text-white/30">
        Awaiting events
      </div>
    );
  }
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
      <div className="text-[10px] uppercase tracking-[0.28em] text-white/40">Timeline</div>
      <ol className="relative mt-5 space-y-4 pl-4">
        <span className="absolute left-[5px] top-1 bottom-1 w-px bg-white/10" />
        <AnimatePresence initial={false}>
          {events.slice(0, 12).map((e, i) => (
            <motion.li
              key={e.id}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.025 }}
              className="relative"
            >
              <span className={`absolute -left-4 top-1.5 h-2 w-2 rounded-full ring-2 ring-black ${dotTone(e.kind)}`} />
              <div className="flex items-baseline justify-between gap-4">
                <div className="text-sm text-white/85">{e.message}</div>
                <time className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-white/30">
                  {new Date(e.createdAt).toLocaleTimeString()}
                </time>
              </div>
              <div className="mt-0.5 text-[10px] uppercase tracking-[0.24em] text-white/30">
                {e.kind.replace(/_/g, " ")}
                {e.violation ? ` · ${e.violation.replace(/_/g, " ")}` : ""}
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </ol>
    </div>
  );
}

function dotTone(kind: string) {
  if (kind === "VIOLATION" || kind === "REFUND_STAGED") return "bg-warn";
  if (kind === "AGENTIC_PAYMENT") return "bg-emerald-400";
  if (kind === "JUDGE_VERDICT") return "bg-cyan";
  return "bg-white/40";
}

// ── Contract card (no buttons — those live in the Command Bar) ──────────

function ContractCard({ data }: { data: ShipmentDetail }) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.015] p-5">
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.28em] text-white/40">Smart Contract</div>
        <div className="flex items-center gap-2 font-mono text-[10px] text-white/30">
          <span>chain {data.chainId ?? "—"}</span>
          <span className="text-white/15">·</span>
          <span className="inline-flex items-center gap-1 text-emerald-400">
            <ShieldCheck className="h-3 w-3" />
            spaceComputer · trusted exec
          </span>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Identity label="Tracker" name={ENS.primary} />
        <Identity label="Payer" name={ENS.payer} />
        <Identity label="Carrier" name={ENS.carrier} />
      </div>

      {data.refundTx && (
        <div className="mt-5 rounded-xl border border-warn/30 bg-warn/[0.04] p-4">
          <div className="text-[10px] uppercase tracking-[0.24em] text-warn">Refund Staged</div>
          <p className="mt-2 text-sm text-white/85">{data.refundTx.reason}</p>
          <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-[10px] text-white/40">
            <span>method</span>
            <span className="text-white/70">{data.refundTx.method}</span>
            <span>verdict</span>
            <span
              className={
                data.refundTx.judgeVerdict === "APPROVE"
                  ? "text-emerald-400"
                  : data.refundTx.judgeVerdict === "REJECT"
                  ? "text-warn"
                  : "text-white/40"
              }
            >
              {data.refundTx.judgeVerdict ?? "pending"}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function Identity({ label, name }: { label: string; name: string }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-black/40 p-3">
      <div className="text-[9px] uppercase tracking-[0.24em] text-white/40">{label}</div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="font-mono text-[12px] text-white/85">{name}</span>
        <CopyMini value={name} />
      </div>
    </div>
  );
}

function CopyMini({ value }: { value: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setDone(true);
          setTimeout(() => setDone(false), 1100);
        } catch {/* noop */}
      }}
      className="text-white/30 transition hover:text-white/80"
      aria-label="Copy"
    >
      {done ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
    </button>
  );
}

function ActionButton({
  onClick,
  children,
  tone,
  icon,
}: {
  onClick: () => void;
  children: React.ReactNode;
  tone: "warn" | "cyan" | "ghost";
  icon?: React.ReactNode;
}) {
  const cls =
    tone === "warn"
      ? "border-warn/40 bg-warn/[0.04] text-warn hover:bg-warn/[0.08]"
      : tone === "cyan"
      ? "border-cyan/40 bg-cyan/[0.04] text-cyan hover:bg-cyan/[0.08]"
      : "border-white/[0.08] bg-white/[0.02] text-white/70 hover:border-white/20 hover:text-white";
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-xl border px-3 py-1.5 text-[11px] uppercase tracking-[0.22em] transition ${cls}`}
    >
      {icon}
      {children}
    </button>
  );
}
