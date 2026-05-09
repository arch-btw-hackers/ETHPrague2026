// Demo seed.
// Builds a real highway-aligned route Prague → Nuremberg → Lyon → Barcelona →
// Málaga via the public OSRM router, stores the polyline, and backfills
// telemetry along the first ~25% of the route so the dashboard opens with a
// fully drawn road trail and a moving package head.

import { PrismaClient } from "@prisma/client";
import { randomBytes } from "crypto";

const prisma = new PrismaClient();

// Highway-aligned waypoints (lng, lat). OSRM walks the road network through
// every one of them in order, producing a real driving polyline that hugs
// E50 → E15 → AP-7 → A-7.
const WAYPOINTS: { name: string; lng: number; lat: number }[] = [
  { name: "Prague, CZ",     lng: 14.4378, lat: 50.0755 },
  { name: "Nuremberg, DE",  lng: 11.0767, lat: 49.4521 },
  { name: "Lyon, FR",       lng:  4.8357, lat: 45.7640 },
  { name: "Barcelona, ES",  lng:  2.1734, lat: 41.3851 },
  { name: "Málaga, ES",     lng: -4.4214, lat: 36.7213 },
];

interface OsrmResponse {
  routes: {
    geometry: { coordinates: [number, number][] };
    distance: number;
    duration: number;
  }[];
}

async function fetchRoute(): Promise<{
  coords: [number, number][];
  distanceM: number;
  durationS: number;
}> {
  const path = WAYPOINTS.map((w) => `${w.lng},${w.lat}`).join(";");
  const url = `https://router.project-osrm.org/route/v1/driving/${path}?overview=full&geometries=geojson`;
  const r = await fetch(url, {
    headers: { "User-Agent": "VibeTrack/0.2 (+https://vibetrack.local)" },
  });
  if (!r.ok) throw new Error(`OSRM ${r.status}`);
  const data = (await r.json()) as OsrmResponse;
  const route = data.routes[0];
  if (!route) throw new Error("OSRM returned no routes");
  return {
    coords: route.geometry.coordinates,
    distanceM: route.distance,
    durationS: route.duration,
  };
}

function downsample<T>(arr: T[], count: number): T[] {
  if (arr.length <= count) return arr;
  const out: T[] = [];
  const step = (arr.length - 1) / (count - 1);
  for (let i = 0; i < count; i++) out.push(arr[Math.round(i * step)]);
  return out;
}

async function main() {
  const trackingCode = "VBT-0001";
  await prisma.shipment.deleteMany({ where: { trackingCode } });

  console.log("→ Fetching highway route Prague → Málaga from OSRM…");
  const { coords, distanceM, durationS } = await fetchRoute();
  const path = downsample(coords, 800);
  console.log(
    `  ✓ ${coords.length} raw points · ${(distanceM / 1000).toFixed(0)} km · ` +
      `${Math.round(durationS / 3600)}h drive`
  );

  const startedAt = Date.now() - durationS * 1000 * 0.25;
  const etaAt = new Date(startedAt + durationS * 1000);
  const initialIndex = Math.floor(path.length * 0.25);

  const shipment = await prisma.shipment.create({
    data: {
      trackingCode,
      asset: "Patek Philippe Nautilus 5711 — vault transfer",
      origin: WAYPOINTS[0].name,
      destination: WAYPOINTS[WAYPOINTS.length - 1].name,
      status: "IN_TRANSIT",
      contractAddress: "0x1234567890abcdef1234567890abcdef12345678",
      chainId: 8453,
      payerAddress: "0xPAYER000000000000000000000000000000000001",
      carrierAddress: "0xCARRIER0000000000000000000000000000000002",
      maxTempC: 8,
      minTempC: -5,
      maxShockG: 5,
      routePath: path,
      routeIndex: initialIndex,
      etaAt,
    },
  });

  const apiKey = randomBytes(16).toString("hex");
  await prisma.device.create({
    data: { serial: "SC-DEV-0001", apiKey, shipmentId: shipment.id },
  });

  // Backfill samples evenly across the first ~25% of the route.
  const SAMPLES = 120;
  const now = Date.now();
  const stepMs = (durationS * 1000 * 0.25) / SAMPLES;
  for (let i = 0; i < SAMPLES; i++) {
    const idx = Math.floor((i / (SAMPLES - 1)) * initialIndex);
    const [lng, lat] = path[idx];
    // Pyrenees pseudo-altitude awareness for backfill: a slight cool dip if
    // we're near the lat/lng box of the Pyrenees crossing.
    const inPyrenees = lat > 42.0 && lat < 43.4 && lng > -1.0 && lng < 3.0;
    const tempBase = inPyrenees ? 1.6 : 4.0;
    await prisma.telemetry.create({
      data: {
        shipmentId: shipment.id,
        tempC: tempBase + Math.sin(i / 6) * 1.2 + (Math.random() - 0.5) * 0.4,
        shockG: 0.3 + Math.random() * 0.5,
        humidity: 45 + Math.sin(i / 8) * 6 + (Math.random() - 0.5) * 1.2,
        tilt: Math.abs(Math.sin(i / 4)) * 4 + (Math.random() - 0.5) * 0.6,
        speedKph: 80 + Math.sin(i / 5) * 25 + (Math.random() - 0.5) * 6,
        lat,
        lng,
        battery: Math.max(40, 95 - i * 0.25),
        recordedAt: new Date(now - (SAMPLES - i) * stepMs),
      },
    });
  }

  console.log("✓ Seeded shipment :", trackingCode);
  console.log("✓ Device API key  :", apiKey);
  console.log("→ Run with DEMO=1 to keep the tracker advancing live.");
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
