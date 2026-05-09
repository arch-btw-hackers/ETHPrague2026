// VibeTrack Arbitrator v2 — deterministic violation engine + Refund Staging.
//
// Rules (Smart Contract conditions):
//   - Temperature > shipment.maxTempC  →  TEMPERATURE_HIGH
//   - Temperature < shipment.minTempC  →  TEMPERATURE_LOW
//   - Shock G    > shipment.maxShockG  →  SHOCK
//   - Outside geofence radius          →  GEOFENCE
//
// On any violation:
//   1. Append one Event per breach (kind = VIOLATION).
//   2. Flip Shipment.status → COMPROMISED (one-way from IN_TRANSIT).
//   3. Stage RefundTx (idempotent upsert) — the on-chain payload an external
//      signer or the Supreme Judge agent will broadcast.
//   4. Append a REFUND_STAGED event so the timeline surfaces the staked-funds
//      pathway.

import type { Shipment, Telemetry } from "@prisma/client";
import { prisma } from "../db";

export type Violation = {
  kind: "TEMPERATURE_HIGH" | "TEMPERATURE_LOW" | "SHOCK" | "GEOFENCE";
  message: string;
  observed: number;
  threshold: number;
};

function distanceKm(
  a: { lat: number; lng: number },
  b: { lat: number; lng: number }
) {
  const R = 6371;
  const toRad = (x: number) => (x * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

export function evaluate(shipment: Shipment, t: Telemetry): Violation[] {
  const out: Violation[] = [];

  if (t.tempC > shipment.maxTempC) {
    out.push({
      kind: "TEMPERATURE_HIGH",
      message: `Temperature ${t.tempC.toFixed(1)}°C exceeds max ${shipment.maxTempC}°C`,
      observed: t.tempC,
      threshold: shipment.maxTempC,
    });
  } else if (t.tempC < shipment.minTempC) {
    out.push({
      kind: "TEMPERATURE_LOW",
      message: `Temperature ${t.tempC.toFixed(1)}°C below min ${shipment.minTempC}°C`,
      observed: t.tempC,
      threshold: shipment.minTempC,
    });
  }

  if (t.shockG > shipment.maxShockG) {
    out.push({
      kind: "SHOCK",
      message: `Shock ${t.shockG.toFixed(2)}G exceeds max ${shipment.maxShockG}G`,
      observed: t.shockG,
      threshold: shipment.maxShockG,
    });
  }

  const fence = shipment.geofence as
    | { lat: number; lng: number; radiusKm: number }
    | null
    | undefined;
  if (fence && t.lat != null && t.lng != null) {
    const d = distanceKm({ lat: t.lat, lng: t.lng }, fence);
    if (d > fence.radiusKm) {
      out.push({
        kind: "GEOFENCE",
        message: `Outside geofence by ${(d - fence.radiusKm).toFixed(1)}km`,
        observed: d,
        threshold: fence.radiusKm,
      });
    }
  }

  return out;
}

export async function processTelemetry(
  shipmentId: string,
  telemetryId: string
) {
  const shipment = await prisma.shipment.findUniqueOrThrow({
    where: { id: shipmentId },
  });
  const telemetry = await prisma.telemetry.findUniqueOrThrow({
    where: { id: telemetryId },
  });

  const violations = evaluate(shipment, telemetry);

  if (violations.length === 0) {
    await prisma.device.updateMany({
      where: { shipmentId },
      data: { lastSeenAt: new Date() },
    });
    return { ok: true, violations: [] as Violation[] };
  }

  await prisma.$transaction(async (tx) => {
    for (const v of violations) {
      await tx.event.create({
        data: {
          shipmentId,
          kind: "VIOLATION",
          violation: v.kind,
          message: v.message,
          meta: {
            observed: v.observed,
            threshold: v.threshold,
            telemetryId,
          },
        },
      });
    }

    if (shipment.status === "IN_TRANSIT") {
      await tx.shipment.update({
        where: { id: shipmentId },
        data: { status: "COMPROMISED" },
      });
      await tx.event.create({
        data: {
          shipmentId,
          kind: "STATUS_CHANGE",
          message: "Shipment marked COMPROMISED — Arbitrator quorum reached.",
        },
      });
    }

    if (shipment.contractAddress && shipment.chainId) {
      const reason = violations.map((v) => v.message).join("; ");
      const refund = await tx.refundTx.upsert({
        where: { shipmentId },
        create: {
          shipmentId,
          contractAddress: shipment.contractAddress,
          chainId: shipment.chainId,
          method: "triggerRefund(bytes32,string)",
          args: {
            trackingCode: shipment.trackingCode,
            reason,
            payer: shipment.payerAddress,
          },
          reason,
        },
        update: { reason },
      });
      await tx.event.create({
        data: {
          shipmentId,
          kind: "REFUND_STAGED",
          message: `Refund staged · staked funds locked for release on chain ${shipment.chainId}.`,
          meta: {
            contractAddress: shipment.contractAddress,
            refundTxId: refund.id,
          },
        },
      });
    }
  });

  return { ok: false, violations };
}
