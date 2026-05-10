// External device proxy.
//
// Wraps the GigaService API at EXTERNAL_API_BASE (default
// http://80.211.207.162:8000) and remaps its `DeviceSummary` /
// `DeviceDetail` shapes onto the dashboard's `ShipmentDetail` shape so
// the existing UI components render real device telemetry without
// modification.
//
// Mapping notes:
//   - `temp_c`                 → tempC
//   - `acceleration_overload`  → shockG (already in g-force)
//   - `lat` / `lon`            → lat / lng
//   - `is_valid` (per record)  → drives status (any false → COMPROMISED)
//   - `timestamp`              → recordedAt (ISO)
//   - routePath is synthesised from telemetry coordinates so the LiveMap
//     has something to draw; if no coordinates exist we fall back to a
//     point near the latest reading or null.

const EXTERNAL_API_BASE =
  process.env.EXTERNAL_API_BASE ?? "http://80.211.207.162:8000";
const EXTERNAL_PATH = "/api/v1/dashboard/devices";
const HISTORY_LIMIT = 200;

export interface ExternalLatestReading {
  temp_c: number | null;
  acceleration_overload: number | null;
  lat: number | null;
  lon: number | null;
}

export interface ExternalDeviceSummary {
  device_id: string;
  conditions_hash: string | null;
  latest_telemetry_hash: string | null;
  latest_reading: ExternalLatestReading | null;
  is_valid: boolean | null;
  reason: string | null;
  timestamp: string | null;
  nonce: string | null;
}

export interface ExternalTelemetryRecord {
  device_id: string;
  nonce: string | null;
  temp_c: number | null;
  acceleration_overload: number | null;
  lat: number | null;
  lon: number | null;
  is_valid: boolean | null;
  reason: string | null;
  timestamp: string | null;
  swarm_hash: string | null;
}

export interface ExternalDeviceDetail {
  device_id: string;
  conditions_hash: string | null;
  latest_telemetry_hash: string | null;
  history: ExternalTelemetryRecord[];
}

async function fetchJson<T>(path: string): Promise<T> {
  const url = `${EXTERNAL_API_BASE}${path}`;
  const r = await fetch(url, {
    headers: { accept: "application/json" },
    // Keep this snappy — the external service occasionally stalls.
    signal: AbortSignal.timeout(8000),
  });
  if (!r.ok) {
    throw Object.assign(new Error(`external ${r.status}`), { status: r.status });
  }
  return (await r.json()) as T;
}

export async function listExternalDevices(): Promise<ExternalDeviceSummary[]> {
  return fetchJson<ExternalDeviceSummary[]>(EXTERNAL_PATH);
}

export async function getExternalDevice(
  deviceId: string,
  limit = HISTORY_LIMIT
): Promise<ExternalDeviceDetail> {
  return fetchJson<ExternalDeviceDetail>(
    `${EXTERNAL_PATH}/${encodeURIComponent(deviceId)}?limit=${limit}`
  );
}

// ---------------------------------------------------------------------------
// Remap to ShipmentDetail-compatible shape
// ---------------------------------------------------------------------------

interface ShipmentTelemetry {
  id: string;
  tempC: number;
  shockG: number;
  humidity: number | null;
  tilt: number | null;
  speedKph: number | null;
  lat: number | null;
  lng: number | null;
  battery: number | null;
  recordedAt: string;
}

interface ShipmentEvent {
  id: string;
  kind: string;
  violation: string | null;
  message: string;
  meta: Record<string, unknown> | null;
  createdAt: string;
}

export interface MappedShipment {
  id: string;
  trackingCode: string;
  asset: string;
  origin: string;
  destination: string;
  status: "IN_TRANSIT" | "COMPROMISED" | "DELIVERED";
  contractAddress: string | null;
  chainId: number | null;
  payerAddress: string | null;
  carrierAddress: string | null;
  maxTempC: number;
  minTempC: number;
  maxShockG: number;
  geofence: null;
  routePath: [number, number][] | null;
  routeIndex: number;
  etaAt: string | null;
  telemetries: ShipmentTelemetry[];
  events: ShipmentEvent[];
  refundTx: null;
  device: { serial: string; lastSeenAt: string | null } | null;
  updatedAt: string;
  /** Marker so the frontend knows this is an external (read-only) device. */
  source: "external";
}

const DEFAULT_MAX_TEMP_C = 25;
const DEFAULT_MIN_TEMP_C = -10;
const DEFAULT_MAX_SHOCK_G = 2;

function safeNum(v: unknown): number | null {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function ensureIsoTimestamp(input: string | null | undefined, fallback: number): string {
  if (!input) return new Date(fallback).toISOString();
  const t = Date.parse(input);
  if (Number.isFinite(t)) return new Date(t).toISOString();
  return new Date(fallback).toISOString();
}

export function deviceDetailToShipment(
  detail: ExternalDeviceDetail
): MappedShipment {
  // External history typically arrives newest-first. The dashboard expects
  // telemetry in chronological order (oldest → newest).
  const history = [...detail.history].sort((a, b) => {
    const ta = a.timestamp ? Date.parse(a.timestamp) : 0;
    const tb = b.timestamp ? Date.parse(b.timestamp) : 0;
    return ta - tb;
  });

  const now = Date.now();
  const telemetries: ShipmentTelemetry[] = history.map((r, i) => {
    const recordedAt = ensureIsoTimestamp(r.timestamp, now - (history.length - i) * 60_000);
    return {
      id: r.swarm_hash ?? `${detail.device_id}-${i}`,
      tempC: safeNum(r.temp_c) ?? 0,
      shockG: safeNum(r.acceleration_overload) ?? 0,
      humidity: null,
      tilt: null,
      speedKph: null,
      lat: safeNum(r.lat),
      lng: safeNum(r.lon),
      battery: null,
      recordedAt,
    };
  });

  // Build route path from any GPS-tagged telemetry. This gives the LiveMap a
  // line to draw and lets the temporal scrubber project past/future
  // positions onto something physically sensible.
  const geoPoints: [number, number][] = telemetries
    .filter((t) => t.lat != null && t.lng != null)
    .map((t) => [t.lng as number, t.lat as number]);
  const routePath = geoPoints.length >= 2 ? geoPoints : null;
  const routeIndex = routePath ? routePath.length - 1 : 0;

  const events: ShipmentEvent[] = history
    .filter((r) => r.is_valid === false || (r.reason && r.reason !== "ok"))
    .slice(-20)
    .map((r, i) => ({
      id: `${detail.device_id}-event-${i}`,
      kind: r.is_valid === false ? "VIOLATION" : "NOTE",
      violation: r.is_valid === false ? r.reason ?? "policy" : null,
      message: r.reason ?? "Telemetry flagged",
      meta: { swarm_hash: r.swarm_hash, nonce: r.nonce },
      createdAt: ensureIsoTimestamp(r.timestamp, now),
    }))
    .reverse();

  // A single recent invalid sample flips the whole shipment to COMPROMISED so
  // the existing dashboard panic styling kicks in.
  const recentlyInvalid = history.slice(-5).some((r) => r.is_valid === false);
  const status = recentlyInvalid ? "COMPROMISED" : "IN_TRANSIT";

  const last = telemetries[telemetries.length - 1];
  const lastSeenAt = last ? last.recordedAt : null;

  return {
    id: detail.device_id,
    trackingCode: detail.device_id,
    asset: detail.device_id,
    origin: "Field tracker",
    destination: "Live route",
    status,
    contractAddress: null,
    chainId: null,
    payerAddress: null,
    carrierAddress: null,
    maxTempC: DEFAULT_MAX_TEMP_C,
    minTempC: DEFAULT_MIN_TEMP_C,
    maxShockG: DEFAULT_MAX_SHOCK_G,
    geofence: null,
    routePath,
    routeIndex,
    etaAt: null,
    telemetries,
    events,
    refundTx: null,
    device: {
      serial: detail.device_id,
      lastSeenAt,
    },
    updatedAt: lastSeenAt ?? new Date(now).toISOString(),
    source: "external",
  };
}
