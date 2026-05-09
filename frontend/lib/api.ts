// Shared types mirroring the Prisma models the dashboard cares about.
export type ShipmentStatus = "IN_TRANSIT" | "COMPROMISED" | "DELIVERED";

export interface Telemetry {
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

export interface TimelineEvent {
  id: string;
  kind: string;
  violation: string | null;
  message: string;
  meta: Record<string, unknown> | null;
  createdAt: string;
}

export interface RefundTx {
  id: string;
  contractAddress: string;
  chainId: number;
  method: string;
  reason: string;
  judgeVerdict: "APPROVE" | "REJECT" | null;
  judgeNotes: string | null;
  broadcastTxHash: string | null;
  createdAt: string;
}

export interface ShipmentDetail {
  id: string;
  trackingCode: string;
  asset: string;
  origin: string;
  destination: string;
  status: ShipmentStatus;
  contractAddress: string | null;
  chainId: number | null;
  payerAddress: string | null;
  carrierAddress: string | null;
  maxTempC: number;
  minTempC: number;
  maxShockG: number;
  geofence: { lat: number; lng: number; radiusKm: number } | null;
  routePath: [number, number][] | null;
  routeIndex: number;
  etaAt: string | null;
  telemetries: Telemetry[];
  events: TimelineEvent[];
  refundTx: RefundTx | null;
  device: { serial: string; lastSeenAt: string | null } | null;
  updatedAt: string;
}

export interface ForecastPoint {
  t: string;
  tempC: number;
  shockG: number;
  speedKph: number;
}

export interface Insight {
  riskScore: number;
  riskLabel: "LOW" | "MODERATE" | "ELEVATED" | "CRITICAL";
  etaConfidence: number;
  etaIso: string | null;
  headline: string;
  summary: string;
  anomalies: string[];
  recommendations: string[];
  forecast: ForecastPoint[];
  forecastNote: string;
  generatedAt: string;
  model: string;
}

export const fetcher = async (url: string) => {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
};
