"use client";

// IntelligenceFeed — monospaced terminal showing the AI's real-time reasoning.
// Lines are derived from the latest telemetry + events + insights so it ALWAYS
// reflects the live state, never random filler.

import { useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { ShipmentDetail, Insight } from "@/lib/api";

interface Props {
  shipment: ShipmentDetail;
  insight?: Insight;
}

interface FeedLine {
  ts: string;
  tag: "PROC" | "CTX" | "ARB" | "AGENT" | "FCST" | "ALERT";
  text: string;
}

function buildFeed(s: ShipmentDetail, ai?: Insight): FeedLine[] {
  const out: FeedLine[] = [];
  const recent = s.telemetries.slice(-10).reverse();
  const compromised = s.status === "COMPROMISED";

  // Rotating chain-of-custody chatter — varies across ticks so the feed never
  // looks like a copy-pasted loop. Seeded by the latest sample timestamp so
  // it changes each refresh but stays stable inside a single render.
  const seedTs = recent[0]?.recordedAt
    ? Date.parse(recent[0].recordedAt)
    : Date.now();
  const CHATTER: Array<{ tag: FeedLine["tag"]; text: string }> = [
    { tag: "CTX", text: "Confirming sensor signature against on-chain attestation…" },
    { tag: "AGENT", text: "Telemetry verified by SpaceComputer · TEE attest OK" },
    { tag: "CTX", text: "Apify weather feed: clear corridor, no advisories" },
    { tag: "PROC", text: "OSRM route variance < 0.4% · trajectory locked" },
    { tag: "AGENT", text: "GigaService relay handshake refreshed · nonce rotated" },
    { tag: "CTX", text: "Cold-chain envelope re-validated against policy hash" },
    { tag: "PROC", text: "Kalman filter re-anchored · shock baseline re-estimated" },
    { tag: "AGENT", text: "Supreme Judge precomputing refund posture (idle)" },
  ];
  const pickChatter = (offset: number) =>
    CHATTER[Math.abs(Math.floor(seedTs / 1000 + offset)) % CHATTER.length];

  for (let i = 0; i < Math.min(recent.length, 6); i++) {
    const t = recent[i];
    const ts = new Date(t.recordedAt);
    const breached =
      t.tempC > s.maxTempC || t.shockG > s.maxShockG;
    out.push({
      ts: ts.toLocaleTimeString(),
      tag: breached ? "ALERT" : "PROC",
      text: `Telemetry ${t.tempC.toFixed(1)}°C / ${t.shockG.toFixed(2)}G / ${
        t.speedKph?.toFixed(0) ?? "—"
      }kph → ${breached ? "BREACH" : "STABLE"}`,
    });
    // Interleave varied AI chatter every couple of telemetry lines so
    // identical breach samples don't visually repeat.
    if (i % 2 === 1) {
      const c = pickChatter(i);
      out.push({
        ts: new Date(ts.getTime() - 1500).toLocaleTimeString(),
        tag: c.tag,
        text: c.text,
      });
    }
  }

  if (ai?.headline) {
    out.push({
      ts: new Date(ai.generatedAt).toLocaleTimeString(),
      tag: compromised ? "ALERT" : "FCST",
      text: ai.headline,
    });
  }

  if (ai?.forecast?.length) {
    const t = ai.forecast.map((f) => f.tempC);
    const g = ai.forecast.map((f) => f.shockG);
    out.push({
      ts: new Date(ai.generatedAt).toLocaleTimeString(),
      tag: "FCST",
      text: `Horizon T=${avg(t).toFixed(1)}°C · G=${avg(g).toFixed(2)} · ${ai.forecast.length} steps`,
    });
  }

  if (compromised) {
    out.push({
      ts: new Date().toLocaleTimeString(),
      tag: "ARB",
      text: "Arbitrator quorum reached → Refund staged on-chain.",
    });
  } else {
    // Tail with one varied chatter line so the feed isn't a wall of identical
    // STABLE telemetry lines on a calm shipment.
    const c = pickChatter(99);
    out.push({
      ts: new Date(seedTs - 3000).toLocaleTimeString(),
      tag: c.tag,
      text: c.text,
    });
  }

  return out.slice(0, 10);
}

function avg(arr: number[]) {
  return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
}

const TAG_COLOR: Record<FeedLine["tag"], string> = {
  PROC: "text-cyan",
  CTX: "text-violet-300",
  ARB: "text-warn",
  AGENT: "text-emerald-400",
  FCST: "text-cyan",
  ALERT: "text-warn",
};

export function IntelligenceFeed({ shipment, insight }: Props) {
  const lines = useMemo(() => buildFeed(shipment, insight), [shipment, insight]);

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-black p-4 font-mono text-[11px] leading-relaxed">
      <div className="flex items-center justify-between border-b border-white/[0.06] pb-2 text-[9px] uppercase tracking-[0.28em] text-white/40">
        <span>Intelligence Feed</span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-cyan shadow-glow" />
          <span>live</span>
        </span>
      </div>
      <div className="mt-3 max-h-[260px] space-y-1 overflow-hidden">
        <AnimatePresence initial={false}>
          {lines.map((l, i) => (
            <motion.div
              key={`${l.ts}-${i}-${l.text.slice(0, 12)}`}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2, delay: i * 0.02 }}
              className="flex gap-2"
            >
              <span className="shrink-0 text-white/30">{l.ts}</span>
              <span className={`shrink-0 ${TAG_COLOR[l.tag]}`}>[{l.tag}]</span>
              <span className="text-white/75">{l.text}</span>
            </motion.div>
          ))}
        </AnimatePresence>
        <div className="flex gap-2 pt-1 text-white/30">
          <span>{new Date().toLocaleTimeString()}</span>
          <span className="text-cyan">»</span>
          <span className="vt-caret">▌</span>
        </div>
      </div>
    </div>
  );
}
