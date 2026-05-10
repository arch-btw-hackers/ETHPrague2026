// External device proxy routes — surfaces a remote GigaService device under
// the same JSON contract the dashboard already speaks for local shipments.
//
// Endpoints (all read-only):
//   GET  /api/external/devices                    → device list (lite)
//   GET  /api/external/devices/:id                → ShipmentDetail
//   GET  /api/external/devices/:id/insights       → AI insight (uses OpenAI)
//   POST /api/external/devices/:id/chat           → AI chat (Supreme Judge)

import { Router } from "express";
import {
  deviceDetailToShipment,
  getExternalDevice,
  getPragueMalagaRoute,
  listExternalDevices,
  type ExternalLatestReading,
  type MappedShipment,
} from "../services/external";
import { callOpenAI, type AnalysisInput, type Insight } from "../services/insights";
import { runJudgeChat } from "../services/judgechat";
import { renderReportFromData } from "../services/judgechat";

export const externalRouter = Router();

// Tiny in-memory cache so the dashboard's 3s SWR poll doesn't hammer the
// upstream service. Keyed by device id (or "list" for the index).
const SHIP_TTL_MS = 5_000;
const INSIGHT_TTL_MS = 30_000;
const shipCache = new Map<string, { at: number; data: MappedShipment }>();
const listCache = { at: 0, data: [] as Array<Record<string, unknown>> };
const insightCache = new Map<string, { at: number; data: Insight }>();

function passthroughError(res: import("express").Response, e: unknown, fallback: number = 502) {
  const status = (e as { status?: number })?.status ?? fallback;
  const message = (e as { message?: string })?.message ?? "external_unreachable";
  console.warn("[external]", message);
  res.status(status === 200 ? fallback : status).json({
    error: "EXTERNAL_API_ERROR",
    message,
  });
}

externalRouter.get("/devices", async (_req, res) => {
  if (Date.now() - listCache.at < SHIP_TTL_MS && listCache.data.length) {
    return res.json(listCache.data);
  }
  try {
    const list = await listExternalDevices();
    const compact = list.map((d) => ({
      device_id: d.device_id,
      latest_reading: d.latest_reading,
      is_valid: d.is_valid,
      reason: d.reason,
      timestamp: d.timestamp,
      conditions_hash: d.conditions_hash,
      latest_telemetry_hash: d.latest_telemetry_hash,
    }));
    listCache.at = Date.now();
    listCache.data = compact;
    res.json(compact);
  } catch (e) {
    passthroughError(res, e);
  }
});

externalRouter.get("/devices/:id", async (req, res) => {
  const id = req.params.id;
  const cached = shipCache.get(id);
  if (cached && Date.now() - cached.at < SHIP_TTL_MS) {
    return res.json(cached.data);
  }
  try {
    const [detail, summaries, route] = await Promise.all([
      getExternalDevice(id),
      listExternalDevices().catch(() => [] as Awaited<ReturnType<typeof listExternalDevices>>),
      getPragueMalagaRoute(),
    ]);
    const latest: ExternalLatestReading | null =
      summaries.find((s) => s.device_id === id)?.latest_reading ?? null;
    const shipment = deviceDetailToShipment(detail, latest, route);
    shipCache.set(id, { at: Date.now(), data: shipment });
    res.json(shipment);
  } catch (e) {
    passthroughError(res, e, 404);
  }
});

// ── SSE stream proxy ──────────────────────────────────────────────────
//
// Pipes the upstream Server-Sent Events stream
//   GET ${EXTERNAL_API_BASE}/api/v1/dashboard/stream
// (raw `data: <json-array>\n\n` frames every ~0.5s) straight to the browser.
// The browser opens an EventSource on `/api/external/stream` and gets the
// device list pushed in real time without polling.

const EXTERNAL_STREAM_BASE =
  process.env.EXTERNAL_API_BASE ?? "http://80.211.207.162:8000";

externalRouter.get("/stream", async (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache, no-transform");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");
  res.flushHeaders?.();

  const ac = new AbortController();
  req.on("close", () => ac.abort());

  try {
    const upstream = await fetch(
      `${EXTERNAL_STREAM_BASE}/api/v1/dashboard/stream`,
      { signal: ac.signal, headers: { Accept: "text/event-stream" } }
    );
    if (!upstream.ok || !upstream.body) {
      res.write(`event: error\ndata: ${JSON.stringify({ status: upstream.status })}\n\n`);
      return res.end();
    }
    const reader = upstream.body.getReader();
    const decoder = new TextDecoder();
    while (!ac.signal.aborted) {
      const { value, done } = await reader.read();
      if (done) break;
      if (value) res.write(decoder.decode(value, { stream: true }));
    }
  } catch (e) {
    if (!ac.signal.aborted) {
      const message = (e as { message?: string })?.message ?? "stream_error";
      res.write(`event: error\ndata: ${JSON.stringify({ message })}\n\n`);
    }
  } finally {
    res.end();
  }
});

function buildAnalysisInput(shipment: MappedShipment): AnalysisInput {
  // Newest-first window the AI prompt expects.
  const recent = [...shipment.telemetries]
    .reverse()
    .slice(0, 30)
    .map((t) => ({
      tempC: t.tempC,
      shockG: t.shockG,
      humidity: t.humidity,
      battery: t.battery,
      speedKph: t.speedKph,
      recordedAt: t.recordedAt,
    }));
  const events = [...shipment.events].slice(0, 15).map((e) => ({
    kind: e.kind,
    message: e.message,
    createdAt: e.createdAt,
  }));
  const path = shipment.routePath ?? [];
  const routeAhead: [number, number][] = [];
  if (path.length > 0) {
    const remaining = Math.max(1, path.length - 1 - shipment.routeIndex);
    const stride = Math.max(1, Math.floor(remaining / 12));
    for (let i = 1; i <= 12; i++) {
      const idx = Math.min(path.length - 1, shipment.routeIndex + i * stride);
      routeAhead.push(path[idx]);
    }
  }
  return {
    trackingCode: shipment.trackingCode,
    asset: shipment.asset,
    origin: shipment.origin,
    destination: shipment.destination,
    status: shipment.status,
    maxTempC: shipment.maxTempC,
    maxShockG: shipment.maxShockG,
    etaAt: shipment.etaAt,
    recent,
    events,
    routeAhead,
  };
}

externalRouter.get("/devices/:id/insights", async (req, res) => {
  const id = req.params.id;
  const force = req.query.force === "1";
  const cached = insightCache.get(id);
  if (!force && cached && Date.now() - cached.at < INSIGHT_TTL_MS) {
    return res.json(cached.data);
  }
  try {
    const [detail, summaries, route] = await Promise.all([
      getExternalDevice(id),
      listExternalDevices().catch(() => [] as Awaited<ReturnType<typeof listExternalDevices>>),
      getPragueMalagaRoute(),
    ]);
    const latest: ExternalLatestReading | null =
      summaries.find((s) => s.device_id === id)?.latest_reading ?? null;
    const shipment = deviceDetailToShipment(detail, latest, route);
    const insight = await callOpenAI(buildAnalysisInput(shipment));
    insightCache.set(id, { at: Date.now(), data: insight });
    res.json(insight);
  } catch (e) {
    passthroughError(res, e);
  }
});

externalRouter.post("/devices/:id/chat", async (req, res) => {
  const id = req.params.id;
  const question = String(req.body?.question ?? "").trim();
  if (!question) return res.status(400).json({ error: "EMPTY" });
  const history = Array.isArray(req.body?.history) ? req.body.history : [];
  try {
    const [detail, summaries, route] = await Promise.all([
      getExternalDevice(id),
      listExternalDevices().catch(() => [] as Awaited<ReturnType<typeof listExternalDevices>>),
      getPragueMalagaRoute(),
    ]);
    const latest: ExternalLatestReading | null =
      summaries.find((s) => s.device_id === id)?.latest_reading ?? null;
    const shipment = deviceDetailToShipment(detail, latest, route);
    const last = shipment.telemetries[shipment.telemetries.length - 1];
    const facts =
      `External device ${shipment.trackingCode}\n` +
      `Status ${shipment.status} · samples ${shipment.telemetries.length}\n` +
      `Thresholds: maxTemp ${shipment.maxTempC}°C · maxShock ${shipment.maxShockG}G\n` +
      (last
        ? `Latest sample @ ${last.recordedAt}: T=${last.tempC.toFixed(1)}°C · ` +
          `G=${last.shockG.toFixed(2)} · GPS ${last.lat ?? "-"},${last.lng ?? "-"}\n`
        : "No telemetry yet.\n") +
      `Recent events:\n${shipment.events
        .slice(0, 6)
        .map((e) => `  · ${e.kind}: ${e.message}`)
        .join("\n") || "  · none"}`;
    const result = await runJudgeChat(facts, question.slice(0, 600), history);
    res.json(result);
  } catch (e) {
    passthroughError(res, e);
  }
});

// Forensic PDF report — same template the local shipments use, fed by the
// external (proxied) shipment + a fresh AI insight (or cached one).
externalRouter.get("/devices/:id/report.pdf", async (req, res) => {
  const id = req.params.id;
  try {
    const [detail, summaries, route] = await Promise.all([
      getExternalDevice(id),
      listExternalDevices().catch(() => [] as Awaited<ReturnType<typeof listExternalDevices>>),
      getPragueMalagaRoute(),
    ]);
    const latest: ExternalLatestReading | null =
      summaries.find((s) => s.device_id === id)?.latest_reading ?? null;
    const shipment = deviceDetailToShipment(detail, latest, route);

    const cachedInsight = insightCache.get(id);
    const insight: Insight =
      cachedInsight && Date.now() - cachedInsight.at < INSIGHT_TTL_MS
        ? cachedInsight.data
        : await callOpenAI(buildAnalysisInput(shipment));
    if (!cachedInsight || Date.now() - cachedInsight.at >= INSIGHT_TTL_MS) {
      insightCache.set(id, { at: Date.now(), data: insight });
    }

    // Newest-first telemetries (last ~120) for the PDF envelope/sparklines.
    const telemetries = [...shipment.telemetries]
      .reverse()
      .slice(0, 120)
      .map((t) => ({
        tempC: t.tempC,
        shockG: t.shockG,
        lat: t.lat,
        lng: t.lng,
        recordedAt: t.recordedAt,
      }));

    const buf = await renderReportFromData(
      {
        trackingCode: shipment.trackingCode,
        asset: shipment.asset,
        origin: shipment.origin,
        destination: shipment.destination,
        status: shipment.status,
        maxTempC: shipment.maxTempC,
        maxShockG: shipment.maxShockG,
        contractAddress: shipment.contractAddress,
        chainId: shipment.chainId,
        payerAddress: shipment.payerAddress,
        carrierAddress: shipment.carrierAddress,
        telemetries,
      },
      insight
    );
    res.setHeader("content-type", "application/pdf");
    res.setHeader(
      "content-disposition",
      `inline; filename="vibetrack-${shipment.trackingCode}.pdf"`
    );
    res.send(buf);
  } catch (e) {
    console.error("[external-report]", e);
    passthroughError(res, e);
  }
});
