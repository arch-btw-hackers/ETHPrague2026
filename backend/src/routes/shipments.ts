// REST surface consumed by the dashboard.
// GET /api/shipments              — list with latest sample + status.
// GET /api/shipments/:code        — full detail for one shipment.
// POST /api/shipments/:code/deliver — mark delivered (carrier action).
// POST /api/shipments/:code/judge — kick off Supreme Judge review.

import { Router } from "express";
import { prisma } from "../db";
import { reviewRefund } from "../services/judge";
import { getInsight } from "../services/insights";
import { chatWithJudge, renderReport } from "../services/judgechat";

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

// AI chat — operator asks the Supreme Judge a free-form question and gets
// a forensic, telemetry-grounded reply.
shipmentsRouter.post("/:code/chat", async (req, res) => {
  const shipment = await prisma.shipment.findUnique({
    where: { trackingCode: req.params.code },
  });
  if (!shipment) return res.status(404).json({ error: "NOT_FOUND" });
  const question = String(req.body?.question ?? "").trim();
  if (!question) return res.status(400).json({ error: "EMPTY" });
  const history = Array.isArray(req.body?.history) ? req.body.history : [];
  const result = await chatWithJudge(shipment.id, question.slice(0, 600), history);
  res.json(result);
});

// Forensic PDF report — downloadable, branded, AI-summarised.
shipmentsRouter.get("/:code/report.pdf", async (req, res) => {
  const shipment = await prisma.shipment.findUnique({
    where: { trackingCode: req.params.code },
  });
  if (!shipment) return res.status(404).json({ error: "NOT_FOUND" });
  try {
    const buf = await renderReport(shipment.id);
    res.setHeader("content-type", "application/pdf");
    res.setHeader(
      "content-disposition",
      `inline; filename="vibetrack-${shipment.trackingCode}.pdf"`
    );
    res.send(buf);
  } catch (e) {
    console.error("[report]", e);
    res.status(500).json({ error: "REPORT_FAILED" });
  }
});
