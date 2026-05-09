// AI Insights — calls OpenAI to summarise shipment health, predict future
// telemetry, and produce risk/ETA assessment.
//
// The dashboard polls /api/shipments/:code/insights and gets back a strict
// JSON shape: gauge, headline, summary, anomalies, recommendations, AND a
// forecast block with future tempC / shockG / speedKph values so the charts
// can render a "ghost" predicted curve beyond the live tail.
//
// If OPENAI_API_KEY is missing OR the network call fails, we fall back to a
// deterministic heuristic so the UI never blanks in dev / offline.

import { prisma } from "../db";

export interface ForecastPoint {
  /** ISO timestamp of the predicted sample. */
  t: string;
  tempC: number;
  shockG: number;
  speedKph: number;
}

export interface Insight {
  riskScore: number; // 0..100
  riskLabel: "LOW" | "MODERATE" | "ELEVATED" | "CRITICAL";
  etaConfidence: number; // 0..100
  etaIso: string | null;
  headline: string;
  summary: string;
  anomalies: string[];
  recommendations: string[];
  /** Forward-looking trace, ~12 points, ~24 minutes ahead at 2-min spacing. */
  forecast: ForecastPoint[];
  /** AI commentary on the forecast (one short sentence). */
  forecastNote: string;
  generatedAt: string;
  model: string;
}

const cache = new Map<string, { at: number; data: Insight }>();
const TTL_MS = 30_000;

const FORECAST_HORIZON = 12;
const FORECAST_STEP_MS = 2 * 60 * 1000;

const SYSTEM_PROMPT = `You are the Supreme Judge for a high-value RWA logistics platform.
You analyse cold-chain telemetry, score risk, and forecast the next 12 samples.
Respond with STRICT JSON ONLY. No markdown. No prose outside the JSON.

Schema (TypeScript):
{
  riskScore: number,            // 0 (perfect) to 100 (catastrophic)
  riskLabel: "LOW" | "MODERATE" | "ELEVATED" | "CRITICAL",
  etaConfidence: number,        // 0..100
  headline: string,             // <= 60 chars, no emojis
  summary: string,              // 1-2 calm factual sentences
  anomalies: string[],          // up to 3 short bullets
  recommendations: string[],    // up to 3 short imperative bullets
  forecast: { tempC: number, shockG: number, speedKph: number }[], // exactly 12 entries
  forecastNote: string          // one short sentence about the trend
}

Forecast rules:
- Continue the recent trend smoothly. No sudden jumps unless events imply one.
- Stay within physically plausible bounds (temp 0..15°C cold chain, shockG 0..6, speed 0..130 km/h).
- If status is COMPROMISED, anomalies/recommendations must reflect breach handling.`;

interface AnalysisInput {
  trackingCode: string;
  asset: string;
  origin: string;
  destination: string;
  status: string;
  maxTempC: number;
  maxShockG: number;
  etaAt: string | null;
  recent: {
    tempC: number;
    shockG: number;
    humidity: number | null;
    battery: number | null;
    speedKph: number | null;
    recordedAt: string;
  }[];
  events: { kind: string; message: string; createdAt: string }[];
  /** Up to 12 forward route points [lng, lat], one per forecast step. */
  routeAhead: [number, number][];
}

// Geographic context — enables true predictive analytics rather than blind extrapolation.
function geoContext(p: [number, number] | undefined) {
  if (!p) return { tempDelta: 0, shockBias: 0, label: "" };
  const [lng, lat] = p;
  // Pyrenees crossing — significant altitude → temperature drop.
  if (lat > 42.0 && lat < 43.4 && lng > -1.0 && lng < 3.0) {
    return { tempDelta: -2.6, shockBias: 0.25, label: "Pyrenees crossing" };
  }
  // Massif Central / Auvergne plateau — moderate altitude.
  if (lat > 44.5 && lat < 46.0 && lng > 2.5 && lng < 4.5) {
    return { tempDelta: -1.2, shockBias: 0.10, label: "Massif Central" };
  }
  // Catalan coast & Andalusian valleys — warmer, smooth highway.
  if (lat < 38.0 && lng < 0) {
    return { tempDelta: 1.8, shockBias: -0.05, label: "Andalusian valley" };
  }
  return { tempDelta: 0, shockBias: 0, label: "" };
}

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, isFinite(n) ? n : 0));
}

function stampForecast(
  base: { tempC: number; shockG: number; speedKph: number }[]
): ForecastPoint[] {
  const start = Date.now();
  return base.slice(0, FORECAST_HORIZON).map((p, i) => ({
    t: new Date(start + (i + 1) * FORECAST_STEP_MS).toISOString(),
    tempC: clamp(Number(p.tempC), -10, 30),
    shockG: clamp(Number(p.shockG), 0, 8),
    speedKph: clamp(Number(p.speedKph), 0, 160),
  }));
}

function heuristicForecast(input: AnalysisInput): ForecastPoint[] {
  const window = input.recent.slice(0, 8);
  if (window.length === 0) {
    return stampForecast(
      Array.from({ length: FORECAST_HORIZON }, () => ({
        tempC: 4,
        shockG: 0.4,
        speedKph: 80,
      }))
    );
  }
  const avg = (key: "tempC" | "shockG" | "speedKph") => {
    const vals = window.map((s) => Number(s[key] ?? 0));
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  };
  const slope = (key: "tempC" | "shockG" | "speedKph") => {
    if (window.length < 2) return 0;
    const last = Number(window[0][key] ?? 0);
    const first = Number(window[window.length - 1][key] ?? 0);
    return (last - first) / window.length;
  };
  const baseT = avg("tempC");
  const baseG = avg("shockG");
  const baseV = avg("speedKph");
  const dT = slope("tempC");
  const dG = slope("shockG");
  const dV = slope("speedKph");
  const out: { tempC: number; shockG: number; speedKph: number }[] = [];
  for (let i = 1; i <= FORECAST_HORIZON; i++) {
    const ctx = geoContext(input.routeAhead[i - 1]);
    // Smooth ramp into the geographic effect so the curve doesn't cliff.
    const ramp = Math.min(1, i / 4);
    out.push({
      tempC: baseT + dT * i + Math.sin(i / 3) * 0.4 + ctx.tempDelta * ramp,
      shockG: Math.max(
        0,
        baseG + dG * i * 0.5 + (Math.random() - 0.5) * 0.1 + ctx.shockBias * ramp
      ),
      speedKph: Math.max(0, baseV + dV * i + Math.sin(i / 2) * 4),
    });
  }
  return stampForecast(out);
}

function heuristicFallback(input: AnalysisInput): Insight {
  const tempBreach = input.recent.filter((s) => s.tempC > input.maxTempC).length;
  const shockBreach = input.recent.filter((s) => s.shockG > input.maxShockG).length;
  const breaches = tempBreach + shockBreach;
  const score = Math.min(
    100,
    breaches * 12 + (input.status === "COMPROMISED" ? 60 : 0)
  );
  const label: Insight["riskLabel"] =
    score >= 70 ? "CRITICAL" : score >= 40 ? "ELEVATED" : score >= 15 ? "MODERATE" : "LOW";
  const forecast = heuristicForecast(input);
  return {
    riskScore: score,
    riskLabel: label,
    etaConfidence: input.status === "COMPROMISED" ? 35 : 88,
    etaIso: input.etaAt,
    headline:
      input.status === "COMPROMISED"
        ? "Shipment integrity violated"
        : "All metrics within bounds",
    summary:
      input.status === "COMPROMISED"
        ? `Detected ${breaches} threshold breach(es) across recent samples. Refund pathway armed.`
        : "Telemetry stable. Cold-chain and shock envelope nominal.",
    anomalies:
      breaches > 0
        ? [
            `${tempBreach} temperature excursion(s)`,
            `${shockBreach} shock event(s) above ${input.maxShockG}G`,
          ].filter(Boolean)
        : [],
    recommendations:
      input.status === "COMPROMISED"
        ? [
            "Trigger Supreme Judge review",
            "Notify payer & carrier",
            "Hold final delivery handoff",
          ]
        : ["Maintain current handling profile"],
    forecast,
    forecastNote:
      input.status === "COMPROMISED"
        ? "Forecast assumes continued breach pressure — review urgently."
        : "Trend stable; expected curve mirrors current envelope.",
    generatedAt: new Date().toISOString(),
    model: "heuristic",
  };
}

async function callOpenAI(input: AnalysisInput): Promise<Insight> {
  const key = process.env.OPENAI_API_KEY;
  if (!key) return heuristicFallback(input);

  const model = process.env.OPENAI_MODEL ?? "gpt-4o-mini";

  const ctxLabels = input.routeAhead
    .map((p, i) => ({ i, ...geoContext(p) }))
    .filter((c) => c.label)
    .slice(0, 4)
    .map((c) => `step ${c.i + 1} → ${c.label} (Δtemp ${c.tempDelta}°C, Δshock ${c.shockBias}G)`)
    .join("; ");

  const userPrompt = `Shipment ${input.trackingCode} · ${input.asset}
Route       : ${input.origin} → ${input.destination}
Status      : ${input.status}
Thresholds  : maxTemp ${input.maxTempC}°C · maxShock ${input.maxShockG}G
ETA target  : ${input.etaAt ?? "unset"}
Geo context : ${ctxLabels || "flat highway"}

Recent samples (newest first, max 20):
${input.recent
  .slice(0, 20)
  .map(
    (s) =>
      `  ${s.recordedAt}  T=${s.tempC.toFixed(1)}°C  G=${s.shockG.toFixed(2)}  ` +
      `H=${s.humidity?.toFixed(0) ?? "-"}%  V=${s.speedKph?.toFixed(0) ?? "-"}kph  bat=${s.battery?.toFixed(0) ?? "-"}%`
  )
  .join("\n")}

Events (newest first, max 10):
${input.events
  .slice(0, 10)
  .map((e) => `  [${e.createdAt}] ${e.kind}: ${e.message}`)
  .join("\n")}

Produce the JSON described in the system prompt. The forecast array MUST contain exactly 12 entries.`;

  try {
    const r = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${key}`,
      },
      body: JSON.stringify({
        model,
        temperature: 0.2,
        response_format: { type: "json_object" },
        messages: [
          { role: "system", content: SYSTEM_PROMPT },
          { role: "user", content: userPrompt },
        ],
      }),
    });
    if (!r.ok) {
      console.warn("[insights] OpenAI HTTP", r.status, await r.text());
      return heuristicFallback(input);
    }
    const data = await r.json();
    const raw = data.choices?.[0]?.message?.content;
    if (!raw) return heuristicFallback(input);
    const parsed = JSON.parse(raw);

    const forecast = Array.isArray(parsed.forecast)
      ? stampForecast(parsed.forecast.slice(0, FORECAST_HORIZON))
      : heuristicForecast(input);

    return {
      riskScore: clamp(Number(parsed.riskScore ?? 0), 0, 100),
      riskLabel: ["LOW", "MODERATE", "ELEVATED", "CRITICAL"].includes(
        parsed.riskLabel
      )
        ? parsed.riskLabel
        : "LOW",
      etaConfidence: clamp(Number(parsed.etaConfidence ?? 50), 0, 100),
      etaIso: input.etaAt,
      headline: String(parsed.headline ?? "").slice(0, 80) || "Telemetry analysed",
      summary: String(parsed.summary ?? ""),
      anomalies: Array.isArray(parsed.anomalies)
        ? parsed.anomalies.slice(0, 5).map(String)
        : [],
      recommendations: Array.isArray(parsed.recommendations)
        ? parsed.recommendations.slice(0, 5).map(String)
        : [],
      forecast,
      forecastNote: String(parsed.forecastNote ?? "").slice(0, 140),
      generatedAt: new Date().toISOString(),
      model,
    };
  } catch (e) {
    console.warn("[insights] error, falling back", e);
    return heuristicFallback(input);
  }
}

export async function getInsight(
  shipmentId: string,
  force = false
): Promise<Insight> {
  const cached = cache.get(shipmentId);
  if (!force && cached && Date.now() - cached.at < TTL_MS) return cached.data;

  const shipment = await prisma.shipment.findUniqueOrThrow({
    where: { id: shipmentId },
    include: {
      telemetries: { orderBy: { recordedAt: "desc" }, take: 30 },
      events: { orderBy: { createdAt: "desc" }, take: 15 },
    },
  });

  const path = (shipment.routePath as [number, number][] | null) ?? [];
  const routeAhead: [number, number][] = [];
  if (path.length > 0) {
    // Pull 12 evenly-spaced lookaheads, ~equivalent to the forecast horizon.
    const remaining = path.length - 1 - shipment.routeIndex;
    const stride = Math.max(1, Math.floor(remaining / FORECAST_HORIZON));
    for (let i = 1; i <= FORECAST_HORIZON; i++) {
      const idx = Math.min(path.length - 1, shipment.routeIndex + i * stride);
      routeAhead.push(path[idx]);
    }
  }

  const insight = await callOpenAI({
    trackingCode: shipment.trackingCode,
    asset: shipment.asset,
    origin: shipment.origin,
    destination: shipment.destination,
    status: shipment.status,
    maxTempC: shipment.maxTempC,
    maxShockG: shipment.maxShockG,
    etaAt: shipment.etaAt?.toISOString() ?? null,
    recent: shipment.telemetries.map((t) => ({
      tempC: t.tempC,
      shockG: t.shockG,
      humidity: t.humidity,
      battery: t.battery,
      speedKph: t.speedKph,
      recordedAt: t.recordedAt.toISOString(),
    })),
    events: shipment.events.map((e) => ({
      kind: e.kind,
      message: e.message,
      createdAt: e.createdAt.toISOString(),
    })),
    routeAhead,
  });

  cache.set(shipmentId, { at: Date.now(), data: insight });
  return insight;
}
