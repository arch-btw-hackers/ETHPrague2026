// REST surface consumed by the dashboard.
// GET /api/shipments              — list with latest sample + status.
// GET /api/shipments/:code        — full detail for one shipment.
// POST /api/shipments/:code/deliver — mark delivered (carrier action).
// POST /api/shipments/:code/judge — kick off Supreme Judge review.

import { Router } from "express";
import { prisma } from "../db";
import { reviewRefund } from "../services/judge";
import { getInsight } from "../services/insights";

export const shipmentsRouter = Router();

shipmentsRouter.get("/", async (_req, res) => {
  const shipments = await prisma.shipment.findMany({
    orderBy: { updatedAt: "desc" },
    include: {
      telemetries: { orderBy: { recordedAt: "desc" }, take: 1 },
      refundTx: true,
    },
  });
  res.json(shipments);
});

shipmentsRouter.get("/:code", async (req, res) => {
  const shipment = await prisma.shipment.findUnique({
    where: { trackingCode: req.params.code },
    include: {
      telemetries: { orderBy: { recordedAt: "desc" }, take: 120 },
      events: { orderBy: { createdAt: "desc" }, take: 80 },
      refundTx: true,
      device: { select: { serial: true, lastSeenAt: true } },
    },
  });
  if (!shipment) return res.status(404).json({ error: "NOT_FOUND" });

  // Telemetries arrive newest-first; the chart wants oldest-first.
  shipment.telemetries.reverse();
  res.json(shipment);
});

shipmentsRouter.post("/:code/deliver", async (req, res) => {
  const shipment = await prisma.shipment.findUnique({
    where: { trackingCode: req.params.code },
  });
  if (!shipment) return res.status(404).json({ error: "NOT_FOUND" });
  if (shipment.status === "COMPROMISED") {
    return res.status(409).json({ error: "CANNOT_DELIVER_COMPROMISED" });
  }
  await prisma.$transaction([
    prisma.shipment.update({
      where: { id: shipment.id },
      data: { status: "DELIVERED" },
    }),
    prisma.event.create({
      data: {
        shipmentId: shipment.id,
        kind: "STATUS_CHANGE",
        message: "Shipment marked DELIVERED.",
      },
    }),
  ]);
  res.json({ ok: true });
});

shipmentsRouter.post("/:code/judge", async (req, res) => {
  const shipment = await prisma.shipment.findUnique({
    where: { trackingCode: req.params.code },
  });
  if (!shipment) return res.status(404).json({ error: "NOT_FOUND" });
  const verdict = await reviewRefund(shipment.id);
  if (!verdict) return res.status(409).json({ error: "NO_REFUND_PREPARED" });
  res.json(verdict);
});

// AI Insights — cached for 30s, force=1 forces a refresh.
shipmentsRouter.get("/:code/insights", async (req, res) => {
  const shipment = await prisma.shipment.findUnique({
    where: { trackingCode: req.params.code },
  });
  if (!shipment) return res.status(404).json({ error: "NOT_FOUND" });
  const insight = await getInsight(shipment.id, req.query.force === "1");
  res.json(insight);
});
