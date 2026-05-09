// POST /api/telemetry — entrypoint for hardware (SpaceComputer) trackers.
// Validates payload, persists raw sample, then hands off to the Arbitrator.

import { Router } from "express";
import { z } from "zod";
import { prisma } from "../db";
import { processTelemetry } from "../services/arbitrator";

export const telemetryRouter = Router();

const TelemetrySchema = z.object({
  // Either trackingCode + apiKey, or deviceSerial + apiKey.
  trackingCode: z.string().min(3).optional(),
  deviceSerial: z.string().min(3).optional(),
  tempC: z.number().finite(),
  shockG: z.number().finite().nonnegative(),
  lat: z.number().finite().optional(),
  lng: z.number().finite().optional(),
  battery: z.number().finite().optional(),
  raw: z.record(z.any()).optional(),
});

telemetryRouter.post("/", async (req, res) => {
  const parsed = TelemetrySchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: "INVALID_PAYLOAD", details: parsed.error.flatten() });
  }
  const body = parsed.data;
  const apiKey = req.header("x-device-key");

  // Resolve the bound shipment via the device's API key.
  const device = await prisma.device.findFirst({
    where: {
      apiKey: apiKey ?? "__missing__",
      ...(body.deviceSerial ? { serial: body.deviceSerial } : {}),
      ...(body.trackingCode
        ? { shipment: { trackingCode: body.trackingCode } }
        : {}),
    },
    include: { shipment: true },
  });

  if (!device) return res.status(401).json({ error: "UNAUTHORIZED_DEVICE" });
  if (device.shipment.status === "DELIVERED") {
    return res.status(409).json({ error: "SHIPMENT_DELIVERED" });
  }

  const telemetry = await prisma.telemetry.create({
    data: {
      shipmentId: device.shipmentId,
      tempC: body.tempC,
      shockG: body.shockG,
      lat: body.lat,
      lng: body.lng,
      battery: body.battery,
      raw: body.raw,
    },
  });

  const result = await processTelemetry(device.shipmentId, telemetry.id);

  return res.status(201).json({
    telemetryId: telemetry.id,
    healthy: result.ok,
    violations: result.violations,
  });
});
