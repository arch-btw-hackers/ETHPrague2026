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
  listExternalDevices,
  type MappedShipment,
} from "../services/external";
import { callOpenAI, type AnalysisInput, type Insight } from "../services/insights";
import { runJudgeChat } from "../services/judgechat";

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
    const detail = await getExternalDevice(id);
    const shipment = deviceDetailToShipment(detail);
    shipCache.set(id, { at: Date.now(), data: shipment });
    res.json(shipment);
  } catch (e) {
    passthroughError(res, e, 404);
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
    const detail = await getExternalDevice(id);
    const shipment = deviceDetailToShipment(detail);
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
    const detail = await getExternalDevice(id);
    const shipment = deviceDetailToShipment(detail);
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
