// Live demo simulator.
// When DEMO=1 is set, the hub advances every IN_TRANSIT shipment along its
// pre-computed driving polyline (Shipment.routePath) and emits a fresh
// telemetry sample. The package "drives" the real road every 2 seconds.

import { prisma } from "../db";
import { processTelemetry } from "./arbitrator";

// Number of route vertices to advance per tick.
// Smaller = slower, smoother. Bigger = faster, jumpier.
const STEP_PER_TICK = 2;
const TICK_MS = 2000;

async function tick() {
  const shipments = await prisma.shipment.findMany({
    where: { status: "IN_TRANSIT", routePath: { not: undefined } },
    include: {
      telemetries: { orderBy: { recordedAt: "desc" }, take: 1 },
    },
  });

  for (const s of shipments) {
    const path = s.routePath as [number, number][] | null;
    if (!path || path.length < 2) continue;

    const nextIndex = Math.min(path.length - 1, s.routeIndex + STEP_PER_TICK);
    const [lng, lat] = path[nextIndex];
    const last = s.telemetries[0];

    const now = Date.now();
    // Geographic context — Pyrenees crossing pulls temperature down and adds
    // road vibration, mirroring real altitude effects.
    const inPyrenees = lat > 42.0 && lat < 43.4 && lng > -1.0 && lng < 3.0;
    const inAndalusia = lat < 38.0 && lng < 0;
    const tempBias = inPyrenees ? -2.4 : inAndalusia ? 1.6 : 0;
    const shockBias = inPyrenees ? 0.25 : 0;
    const tempC =
      4 + tempBias + Math.sin(now / 90_000) * 1.6 + (Math.random() - 0.5) * 0.6;
    const shockG = 0.3 + shockBias + Math.random() ** 2 * 1.2; // mostly small, rare spikes
    const humidity =
      48 + Math.sin(now / 120_000) * 6 + (Math.random() - 0.5) * 1.5;
    const tilt = Math.abs(Math.sin(now / 18_000)) * 5 + Math.random() * 0.6;
    const speedKph =
      75 + Math.sin(now / 40_000) * 30 + (Math.random() - 0.5) * 5;

    const telemetry = await prisma.telemetry.create({
      data: {
        shipmentId: s.id,
        tempC,
        shockG,
        humidity,
        tilt,
        speedKph,
        lat,
        lng,
        battery: Math.max(15, (last?.battery ?? 90) - 0.04),
      },
    });

    await prisma.shipment.update({
      where: { id: s.id },
      data: {
        routeIndex: nextIndex,
        // Auto-deliver when the head reaches the end of the route.
        ...(nextIndex >= path.length - 1
          ? { status: "DELIVERED" as const }
          : {}),
      },
    });

    if (nextIndex >= path.length - 1) {
      await prisma.event.create({
        data: {
          shipmentId: s.id,
          kind: "STATUS_CHANGE",
          message: "Shipment marked DELIVERED — destination reached.",
        },
      });
    }

    await processTelemetry(s.id, telemetry.id);
  }
}

export function startSimulator() {
  if (process.env.DEMO !== "1") return;
  console.log(`● demo simulator running (DEMO=1) — tick every ${TICK_MS}ms`);
  setInterval(() => {
    tick().catch((e) => console.error("[simulator]", e));
  }, TICK_MS);
}
