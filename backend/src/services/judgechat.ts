// AI chat + PDF report — bound to a specific shipment for context.
//
// chatWithJudge() reuses the OpenAI configuration from insights.ts but with a
// different system prompt so the model speaks in the operator's voice instead
// of returning JSON. If the API key is missing or the call fails, we fall
// back to a deterministic answer drawn from the live telemetry.
//
// renderReport() produces a styled PDF (pdfkit) summarising the shipment for
// the judges, including a vector Ethereum logo, key metrics, and the latest
// AI risk assessment.

import PDFDocument from "pdfkit";
import { prisma } from "../db";
import { getInsight } from "./insights";

interface ChatTurn { role: "user" | "assistant"; content: string }

const CHAT_SYSTEM = `You are the VibeTrack Supreme Judge — a calm, precise
forensic AI for a high-value RWA logistics platform. You analyse cold-chain
telemetry and answer operator questions about the shipment.

Style: forensic, expensive, silent. No filler. No emojis. Plain prose, max
3 short sentences. If the user asks for a number, give the number with units.
If asked about risk, cite a specific telemetry signal.`;

export interface ChatResult {
  answer: string;
  model: string;
}

export async function chatWithJudge(
  shipmentId: string,
  question: string,
  history: ChatTurn[] = []
): Promise<ChatResult> {
  const shipment = await prisma.shipment.findUniqueOrThrow({
    where: { id: shipmentId },
    include: {
      telemetries: { orderBy: { recordedAt: "desc" }, take: 12 },
      events: { orderBy: { createdAt: "desc" }, take: 6 },
    },
  });

  const last = shipment.telemetries[0];
  const facts =
    `Tracking ${shipment.trackingCode} · ${shipment.asset}\n` +
    `Route ${shipment.origin} → ${shipment.destination} · status ${shipment.status}\n` +
    `Thresholds: maxTemp ${shipment.maxTempC}°C · maxShock ${shipment.maxShockG}G\n` +
    (last
      ? `Latest sample: T=${last.tempC.toFixed(1)}°C · G=${last.shockG.toFixed(2)} · ` +
        `V=${last.speedKph?.toFixed(0) ?? "-"} kph · battery ${last.battery?.toFixed(0) ?? "-"}%\n`
      : "No telemetry yet.\n") +
    `Recent events:\n${shipment.events
      .map((e) => `  · ${e.kind}: ${e.message}`)
      .join("\n") || "  · none"}`;

  const key = process.env.OPENAI_API_KEY;
  if (!key) return { answer: localAnswer(question, facts), model: "heuristic" };

  const model = process.env.OPENAI_MODEL ?? "gpt-4o-mini";
  try {
    const r = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${key}`,
      },
      body: JSON.stringify({
        model,
        temperature: 0.3,
        messages: [
          { role: "system", content: CHAT_SYSTEM },
          { role: "system", content: `Live shipment context:\n${facts}` },
          ...history.slice(-6),
          { role: "user", content: question },
        ],
      }),
    });
    if (!r.ok) return { answer: localAnswer(question, facts), model: "heuristic" };
    const data = await r.json();
    const content = data.choices?.[0]?.message?.content?.trim();
    if (!content) return { answer: localAnswer(question, facts), model: "heuristic" };
    return { answer: content.slice(0, 800), model };
  } catch {
    return { answer: localAnswer(question, facts), model: "heuristic" };
  }
}

function localAnswer(_q: string, facts: string): string {
  return `Operating offline. Snapshot:\n${facts}`;
}

// ---------------------------------------------------------------------------
// PDF report
// ---------------------------------------------------------------------------

const ETH_PATH_TOP =
  // Ethereum diamond — top half (filled), drawn relative to (0,0).
  "M 32 0 L 0 52 L 32 38 L 64 52 Z";
const ETH_PATH_BOTTOM = "M 32 96 L 0 60 L 32 78 L 64 60 Z";

export async function renderReport(shipmentId: string): Promise<Buffer> {
  const shipment = await prisma.shipment.findUniqueOrThrow({
    where: { id: shipmentId },
    include: {
      telemetries: { orderBy: { recordedAt: "desc" }, take: 120 },
    },
  });
  const insight = await getInsight(shipmentId, false);

  const doc = new PDFDocument({ size: "A4", margin: 56 });
  const chunks: Buffer[] = [];
  doc.on("data", (c) => chunks.push(c as Buffer));
  const done = new Promise<Buffer>((resolve) => {
    doc.on("end", () => resolve(Buffer.concat(chunks)));
  });

  const PAGE_W = doc.page.width;
  const MARGIN = 56;

  // ---------- Header band ----------
  doc.rect(0, 0, PAGE_W, 96).fill("#050708");
  doc.save().translate(MARGIN, 24);
  // Ethereum mark, scaled.
  doc.save().scale(0.5);
  doc.fillColor("#7B8CFF").path(ETH_PATH_TOP).fill();
  doc.fillColor("#A4B0FF").path(ETH_PATH_BOTTOM).fill();
  doc.restore();
  doc.fillColor("#E6E9EF").font("Helvetica-Bold").fontSize(11)
    .text("VIBETRACK", 56, 18, { characterSpacing: 4 });
  doc.fillColor("#7A8190").font("Helvetica").fontSize(8)
    .text("INTELLIGENCE HUB · FORENSIC LOGISTICS REPORT", 56, 34, {
      characterSpacing: 2,
    });
  doc.restore();

  doc.fillColor("#7A8190").font("Helvetica").fontSize(8)
    .text(`Generated ${new Date().toUTCString()}`, MARGIN, 64, {
      characterSpacing: 1,
    });

  // ---------- Title ----------
  doc.fillColor("#0B0D10");
  let y = 128;
  doc.font("Helvetica").fontSize(9).fillColor("#9099AA")
    .text("CASE", MARGIN, y, { characterSpacing: 3 });
  y += 14;
  doc.font("Helvetica-Bold").fontSize(22).fillColor("#0B0D10")
    .text(`${shipment.trackingCode} — ${shipment.asset}`, MARGIN, y, {
      width: PAGE_W - MARGIN * 2,
    });
  y = doc.y + 8;
  doc.font("Helvetica").fontSize(10).fillColor("#4A5160")
    .text(`${shipment.origin}  →  ${shipment.destination}`, MARGIN, y);
  y = doc.y + 18;

  // ---------- Verdict box ----------
  const verdictColor =
    insight.riskLabel === "CRITICAL"
      ? "#D9480F"
      : insight.riskLabel === "ELEVATED"
      ? "#C58B00"
      : insight.riskLabel === "MODERATE"
      ? "#0E7C7B"
      : "#1F8A4C";
  doc.roundedRect(MARGIN, y, PAGE_W - MARGIN * 2, 76, 8)
    .lineWidth(0.5).strokeColor("#D7DBE2").fillAndStroke("#FAFBFC", "#D7DBE2");
  doc.fillColor("#9099AA").font("Helvetica").fontSize(8)
    .text("RISK SCORE", MARGIN + 16, y + 14, { characterSpacing: 3 });
  doc.fillColor(verdictColor).font("Helvetica-Bold").fontSize(34)
    .text(`${insight.riskScore.toFixed(0)}`, MARGIN + 16, y + 28);
  doc.fillColor("#9099AA").font("Helvetica").fontSize(8)
    .text("STATUS", MARGIN + 130, y + 14, { characterSpacing: 3 });
  doc.fillColor(verdictColor).font("Helvetica-Bold").fontSize(14)
    .text(insight.riskLabel, MARGIN + 130, y + 32);
  doc.fillColor("#9099AA").font("Helvetica").fontSize(8)
    .text("HEADLINE", MARGIN + 240, y + 14, { characterSpacing: 3 });
  doc.fillColor("#0B0D10").font("Helvetica-Bold").fontSize(11)
    .text(insight.headline, MARGIN + 240, y + 30, {
      width: PAGE_W - MARGIN - 240 - 16,
    });
  y += 96;

  // ---------- Telemetry stats ----------
  const last = shipment.telemetries[shipment.telemetries.length - 1];
  const tempVals = shipment.telemetries.map((t) => t.tempC);
  const shockVals = shipment.telemetries.map((t) => t.shockG);
  const stat = (vals: number[]) => ({
    avg: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0,
    max: vals.length ? Math.max(...vals) : 0,
    min: vals.length ? Math.min(...vals) : 0,
  });
  const tStat = stat(tempVals);
  const gStat = stat(shockVals);

  drawSectionLabel(doc, "TELEMETRY ENVELOPE", MARGIN, y);
  y += 22;
  drawKV(doc, "Samples", `${shipment.telemetries.length}`, MARGIN, y);
  drawKV(doc, "Temp", `min ${tStat.min.toFixed(1)} · avg ${tStat.avg.toFixed(1)} · max ${tStat.max.toFixed(1)} °C`, MARGIN + 140, y);
  y += 16;
  drawKV(doc, "Threshold", `${shipment.maxTempC}°C max`, MARGIN, y);
  drawKV(doc, "Shock", `min ${gStat.min.toFixed(2)} · avg ${gStat.avg.toFixed(2)} · max ${gStat.max.toFixed(2)} G`, MARGIN + 140, y);
  y += 16;
  if (last) {
    drawKV(
      doc,
      "Last sample",
      `${new Date(last.recordedAt).toUTCString()}  ·  ${last.lat?.toFixed(4)}, ${last.lng?.toFixed(4)}`,
      MARGIN,
      y
    );
    y += 18;
  }

  // ---------- AI summary ----------
  y += 8;
  drawSectionLabel(doc, "EXECUTIVE SUMMARY", MARGIN, y);
  y += 22;
  doc.fillColor("#0B0D10").font("Helvetica").fontSize(11)
    .text(insight.summary || "—", MARGIN, y, {
      width: PAGE_W - MARGIN * 2,
      lineGap: 3,
    });
  y = doc.y + 14;

  if (insight.anomalies.length) {
    drawSectionLabel(doc, "ANOMALIES", MARGIN, y);
    y += 18;
    for (const a of insight.anomalies) {
      doc.fillColor("#0B0D10").font("Helvetica").fontSize(10).text(`·  ${a}`, MARGIN + 6, y, {
        width: PAGE_W - MARGIN * 2 - 6,
      });
      y = doc.y + 4;
    }
    y += 10;
  }

  if (insight.recommendations.length) {
    drawSectionLabel(doc, "RECOMMENDED ACTIONS", MARGIN, y);
    y += 18;
    for (const a of insight.recommendations) {
      doc.fillColor("#0B0D10").font("Helvetica").fontSize(10).text(`·  ${a}`, MARGIN + 6, y, {
        width: PAGE_W - MARGIN * 2 - 6,
      });
      y = doc.y + 4;
    }
    y += 10;
  }

  // ---------- Identity / contract ----------
  drawSectionLabel(doc, "ON-CHAIN IDENTITY", MARGIN, y);
  y += 22;
  drawKV(doc, "Contract", shipment.contractAddress ?? "—", MARGIN, y); y += 16;
  drawKV(doc, "Chain ID", String(shipment.chainId ?? "—"), MARGIN, y); y += 16;
  drawKV(doc, "Payer", shipment.payerAddress ?? "—", MARGIN, y); y += 16;
  drawKV(doc, "Carrier", shipment.carrierAddress ?? "—", MARGIN, y); y += 16;

  // ---------- Footer ----------
  const footY = doc.page.height - 60;
  doc.moveTo(MARGIN, footY).lineTo(PAGE_W - MARGIN, footY)
    .lineWidth(0.5).strokeColor("#E1E4EA").stroke();
  doc.fillColor("#9099AA").font("Helvetica").fontSize(8)
    .text(`Model ${insight.model}  ·  Forecast horizon ${insight.forecast.length} steps  ·  vibetrack.eth`,
      MARGIN, footY + 10, { width: PAGE_W - MARGIN * 2, align: "center", characterSpacing: 2 });

  doc.end();
  return done;
}

function drawSectionLabel(doc: PDFKit.PDFDocument, label: string, x: number, y: number) {
  doc.fillColor("#9099AA").font("Helvetica-Bold").fontSize(8)
    .text(label, x, y, { characterSpacing: 3 });
  doc.moveTo(x, y + 14).lineTo(x + 56, y + 14)
    .lineWidth(1).strokeColor("#0B0D10").stroke();
}

function drawKV(doc: PDFKit.PDFDocument, k: string, v: string, x: number, y: number) {
  doc.fillColor("#9099AA").font("Helvetica").fontSize(8)
    .text(k.toUpperCase(), x, y, { characterSpacing: 2 });
  doc.fillColor("#0B0D10").font("Helvetica").fontSize(10)
    .text(v, x, y + 11, { width: 380 });
}
