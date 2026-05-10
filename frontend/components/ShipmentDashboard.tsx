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

import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import {
  ArrowLeft,
  Check,
  Copy,
  Gavel,
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
  apiBase,
  readOnly = false,
  showDevicesLink = false,
}: {
  trackingCode: string;
  /** Override the API root. Defaults to `/api/shipments/<trackingCode>`.
   *  External devices pass `/api/external/devices/<id>`. */
  apiBase?: string;
  /** Hide write actions (Dispute / Judge / Report) — used for external
   *  read-only feeds where those endpoints don't exist. */
  readOnly?: boolean;
  /** Show “Live devices” link in the top bar. */
  showDevicesLink?: boolean;
}) {
  const base = apiBase ?? `/api/shipments/${trackingCode}`;
  const { data, error, isLoading, mutate } = useSWR<ShipmentDetail>(
    base,
    fetcher,
    { refreshInterval: 3000 }
  );
  const { data: insight } = useSWR<Insight>(
    `${base}/insights`,
    fetcher,
    { refreshInterval: 30_000 }
  );

  // ── Temporal scrubber state ───────────────────────────────────────────
  // scrubT is an absolute timestamp (ms). Domain spans the full journey
  // from the first observation to the predicted ETA. NOW marks the present;
  // anything left of NOW is historic, anything right is AI-forecast.
  const [scrubT, setScrubT] = useState<number | null>(null);
  const [follow, setFollow] = useState(true); // when true, scrubT == now (live)

  const enrichedEvents = useMemoEnrichment(data?.events ?? []);

  const compromised = data?.status === "COMPROMISED";

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.body.classList.toggle("vt-compromised", !!compromised);
  }, [compromised]);

  // ── Derive scrubbed views ─────────────────────────────────────────────
  const tele = data?.telemetries ?? [];
  const now = Date.now();

  // Domain: weight the bar so HISTORY dominates and the future is a healthy
  // tail to the right of NOW (~60% past / ~40% future). Past span = how
  // long the shipment has been observed (with a generous floor so a fresh
  // shipment still has a usable scrub area). Future span = the larger of
  // the ETA distance and a generous fraction of past, so NOW always sits
  // around 60% of the bar even when ETA is missing.
  const firstT = tele.length
    ? new Date(tele[0].recordedAt).getTime()
    : now - 3_600_000;
  const etaT = data?.etaAt ? new Date(data.etaAt).getTime() : null;
  const MIN_PAST_MS = 24 * 3_600_000; // always show at least 24h of history
  const pastSpan = Math.max(now - firstT, MIN_PAST_MS);
  // Always reserve ~⅔ of past as forward room (caps the bar at ~60/40).
  const FUTURE_FLOOR = Math.round(pastSpan * 0.66);
  const futureSpan = Math.min(
    Math.max(etaT != null ? etaT - now : FUTURE_FLOOR, FUTURE_FLOOR),
    Math.round(pastSpan * 0.85),
  );
  const domainStart = now - pastSpan;
  const domainEnd = now + futureSpan;

  const t = follow || scrubT == null ? now : scrubT;
  // Mode classification with a small dead-zone around "now" so live state
  // doesn't flicker if the user lets go just before now.
  const mode: "past" | "live" | "future" =
    follow || Math.abs(t - now) < 30_000
      ? "live"
      : t < now
      ? "past"
      : "future";
  const isLive = mode === "live";

  // ── Predicting state ──────────────────────────────────────────────────
  // When the user scrubs into the future, simulate a 3-second AI inference
  // before revealing predicted values. Re-armed each time we enter future
  // mode (or jump to a different forecast hour).
  const [predicting, setPredicting] = useState(false);
  const futureBucket = mode === "future" ? Math.floor(t / 3_600_000) : null;
  useEffect(() => {
    if (futureBucket == null) {
      setPredicting(false);
      return;
    }
    setPredicting(true);
    const id = setTimeout(() => setPredicting(false), 3000);
    return () => clearTimeout(id);
  }, [futureBucket]);

  // Map marker position derived from scrub time.
  // Simple linear mapping: domainStart → Prague (route[0]),
  // domainEnd → Málaga (route[lastIdx]).
  // NOW sits at ~60% of the bar so the live marker is ~60% through the road.
  // Scrubbing left approaches Prague; scrubbing right approaches Málaga.
  const scrubTele = useMemo<Telemetry | undefined>(() => {
    if (!tele.length) return undefined;
    const head = tele[tele.length - 1];
    const route = (data?.routePath ?? []) as [number, number][];
    if (route.length < 2) return head;
    const lastIdx = route.length - 1;

    const totalSpan = domainEnd - domainStart;
    const r = totalSpan > 0
      ? Math.min(1, Math.max(0, (t - domainStart) / totalSpan))
      : 1;
    const frac = r * lastIdx;
    const i0 = Math.floor(frac);
    const i1 = Math.min(lastIdx, i0 + 1);
    const f = frac - i0;
    const a = route[i0];
    const b = route[i1];
    const lng = a[0] + (b[0] - a[0]) * f;
    const lat = a[1] + (b[1] - a[1]) * f;
    return { ...head, lat, lng, recordedAt: new Date(t).toISOString() };
  }, [tele, t, data?.routePath, domainStart, domainEnd]);

  // Hourly averages over historical telemetry — kept for chart slicing.
  const hourly = useMemo(() => {
    type Bucket = {
      t: number;
      tempSum: number;
      shockSum: number;
      humSum: number;
      speedSum: number;
      n: number;
    };
    const map = new Map<number, Bucket>();
    for (const x of tele) {
      const ts = new Date(x.recordedAt).getTime();
      const hr = Math.floor(ts / 3_600_000) * 3_600_000;
      let b = map.get(hr);
      if (!b) {
        b = { t: hr, tempSum: 0, shockSum: 0, humSum: 0, speedSum: 0, n: 0 };
        map.set(hr, b);
      }
      b.tempSum += x.tempC ?? 0;
      b.shockSum += x.shockG ?? 0;
      b.humSum += x.humidity ?? 0;
      b.speedSum += x.speedKph ?? 0;
      b.n += 1;
    }
    return [...map.values()]
      .map((b) => ({
        t: b.t,
        temp: b.tempSum / b.n,
        shock: b.shockSum / b.n,
        hum: b.humSum / b.n,
        speed: b.speedSum / b.n,
      }))
      .sort((a, b) => a.t - b.t);
  }, [tele]);

  const liveSample = tele[tele.length - 1];

  // Peak shock over the trailing 60 s window. The SHOCK readout is meant to
  // surface the worst impact in recent history, not just whatever the device
  // happened to report this tick (which is usually near 1 g of gravity).
  const liveShockMax = useMemo(() => {
    if (!tele.length) return undefined;
    const cutoff = Date.now() - 60_000;
    let peak = -Infinity;
    for (const s of tele) {
      const ts = new Date(s.recordedAt).getTime();
      if (ts < cutoff) continue;
      const g = s.shockG ?? 0;
      if (g > peak) peak = g;
    }
    return Number.isFinite(peak) ? peak : (liveSample?.shockG ?? 0);
  }, [tele, liveSample]);

  // Past readouts. We don't have ground-truth values for every historical
  // hour, but the user wants the numbers to react instantly while scrubbing.
  // Seed a deterministic pseudo-random drift per hour bucket, anchored to
  // the live sample so values feel realistic. Re-scrubbing to the same
  // hour produces the same numbers.
  const pastReadout = useMemo(() => {
    if (mode !== "past" || !liveSample) return null;
    // Prefer a real hourly bucket if telemetry actually covers this slot.
    const realHr = Math.floor(t / 3_600_000) * 3_600_000;
    const realBucket = hourly.find((b) => b.t === realHr);
    if (realBucket) {
      return {
        temp: realBucket.temp,
        shock: realBucket.shock,
        hum: realBucket.hum,
        speed: realBucket.speed,
      };
    }
    const hr = Math.floor(t / 3_600_000);
    const rand = (s: number) => {
      const x = Math.sin(s * 7349 + 12379) * 233280;
      return x - Math.floor(x);
    };
    const drift = (seed: number, scale: number) => (rand(seed) * 2 - 1) * scale;
    return {
      temp: (liveSample.tempC ?? 0) + drift(hr, 1.6),
      shock: Math.max(0, (liveSample.shockG ?? 0) + drift(hr + 17, 0.22)),
      hum: Math.min(
        95,
        Math.max(20, (liveSample.humidity ?? 50) + drift(hr + 31, 7)),
      ),
      speed: Math.max(
        0,
        (liveSample.speedKph ?? 0) + drift(hr + 53, 14),
      ),
    };
  }, [mode, liveSample, t, hourly]);

  // Series for charts. Always show the full real telemetry line so the
  // graph never blanks out when scrubbing into deep history (where we
  // don't have ground-truth samples). The scrubbed value is reflected in
  // the big readout on the top-right of each chart instead. Forecast is
  // hidden during the 3s "predicting…" window.
  const series = useMemo(() => {
    const realPoints = (key: keyof Telemetry) =>
      tele
        .filter((x) => x[key] != null)
        .map((x) => ({
          t: new Date(x.recordedAt).getTime(),
          v: x[key] as number,
        }));
    const fcPoints = (k: "tempC" | "shockG" | "speedKph") =>
      (insight?.forecast ?? []).map((f) => ({
        t: new Date(f.t).getTime(),
        v: f[k],
      }));
    const showForecast = mode !== "past" && !predicting;
    return {
      temp: realPoints("tempC"),
      shock: realPoints("shockG"),
      hum: realPoints("humidity"),
      speed: realPoints("speedKph"),
      fc: {
        temp: showForecast ? fcPoints("tempC") : [],
        shock: showForecast ? fcPoints("shockG") : [],
        speed: showForecast ? fcPoints("speedKph") : [],
      },
    };
  }, [tele, insight, mode, predicting]);

  // Snapshot the latest live sample at the moment we enter future mode so
  // predicted values don't drift as new live telemetry arrives.
  const futureBaseRef = useRef<Telemetry | null>(null);
  useEffect(() => {
    if (mode === "future" && !futureBaseRef.current) {
      futureBaseRef.current = liveSample ?? null;
    }
    if (mode !== "future") {
      futureBaseRef.current = null;
    }
  }, [mode, liveSample]);

  // Deterministic pseudo-random forecast values (seeded by hour bucket) —
  // used so future readouts are stable when re-scrubbed and don't churn.
  const futureReadout = useMemo(() => {
    const base = futureBaseRef.current ?? liveSample;
    if (mode !== "future" || predicting || !base) return null;
    const hr = Math.floor(t / 3_600_000);
    const rand = (s: number) => {
      const x = Math.sin(s * 9301 + 49297) * 233280;
      return x - Math.floor(x);
    };
    const drift = (seed: number, scale: number) => (rand(seed) * 2 - 1) * scale;
    return {
      temp: (base.tempC ?? 0) + drift(hr, 1.4),
      shock: Math.max(0, (base.shockG ?? 0) + drift(hr + 1, 0.25)),
      hum: Math.min(95, Math.max(20, (base.humidity ?? 50) + drift(hr + 2, 6))),
      speed: Math.max(0, (base.speedKph ?? 0) + drift(hr + 3, 12)),
    };
  }, [mode, predicting, liveSample, t]);

  // Final readout values per chart, by mode.
  const readout = (() => {
    if (mode === "live") {
      return {
        temp: liveSample?.tempC,
        shock: liveShockMax,
        hum: liveSample?.humidity ?? undefined,
        speed: liveSample?.speedKph ?? undefined,
      };
    }
    if (mode === "past") {
      return {
        temp: pastReadout?.temp,
        shock: pastReadout?.shock,
        hum: pastReadout?.hum,
        speed: pastReadout?.speed,
      };
    }
    // future
    return {
      temp: futureReadout?.temp,
      shock: futureReadout?.shock,
      hum: futureReadout?.hum,
      speed: futureReadout?.speed,
    };
  })();

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
      <ActionRunner trackingCode={trackingCode} onMutate={mutate} disabled={readOnly}>
        {(run, banner) => (
          <>
            <TopBar
              data={data}
              compromised={!!compromised}
              onDispute={() => run("dispute")}
              onJudge={() => run("judge")}
              readOnly={readOnly}
              showDevicesLink={showDevicesLink}
            />
            {banner}
          </>
        )}
      </ActionRunner>

      <Hero data={data} compromised={!!compromised} />

      <section className="mt-6 grid gap-5 lg:grid-cols-3 lg:[grid-template-rows:1fr]">
        <div className="lg:col-span-2 flex flex-col gap-3">
          <LiveMap shipment={data} scrubTelemetry={scrubTele} />
          <TimelineScrubber
            domainStart={domainStart}
            domainEnd={domainEnd}
            now={now}
            t={t}
            mode={mode}
            onScrub={(ms) => {
              setScrubT(ms);
              setFollow(false);
            }}
            onLive={() => {
              setFollow(true);
              setScrubT(null);
            }}
          />
        </div>
        <div className="lg:h-[calc(460px+74px+12px)] min-h-0">
          <AIInsights
            trackingCode={trackingCode}
            apiBase={base}
            panic={!!compromised}
          />
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
          liveValue={readout.temp}
          mode={mode}
          predicting={predicting}
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
          liveValue={readout.shock}
          mode={mode}
          predicting={predicting}
        />
        <SensorChart
          data={series.hum}
          unit="%"
          label="Humidity"
          accent="violet"
          height={180}
          precision={0}
          panic={!!compromised}
          liveValue={readout.hum}
          mode={mode}
          predicting={predicting}
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
          liveValue={readout.speed}
          mode={mode}
          predicting={predicting}
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
  readOnly = false,
  showDevicesLink = false,
}: {
  data: ShipmentDetail;
  compromised: boolean;
  onDispute: () => void;
  onJudge: () => void;
  readOnly?: boolean;
  showDevicesLink?: boolean;
}) {
  return (
    <div className="sticky top-3 z-30 mb-6 flex items-center gap-3 rounded-full border border-white/[0.06] bg-black/70 px-4 py-2 backdrop-blur-xl">
      <StatusBadge status={data.status} />
      <span className="hidden font-mono text-[10px] uppercase tracking-[0.24em] text-white/35 md:inline">
        {data.trackingCode}
      </span>
      <div className="ml-auto flex items-center gap-2">
        {showDevicesLink && (
          <Link
            href="/devices"
            className="group hidden items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.02] px-3 py-1 font-mono text-[10px] uppercase tracking-[0.28em] text-white/55 transition hover:border-cyan/40 hover:text-cyan sm:inline-flex"
          >
            <Radio className="h-3 w-3" />
            Live devices
          </Link>
        )}
        {readOnly ? (
          <>
            <Link
              href="/"
              className="group inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.02] px-3 py-1 font-mono text-[10px] uppercase tracking-[0.28em] text-white/55 transition hover:border-cyan/40 hover:text-cyan"
            >
              <ArrowLeft className="h-3 w-3" />
              Hub
            </Link>
            <span className="rounded-full border border-white/10 bg-white/[0.02] px-3 py-1 font-mono text-[9px] uppercase tracking-[0.28em] text-white/45">
              External · Read-only
            </span>
          </>
        ) : (
          <>
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
          </>
        )}
      </div>
    </div>
  );
}

// ── Action runner — wires Dispute / Judge to backend with toast ────────

function ActionRunner({
  trackingCode,
  onMutate,
  disabled = false,
  children,
}: {
  trackingCode: string;
  onMutate: () => void;
  disabled?: boolean;
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
    if (busy || disabled) return;
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
      </div>
    </header>
  );
}

// ── Temporal Scrubber ──────────────────────────────────────────────────
// Full-journey timeline. Past = solid track, future = dashed (AI forecast).
// NOW marker is fixed at the present position; the handle can be dragged
// freely across past, present, future. Snapping back to NOW restores live.

function TimelineScrubber({
  domainStart,
  domainEnd,
  now,
  t,
  mode,
  onScrub,
  onLive,
}: {
  domainStart: number;
  domainEnd: number;
  now: number;
  t: number;
  mode: "past" | "live" | "future";
  onScrub: (ms: number) => void;
  onLive: () => void;
}) {
  const span = Math.max(1, domainEnd - domainStart);
  const nowPct = Math.min(100, Math.max(0, ((now - domainStart) / span) * 100));
  const tPct = Math.min(100, Math.max(0, ((t - domainStart) / span) * 100));

  const fmt = (ms: number) =>
    new Date(ms).toLocaleString(undefined, {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  const fmtTick = (ms: number) =>
    new Date(ms).toLocaleString(undefined, { day: "2-digit", month: "short" });

  // 5 evenly-spaced tick marks across the domain
  const ticks = [0, 0.25, 0.5, 0.75, 1].map(
    (k) => domainStart + span * k
  );

  const accent = mode === "future" ? "#A78BFA" : mode === "past" ? "#94A3B8" : "#22D3EE";

  return (
    <div className="relative rounded-2xl border border-white/[0.06] bg-white/[0.015] px-5 pt-5 pb-3">
      {/* Top row: scrubbed timestamp + mode badge + jump to NOW */}
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="font-mono text-[11px] uppercase tracking-[0.28em] text-white/80">
          {fmt(t)}
        </div>
        <div className="flex items-center gap-2">
          <span
            className="rounded-full border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.28em]"
            style={{
              borderColor: `${accent}55`,
              color: accent,
              background: `${accent}10`,
            }}
          >
            {mode === "past" ? "Replay" : mode === "future" ? "AI Forecast" : "Live"}
          </span>
          {mode !== "live" && (
            <button
              onClick={onLive}
              className="rounded-full border border-white/15 bg-white/[0.02] px-2.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.28em] text-white/65 transition hover:border-cyan/60 hover:text-cyan"
            >
              Jump to NOW
            </button>
          )}
        </div>
      </div>

      {/* Track */}
      <div className="relative h-9">
        {/* Solid past line, dashed future line */}
        <div
          className="absolute top-1/2 left-0 h-px -translate-y-1/2"
          style={{
            width: `${nowPct}%`,
            background: "rgba(255,255,255,0.45)",
          }}
        />
        <div
          className="absolute top-1/2 h-px -translate-y-1/2"
          style={{
            left: `${nowPct}%`,
            width: `${100 - nowPct}%`,
            backgroundImage:
              "repeating-linear-gradient(to right, rgba(255,255,255,0.28) 0 4px, transparent 4px 8px)",
          }}
        />

        {/* AI Forecast accent dot (above NOW marker) */}
        <span
          className="absolute h-2 w-2 -translate-x-1/2 rounded-full"
          style={{
            left: `${nowPct}%`,
            top: "calc(50% - 14px)",
            background: "#34D399",
            boxShadow: "0 0 10px rgba(52,211,153,0.85)",
          }}
        />

        {/* NOW vertical guide */}
        <span
          className="absolute top-1/2 h-3 w-px -translate-x-1/2 -translate-y-1/2"
          style={{ left: `${nowPct}%`, background: "rgba(255,255,255,0.55)" }}
        />

        {/* Range slider (transparent, on top of the rendered track) */}
        <input
          type="range"
          min={0}
          max={10000}
          value={Math.round((tPct / 100) * 10000)}
          onChange={(e) => {
            const k = Number(e.target.value) / 10000;
            onScrub(domainStart + span * k);
          }}
          className="vt-scrub-bare absolute inset-0 w-full cursor-pointer"
          style={{ ["--vt-thumb" as string]: accent } as React.CSSProperties}
          aria-label="Timeline scrubber"
        />

        {/* Visible handle (mirrors slider value) */}
        <span
          className="pointer-events-none absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-black"
          style={{
            left: `${tPct}%`,
            background: "#FFFFFF",
            boxShadow: `0 0 14px ${accent}88`,
          }}
        />
      </div>

      {/* Bottom row: tick labels + NOW caption */}
      <div className="relative mt-1 h-4">
        {ticks.map((ms, i) => {
          const pct = [0, 25, 50, 75, 100][i];
          // Anchor edge labels so they sit fully inside the panel: the
          // first label aligns to its left edge, the last to its right
          // edge, the inner three remain centred.
          const transform =
            i === 0
              ? "translateX(0)"
              : i === ticks.length - 1
              ? "translateX(-100%)"
              : "translateX(-50%)";
          return (
            <span
              key={i}
              className="absolute font-mono text-[9px] uppercase tracking-[0.24em] text-white/45"
              style={{ left: `${pct}%`, transform }}
            >
              {fmtTick(ms)}
            </span>
          );
        })}
        <span
          className="absolute -translate-x-1/2 font-mono text-[9px] uppercase tracking-[0.32em] text-white/55"
          style={{ left: `${nowPct}%`, top: 14 }}
        >
          now
        </span>
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

// ── Timeline ────────────────────────────────────────────────────────────

function useMemoEnrichment(events: TimelineEvent[]): TimelineEvent[] {
  return useMemo(() => {
    if (!events || events.length === 0) return [];
    // Collapse consecutive duplicates (e.g. operator spamming Dispute) so
    // the timeline stays clean. Same kind + same message within 90s window
    // → group, keep the latest, append " × N" suffix.
    const collapsed: TimelineEvent[] = [];
    for (const ev of events) {
      const prev = collapsed[collapsed.length - 1];
      const baseMessage = ev.message.replace(/\s+×\s*\d+$/, "");
      const prevBase = prev?.message.replace(/\s+×\s*\d+$/, "");
      const dt = prev
        ? Math.abs(
            new Date(ev.createdAt).getTime() -
              new Date(prev.createdAt).getTime()
          )
        : Infinity;
      if (
        prev &&
        prev.kind === ev.kind &&
        prevBase === baseMessage &&
        dt < 5 * 60_000
      ) {
        const m = (prev.meta as { _count?: number } | null) ?? {};
        const count = (m._count ?? 1) + 1;
        collapsed[collapsed.length - 1] = {
          ...ev,
          message: `${baseMessage} × ${count}`,
          meta: { ...(ev.meta ?? {}), _count: count },
        };
      } else {
        collapsed.push(ev);
      }
    }
    return collapsed;
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
